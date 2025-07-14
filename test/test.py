import asyncio
from app.dao.database import async_session_maker
from app.auth.dao import UsersDAO, SessionDAO
from app.auth.schemas import UserTelegramID

async def login_by_telegram_id(telegram_id: int):
    """Вход в аккаунт по Telegram ID"""
    async with async_session_maker() as session:
        users_dao = UsersDAO(session)
        session_dao = SessionDAO(session)
        
        # Ищем пользователя по Telegram ID
        user = await users_dao.find_one_or_none(
            filters=UserTelegramID(telegram_id=telegram_id)
        )
        
        if not user:
            print(f"Пользователь с Telegram ID {telegram_id} не найден")
            return None
        
        # Создаем сессию
        session_token = await session_dao.create_session(user.id)
        
        print(f"Пользователь найден: {user.full_name} (ID: {user.id})")
        print(f"Токен сессии: {session_token}")
        
        return {
            "user": user,
            "token": session_token,
            "cookies": {
                "session_token": session_token,
                "session_token_alt": session_token
            }
        }

# Использование
if __name__ == "__main__":
    # Замените на ваш Telegram ID
    result = asyncio.run(login_by_telegram_id(123456789))
    if result:
        print("\nКуки для браузера:")
        for name, value in result["cookies"].items():
            print(f"{name}={value}; path=/; max-age=604800")
