import asyncio
from aiogram import Bot, Dispatcher
from aiohttp import web
from config import BOT_TOKEN, PORT
from handlers import start, quiz, admin, profile, ai_tutor
from middlewares.throttling import ThrottlingMiddleware
from services.cleaner import periodic_cleaner_task

# Ініціалізація бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Захист від спаму кнопками
dp.callback_query.middleware(ThrottlingMiddleware(slow_down_rate=0.6))

# Підключення роутерів
dp.include_router(start.router)
dp.include_router(quiz.router)
dp.include_router(admin.router)
dp.include_router(profile.router)
dp.include_router(ai_tutor.router)


async def handle_ping(request):
    return web.Response(text="NetaNMT is actively running!")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()


async def main():
    # 1. Запуск веб-сервера для збереження аптайму
    await start_web_server()

    # 2. Очищення старих оновлень
    await bot.delete_webhook(drop_pending_updates=True)

    # 3. Запуск фонового авто-очищувача бази даних (кожні 24 години)
    cleaner_task = asyncio.create_task(periodic_cleaner_task(bot))

    try:
        # 4. Запуск лонг-полінгу
        await dp.start_polling(bot)
    finally:
        cleaner_task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
