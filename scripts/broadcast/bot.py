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
    waiting_for_captains_message = State()
    waiting_for_captains_confirmation = State()
    waiting_for_friends_message = State()  # New state for friends broadcast message
    waiting_for_friends_confirmation = State() # New state for friends broadcast confirmation


class ListUsersState(StatesGroup):
    browsing = State()
    browsing_captains = State()
    browsing_friends = State() # New state for browsing friends


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


@dp.message(Command("broadcast_captains"))
async def cmd_broadcast_captains(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS_ID:
        await message.reply("У вас нет прав использовать эту команду.")
        logger.warning(
            f"Пользователь {message.from_user.id} попытался использовать /broadcast_captains без прав."
        )
        return
    await message.reply("Пожалуйста, отправьте сообщение для рассылки капитанам команд.")
    await state.set_state(BroadcastState.waiting_for_captains_message)


@dp.message(Command("broadcast_friends"))
async def cmd_broadcast_friends(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS_ID:
        await message.reply("У вас нет прав использовать эту команду.")
        logger.warning(
            f"Пользователь {message.from_user.id} попытался использовать /broadcast_friends без прав."
        )
        return
    await message.reply("Пожалуйста, отправьте сообщение для рассылки пользователям, ищущим команду.")
    await state.set_state(BroadcastState.waiting_for_friends_message)


@dp.message(StateFilter(BroadcastState.waiting_for_message))
async def broadcast_message_handler(message: types.Message, state: FSMContext):
    await state.update_data(broadcast_message=message)

    # Получаем количество пользователей для рассылки
    users = await get_users_for_broadcast()
    total_users = len(users)

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

    # Сообщение с количеством получателей
    confirmation_text = f"Сообщение будет отправлено {total_users} пользователям.\n\n"
    
    if message.content_type == "text":
        await message.answer(
            confirmation_text + "Вы хотите отправить следующее текстовое сообщение всем пользователям:",
            reply_markup=keyboard,
        )
        await message.answer(message.text, disable_web_page_preview=True)
    elif message.content_type in ["photo", "document", "video", "audio"]:
        await message.answer(
            confirmation_text + f"Вы хотите отправить следующее {message.content_type} сообщение всем пользователям:",
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
    asyncio.create_task(broadcast_to_all_users(broadcast_message, callback_query.from_user.id))
    await state.clear()


@dp.callback_query(
    F.data == "cancel_broadcast", 
    StateFilter(BroadcastState.waiting_for_confirmation, 
                BroadcastState.waiting_for_short_names_confirmation, 
                BroadcastState.waiting_for_captains_confirmation,
                BroadcastState.waiting_for_friends_confirmation)
)
async def cancel_broadcast(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data() # Get state to determine which broadcast was cancelled
    current_state = await state.get_state()
    
    cancel_message = "Рассылка отменена."
    if current_state == BroadcastState.waiting_for_short_names_confirmation:
        cancel_message = "Рассылка пользователям с ФИО менее 3 слов отменена."
    elif current_state == BroadcastState.waiting_for_captains_confirmation:
        cancel_message = "Рассылка капитанам отменена."
    elif current_state == BroadcastState.waiting_for_friends_confirmation:
        cancel_message = "Рассылка пользователям, ищущим команду, отменена."
        
    await bot.send_message(callback_query.from_user.id, cancel_message)
    await state.clear()
    await callback_query.answer()
    logger.info(f"Рассылка ({current_state}) отменена администратором.")


@dp.message(StateFilter(BroadcastState.waiting_for_short_names_message))
async def short_names_message_handler(message: types.Message, state: FSMContext):
    await state.update_data(broadcast_message=message)

    # Получаем количество пользователей для рассылки с коротким ФИО
    users = await get_users_for_broadcast(filter_short_names=True)
    total_users = len(users)

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

    # Сообщение с количеством получателей
    confirmation_text = f"Сообщение будет отправлено {total_users} пользователям с ФИО менее 3 слов.\n\n"

    if message.content_type == "text":
        await message.answer(
            confirmation_text + "Вы хотите отправить следующее текстовое сообщение пользователям с ФИО менее 3 слов:",
            reply_markup=keyboard,
        )
        await message.answer(message.text, disable_web_page_preview=True)
    elif message.content_type in ["photo", "document", "video", "audio"]:
        await message.answer(
            confirmation_text + f"Вы хотите отправить следующее {message.content_type} сообщение пользователям с ФИО менее 3 слов:",
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


@dp.message(StateFilter(BroadcastState.waiting_for_captains_message))
async def captains_message_handler(message: types.Message, state: FSMContext):
    await state.update_data(broadcast_message=message)

    # Получаем количество капитанов для рассылки
    captains = await get_captains_for_broadcast()
    total_captains = len(captains)

    if total_captains == 0:
        await message.answer("В базе данных нет капитанов для рассылки.")
        await state.clear()
        return

    # Создаем инлайн-клавиатуру с кнопками подтверждения
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить", callback_data="confirm_captains_broadcast"
                ),
                InlineKeyboardButton(text="Отменить", callback_data="cancel_broadcast"), # Can reuse cancel
            ]
        ]
    )

    # Сообщение с количеством получателей
    confirmation_text = f"Сообщение будет отправлено {total_captains} капитанам."

    if message.content_type == "text":
        await message.answer(
            confirmation_text + "Вы хотите отправить следующее текстовое сообщение капитанам:",
            reply_markup=keyboard,
        )
        await message.answer(message.text, disable_web_page_preview=True)
    elif message.content_type in ["photo", "document", "video", "audio"]:
        await message.answer(
            confirmation_text + f"Вы хотите отправить следующее {message.content_type} сообщение капитанам:",
            reply_markup=keyboard,
        )
        # Отправка предпросмотра медиа
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

    await state.set_state(BroadcastState.waiting_for_captains_confirmation)


@dp.message(StateFilter(BroadcastState.waiting_for_friends_message))
async def friends_message_handler(message: types.Message, state: FSMContext):
    await state.update_data(broadcast_message=message)

    # Получаем количество пользователей, ищущих команду
    friends = await get_friends_for_broadcast()
    total_friends = len(friends)

    if total_friends == 0:
        await message.answer("В базе данных нет пользователей, ищущих команду.")
        await state.clear()
        return

    # Создаем инлайн-клавиатуру с кнопками подтверждения
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить", callback_data="confirm_friends_broadcast"
                ),
                InlineKeyboardButton(text="Отменить", callback_data="cancel_broadcast"),
            ]
        ]
    )

    # Сообщение с количеством получателей
    confirmation_text = f"Сообщение будет отправлено {total_friends} пользователям, ищущим команду."

    if message.content_type == "text":
        await message.answer(
            confirmation_text + "\n\nВы хотите отправить следующее текстовое сообщение:",
            reply_markup=keyboard,
        )
        await message.answer(message.text, disable_web_page_preview=True)
    elif message.content_type in ["photo", "document", "video", "audio"]:
        await message.answer(
            confirmation_text + f"\n\nВы хотите отправить следующее {message.content_type} сообщение:",
            reply_markup=keyboard,
        )
        # Отправка предпросмотра медиа
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

    await state.set_state(BroadcastState.waiting_for_friends_confirmation)


# Общая функция для получения списка пользователей для рассылки
async def get_users_for_broadcast(filter_short_names=False):
    """
    Получает список пользователей для рассылки.
    
    Args:
        filter_short_names (bool): Если True, возвращает только пользователей с ФИО менее 3 слов
        
    Returns:
        list: Список кортежей (telegram_id, full_name)
    """
    db_path = "/projects/hse_run_full/backend/data/db.sqlite3"  # Use absolute path
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT telegram_id, full_name FROM users") as cursor:
            users = await cursor.fetchall()
    
    if filter_short_names:
        # Фильтрация пользователей с ФИО менее 3 слов
        return [(user_id, full_name) for user_id, full_name in users if len(full_name.split()) < 3]
    
    return users


# Функция для получения списка капитанов для рассылки
async def get_captains_for_broadcast():
    """
    Получает список пользователей, являющихся капитанами.
    
    Returns:
        list: Список кортежей (telegram_id, full_name)
    """
    db_path = "/projects/hse_run_full/backend/data/db.sqlite3"
    async with aiosqlite.connect(db_path) as db:
        # Запрос для получения telegram_id и full_name пользователей, которые являются капитанами
        # Присоединяем users к commandsuser по user_id
        # Присоединяем commandsuser к roleusercommands по role_id
        # Фильтруем по имени роли 'captain'
        query = """
            SELECT DISTINCT u.telegram_id, u.full_name
            FROM users u
            JOIN commandsusers cu ON u.id = cu.user_id
            JOIN roleusercommands ruc ON cu.role_id = ruc.id
            WHERE ruc.name = 'captain'
        """
        async with db.execute(query) as cursor:
            captains = await cursor.fetchall()
            
    if not captains:
        logger.info("Капитаны не найдены в базе данных.")
    else:
        logger.info(f"Найдено {len(captains)} капитанов.")
        
    return captains


# Функция для получения списка пользователей, ищущих команду
async def get_friends_for_broadcast():
    """
    Получает список пользователей с is_looking_for_friends = 1.
    
    Returns:
        list: Список кортежей (telegram_id, full_name)
    """
    db_path = "/projects/hse_run_full/backend/data/db.sqlite3"
    async with aiosqlite.connect(db_path) as db:
        # Выбираем пользователей, у которых is_looking_for_friends = 1
        query = "SELECT telegram_id, full_name FROM users WHERE is_looking_for_friends = 1"
        async with db.execute(query) as cursor:
            friends = await cursor.fetchall()
            
    if not friends:
        logger.info("Пользователи, ищущие команду, не найдены.")
    else:
        logger.info(f"Найдено {len(friends)} пользователей, ищущих команду.")
        
    return friends


# Функция для рассылки сообщений всем пользователям
async def broadcast_to_all_users(message: types.Message, admin_id=None):
    users = await get_users_for_broadcast()

    if not users:
        logger.info("Нет пользователей для рассылки.")
        if admin_id:
            await bot.send_message(admin_id, "Нет пользователей для рассылки.")
        return

    user_ids = [user[0] for user in users]
    total_users = len(user_ids)
    failed_users = []
    
    logger.info(f"Начинаем рассылку сообщений {total_users} пользователям.")
    print(f"Начинаем рассылку сообщений {total_users} пользователям.")
    
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
                    failed_users.append((user_id, "Неподдерживаемый тип сообщения"))
            except Exception as e:
                error_msg = f"Не удалось отправить сообщение пользователю {user_id}: {e}"
                logger.error(error_msg)
                print(error_msg)
                failed_users.append((user_id, str(e)))

    # Создаем список задач для отправки сообщений
    tasks = [send_message(user_id) for user_id in user_ids]

    # Запускаем все задачи
    await asyncio.gather(*tasks)

    # Выводим итоговую статистику
    success_count = total_users - len(failed_users)
    completion_msg = f"Рассылка завершена. Успешно: {success_count}/{total_users}."
    logger.info(completion_msg)
    print(completion_msg)
    
    # Отправляем отчет администратору
    if admin_id:
        await bot.send_message(admin_id, completion_msg)
        
        # Отправляем список пользователей, которым не удалось отправить сообщение
        if failed_users:
            failed_msg = "Список пользователей, которым НЕ было отправлено сообщение:\n\n"
            for i, (user_id, reason) in enumerate(failed_users[:20], 1):
                failed_msg += f"{i}. ID: {user_id}, причина: {reason}\n"
                
            if len(failed_users) > 20:
                failed_msg += f"\n... и еще {len(failed_users) - 20} пользователей"
                
            await bot.send_message(admin_id, failed_msg)
    
    # Выводим информацию о не отправленных сообщениях в терминал
    if failed_users:
        print("\nСписок пользователей, которым НЕ было отправлено сообщение:")
        for user_id, reason in failed_users:
            print(f"ID: {user_id}, причина: {reason}")


# Функция для удаления пользователя из базы данных
async def remove_user(user_id):
    db_path = "/projects/hse_run_full/backend/data/db.sqlite3"  # Use absolute path
    async with aiosqlite.connect(db_path) as db:
        await db.execute("DELETE FROM users WHERE telegram_id = ?", (user_id,))
        await db.commit()
    logger.info(f"Пользователь {user_id} удален из базы данных.")


# Функция для получения пользователей с ФИО менее 3 слов
async def get_users_with_short_names():
    return await get_users_for_broadcast(filter_short_names=True)


# Функция для рассылки сообщений пользователям с коротким ФИО
async def broadcast_to_short_names_users(message: types.Message, admin_id: int):
    users = await get_users_for_broadcast(filter_short_names=True)
    
    if not users:
        logger.info("Нет пользователей с ФИО менее 3 слов для рассылки.")
        await bot.send_message(admin_id, "Нет пользователей с ФИО менее 3 слов для рассылки.")
        return

    user_ids = [user[0] for user in users]
    total_users = len(user_ids)
    failed_users = []
    
    logger.info(f"Начинаем рассылку сообщений {total_users} пользователям с ФИО менее 3 слов.")
    await bot.send_message(admin_id, f"Начата рассылка {total_users} пользователям с ФИО менее 3 слов.")
    print(f"Начинаем рассылку сообщений {total_users} пользователям с ФИО менее 3 слов.")

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
                    failed_users.append((user_id, "Неподдерживаемый тип сообщения"))
            except Exception as e:
                error_msg = f"Не удалось отправить сообщение пользователю {user_id}: {e}"
                logger.error(error_msg)
                print(error_msg)
                failed_users.append((user_id, str(e)))

    # Создаем список задач для отправки сообщений
    tasks = [send_message(user_id) for user_id in user_ids]

    # Запускаем все задачи
    await asyncio.gather(*tasks)

    # Выводим итоговую статистику
    success_count = total_users - len(failed_users)
    completion_msg = f"Рассылка пользователям с ФИО менее 3 слов завершена. Успешно: {success_count}/{total_users}."
    logger.info(completion_msg)
    await bot.send_message(admin_id, completion_msg)
    print(completion_msg)
    
    # Выводим информацию о не отправленных сообщениях
    if failed_users:
        print("\nСписок пользователей с ФИО менее 3 слов, которым НЕ было отправлено сообщение:")
        for user_id, reason in failed_users:
            print(f"ID: {user_id}, причина: {reason}")


@dp.message(Command("list_broadcast_users"))
async def cmd_list_users(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS_ID:
        await message.reply("У вас нет прав использовать эту команду.")
        logger.warning(
            f"Пользователь {message.from_user.id} попытался использовать /list_broadcast_users без прав."
        )
        return

    # Используем общую функцию для получения пользователей
    users = await get_users_for_broadcast()

    if not users:
        await message.reply("В базе данных нет пользователей для рассылки.")
        return

    # Подготовка данных по 10 пользователей на страницу
    users_per_page = 10
    total_users = len(users)
    total_pages = (total_users + users_per_page - 1) // users_per_page

    # Сохраняем данные в состоянии
    await state.update_data(users=users, page=0, users_per_page=users_per_page, total_pages=total_pages)
    
    # Показываем первую страницу
    await show_users_page(message, state)
    await state.set_state(ListUsersState.browsing)


@dp.message(Command("list_captains"))
async def cmd_list_captains(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS_ID:
        await message.reply("У вас нет прав использовать эту команду.")
        logger.warning(
            f"Пользователь {message.from_user.id} попытался использовать /list_captains без прав."
        )
        return

    # Получаем список капитанов
    captains = await get_captains_for_broadcast()

    if not captains:
        await message.reply("В базе данных нет капитанов.")
        return

    # Подготовка данных для пагинации
    captains_per_page = 10
    total_captains = len(captains)
    total_pages = (total_captains + captains_per_page - 1) // captains_per_page

    # Сохраняем данные в состоянии
    await state.update_data(captains=captains, page=0, captains_per_page=captains_per_page, total_pages=total_pages)
    
    # Показываем первую страницу
    await show_captains_page(message, state)
    await state.set_state(ListUsersState.browsing_captains) # Используем новое состояние


@dp.message(Command("list_friends"))
async def cmd_list_friends(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMINS_ID:
        await message.reply("У вас нет прав использовать эту команду.")
        logger.warning(
            f"Пользователь {message.from_user.id} попытался использовать /list_friends без прав."
        )
        return

    # Получаем список пользователей, ищущих команду
    friends = await get_friends_for_broadcast()

    if not friends:
        await message.reply("В базе данных нет пользователей, ищущих команду.")
        return

    # Подготовка данных для пагинации
    friends_per_page = 10
    total_friends = len(friends)
    total_pages = (total_friends + friends_per_page - 1) // friends_per_page

    # Сохраняем данные в состоянии
    await state.update_data(friends=friends, page=0, friends_per_page=friends_per_page, total_pages=total_pages)
    
    # Показываем первую страницу
    await show_friends_page(message, state)
    await state.set_state(ListUsersState.browsing_friends) # Используем новое состояние


async def show_users_page(message: types.Message, state: FSMContext, callback_query: types.CallbackQuery = None):
    data = await state.get_data()
    users = data["users"]
    page = data["page"]
    users_per_page = data["users_per_page"]
    total_pages = data["total_pages"]
    
    # Вычисляем индексы пользователей для текущей страницы
    start_idx = page * users_per_page
    end_idx = min((page + 1) * users_per_page, len(users))
    
    # Формируем сообщение со списком пользователей
    user_list = []
    for i, (user_id, full_name) in enumerate(users[start_idx:end_idx], start=start_idx + 1):
        user_list.append(f"{i}. {full_name} (ID: {user_id})")
    
    users_text = "\n".join(user_list)
    
    # Создаем клавиатуру для навигации
    keyboard = []
    
    # Добавляем навигационные кнопки
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data="prev_page"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data="next_page"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Добавляем кнопку для просмотра пользователей с коротким ФИО
    keyboard.append([InlineKeyboardButton(text="Пользователи с ФИО < 3 слов", callback_data="show_short_names")])
    
    # Добавляем кнопку закрытия
    keyboard.append([InlineKeyboardButton(text="Закрыть", callback_data="close_list")])
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    # Отправляем или редактируем сообщение
    text = f"Пользователи для рассылки (всего: {len(users)}):\n\n{users_text}\n\nСтраница {page + 1} из {total_pages}"
    
    try:
        if hasattr(message, "message_id"):
            # Check if message content needs updating
            if message.text == text and message.reply_markup == reply_markup:
                # If the callback query is available, answer it
                if callback_query:
                    await callback_query.answer() 
                return
            # Это колбэк-запрос, редактируем сообщение
            await bot.edit_message_text(text, chat_id=message.chat.id, message_id=message.message_id, reply_markup=reply_markup)
        else:
            # Это новое сообщение
            await message.answer(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка при отправке/редактировании сообщения: {e}")
        # Если не удалось отредактировать сообщение, отправляем новое
        if hasattr(message, "chat"):
            await bot.send_message(message.chat.id, text, reply_markup=reply_markup)


@dp.callback_query(F.data == "prev_page", StateFilter(ListUsersState.browsing))
async def prev_page(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = data["page"]
    
    if page > 0:
        await state.update_data(page=page - 1)
        await show_users_page(callback_query.message, state, callback_query)
    else:
        await callback_query.answer() # Answer if no change


@dp.callback_query(F.data == "next_page", StateFilter(ListUsersState.browsing))
async def next_page(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = data["page"]
    total_pages = data["total_pages"]
    
    if page < total_pages - 1:
        await state.update_data(page=page + 1)
        await show_users_page(callback_query.message, state, callback_query)
    else:
        await callback_query.answer() # Answer if no change


@dp.callback_query(F.data == "show_short_names", StateFilter(ListUsersState.browsing))
async def show_short_names(callback_query: types.CallbackQuery, state: FSMContext):
    # Используем общую функцию для получения пользователей с коротким ФИО
    short_name_users = await get_users_for_broadcast(filter_short_names=True)
    
    if not short_name_users:
        await callback_query.answer("Нет пользователей с ФИО менее 3 слов")
        return
    
    # Обновляем данные состояния
    data = await state.get_data()
    current_users = data.get('users')
    current_view_mode = data.get('view_mode')

    # Проверяем, не показываем ли мы уже этот список
    if current_view_mode == "short_names" and current_users == short_name_users:
        await callback_query.answer("Уже показаны пользователи с ФИО < 3 слов")
        return
        
    await state.update_data(
        users=short_name_users, 
        page=0, 
        users_per_page=10, 
        total_pages=(len(short_name_users) + 9) // 10,
        view_mode="short_names" # Keep track of view mode
    )
    
    await show_users_page(callback_query.message, state, callback_query)
    await callback_query.answer("Показаны пользователи с ФИО менее 3 слов")


@dp.callback_query(F.data == "close_list", StateFilter(ListUsersState.browsing))
async def close_list(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id)
    await state.clear()
    await callback_query.answer()


@dp.callback_query(
    F.data == "confirm_captains_broadcast", 
    StateFilter(BroadcastState.waiting_for_captains_confirmation)
)
async def confirm_captains_broadcast(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    broadcast_message = data.get("broadcast_message")

    await callback_query.answer("Рассылка капитанам началась. Это может занять некоторое время.")
    await bot.send_message(callback_query.from_user.id, "Рассылка капитанам запущена.")

    # Запускаем рассылку в отдельной задаче
    asyncio.create_task(broadcast_to_captains(broadcast_message, callback_query.from_user.id))
    await state.clear()


# Функция для рассылки сообщений капитанам
async def broadcast_to_captains(message: types.Message, admin_id: int):
    captains = await get_captains_for_broadcast()
    
    if not captains:
        logger.info("Нет капитанов для рассылки.")
        await bot.send_message(admin_id, "Нет капитанов для рассылки.")
        return

    captain_ids = [captain[0] for captain in captains]
    total_captains = len(captain_ids)
    failed_captains = []
    
    logger.info(f"Начинаем рассылку сообщений {total_captains} капитанам.")
    await bot.send_message(admin_id, f"Начата рассылка {total_captains} капитанам.")
    print(f"Начинаем рассылку сообщений {total_captains} капитанам.")

    semaphore = asyncio.Semaphore(10) # Ограничение одновременных отправок

    async def send_message_to_captain(user_id):
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
                        f"Не поддерживаемый тип сообщения для рассылки капитану {user_id}."
                    )
                    failed_captains.append((user_id, "Неподдерживаемый тип сообщения"))
            except Exception as e:
                error_msg = f"Не удалось отправить сообщение капитану {user_id}: {e}"
                logger.error(error_msg)
                print(error_msg)
                failed_captains.append((user_id, str(e)))

    tasks = [send_message_to_captain(user_id) for user_id in captain_ids]
    await asyncio.gather(*tasks)

    success_count = total_captains - len(failed_captains)
    completion_msg = f"Рассылка капитанам завершена. Успешно: {success_count}/{total_captains}."
    logger.info(completion_msg)
    await bot.send_message(admin_id, completion_msg)
    print(completion_msg)
    
    if failed_captains:
        failed_msg = "Список капитанов, которым НЕ было отправлено сообщение:"
        for i, (user_id, reason) in enumerate(failed_captains[:20], 1):
            failed_msg += f"{i}. ID: {user_id}, причина: {reason}"
            
        if len(failed_captains) > 20:
            failed_msg += f"\n... и еще {len(failed_captains) - 20} капитанов"
            
        await bot.send_message(admin_id, failed_msg)
        print("Список капитанов, которым НЕ было отправлено сообщение:")
        for user_id, reason in failed_captains:
            print(f"ID: {user_id}, причина: {reason}")


async def show_captains_page(message: types.Message, state: FSMContext, callback_query: types.CallbackQuery = None):
    data = await state.get_data()
    captains = data["captains"]
    page = data["page"]
    captains_per_page = data["captains_per_page"]
    total_pages = data["total_pages"]
    
    start_idx = page * captains_per_page
    end_idx = min((page + 1) * captains_per_page, len(captains))
    
    captain_list = []
    for i, (captain_id, full_name) in enumerate(captains[start_idx:end_idx], start=start_idx + 1):
        captain_list.append(f"{i}. {full_name} (ID: {captain_id})")
    
    captains_text = "\n".join(captain_list)
    
    keyboard = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data="prev_captain_page"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data="next_captain_page"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
        
    keyboard.append([InlineKeyboardButton(text="Закрыть", callback_data="close_captain_list")])
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    text = f"Капитаны команд (всего: {len(captains)}):\n\n{captains_text}\n\nСтраница {page + 1} из {total_pages}"
    
    try:
        if hasattr(message, "message_id"):
            # Check if message content needs updating
            if message.text == text and message.reply_markup == reply_markup:
                # If the callback query is available, answer it
                if callback_query:
                    await callback_query.answer() 
                return
            # Это колбэк-запрос, редактируем сообщение
            await bot.edit_message_text(text, chat_id=message.chat.id, message_id=message.message_id, reply_markup=reply_markup)
        else:
            # Это новое сообщение
            await message.answer(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка при отправке/редактировании списка капитанов: {e}")
        if hasattr(message, "chat"):
             await bot.send_message(message.chat.id, text, reply_markup=reply_markup)


@dp.callback_query(F.data == "prev_captain_page", StateFilter(ListUsersState.browsing_captains))
async def prev_captain_page(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = data["page"]
    
    if page > 0:
        await state.update_data(page=page - 1)
        await show_captains_page(callback_query.message, state, callback_query)
    else:
        await callback_query.answer() # Answer if no change


@dp.callback_query(F.data == "next_captain_page", StateFilter(ListUsersState.browsing_captains))
async def next_captain_page(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = data["page"]
    total_pages = data["total_pages"]
    
    if page < total_pages - 1:
        await state.update_data(page=page + 1)
        await show_captains_page(callback_query.message, state, callback_query)
    else:
        await callback_query.answer() # Answer if no change


@dp.callback_query(F.data == "close_captain_list", StateFilter(ListUsersState.browsing_captains))
async def close_captain_list(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id)
    await state.clear()
    await callback_query.answer()


@dp.callback_query(
    F.data == "confirm_friends_broadcast",
    StateFilter(BroadcastState.waiting_for_friends_confirmation)
)
async def confirm_friends_broadcast(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    broadcast_message = data.get("broadcast_message")

    await callback_query.answer("Рассылка ищущим команду началась. Это может занять некоторое время.")
    await bot.send_message(callback_query.from_user.id, "Рассылка пользователям, ищущим команду, запущена.")

    # Запускаем рассылку в отдельной задаче
    asyncio.create_task(broadcast_to_friends(broadcast_message, callback_query.from_user.id))
    await state.clear()


# Функция для рассылки сообщений пользователям, ищущим команду
async def broadcast_to_friends(message: types.Message, admin_id: int):
    friends = await get_friends_for_broadcast()
    
    if not friends:
        logger.info("Нет пользователей, ищущих команду, для рассылки.")
        await bot.send_message(admin_id, "Нет пользователей, ищущих команду, для рассылки.")
        return

    friend_ids = [friend[0] for friend in friends]
    total_friends = len(friend_ids)
    failed_friends = []
    
    logger.info(f"Начинаем рассылку сообщений {total_friends} пользователям, ищущим команду.")
    await bot.send_message(admin_id, f"Начата рассылка {total_friends} пользователям, ищущим команду.")
    print(f"Начинаем рассылку сообщений {total_friends} пользователям, ищущим команду.")

    semaphore = asyncio.Semaphore(10)

    async def send_message_to_friend(user_id):
        async with semaphore:
            try:
                # Копирование логики отправки из broadcast_to_all_users
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
                        f"Не поддерживаемый тип сообщения для рассылки пользователю {user_id} (ищет команду)."
                    )
                    failed_friends.append((user_id, "Неподдерживаемый тип сообщения"))
            except Exception as e:
                error_msg = f"Не удалось отправить сообщение пользователю {user_id} (ищет команду): {e}"
                logger.error(error_msg)
                print(error_msg)
                failed_friends.append((user_id, str(e)))

    tasks = [send_message_to_friend(user_id) for user_id in friend_ids]
    await asyncio.gather(*tasks)

    success_count = total_friends - len(failed_friends)
    completion_msg = f"Рассылка пользователям, ищущим команду, завершена. Успешно: {success_count}/{total_friends}."
    logger.info(completion_msg)
    await bot.send_message(admin_id, completion_msg)
    print(completion_msg)
    
    if failed_friends:
        failed_msg = "Список пользователей (ищут команду), которым НЕ было отправлено сообщение:"
        for i, (user_id, reason) in enumerate(failed_friends[:20], 1):
            failed_msg += f"\n{i}. ID: {user_id}, причина: {reason}"
            
        if len(failed_friends) > 20:
            failed_msg += f"\n... и еще {len(failed_friends) - 20} пользователей"
            
        await bot.send_message(admin_id, failed_msg)
        print("\nСписок пользователей (ищут команду), которым НЕ было отправлено сообщение:")
        for user_id, reason in failed_friends:
            print(f"ID: {user_id}, причина: {reason}")


async def show_friends_page(message: types.Message, state: FSMContext, callback_query: types.CallbackQuery = None):
    data = await state.get_data()
    friends = data["friends"]
    page = data["page"]
    friends_per_page = data["friends_per_page"]
    total_pages = data["total_pages"]
    
    start_idx = page * friends_per_page
    end_idx = min((page + 1) * friends_per_page, len(friends))
    
    friend_list = []
    for i, (friend_id, full_name) in enumerate(friends[start_idx:end_idx], start=start_idx + 1):
        friend_list.append(f"{i}. {full_name} (ID: {friend_id})")
    
    friends_text = "\n".join(friend_list)
    
    keyboard = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data="prev_friend_page"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data="next_friend_page"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
        
    keyboard.append([InlineKeyboardButton(text="Закрыть", callback_data="close_friend_list")])
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    text = f"Пользователи, ищущие команду (всего: {len(friends)}):\n\n{friends_text}\n\nСтраница {page + 1} из {total_pages}"
    
    try:
        if hasattr(message, "message_id"):
            if message.text == text and message.reply_markup == reply_markup:
                if callback_query:
                    await callback_query.answer()
                return
            await bot.edit_message_text(text, chat_id=message.chat.id, message_id=message.message_id, reply_markup=reply_markup)
        else:
            await message.answer(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка при отправке/редактировании списка ищущих команду: {e}")
        if hasattr(message, "chat"):
             await bot.send_message(message.chat.id, text, reply_markup=reply_markup)


@dp.callback_query(F.data == "prev_friend_page", StateFilter(ListUsersState.browsing_friends))
async def prev_friend_page(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = data["page"]
    
    if page > 0:
        await state.update_data(page=page - 1)
        await show_friends_page(callback_query.message, state, callback_query)
    else:
        await callback_query.answer()


@dp.callback_query(F.data == "next_friend_page", StateFilter(ListUsersState.browsing_friends))
async def next_friend_page(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = data["page"]
    total_pages = data["total_pages"]
    
    if page < total_pages - 1:
        await state.update_data(page=page + 1)
        await show_friends_page(callback_query.message, state, callback_query)
    else:
        await callback_query.answer()


@dp.callback_query(F.data == "close_friend_list", StateFilter(ListUsersState.browsing_friends))
async def close_friend_list(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.delete_message(callback_query.message.chat.id, callback_query.message.message_id)
    await state.clear()
    await callback_query.answer()


async def main():
    logger.info("Запуск бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
