import html
from aiogram import Router, Bot, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command, CommandObject
from database.db_client import get_or_create_user, supabase
from config import CHANNEL_ID

router = Router()

CHANNEL_LINK = "https://t.me/nedo_english"
SUPPORT_BOT = "netaschoolbot"

# --- СТАТИЧНІ КЛАВІАТУРИ (Оптимізація пам'яті: створюються один раз при завантаженні модуля) ---
KB_SUBSCRIBE = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📢 Підписатися на канал", url=CHANNEL_LINK)],
    [InlineKeyboardButton(text="🔄 Перевірити підписку", callback_data="check_sub")]
])

KB_MAIN_START = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🚀 Почати тест", callback_data="back_to_main_menu"), # Тригер повернення в меню квізів з quiz.py
        InlineKeyboardButton(text="👤 Профіль", callback_data="refresh_profile")       # Тригер оновлення/показу профілю з profile.py
    ],
    [
        InlineKeyboardButton(text="❓ Інструкція", callback_data="show_help_guide"),
        InlineKeyboardButton(text="📩 Підтримка", url=f"https://t.me/{SUPPORT_BOT}")
    ]
])

KB_BACK_TO_START = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_start_hub")]
])


# --- ДОПОМІЖНІ ФУНКЦІЇ ---
async def check_subscription(bot: Bot, user_id: int) -> bool:
    """Перевіряє підписку користувача на обов'язковий канал."""
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return True


def build_welcome_text(user: dict) -> str:
    """Генерує інформативний та структурований інтерфейс головного хабу."""
    status = "Premium 💎" if user.get("is_premium") else "Безкоштовний 🆓"
    limit = "∞" if user.get("is_premium") else user.get("daily_tests_left", 0)
    clean_name = html.escape(user.get('first_name') or "Користувач")
    
    return (
        f"👋 <b>Вітаємо у тренажері НМТ, {clean_name}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Твій статус: <b>{status}</b>\n"
        f"⏳ Доступно тестів на сьогодні: <b>{limit}</b>\n\n"
        f"📚 <b>ШВИДКА ІНСТРУКЦІЯ:</b>\n"
        f"• 🎯 <code>/quiz</code> — запуск тренувальних та пробних тестів.\n"
        f"• 👤 <code>/profile</code> — реферальне посилання, баланс та вивід Stars.\n"
        f"• ❓ <code>/help</code> — розгорнутий посібник користувача.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 Використовуй інлайн-меню для миттєвої навігації:"
    )


def build_help_text() -> str:
    """Генерує текст посібника користувача (Help Guide)."""
    return (
        "❓ <b>ДОВІДКА ТА ПРАВИЛА ПЛАТФОРМИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎯 <b>Як проходити тести?</b>\n"
        "Натисни <u>🚀 Почати тест</u> або напиши команду /quiz. Обери потрібну категорію (Авторські, Зливи або Моки) та стартуй варіант.\n\n"
        "🆓 <b>Які обмеження на безкоштовному тарифі?</b>\n"
        "Користувачам без Premium доступно <b>3 безкоштовні тести на добу</b>. Ліміти оновлюються автоматично щодня.\n\n"
        "👥 <b>Як працює реферальна система?</b>\n"
        "У вкладці <u>👤 Профіль</u> знаходиться твоє унікальне посилання. Пересилай його друзям. "
        "Коли твій реферал купує Premium доступ, на твій баланс миттєво нараховується <b>100 ⭐ (Telegram Stars)</b>, які можна вивести!\n\n"
        "💎 <b>Що дає Premium допуск?</b>\n"
        "Повний безліміт на проходження тестів 24/7 та доступ до детальних розборів і граматичних правил при кожній помилці.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📩 Виникли технічні проблеми чи баги? Напиши куратору системи."
    )


# ---------------------------
# КОМАНДИ /start ТА /help
# ---------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, command: CommandObject):
    user_id = message.from_user.id
    args = command.args

    # 1. Отримання або створення користувача
    user = await get_or_create_user(user_id, message.from_user.username, message.from_user.first_name)

    # 2. Оптимізована реферальна логіка (спрацьовує виключно 1 раз при реєстрації)
    if args and args.isdigit() and not user.get("referred_by"):
        referrer_id = int(args)
        
        if referrer_id != user_id:
            ref_check = supabase.table("users").select("referral_count").eq("id", referrer_id).execute()
            
            if ref_check.data:
                supabase.table("users").update({"referred_by": referrer_id}).eq("id", user_id).execute()
                user["referred_by"] = referrer_id
                
                current_ref_count = ref_check.data[0].get("referral_count", 0) or 0
                supabase.table("users").update({
                    "referral_count": current_ref_count + 1
                }).eq("id", referrer_id).execute()
                
                try:
                    await bot.send_message(
                        chat_id=referrer_id,
                        text="👤 <b>За твоїм посиланням зареєструвався новий учень!</b>\nКоли він придбає Premium, ти отримаєш 100 Stars ⭐"
                    )
                except Exception:
                    pass

    # 3. Обов'язкова перевірка підписки
    if not await check_subscription(bot, user_id):
        await message.answer(
            "⚠️ <b>Доступ обмежено!</b>\n\n"
            "Щоб зберегти твій прогрес навчання, бали та відкрити безкоштовні тести, будь ласка, підпишись на наш офіційний канал.", 
            reply_markup=KB_SUBSCRIBE,
            parse_mode="HTML"
        )
        return

    # Надсилаємо головний хаб
    await message.answer(build_welcome_text(user), reply_markup=KB_MAIN_START, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message, bot: Bot):
    # Перед показом довідки перевіряємо підписку, щоб уникнути обходу системи захисту
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Будь ласка, підпишись на канал, щоб отримати доступ до довідки.", reply_markup=KB_SUBSCRIBE)
        return
    await message.answer(build_help_text(), reply_markup=KB_BACK_TO_START, parse_mode="HTML")


# ---------------------------
# CALLBACK HANDLERS (ІНТЕРАКТИВ)
# ---------------------------
@router.callback_query(F.data == "check_sub")
async def check_sub(callback: CallbackQuery, bot: Bot):
    if await check_subscription(bot, callback.from_user.id):
        try:
            await callback.message.delete()
        except Exception:
            pass
            
        fake_command = CommandObject(prefix="/", command="start", args=None)
        await cmd_start(callback.message, bot, fake_command)
    else:
        await callback.answer("❌ Ти ще не підписався на канал. Спробуй знову!", show_alert=True)


@router.callback_query(F.data == "show_help_guide")
async def inline_help(callback: CallbackQuery):
    """Перемикає інтерфейс на сторінку допомоги без надсилання нових повідомлень."""
    await callback.message.edit_text(build_help_text(), reply_markup=KB_BACK_TO_START, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "back_to_start_hub")
async def back_to_start(callback: CallbackQuery):
    """Повертає з довідки на головний вітальний екран."""
    res = supabase.table("users").select("*").eq("id", callback.from_user.id).execute()
    if not res.data:
        await callback.answer("Помилка профілю.", show_alert=True)
        return
        
    user = res.data[0]
    await callback.message.edit_text(build_welcome_text(user), reply_markup=KB_MAIN_START, parse_mode="HTML")
    await callback.answer()
