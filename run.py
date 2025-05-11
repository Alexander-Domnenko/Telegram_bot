import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import TOKEN
from app.user.handlers import router as user_router
from app.admin.handlers import router as admin_router
from app.middlewares import DbSessionMiddleware
from app.database.models import AsyncSessionLocal

bot = Bot(token=TOKEN)
dp = Dispatcher()

async def main():
    try:
        dp.include_router(admin_router)
        dp.include_router(user_router)
        dp.update.middleware(DbSessionMiddleware(session_pool=AsyncSessionLocal))
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Exit')
    except Exception as e:
        logging.error(f"Необработанная ошибка: {e}")