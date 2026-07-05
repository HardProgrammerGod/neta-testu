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
                text="📤 Поділитись реферальним посиланням",
                url=f"https://t.me/share/url?url={ref_link}&text=Привіт!+Готуюсь+до+НМТ+з+англійської+тут.+Заходь,+тести+реально+вогонь!+🔥"
            )
        ],
        [
            InlineKeyboardButton(text="💰 Вивід Stars", callback_data="withdraw"),
            InlineKeyboardButton(text="🔄 Оновити дані", callback_data="refresh_profile")
        ],
        [
            InlineKeyboardButton(
                text="📩 Підтримка / співпраця",
                url=f"https://t.me/{SUPPORT_BOT}"
            )
        ]
    ])


def get_student_rank(tests_passed: int) -> str:
    """Психологічний триггер: динамічні звання для підвищення утримання (Retention)."""
    if tests_passed >= 200: return "🧠 Магістр НМТ (200+ балів)"
    if tests_passed >= 100: return "⚡ Експерт граматики"
    if tests_passed >= 50:  return "🔥 Активний абітурієнт"
    if tests_passed >= 10:  return "📚 Цілеспрямований учень"
    return "🌱 Новачок (Початок шляху)"


def build_profile_text(user: dict, ref_link: str) -> str:
    """Генератор тексту профілю з безпечним екрануванням та триггерами."""
    is_premium = user.get("is_premium", False)
    status = "💎 <b>Premium допуск</b>" if is_premium else "🆓 <b>Безкоштовний (Free)</b>"
    
    first_name = html.escape(user.get('first_name') or "Користувач")
    tests_passed = user.get('total_tests_passed', 0)
    rank = get_student_rank(tests_passed)
    
    # Психологічний байт на покупку Premium
    premium_marketing = ""
    if not is_premium:
        premium_marketing = (
            "━━━━━━━━━━━━━━━\n"
            "⚠️ <b>Тобі недоступні повні розбори помилок!</b>\n"
            "Premium учні бачать детальні правила до кожного питання. Не втрачай бали на іспиті, активуй підписку через /quiz ⚡\n"
        )
    
    return (
        "👤 <b>МІЙ ОСОБИСТИЙ КАБІНЕТ</b>\n"
        "━━━━━━━━━━━━━━━\n\n"

        f"🧑 Імʼя: <b>{first_name}</b>\n"
        f"📊 Статус: {status}\n"
        f"🎯 Ранг: <code>{rank}</code>\n"
        f"📚 Вирішено завдань: <b>{tests_passed}</b>\n\n"

        f"{premium_marketing}"

        "━━━━━━━━━━━━━━━\n"
        "👥 <b>РЕФЕРАЛЬНА ПРОГРАМА</b>\n\n"
        f"👤 Запрошено друзів: <b>{user.get('referral_count', 0)}</b>\n"
        f"💎 З них придбали Premium: <b>{user.get('premium_referrals_count', 0)}</b>\n"
        f"💰 Твій баланс: <b>{user.get('referral_balance', 0)} ⭐ (Telegram Stars)</b>\n\n"

        "━━━━━━━━━━━━━━━\n"
        "🔗 <b>ТВОЄ ПОСИЛАННЯ ДЛЯ ЗАПРОШЕННЯ:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        "<i>За кожного друга, який купує Premium, ти миттєво отримуєш 100 ⭐ на баланс!</i>"
    )


# ---------------------------
# PROFILE
# ---------------------------
@router.message(Command("profile"))
async def show_profile(message: Message, bot: Bot):
    try:
        user = await get_or_create_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name
        )

        ref_link = f"https://t.me/{BOT_USERNAME}?start={message.from_user.id}"
        text = build_profile_text(user, ref_link)
        kb = generate_profile_markup(ref_link)

        await message.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await message.answer("⚠️ Не вдалося завантажити профіль через технічні неполадки мережі. Спробуй пізніше через /profile")


# ---------------------------
# REFRESH
# ---------------------------
@router.callback_query(F.data == "refresh_profile")
async def refresh(callback: CallbackQuery, bot: Bot):
    try:
        res = supabase.table("users").select("*").eq("id", callback.from_user.id).execute()
        
        if not res.data:
            await callback.answer("❌ Користувача не знайдено в базі.", show_alert=True)
            return
            
        user = res.data[0]
        ref_link = f"https://t.me/{BOT_USERNAME}?start={callback.from_user.id}"
        
        new_text = build_profile_text(user, ref_link)
        kb = generate_profile_markup(ref_link)
        
        await callback.message.edit_text(new_text, reply_markup=kb, parse_mode="HTML")
        await callback.answer("🔄 Профіль оновлено!")
    except Exception:
        await callback.answer("Дані вже актуальні.")


# ---------------------------
# WITHDRAW (ЗАХИЩЕНИЙ ВИВІД КОШТІВ)
# ---------------------------
@router.callback_query(F.data == "withdraw")
async def withdraw(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    
    try:
        # 1. Спочатку беремо актуальні дані з бази
        res = supabase.table("users").select("*").eq("id", user_id).execute()
        if not res.data:
            await callback.answer("Помилка ідентифікації профілю.", show_alert=True)
            return

        user = res.data[0]
        balance = user.get("referral_balance", 0)

        if balance <= 0:
            await callback.answer(
                "❌ Твій баланс порожній. Запрошуй друзів через реферальне посилання, щоб заробити Stars!",
                show_alert=True
            )
            return

        # 2. АТОМАРНА БЕЗПЕКА: Спочатку списуємо гроші в базі з перевіркою, щоб захиститися від флуду кліками
        update_res = supabase.table("users")\
            .update({"referral_balance": 0})\
            .eq("id", user_id)\
            .gt("referral_balance", 0)\
            .execute()

        # Якщо апдейт не повернув дані, значить баланс вже встиг стати 0 (подвійне натискання кнопки)
        if not update_res.data:
            await callback.answer("⚠️ Заявка вже обробляється або баланс змінився.", show_alert=True)
            return

        # 3. Тільки після успішного списання в БД відправляємо повідомлення адміну
        user_name = html.escape(user.get('first_name') or "Без імені")
        tg_username = f"@{user.get('username')}" if user.get('username') else "немає тегу"
        
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "🚨 <b>НОВА ЗАЯВКА НА ВИВІД</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 Користувач: <b>{user_name}</b>\n"
                f"🆔 Telegram ID: <code>{user_id}</code>\n"
                f"🔗 Юзернейм: {tg_username}\n"
                f"💰 Сума до виведення: <b>{balance} ⭐</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ Розрахунок списано з балансу користувача автоматично. Виплати йому зірки вручну."
            ),
            parse_mode="HTML"
        )

        # 4. Оновлюємо інтерфейс користувача
        await callback.message.answer(
            "✅ <b>Заявку успішно надіслано!</b>\n"
            f"Твій запит на виведення <b>{balance} ⭐</b> передано адміністрації. Очікуй нарахування протягом 24 годин.", 
            parse_mode="HTML"
        )
        
        user["referral_balance"] = 0
        ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        await callback.message.edit_text(build_profile_text(user, ref_link), reply_markup=generate_profile_markup(ref_link), parse_mode="HTML")

    except Exception as e:
        await callback.message.answer("⚠️ Сталася технічна помилка. Спробуй ще раз через кнопку 'Оновити' або звернись у підтримку.")
    
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
