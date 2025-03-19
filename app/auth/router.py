from typing import List
from fastapi import APIRouter, Response, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
import secrets

from app.auth.models import User, Session
from app.auth.utils import set_tokens, create_session
from app.dependencies.auth_dep import get_current_user
from app.dependencies.dao_dep import get_session_with_commit, get_session_without_commit
from app.exceptions import UserAlreadyExistsException, IncorrectTelegramIdOrPasswordException
from app.auth.dao import UsersDAO, SessionDAO
from app.auth.schemas import SUserRegister, SUserAuth, TelegramModel, SUserAddDB, SUserInfo, TelegramAuthData, UserFindCompleteRegistration, UserMakeCompleteRegistration, UserTelegramID
from pydantic import BaseModel
from fastapi.responses import JSONResponse

router = APIRouter()


# @router.post("/register/")
# async def register_user(user_data: SUserRegister,
#                         session: AsyncSession = Depends(get_session_with_commit)) -> dict:
#     # Проверка существования пользователя
#     user_dao = UsersDAO(session)

#     existing_user = await user_dao.find_one_or_none(filters=TelegramModel(telegram_id=user_data.telegram_id))
#     if existing_user:
#         raise UserAlreadyExistsException

#     # Подготовка данных для добавления
#     user_data_dict = user_data.model_dump()

#     # Добавление пользователя
#     await user_dao.add(values=SUserAddDB(**user_data_dict))

#     return {'message': 'Вы успешно зарегистрированы!'}


# @router.post("/login/")
# async def auth_user(
#         response: Response,
#         user_data: SUserAuth,
#         session: AsyncSession = Depends(get_session_without_commit)
# ) -> dict:
#     users_dao = UsersDAO(session)
#     user = await users_dao.find_one_or_none(
#         filters=TelegramModel(telegram_id=user_data.telegram_id)
#     )

#     if not (user and await authenticate_user(user=user, password=user_data.password)):
#         raise IncorrectTelegramIdOrPasswordException
#     set_tokens(response, user.id)
#     return {
#         'ok': True,
#         'message': 'Авторизация успешна!'
#     }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("session_token")
    return {'message': 'Пользователь успешно вышел из системы'}


@router.get("/me/")
async def get_me(user_data: User = Depends(get_current_user)) -> SUserInfo:
    return SUserInfo.model_validate(user_data)


# @router.get("/all_users/")
# async def get_all_users(session: AsyncSession = Depends(get_session_with_commit),
#                         user_data: User = Depends(get_current_admin_user)
#                         ) -> List[SUserInfo]:
#     return await UsersDAO(session).find_all()


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
    #TODO 
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


class CompleteRegistrationRequest(BaseModel):
    full_name: str

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

