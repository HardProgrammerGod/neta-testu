from aiogram import Router, Bot
from aiogram.types import Message
from aiogram.filters import CommandStart
from database.db_client import get_or_create_user
from config import CHANNEL_ID

router = Router()

async def check_subscription(bot: Bot, user_id: int) -> bool:
    """Перевіряє підписку на канал. Якщо користувач адмін/творець — пропускає автоматично."""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    if not await check_subscription(bot, message.from_user.id):
        await message.answer(
            "⚠️ **Доступ обмежено!**\n\n"
            "Щоб проходити тести та готуватись до ЗНО/НМТ з англійської, підпишись на наш канал.\n\n"
            "Після підписки знову натисни /start"
        )
        return

    await message.answer(
        f"👋 Вітаємо, {user['first_name']} у тренажері **TurboZNO**!\n\n"
        f"📈 Твій статус: {'Premium (Безліміт) 💎' if user['is_premium'] else 'Безкоштовний 🆓'}\n"
        f"⏳ Залишилось безкоштовних тестів на сьогодні: {user['daily_tests_left'] if not user['is_premium'] else '∞'}\n\n"
        "👉 Напиши /quiz, щоб розпочати тестування."
    )
