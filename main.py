import asyncio
from aiogram import Bot, Dispatcher
from aiohttp import web
from config import BOT_TOKEN, PORT
# 🎯 1. Додаємо ai_tutor в імпорт хендлерів:
from handlers import start, quiz, admin, profile, ai_tutor
from middlewares.throttling import ThrottlingMiddleware

# ініціалізація бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# захист від спаму кнопками
dp.callback_query.middleware(ThrottlingMiddleware(slow_down_rate=0.6))

# роутери бота
dp.include_router(start.router)
dp.include_router(quiz.router)
dp.include_router(admin.router)
dp.include_router(profile.router)
# 🎯 2. Підключаємо роутер AI-тьютора:
dp.include_router(ai_tutor.router)


# для підтримки аптайму сервера (ping endpoint)
async def handle_ping(request):
    return web.Response(text="NetaNMT is actively running!")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # веб-сервер для аптайму
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

# запуск бота
async def main():
    # веб-сервер щоб бот не падав на хостингу
    await start_web_server()   
    # очистка старих оновлень перед лонг-полінгом
    await bot.delete_webhook(drop_pending_updates=True)    
    # запуск лонг-полінгу
    await dp.start_polling(bot)

if __name__ == "__main__":
    async def run():
        try:
            await main()
        except (KeyboardInterrupt, SystemExit):
            pass

    asyncio.run(run())
