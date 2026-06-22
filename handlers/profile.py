from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from database.db_client import get_or_create_user, supabase
from config import ADMIN_ID

router = Router()

BOT_USERNAME = "netaNMT_bot"
SUPPORT_BOT = "netaschoolbot"


# ---------------------------
# PROFILE COMMAND
# ---------------------------
@router.message(Command("profile"))
async def show_profile(message: Message, bot: Bot):
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    ref_link = f"https://t.me/{BOT_USERNAME}?start={message.from_user.id}"

    status = "💎 Premium" if user.get("is_premium") else "🆓 Free"

    text = (
        "👤 Профіль користувача\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Імʼя: {user.get('first_name')}\n"
        f"Статус: {status}\n"
        f"Вирішено задач: {user.get('total_tests_passed', 0)}\n\n"
        "👥 Реферали:\n"
        f"- Запрошено: {user.get('referral_count', 0)}\n"
        f"- Premium реферали: {user.get('premium_referrals_count', 0)}\n\n"
        f"💰 Баланс: {user.get('referral_balance', 0)} ⭐\n\n"
        f"🔗 Реферальне посилання:\n{ref_link}\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 Вивід коштів", url=f"https://t.me/{SUPPORT_BOT}")
        ],
        [
            InlineKeyboardButton(text="🔄 Оновити", callback_data="refresh_profile"),
            InlineKeyboardButton(text="📩 Підтримка", url=f"https://t.me/{SUPPORT_BOT}")
        ]
    ])

    await message.answer(text, reply_markup=kb)


# ---------------------------
# REFRESH PROFILE
# ---------------------------
@router.callback_query(F.data == "refresh_profile")
async def refresh(callback: CallbackQuery, bot: Bot):
    await callback.message.delete()
    await show_profile(callback.message, bot)
    await callback.answer()


# ---------------------------
# WITHDRAW / REQUEST MONEY
# ---------------------------
@router.callback_query(F.data == "withdraw")
async def withdraw(callback: CallbackQuery, bot: Bot):
    user = supabase.table("users").select("*").eq("id", callback.from_user.id).execute()

    if not user.data:
        await callback.answer("Помилка профілю", show_alert=True)
        return

    user = user.data[0]
    balance = user.get("referral_balance", 0)

    if balance <= 0:
        await callback.answer(
            "❌ Баланс порожній. Запрошуй друзів для заробітку!",
            show_alert=True
        )
        return

    # повідомлення адмінy (без Markdown — безпечно)
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "💰 ЗАЯВКА НА ВИВІД\n\n"
                f"Користувач: {user.get('first_name')}\n"
                f"ID: {callback.from_user.id}\n"
                f"Username: @{user.get('username')}\n"
                f"Баланс: {balance} ⭐"
            )
        )

        await callback.message.answer(
            "✅ Заявку відправлено. Очікуй відповіді!"
        )

    except Exception:
        await callback.message.answer(
            "⚠️ Не вдалося відправити заявку. Напиши в підтримку."
        )

    await callback.answer()


# ---------------------------
# SUPPORT COMMAND (опціонально)
# ---------------------------
@router.message(Command("support"))
async def support(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📩 Написати підтримці",
            url=f"https://t.me/{SUPPORT_BOT}"
        )]
    ])

    await message.answer(
        "📩 Підтримка та співпраця\n\n"
        "Якщо у тебе питання щодо бота, помилки або пропозиції — напиши нам.",
        reply_markup=kb
    )
