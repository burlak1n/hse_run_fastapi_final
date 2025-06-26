from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
import os
import re
from typing import Optional
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from loguru import logger

# Импорты из основного приложения
import sys
sys.path.append('/projects/hse_run_full/backend')

from app.dao.database import Base
from app.auth.models import User, Role, Command, CommandsUser, RoleUserCommand, Event, Language, UserProfile
from app.auth.dao import UsersDAO, RolesDAO, CommandsDAO, CommandsUsersDAO, RolesUsersCommandDAO, EventsDAO, LanguagesDAO, UserProfileDAO, CommandInviteDAO
from app.auth.schemas import SUserAddDB, UserTelegramID, RoleFilter, CommandBase, CommandsUserBase

load_dotenv()

# Разрешенные домены для email
ALLOWED_EMAIL_DOMAINS = [
    "edu.hse.ru"
]

# Инициализация бота и диспетчера
bot = Bot(token=os.getenv("BOT_TOKEN"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Подключение к отдельной БД для бота
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./registration_bot.db")
engine = create_async_engine(DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Определение состояний FSM
class RegistrationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_email = State()

class CommandStates(StatesGroup):
    waiting_for_command_name = State()

class JoinStates(StatesGroup):
    pending_join = State()  # Состояние для запоминания приглашения

async def get_async_session() -> AsyncSession:
    """Получение асинхронной сессии базы данных"""
    async with async_session_maker() as session:
        return session

def validate_full_name(name: str) -> bool:
    """Валидация ФИО (должно содержать минимум 2 слова)"""
    if not name or not name.strip():
        return False
    words = [word for word in name.strip().split() if word]  # Убираем пустые строки
    if len(words) < 2:
        return False
    # Проверяем, что каждое слово содержит только буквы
    for word in words:
        if not word.replace('-', '').replace("'", '').isalpha():
            return False
    return True

def validate_email(email: str) -> bool:
    """Валидация email с проверкой разрешенных доменов"""
    if not email or not email.strip():
        return False
    
    email = email.strip().lower()
    
    # Простая проверка формата email
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False
    
    # Проверяем домен
    domain = email.split('@')[1]
    return domain in ALLOWED_EMAIL_DOMAINS

async def is_user_registered(telegram_id: int) -> tuple[bool, Optional[User]]:
    """Проверяет, зарегистрирован ли пользователь полностью"""
    async with async_session_maker() as session:
        users_dao = UsersDAO(session)
        profile_dao = UserProfileDAO(session)
        user = await users_dao.find_one_or_none(filters=UserTelegramID(telegram_id=telegram_id))
        
        if not user:
            return False, None
        
        # Проверяем, заполнено ли ФИО, email в профиле и установлена ли роль
        profile = await profile_dao.get_by_user_id(user.id)
        if (user.full_name and user.full_name.strip() and 
            profile and profile.email and user.role_id):
            return True, user
        return False, user

async def create_or_get_user(telegram_id: int, telegram_username: str = None) -> Optional[User]:
    """Создает или получает существующего пользователя"""
    async with async_session_maker() as session:
        users_dao = UsersDAO(session)
        
        # Сначала пытаемся найти существующего пользователя
        user = await users_dao.find_one_or_none(filters=UserTelegramID(telegram_id=telegram_id))
        
        if not user:
            # Создаем нового пользователя
            try:
                user = await users_dao.add(values=SUserAddDB(
                    full_name="",  # Пустое ФИО, будет заполнено позже
                    telegram_id=telegram_id,
                    telegram_username=telegram_username
                ))
                await session.commit()  # Явно коммитим транзакцию
                logger.info(f"Создан новый пользователь с Telegram ID: {telegram_id}")
            except Exception as e:
                logger.error(f"Ошибка при создании пользователя {telegram_id}: {e}")
                await session.rollback()
                return None
        
        return user

async def update_user_name(telegram_id: int, full_name: str) -> bool:
    """Обновляет ФИО пользователя"""
    async with async_session_maker() as session:
        try:
            users_dao = UsersDAO(session)
            user = await users_dao.find_one_or_none(filters=UserTelegramID(telegram_id=telegram_id))
            if not user:
                return False
            
            user.full_name = full_name
            await session.commit()
            logger.info(f"Обновлено ФИО пользователя {telegram_id}: {full_name}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при обновлении ФИО пользователя {telegram_id}: {e}")
            await session.rollback()
            return False

async def complete_user_registration(telegram_id: int, email: str) -> bool:
    """Завершает регистрацию пользователя - устанавливает email в профиле и роль guest"""
    async with async_session_maker() as session:
        try:
            users_dao = UsersDAO(session)
            roles_dao = RolesDAO(session)
            profile_dao = UserProfileDAO(session)
            
            # Получаем пользователя
            user = await users_dao.find_one_or_none(filters=UserTelegramID(telegram_id=telegram_id))
            if not user:
                return False
            
            # Получаем роль guest, создаем если не существует
            guest_role = await roles_dao.find_one_or_none(filters=RoleFilter(name="guest"))
            if not guest_role:
                logger.warning("Роль guest не найдена, создаем...")
                try:
                    # Создаем роль напрямую через модель
                    from app.auth.models import Role
                    guest_role = Role(name="guest")
                    session.add(guest_role)
                    await session.flush()  # Чтобы получить ID сразу
                    logger.info(f"Роль 'guest' создана с ID: {guest_role.id}")
                except Exception as e:
                    logger.error(f"Ошибка при создании роли guest: {e}")
                    await session.rollback()
                    return False
            
            # Создаем/обновляем профиль пользователя с email
            await profile_dao.create_or_update(user_id=user.id, email=email)
            
            # Устанавливаем роль пользователю
            user.role_id = guest_role.id
            await session.commit()
            
            logger.info(f"Завершена регистрация пользователя {telegram_id}: {email}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при завершении регистрации пользователя {telegram_id}: {e}")
            await session.rollback()
            return False

async def get_user_profile(telegram_id: int) -> Optional[dict]:
    """Получает профиль пользователя с информацией о команде"""
    async with async_session_maker() as session:
        try:
            users_dao = UsersDAO(session)
            profile_dao = UserProfileDAO(session)
            commands_dao = CommandsDAO(session)
            
            user = await users_dao.find_one_or_none(filters=UserTelegramID(telegram_id=telegram_id))
            if not user:
                return None
            
            # Получаем профиль пользователя с email
            user_profile = await profile_dao.get_by_user_id(user.id)
            
            # Поиск команды пользователя
            user_command = await users_dao.find_user_command_in_event(user_id=user.id, event_id=1)
            logger.info(f"Команда найдена: {user_command.name if user_command else 'Нет команды'}")
            
            profile = {
                "full_name": user.full_name,
                "email": user_profile.email if user_profile else None,
                "has_team": user_command is not None,
                "team_info": None
            }
            
            if user_command:
                # Получаем UUID приглашения для команды
                invite_dao = CommandInviteDAO(session)
                invite_uuid = await invite_dao.get_uuid_by_command_id(user_command.id)
                
                # Если UUID не найден для существующей команды, создаем его
                if not invite_uuid:
                    logger.info(f"UUID не найден для команды {user_command.id}, создаем новый")
                    invite_uuid = await invite_dao.create_invite(user_command.id, auto_commit=True)
                
                # Получаем информацию о команде и роли пользователя
                profile["team_info"] = {
                    "name": user_command.name,
                    "command_id": user_command.id,
                    "invite_uuid": invite_uuid,
                    "members_count": len(user_command.users),
                    "is_captain": any(cu.user_id == user.id and cu.role.name == "captain" 
                                    for cu in user_command.users)
                }
            
            return profile
        except Exception as e:
            logger.error(f"Ошибка при получении профиля пользователя {telegram_id}: {e}")
            return None

async def create_command(telegram_id: int, command_name: str) -> tuple[bool, str]:
    """Создает команду и назначает пользователя капитаном"""
    async with async_session_maker() as session:
        try:
            users_dao = UsersDAO(session)
            commands_dao = CommandsDAO(session)
            commands_users_dao = CommandsUsersDAO(session)
            roles_users_dao = RolesUsersCommandDAO(session)
            invite_dao = CommandInviteDAO(session)
            
            # Получаем пользователя
            user = await users_dao.find_one_or_none(filters=UserTelegramID(telegram_id=telegram_id))
            if not user:
                return False, "Пользователь не найден"
            
            # Проверяем, не состоит ли уже в команде
            existing_command = await users_dao.find_user_command_in_event(user_id=user.id, event_id=1)
            if existing_command:
                return False, f"Вы уже состоите в команде '{existing_command.name}'"
            
            # Создаем команду
            command = await commands_dao.add(values=CommandBase(
                name=command_name,
                event_id=1,  # По умолчанию событие с ID 1
                language_id=1  # По умолчанию язык с ID 1
            ))
            
            # Получаем роль капитана
            captain_role_id = await roles_users_dao.get_role_id(role_name="captain")
            if not captain_role_id:
                return False, "Ошибка при получении роли капитана"
            
            # Назначаем пользователя капитаном
            await commands_users_dao.add(CommandsUserBase(
                command_id=command.id,
                user_id=user.id,
                role_id=captain_role_id
            ))
            
            # Создаем UUID приглашение для команды
            invite_uuid = await invite_dao.create_invite(command.id)
            
            # Коммитим все изменения
            await session.commit()
            
            # Создаем ссылку для присоединения (используем UUID)
            bot_info = await bot.get_me()
            invite_link = f"https://t.me/{bot_info.username}?start=join_{invite_uuid}"
            
            logger.info(f"Создана команда {command_name} (ID: {command.id}) с UUID {invite_uuid} капитаном {telegram_id}")
            return True, invite_link
            
        except Exception as e:
            logger.error(f"Ошибка при создании команды {command_name}: {e}")
            await session.rollback()
            return False, "Ошибка при создании команды"

# Обработчик команды /start
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Проверяем, есть ли параметр для присоединения к команде
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    if args and args[0].startswith("join_"):
        invite_uuid = args[0].replace("join_", "")
        
        # Если пользователь зарегистрирован, сразу добавляем в команду
        is_registered, user = await is_user_registered(user_id)
        if is_registered:
            await handle_join_command(message, invite_uuid)
            return
        else:
            # Если не зарегистрирован, сохраняем UUID и начинаем регистрацию
            await state.set_data({"pending_invite_uuid": invite_uuid})
            await state.set_state(JoinStates.pending_join)
            
            # Создаем пользователя в базе
            user_obj = await create_or_get_user(user_id, username)
            if not user_obj:
                await message.answer("Произошла ошибка при регистрации. Попробуйте позже.")
                return
            
            await state.set_state(RegistrationStates.waiting_for_name)
            await message.answer("Привет! Для присоединения к команде сначала нужно зарегистрироваться.\n\nВведи своё ФИО:")
            return
    
    # Проверяем, зарегистрирован ли пользователь
    is_registered, user = await is_user_registered(user_id)
    
    if is_registered:
        # Пользователь уже зарегистрирован
        await message.answer(f"Здравствуйте, {user.full_name}! Вы уже зарегистрированы.\n\nИспользуйте /profile для просмотра профиля или /create для создания команды.")
        return
    
    # Если пользователь не зарегистрирован, создаем его в базе или получаем существующего
    user_obj = await create_or_get_user(user_id, username)
    if not user_obj:
        await message.answer("Произошла ошибка при регистрации. Попробуйте позже.")
        return
    
    await state.set_state(RegistrationStates.waiting_for_name)
    await message.answer("Привет! Для регистрации введи своё ФИО")

# Обработчик ввода ФИО
@dp.message(RegistrationStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    full_name = message.text.strip()
    
    # Валидируем ФИО
    if not validate_full_name(full_name):
        await message.answer(
            "❌ Неверный формат ФИО!\n\n"
            "Требования:\n"
            "• Минимум 2 слова (имя и фамилия)\n"
            "• Только буквы (допускаются дефис и апостроф)\n"
            "• Пример: Иван Петров\n\n"
            "Попробуй еще раз:"
        )
        return
    
    # Обновляем ФИО пользователя
    success = await update_user_name(user_id, full_name)
    if not success:
        await message.answer("Произошла ошибка при сохранении данных. Попробуйте позже.")
        return
    
    # Сохраняем данные о приглашении, если они есть
    state_data = await state.get_data()
    await state.set_state(RegistrationStates.waiting_for_email)
    if state_data.get("pending_invite_uuid"):
        await state.set_data({"pending_invite_uuid": state_data["pending_invite_uuid"]})
    
    await message.answer("✅ Отлично! Теперь введи корпоративную почту")

# Обработчик ввода email
@dp.message(RegistrationStates.waiting_for_email)
async def process_email(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    email = message.text.strip()
    
    # Валидируем email
    if not validate_email(email):
        domains_text = ", ".join(ALLOWED_EMAIL_DOMAINS[:8]) + "..." if len(ALLOWED_EMAIL_DOMAINS) > 8 else ", ".join(ALLOWED_EMAIL_DOMAINS)
        await message.answer(
            f"❌ Неверный формат почты!\n\n"
            f"Разрешенные домены:\n{domains_text}\n\n"
            f"Попробуй еще раз:"
        )
        return
    
    # Завершаем регистрацию пользователя
    success = await complete_user_registration(user_id, email)
    if not success:
        await message.answer("Произошла ошибка при сохранении данных. Попробуйте позже.")
        return
    
    # Логируем информацию о пользователе
    logger.info(f"Зарегистрирован новый пользователь ID: {user_id}, email: {email}")
    
    # Проверяем, есть ли сохраненное приглашение
    state_data = await state.get_data()
    pending_invite_uuid = state_data.get("pending_invite_uuid")
    
    # Сбрасываем состояние
    await state.clear()
    
    if pending_invite_uuid:
        # Если есть сохраненное приглашение, автоматически добавляем в команду
        await message.answer("✅ Регистрация завершена! Теперь добавляем тебя в команду...")
        await handle_join_command(message, pending_invite_uuid)
    else:
        # Отправляем стандартное подтверждение
        await message.answer(
            "Поздравляем, ты зарегистрирован! Чтобы принять участие в квесте нужно создать команду или присоединиться к существующей.\n\n"
            "Для создания введи /create, для присоединения получи от капитана ссылку, которая находится в профиле (/profile)"
        )

# Команда для просмотра профиля
@dp.message(F.text == "/profile")
async def cmd_profile(message: types.Message):
    user_id = message.from_user.id
    
    # Проверяем регистрацию
    is_registered, user = await is_user_registered(user_id)
    if not is_registered:
        await message.answer("Вы не зарегистрированы. Используйте команду /start")
        return
    
    profile = await get_user_profile(user_id)
    if not profile:
        await message.answer("Ошибка при получении профиля")
        return
    
    profile_text = f"👤 Профиль\n\n"
    profile_text += f"ФИО: {profile['full_name']}\n"
    profile_text += f"Email: {profile['email']}\n\n"
    
    if profile['has_team']:
        team_info = profile['team_info']
        role = "Капитан" if team_info['is_captain'] else "Участник"
        profile_text += f"🚀 Команда: {team_info['name']}\n"
        profile_text += f"Роль: {role}\n"
        profile_text += f"Участников: {team_info['members_count']}/6\n\n"
        
        # Получаем список участников команды
        async with async_session_maker() as session:
            from sqlalchemy import text
            members_query = text("""
                SELECT u.full_name, ruc.name as role_name
                FROM users u
                JOIN commandsusers cu ON u.id = cu.user_id
                JOIN roleusercommands ruc ON cu.role_id = ruc.id
                WHERE cu.command_id = :command_id
                ORDER BY CASE WHEN ruc.name = 'captain' THEN 0 ELSE 1 END, u.full_name
            """)
            members_result = await session.execute(members_query, {"command_id": team_info['command_id']})
            members = members_result.fetchall()
            
            profile_text += "👥 Участники:\n"
            for member in members:
                if member.role_name == "captain":
                    profile_text += f"👑 {member.full_name}\n"
                else:
                    profile_text += f"👤 {member.full_name}\n"
        
        if team_info['is_captain']:
            # Для капитана показываем ссылку для приглашения с UUID
            invite_uuid = team_info.get('invite_uuid')
            if invite_uuid:
                bot_info = await bot.get_me()
                invite_url = f"https://t.me/{bot_info.username}?start=join_{invite_uuid}"
                profile_text += f"\n🔗 <a href='{invite_url}'>Пригласить в команду</a> (Пришли эту ссылку друзьям)"
    else:
        profile_text += "❗ Команда: не создана\n\n"
        profile_text += "Для создания команды введи /create\n"
        profile_text += "Для присоединения к команде получи ссылку от капитана"
    
    # Используем HTML форматирование для кликабельной ссылки
    await message.answer(profile_text, parse_mode="HTML")

# Команда для создания команды
@dp.message(F.text == "/create")
async def cmd_create(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Проверяем регистрацию
    is_registered, user = await is_user_registered(user_id)
    if not is_registered:
        await message.answer("Вы не зарегистрированы. Используйте команду /start")
        return
    
    # Проверяем, нет ли уже команды у пользователя
    async with async_session_maker() as session:
        users_dao = UsersDAO(session)
        existing_command = await users_dao.find_user_command_in_event(user_id=user.id, event_id=1)
        
        if existing_command:
            await message.answer(
                f"❌ У вас уже есть команда '{existing_command.name}'!\n\n"
                f"Один пользователь может состоять только в одной команде.\n"
                f"Для просмотра информации о команде используйте /profile"
            )
            return
    
    await state.set_state(CommandStates.waiting_for_command_name)
    await message.answer("Введи название команды")

# Обработчик ввода названия команды
@dp.message(CommandStates.waiting_for_command_name)
async def process_command_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    command_name = message.text.strip()
    
    if not command_name:
        await message.answer("Название команды не может быть пустым. Попробуйте еще раз:")
        return
    
    # Создаем команду
    success, result = await create_command(user_id, command_name)
    if not success:
        await message.answer(f"Ошибка при создании команды: {result}")
        return
    
    # Сбрасываем состояние
    await state.clear()
    
    # Отправляем ссылку для приглашения
    await message.answer(
        f"Команда '{command_name}' успешно создана! 🎉\n\n"
        f"А теперь пришли эту [ссылку]({result}) друзьям, которых хочешь пригласить в команду!",
        parse_mode="Markdown"
    )

# Обработчик присоединения к команде по ссылке
async def handle_join_command(message: types.Message, invite_uuid: str):
    user_id = message.from_user.id
    
    # Проверяем регистрацию
    is_registered, user = await is_user_registered(user_id)
    if not is_registered:
        await message.answer("Сначала нужно зарегистрироваться. Используйте команду /start")
        return
    
    async with async_session_maker() as session:
        try:
            users_dao = UsersDAO(session)
            invite_dao = CommandInviteDAO(session)
            commands_users_dao = CommandsUsersDAO(session)
            roles_users_dao = RolesUsersCommandDAO(session)
            
            # Проверяем, не состоит ли уже в команде
            existing_command = await users_dao.find_user_command_in_event(user_id=user.id, event_id=1)
            if existing_command:
                await message.answer(f"❌ Вы уже состоите в команде '{existing_command.name}'!")
                return
            
            # Ищем команду по UUID приглашения
            command = await invite_dao.find_command_by_uuid(invite_uuid)
            if not command:
                await message.answer("❌ Ссылка недействительна или команда не найдена")
                return
            
            # Проверяем, не переполнена ли команда (максимум 6 человек)
            # Используем прямой SQL запрос для подсчета участников
            from sqlalchemy import text, func
            count_query = text("SELECT COUNT(*) FROM commandsusers WHERE command_id = :command_id")
            count_result = await session.execute(count_query, {"command_id": command.id})
            current_members_count = count_result.scalar()
            
            if current_members_count >= 6:
                await message.answer(f"❌ Команда '{command.name}' уже заполнена (6/6 участников)")
                return
            
            # Получаем роль участника команды
            member_role_id = await roles_users_dao.get_role_id(role_name="member")
            if not member_role_id:
                await message.answer("❌ Ошибка при получении роли участника")
                return
            
            # Используем прямой SQL запрос для вставки, чтобы избежать проблем с SQLAlchemy
            from sqlalchemy import text
            insert_query = text("""
                INSERT INTO commandsusers (command_id, user_id, role_id) 
                VALUES (:command_id, :user_id, :role_id)
            """)
            
            await session.execute(insert_query, {
                "command_id": command.id,
                "user_id": user.id, 
                "role_id": member_role_id
            })
            
            await session.commit()
            
            # Используем уже посчитанное количество участников
            current_members = current_members_count + 1  # +1 за нового участника
            await message.answer(
                f"🎉 Добро пожаловать в команду '{command.name}'!\n\n"
                f"Участников в команде: {current_members}/6\n\n"
                f"Для просмотра информации о команде используйте /profile"
            )
            
            logger.info(f"Пользователь {user_id} присоединился к команде {command.name} (ID: {command.id})")
            
        except Exception as e:
            logger.error(f"Ошибка при присоединении к команде: {e}")
            await session.rollback()
            await message.answer("❌ Произошла ошибка при присоединении к команде")

# Команда для повторной регистрации
@dp.message(F.text == "/reregister")
async def cmd_reregister(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Проверяем, что пользователь существует в базе
    async with async_session_maker() as session:
        users_dao = UsersDAO(session)
        user = await users_dao.find_one_or_none(filters=UserTelegramID(telegram_id=user_id))
        if not user:
            await message.answer("Вы не зарегистрированы. Используйте команду /start")
            return
    
    await state.set_state(RegistrationStates.waiting_for_name)
    await message.answer("Пожалуйста, введите ваше ФИО заново")

# Обработчик неизвестных сообщений
@dp.message()
async def handle_unknown_message(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == RegistrationStates.waiting_for_name:
        await message.answer("Пожалуйста, введите ваше ФИО. Если хотите начать заново, используйте /start")
    elif current_state == RegistrationStates.waiting_for_email:
        await message.answer("Пожалуйста, введите корпоративную почту. Если хотите начать заново, используйте /start")
    elif current_state == CommandStates.waiting_for_command_name:
        await message.answer("Пожалуйста, введите название команды. Если хотите начать заново, используйте /create")
    else:
        await message.answer("Для регистрации используйте команду /start\nДля просмотра профиля: /profile\nДля создания команды: /create")

# Создание таблиц в базе данных
async def create_tables():
    """Создает все необходимые таблицы для работы бота"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Создаем базовые данные
    async with async_session_maker() as session:
        try:
            # Создаем основные роли пользователей
            from app.auth.models import Role
            roles_dao = RolesDAO(session)
            guest_role = await roles_dao.find_one_or_none(filters=RoleFilter(name="guest"))
            if not guest_role:
                guest_role = Role(name="guest")
                session.add(guest_role)
                await session.commit()
                logger.info("Создана роль 'guest'")
            
            admin_role = await roles_dao.find_one_or_none(filters=RoleFilter(name="admin"))
            if not admin_role:
                admin_role = Role(name="admin")
                session.add(admin_role)
                await session.commit()
                logger.info("Создана роль 'admin'")
            
            # Создаем роли для команд
            # Проверяем captain роль напрямую через SQL
            query_captain = select(RoleUserCommand).filter_by(name="captain")
            result_captain = await session.execute(query_captain)
            captain_role = result_captain.scalar_one_or_none()
            
            if not captain_role:
                captain_role = RoleUserCommand(name="captain")
                session.add(captain_role)
                await session.flush()  # Получаем ID сразу
                logger.info(f"Создана роль 'captain' с ID: {captain_role.id}")
            
            # Проверяем member роль напрямую через SQL
            query_member = select(RoleUserCommand).filter_by(name="member")
            result_member = await session.execute(query_member)
            member_role = result_member.scalar_one_or_none()
            
            if not member_role:
                member_role = RoleUserCommand(name="member")
                session.add(member_role)
                await session.flush()  # Получаем ID сразу
                logger.info(f"Создана роль 'member' с ID: {member_role.id}")
            
            await session.commit()  # Коммитим все роли для команд
            
            # Создаем событие по умолчанию
            query_event = select(Event).filter_by(name="KRUN")
            result_event = await session.execute(query_event)
            default_event = result_event.scalar_one_or_none()
            if not default_event:
                default_event = Event(name="KRUN")
                session.add(default_event)
                await session.commit()
                logger.info("Создано событие 'KRUN'")
            
            # Создаем язык по умолчанию
            query_language = select(Language).filter_by(name="Русский")
            result_language = await session.execute(query_language)
            default_language = result_language.scalar_one_or_none()
            if not default_language:
                default_language = Language(name="Русский")
                session.add(default_language)
                await session.commit()
                logger.info("Создан язык 'Русский'")
                
        except Exception as e:
            logger.error(f"Ошибка при создании базовых данных: {e}")
            await session.rollback()

# Запуск бота
async def main():
    logger.info("Запуск регистрационного бота KRUN")
    
    # Удаляем webhook (если был установлен)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook удален")
    except Exception as e:
        logger.error(f"Ошибка при удалении webhook: {e}")
    
    # Создаем таблицы и необходимые данные
    try:
        logger.info("Начинаем инициализацию базы данных...")
        await create_tables()
        logger.info("База данных успешно инициализирована")
        
        # Проверяем, что все роли созданы, если нет - создаем принудительно
        async with async_session_maker() as session:
            roles_dao = RolesDAO(session)
            guest_role = await roles_dao.find_one_or_none(filters=RoleFilter(name="guest"))
            if guest_role:
                logger.info(f"Роль 'guest' найдена с ID: {guest_role.id}")
            else:
                logger.warning("Роль 'guest' не найдена после инициализации, создаем принудительно...")
                try:
                    # Создаем роль напрямую через модель
                    from app.auth.models import Role
                    guest_role = Role(name="guest")
                    session.add(guest_role)
                    await session.commit()
                    logger.info(f"Роль 'guest' принудительно создана с ID: {guest_role.id}")
                except Exception as e:
                    logger.error(f"Ошибка при принудительном создании роли 'guest': {e}")
                    await session.rollback()
            
            # Проверяем роли для команд
            query_captain = select(RoleUserCommand).filter_by(name="captain")
            result_captain = await session.execute(query_captain)
            captain_role = result_captain.scalar_one_or_none()
            
            if captain_role:
                logger.info(f"Роль 'captain' найдена с ID: {captain_role.id}")
            else:
                logger.warning("Роль 'captain' не найдена, создаем принудительно...")
                try:
                    captain_role = RoleUserCommand(name="captain")
                    session.add(captain_role)
                    await session.commit()
                    logger.info(f"Роль 'captain' принудительно создана с ID: {captain_role.id}")
                except Exception as e:
                    logger.error(f"Ошибка при принудительном создании роли 'captain': {e}")
                    await session.rollback()
            
            query_member = select(RoleUserCommand).filter_by(name="member")
            result_member = await session.execute(query_member)
            member_role = result_member.scalar_one_or_none()
            
            if member_role:
                logger.info(f"Роль 'member' найдена с ID: {member_role.id}")
            else:
                logger.warning("Роль 'member' не найдена, создаем принудительно...")
                try:
                    member_role = RoleUserCommand(name="member")
                    session.add(member_role)
                    await session.commit()
                    logger.info(f"Роль 'member' принудительно создана с ID: {member_role.id}")
                except Exception as e:
                    logger.error(f"Ошибка при принудительном создании роли 'member': {e}")
                    await session.rollback()
                
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        return
        
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
