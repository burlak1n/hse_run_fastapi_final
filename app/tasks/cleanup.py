import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select  # Импортируем delete и select
from datetime import datetime, timezone
# Удаляем импорт SessionLocal и Session из orm
from app.dao.database import async_session_maker  # Импортируем async_session_maker
from app.auth.models import Session as SessionModel # Переименовываем импорт модели Session
from loguru import logger # Добавляем логгер
from faststream import FastStream, Context
from faststream.redis import RedisBroker
from faststream import Depends
from app.config import settings # Import settings

# Initialize Redis broker using settings
# TODO: Move broker URL to configuration - DONE
broker = RedisBroker(settings.REDIS_URL)
# Remove the FastStream app instance as schedule should be on the broker
# stream_app = FastStream(broker)

# Dependency function to provide AsyncSession
async def get_session():
    async with async_session_maker() as session:
        yield session

# @broker.schedule(cron="0 * * * *") # Revert to using schedule from the broker instance
# async def cleanup_expired_sessions(session: AsyncSession = Depends(get_session)):
#     """Асинхронное удаление истёкших сессий из базы данных (запускается FastStream)."""
#     logger.info("Запуск задачи очистки истекших сессий через FastStream...")
#     try:
#         now = datetime.now(timezone.utc)
#         stmt = delete(SessionModel).where(SessionModel.expires_at < now)
#         result = await session.execute(stmt)
#         await session.commit()
#         logger.info(f"Удалено {result.rowcount} истекших сессий.")
#     except Exception as e:
#         await session.rollback() # Rollback is handled by Depends context manager if exception propagates
#         logger.error(f"Ошибка при очистке истекших сессий: {e}")
#         # Re-raise exception for FastStream to handle/log if needed
#         raise
#     finally:
#         # Session closing is handled by Depends context manager
#         logger.info("Задача очистки истекших сессий завершена.")

# Пример запуска задачи (если она запускается отдельно)
# async def main():
#     await cleanup_expired_sessions()

# if __name__ == "__main__":
#     asyncio.run(main())
