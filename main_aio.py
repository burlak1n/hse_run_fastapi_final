import asyncio

from aiogram import Bot, Dispatcher
from app.auth.router_aio import router as auth_router
from app.logger import logger

bot = Bot(token="7190707372:AAHGNCZr8dhT9kJ40rBa1wdLa1cHqANGXJA")
dp = Dispatcher()

async def main():
    dp.include_router(auth_router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
