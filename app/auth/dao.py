from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload
from app.auth.schemas import SessionCreate, SessionFindUpdate, SessionGet, SessionMakeUpdate
from app.dao.base import BaseDAO
from app.auth.models import Event, Session, User, CommandsUser, Command
from app.logger import logger
import uuid
import secrets
from app.config import SESSION_EXPIRE_SECONDS

class UsersDAO(BaseDAO):
    model = User
    async def find_user_command_in_event(self, user_id: int, event_name: str) -> Optional[Command]:
        """
        Находит команду, в которой состоит пользователь для указанного мероприятия.
        """
        logger.info(f"Поиск команды для пользователя {user_id} в мероприятии {event_name}")
        try:
            query = (
                select(Command)
                .join(CommandsUser, Command.id == CommandsUser.command_id)
                .join(Event, Command.event_id == Event.id)
                .filter(Event.name == event_name)  # Фильтруем по названию мероприятия
                .filter(CommandsUser.user_id == user_id)  # Фильтруем по ID пользователя
                .options(selectinload(Command.users_association).selectinload(CommandsUser.user))
                .options(selectinload(Command.users_association).selectinload(CommandsUser.role))
            )
            result = await self._session.execute(query)
            command = result.scalar_one_or_none()
            logger.info(f"Результат поиска команды: {command}")
            return command
        except Exception as e:
            logger.error(f"Ошибка при поиске команды: {e}")
            raise

    async def is_user_captain_in_command(self, user_id: int, command_id: int) -> bool:
        """
        Проверяет, является ли пользователь капитаном в указанной команде.
        """
        logger.info(f"Проверка, является ли пользователь {user_id} капитаном в команде {command_id}")
        try:
            query = (
                select(CommandsUser)
                .filter_by(command_id=command_id)
                .filter_by(user_id=user_id)
            )
            result = await self._session.execute(query)
            command_user = result.scalar_one_or_none()

            if command_user:
                is_captain = command_user.role.name == "captain"
                logger.info(f"Результат проверки: пользователь {'является' if is_captain else 'не является'} капитаном")
                return is_captain

            logger.info("Запись о пользователе в команде не найдена")
            return None
        except Exception as e:
            logger.error(f"Ошибка при проверке роли капитана: {e}")
            raise

    async def create_command_user(self, command_id: int, user_id: int, role_id: int):
        """
        Создает запись в таблице CommandsUser.
        """
        logger.info(f"Создание записи в таблице CommandsUser для команды {command_id} и пользователя {user_id}")
        try:
            command_user = CommandsUser(command_id=command_id, user_id=user_id, role_id=role_id)
            await self.add(command_user)
            logger.info(f"Запись в таблице CommandsUser успешно создана")
            return command_user
        except Exception as e:
            logger.error(f"Ошибка при создании записи в таблице CommandsUser: {e}")
            raise

class CommandsUsersDAO(BaseDAO):
    model = CommandsUser

class CommandsDAO(BaseDAO):
    model = Command

# class RoleDAO(BaseDAO):
#     model = Role

class EventsDAO(BaseDAO):
    model = Event

class SessionDAO(BaseDAO):
    model = Session

    async def create_session(self, user_id: int) -> str:
        """
        Создает новую сессию для пользователя.
        Если у пользователя уже есть активная сессия, она будет деактивирована.
        Возвращает токен созданной сессии.
        """
        logger.info(f"Создание новой сессии для пользователя {user_id}")
        try:
            # Деактивируем все активные сессии пользователя
            await self.deactivate_all_sessions(user_id)
            
            # Создаем новую сессию
            session_token = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=SESSION_EXPIRE_SECONDS)
    
            session_data = SessionCreate(
                user_id=user_id,
                token=session_token,
                expires_at=expires_at,
                is_active=True
            )
            new_session = await self.add(values=session_data)

            logger.info(f"Новая сессия успешно создана для пользователя {user_id}")
            return session_token
        except Exception as e:
            logger.error(f"Ошибка при создании сессии: {e}")
            raise

    async def deactivate_all_sessions(self, user_id: int):
        """
        Деактивирует все активные сессии пользователя.
        """
        logger.info(f"Деактивация всех сессий пользователя {user_id}")
        try:
            await self.update(
                filters=SessionFindUpdate(user_id=user_id, is_active=True),
                values=SessionMakeUpdate(is_active=False, expires_at=datetime.now(timezone.utc))
            )
            logger.info(f"Все сессии пользователя {user_id} успешно деактивированы")
        except Exception as e:
            logger.error(f"Ошибка при деактивации сессий: {e}")
            raise

    async def deactivate_session(self, session_token: str):
        """
        Деактивирует сессию по её токену.
        """
        logger.info(f"Деактивация сессии с токеном {session_token}")
        try:
            await self.update(
                filters={"token": session_token},
                values={"is_active": False, "expires_at": datetime.now(timezone.utc)}
            )
            logger.info(f"Сессия с токеном {session_token} успешно деактивирована")
        except Exception as e:
            logger.error(f"Ошибка при деактивации сессии: {e}")
            raise

    async def get_session(self, session_token: str):
        """
        Получает сессию по токену.
        """
        logger.info(f"Получение сессии по токену {session_token}")
        try:
            session = await self.find_one_or_none(filters=SessionGet(token=session_token))
            if not session or not session.is_valid():
                raise ValueError("Invalid or expired session token")
            logger.info(f"Сессия с токеном {session_token} успешно получена")
            return session
        except Exception as e:
            logger.error(f"Ошибка при получении сессии: {e}")
            raise

