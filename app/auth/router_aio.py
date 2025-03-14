from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.dao import UsersDAO
from app.auth.schemas import TelegramModel, UserBase
from app.dependencies.dao_dep import get_session_with_commit
from app.exceptions import UserAlreadyExistsException
from app.logger import logger
from fastapi import Depends

class Auth(StatesGroup):
    full_name = State()

router = Router()

@router.message(Command("start"))
async def start(message: Message, state: FSMContext):
    async for session in get_session_with_commit():
        user_dao = UsersDAO(session)
        user_data = TelegramModel(telegram_id=message.from_user.id, telegram_username=message.from_user.username)
        existing_user = await user_dao.find_one_or_none(filters=user_data)
        if existing_user:
            logger.info(f"{existing_user.id} {UserAlreadyExistsException}")
            await message.answer(get_info_user(existing_user))

        else:
            await message.answer("Введите ФИО")
            await state.set_state(Auth.full_name)
@router.message(Auth.full_name)
async def full_name(message: Message, state: FSMContext):
    async for session in get_session_with_commit():
        user_dao = UsersDAO(session)
        await state.update_data(full_name=message.text)
        data = await state.get_data()
        user_data = TelegramModel(telegram_id=message.from_user.id, telegram_username=message.from_user.username)
        existing_user = await user_dao.find_one_or_none(filters=user_data)
        if existing_user:
            logger.info(f"{existing_user.id} {UserAlreadyExistsException}")
        else:
            user_data_dict = user_data.model_dump()
            existing_user = await user_dao.add(values=UserBase(**user_data_dict, **data))
        await message.answer(get_info_user(existing_user))

@router.message(Command("profile"))
async def profile(message: Message, state: FSMContext, session: AsyncSession = Depends(get_session_with_commit)):
    users_dao = UsersDAO(session)
    user = await users_dao.find_one_or_none(filters=TelegramModel(telegram_id=message.from_user.id, telegram_username=message.from_user.username))
    if user:
        await message.answer(user.to_dict())
    else:
        await message.answer("Вы не зарегистрированы")

def get_info_user(user: User):
    return repr(user)
