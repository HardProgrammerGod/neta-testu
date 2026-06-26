import asyncio
from aiogram import Bot, Dispatcher
from aiohttp import web
from config import BOT_TOKEN, PORT
from handlers import start, quiz, admin, profile
from middlewares.throttling import ThrottlingMiddleware

# иниц бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# защитка от спама кнопками
dp.callback_query.middleware(ThrottlingMiddleware(slow_down_rate=0.6))

# роутеры бота
dp.include_router(start.router)
dp.include_router(quiz.router)
dp.include_router(admin.router)
dp.include_router(profile.router)


# для оживки сервер для аптайм
async def handle_ping(request):
    return web.Response(text="NetaNMT is actively running!")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # сервер аптаймера 
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

# врубка бота
async def main():
    # веб сервер чтобы бот не падал
    await start_web_server()  
    # очистка старых соо перед полингом
    await bot.delete_webhook(drop_pending_updates=True)   
    # запуск лонг полинга
    await dp.start_polling(bot)

if __name__ == "__main__":
    async def run():
        try:
            await main()
        except (KeyboardInterrupt, SystemExit):
            pass

    asyncio.run(run())
