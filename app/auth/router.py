from fastapi import APIRouter, Response, Depends, Body
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
import io
import base64
from typing import Optional, Union, List, Dict, Any

from app.auth.models import User, CommandsUser, Command, InsiderInfo
from app.auth.utils import set_tokens, generate_qr_image
from app.dependencies.auth_dep import get_access_token, get_current_user
from app.dependencies.dao_dep import get_session_with_commit, get_session_without_commit
from app.auth.dao import CommandsDAO, CommandsUsersDAO, RolesUsersCommandDAO, UsersDAO, SessionDAO, EventsDAO, RolesDAO, InsidersInfoDAO
from app.auth.schemas import CommandBase, CommandInfo, CommandName, CommandEdit, CommandsUserBase, CompleteRegistrationRequest, RoleModel, SUserInfo, TelegramAuthData, UserFindCompleteRegistration, UserMakeCompleteRegistration, UserTelegramID, SUserAddDB, EventID, ParticipantInfo, RoleFilter, UpdateProfileRequest
from fastapi.responses import JSONResponse, StreamingResponse
from app.exceptions import InternalServerErrorException, TokenExpiredException
from app.logger import logger
from app.config import settings
from fastapi import status

router = APIRouter()

# Аутентификация и авторизация
# ===========================

@router.post("/telegram")
async def telegram_auth(
    user_data: TelegramAuthData,
    session: AsyncSession = Depends(get_session_with_commit)
):
    users_dao = UsersDAO(session)
    session_dao = SessionDAO(session)

    # Проверяем, существует ли пользователь
    user = await users_dao.find_one_or_none(
        filters=UserTelegramID(telegram_id=user_data.id)
    )
    if not user: 
        # Создаём нового пользователя
        new_user = await users_dao.add(
            values=SUserAddDB(
                full_name=user_data.first_name,
                telegram_id=user_data.id,
                telegram_username=user_data.username
            )
        )
        user = new_user

    # Создаём сессию с помощью DAO
    session_token = await session_dao.create_session(user.id)
    
    # Проверяем наличие кода регистрации для инсайдера
    registration_type = "default"
    
    # Если передан код регистрации и он указывает на инсайдера
    if user_data.registration_code and user_data.registration_code == "insider":
        registration_type = "insider"
        
    response = JSONResponse(
        content={
            "ok": True,
            "message": "Telegram authentication successful",
            "user": {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "full_name": user.full_name,
                "telegram_username": user.telegram_username,
                "is_active": user.role_id is not None
            },
            "registration_type": registration_type
        }
    )
    set_tokens(response, session_token)
    return response


@router.post("/complete-registration")
async def complete_registration(
    request: CompleteRegistrationRequest,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    users_dao = UsersDAO(session)
    roles_dao = RolesDAO(session)
    
    # Определяем роль пользователя (инсайдер или гость)
    role_name = "guest"
    
    # Если есть данные студенческой организации, значит это инсайдер
    if request.student_organization:
        role_name = "insider"
        
    # Получаем ID роли
    role = await roles_dao.find_one_or_none(filters=RoleFilter(name=role_name))
    if not role:
        logger.error(f"Роль {role_name} не найдена")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": "Ошибка при выборе роли пользователя"}
        )
    
    # Обновляем данные пользователя
    await users_dao.update(
        filters=UserFindCompleteRegistration(id=user.id),
        values=UserMakeCompleteRegistration(full_name=request.full_name, role_id=role.id)
    )
    
    # Если это инсайдер, сохраняем дополнительную информацию
    if role_name == "insider" and (request.student_organization or request.geo_link):
        try:
            insiders_dao = InsidersInfoDAO(session)
            await insiders_dao.create_or_update(
                user_id=user.id, 
                student_organization=request.student_organization,
                geo_link=request.geo_link
            )
        except Exception as e:
            logger.error(f"Ошибка при сохранении информации инсайдера: {e}")
            return JSONResponse(
                status_code=500,
                content={"ok": False, "message": "Ошибка при сохранении дополнительной информации"}
            )
    
    return {
        "ok": True,
        "message": "Регистрация успешно завершена"
    }


@router.post("/logout")
async def logout(response: Response):
    # Удаляем основной токен сессии
    response.delete_cookie("session_token", path="/")
    # Удаляем альтернативный токен сессии
    response.delete_cookie("session_token_alt", path="/")
    
    return {'message': 'Пользователь успешно вышел из системы'}


# Пользователи и профили
# =====================

@router.get("/me")
async def get_me(
    user_data: Optional[User] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_with_commit)
):
    # Если пользователь не авторизован, возвращаем сообщение
    if not user_data:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"ok": False, "message": "Пользователь не авторизован"}
        )
    
    # Оптимизированный запрос с минимально необходимыми данными
    users_dao = UsersDAO(session)
    user = await users_dao.find_one_by_id(
        user_data.id,
        options=[
            selectinload(User.commands).joinedload(CommandsUser.command).joinedload(Command.users).joinedload(CommandsUser.user),
            selectinload(User.commands).joinedload(CommandsUser.command).joinedload(Command.users).joinedload(CommandsUser.role),
            selectinload(User.commands).joinedload(CommandsUser.role),
            selectinload(User.role),
            selectinload(User.insider_info)
        ]
    )
    
    # Оптимизированное формирование информации о командах
    commands_info = []
    for cu in user.commands:
        # Форматируем участников с помощью вспомогательной функции
        participants = format_participants(cu.command.users, include_role=True)
            
        command_info = CommandInfo(
            id=cu.command.id,
            name=cu.command.name,
            role=cu.role.name,
            event_id=cu.command.event_id,
            language_id=cu.command.language_id,
            participants=participants
        ).model_dump()
        
        commands_info.append(command_info)

    # Возвращаем информацию о пользователе
    user_info = {
        "id": user.id,
        "full_name": user.full_name,
        "telegram_id": user.telegram_id,
        "telegram_username": user.telegram_username,
        "role": RoleModel(id=user.role.id, name=user.role.name).model_dump() if user.role else None,
        "commands": commands_info,
        "is_looking_for_friends": user.is_looking_for_friends
    }
    
    # Добавляем информацию инсайдера, если пользователь - инсайдер
    if user.role and user.role.name == "insider" and user.insider_info:
        user_info["insider_info"] = {
            "student_organization": user.insider_info.student_organization,
            "geo_link": user.insider_info.geo_link
        }
    
    return user_info


@router.get("/qr")
async def get_me_qr_code(
    user_data: Optional[User] = Depends(get_current_user),
    session_token: Optional[str] = Depends(get_access_token),
):
    # Если пользователь не авторизован или токен отсутствует, возвращаем ошибку
    if not user_data or not session_token:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"ok": False, "message": "Пользователь не авторизован"}
        )
    
    # Генерация QR-кода с ссылкой на эндпоинт проверки
    qr_link = f"{settings.BASE_URL}/qr/verify?token={session_token}"
    qr_data = generate_qr_image(qr_link)
    
    # Возвращаем JSON с ссылкой и изображением
    return JSONResponse({
        "qr_link": qr_link,
        "qr_image": base64.b64encode(qr_data).decode("utf-8")  # Кодируем изображение в base64
    })

class QRVerifyRequest(BaseModel):
    token: str

@router.post("/toggle_looking_for_team")
async def toggle_looking_for_team(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_with_commit)
):
    """
    Переключает флаг is_looking_for_team у текущего пользователя
    """
    if not user:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"ok": False, "message": "Пользователь не авторизован"}
        )
    
    try:
        # Получаем свежую копию объекта пользователя из текущей сессии
        users_dao = UsersDAO(session)
        current_user = await users_dao.find_one_by_id(user.id)
        
        if not current_user:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"ok": False, "message": "Пользователь не найден"}
            )
        
        # Переключаем флаг
        current_user.is_looking_for_friends = not current_user.is_looking_for_friends
        await session.commit()
        
        return {"ok": True, "is_looking_for_friends": current_user.is_looking_for_friends}
    except Exception as e:
        logger.error(f"Ошибка при переключении флага is_looking_for_friends: {str(e)}")
        await session.rollback()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"ok": False, "message": "Ошибка сервера при обновлении статуса"}
        )

@router.post("/qr/verify")
async def verify_qr(
    request: QRVerifyRequest,
    scanner_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_without_commit)
):
    """
    Проверяет валидность сессионного токена.
    В зависимости от роли пользователя, который сканирует:
    - guest: показывает информацию о команде и возможность присоединения
    - insider/organizer: возвращает информацию о команде
    """
    if not scanner_user:
        logger.warning("Попытка проверки QR-кода неавторизованным пользователем")
        return JSONResponse(
            status_code=403,
            content={"detail": "Необходима авторизация для проверки QR-кода"}
        )
    
    logger.info(f"Начало проверки QR-кода. Сканирующий пользователь: {scanner_user.id}")
    
    # Получаем пользователя, чей QR сканируют, через get_current_user
    try:
        qr_user = await get_current_user(request.token, session)
        if not qr_user:
            logger.warning("Пользователь по QR-коду не найден")
            return JSONResponse(
                status_code=401,
                content={"detail": "Срок действия QR-кода или ссылки истек. Пожалуйста, получите новую ссылку в профиле."}
            )
    except Exception as e:
        logger.error(f"Ошибка при получении пользователя по QR-коду: {str(e)}")
        return JSONResponse(
            status_code=401,
            content={"detail": "Срок действия QR-кода или ссылки истек. Пожалуйста, получите новую ссылку в профиле."}
        )

    logger.info(f"Пользователь по QR-коду найден: {qr_user.id}")

    users_dao = UsersDAO(session)
    
    # Получаем команду пользователя, чей QR сканируют
    try:
        qr_user_command = await users_dao.find_user_command_in_event(user_id=qr_user.id)
        if not qr_user_command:
            logger.warning(f"Пользователь {qr_user.id} не состоит в команде")
            return {
                "ok": False,
                "message": "Пользователь не состоит в команде"
            }
    except Exception as e:
        logger.error(f"Ошибка при получении команды пользователя {qr_user.id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Ошибка при получении информации о команде. Пожалуйста, попробуйте позже."}
        )
    
    # Проверяем, что владелец QR - капитан
    qr_user_role, is_captain = get_user_role_in_command(qr_user_command.users, qr_user.id)
    if not is_captain:
        logger.warning(f"Пользователь {qr_user.id} не является капитаном команды")
        return {
            "ok": False,
            "message": "Только QR капитана команды позволяет присоединиться"
        }
    
    # Проверяем, состоит ли сканирующий пользователь уже в команде
    scanner_user_command = None
    try:
        scanner_user_command = await users_dao.find_user_command_in_event(user_id=scanner_user.id)
    except Exception as e:
        logger.error(f"Ошибка при проверке команды сканирующего пользователя: {str(e)}")
    
    # Обработка в зависимости от роли сканирующего
    if not scanner_user or not scanner_user.role or scanner_user.role.name not in ["insider", "organizer", "guest"]:
        logger.warning("Пользователь без роли пытается проверить QR-код")
        return {
            "ok": False,
            "message": "Недостаточно прав для проверки QR-кода"
        }
        
    if scanner_user.role.name in ["insider", "organizer"]:
        # Инсайдер или организатор - возвращаем полную информацию
        
        # Форматируем участников с помощью вспомогательной функции
        # Для QR-verify используем упрощенную версию (без ролей)
        participants = format_participants(qr_user_command.users, include_role=False)
        
        response_data = {
            "ok": True,
            "scanner_role": scanner_user.role.name,
            "is_captain": is_captain,
            "user": {
                "id": qr_user.id,
                "full_name": qr_user.full_name,
                "role": qr_user.role.name,
                "telegram_id": qr_user.telegram_id,
                "telegram_username": qr_user.telegram_username
            },
            "command": {
                "id": qr_user_command.id,
                "name": qr_user_command.name,
                "event_id": qr_user_command.event_id,
                "participants": participants
            }
        }
        
        can_join = scanner_user.role.name == "organizer" and not scanner_user_command and is_captain and len(qr_user_command.users) < 6
        
        response_data.update({
            "can_join": can_join,
            "join_reason": None if can_join else (
                "already_in_team" if scanner_user_command else
                "not_captain" if not is_captain else
                "team_full" if len(qr_user_command.users) >= 6 else
                "unknown"
            ),
            "command_name": qr_user_command.name,
            "captain_name": qr_user.full_name,
            "token": request.token
        })
        
        return response_data
    else:
        # Для гостей возвращаем сокращенную информацию с указанием причины, почему нельзя присоединиться
        can_join = is_captain and scanner_user_command is None and len(qr_user_command.users) < 6
        
        join_reason = (
            "already_in_team" if scanner_user_command is not None else
            "not_captain" if not is_captain else
            "team_full" if len(qr_user_command.users) >= 6 else
            None  # Если присоединение возможно, причина отсутствует
        ) if not can_join else None
        
        return {
            "ok": True,
            "message": "QR-код проверен",
            "can_join": can_join,
            "join_reason": join_reason,
            "command_name": qr_user_command.name,
            "captain_name": qr_user.full_name,
            "token": request.token
        }
    
    # Это условие не будет достигнуто из-за изменённого if-else, но оставим на всякий случай
    logger.warning(f"Роль пользователя не позволяет выполнить это действие")
    return {
        "ok": False,
        "message": "Ваша роль не позволяет выполнить это действие"
    }

# Новый маршрут для присоединения к команде
class JoinTeamRequest(BaseModel):
    token: str  # Токен QR-кода

@router.post("/command/join")
async def join_team(
    request: JoinTeamRequest,
    scanner_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_with_commit)
):
    """Присоединение к команде через QR-код"""
    logger.info(f"Запрос на присоединение к команде от пользователя {scanner_user.id}")
    
    # Проверяем, что пользователь авторизован
    if not scanner_user:
        logger.warning("Попытка присоединения к команде неавторизованным пользователем")
        return JSONResponse(
            status_code=403, # Используем 403 для ошибок авторизации
            content={"detail": "Необходима авторизация для присоединения к команде"}
        )
    
    # Получаем пользователя, чей QR сканировали
    try:
        qr_user = await get_current_user(request.token, session)
        if not qr_user:
            logger.warning("Пользователь по QR-коду не найден")
            return JSONResponse(
                status_code=401, # Оставляем 401 для недействительных токенов
                content={"detail": "Срок действия QR-кода или ссылки истек. Пожалуйста, получите новую ссылку в профиле."}
            )
    except Exception as e:
        logger.error(f"Ошибка при получении пользователя по QR-коду: {str(e)}")
        return JSONResponse(
            status_code=401,
            content={"detail": "Срок действия QR-кода или ссылки истек. Пожалуйста, получите новую ссылку в профиле."}
        )

    users_dao = UsersDAO(session)
    commands_users_dao = CommandsUsersDAO(session)
    roles_dao = RolesDAO(session)
    
    # Получаем команду пользователя, чей QR сканировали
    try:
        qr_user_command = await users_dao.find_user_command_in_event(user_id=qr_user.id)
        if not qr_user_command:
            logger.warning(f"Пользователь {qr_user.id} не состоит в команде")
            return {
                "ok": False,
                "message": "Пользователь не состоит в команде"
            }
    except Exception as e:
        logger.error(f"Ошибка при получении команды пользователя {qr_user.id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Ошибка при получении информации о команде. Пожалуйста, обратитесь к организаторам."}
        )
    
    # Проверяем, что владелец QR - капитан
    qr_user_role, is_captain = get_user_role_in_command(qr_user_command.users, qr_user.id)
    if not is_captain:
        logger.warning(f"Пользователь {qr_user.id} не является капитаном команды")
        return {
            "ok": False,
            "message": "Только QR капитана команды позволяет присоединиться"
        }
    
    # Проверяем, не состоит ли уже пользователь в команде
    scanner_user_command = await users_dao.find_user_command_in_event(user_id=scanner_user.id)
    if scanner_user_command:
        logger.warning(f"Пользователь {scanner_user.id} уже состоит в команде {scanner_user_command.id}")
        return {
            "ok": False,
            "message": "Вы уже состоите в другой команде"
        }
    
    # Проверяем, не состоит ли пользователь уже в этой команде
    if any(cu.user_id == scanner_user.id for cu in qr_user_command.users):
        logger.warning(f"Пользователь {scanner_user.id} уже состоит в этой команде")
        return {
            "ok": False,
            "message": "Вы уже состоите в этой команде"
        }
    
    # Проверяем максимальное количество участников
    if len(qr_user_command.users) >= 6:
        logger.warning(f"Команда {qr_user_command.id} уже имеет максимальное количество участников")
        return {
            "ok": False,
            "message": "В команде уже максимальное количество участников"
        }
    
    # Получаем роль для участника команды
    try:
        # Используем RolesUsersCommandDAO для получения роли участника
        roles_users_dao = RolesUsersCommandDAO(session)
        member_role_id = await roles_users_dao.get_role_id(role_name="member")
        
        if not member_role_id:
            logger.error("Роль 'member' не найдена в базе данных")
            return JSONResponse(
                status_code=500,
                content={"detail": "Внутренняя ошибка сервера. Пожалуйста, обратитесь к организаторам."}
            )
        
        # Добавляем пользователя в команду с ролью участника
        await commands_users_dao.add(CommandsUserBase(
            command_id=qr_user_command.id,
            user_id=scanner_user.id,
            role_id=member_role_id
        ))
        
        logger.info(f"Пользователь {scanner_user.id} успешно добавлен в команду {qr_user_command.id}")
        return {
            "ok": True,
            "message": "Вы успешно добавлены в команду"
        }
    except Exception as e:
        logger.error(f"Ошибка при добавлении пользователя {scanner_user.id} в команду {qr_user_command.id}: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Ошибка при добавлении в команду. Пожалуйста, обратитесь к организаторам."}
        )


# Управление командами
# ==================

@router.get("/command")
async def get_user_command(
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
) -> CommandInfo:
    users_dao = UsersDAO(session)
    command = await users_dao.find_user_command_in_event(user_id=user.id)
    return CommandInfo.model_validate(command)


@router.post("/command/create")
async def command_create(
    request: CommandEdit,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    logger.info(f"Попытка создания команды пользователем {user.id} с именем {request.name}")
    
    try:
        # Получаем текущее событие
        event_dao = EventsDAO(session)
        curr_event_id = await event_dao.get_event_id_by_name()
        
        if not curr_event_id:
            logger.error("Не удалось получить ID текущего события")
            return JSONResponse(
                status_code=500,
                content={"detail": "Не удалось получить информацию о текущем событии. Пожалуйста, попробуйте позже."}
            )

        command_dao = CommandsDAO(session)
        
        # Проверяем, существует ли команда с таким названием
        existing_command = await command_dao.find_one_or_none(filters=CommandName(name=request.name))
        if existing_command:
            logger.warning(f"Команда с названием {request.name} уже существует")
            return JSONResponse(
                status_code=400,
                content={"detail": "Команда с таким названием уже существует."}
            )

        # Создаем команду с event_id текущего события и language_id из запроса
        command = await command_dao.add(values=CommandBase(
            name=request.name, 
            event_id=curr_event_id, 
            language_id=request.language_id
        ))
        logger.info(f"Создана новая команда с ID {command.id}")

        # Получаем роль капитана
        roles_users_dao = RolesUsersCommandDAO(session)
        captain_role_id = await roles_users_dao.get_role_id()
        
        if not captain_role_id:
            logger.error("Не удалось получить ID роли капитана")
            return JSONResponse(
                status_code=500,
                content={"detail": "Не удалось получить информацию о роли капитана. Пожалуйста, попробуйте позже."}
            )

        command_users_dao = CommandsUsersDAO(session)
        # Создаем связь пользователя с командой
        await command_users_dao.add(CommandsUserBase(
            command_id=command.id,
            user_id=user.id,
            role_id=captain_role_id
        ))
        logger.info(f"Пользователь {user.id} назначен капитаном команды {command.id}")
        
        logger.info(f"Команда {command.id} успешно создана")
        return JSONResponse(
            status_code=200,
            content={"message": "Команда успешно создана"}
        )
    except Exception as e:
        logger.error(f"Ошибка при создании команды: {str(e)}")
        # Проверка типа ошибки
        if hasattr(e, 'status_code'):
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail if hasattr(e, 'detail') else "Произошла ошибка. Пожалуйста, попробуйте позже."}
            )
        return JSONResponse(
            status_code=500,
            content={"detail": "Не удалось создать команду. Пожалуйста, попробуйте позже."}
        )

@router.post("/command/delete")
async def delete_command(
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """Удаление команды капитаном"""
    logger.info(f"Попытка удаления команды пользователем {user.id}")
    
    try:
        # Получаем команду пользователя
        users_dao = UsersDAO(session)
        command = await users_dao.find_user_command_in_event(user_id=user.id)
        
        if not command:
            return JSONResponse(
                status_code=404,
                content={"detail": "Команда не найдена"}
            )
        
        # Проверяем, является ли пользователь капитаном
        user_role, is_captain = get_user_role_in_command(command.users, user.id)
        if not is_captain:
            return JSONResponse(
                status_code=403,
                content={"detail": "Только капитан может удалить команду"}
            )
        
        # Удаляем команду напрямую - связи удалятся автоматически благодаря каскадному удалению
        commands_dao = CommandsDAO(session)
        await commands_dao.delete_by_id(command.id)
        
        return JSONResponse(
            status_code=200,
            content={"message": "Команда успешно удалена"}
        )
    except Exception as e:
        logger.error(f"Ошибка при удалении команды: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Не удалось удалить команду. Пожалуйста, попробуйте позже."}
        )

@router.post("/command/rename")
async def rename_command(
    request: CommandEdit,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """Переименование команды капитаном"""
    logger.info(f"Попытка изменения команды пользователем {user.id} на {request.name}")
    
    try:
        # Получаем команду пользователя
        users_dao = UsersDAO(session)
        command = await users_dao.find_user_command_in_event(user_id=user.id)
        
        if not command:
            return JSONResponse(
                status_code=404,
                content={"detail": "Команда не найдена"}
            )
        
        # Проверяем, является ли пользователь капитаном
        user_role, is_captain = get_user_role_in_command(command.users, user.id)
        if not is_captain:
            return JSONResponse(
                status_code=403,
                content={"detail": "Только капитан может изменять команду"}
            )
        
        # Проверяем, существует ли команда с таким названием
        commands_dao = CommandsDAO(session)
        existing_command = await commands_dao.find_one_or_none(filters=CommandName(name=request.name))
        if existing_command and existing_command.id != command.id:
            logger.warning(f"Команда с названием {request.name} уже существует")
            return JSONResponse(
                status_code=400,
                content={"detail": "Команда с таким названием уже существует."}
            )
        
        # Обновляем название и язык команды
        await commands_dao.update_name(command.id, request.name, request.language_id)
        
        return JSONResponse(
            status_code=200,
            content={"message": "Команда успешно обновлена"}
        )
    except Exception as e:
        logger.error(f"Ошибка при переименовании команды: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Не удалось переименовать команду. Пожалуйста, попробуйте позже."}
        )

@router.post("/command/leave")
async def leave_command(
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """Выход пользователя из команды"""
    logger.info(f"Попытка выхода из команды пользователем {user.id}")
    
    try:
        # Получаем команду пользователя
        users_dao = UsersDAO(session)
        command = await users_dao.find_user_command_in_event(user_id=user.id)
        
        if not command:
            return JSONResponse(
                status_code=404,
                content={"detail": "Команда не найдена"}
            )
        
        # Проверяем роль пользователя
        user_role, is_captain = get_user_role_in_command(command.users, user.id)
        
        # Если пользователь - капитан, нельзя выйти из команды (нужно удалить её)
        if is_captain:
            return JSONResponse(
                status_code=403,
                content={"detail": "Капитан не может покинуть команду. Вместо этого удалите команду."}
            )
        
        # Удаляем пользователя из команды
        commands_users_dao = CommandsUsersDAO(session)
        await commands_users_dao.delete_by_user_id(user.id)
        
        return JSONResponse(
            status_code=200,
            content={"message": "Вы успешно покинули команду"}
        )
    except Exception as e:
        logger.error(f"Ошибка при выходе из команды: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Не удалось выйти из команды. Пожалуйста, попробуйте позже."}
        )

@router.post("/command/remove_user")
async def remove_user_from_command(
    user_id: int = Body(..., embed=True),
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """Исключение пользователя из команды капитаном"""
    logger.info(f"Попытка исключения пользователя {user_id} из команды пользователем {user.id}")
    
    try:
        # Получаем команду пользователя
        users_dao = UsersDAO(session)
        command = await users_dao.find_user_command_in_event(user_id=user.id)
        
        if not command:
            return JSONResponse(
                status_code=404,
                content={"detail": "Команда не найдена"}
            )
        
        # Проверяем, является ли пользователь капитаном
        user_role, is_captain = get_user_role_in_command(command.users, user.id)
        if not is_captain:
            return JSONResponse(
                status_code=403,
                content={"detail": "Только капитан может исключать участников"}
            )
        
        # Проверяем, что исключаемый пользователь существует и находится в команде
        target_user = next((cu for cu in command.users if cu.user_id == user_id), None)
        if not target_user:
            return JSONResponse(
                status_code=404,
                content={"detail": "Пользователь не найден в команде"}
            )
        
        # Проверяем, что исключаемый пользователь не капитан
        target_role, target_is_captain = get_user_role_in_command(command.users, user_id)
        if target_is_captain:
            return JSONResponse(
                status_code=403,
                content={"detail": "Нельзя исключить капитана из команды"}
            )
        
        # Удаляем пользователя из команды
        commands_users_dao = CommandsUsersDAO(session)
        await commands_users_dao.delete_by_user_id(user_id)
        
        return JSONResponse(
            status_code=200,
            content={"message": "Пользователь успешно исключен из команды"}
        )
    except Exception as e:
        logger.error(f"Ошибка при исключении пользователя из команды: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Не удалось исключить пользователя из команды. Пожалуйста, попробуйте позже."}
        )

@router.post("/update_profile")
async def update_profile(
    request: UpdateProfileRequest,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    """Обновление профиля пользователя"""
    logger.info(f"Обновление профиля пользователя {user.id}")
    
    if not user:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"ok": False, "message": "Пользователь не авторизован"}
        )
    
    try:
        users_dao = UsersDAO(session)
        
        # Обновляем ФИО пользователя
        await users_dao.update_full_name(user.id, request.full_name)
        
        # Если пользователь - инсайдер и есть дополнительные поля, обновляем их
        if user.role and user.role.name == "insider" and (request.student_organization is not None or request.geo_link is not None):
            insiders_dao = InsidersInfoDAO(session)
            await insiders_dao.create_or_update(
                user_id=user.id,
                student_organization=request.student_organization,
                geo_link=request.geo_link
            )
        
        return JSONResponse(
            status_code=200,
            content={"message": "Профиль успешно обновлен"}
        )
    except Exception as e:
        logger.error(f"Ошибка при обновлении профиля: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Не удалось обновить профиль. Пожалуйста, попробуйте позже."}
        )

# Проверка активности события
@router.get("/event/status")
async def check_event_status(
    session: AsyncSession = Depends(get_session_with_commit),
    user: Optional[User] = Depends(get_current_user)
):
    """
    Проверяет, активно ли текущее событие
    
    Returns:
        JSON с полем is_active: True, если событие активно, иначе False
    """
    try:
        # Проверяем, является ли пользователь организатором
        if user and user.role and user.role.name == "organizer":
            # Организаторы всегда могут входить в квест
            return {"is_active": True}
            
        events_dao = EventsDAO(session)
        event_id = await events_dao.get_event_id_by_name()
        
        if not event_id:
            return {"is_active": False}
        
        is_active = await events_dao.is_event_active(event_id)
        return {"is_active": is_active}
    except Exception as e:
        logger.error(f"Ошибка при проверке активности события: {e}")
        return {"is_active": False}

# Вспомогательная функция для получения роли пользователя в команде
def get_user_role_in_command(command_users, user_id):
    """
    Проверяет роль пользователя в команде
    
    Args:
        command_users: Список объектов CommandsUser
        user_id: ID пользователя для проверки
        
    Returns:
        role_name: Название роли пользователя или None, если пользователь не найден
        is_captain: True, если пользователь - капитан, False в противном случае
    """
    user_role = next((cu.role.name for cu in command_users if cu.user_id == user_id), None)
    is_captain = user_role == "captain"
    return user_role, is_captain

# Вспомогательная функция для форматирования участников команды с капитаном в начале списка
def format_participants(command_users, include_role=True) -> List[Dict[str, Any]]:
    """
    Форматирует список участников команды, помещая капитана в начало списка.
    
    Args:
        command_users: Список объектов CommandsUser (связь между пользователем и командой)
        include_role: Включать ли информацию о роли пользователя в команде
        
    Returns:
        Отформатированный список участников с капитаном в начале
    """
    participants = []
    captain_info = None
    
    for cu in command_users:
        if include_role:
            participant_info = {
                "id": cu.user.id,
                "full_name": cu.user.full_name,
                "role": cu.role.name
            }
        else:
            participant_info = {
                "id": cu.user.id,
                "full_name": cu.user.full_name
            }
        
        # Определяем капитана
        if cu.role.name == "captain":
            captain_info = participant_info
        else:
            participants.append(participant_info)
    
    # Ставим капитана в начало списка
    if captain_info:
        participants.insert(0, captain_info)
        
    return participants

@router.get("/stats/registrations")
async def get_registration_stats(
    session: AsyncSession = Depends(get_session_with_commit),
    user: Optional[User] = Depends(get_current_user)
):
    """Получает статистику по зарегистрированным пользователям и командам"""
    logger.info("Запрос статистики регистраций")
    
    # Проверяем авторизацию и роль пользователя
    if not user or user.role.name not in ["organizer"]:
        logger.warning(f"Отказано в доступе пользователю {user.id if user else 'неавторизован'}")
        return JSONResponse(
            content={"ok": False, "message": "Недостаточно прав для просмотра статистики"},
            status_code=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Получаем DAO для работы с данными
        users_dao = UsersDAO(session)
        commands_dao = CommandsDAO(session)
        event_dao = EventsDAO(session)
        
        # Получаем текущее событие
        curr_event_id = await event_dao.get_event_id_by_name()
        if not curr_event_id:
            logger.error("Не удалось получить информацию о текущем событии")
            return JSONResponse(
                content={"ok": False, "message": "Не удалось получить информацию о текущем событии"},
                status_code=500
            )
        
        # Импортируем необходимые функции для загрузки связанных объектов
        from sqlalchemy.orm import selectinload
        # Импортируем модель Command
        from app.auth.models import Command
        
        # Получаем команды текущего события с загрузкой связанных пользователей
        teams = await commands_dao.find_all_by_event(
            curr_event_id,
            options=[selectinload(Command.users)]
        )
        
        total_teams = len(teams)
        
        # Получаем распределение по командам
        team_sizes = {}
        for i in range(1, 7):  # Команды от 1 до 6 участников
            team_sizes[i] = len([team for team in teams if len(team.users) == i])
            
        # Подсчитываем общее количество пользователей и активных пользователей
        total_users = await users_dao.count_all_users()
        active_users = await users_dao.count_users_with_role()
        looking_for_team = await users_dao.count_users_looking_for_friends()
        
        # Получаем статистику регистраций по дням
        try:
            registrations_by_date = await users_dao.get_registrations_by_date("guest")
            logger.info(f"Получены данные о регистрациях по дням: {len(registrations_by_date)} записей")
        except Exception as e:
            logger.error(f"Ошибка при получении данных о регистрациях по дням: {e}")
            registrations_by_date = []
        
        # Получаем статистику пользователей по ролям
        try:
            roles_distribution = await users_dao.get_users_by_role()
            logger.info(f"Получены данные о распределении пользователей по ролям")
        except Exception as e:
            logger.error(f"Ошибка при получении данных о распределении пользователей по ролям: {e}")
            roles_distribution = {}
            
        # Получаем статистику пользователей с необычным ФИО
        try:
            unusual_name_count = await users_dao.count_users_with_unusual_name()
            unusual_name_registrations = await users_dao.get_unusual_name_registrations_by_date()
            logger.info(f"Получены данные о пользователях с необычным ФИО: {unusual_name_count}")
        except Exception as e:
            logger.error(f"Ошибка при получении данных о пользователях с необычным ФИО: {e}")
            unusual_name_count = 0
            unusual_name_registrations = []
        
        # Вычисляем средний размер команды
        average_team_size = 0
        if total_teams > 0:
            team_members_sum = sum(size * count for size, count in team_sizes.items())
            average_team_size = team_members_sum / total_teams
        
        # Собираем статистику
        stats = {
            "total_users": total_users,
            "active_users": active_users,
            "total_teams": total_teams,
            "team_distribution": team_sizes,
            "users_looking_for_team": looking_for_team,
            "average_team_size": average_team_size,
            "registrations_by_date": registrations_by_date,
            "roles_distribution": roles_distribution,
            "unusual_name_count": unusual_name_count,
            "unusual_name_registrations": unusual_name_registrations
        }
        
        logger.info(f"Статистика регистраций успешно собрана")
        return JSONResponse(
            content={"ok": True, "stats": stats}
        )
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики регистраций: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"ok": False, "message": "Внутренняя ошибка сервера"},
            status_code=500
        )

