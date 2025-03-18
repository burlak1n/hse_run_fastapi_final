from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.auth.models import CommandsUser, User, RoleUserCommand, Role, Event
from app.auth.dao import CommandsDAO, CommandsUsersDAO, SessionDAO, UsersDAO, EventsDAO
from app.auth.schemas import CommandID, UserBase, UserFullname, UserID, TelegramModel, CommandBase, EventID, CommandName
from app.dependencies.dao_dep import get_session_with_commit
from app.exceptions import UserAlreadyExistsException
from app.logger import logger
from app.config import EVENT_NAME

class Auth(StatesGroup):
    full_name = State()
    change_full_name = State()
    create_command = State()
    change_command_name = State()
router = Router()

@router.message(Command("start"))
async def start(message: Message):
    text, keyboard = await get_menu_text(message.from_user.id)
    await message.answer(text, reply_markup=keyboard)


async def get_menu_text(user_id: int):
    async for session in get_session_with_commit():
        user_dao = UsersDAO(session)
        user_data = UserID(telegram_id=user_id)
        existing_user: User | None = await user_dao.find_one_or_none(filters=user_data)
        builder = InlineKeyboardBuilder()

        if existing_user and existing_user.role_id:
            session_dao = SessionDAO(session)
            session_token = await session_dao.get_session_token(user_id)
            builder.button(text="Профиль", callback_data=f"profile {session_token}")
        else:
            builder.button(text="Зарегистрироваться", callback_data="register")
        builder.button(text="Начать квест", callback_data="start_quest")
        builder.adjust(1)
        return "HSE RUN 29", builder.as_markup()

@router.callback_query(F.data == "register")
async def register(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Введите ФИО")
    await state.set_state(Auth.full_name)

@router.message(Auth.full_name)
async def full_name(message: Message, state: FSMContext):
    async for session in get_session_with_commit():
        user_dao = UsersDAO(session)
        await state.update_data(full_name=message.text)
        data = await state.get_data()
        user_data = UserID(telegram_id=message.from_user.id)
        existing_user = await user_dao.find_one_or_none(filters=user_data)
        if existing_user:
            logger.info(f"{existing_user.id} {UserAlreadyExistsException}")
        else:
            user_data_dict = user_data.model_dump()
            user_data_dict.update(data)
            user_data_dict.update({"telegram_username": message.from_user.username})
            existing_user = await user_dao.add(values=UserBase(**user_data_dict))
        text, keyboard = await get_profile_text(existing_user)
        await message.answer(text, reply_markup=keyboard)

@router.message(Command("profile"))
async def profile(message: Message, state: FSMContext):
    async for session in get_session_with_commit():
        users_dao = UsersDAO(session)
        user = await users_dao.find_one_or_none(filters=UserID(telegram_id=message.from_user.id))
        if user:
            text, keyboard = await get_profile_text(user)
            await message.answer(text, reply_markup=keyboard)
        else:
            await message.answer("Вы не зарегистрированы. Пожалуйста, введите ФИО для регистрации.")
            await state.set_state(Auth.full_name)

@router.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    async for session in get_session_with_commit():
        users_dao = UsersDAO(session)
        user = await users_dao.find_one_or_none(filters=UserID(telegram_id=callback.from_user.id))
        if user:
            text, keyboard = await get_profile_text(user)
            await callback.message.answer(text, reply_markup=keyboard)
        else:
            await callback.message.answer("Вы не зарегистрированы. Пожалуйста, введите ФИО для регистрации.")
            await state.set_state(Auth.full_name)

@router.callback_query(F.data == "change_full_name")
async def change_full_name(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Введите новое ФИО")
    await state.set_state(Auth.change_full_name)

@router.message(Auth.change_full_name)
async def process_change_full_name(message: Message, state: FSMContext):
    async for session in get_session_with_commit():
        users_dao = UsersDAO(session)
        user = await users_dao.find_one_or_none(filters=UserID(telegram_id=message.from_user.id))
        if user:
            await users_dao.update(UserID(telegram_id=user.telegram_id), UserFullname(full_name=message.text))
            await message.answer("ФИО успешно изменено")
            text, keyboard = await get_profile_text(user)
            await message.answer(text, reply_markup=keyboard)
        else:
            await message.answer("Пользователь не найден")
        await state.clear()

@router.callback_query(F.data == "delete_account")
async def delete_account(callback: CallbackQuery):
    await callback.answer()
    async for session in get_session_with_commit():
        users_dao = UsersDAO(session)
        user = await users_dao.find_one_or_none(filters=UserID(telegram_id=callback.from_user.id))
        if user:
            await users_dao.delete(UserID(telegram_id=user.telegram_id))
            await callback.message.answer("Аккаунт успешно удалён")
        else:
            await callback.message.answer("Пользователь не найден")

@router.callback_query(F.data == "create_command")
async def create_command(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Введите название команды")
    await state.set_state(Auth.create_command)

@router.message(Auth.create_command)
async def process_create_command(message: Message, state: FSMContext):
    await state.update_data(command_name=message.text)
    async for session in get_session_with_commit():
        users_dao = UsersDAO(session)
        user = await users_dao.find_one_or_none(filters=UserID(telegram_id=message.from_user.id))
        if user:
            command_dao = CommandsDAO(session)
            event_dao = EventsDAO(session)

            # TODO Ходить с event id | Объёктом id
            event = await event_dao.find_one_or_none(filters=EventID(name=EVENT_NAME))
            
            command = await command_dao.add(values=CommandBase(name=message.text, event_id=event.id))

            stmt = select(RoleUserCommand).where(RoleUserCommand.name.in_(["captain", "member"]))
            result = await session.execute(stmt)
            roles = result.scalars().all()
            
            role_captain = next((role for role in roles if role.name == "captain"), None)
            command_user = await users_dao.create_command_user(command_id=command.id, user_id=user.id, role_id=role_captain.id)
             
            await message.answer("Команда успешно создана")
            text, keyboard = await get_profile_text(user)
            await message.answer(text, reply_markup=keyboard)
        else:
            await message.answer("Пользователь не найден")

@router.callback_query(F.data.startswith("change_command_name"))
async def change_command_name(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer("Введите новое название команды")
    await state.update_data(command_id=int(callback.data.split()[1]))
    await state.set_state(Auth.change_command_name)

@router.message(Auth.change_command_name)
async def process_change_command_name(message: Message, state: FSMContext):
    logger.info(f"Пользователь {message.from_user.id} начал процесс изменения названия команды")
    await state.update_data(command_name=message.text)
    data = await state.get_data()
    async for session in get_session_with_commit():
        #TODO вынести в отдельную middleware
        users_dao = UsersDAO(session)
        user: User = await users_dao.find_one_or_none(filters=UserID(telegram_id=message.from_user.id))
        if not user:
            logger.warning(f"Пользователь {message.from_user.id} не найден в базе данных")
            await message.answer("Пользователь не найден")
            return

        command_dao = CommandsDAO(session)
        # Проверяем, существует ли команда с таким названием
        existing_command = await command_dao.find_one_or_none(filters=CommandName(name=data["command_name"]))
        if existing_command:
            logger.warning(f"Попытка создания дубликата команды с именем {data['command_name']}")
            await message.answer("Команда с таким названием уже существует. Попробуйте другое")
            await state.clear()
            await state.set_state(Auth.change_command_name)
            return

        # Меняем название команды
        command = await command_dao.find_one_or_none(filters=CommandID(id=data["command_id"]))
        if command:
            logger.info(f"Обновление названия команды {command.id} на {data['command_name']}")
            await command_dao.update(CommandID(id=command.id), CommandName(name=data["command_name"]))
            logger.info(f"Название команды {command.id} успешно изменено")
            await message.answer(f"Название команды успешно изменено на '{data['command_name']}'")
        else:
            logger.warning(f"Команда с ID {data['command_id']} не найдена")
            await message.answer("Команда не найдена")

def get_info_user(user: User):
    return repr(user)

async def get_info_command_user(user: User):
    async for session in get_session_with_commit():
        users_dao = UsersDAO(session)
        command_users = await users_dao.find_user_command_in_event(user.id, EVENT_NAME)
        if command_users:
            is_captain = await users_dao.is_user_captain_in_command(user.id, command_users.id)
            return command_users, is_captain
        return None



async def get_profile_text(user: User):
    user_info = get_info_user(user)
    builder = InlineKeyboardBuilder()
    builder.button(text="Изменить ФИО", callback_data="change_full_name")
    builder.button(text="Удалить аккаунт", callback_data="delete_account")
    # builder.button(text="Выйти из профиля", callback_data="exit_profile")
    command_info = await get_info_command_user(user)
    if command_info:
        command_info_str = repr(command_info[0])
        if command_info[1]:
            text = f"{user_info}\n\n{command_info_str}"
            builder.button(text="Пригласить в команду", callback_data="invite_command")
            builder.button(text="Удалить команду", callback_data="delete_command")
            builder.button(text="Изменить название команды", callback_data=f"change_command_name {command_info[0].id}")
        else:
            text = f"{user_info}\n\nВы член команды {command_info[0].name}"
            builder.button(text="Выйти из команды", callback_data="exit_command")
    else:
        text = user_info
        builder.button(text="Создать команду", callback_data="create_command")
    
    builder.button(text="Назад", callback_data="menu")
    builder.adjust(2)  # Ограничиваем количество кнопок в строке до 2
    return text, builder.as_markup()

async def user_middleware(handler, event, data):
    """Middleware для получения пользователя по сессии"""
    user_id = event.from_user.id
    async for session in get_session_with_commit():
        # Получаем токен сессии
        session_dao = SessionDAO(session)
        session_token = await session_dao.get_session_token(user_id)
        
        # Проверяем наличие сессии
        if not session_token:
            await event.answer("Сессия не найдена")
            return
        
        # Ищем пользователя по telegram_id
        users_dao = UsersDAO(session)
        user = await users_dao.find_one_or_none(filters=UserID(telegram_id=user_id))
        
        # Проверяем наличие пользователя
        if not user:
            await event.answer("Пользователь не найден")
            return
        
        # Возвращаем пользователя и токен сессии
        return {
            'user': user,
            'session_token': session_token
        }

router.message.middleware(user_middleware)
router.callback_query.middleware(user_middleware)
