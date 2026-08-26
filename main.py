import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiohttp import web
from supabase import create_client, Client

try:
    from config import BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY, ADMIN_ID
except ImportError:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    ADMIN_ID = os.getenv("ADMIN_ID")

try:
    from config import PORT
except ImportError:
    PORT = os.getenv("PORT", 8080)

# Путь к картинке предпросмотра
PHOTO_PATH = "preview.png"

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Инициализация Supabase клиента
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# --- ВЕБ-СЕРВЕР ДЛЯ UPTIMER / HEALTH CHECK ---
async def handle_ping(request):
    """Эндпоинт для пинга UptimeRobot"""
    return web.Response(text="OK", status=200)

async def start_health_server():
    """Запуск фонового HTTP-сервера"""
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    
    server_port = int(PORT) if PORT else 8080
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", server_port)
    await site.start()
    logger.info(f"🌐 Health-check веб-сервер запущено на порту {server_port}")


# --- КЛАВИАТУРЫ ---
join_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🎯 Забронювати місце в Early Access", callback_data="register_lead")]
])

admin_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
    [InlineKeyboardButton(text="🚀 Почати розсилку", callback_data="admin_broadcast_pre")],
])


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def check_admin(message: types.Message) -> bool:
    """Проверка, является ли пользователь админом."""
    return str(message.from_user.id) == str(ADMIN_ID)


# --- ХЭНДЛЕРЫ КЛИЕНТСКИЕ ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # 1. Отправляем картинку
    if os.path.exists(PHOTO_PATH):
        try:
            photo = FSInputFile(PHOTO_PATH)
            await message.answer_photo(photo)
        except Exception as e:
            logger.error(f"Помилка відправки фото: {e}")
    else:
        logger.warning(f"Файл фото не знайдено за шляхом: {PHOTO_PATH}")

    # 2. Обрабатываем реферала
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    referrer_id = int(args[0]) if args and args[0].isdigit() and int(args[0]) != user_id else None

    # 3. Записываем/обновляем в Supabase (неблокирующий вызов)
    try:
        user_data = {
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "is_active": True,
        }
        if referrer_id:
            user_data["referred_by"] = referrer_id

        await asyncio.to_thread(lambda: supabase.table("users").upsert(user_data, on_conflict="id").execute())
    except Exception as e:
        logger.error(f"Помилка БД Supabase: {e}")

    # 4. Отправляем прогревающий текст
    welcome_text = (
        f"<b>Привіт, {first_name or 'абітурієнте'}! 🖐️</b>\n\n"
        "Якщо ти тут — значить, розумієш: <b>10-11 клас — це вирішальний ривок</b>, "
        "а підготовка до НМТ здається чимось нереально стресовим.\n\n"
        "Але давай чесно: більшість починає зубрити 1 вересня і вигорає вже до листопада. "
        "Ми готуємо систему, яка не просто вчить, а <b>знімає тривогу</b>, дає чіткий план і робить підготовку легкою рутиною без безсонних ночей.\n\n"
        "🚀 <b>Офіційний старт і відкриття доступу — 1 вересня.</b>\n\n"
        "Тисни кнопку нижче, щоб забронювати місце в <b>Early Access</b> та зафіксувати свій бонус!"
    )
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=join_kb)

@dp.callback_query(F.data == "register_lead")
async def process_register(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    try:
        await asyncio.to_thread(lambda: supabase.table("users").update({"is_active": True}).eq("id", user_id).execute())
    except Exception as e:
        logger.error(f"Помилка оновлення статусу: {e}")

    success_text = (
        "<b>Вітаємо! Ти в списку ⚡</b>\n\n"
        "Твій контакт успішно збережено в базі раннього доступу Neta School.\n\n"
        "<b>Що далі?</b>\n"
        "1. Відпочивай та набирайся сил до кінця серпня.\n"
        "2. <b>1 вересня</b> сюди прийде сповіщення з відкриттям доступу та першим матеріалом.\n\n"
        "Ти вже зробив перший крок раніше за 90% інших абітурієнтів. До зустрічі! 🔥"
    )
    await callback.message.edit_text(success_text, parse_mode="HTML")
    await callback.answer()


# --- ХЭНДЛЕРЫ АДМИНКИ ---

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not await check_admin(message):
        return
    await message.answer("🛠 Панель адміністратора:", reply_markup=admin_kb)

@dp.callback_query(F.data == "admin_stats")
async def process_admin_stats(callback: types.CallbackQuery):
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("❌ Доступ заборонено")
        return

    # Получаем статистику из Supabase
    try:
        total_res = await asyncio.to_thread(
            lambda: supabase.table("users").select("id", count="exact").execute()
        )
        total_count = total_res.count if total_res.count is not None else 0

        active_res = await asyncio.to_thread(
            lambda: supabase.table("users").select("id", count="exact").eq("is_active", True).execute()
        )
        active_count = active_res.count if active_res.count is not None else 0

        # ИСПРАВЛЕНИЕ: корректная проверка на IS NOT NULL в Supabase Python SDK
        referred_res = await asyncio.to_thread(
            lambda: supabase.table("users").select("id", count="exact").not_.is_("referred_by", None).execute()
        )
        referred_count = referred_res.count if referred_res.count is not None else 0

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        stats_text = (
            f"<b>📊 Статистика (на {now_str}):</b>\n\n"
            f"👥 Всього користувачів: <code>{total_count}</code>\n"
            f"✅ Активних лидів: <code>{active_count}</code>\n"
            f"🔗 Запрошені рефералами: <code>{referred_count}</code>"
        )
        await callback.message.answer(stats_text, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        logger.error(f"Помилка отримання статистики: {e}")
        await callback.message.answer("⚠️ Помилка отримання статистики з БД Supabase.")
        await callback.answer()


@dp.callback_query(F.data == "admin_broadcast_pre")
async def process_broadcast_pre(callback: types.CallbackQuery):
    if str(callback.from_user.id) != str(ADMIN_ID):
        await callback.answer("❌ Доступ заборонено")
        return
    
    await callback.message.answer(
        "📝 Вкажіть текст для розсилки після команди `/broadcast`.\n\n"
        "Приклад:\n`/broadcast Привіт! Ми відкрилися! Тисни сюди...`"
    )
    await callback.answer()


# --- АДМИН-РАССЫЛКА (Команда) ---
# Использование: /broadcast Текст рассылки
@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    if not await check_admin(message):
        return

    text_to_send = message.text.replace("/broadcast", "").strip()
    if not text_to_send:
        await message.answer("⚠️ Вкажи текст для розсилки. Приклад:\n`/broadcast Текст повідомлення`")
        return

    try:
        res = await asyncio.to_thread(
            lambda: supabase.table("users").select("id").eq("is_active", True).execute()
        )
        users = res.data or []
    except Exception as e:
        logger.error(f"Помилка отримання юзерів для розсилки: {e}")
        await message.answer("⚠️ Помилка отримання списку користувачів з БД.")
        return

    await message.answer(f"🚀 Починаю розсилку на {len(users)} користувачів...")
    logger.info(f"Початок розсилки на {len(users)} юзерів: {text_to_send[:50]}...")

    count_success = 0
    count_blocked = 0

    for u in users:
        try:
            await bot.send_message(chat_id=u["id"], text=text_to_send, parse_mode="HTML")
            count_success += 1
            await asyncio.sleep(0.05)  # Защита от лимитов (20 собщ/сек)
        except Exception:
            try:
                await asyncio.to_thread(
                    lambda: supabase.table("users").update({"is_active": False}).eq("id", u["id"]).execute()
                )
                count_blocked += 1
            except Exception as update_e:
                logger.error(f"Помилка оновлення статусу юзера {u['id']}: {update_e}")

    complete_text = (
        f"✅ <b>Розсилка завершена!</b>\n\n"
        f"Успішно: <code>{count_success}</code>\n"
        f"Заблокували бота (is_active=False): <code>{count_blocked}</code>"
    )
    await message.answer(complete_text, parse_mode="HTML")
    logger.info(f"Розсилка завершена. Успішно: {count_success}, Заблоковано: {count_blocked}")


async def main():
    # 1. Запускаем сервер пинга для UptimeRobot
    await start_health_server()
    # 2. Запускаем поллинг бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинений.")
