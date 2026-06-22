from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from database.db_client import get_or_create_user, supabase
from config import ADMIN_ID

router = Router()

BOT_USERNAME = "netaNMT_bot"
SUPPORT_BOT = "netaschoolbot"


# ---------------------------
# PROFILE
# ---------------------------
@router.message(Command("profile"))
async def show_profile(message: Message, bot: Bot):
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    ref_link = f"https://t.me/{BOT_USERNAME}?start={message.from_user.id}"

    status = "💎 <b>Premium</b>" if user.get("is_premium") else "🆓 <b>Free</b>"

    text = (
        "👤 <b>ПРОФІЛЬ</b>\n"
        "━━━━━━━━━━━━━━━\n\n"

        f"🧑 Імʼя: <b>{user.get('first_name')}</b>\n"
        f"📊 Статус: {status}\n"
        f"📚 Тести: <b>{user.get('total_tests_passed', 0)}</b>\n\n"

        "━━━━━━━━━━━━━━━\n"
        "👥 <b>РЕФЕРАЛИ</b>\n\n"
        f"👤 Запрошено: <b>{user.get('referral_count', 0)}</b>\n"
        f"💎 Premium: <b>{user.get('premium_referrals_count', 0)}</b>\n"
        f"💰 Баланс: <b>{user.get('referral_balance', 0)} ⭐</b>\n\n"

        "━━━━━━━━━━━━━━━\n"
        "🔗 <b>РЕФЕРАЛЬНЕ ПОСИЛАННЯ</b>\n"
        f"<code>{ref_link}</code>\n\n"

        "━━━━━━━━━━━━━━━\n"
        "🎯 <i>Запрошуй друзів і заробляй бонуси</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📤 Поділитись реферальним",
                url=f"https://t.me/share/url?url={ref_link}"
            )
        ],
        [
            InlineKeyboardButton(text="💰 Вивід коштів", callback_data="withdraw"),
            InlineKeyboardButton(text="🔄 Оновити", callback_data="refresh_profile")
        ],
        [
            InlineKeyboardButton(
                text="📩 Підтримка / співпраця",
                url=f"https://t.me/{SUPPORT_BOT}"
            )
        ]
    ])

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ---------------------------
# REFRESH
# ---------------------------
@router.callback_query(F.data == "refresh_profile")
async def refresh(callback: CallbackQuery, bot: Bot):
    await callback.message.delete()
    await show_profile(callback.message, bot)
    await callback.answer()


# ---------------------------
# WITHDRAW
# ---------------------------
@router.callback_query(F.data == "withdraw")
async def withdraw(callback: CallbackQuery, bot: Bot):
    res = supabase.table("users").select("*").eq("id", callback.from_user.id).execute()

    if not res.data:
        await callback.answer("Помилка профілю", show_alert=True)
        return

    user = res.data[0]
    balance = user.get("referral_balance", 0)

    if balance <= 0:
        await callback.answer(
            "❌ Баланс 0. Запрошуй друзів!",
            show_alert=True
        )
        return

    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "💰 ЗАЯВКА НА ВИВІД\n\n"
                f"👤 {user.get('first_name')}\n"
                f"ID: {callback.from_user.id}\n"
                f"@{user.get('username')}\n"
                f"Баланс: {balance} ⭐"
            )
        )

        await callback.message.answer("✅ Заявка відправлена!")

    except Exception:
        await callback.message.answer("⚠️ Помилка. Напиши в підтримку.")

    await callback.answer()


# ---------------------------
# SUPPORT
# ---------------------------
@router.message(Command("support"))
async def support(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📩 Написати підтримці",
                url=f"https://t.me/{SUPPORT_BOT}"
            )
        ]
    ])

    await message.answer(
        "📩 <b>Підтримка та співпраця</b>\n\n"
        "Є питання, помилки або пропозиції — напиши нам.",
        reply_markup=kb,
        parse_mode="HTML"
    )
