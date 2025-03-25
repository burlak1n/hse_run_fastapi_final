from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.auth.schemas import SessionCreate, SessionFindUpdate, SessionGet, SessionMakeUpdate
from app.auth.utils import create_session
from app.config import CAPTAIN_ROLE_NAME, CURRENT_EVENT_NAME
from app.dao.base import BaseDAO
from app.auth.models import Event, Language, Role, RoleUserCommand, Session, User, CommandsUser, Command
from app.logger import logger
from sqlalchemy.exc import SQLAlchemyError


class UsersDAO(BaseDAO):
    model = User
    async def find_one_by_id(self, user_id: int, options: list = None) -> Optional[User]:
        """
        Находит пользователя по ID с возможностью загрузки связанных данных.
        """
        logger.info(f"Поиск пользователя с ID {user_id} с опциями: {options}")
        try:
            query = select(self.model).filter_by(id=user_id)
            if options:
                for option in options:
                    query = query.options(option)
            result = await self._session.execute(query)
            user = result.scalar_one_or_none()
            logger.info(f"Пользователь {'найден' if user else 'не найден'}")
            return user
        except Exception as e:
            logger.error(f"Ошибка при поиске пользователя: {e}")
            raise

    async def find_user_command_in_event(self, user_id: int, event_id: int = 1) -> Optional[Command]:
        """
        Находит команду, в которой состоит пользователь для указанного мероприятия.
        """
        logger.info(f"Поиск команды для пользователя {user_id} в мероприятии {event_id}")
        try:
            query = (
                select(Command)
                .join(CommandsUser, Command.id == CommandsUser.command_id)
                .filter(Command.event_id == event_id)
                .filter(CommandsUser.user_id == user_id)
                .options(
                    selectinload(Command.users).joinedload(CommandsUser.user),
                    selectinload(Command.users).joinedload(CommandsUser.role)
                )
                .limit(1)  # Добавляем лимит для оптимизации
            )
            result = await self._session.execute(query)
            return result.unique().scalar_one_or_none()
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

    async def create_command_user(self, CommandsUserBase):
        """
        Создает запись в таблице CommandsUser.
        """
        logger.info(f"Создание записи в таблице CommandsUser для команды {CommandsUserBase.command_id} и пользователя {CommandsUserBase.user_id}")
        try:
            command_user = await self.add(CommandsUserBase)
            logger.info("Запись в таблице CommandsUser успешно создана")
            return command_user
        except Exception as e:
            logger.error(f"Ошибка при создании записи в таблице CommandsUser: {e}")
            raise

class CommandsUsersDAO(BaseDAO):
    model = CommandsUser

class CommandsDAO(BaseDAO):
    model = Command

class RolesDAO(BaseDAO):
    model = Role

class LanguagesDAO(BaseDAO):
    model = Language
    

class RolesUsersCommandDAO(BaseDAO):
    model = RoleUserCommand

    async def get_role_id(self, role_name = CAPTAIN_ROLE_NAME) -> Optional[int]:
        """
        Получает ID роли по имени. Стандартно - капитана

        Returns:
            ID роли капитана или None, если роль не найдена
        """
        logger.info(f"Попытка получения ID роли с именем '{role_name}'")
        try:
            # Ищем роль с именем "captain" и возвращаем только её ID
            query = select(RoleUserCommand.id).where(RoleUserCommand.name == role_name)
            result = await self._session.execute(query)
            role_id = result.scalar_one_or_none()
            
            if role_id:
                logger.info(f"Успешно получен ID {role_id} для роли '{role_name}'")
            else:
                logger.warning(f"Роль с именем '{role_name}' не найдена")
                
            return role_id
        except Exception as e:
            logger.error(f"Ошибка при получении ID роли '{role_name}': {e}")
            raise

class EventsDAO(BaseDAO):
    model = Event

    async def get_event_id_by_name(self, event_name: str = CURRENT_EVENT_NAME) -> Optional[int]:
        """
        Получает ID события по его имени. По умолчанию - текущее событие

        Args:
            event_name: Название события

        Returns:
            ID события или None, если событие не найдено
        """
        try:
            query = select(self.model.id).where(self.model.name == event_name)
            result = await self._session.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Ошибка при получении ID события по имени '{event_name}': {e}")
            raise

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
            session = await create_session(user_id)
    
            session_data = SessionCreate(
                user_id=user_id,
                token=session.token,
                expires_at=session.expires_at,
                is_active=True
            )

            await self.add(values=session_data)

            logger.info(f"Новая сессия успешно создана для пользователя {user_id}")
            return session.token

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
