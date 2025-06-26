from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
import logging
import json
import os
from typing import Any, Dict
from dotenv import load_dotenv

load_dotenv()
# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
USERS_DATA_FILE = "users_data.json"  # Файл для хранения данных пользователей

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Функции для работы с файлом данных
def load_users_data() -> Dict[str, Dict[str, Any]]:
    """Загружает данные пользователей из файла"""
    if os.path.exists(USERS_DATA_FILE):
        try:
            with open(USERS_DATA_FILE, 'r', encoding='utf-8') as file:
                return json.load(file)
        except json.JSONDecodeError:
            logging.error(f"Ошибка чтения файла {USERS_DATA_FILE}")
            return {}
    return {}

def save_users_data(data: Dict[str, Dict[str, Any]]) -> None:
    """Сохраняет данные пользователей в файл"""
    with open(USERS_DATA_FILE, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

# Словарь для хранения информации о пользователях
users_data = load_users_data()

# Определение состояний FSM
class RegistrationStates(StatesGroup):
    waiting_for_name = State()

# Проверка регистрации пользователя
def is_user_registered(user_id: str) -> bool:
    """Проверяет, зарегистрирован ли пользователь и заполнено ли его ФИО"""
    return (user_id in users_data and 
            users_data[user_id].get("full_name") is not None)

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    
    # Проверяем, зарегистрирован ли пользователь
    if is_user_registered(user_id):
        # Пользователь уже зарегистрирован
        full_name = users_data[user_id]["full_name"]
        await message.answer(f"Здравствуйте, {full_name}! Вы уже зарегистрированы.")
        return
    
    # Если пользователь не зарегистрирован, начинаем процесс регистрации
    users_data[user_id] = {
        "user_id": user_id,
        "username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "last_name": message.from_user.last_name,
        "is_premium": message.from_user.is_premium,
        "language_code": message.from_user.language_code,
        "full_name": None  # Будет заполнено позже
    }
    
    # Сохраняем данные в файл
    save_users_data(users_data)
    
    await state.set_state(RegistrationStates.waiting_for_name)
    await message.answer("Привет! Пока сайт HSE RUN не работает, регистрируйся здесь!\n\nНапиши ФИО полностью")

# Добавляем команду для повторной регистрации (по желанию пользователя)
@dp.message(Command("reregister"))
async def cmd_reregister(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    
    # Обновляем запись пользователя, сбрасывая ФИО
    if user_id in users_data:
        users_data[user_id]["full_name"] = None
        save_users_data(users_data)
    
    await state.set_state(RegistrationStates.waiting_for_name)
    await message.answer("Пожалуйста, введите ваше ФИО заново")

# Обработчик ввода ФИО
@dp.message(RegistrationStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    full_name = message.text
    
    # Сохраняем ФИО пользователя
    if user_id in users_data:
        users_data[user_id]["full_name"] = full_name
        # Сохраняем обновленные данные в файл
        save_users_data(users_data)
    
    # Логируем информацию о пользователе
    logging.info(f"Зарегистрирован новый пользователь: {users_data[user_id]}")
    
    # Сбрасываем состояние
    await state.clear()
    
    # Отправляем подтверждение
    await message.answer(f"Спасибо за регистрацию!")

# Запуск бота
async def main():
    logging.info("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
