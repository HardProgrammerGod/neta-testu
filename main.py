import asyncio
from aiogram import Bot, Dispatcher
from aiohttp import web
from config import BOT_TOKEN, PORT
from handlers import start, quiz, admin

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.include_router(start.router)
dp.include_router(quiz.router)
dp.include_router(admin.router)

async def handle_ping(request):
    return web.Response(text="TurboZNO is actively running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

async def main():
    # Запуск легкого веб-сервера, щоб Render не вимикав сервіс
    await start_web_server()
    # Запуск лонг-полінгу бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
