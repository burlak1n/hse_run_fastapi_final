from fastapi import APIRouter, Response, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.auth.models import User, CommandsUser, Command
from app.auth.utils import set_tokens
from app.dependencies.auth_dep import get_current_user
from app.dependencies.dao_dep import get_session_with_commit
from app.auth.dao import CommandsDAO, CommandsUsersDAO, RolesUsersCommandDAO, UsersDAO, SessionDAO, EventsDAO, RolesDAO
from app.auth.schemas import CommandBase, CommandInfo, CommandName, CommandsUserBase, CompleteRegistrationRequest, RoleModel, SUserInfo, TelegramAuthData, UserFindCompleteRegistration, UserMakeCompleteRegistration, UserTelegramID, SUserAddDB, EventID, ParticipantInfo
from fastapi.responses import JSONResponse
from app.exceptions import InternalServerErrorException
from app.logger import logger

router = APIRouter()

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("session_token")
    return {'message': 'Пользователь успешно вышел из системы'}

# @router.post("/refresh")
# async def process_refresh_token(
#         response: Response,
#         user: User = Depends(check_refresh_token)
# ):
#     set_tokens(response, user.id)
#     return {"message": "Токены успешно обновлены"}


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
        role_id=user.role_id,
        role=RoleModel(id=user.role.id, name=user.role.name),
        commands=commands_info
    )

@router.get("/command")
async def command_create(
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
