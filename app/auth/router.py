from fastapi import APIRouter, Response, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
import io

from app.auth.models import User, CommandsUser, Command
from app.auth.utils import set_tokens, generate_qr_image
from app.dependencies.auth_dep import get_access_token, get_current_user
from app.dependencies.dao_dep import get_session_with_commit, get_session_without_commit
from app.auth.dao import CommandsDAO, CommandsUsersDAO, RolesUsersCommandDAO, UsersDAO, SessionDAO, EventsDAO, RolesDAO
from app.auth.schemas import CommandBase, CommandInfo, CommandName, CommandsUserBase, CompleteRegistrationRequest, RoleModel, SUserInfo, TelegramAuthData, UserFindCompleteRegistration, UserMakeCompleteRegistration, UserTelegramID, SUserAddDB, EventID, ParticipantInfo
from fastapi.responses import JSONResponse, StreamingResponse
from app.exceptions import InternalServerErrorException, TokenExpiredException, UserNotFoundException
from app.logger import logger
from app.config import settings

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
            }
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
    
    # Обновляем данные пользователя
    await users_dao.update(
        filters=UserFindCompleteRegistration(id = user.id),
        values=UserMakeCompleteRegistration(full_name=request.full_name, role_id=1)  # role_id = 1 - стандартная роль гостя
    )
    
    return {
        "ok": True,
        "message": "Регистрация успешно завершена"
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("session_token")
    return {'message': 'Пользователь успешно вышел из системы'}


# Пользователи и профили
# =====================

@router.get("/me")
async def get_me(
    user_data: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_with_commit)
) -> SUserInfo:
    # Оптимизированный запрос с минимально необходимыми данными
    users_dao = UsersDAO(session)
    user = await users_dao.find_one_by_id(
        user_data.id,
        options=[
            selectinload(User.commands).joinedload(CommandsUser.command).joinedload(Command.users).joinedload(CommandsUser.user),
            selectinload(User.commands).joinedload(CommandsUser.role),
            selectinload(User.role)
        ]
    )
    
    # Оптимизированное формирование информации о командах
    commands_info = [
        CommandInfo(
            id=cu.command.id,
            name=cu.command.name,
            role=cu.role.name,
            event_id=cu.command.event_id,
            language_id=cu.command.language_id,
            participants=[
                ParticipantInfo(
                    id=cu_user.user.id,
                    full_name=cu_user.user.full_name,
                    role=cu_user.role.name
                )
                for cu_user in cu.command.users
            ]
        ).model_dump()
        for cu in user.commands
    ]

    # Возвращаем информацию о пользователе
    return SUserInfo(
        id=user.id,
        full_name=user.full_name,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        role=RoleModel(id=user.role.id, name=user.role.name),
        commands=commands_info
    )


@router.get("/qr")
async def get_me_qr_code(
    user_data: User = Depends(get_current_user),
    session_token: str = Depends(get_access_token),
):
    # Генерация QR-кода с ссылкой на эндпоинт проверки
    qr_data = generate_qr_image(f"{settings.BASE_URL}/api/auth/qr/verify?token={session_token}")
    return StreamingResponse(io.BytesIO(qr_data), media_type="image/png")


@router.get("/qr/verify")
async def verify_qr(
    token: str,
    scanner_user: User = Depends(get_current_user),  # Пользователь, который сканирует
    session: AsyncSession = Depends(get_session_without_commit)
):
    """
    Проверяет валидность сессионного токена.
    В зависимости от роли пользователя, который сканирует:
    - guest: добавляет в команду
    - insider/organizer: возвращает информацию о команде
    """
    # Получаем пользователя, чей QR сканируют, через get_current_user
    try:
        qr_user = await get_current_user(token, session)
    except (TokenExpiredException, UserNotFoundException):
        return {
            "ok": False,
            "message": "Недействительный QR-код"
        }
    
    commands_dao = CommandsDAO(session)
    commands_users_dao = CommandsUsersDAO(session)
    roles_dao = RolesDAO(session)
    
    # Получаем команду пользователя, чей QR сканируют
    qr_user_command = await commands_dao.find_user_command_in_event(user_id=qr_user.id)
    if not qr_user_command:
        return {
            "ok": False,
            "message": "Пользователь не состоит в команде"
        }
    
    # Проверяем, что qr_user является капитаном команды
    qr_user_role = next((cu.role.name for cu in qr_user_command.users if cu.user_id == qr_user.id), None)
    if qr_user_role != "captain":
        return {
            "ok": False,
            "message": "Пользователь не является капитаном команды"
        }
    
    # Обработка в зависимости от роли сканирующего
    if scanner_user.role.name == "guest":
        # Проверяем, не состоит ли уже пользователь в команде
        scanner_user_command = await commands_dao.find_user_command_in_event(user_id=scanner_user.id)
        if scanner_user_command:
            return {
                "ok": False,
                "message": "Вы уже состоите в другой команде"
            }
        
        # Проверяем, не состоит ли пользователь уже в этой команде
        if any(cu.user_id == scanner_user.id for cu in qr_user_command.users):
            return {
                "ok": False,
                "message": "Вы уже состоите в этой команде"
            }
        
        # Проверяем максимальное количество участников
        if len(qr_user_command.users) >= 6:
            return {
                "ok": False,
                "message": "В команде уже максимальное количество участников"
            }
        
        # Получаем ID роли участника
        participant_role = await roles_dao.find_one_or_none(filters={"name": "participant"})
        if not participant_role:
            raise InternalServerErrorException(detail="Роль участника не найдена")
        
        # Добавляем пользователя в команду
        await commands_users_dao.add(CommandsUserBase(
            command_id=qr_user_command.id,
            user_id=scanner_user.id,
            role_id=participant_role.id
        ))
        
        return {
            "ok": True,
            "message": "Вы успешно добавлены в команду"
        }
    
    # Для insider и organizer возвращаем информацию о команде
    elif scanner_user.role.name in ["insider", "organizer"]:
        return {
            "ok": True,
            "command": {
                "id": qr_user_command.id,
                "name": qr_user_command.name,
                "event_id": qr_user_command.event_id,
                "participants": [
                    {
                        "id": cu.user.id,
                        "full_name": cu.user.full_name,
                        "role": cu.role.name
                    }
                    for cu in qr_user_command.users
                ]
            }
        }
    
    # Для других ролей возвращаем ошибку
    return {
        "ok": False,
        "message": "Ваша роль не позволяет выполнить это действие"
    }


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
    request: CommandName,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    logger.info(f"Попытка создания команды пользователем {user.id} с именем {request.name}")
    
    # Получаем текущее событие
    event_dao = EventsDAO(session)
    curr_event_id = await event_dao.get_event_id_by_name()
    
    if not curr_event_id:
        logger.error("Не удалось получить ID текущего события")
        raise InternalServerErrorException

    command_dao = CommandsDAO(session)
    users_dao = UsersDAO(session)
    
    # Создаем команду с event_id текущего события
    command = await command_dao.add(values=CommandBase(name=request.name, event_id=curr_event_id))
    logger.info(f"Создана новая команда с ID {command.id}")

    # Получаем роль капитана
    roles_users_dao = RolesUsersCommandDAO(session)
    captain_role_id = await roles_users_dao.get_role_id()
    
    if not captain_role_id:
        logger.error("Не удалось получить ID роли капитана")
        raise InternalServerErrorException

    
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

# @router.post("command/delete")

# @router.post("command/rename")

# @router.post("command/get_link")

# @router.post("command/handle_link") ???

