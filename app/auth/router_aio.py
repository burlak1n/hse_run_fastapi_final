from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.auth.models import User, RoleUserCommand, Role
from app.auth.dao import CommandsUsersDAO, UsersDAO
from app.auth.schemas import UserBase, UserFullname, UserID, TelegramModel
from app.dependencies.dao_dep import get_session_with_commit
from app.exceptions import UserAlreadyExistsException
from app.logger import logger

class Auth(StatesGroup):
    full_name = State()
    change_full_name = State()
    create_command = State()

router = Router()

@router.message(Command("start"))
async def start(message: Message, state: FSMContext):
    async for session in get_session_with_commit():
        user_dao = UsersDAO(session)
        user_data = UserID(telegram_id=message.from_user.id)
        existing_user = await user_dao.find_one_or_none(filters=user_data)
        if existing_user:
            logger.info(f"{existing_user.id} {UserAlreadyExistsException}")

            text, keyboard = await get_profile_text(existing_user)
            await message.answer(text, reply_markup=keyboard)

        else:
            await message.answer("Введите ФИО")
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
    data = await state.get_data()
    await message.answer("Команда успешно создана")

async def init_router():
    async for session in get_session_with_commit():
        rolesusercommand = [
            RoleUserCommand(name="member"),
            RoleUserCommand(name="captain"),
        ]

        roles = [
            Role(name="guest"),
            Role(name="organizer"),
            Role(name="insider"),
        ]

        # Добавляем роли в базу данных
        session.add_all(rolesusercommand)
        session.add_all(roles)

        session.commit()

def get_info_user(user: User):
    return repr(user)

# async def get_info_command_user(user: User):
#     async for session in get_session_with_commit():
#         command_dao = CommandsUsersDAO(session)
#         command_users = await command_dao.find_all(UserID(command_id=user.command_id))
#         return repr(command_users)

async def get_profile_text(user: User):
    user_info = get_info_user(user)
    builder = InlineKeyboardBuilder()
    builder.button(text="Изменить ФИО", callback_data="change_full_name")
    builder.button(text="Удалить аккаунт", callback_data="delete_account")
    # builder.button(text="Выйти из профиля", callback_data="exit_profile")
    # command_info = await get_info_command_user(user)
    # if command_info:
    #     text = f"{user_info}\n\n{command_info}"
    #     builder.button(text="Выйти из команды", callback_data="exit_command")
    # else:
    #     text = user_info
    #     builder.button(text="Создать команду", callback_data="create_command")
    text = user_info
    return text, builder.as_markup()