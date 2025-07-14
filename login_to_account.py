import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.dao.database import async_session_maker
from app.auth.dao import UsersDAO, SessionDAO
from app.auth.schemas import UserTelegramID
from app.config import settings
from app.auth.redis_session import init_redis_session_service
from app.tasks.cleanup import broker as cleanup_broker

async def login_to_account(telegram_id: int = None, username: str = None, full_name: str = None):
    """
    Универсальная функция для входа в аккаунт
    
    Args:
        telegram_id: Telegram ID пользователя
        username: Telegram username (без @)
        full_name: ФИО пользователя
    """
    if not any([telegram_id, username, full_name]):
        print("Необходимо указать хотя бы один параметр: telegram_id, username или full_name")
        return None
    
        # Инициализируем Redis если он включен
    if settings.USE_REDIS:
        print("🔧 Инициализация Redis...")
        try:
            await cleanup_broker.start()
            await init_redis_session_service(cleanup_broker)
            print("✅ Redis успешно инициализирован")
        except Exception as e:
            print(f"❌ Ошибка инициализации Redis: {e}")
            print("🔄 Переключаемся на базу данных...")
            settings.USE_REDIS = False
    else:
        print("🔧 Redis отключен, используем базу данных")
    
    try:
        async with async_session_maker() as session:
            users_dao = UsersDAO(session)
            session_dao = SessionDAO(session)
            
            user = None
            
            # Поиск по Telegram ID (приоритетный)
            if telegram_id:
                user = await users_dao.find_one_or_none(
                    filters=UserTelegramID(telegram_id=telegram_id)
                )
                if user:
                    print(f"Пользователь найден по Telegram ID: {telegram_id}")
            
            # Поиск по username
            elif username:
                user = await users_dao.find_one_or_none(
                    filters={"telegram_username": username}
                )
                if user:
                    print(f"Пользователь найден по username: @{username}")
            
            # Поиск по ФИО
            elif full_name:
                user = await users_dao.find_one_or_none(
                    filters={"full_name": full_name}
                )
                if user:
                    print(f"Пользователь найден по ФИО: {full_name}")
            
            if not user:
                print("Пользователь не найден")
                return None
            
            # Создаем сессию
            session_token = await session_dao.create_session(user.id)
            
            print(f"\n✅ Успешный вход!")
            print(f"👤 Пользователь: {user.full_name}")
            print(f"🆔 ID в БД: {user.id}")
            print(f"📱 Telegram ID: {user.telegram_id}")
            print(f"👤 Username: @{user.telegram_username}")
            print(f"🎭 Роль: {user.role.name if user.role else 'Не установлена'}")
            print(f"🔑 Токен сессии: {session_token}")
            
            # Формируем куки для браузера
            cookies = {
                "session_token": session_token,
                "session_token_alt": session_token
            }
            
            print(f"\n🍪 Куки для установки в браузере:")
            for name, value in cookies.items():
                print(f"{name}={value}; path=/; max-age=604800")
            
            print(f"\n📋 Готовые команды для копирования:")
            print(f"\n🔧 JavaScript для браузера (F12 → Console):")
            print(f'document.cookie = "session_token={session_token}; path=/; max-age=604800";')
            print(f'document.cookie = "session_token_alt={session_token}; path=/; max-age=604800";')
            print(f'location.reload();')
            
            print(f"\n📡 Команды curl:")
            print(f'# Проверка профиля')
            print(f'curl -X GET "http://localhost:8000/api/auth/me" -H "Cookie: session_token={session_token}"')
            print(f'# Полный профиль с командами')
            print(f'curl -X GET "http://localhost:8000/api/auth/profile" -H "Cookie: session_token={session_token}"')
            print(f'# Список команд')
            print(f'curl -X GET "http://localhost:8000/api/auth/commands" -H "Cookie: session_token={session_token}"')
            
            print(f"\n🌐 Или просто откройте в браузере:")
            print(f'http://localhost:8000')
            print(f'И вставьте в консоль (F12 → Console):')
            print(f'document.cookie = "session_token={session_token}; path=/; max-age=604800"; document.cookie = "session_token_alt={session_token}; path=/; max-age=604800"; location.reload();')
            
            return {
                "user": user,
                "token": session_token,
                "cookies": cookies
            }
    finally:
        # Останавливаем Redis broker если он был запущен
        if settings.USE_REDIS:
            try:
                await cleanup_broker.stop()
                print("🔧 Redis broker остановлен")
            except Exception as e:
                print(f"⚠️ Ошибка при остановке Redis broker: {e}")

def main():
    """Основная функция для запуска из командной строки"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Вход в аккаунт HSE RUN")
    parser.add_argument("--telegram-id", type=int, help="Telegram ID пользователя")
    parser.add_argument("--username", type=str, help="Telegram username (без @)")
    parser.add_argument("--full-name", type=str, help="ФИО пользователя")
    
    args = parser.parse_args()
    
    if not any([args.telegram_id, args.username, args.full_name]):
        print("Необходимо указать хотя бы один параметр:")
        print("  --telegram-id 123456789")
        print("  --username username")
        print("  --full-name 'Иван Иванов'")
        return
    
    result = asyncio.run(login_to_account(
        telegram_id=args.telegram_id,
        username=args.username,
        full_name=args.full_name
    ))

if __name__ == "__main__":
    main() 