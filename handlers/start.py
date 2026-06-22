from aiogram import Router, Bot, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart
from database.db_client import get_or_create_user
from config import CHANNEL_ID

router = Router()

CHANNEL_LINK = "https://t.me/nedo_english"


async def check_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return True


async def send_welcome(message: Message, user: dict):
    status = "Premium 💎" if user.get("is_premium") else "Безкоштовний 🆓"
    limit = "∞" if user.get("is_premium") else user.get("daily_tests_left", 0)

    await message.answer(
        f"👋 Привіт, {user['first_name']}!\n\n"
        f"📊 Статус: {status}\n"
        f"⏳ Спроб: {limit}\n\n"
        "👉 /quiz — почати тест"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    if not await check_subscription(bot, message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Підписатися", url=CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Перевірити", callback_data="check_sub")]
        ])

        await message.answer("⚠️ Потрібна підписка", reply_markup=kb)
        return

    await send_welcome(message, user)


@router.callback_query(F.data == "check_sub")
async def check_sub(callback: CallbackQuery, bot: Bot):
    if await check_subscription(bot, callback.from_user.id):
        await callback.message.delete()
        await cmd_start(callback.message, bot)
    else:
        await callback.answer("❌ Ще не підписаний", show_alert=True)
