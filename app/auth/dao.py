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

    async def update_full_name(self, user_id: int, full_name: str):
        """
        Обновляет ФИО пользователя
        """
        logger.info(f"Обновление ФИО пользователя {user_id}")
        try:
            user = await self.find_one_by_id(user_id)
            if not user:
                raise ValueError(f"Пользователь с ID {user_id} не найден")
            
            user.full_name = full_name
            await self._session.commit()
            logger.info(f"ФИО пользователя {user_id} успешно обновлено")
            return user
        except Exception as e:
            logger.error(f"Ошибка при обновлении ФИО пользователя: {e}")
            raise

class CommandsUsersDAO(BaseDAO):
    model = CommandsUser

    async def delete_by_command_id(self, command_id: int):
        """
        Удаляет все записи связанные с командой
        """
        logger.info(f"Удаление всех пользователей из команды {command_id}")
        try:
            stmt = select(self.model).where(self.model.command_id == command_id)
            result = await self._session.execute(stmt)
            command_users = result.scalars().all()
            
            for cu in command_users:
                await self._session.delete(cu)
            
            await self._session.commit()
            logger.info(f"Все пользователи успешно удалены из команды {command_id}")
        except Exception as e:
            logger.error(f"Ошибка при удалении пользователей из команды: {e}")
            raise
    
    async def delete_by_user_id(self, user_id: int):
        """
        Удаляет запись пользователя из команды
        """
        logger.info(f"Удаление пользователя {user_id} из команды")
        try:
            stmt = select(self.model).where(self.model.user_id == user_id)
            result = await self._session.execute(stmt)
            command_user = result.scalar_one_or_none()
            
            if command_user:
                await self._session.delete(command_user)
                await self._session.commit()
                logger.info(f"Пользователь {user_id} успешно удален из команды")
            else:
                logger.warning(f"Пользователь {user_id} не найден в команде")
        except Exception as e:
            logger.error(f"Ошибка при удалении пользователя из команды: {e}")
            raise

class CommandsDAO(BaseDAO):
    model = Command
    
    async def delete_by_id(self, command_id: int):
        """
        Удаляет команду по ID с учётом всех связей (attempts, commandsusers)
        """
        logger.info(f"Удаление команды {command_id}")
        try:
            # Получаем команду
            stmt = select(self.model).where(self.model.id == command_id)
            result = await self._session.execute(stmt)
            command = result.scalar_one_or_none()
            
            if not command:
                logger.warning(f"Команда {command_id} не найдена")
                return
                
            # Удаляем команду (связи удалятся автоматически благодаря cascade)
            await self._session.delete(command)
            try:
                await self._session.flush()
                logger.info(f"Команда {command_id} успешно удалена")
            except Exception as e:
                # В случае ошибки сделаем rollback и выполним более детальное удаление
                await self._session.rollback()
                logger.warning(f"Ошибка при каскадном удалении команды: {e}, выполняем ручное удаление связей")
                
                # Удаляем связанные попытки
                from app.quest.models import Attempt
                attempt_stmt = select(Attempt).where(Attempt.command_id == command_id)
                attempt_result = await self._session.execute(attempt_stmt)
                attempts = attempt_result.scalars().all()
                
                for attempt in attempts:
                    await self._session.delete(attempt)
                
                # Удаляем связи пользователей с командой
                cu_stmt = select(CommandsUser).where(CommandsUser.command_id == command_id)
                cu_result = await self._session.execute(cu_stmt)
                command_users = cu_result.scalars().all()
                
                for cu in command_users:
                    await self._session.delete(cu)
                
                # Теперь удаляем команду
                stmt = select(self.model).where(self.model.id == command_id)
                result = await self._session.execute(stmt)
                command = result.scalar_one_or_none()
                
                if command:
                    await self._session.delete(command)
                
                logger.info(f"Команда {command_id} успешно удалена вручную")
            
            # Завершаем транзакцию
            await self._session.commit()
            
        except Exception as e:
            await self._session.rollback()
            logger.error(f"Ошибка при удалении команды: {e}")
            raise
    
    async def update_name(self, command_id: int, name: str):
        """
        Обновляет название команды
        """
        logger.info(f"Обновление названия команды {command_id}")
        try:
            stmt = select(self.model).where(self.model.id == command_id)
            result = await self._session.execute(stmt)
            command = result.scalar_one_or_none()
            
            if command:
                command.name = name
                await self._session.commit()
                logger.info(f"Название команды {command_id} успешно обновлено")
            else:
                logger.warning(f"Команда {command_id} не найдена")
        except Exception as e:
            logger.error(f"Ошибка при обновлении названия команды: {e}")
            raise

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

    async def is_event_active(self, event_id: int) -> bool:
        """
        Проверяет, активно ли событие в данный момент

        Args:
            event_id: ID события

        Returns:
            True, если событие активно, иначе False
        """
        try:
            query = select(self.model).where(
                self.model.id == event_id,
                self.model.start_time <= datetime.now(timezone.utc),
                self.model.end_time >= datetime.now(timezone.utc)
            )
            result = await self._session.execute(query)
            return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"Ошибка при проверке активности события {event_id}: {e}")
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
                logger.warning(f"Недействительная или истекшая сессия с токеном {session_token}")
                return None
            logger.info(f"Сессия с токеном {session_token} успешно получена")
            return session
        except Exception as e:
            logger.error(f"Ошибка при получении сессии: {e}")
            return None
