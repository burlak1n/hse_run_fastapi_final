from datetime import datetime, timezone
from fastapi import Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from app.auth.dao import UsersDAO
from app.auth.models import User
from app.config import settings
from app.dependencies.dao_dep import get_session_without_commit
from app.exceptions import (
    TokenNoFound, NoJwtException, TokenExpiredException, NoUserIdException, ForbiddenException, UserNotFoundException
)
from app.auth.dao import SessionDAO
from app.logger import logger



def get_access_token(request: Request) -> Optional[str]:
    """Извлекаем access_token из кук."""
    logger.info(f"Попытка извлечения токена сессии из cookies")
    
    # Пробуем получить основной токен сессии
    token = request.cookies.get('session_token')
    
    # Если основной токен отсутствует, пробуем альтернативный
    if not token:
        token = request.cookies.get('session_token_alt')
        if token:
            logger.info("Токен сессии получен из альтернативной cookie")
            return token
        
        logger.warning("Токен сессии не найден в cookies")
        return None
    
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
        session_token: Optional[str] = Depends(get_access_token),
        session: AsyncSession = Depends(get_session_without_commit)
) -> Optional[User]:
    """Получаем текущего пользователя по токену сессии."""
    if not session_token:
        logger.warning("Не предоставлен токен сессии")
        return None
    
    session_dao = SessionDAO(session)
    users_dao = UsersDAO(session)
    
    logger.info(f"Попытка получения пользователя по токену сессии: {session_token}")
    
    try:
        # Получаем сессию по токену
        user_session = await session_dao.get_session(session_token)
        if not user_session:
            logger.warning(f"Недействительная или не найденная сессия для токена: {session_token}")
            return None
        
        # Проверяем валидность сессии (работает для обоих типов)
        if not user_session.is_valid():
            logger.warning(f"Недействительная сессия для токена: {session_token}")
            return None
        
        logger.info(f"Найдена сессия для пользователя с ID: {user_session.user_id}")
        
        # Получаем пользователя
        user = await users_dao.find_one_or_none_by_id(user_session.user_id)
        if not user:
            logger.error(f"Пользователь с ID {user_session.user_id} не найден в базе данных")
            return None
        
        logger.info(f"Успешно получен пользователь: {user.id} {user.full_name}")
        return user
    except Exception as e:
        logger.error(f"Ошибка при получении пользователя: {str(e)}")
        return None


# async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
#     """Проверяем права пользователя как администратора."""
#     if current_user.role.id in [3, 4]:
#         return current_user
#     raise ForbiddenException

def require_role(allowed_roles: List[str]):
    """
    Dependency factory that creates a dependency to ensure the current user 
    has one of the specified roles.
    
    Args:
        allowed_roles: A list of role names (strings) that are allowed.
        
    Returns:
        An asynchronous dependency function.
    """
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        # get_current_user already returns Optional[User], so we handle None first.
        if not user:
            # This case covers no token or invalid session leading to no user.
            # Raising ForbiddenException as access is denied.
            raise ForbiddenException 
        
        # Now we know user is not None, check the role.
        if not user.role or user.role.name not in allowed_roles:
            logger.warning(f"User {user.id} with role '{user.role.name if user.role else 'None'}' tried to access resource requiring roles: {allowed_roles}")
            raise ForbiddenException
        
        logger.debug(f"User {user.id} role '{user.role.name}' authorized for roles: {allowed_roles}")
        return user
        
    return role_checker
