from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.auth.schemas import SessionCreate, SessionFindUpdate, SessionGet, SessionMakeUpdate
from app.auth.utils import create_session
from app.config import CAPTAIN_ROLE_NAME, CURRENT_EVENT_NAME
from app.dao.base import BaseDAO
from app.auth.models import Event, Language, Role, RoleUserCommand, Session, User, CommandsUser, Command, InsiderInfo
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

    async def count_all_users(self) -> int:
        """
        Подсчитывает общее количество зарегистрированных пользователей
        """
        logger.info("Подсчет общего количества пользователей")
        try:
            from sqlalchemy import func
            query = select(func.count(self.model.id))
            result = await self._session.execute(query)
            count = result.scalar()
            logger.info(f"Общее количество пользователей: {count}")
            return count
        except Exception as e:
            logger.error(f"Ошибка при подсчете пользователей: {e}")
            raise
    
    async def count_users_with_role(self) -> int:
        """
        Подсчитывает количество активных пользователей (с установленной ролью)
        """
        logger.info("Подсчет количества пользователей с ролью")
        try:
            from sqlalchemy import func
            query = select(func.count(self.model.id)).where(self.model.role_id.isnot(None))
            result = await self._session.execute(query)
            count = result.scalar()
            logger.info(f"Количество пользователей с ролью: {count}")
            return count
        except Exception as e:
            logger.error(f"Ошибка при подсчете пользователей с ролью: {e}")
            raise
    
    async def count_users_looking_for_friends(self) -> int:
        """
        Подсчитывает количество пользователей, ищущих команду
        """
        logger.info("Подсчет количества пользователей, ищущих команду")
        try:
            from sqlalchemy import func
            query = select(func.count(self.model.id)).where(self.model.is_looking_for_friends == True)
            result = await self._session.execute(query)
            count = result.scalar()
            logger.info(f"Количество пользователей, ищущих команду: {count}")
            return count
        except Exception as e:
            logger.error(f"Ошибка при подсчете пользователей, ищущих команду: {e}")
            raise

    async def get_registrations_by_date(self, role_name: str = None) -> list:
        """
        Получает статистику регистраций пользователей по дням
        
        Args:
            role_name: Опциональный параметр для фильтрации по роли

        Returns:
            Список словарей с датой и количеством регистраций
        """
        logger.info(f"Получение статистики регистраций по дням{' для роли: ' + role_name if role_name else ''}")
        try:
            from sqlalchemy import func, and_
            from datetime import datetime
            from app.auth.models import Role
            
            # Устанавливаем минимальную дату для учета пользователей - 7 апреля
            cutoff_date = datetime(2025, 4, 7, 0, 0, 0)
            
            # Используем функцию date SQLAlchemy для группировки по дате
            query = (
                select(
                    func.date(self.model.created_at).label('date'),
                    func.count(self.model.id).label('count')
                )
                .where(self.model.created_at >= cutoff_date)
            )
            
            # Добавляем фильтрацию по роли, если указана
            if role_name:
                query = (
                    query
                    .join(Role, self.model.role_id == Role.id)
                    .where(Role.name == role_name)
                )
            
            # Группировка и сортировка
            query = (
                query
                .group_by(func.date(self.model.created_at))
                .order_by(func.date(self.model.created_at))
            )
            
            # Выполняем запрос
            logger.info(f"Выполняем запрос для получения регистраций по дням")
            result = await self._session.execute(query)
            
            logger.info(f"Запрос выполнен успешно, получаем результаты")
            
            # Получаем результаты
            registrations_by_date = result.all()
            logger.info(f"Получено {len(registrations_by_date)} записей")
            
            # Форматируем результат для удобства использования
            formatted_result = []
            
            for row in registrations_by_date:
                try:
                    # Преобразуем дату в строку в формате дд.мм.гггг
                    if hasattr(row.date, 'strftime'):
                        date_str = row.date.strftime('%d.%m.%Y')
                    else:
                        date_str = str(row.date)
                    
                    formatted_result.append({
                        "date": date_str,
                        "count": row.count
                    })
                except Exception as e:
                    logger.error(f"Ошибка при форматировании записи: {e}, строка: {row}")
            
            logger.info(f"Получена статистика регистраций по дням: {len(formatted_result)} записей")
            return formatted_result
        except Exception as e:
            logger.error(f"Ошибка при получении статистики регистраций по дням: {e}")
            # В случае ошибки возвращаем пустой список
            return []

    async def get_users_by_role(self) -> dict:
        """
        Получает распределение пользователей по ролям
        
        Returns:
            Словарь с названиями ролей и количеством пользователей с этой ролью
        """
        logger.info("Получение статистики пользователей по ролям")
        try:
            from sqlalchemy import func, and_
            from app.auth.models import Role
            
            
            query = (
                select(
                    Role.name,
                    func.count(self.model.id).label('count')
                )
                .join(Role, self.model.role_id == Role.id, isouter=True)
                .group_by(Role.name)
            )
            
            result = await self._session.execute(query)
            role_counts = result.all()
            
            # Формируем результат в виде словаря {роль: количество}
            roles_distribution = {}
            for row in role_counts:
                role_name = row.name if row.name else 'неактивные'
                roles_distribution[role_name] = row.count
            
            logger.info(f"Получена статистика пользователей по ролям: {roles_distribution}")
            return roles_distribution
        except Exception as e:
            logger.error(f"Ошибка при получении статистики пользователей по ролям: {e}")
            return {}

    async def count_users_with_unusual_name(self) -> int:
        """
        Подсчитывает количество пользователей, у которых ФИО содержит не 3 слова
        
        Returns:
            Количество пользователей с необычным ФИО
        """
        logger.info("Подсчет пользователей с необычным ФИО")
        try:
            from sqlalchemy import func, text, and_
            from datetime import datetime
            
            # Устанавливаем минимальную дату для учета пользователей - 7 апреля
            cutoff_date = datetime(2025, 4, 7, 0, 0, 0)
            
            # Для SQLite используем функцию length и подсчет пробелов для определения числа слов
            # Если число пробелов меньше 2, значит слов меньше 3
            query = (
                select(func.count(self.model.id))
                .where(
                    and_(
                        text("(length(trim(full_name)) - length(replace(trim(full_name), ' ', ''))) < 2"),
                        self.model.created_at >= cutoff_date
                    )
                )
            )
            
            result = await self._session.execute(query)
            count = result.scalar()
            
            logger.info(f"Количество пользователей с необычным ФИО: {count}")
            return count
        except Exception as e:
            logger.error(f"Ошибка при подсчете пользователей с необычным ФИО: {e}")
            return 0
            
    async def get_unusual_name_registrations_by_date(self) -> list:
        """
        Получает статистику регистраций пользователей с необычным ФИО по дням
        
        Returns:
            Список словарей с датой и количеством регистраций
        """
        logger.info("Получение статистики регистраций пользователей с необычным ФИО по дням")
        try:
            from sqlalchemy import func, text, and_
            from datetime import datetime
            
            # Устанавливаем минимальную дату для учета пользователей - 7 апреля
            cutoff_date = datetime(2025, 4, 7, 0, 0, 0)
            
            query = (
                select(
                    func.date(self.model.created_at).label('date'),
                    func.count(self.model.id).label('count')
                )
                .where(
                    and_(
                        text("(length(trim(full_name)) - length(replace(trim(full_name), ' ', ''))) < 2"),
                        self.model.created_at >= cutoff_date
                    )
                )
                .group_by(func.date(self.model.created_at))
                .order_by(func.date(self.model.created_at))
            )
            
            result = await self._session.execute(query)
            registrations_by_date = result.all()
            
            formatted_result = []
            for row in registrations_by_date:
                try:
                    if hasattr(row.date, 'strftime'):
                        date_str = row.date.strftime('%d.%m.%Y')
                    else:
                        date_str = str(row.date)
                    
                    formatted_result.append({
                        "date": date_str,
                        "count": row.count
                    })
                except Exception as e:
                    logger.error(f"Ошибка при форматировании записи: {e}, строка: {row}")
            
            logger.info(f"Получена статистика регистраций пользователей с необычным ФИО по дням: {len(formatted_result)} записей")
            return formatted_result
        except Exception as e:
            logger.error(f"Ошибка при получении статистики регистраций пользователей с необычным ФИО по дням: {e}")
            return []

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
    
    async def find_all_by_event(self, event_id: int, options: list = None):
        """
        Находит все команды для указанного мероприятия с возможностью загрузки связанных данных.
        
        Args:
            event_id: ID мероприятия
            options: Опции загрузки связанных данных
            
        Returns:
            Список команд
        """
        logger.info(f"Поиск всех команд для мероприятия {event_id}")
        try:
            query = select(self.model).filter(self.model.event_id == event_id)
            if options:
                for option in options:
                    query = query.options(option)
            
            # Выполняем запрос асинхронно
            result = await self._session.execute(query)
            
            # Получаем результаты
            commands = result.scalars().all()
            
            logger.info(f"Найдено {len(commands)} команд для мероприятия {event_id}")
            return commands
        except SQLAlchemyError as e:
            logger.error(f"Ошибка SQL при поиске команд для мероприятия {event_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при поиске команд для мероприятия {event_id}: {e}")
            raise
    
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
    
    async def update_name(self, command_id: int, name: str, language_id: int = None):
        """
        Обновляет название команды и опционально язык
        """
        logger.info(f"Обновление команды {command_id}")
        try:
            stmt = select(self.model).where(self.model.id == command_id)
            result = await self._session.execute(stmt)
            command = result.scalar_one_or_none()
            
            if command:
                command.name = name
                if language_id is not None:
                    command.language_id = language_id
                await self._session.commit()
                logger.info(f"Команда {command_id} успешно обновлена")
            else:
                logger.warning(f"Команда {command_id} не найдена")
        except Exception as e:
            logger.error(f"Ошибка при обновлении команды: {e}")
            raise

    async def update_language(self, command_id: int, language_id: int):
        """
        Обновляет язык команды
        """
        logger.info(f"Обновление языка команды {command_id}")
        try:
            stmt = select(self.model).where(self.model.id == command_id)
            result = await self._session.execute(stmt)
            command = result.scalar_one_or_none()
            
            if command:
                command.language_id = language_id
                await self._session.commit()
                logger.info(f"Язык команды {command_id} успешно обновлен")
            else:
                logger.warning(f"Команда {command_id} не найдена")
        except Exception as e:
            logger.error(f"Ошибка при обновлении языка команды: {e}")
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

class InsidersInfoDAO(BaseDAO):
    model = InsiderInfo

    async def create_or_update(self, user_id: int, student_organization: str = None, geo_link: str = None):
        """
        Создает или обновляет информацию об инсайдере
        """
        logger.info(f"Создание или обновление информации инсайдера для пользователя {user_id}")
        try:
            # Ищем существующую запись
            query = select(self.model).filter_by(user_id=user_id)
            result = await self._session.execute(query)
            insider_info = result.scalar_one_or_none()
            
            if insider_info:
                # Обновляем существующую запись
                if student_organization is not None:
                    insider_info.student_organization = student_organization
                if geo_link is not None:
                    insider_info.geo_link = geo_link
                await self._session.commit()
                logger.info(f"Информация инсайдера для пользователя {user_id} обновлена")
                return insider_info
            else:
                # Создаем новую запись
                insider_info = InsiderInfo(
                    user_id=user_id, 
                    student_organization=student_organization, 
                    geo_link=geo_link
                )
                self._session.add(insider_info)
                await self._session.commit()
                logger.info(f"Информация инсайдера для пользователя {user_id} создана")
                return insider_info
        except Exception as e:
            logger.error(f"Ошибка при создании/обновлении информации инсайдера: {e}")
            await self._session.rollback()
            raise

    async def get_by_user_id(self, user_id: int):
        """
        Получает информацию об инсайдере по ID пользователя
        """
        logger.info(f"Получение информации инсайдера для пользователя {user_id}")
        try:
            query = select(self.model).filter_by(user_id=user_id)
            result = await self._session.execute(query)
            insider_info = result.scalar_one_or_none()
            logger.info(f"Информация инсайдера {'найдена' if insider_info else 'не найдена'}")
            return insider_info
        except Exception as e:
            logger.error(f"Ошибка при получении информации инсайдера: {e}")
            raise
