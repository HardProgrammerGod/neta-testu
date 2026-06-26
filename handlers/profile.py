import html
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from database.db_client import get_or_create_user, supabase
from config import ADMIN_ID

router = Router()

BOT_USERNAME = "netaNMT_bot"
SUPPORT_BOT = "netaschoolbot"


def generate_profile_markup(ref_link: str) -> InlineKeyboardMarkup:
    """Генератор клавіатури профілю для уникнення дублювання коду."""
    return InlineKeyboardMarkup(inline_keyboard=[
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


def build_profile_text(user: dict, ref_link: str) -> str:
    """Генератор тексту профілю з безпечним екрануванням імен."""
    status = "💎 <b>Premium</b>" if user.get("is_premium") else "🆓 <b>Free</b>"
    first_name = html.escape(user.get('first_name') or "Користувач")
    
    return (
        "👤 <b>ПРОФІЛЬ</b>\n"
        "━━━━━━━━━━━━━━━\n\n"

        f"🧑 Імʼя: <b>{first_name}</b>\n"
        f"📊 Status: {status}\n"
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


# ---------------------------
# PROFILE
# ---------------------------
@router.message(Command("profile"))
async def show_profile(message: Message, bot: Bot):
    # Отримуємо користувача або створюємо, якщо його немає
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    ref_link = f"https://t.me/{BOT_USERNAME}?start={message.from_user.id}"
    text = build_profile_text(user, ref_link)
    kb = generate_profile_markup(ref_link)

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# ---------------------------
# REFRESH
# ---------------------------
@router.callback_query(F.data == "refresh_profile")
async def refresh(callback: CallbackQuery, bot: Bot):
    # ПРЯМИЙ і чистий запит до Supabase для миттєвого отримання оновлених рефералів та балансу
    res = supabase.table("users").select("*").eq("id", callback.from_user.id).execute()
    
    if not res.data:
        await callback.answer("❌ Помилка синхронізації з базою", show_alert=True)
        return
        
    user = res.data[0]
    ref_link = f"https://t.me/{BOT_USERNAME}?start={callback.from_user.id}"
    
    new_text = build_profile_text(user, ref_link)
    kb = generate_profile_markup(ref_link)
    
    # Плавне оновлення інтерфейсу без видалення самого повідомлення
    try:
        await callback.message.edit_text(new_text, reply_markup=kb, parse_mode="HTML")
        await callback.answer("🔄 Профіль успішно оновлено!")
    except Exception:
        # На випадок, якщо дані абсолютно не змінилися і Telegram видає ігноровану помилку
        await callback.answer("Дані актуальні.")


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
            "❌ Твій баланс порожній. Запрошуй друзів, щоб заробити Stars!",
            show_alert=True
        )
        return

    try:
        user_name = html.escape(user.get('first_name') or "Без імені")
        tg_username = f"@{user.get('username')}" if user.get('username') else "немає тегу"
        
        # Надсилаємо структуровану заявку адміну
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "🚨 <b>НОВА ЗАЯВКА НА ВИВІД</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 Користувач: <b>{user_name}</b>\n"
                f"🆔 Telegram ID: <code>{callback.from_user.id}</code>\n"
                f"🔗 Юзернейм: {tg_username}\n"
                f"💰 Сума до виведення: <b>{balance} ⭐</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ Після виплати баланс користувача необхідно обнулити в Supabase."
            ),
            parse_mode="HTML"
        )

        # Очищуємо баланс у базі після успішного формування запиту для запобігання дублювання запитів
        supabase.table("users").update({"referral_balance": 0}).eq("id", callback.from_user.id).execute()

        await callback.message.answer(
            "✅ <b>Заявка успішно надіслана адміністрації!</b>\n"
            "Твій поточний реферальний баланс тимчасово заморожено до обробки виплати.", 
            parse_mode="HTML"
        )
        
        # Оновлюємо візуальну картку профілю
        user["referral_balance"] = 0
        ref_link = f"https://t.me/{BOT_USERNAME}?start={callback.from_user.id}"
        await callback.message.edit_text(build_profile_text(user, ref_link), reply_markup=generate_profile_markup(ref_link), parse_mode="HTML")

    except Exception:
        await callback.message.answer("⚠️ Сталася технічна помилка під час формування заявки. Напиши безпосередньо в підтримку.")

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
        "Є питання, знайшов помилку в тестах або маєш пропозиції щодо інтеграцій — напиши нам.",
        reply_markup=kb,
        parse_mode="HTML"
    )
