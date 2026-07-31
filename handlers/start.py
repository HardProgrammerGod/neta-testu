import html
from aiogram import Router, Bot, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from database.db_client import get_or_create_user, purge_blocked_user, supabase
from config import CHANNEL_ID

router = Router()

BOT_USERNAME = "netaNMT_bot"
SUPPORT_BOT = "netaschoolbot"
CHANNEL_LINK = "https://t.me/nedo_english"

# --- СТАТИЧНІ КЛАВІАТУРИ ---
KB_SUBSCRIBE = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📢 Підписатися на канал", url=CHANNEL_LINK)],
    [InlineKeyboardButton(text="🔄 Перевірити підписку", callback_data="check_sub")]
])

KB_MAIN_START = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🚀 Почати тест", callback_data="back_to_main_menu"),
        InlineKeyboardButton(text="🧠 NetaGPT", callback_data="start_ai_tutor")
    ],
    [
        InlineKeyboardButton(text="👤 Профіль", callback_data="refresh_profile"),
        InlineKeyboardButton(text="❓ Інструкція", callback_data="show_help_guide")
    ],
    [
        InlineKeyboardButton(text="📩 Підтримка", url=f"https://t.me/{SUPPORT_BOT}")
    ]
])

KB_BACK_TO_START = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="⬅️ Назад до меню", callback_data="back_to_start_hub")]
])


# --- ДОПОМІЖНІ ФУНКЦІЇ ---
async def check_subscription(bot: Bot, user_id: int) -> bool:
    """Перевіряє підписку користувача на обов'язковий канал."""
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except TelegramForbiddenError:
        # Автоматично видаляємо заблокованого юзера з БД
        await purge_blocked_user(user_id)
        return False
    except Exception:
        return True


async def safe_send_message(bot: Bot, user_id: int, text: str, **kwargs) -> bool:
    """Безпечна відправка повідомлення з очищенням БД при блокуванні."""
    try:
        await bot.send_message(chat_id=user_id, text=text, **kwargs)
        return True
    except TelegramForbiddenError:
        await purge_blocked_user(user_id)
        return False
    except TelegramBadRequest as e:
        if "chat not found" in e.message.lower() or "user is deactivated" in e.message.lower():
            await purge_blocked_user(user_id)
        return False
    except Exception:
        return False


def build_welcome_text(first_name: str, is_premium: bool, daily_tests_left: int, ai_requests_left: int = 3) -> str:
    status = "Premium 💎" if is_premium else "Безкоштовний 🆓"
    limit = "∞" if is_premium else daily_tests_left
    ai_limit = "∞" if is_premium else ai_requests_left
    clean_name = html.escape(first_name or "Користувач")
    
    return (
        f"👋 <b>Вітаємо у тренажері НМТ, {clean_name}!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Твій статус: <b>{status}</b>\n"
        f"⏳ Тестів на сьогодні: <b>{limit}</b>\n"
        f"🧠 Запитів до NetaGPT: <b>{ai_limit}</b>\n\n"
        f"📚 <b>ШВИДКА НАВІГАЦІЯ:</b>\n"
        f"• 🎯 <code>/quiz</code> — каталог тестів та зливів НМТ\n"
        f"• 🧠 <code>/ai</code> — NetaGPT (AI-тьютор з англійської)\n"
        f"• 👤 <code>/profile</code> — реферали, баланс та вивід Stars\n"
        f"• ❓ <code>/help</code> — довідка та правила системи\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 Скористайся меню нижче для миттєвого старту:"
    )


def build_help_text() -> str:
    return (
        "❓ <b>ДОВІДКА ТА ПРАВИЛА ПЛАТФОРМИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎯 <b>Як проходити тести?</b>\n"
        "Натисни <u>🚀 Почати тест</u> або введи команду /quiz. Обери категорію та запускай тренажер.\n\n"
        "🧠 <b>Що таке NetaGPT (/ai)?</b>\n"
        "Це твій особистий штучний інтелект від Neta School, який пояснить будь-яке граматичне правило за 5 секунд!\n\n"
        "🆓 <b>Безкоштовний тариф:</b>\n"
        "Тобі доступно <b>3 безкоштовні тести</b> та <b>3 запити до AI</b> на добу.\n\n"
        "👥 <b>Реферальна система:</b>\n"
        "У вкладці <u>👤 Профіль</u> копіюй своє унікальне посилання. "
        "Коли твій реферал купує Premium доступ, на твій баланс нараховується <b>100 ⭐ (Telegram Stars)</b>!\n\n"
        "💎 <b>Що дає Premium допуск?</b>\n"
        "Повний безліміт на тести 24/7 та розширені AI-пояснення помилок.\n"
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

    # 2. РЕФЕРАЛЬНА СИСТЕМА + ЗАХИСТ ВІД НАКРУТКИ
    if args and args.isdigit():
        referrer_id = int(args)
        
        if referrer_id != user_id and not user.get("referred_by"):
            # 2.1 Перевіряємо вето-список used_referrals (чи цей tg_id вже фігурував раніше)
            used_ref = supabase.table("used_referrals").select("user_id").eq("user_id", user_id).execute()
            
            if not used_ref.data:
                # 2.2 Перевіряємо існування реферера
                ref_check = supabase.table("users").select("referral_count").eq("id", referrer_id).execute()
                
                if ref_check.data:
                    # Прив'язуємо реферера до нового юзера
                    supabase.table("users").update({"referred_by": referrer_id}).eq("id", user_id).execute()
                    user["referred_by"] = referrer_id
                    
                    # Заносимо юзера у veto-список used_referrals назавжди
                    supabase.table("used_referrals").insert({"user_id": user_id}).execute()
                    
                    # Збільшуємо лічильник реферера
                    current_ref_count = ref_check.data[0].get("referral_count", 0) or 0
                    supabase.table("users").update({
                        "referral_count": current_ref_count + 1
                    }).eq("id", referrer_id).execute()
                    
                    # Надсилаємо сповіщення
                    await safe_send_message(
                        bot,
                        referrer_id,
                        "👤 <b>За твоїм посиланням зареєструвався новий учень!</b>\nКоли він придбає Premium, ти отримаєш 100 Stars ⭐",
                        parse_mode="HTML"
                    )

    # 3. Перевірка підписки
    if not await check_subscription(bot, user_id):
        await message.answer(
            "⚠️ <b>Доступ обмежено!</b>\n\n"
            "Щоб зберегти твій прогрес навчання, накопичені бали та відкрити безкоштовні тести, будь ласка, підпишись на наш офіційний канал.", 
            reply_markup=KB_SUBSCRIBE,
            parse_mode="HTML"
        )
        return

    welcome_text = build_welcome_text(
        first_name=user.get('first_name', 'Користувач'),
        is_premium=user.get('is_premium', False),
        daily_tests_left=user.get('daily_tests_left', 0),
        ai_requests_left=user.get('ai_requests_left', 3)
    )
    await message.answer(welcome_text, reply_markup=KB_MAIN_START, parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("⚠️ Будь ласка, підпишись на канал, щоб отримати доступ до довідки.", reply_markup=KB_SUBSCRIBE)
        return
    await message.answer(build_help_text(), reply_markup=KB_BACK_TO_START, parse_mode="HTML")


# ---------------------------
# CALLBACK HANDLERS
# ---------------------------
@router.callback_query(F.data == "check_sub")
async def check_sub(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    
    if await check_subscription(bot, user_id):
        try:
            await callback.message.delete()
        except Exception:
            pass
            
        user = await get_or_create_user(user_id, callback.from_user.username, callback.from_user.first_name)
        welcome_text = build_welcome_text(
            first_name=user.get('first_name', 'Користувач'),
            is_premium=user.get('is_premium', False),
            daily_tests_left=user.get('daily_tests_left', 0),
            ai_requests_left=user.get('ai_requests_left', 3)
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
    user_id = callback.from_user.id
    
    res = supabase.table("users") \
        .select("first_name", "is_premium", "daily_tests_left", "ai_requests_left") \
        .eq("id", user_id) \
        .execute()
    
    if not res.data:
        # Якщо запис був видалений під час блокування — створюємо новий
        user = await get_or_create_user(user_id, callback.from_user.username, callback.from_user.first_name)
    else:
        user = res.data[0]
        
    welcome_text = build_welcome_text(
        first_name=user.get('first_name', 'Користувач'),
        is_premium=user.get('is_premium', False),
        daily_tests_left=user.get('daily_tests_left', 0),
        ai_requests_left=user.get('ai_requests_left', 3)
    )
    
    await callback.message.edit_text(welcome_text, reply_markup=KB_MAIN_START, parse_mode="HTML")
    await callback.answer()
