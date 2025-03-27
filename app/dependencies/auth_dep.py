from datetime import datetime, timezone
from fastapi import Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dao import UsersDAO
from app.auth.models import User
from app.config import settings
from app.dependencies.dao_dep import get_session_without_commit
from app.exceptions import (
    TokenNoFound, NoJwtException, TokenExpiredException, NoUserIdException, ForbiddenException, UserNotFoundException
)
from app.auth.dao import SessionDAO
from app.logger import logger



def get_access_token(request: Request) -> str:
    """Извлекаем access_token из кук."""
    logger.info(f"Попытка извлечения токена сессии из cookies")
    token = request.cookies.get('session_token')
    if not token:
        logger.warning("Токен сессии не найден в cookies")
        raise TokenNoFound
    logger.info("Токен сессии успешно извлечен")
    return token


# def get_refresh_token(request: Request) -> str:
#     """Извлекаем refresh_token из кук."""
#     token = request.cookies.get('user_refresh_token')
#     if not token:
#         raise TokenNoFound
#     return token


# async def check_refresh_token(
#         token: str = Depends(get_refresh_token),
#         session: AsyncSession = Depends(get_session_without_commit)
# ) -> User:
#     """ Проверяем refresh_token и возвращаем пользователя."""
#     try:
#         payload = jwt.decode(
#             token,
#             settings.SECRET_KEY,
#             algorithms=[settings.ALGORITHM]
#         )
#         user_id = payload.get("sub")
#         if not user_id:
#             raise NoJwtException

#         user = await UsersDAO(session).find_one_or_none_by_id(data_id=int(user_id))
#         if not user:
#             raise NoJwtException

#         return user
#     except JWTError:
#         raise NoJwtException


async def get_current_user(
        session_token: str = Depends(get_access_token),
        session: AsyncSession = Depends(get_session_without_commit)
) -> User:
    """Получаем текущего пользователя по токену сессии."""    
    session_dao = SessionDAO(session)
    users_dao = UsersDAO(session)
    
    logger.info(f"Попытка получения пользователя по токену сессии: {session_token}")
    
    # Получаем сессию по токену
    user_session = await session_dao.get_session(session_token)
    if not user_session or not user_session.is_valid():
        logger.warning(f"Недействительная или не найденная сессия для токена: {session_token}")
        raise TokenExpiredException
    
    logger.info(f"Найдена сессия для пользователя с ID: {user_session.user_id}")
    
    # TODO Обновление сессии пользователя?
    # Получаем пользователя
    user = await users_dao.find_one_or_none_by_id(user_session.user_id)
    if not user:
        logger.error(f"Пользователь с ID {user_session.user_id} не найден в базе данных")
        raise UserNotFoundException
    
    logger.info(f"Успешно получен пользователь: {user.id} {user.full_name}")
    
    return user


# async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
#     """Проверяем права пользователя как администратора."""
#     if current_user.role.id in [3, 4]:
#         return current_user
#     raise ForbiddenException
