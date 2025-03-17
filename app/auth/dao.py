from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.dao.base import BaseDAO
from app.auth.models import Event, User, CommandsUser, Command
from app.logger import logger

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
