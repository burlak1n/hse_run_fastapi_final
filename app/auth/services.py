import base64
from typing import Any, Dict, List, Optional, Tuple

# Cache imports removed
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dao import (CommandsDAO, CommandsUsersDAO, EventsDAO,
                          InsidersInfoDAO, ProgramDAO, RolesDAO,
                          RolesUsersCommandDAO, SessionDAO, UsersDAO)
from app.auth.models import Command, CommandsUser, User
from app.auth.schemas import (CommandBase, CommandEdit, CommandInfo,
                              CommandLeaderboardData, CommandLeaderboardEntry,
                              CommandName, CommandNameAndEvent, CommandsUserBase,
                              CompleteRegistrationRequest, ProgramScoreAdd,
                              ProgramScoreInfo, ProgramScoreTotal, RoleFilter,
                              RoleModel, SUserAddDB, TelegramAuthData,
                              UpdateProfileRequest,
                              UserFindCompleteRegistration,
                              UserMakeCompleteRegistration, UserTelegramID)
from app.auth.utils import generate_qr_image
from app.config import settings
from app.exceptions import (BadRequestException, ForbiddenException,
                            InternalServerErrorException, NotFoundException,
                            TokenExpiredException)
from app.logger import logger
from app.quest.models import Attempt, AttemptType


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users_dao = UsersDAO(session)
        self.session_dao = SessionDAO(session)
        self.roles_dao = RolesDAO(session)
        self.insiders_dao = InsidersInfoDAO(session)
        self.program_dao = ProgramDAO(session)
        self.commands_users_dao = CommandsUsersDAO(session) # Для get_me

    async def handle_telegram_auth(self, user_data: TelegramAuthData) -> Tuple[Dict[str, Any], str]:
        """Обрабатывает аутентификацию через Telegram, создает или находит пользователя, создает сессию."""
        user = await self.users_dao.find_one_or_none(
            filters=UserTelegramID(telegram_id=user_data.id)
        )
        if not user:
            logger.info(f"Создание нового пользователя для Telegram ID: {user_data.id}")
            new_user = await self.users_dao.add(
                values=SUserAddDB(
                    full_name=user_data.first_name,
                    telegram_id=user_data.id,
                    telegram_username=user_data.username
                )
            )
            user = new_user
        else:
            logger.info(f"Пользователь найден для Telegram ID: {user_data.id}")

        session_token = await self.session_dao.create_session(user.id)
        
        registration_type = "default"
        if user_data.registration_code and user_data.registration_code == "insider":
            registration_type = "insider"
            
        user_info = {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "full_name": user.full_name,
            "telegram_username": user.telegram_username,
            "is_active": user.role_id is not None
        }
        
        response_content = {
            "ok": True,
            "message": "Telegram authentication successful",
            "user": user_info,
            "registration_type": registration_type
        }
        
        return response_content, session_token

    async def complete_registration(self, user: User, request: CompleteRegistrationRequest) -> None:
        """Завершает регистрацию пользователя, устанавливая ФИО, роль и информацию инсайдера."""
        role_name = "insider" if request.student_organization else "guest"
        
        role = await self.roles_dao.find_one_or_none(filters=RoleFilter(name=role_name))
        if not role:
            logger.error(f"Роль {role_name} не найдена")
            raise InternalServerErrorException("Ошибка при выборе роли пользователя")
        
        await self.users_dao.update(
            filters=UserFindCompleteRegistration(id=user.id),
            values=UserMakeCompleteRegistration(full_name=request.full_name, role_id=role.id)
        )
        
        if role_name == "insider" and (request.student_organization or request.geo_link):
            try:
                await self.insiders_dao.create_or_update(
                    user_id=user.id, 
                    student_organization=request.student_organization,
                    geo_link=request.geo_link
                )
            except Exception as e:
                logger.error(f"Ошибка при сохранении информации инсайдера {user.id}: {e}")
                raise InternalServerErrorException("Ошибка при сохранении дополнительной информации")

    async def get_user_profile(self, user_id: int, event_id: int) -> Dict[str, Any]:
        """Получает расширенную информацию о профиле пользователя."""
        user = await self.users_dao.find_one_by_id(
            user_id,
            options=[
                selectinload(User.role),
                selectinload(User.insider_info)
            ]
        )
        if not user:
            raise NotFoundException("Пользователь не найден")

        # Получаем команду пользователя только для текущего события
        command = await self.users_dao.find_user_command_in_event(
            user_id=user_id,
            event_id=event_id
        )

        # Перемещаем форматирование участников в utils
        from .utils import format_participants 
        commands_info = []
        if command:
            participants = format_participants(command.users, include_role=True)
            # Находим роль пользователя в команде
            user_role = None
            for cu in command.users:
                if cu.user_id == user_id:
                    user_role = cu.role.name
                    break
            
            command_info = CommandInfo(
                id=command.id,
                name=command.name,
                role=user_role or "member",
                event_id=command.event_id,
                language_id=command.language_id,
                participants=participants
            ).model_dump()
            commands_info.append(command_info)

        total_score = 0
        try:
            total_score = await self.program_dao.get_total_score(user.id)
        except Exception as e:
            logger.warning(f"Не удалось получить баллы для пользователя {user.id}: {e}")

        user_profile = {
            "id": user.id,
            "full_name": user.full_name,
            "telegram_id": user.telegram_id,
            "telegram_username": user.telegram_username,
            "role": RoleModel(id=user.role.id, name=user.role.name).model_dump() if user.role else None,
            "commands": commands_info,
            "is_looking_for_friends": user.is_looking_for_friends,
            "score": total_score
        }

        if user.role and user.role.name in ["insider", "ctc"] and user.insider_info:
            student_organization = None
            if user.role.name == "insider":
                student_organization = user.insider_info.student_organization
            elif user.role.name == "ctc":
                student_organization = "СтС" 
            
            user_profile["insider_info"] = {
                "student_organization": student_organization,
                "geo_link": user.insider_info.geo_link
            }
            
        return user_profile

    async def update_profile(self, user: User, request: UpdateProfileRequest) -> None:
        """Обновляет ФИО и информацию инсайдера/СтС и инвалидирует кэш профиля."""
        try:
            # Update user's full name directly on the object
            user.full_name = request.full_name
            self.session.add(user) # Add user to session to track changes

            if user.role and user.role.name in ["insider", "ctc"]:
                student_organization_to_save = None
                geo_link_to_save = request.geo_link

                if user.role.name == "insider":
                    student_organization_to_save = request.student_organization
                elif user.role.name == "ctc":
                    # Ensure insider_info exists for СтС before potentially saving geo_link
                    if not user.insider_info:
                        await self.insiders_dao.create_or_update(user_id=user.id, student_organization="СтС")
                        # Re-fetch user or manually create insider_info object if needed immediately
                    student_organization_to_save = "СтС" # This isn't saved in the db column usually

                if student_organization_to_save is not None or geo_link_to_save is not None:
                    await self.insiders_dao.create_or_update(
                        user_id=user.id,
                        student_organization=student_organization_to_save if user.role.name == "insider" else None, # Only save for insider
                        geo_link=geo_link_to_save
                    )
            
            # Commit changes within the service method
            await self.session.commit()
            logger.info(f"User profile {user.id} updated and committed successfully.")
            
            # Cache invalidation removed

        except SQLAlchemyError as db_err:
             logger.exception(f"Database error updating profile for user {user.id}")
             await self.session.rollback()
             raise InternalServerErrorException("Ошибка базы данных при обновлении профиля.")
        except Exception as e:
             logger.exception(f"Unexpected error updating profile for user {user.id}")
             await self.session.rollback()
             raise InternalServerErrorException("Непредвиденная ошибка при обновлении профиля.")

    async def toggle_looking_for_team(self, user_id: int) -> bool:
        """Переключает флаг поиска команды для пользователя."""
        current_user = await self.users_dao.find_one_by_id(user_id)
        if not current_user:
            raise NotFoundException("Пользователь не найден")
        
        current_user.is_looking_for_friends = not current_user.is_looking_for_friends
        # Коммит будет выполнен в роутере через зависимость get_session_with_commit
        # await self.session.commit() - убираем явный коммит из сервиса
        return current_user.is_looking_for_friends

    async def get_users_looking_for_team(self, current_user_id: int) -> List[Dict[str, Any]]:
         """Возвращает список пользователей, ищущих команду, исключая текущего."""
         looking_users = await self.users_dao.find_all_looking_for_team()
         
         users_list = [
             {
                 "id": u.id,
                 "full_name": u.full_name,
                 "telegram_username": u.telegram_username,
                 # Информацию о команде и капитанстве лучше получать отдельно при необходимости,
                 # чтобы не усложнять этот запрос
                 # "is_captain": getattr(u, "is_captain", False), # Убираем
                 # "team_name": getattr(u, "team_name", None)   # Убираем
             }
             for u in looking_users if u.id != current_user_id
         ]
         return users_list


class QRService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users_dao = UsersDAO(session)
        self.program_dao = ProgramDAO(session)

    async def generate_qr_for_user(self, user: User, session_token: str, domain: str = None) -> Dict[str, str]:
        """Генерирует QR-код для пользователя."""
        # Используем переданный домен или fallback на настройки
        if domain:
            # Определяем схему (http/https) на основе домена
            scheme = "https" if domain not in ["localhost", "127.0.0.1"] else "http"
            base_url = f"{scheme}://{domain}"
        else:
            base_url = settings.BASE_URL
            
        qr_link = f"{base_url}/qr/verify?token={session_token}"
        qr_data = generate_qr_image(qr_link)
        return {
            "qr_link": qr_link,
            "qr_image": base64.b64encode(qr_data).decode("utf-8")
        }

    async def verify_qr_and_get_info(self, scanner_user: User, qr_token: str, event_id: int) -> Dict[str, Any]:
        """Проверяет QR-код и возвращает информацию в зависимости от роли сканирующего."""
        
        from .utils import format_participants  # Импорт внутри метода
        from .utils import get_user_role_in_command
        
        try:
            # Используем SessionDAO для валидации токена и получения пользователя
            session_dao = SessionDAO(self.session)
            qr_user_session = await session_dao.get_session(qr_token)
            if not qr_user_session:
                 raise TokenExpiredException("Срок действия QR-кода или ссылки истек.")
                 
            qr_user = await self.users_dao.find_one_by_id(
                qr_user_session.user_id, 
                options=[selectinload(User.role)] # Загружаем роль
            )
            if not qr_user:
                 raise NotFoundException("Пользователь по QR-коду не найден.")
                 
        except TokenExpiredException as e:
             logger.warning(f"Недействительный токен при проверке QR: {e}")
             raise # Передаем исключение дальше
        except Exception as e:
            logger.error(f"Ошибка при получении пользователя по QR-коду {qr_token}: {e}")
            raise InternalServerErrorException("Ошибка при проверке QR-кода.")

        # Получаем команду пользователя из QR для конкретного события
        qr_user_command = await self.users_dao.find_user_command_in_event(
             user_id=qr_user.id,
             event_id=event_id
         )
        if not qr_user_command:
            logger.warning(f"Пользователь {qr_user.id} (из QR) не состоит в команде")
            return {"ok": False, "message": "Пользователь не состоит в команде"}

        qr_user_role_name, is_captain = get_user_role_in_command(qr_user_command.users, qr_user.id)

        # Получаем команду сканирующего пользователя для конкретного события
        scanner_user_command = await self.users_dao.find_user_command_in_event(user_id=scanner_user.id, event_id=event_id)

        scanner_role_name = scanner_user.role.name if scanner_user.role else None
        
        if not scanner_role_name or scanner_role_name not in ["insider", "organizer", "guest", "ctc"]:
            raise ForbiddenException("Недостаточно прав для проверки QR-кода")

        if scanner_role_name in ["insider", "organizer", "ctc"]:
            participants = format_participants(qr_user_command.users, include_role=False)
            response_data = {
                "ok": True,
                "scanner_role": scanner_role_name,
                "is_captain": is_captain,
                "user": {
                    "id": qr_user.id,
                    "full_name": qr_user.full_name,
                    "role": qr_user.role.name if qr_user.role else None,
                    "telegram_id": qr_user.telegram_id,
                    "telegram_username": qr_user.telegram_username
                },
                "command": {
                    "id": qr_user_command.id,
                    "name": qr_user_command.name,
                    "event_id": qr_user_command.event_id,
                    "participants": participants
                }
            }
            
            if scanner_role_name == "ctc":
                try:
                    total_score = await self.program_dao.get_total_score(qr_user.id)
                    response_data["program"] = {"total_score": total_score, "can_add_score": True}
                except Exception as e:
                    logger.error(f"Ошибка при получении баллов пользователя {qr_user.id} при сканировании QR: {e}")
                    response_data["program"] = {"total_score": 0, "can_add_score": True, "error": "Не удалось загрузить баллы"}

            can_join = scanner_role_name == "organizer" and not scanner_user_command and is_captain and len(qr_user_command.users) < 6
            join_reason = None
            if not can_join:
                 join_reason = ("already_in_team" if scanner_user_command else
                                "not_captain" if not is_captain else
                                "team_full" if len(qr_user_command.users) >= 6 else
                                "only_guests_can_join" if scanner_role_name != 'guest' else # Уточнение для не-гостей
                                "unknown")

            response_data.update({
                "can_join": can_join,
                "join_reason": join_reason,
                "command_name": qr_user_command.name,
                "captain_name": qr_user.full_name,
                "token": qr_token # Возвращаем токен для возможности присоединения
            })
            return response_data
            
        elif scanner_role_name == "guest":
             # Логика для гостя
             if not is_captain:
                  return {"ok": False, "message": "Только QR капитана команды позволяет присоединиться"}
                  
             can_join = not scanner_user_command and len(qr_user_command.users) < 6
             join_reason = None
             if not can_join:
                  join_reason = ("already_in_team" if scanner_user_command else
                                "team_full" if len(qr_user_command.users) >= 6 else
                                "unknown")
             
             return {
                 "ok": True,
                 "message": "QR-код проверен",
                 "can_join": can_join,
                 "join_reason": join_reason,
                 "command_name": qr_user_command.name,
                 "captain_name": qr_user.full_name,
                 "token": qr_token
             }
        else:
             # На всякий случай, если роли не совпали
             raise ForbiddenException("Ваша роль не позволяет выполнить это действие")

# --- Command Service ---
class CommandService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users_dao = UsersDAO(session)
        self.commands_dao = CommandsDAO(session)
        self.commands_users_dao = CommandsUsersDAO(session)
        self.roles_users_dao = RolesUsersCommandDAO(session)
        self.events_dao = EventsDAO(session)

    async def get_user_command_info(self, user_id: int, event_id: int) -> Command:
        """Получает информацию о команде текущего пользователя для текущего события."""
        command = await self.users_dao.find_user_command_in_event(user_id=user_id, event_id=event_id)
        if not command:
            raise NotFoundException("Команда не найдена")
        return command # Возвращаем ORM модель, валидация будет в роутере

    async def create_command(self, user: User, command_data: CommandEdit, event_name: str) -> None:
        """Создает новую команду и назначает пользователя капитаном."""
        curr_event_id = await self.events_dao.get_event_id_by_name(event_name)
        if not curr_event_id:
            logger.error(f"Не удалось получить ID события '{event_name}' при создании команды")
            raise InternalServerErrorException("Не удалось получить информацию о текущем событии.")

        existing_command = await self.commands_dao.find_one_or_none(filters=CommandNameAndEvent(name=command_data.name, event_id=curr_event_id))
        if existing_command:
            logger.warning(f"Попытка создать команду с существующим именем: {command_data.name} в событии {event_name}")
            raise BadRequestException("Команда с таким названием уже существует.")

        command = await self.commands_dao.add(values=CommandBase(
            name=command_data.name, 
            event_id=curr_event_id, 
            language_id=command_data.language_id
        ))
        logger.info(f"Создана новая команда с ID {command.id}")

        captain_role_id = await self.roles_users_dao.get_role_id(role_name="captain") # Явно указываем роль
        if not captain_role_id:
            logger.error("Не удалось получить ID роли капитана")
            raise InternalServerErrorException("Не удалось получить информацию о роли капитана.")

        await self.commands_users_dao.add(CommandsUserBase(
            command_id=command.id,
            user_id=user.id,
            role_id=captain_role_id
        ))
        logger.info(f"Пользователь {user.id} назначен капитаном команды {command.id}")

    async def _validate_captain(self, user_id: int, event_id: int) -> Command:
        """Проверяет, является ли пользователь капитаном своей команды, и возвращает команду."""
        command = await self.users_dao.find_user_command_in_event(
            user_id=user_id,
            event_id=event_id
        )
        if not command:
            raise NotFoundException("Команда не найдена")
            
        from .utils import get_user_role_in_command
        _, is_captain = get_user_role_in_command(command.users, user_id)
        if not is_captain:
            raise ForbiddenException("Только капитан может выполнить это действие")
        return command

    async def delete_command(self, user: User, event_id: int) -> None:
        """Удаляет команду, если пользователь является капитаном."""
        command = await self._validate_captain(user.id, event_id)
        await self.commands_dao.delete_by_id(command.id)
        logger.info(f"Команда {command.id} удалена капитаном {user.id}")

    async def rename_command(self, user: User, command_data: CommandEdit, event_id: int) -> None:
        """Переименовывает команду и обновляет язык, если пользователь является капитаном."""
        command = await self._validate_captain(user.id, event_id)
        
        existing_command = await self.commands_dao.find_one_or_none(filters=CommandNameAndEvent(name=command_data.name, event_id=event_id))
        if existing_command and existing_command.id != command.id:
            logger.warning(f"Попытка переименовать команду {command.id} в существующее имя: {command_data.name} в событии {event_id}")
            raise BadRequestException("Команда с таким названием уже существует.")
            
        await self.commands_dao.update_name(command.id, command_data.name, command_data.language_id)
        logger.info(f"Команда {command.id} переименована капитаном {user.id} в '{command_data.name}'")

    async def leave_command(self, user: User, event_id: int) -> None:
        """Позволяет пользователю покинуть команду, если он не капитан."""
        command = await self.users_dao.find_user_command_in_event(
            user_id=user.id,
            event_id=event_id
        )
        if not command:
            raise NotFoundException("Команда не найдена")
            
        from .utils import get_user_role_in_command
        _, is_captain = get_user_role_in_command(command.users, user.id)
        if is_captain:
            raise ForbiddenException("Капитан не может покинуть команду. Вместо этого удалите команду.")
            
        await self.commands_users_dao.delete_by_user_id(user.id)
        logger.info(f"Пользователь {user.id} покинул команду {command.id}")

    async def remove_user_from_command(self, captain: User, user_to_remove_id: int, event_id: int) -> None:
        """Удаляет пользователя из команды, если текущий пользователь - капитан, а удаляемый - нет."""
        command = await self._validate_captain(captain.id, event_id) # Проверяем, что текущий юзер - капитан
        
        target_user_command_user = next((cu for cu in command.users if cu.user_id == user_to_remove_id), None)
        if not target_user_command_user:
            raise NotFoundException("Пользователь не найден в команде")
            
        from .utils import get_user_role_in_command
        _, target_is_captain = get_user_role_in_command(command.users, user_to_remove_id)
        if target_is_captain:
            # Это не должно произойти, если в команде только один капитан, но проверим
            raise ForbiddenException("Нельзя исключить капитана из команды")
            
        await self.commands_users_dao.delete_by_user_id(user_to_remove_id)
        logger.info(f"Капитан {captain.id} исключил пользователя {user_to_remove_id} из команды {command.id}")

    async def join_command_via_qr(self, scanner_user: User, qr_token: str, event_id: int) -> None:
        """Обрабатывает присоединение пользователя к команде через QR-токен капитана."""
        from .utils import get_user_role_in_command

        # 1. Получаем пользователя по QR токену
        try:
            session_dao = SessionDAO(self.session)
            qr_user_session = await session_dao.get_session(qr_token)
            if not qr_user_session:
                 raise TokenExpiredException("Срок действия QR-кода или ссылки истек.")
            qr_user = await self.users_dao.find_one_by_id(qr_user_session.user_id)
            if not qr_user:
                 raise NotFoundException("Пользователь по QR-коду не найден.")
        except TokenExpiredException as e:
             logger.warning(f"Недействительный токен при попытке присоединения: {e}")
             raise
        except Exception as e:
            logger.error(f"Ошибка при получении пользователя по QR-коду {qr_token[:5]}... : {e}", exc_info=True)
            raise InternalServerErrorException("Ошибка при проверке QR-кода.")
        
        # 2. Получаем команду владельца QR для конкретного события
        qr_user_command = await self.users_dao.find_user_command_in_event(
            user_id=qr_user.id,
            event_id=event_id
        )
        if not qr_user_command:
            raise BadRequestException("Пользователь не состоит в команде")
            
        # 3. Проверяем, что владелец QR - капитан
        _, is_captain = get_user_role_in_command(qr_user_command.users, qr_user.id)
        if not is_captain:
            raise BadRequestException("Только QR капитана команды позволяет присоединиться")
            
        # 4. Проверяем, не состоит ли сканирующий пользователь уже в команде
        scanner_user_command = await self.users_dao.find_user_command_in_event(user_id=scanner_user.id, event_id=event_id)
        if scanner_user_command:
            raise BadRequestException("Вы уже состоите в другой команде")
            
        # 5. Проверяем, не состоит ли сканирующий пользователь уже в ЭТОЙ команде
        if any(cu.user_id == scanner_user.id for cu in qr_user_command.users):
             raise BadRequestException("Вы уже состоите в этой команде")
             
        # 6. Проверяем максимальное количество участников
        if len(qr_user_command.users) >= 6:
            raise BadRequestException("В команде уже максимальное количество участников")
            
        # 7. Получаем роль участника и добавляем пользователя
        member_role_id = await self.roles_users_dao.get_role_id(role_name="member")
        if not member_role_id:
            logger.error("Роль 'member' не найдена в базе данных при присоединении к команде")
            raise InternalServerErrorException("Ошибка конфигурации ролей.")
            
        await self.commands_users_dao.add(CommandsUserBase(
            command_id=qr_user_command.id,
            user_id=scanner_user.id,
            role_id=member_role_id
        ))
        logger.info(f"Пользователь {scanner_user.id} успешно добавлен в команду {qr_user_command.id} через QR")


class EventService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.events_dao = EventsDAO(session)

    async def check_event_status(self, user: Optional[User], event_name: str) -> bool:
        """Проверяет, активно ли указанное событие."""
        try:
            # Проверяем, является ли пользователь организатором
            if user and user.role and user.role.name == "organizer":
                # Организаторы всегда могут входить в квест
                return True
            
            event_id = await self.events_dao.get_event_id_by_name(event_name)
            
            if not event_id:
                return False
            
            is_active = await self.events_dao.is_event_active(event_id)
            return is_active
        except Exception as e:
            logger.error(f"Ошибка при проверке активности события '{event_name}': {e}", exc_info=True)
            # В случае ошибки считаем событие неактивным для безопасности
            return False


class ProgramService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.program_dao = ProgramDAO(session)
        self.users_dao = UsersDAO(session) # Нужен для проверки существования пользователя

    async def add_score(self, target_user_id: int, score_data: ProgramScoreAdd, current_user: User):
        """Добавляет баллы пользователю с проверкой прав."""
        logger.info(f"Попытка добавления баллов пользователю {target_user_id} пользователем {current_user.id}")

        # Проверяем права текущего пользователя
        if not current_user.role or current_user.role.name not in ["ctc", "organizer"]:
            raise ForbiddenException("Недостаточно прав для добавления баллов")

        # Проверяем, что целевой пользователь существует
        target_user = await self.users_dao.find_one_by_id(target_user_id)
        if not target_user:
            raise NotFoundException("Целевой пользователь не найден")
        
        try:
            # Добавляем баллы
            await self.program_dao.add_score(
                user_id=target_user_id,
                score=score_data.score,
                comment=score_data.comment
            )
            
            # Получаем обновленную сумму баллов
            total_score = await self.program_dao.get_total_score(target_user_id)
            return total_score
        except Exception as e:
            logger.error(f"Ошибка при добавлении баллов пользователю {target_user_id}: {str(e)}", exc_info=True)
            await self.session.rollback() # Откатываем транзакцию здесь
            raise InternalServerErrorException("Ошибка при добавлении баллов")

    async def get_user_score(self, target_user_id: int, current_user: User) -> ProgramScoreTotal:
        """Получает информацию о баллах пользователя с проверкой прав."""
        logger.info(f"Получение информации о баллах пользователя {target_user_id} (запросил {current_user.id})")

        # Проверяем, что пользователь имеет право просматривать эту информацию
        if current_user.id != target_user_id and (not current_user.role or current_user.role.name not in ["ctc", "organizer"]):
            raise ForbiddenException("Недостаточно прав для просмотра баллов другого пользователя")

        try:
            # Проверяем существование пользователя (хотя бы для логов, если нужно)
            # target_user = await self.users_dao.find_one_by_id(target_user_id)
            # if not target_user:
            #     raise NotFoundException("Пользователь не найден")
            
            # Получаем информацию о баллах
            total_score = await self.program_dao.get_total_score(target_user_id)
            history_records = await self.program_dao.get_score_history(target_user_id)
            
            # Формируем ответ
            result = ProgramScoreTotal(
                user_id=target_user_id,
                total_score=total_score,
                history=[ProgramScoreInfo.model_validate(record) for record in history_records]
            )
            return result
        except Exception as e:
            logger.error(f"Ошибка при получении информации о баллах для {target_user_id}: {str(e)}", exc_info=True)
            raise InternalServerErrorException("Ошибка при получении информации о баллах")

    async def qr_add_score(self, token: str, score_data: ProgramScoreAdd, scanner_user: User, event_id: int) -> Dict[str, Any]:
        """Добавляет баллы по QR-коду с проверкой прав сканирующего."""
        logger.info(f"Попытка добавления баллов по QR-коду пользователем {scanner_user.id}")

        # Проверяем права сканирующего пользователя
        if not scanner_user.role or scanner_user.role.name not in ["ctc", "organizer"]:
            raise ForbiddenException("Недостаточно прав для добавления баллов по QR")

        try:
            # Получаем пользователя, чей QR сканировали (валидирует токен)
            # Используем SessionDAO для валидации токена и получения пользователя
            session_dao = SessionDAO(self.session)
            qr_user_session = await session_dao.get_session(token)
            if not qr_user_session:
                raise TokenExpiredException("Недействительный или истекший QR-код.")
                
            qr_user = await self.users_dao.find_one_by_id(qr_user_session.user_id)
            if not qr_user:
                raise NotFoundException("Пользователь по QR-коду не найден.")

            # Добавляем баллы
            await self.program_dao.add_score(
                user_id=qr_user.id,
                score=score_data.score,
                comment=score_data.comment
            )

            # Получаем обновленную сумму баллов
            total_score = await self.program_dao.get_total_score(qr_user.id)

            return {
                "user_id": qr_user.id,
                "user_name": qr_user.full_name,
                "total_score": total_score
            }
        except TokenExpiredException as e:
            logger.warning(f"Истекший токен при добавлении баллов по QR: {e}")
            raise e # Пробрасываем TokenExpiredException
        except Exception as e:
            qr_user_id = qr_user.id if 'qr_user' in locals() else 'unknown'
            logger.error(f"Ошибка при добавлении баллов по QR пользователю {qr_user_id}: {str(e)}", exc_info=True)
            await self.session.rollback()
            raise InternalServerErrorException("Ошибка при добавлении баллов по QR")


class StatsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users_dao = UsersDAO(session)
        self.commands_dao = CommandsDAO(session)
        self.event_dao = EventsDAO(session)

    async def get_registration_stats(self, current_user: User, event_name: str) -> Dict[str, Any]:
        """Собирает и возвращает статистику по регистрациям только для текущего события."""
        logger.info(f"Запрос статистики регистраций пользователем {current_user.id} для события '{event_name}'")

        # Проверяем роль пользователя
        if not current_user.role or current_user.role.name not in ["organizer", "ctc"]:
            logger.warning(f"Отказано в доступе пользователю {current_user.id} к статистике регистраций")
            raise ForbiddenException("Недостаточно прав для просмотра статистики")
        
        try:
            # Получаем текущее событие
            curr_event_id = await self.event_dao.get_event_id_by_name(event_name)
            if not curr_event_id:
                logger.error(f"Не удалось получить информацию о событии '{event_name}' для статистики")
                raise InternalServerErrorException(f"Не удалось получить информацию о событии '{event_name}'")
            
            # Получаем команды текущего события с загрузкой связанных пользователей
            teams = await self.commands_dao.find_all_by_event(
                curr_event_id,
                options=[selectinload(Command.users)] # Пользователи нужны только для подсчета размера команды
            )
            
            total_teams = len(teams)
            
            # Получаем распределение по командам
            team_sizes = {i: 0 for i in range(1, 7)} # Инициализируем нулями
            team_members_sum = 0
            for team in teams:
                size = len(team.users)
                if 1 <= size <= 6:
                    team_sizes[size] += 1
                    team_members_sum += size
                
            # Подсчитываем общее количество пользователей и активных пользователей (с ролью) только для event_id
            total_users = await self.users_dao.count_all_users_by_event(curr_event_id)
            active_users = await self.users_dao.count_users_with_role_by_event(curr_event_id)
            looking_for_team = await self.users_dao.count_users_looking_for_friends_by_event(curr_event_id)
            
            # Получаем статистику регистраций по дням (только для гостей)
            registrations_by_date = []
            try:
                registrations_by_date = await self.users_dao.get_registrations_by_date_by_event(curr_event_id, "guest")
                logger.info(f"Получены данные о регистрациях гостей по дням: {len(registrations_by_date)} записей")
            except Exception as e:
                logger.error(f"Ошибка при получении данных о регистрациях гостей по дням: {e}", exc_info=True)
            
            # Получаем статистику пользователей по ролям
            roles_distribution = {}
            try:
                roles_distribution = await self.users_dao.get_users_by_role_by_event(curr_event_id)
                logger.info(f"Получены данные о распределении пользователей по ролям")
            except Exception as e:
                logger.error(f"Ошибка при получении данных о распределении пользователей по ролям: {e}", exc_info=True)
                
            # Получаем статистику пользователей с необычным ФИО (оставляем без фильтрации по event_id)
            unusual_name_count = 0
            unusual_name_registrations = []
            try:
                unusual_name_count = await self.users_dao.count_users_with_unusual_name()
                unusual_name_registrations = await self.users_dao.get_unusual_name_registrations_by_date()
                logger.info(f"Получены данные о пользователях с необычным ФИО: {unusual_name_count}")
            except Exception as e:
                logger.error(f"Ошибка при получении данных о пользователях с необычным ФИО: {e}", exc_info=True)
            
            # Вычисляем средний размер команды
            average_team_size = (team_members_sum / total_teams) if total_teams > 0 else 0
            
            # Собираем статистику
            stats = {
                "total_users": total_users,
                "active_users": active_users,
                "total_teams": total_teams,
                "team_distribution": team_sizes,
                "users_looking_for_team": looking_for_team,
                "average_team_size": round(average_team_size, 2), # Округляем
                "registrations_by_date": registrations_by_date,
                "roles_distribution": roles_distribution,
                "unusual_name_count": unusual_name_count,
                "unusual_name_registrations": unusual_name_registrations
            }
            
            logger.info(f"Статистика регистраций успешно собрана")
            return stats
            
        except (ForbiddenException, InternalServerErrorException) as e:
             raise e # Пробрасываем ожидаемые ошибки
        except Exception as e:
            logger.error(f"Ошибка при получении статистики регистраций: {str(e)}", exc_info=True)
            raise InternalServerErrorException("Внутренняя ошибка сервера при получении статистики")

    async def get_command_leaderboard(self, event_name: str) -> CommandLeaderboardData:
        """Формирует и возвращает лидерборд команд для события."""
        logger.info(f"Запрос лидерборда команд для события '{event_name}' (доступен всем)")

        try:
            # 1. Получаем ID события по имени
            target_event_id = await self.event_dao.get_event_id_by_name(event_name=event_name)
            if not target_event_id:
                logger.warning(f"Событие с именем '{event_name}' не найдено для лидерборда")
                # Возвращаем пустой лидерборд, а не ошибку
                return CommandLeaderboardData(leaderboard=[]) 
                
            # 2. Получаем все команды указанного события, ЗАГРУЖАЕМ язык и пользователей
            commands = await self.commands_dao.find_all_by_event(
                target_event_id,
                options=[
                    selectinload(Command.language),
                    selectinload(Command.users).selectinload(CommandsUser.user) # Не нужно для подсчета очков, но может понадобиться для отображения
                ]
            )

            if not commands:
                logger.info(f"В событии '{event_name}' нет команд для лидерборда")
                return CommandLeaderboardData(leaderboard=[])

            # 4. Вычисляем score и coins для каждой команды на основе верных попыток
            leaderboard_results: List[CommandLeaderboardEntry] = []
            for command in commands:
                user_ids = [cu.user_id for cu in command.users if cu.user_id is not None]

                total_score_base = 0.0 # Сумма AttemptType.score
                total_coins_base = 0   # Сумма AttemptType.money

                if user_ids:
                    # Запрос для суммирования базовых очков и монет за ВСЕ верные попытки пользователей команды
                    stmt = (
                        select(
                            func.sum(AttemptType.score).label("total_score"),
                            func.sum(AttemptType.money).label("total_coins")
                        )
                        .join(Attempt, Attempt.attempt_type_id == AttemptType.id)
                        .where(
                            Attempt.user_id.in_(user_ids),
                            Attempt.is_true == True,
                        )
                    )
                    result = await self.session.execute(stmt)
                    scores = result.fetchone()
                    if scores and scores.total_score is not None:
                        total_score_base = float(scores.total_score)
                    if scores and scores.total_coins is not None:
                        total_coins_base = int(scores.total_coins)

                # Применяем формулу: total_score = (coins * 0.5) + score
                final_total_score = (total_coins_base * 0.5) + total_score_base
                
                # Применяем фильтр >= 2 к финальному баллу
                if final_total_score > 2:
                    leaderboard_results.append(CommandLeaderboardEntry(
                        command_name=command.name,
                        total_score=final_total_score,
                        language_name=command.language.name if command.language else None,
                    ))

            logger.info(f"Лидерборд для события '{event_name}' (score={total_score_base}, coins={total_coins_base}, final=coins*0.5+score, filter: >= 2) успешно сформирован, найдено {len(leaderboard_results)} команд")

            # 5. Сортируем по убыванию финального очка
            leaderboard_results.sort(key=lambda x: x.total_score, reverse=True)
            
            return CommandLeaderboardData(leaderboard=leaderboard_results)

        except Exception as e:
            logger.error(f"Ошибка при формировании лидерборда команд для события '{event_name}': {str(e)}", exc_info=True)
            # Не пробрасываем ошибку, возвращаем пустой лидерборд
            # raise InternalServerErrorException(f"Внутренняя ошибка сервера при формировании лидерборда для '{event_name}")
            return CommandLeaderboardData(leaderboard=[]) # Возвращаем пустой, чтобы не ломать фронт
