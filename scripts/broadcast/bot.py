import logging
import sys
import asyncio
import json
from os import getenv
from dotenv import load_dotenv

# Импорт основных классов бота и диспетчера
from aiogram import Bot, Dispatcher, types, F

# Константа ParseMode теперь находится в aiogram.enums
from aiogram.enums import ParseMode

# Импорт хранилищ для состояний (MemoryStorage и RedisStorage)
from aiogram.fsm.storage.memory import MemoryStorage

# Контекст FSM теперь находится в aiogram.fsm.context
from aiogram.fsm.context import FSMContext

# Состояния для FSM – из aiogram.fsm.state
from aiogram.fsm.state import State, StatesGroup

# Импорт необходимых типов сообщений (например, для создания inline-клавиатур)
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Импорт фильтров для нового регистрационного синтаксиса
from aiogram.filters import Command
from aiogram.filters.state import StateFilter

# Импорт ваших модулей
# from components.service.data_form import (
#     register_handlers as register_data_form_handlers,
# )
# from components.service.menu import register_menu_handlers
# from components.photo.bot import router as photo_router

# Импорт для работы с базой данных
import aiosqlite

# Дополнительный импорт для настройки свойств бота
from aiogram.client.bot import DefaultBotProperties

# Загрузка переменных окружения
load_dotenv()

# Получение токена и ID администраторов из .env
TOKEN = getenv("BOT_TOKEN")
ADMINS_ID = list(
    map(int, getenv("ADMINS_ID", "").split(","))
)  # Убедитесь, что ADMINS_ID задан в .env
ORGANIZER_POINTS_JSON = getenv("ORGANIZER_POINTS", "{}")
ORGANIZER_POINTS = json.loads(ORGANIZER_POINTS_JSON)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(
    token=TOKEN, default_bot_properties=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

storage = MemoryStorage()

dp = Dispatcher(bot=bot, storage=storage)

# Глобальный словарь для хранения сообщений администраторам
admin_messages = {}


class BroadcastState(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirmation = State()
    waiting_for_short_names_message = State()
    waiting_for_short_names_confirmation = State()


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS_ID:
        await message.reply("У вас нет прав использовать эту команду.")
        logger.warning(
            f"Пользователь {message.from_user.id} попытался использовать /broadcast без прав."
        )
        return
    await message.reply("Пожалуйста, отправьте сообщение для рассылки.")
    await state.set_state(BroadcastState.waiting_for_message)


@dp.message(Command("broadcast_short_names"))
async def cmd_broadcast_short_names(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS_ID:
        await message.reply("У вас нет прав использовать эту команду.")
        logger.warning(
            f"Пользователь {message.from_user.id} попытался использовать /broadcast_short_names без прав."
        )
        return
    await message.reply("Пожалуйста, отправьте сообщение для рассылки пользователям с ФИО менее 3 слов.")
    await state.set_state(BroadcastState.waiting_for_short_names_message)


@dp.message(StateFilter(BroadcastState.waiting_for_message))
async def broadcast_message_handler(message: types.Message, state: FSMContext):
    await state.update_data(broadcast_message=message)

    # Создаем инлайн-клавиатуру с кнопками подтверждения
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить", callback_data="confirm_broadcast"
                ),
                InlineKeyboardButton(text="Отменить", callback_data="cancel_broadcast"),
            ]
        ]
    )

    if message.content_type == "text":
        await message.answer(
            "Вы хотите отправить следующее текстовое сообщение всем пользователям:",
            reply_markup=keyboard,
        )
        await message.answer(message.text, disable_web_page_preview=True)
    elif message.content_type in ["photo", "document", "video", "audio"]:
        await message.answer(
            f"Вы хотите отправить следующее {message.content_type} сообщение всем пользователям:",
            reply_markup=keyboard,
        )
        if message.content_type == "photo":
            await message.answer_photo(
                message.photo[-1].file_id, caption=message.caption or ""
            )
        elif message.content_type == "document":
            await message.answer_document(
                message.document.file_id, caption=message.caption or ""
            )
        elif message.content_type == "video":
            await message.answer_video(
                message.video.file_id, caption=message.caption or ""
            )
        elif message.content_type == "audio":
            await message.answer_audio(
                message.audio.file_id, caption=message.caption or ""
            )
    else:
        await message.answer(
            "Этот тип сообщений не поддерживается для рассылки.", reply_markup=keyboard
        )
        await state.finish()
        return

    await state.set_state(BroadcastState.waiting_for_confirmation)


@dp.callback_query(
    F.data == "confirm_broadcast", StateFilter(BroadcastState.waiting_for_confirmation)
)
async def confirm_broadcast(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    broadcast_message = data.get("broadcast_message")

    await callback_query.answer("Рассылка началась. Это может занять некоторое время.")
    await bot.send_message(callback_query.from_user.id, "Рассылка запущена.")

    # Запускаем рассылку в отдельной задаче
    asyncio.create_task(broadcast_to_all_users(broadcast_message))
    await state.clear()


@dp.callback_query(
    F.data == "cancel_broadcast", StateFilter(BroadcastState.waiting_for_confirmation)
)
async def cancel_broadcast(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback_query.from_user.id, "Рассылка отменена.")
    await state.clear()
    await callback_query.answer()
    logger.info("Рассылка отменена администратором.")


@dp.message(StateFilter(BroadcastState.waiting_for_short_names_message))
async def short_names_message_handler(message: types.Message, state: FSMContext):
    await state.update_data(broadcast_message=message)

    # Создаем инлайн-клавиатуру с кнопками подтверждения
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить", callback_data="confirm_short_names_broadcast"
                ),
                InlineKeyboardButton(text="Отменить", callback_data="cancel_broadcast"),
            ]
        ]
    )

    if message.content_type == "text":
        await message.answer(
            "Вы хотите отправить следующее текстовое сообщение пользователям с ФИО менее 3 слов:",
            reply_markup=keyboard,
        )
        await message.answer(message.text, disable_web_page_preview=True)
    elif message.content_type in ["photo", "document", "video", "audio"]:
        await message.answer(
            f"Вы хотите отправить следующее {message.content_type} сообщение пользователям с ФИО менее 3 слов:",
            reply_markup=keyboard,
        )
        if message.content_type == "photo":
            await message.answer_photo(
                message.photo[-1].file_id, caption=message.caption or ""
            )
        elif message.content_type == "document":
            await message.answer_document(
                message.document.file_id, caption=message.caption or ""
            )
        elif message.content_type == "video":
            await message.answer_video(
                message.video.file_id, caption=message.caption or ""
            )
        elif message.content_type == "audio":
            await message.answer_audio(
                message.audio.file_id, caption=message.caption or ""
            )
    else:
        await message.answer(
            "Этот тип сообщений не поддерживается для рассылки.", reply_markup=keyboard
        )
        await state.finish()
        return

    await state.set_state(BroadcastState.waiting_for_short_names_confirmation)


@dp.callback_query(
    F.data == "confirm_short_names_broadcast", 
    StateFilter(BroadcastState.waiting_for_short_names_confirmation)
)
async def confirm_short_names_broadcast(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    broadcast_message = data.get("broadcast_message")

    await callback_query.answer("Рассылка началась. Это может занять некоторое время.")
    await bot.send_message(callback_query.from_user.id, "Рассылка пользователям с ФИО менее 3 слов запущена.")

    # Запускаем рассылку в отдельной задаче
    asyncio.create_task(broadcast_to_short_names_users(broadcast_message, callback_query.from_user.id))
    await state.clear()


@dp.callback_query(
    F.data == "cancel_broadcast", StateFilter(BroadcastState.waiting_for_short_names_confirmation)
)
async def cancel_short_names_broadcast(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.send_message(callback_query.from_user.id, "Рассылка пользователям с ФИО менее 3 слов отменена.")
    await state.clear()
    await callback_query.answer()
    logger.info("Рассылка пользователям с ФИО менее 3 слов отменена администратором.")


# Функция для рассылки сообщений всем пользователям
async def broadcast_to_all_users(message: types.Message):
    async with aiosqlite.connect("backend/data/db.sqlite3") as db:
        async with db.execute("SELECT telegram_id FROM users") as cursor:
            users = await cursor.fetchall()

    if not users:
        logger.info("Нет пользователей для рассылки.")
        return

    user_ids = [user[0] for user in users]
    logger.info(f"Начинаем рассылку сообщений {len(user_ids)} пользователям.")

    # Ограничиваем количество одновременных отправок
    semaphore = asyncio.Semaphore(10)  # Например, 10 одновременных отправок

    async def send_message(user_id):
        async with semaphore:
            try:
                if message.content_type == "text":
                    await bot.send_message(
                        user_id, message.text, disable_web_page_preview=True
                    )
                elif message.content_type == "photo":
                    await bot.send_photo(
                        user_id,
                        message.photo[-1].file_id,
                        caption=message.caption or "",
                    )
                elif message.content_type == "document":
                    await bot.send_document(
                        user_id, message.document.file_id, caption=message.caption or ""
                    )
                elif message.content_type == "video":
                    await bot.send_video(
                        user_id, message.video.file_id, caption=message.caption or ""
                    )
                elif message.content_type == "audio":
                    await bot.send_audio(
                        user_id, message.audio.file_id, caption=message.caption or ""
                    )
                else:
                    logger.warning(
                        f"Не поддерживаемый тип сообщения для рассылки пользователю {user_id}."
                    )
            except Exception as e:
                # Обрабатываем специфичные исключения (например, BotBlocked, ChatNotFound) при необходимости
                logger.error(
                    f"Не удалось отправить сообщение пользователю {user_id}: {e}"
                )

    # Создаем список задач для отправки сообщений
    tasks = [send_message(user_id) for user_id in user_ids]

    # Запускаем все задачи
    await asyncio.gather(*tasks)

    logger.info("Рассылка завершена.")


# Функция для удаления пользователя из базы данных
async def remove_user(user_id):
    async with aiosqlite.connect("backend/data/db.sqlite3") as db:
        await db.execute("DELETE FROM users WHERE telegram_id = ?", (user_id,))
        await db.commit()
    logger.info(f"Пользователь {user_id} удален из базы данных.")


# Функция для получения пользователей с ФИО менее 3 слов
async def get_users_with_short_names():
    async with aiosqlite.connect("backend/data/db.sqlite3") as db:
        async with db.execute("SELECT id, telegram_id, full_name FROM users") as cursor:
            users = await cursor.fetchall()

    user_ids = []
    for user in users:
        user_id = user[1]  # telegram_id
        full_name = user[2]
        # Проверяем количество слов в полном имени
        words_count = len(full_name.split())
        if words_count < 3:
            user_ids.append(user_id)
    
    return user_ids


# Функция для рассылки сообщений пользователям с коротким ФИО
async def broadcast_to_short_names_users(message: types.Message, admin_id: int):
    user_ids = await get_users_with_short_names()
    
    if not user_ids:
        logger.info("Нет пользователей с ФИО менее 3 слов для рассылки.")
        await bot.send_message(admin_id, "Нет пользователей с ФИО менее 3 слов для рассылки.")
        return

    logger.info(f"Начинаем рассылку сообщений {len(user_ids)} пользователям с ФИО менее 3 слов.")
    await bot.send_message(admin_id, f"Начата рассылка {len(user_ids)} пользователям с ФИО менее 3 слов.")

    # Ограничиваем количество одновременных отправок
    semaphore = asyncio.Semaphore(10)  # Например, 10 одновременных отправок

    async def send_message(user_id):
        async with semaphore:
            try:
                if message.content_type == "text":
                    await bot.send_message(
                        user_id, message.text, disable_web_page_preview=True
                    )
                elif message.content_type == "photo":
                    await bot.send_photo(
                        user_id,
                        message.photo[-1].file_id,
                        caption=message.caption or "",
                    )
                elif message.content_type == "document":
                    await bot.send_document(
                        user_id, message.document.file_id, caption=message.caption or ""
                    )
                elif message.content_type == "video":
                    await bot.send_video(
                        user_id, message.video.file_id, caption=message.caption or ""
                    )
                elif message.content_type == "audio":
                    await bot.send_audio(
                        user_id, message.audio.file_id, caption=message.caption or ""
                    )
                else:
                    logger.warning(
                        f"Не поддерживаемый тип сообщения для рассылки пользователю {user_id}."
                    )
            except Exception as e:
                logger.error(
                    f"Не удалось отправить сообщение пользователю {user_id}: {e}"
                )

    # Создаем список задач для отправки сообщений
    tasks = [send_message(user_id) for user_id in user_ids]

    # Запускаем все задачи
    await asyncio.gather(*tasks)

    logger.info("Рассылка пользователям с ФИО менее 3 слов завершена.")
    await bot.send_message(admin_id, "Рассылка пользователям с ФИО менее 3 слов завершена.")


async def main():
    logger.info("Запуск бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
