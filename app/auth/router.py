from fastapi import APIRouter, Response, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.utils import set_tokens
from app.dependencies.auth_dep import get_current_user
from app.dependencies.dao_dep import get_session_with_commit
from app.auth.dao import CommandsDAO, RolesUsersCommand, UsersDAO, SessionDAO, EventsDAO, RolesDAO
from app.auth.schemas import CommandBase, CommandName, CompleteRegistrationRequest, SUserInfo, TelegramAuthData, UserFindCompleteRegistration, UserMakeCompleteRegistration, UserTelegramID, SUserAddDB, EventID
from fastapi.responses import JSONResponse
from app.exceptions import InternalServerErrorException
router = APIRouter()

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("session_token")
    return {'message': 'Пользователь успешно вышел из системы'}


@router.get("/me")
async def get_me(user_data: User = Depends(get_current_user)) -> SUserInfo:
    return SUserInfo.model_validate(user_data)


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

@router.post("command/create")
async def command_create(
    request: CommandName,
    session: AsyncSession = Depends(get_session_with_commit),
    user: User = Depends(get_current_user)
):
    # Получаем текущее событие
    event_dao = EventsDAO(session)
    curr_event_id = await event_dao.get_event_id_by_name()
    
    if not curr_event_id:
        raise InternalServerErrorException

    command_dao = CommandsDAO(session)
    users_dao = UsersDAO(session)
    
    # Создаем команду с event_id текущего события
    command = await command_dao.add(values=CommandBase(name=request.name, event_id=curr_event_id))

    # Получаем роль капитана
    roles_users_dao = RolesUsersCommand(session)
    captain_role_id = await roles_users_dao.get_role_id()
    
    if not captain_role_id:
        raise InternalServerErrorException

    # Создаем связь пользователя с командой
    await users_dao.create_command_user(
        command_id=command.id,
        user_id=user.id,
        role_id=captain_role_id
    )
    
    return JSONResponse(
        status_code=200,
        content={"message": "Команда успешно создана"}
    )


# @router.post("command/delete")

# @router.post("command/rename")

# @router.post("command/get_link")

# @router.post("command/handle_link") ???
