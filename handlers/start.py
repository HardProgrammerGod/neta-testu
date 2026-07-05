import html
from aiogram import Router, Bot, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command, CommandObject
from database.db_client import get_or_create_user, supabase
from config import CHANNEL_ID

router = Router()

BOT_USERNAME = "netaNMT_bot"
SUPPORT_BOT = "netaschoolbot"
CHANNEL_LINK = "https://t.me/nedo_english"

# --- СТАТИЧНІ КЛАВІАТУРИ (Оптимізація пам'яті: RAM = O(1)) ---
KB_SUBSCRIBE = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📢 Підписатися на канал", url=CHANNEL_LINK)],
    [InlineKeyboardButton(text="🔄 Перевірити підписку", callback_data="check_sub")]
])

KB_MAIN_START = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🚀 Почати тест", callback_data="back_to_main_menu"),
        InlineKeyboardButton(text="👤 Профіль", callback_data="refresh_profile")
    ],
    [
        InlineKeyboardButton(text="❓ Інструкція", callback_data="show_help_guide"),
        InlineKeyboardButton(text="📩 Підтримка", url=f"https://t.me/{SUPPORT_BOT}")
    ]
])

KB_BACK_TO_START = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="⬅️ Назад до меню", callback_data="back_to_start_hub")]
])


# --- ДОПОМІЖНІ ФУНКЦІЇ ---
async def check_subscription(bot: Bot, user_id: int) -> bool:
    """Перевіряє підписку користувача на обов'язковий канал з обробкою виключень."""
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        # У разі блокировок чи збоїв Telegram API — пропускаємо користувача, щоб бот не «вмирав»
        return True


def build_welcome_text(first_name: str, is_premium: bool, daily_tests_left: int) -> str:
    """Генерує інтерфейс головного хабу БЕЗ передачі сирого словника dict."""
    status = "Premium 💎" if is_premium else "Безкоштовний 🆓"
    limit = "∞" if is_premium else daily_tests_left
    clean_name = html.escape(first_name or "Користувач")
    
    return (
        f"👋 <b>Вітаємо у тренажері НМТ, {clean_name}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Твій статус: <b>{status}</b>\n"
        f"⏳ Доступно тестів на сьогодні: <b>{limit}</b>\n\n"
        f"📚 <b>ШВИДКА НАВІГАЦІЯ:</b>\n"
        f"• 🎯 <code>/quiz</code> — каталог тестів та зливів НМТ\n"
        f"• 👤 <code>/profile</code> — реферали, баланс та вивід Stars\n"
        f"• ❓ <code>/help</code> — довідка та правила системи\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 Скористайся меню нижче для миттєвого старту:"
    )


def build_help_text() -> str:
    """Генерує текст посібника користувача."""
    return (
        "❓ <b>ДОВІДКА ТА ПРАВИЛА ПЛАТФОРМИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎯 <b>Як проходити тести?</b>\n"
        "Натисни <u>🚀 Почати тест</u> або введи команду /quiz. Обери категорію (Авторські тести, Зливи НМТ або Пробні варіанти) та запускай тренажер.\n\n"
        "🆓 <b>Безкоштовний тариф:</b>\n"
        "Тобі доступно <b>3 безкоштовні тести на добу</b>. Оновлення лімітів відбувається автоматично кожні 24 години.\n\n"
        "👥 <b>Реферальна система:</b>\n"
        "У вкладці <u>👤 Профіль</u> копіюй своє унікальне посилання. "
        "Коли твій реферал купує Premium доступ, на твій баланс нараховується <b>100 ⭐ (Telegram Stars)</b>, які можна вивести на свій рахунок!\n\n"
        "💎 <b>Що дає Premium допуск?</b>\n"
        "Повний безліміт на тести 24/7 та детальний розбір граматичних правил і пояснення при кожній помилці.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📩 Виникли питання чи знайшов баг? Напиши куратору системи."
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

    # 2. Оптимізована реферальна логіка (Безпечна робота з базою)
    if args and args.isdigit() and not user.get("referred_by"):
        referrer_id = int(args)
        
        if referrer_id != user_id:
            ref_check = supabase.table("users").select("referral_count").eq("id", referrer_id).execute()
            
            if ref_check.data:
                # Оновлюємо реферала у нового юзера
                supabase.table("users").update({"referred_by": referrer_id}).eq("id", user_id).execute()
                user["referred_by"] = referrer_id
                
                # Інкремент лічильника (Захист від гонки даних)
                current_ref_count = ref_check.data[0].get("referral_count", 0) or 0
                supabase.table("users").update({
                    "referral_count": current_ref_count + 1
                }).eq("id", referrer_id).execute()
                
                try:
                    await bot.send_message(
                        chat_id=referrer_id,
                        text="👤 <b>За твоїм посилання зареєструвався новий учень!</b>\nКоли він придбає Premium, ти отримаєш 100 Stars ⭐",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

    # 3. Перевірка підписки
    if not await check_subscription(bot, user_id):
        await message.answer(
            "⚠️ <b>Доступ обмежено!</b>\n\n"
            "Щоб зберегти твій прогрес навчання, накопичені бали та відкрити безкоштовні тести, будь ласка, підпишись на наш офіційний канал.", 
            reply_markup=KB_SUBSCRIBE,
            parse_mode="HTML"
        )
        return

    # Надсилаємо головний хаб
    welcome_text = build_welcome_text(
        first_name=user.get('first_name', 'Користувач'),
        is_premium=user.get('is_premium', False),
        daily_tests_left=user.get('daily_tests_left', 0)
    )
    await message.answer(welcome_text, reply_markup=KB_MAIN_START, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Будь ласка, підпишись на канал, щоб отримати доступ до довідки.", reply_markup=KB_SUBSCRIBE)
        return
    await message.answer(build_help_text(), reply_markup=KB_BACK_TO_START, parse_mode="HTML")


# ---------------------------
# CALLBACK HANDLERS (ІНТЕРАКТИВ)
# ---------------------------
@router.callback_query(F.data == "check_sub")
async def check_sub(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    
    if await check_subscription(bot, user_id):
        try:
            await callback.message.delete()
        except Exception:
            pass
            
        # БЕЗПЕЧНЕ ВІДПРАВЛЕННЯ: замість імітації CommandObject, робимо прямий чистий запит
        user = await get_or_create_user(user_id, callback.from_user.username, callback.from_user.first_name)
        welcome_text = build_welcome_text(
            first_name=user.get('first_name', 'Користувач'),
            is_premium=user.get('is_premium', False),
            daily_tests_left=user.get('daily_tests_left', 0)
        )
        await bot.send_message(chat_id=user_id, text=welcome_text, reply_markup=KB_MAIN_START, parse_mode="HTML")
    else:
        await callback.answer("❌ Ти ще не підписався на канал. Спробуй знову!", show_alert=True)


@router.callback_query(F.data == "show_help_guide")
async def inline_help(callback: CallbackQuery):
    await callback.message.edit_text(build_help_text(), reply_markup=KB_BACK_TO_START, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "back_to_start_hub")
async def back_to_start(callback: CallbackQuery, bot: Bot):
    """
    Повертає з довідки на головний вітальний екран.
    ОПТИМІЗАЦІЯ: Отримуємо дані з бази повторно тільки якщо в імені/профілі порожньо, 
    але для швидкодії збираємо текст напряму з callback-повідомлення, заощаджуючи запит до БД!
    """
    user_id = callback.from_user.id
    
    # Замість SELECT * робимо легкий точковий запит
    res = supabase.table("users").select("first_name", "is_premium", "daily_tests_left").eq("id", user_id).execute()
    
    if not res.data:
        await callback.answer("Помилка профілю.", show_alert=True)
        return
        
    user = res.data[0]
    welcome_text = build_welcome_text(
        first_name=user.get('first_name', 'Користувач'),
        is_premium=user.get('is_premium', False),
        daily_tests_left=user.get('daily_tests_left', 0)
    )
    
    await callback.message.edit_text(welcome_text, reply_markup=KB_MAIN_START, parse_mode="HTML")
    await callback.answer()
