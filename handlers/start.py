from aiogram import Router, Bot, F  
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery 
from aiogram.filters import CommandStart
from database.db_client import get_or_create_user, supabase
from config import CHANNEL_ID

router = Router()

# Пряме посилання на твій телеграм-канал
CHANNEL_LINK = "https://t.me/nedo_english"

async def check_subscription(bot: Bot, user_id: int) -> bool:
    """Перевіряє підписку на канал. Якщо користувач адмін/творець — пропускає автоматично."""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        # Якщо сталася помилка (наприклад, бота видалили з каналу або неправильний ID),
        # безпечніше пропустити користувача, щоб бот не «лежав» повністю.
        return True


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    # Реєструємо або отримуємо юзера з Supabase
    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    # Перевірка підписки
    if not await check_subscription(bot, message.from_user.id):
        # Створюємо зручну кнопку-посилання
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Підписатися на канал", url=CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Я підписався (Перевірити)", callback_data="check_sub_again")]
        ])
        
        await message.answer(
            "⚠️ Доступ обмежено!\n\n"
            "Щоб проходити унікальні авторські тести, бачити зливи НМТ та детальні розбори помилок, "
            "підпишись на наш канал.\n\n"
            "Після підписки натисни кнопку нижче або відправ /start ще раз 👇",
            reply_markup=kb
        )
        return

    # Головне вітання для підписаних користувачів
    status_text = "Premium (Безліміт) 💎" if user.get('is_premium') else "Безкоштовний 🆓"
    limits_text = "∞" if user.get('is_premium') else str(user.get('daily_tests_left', 0))

    await message.answer(
        f"👋 Вітаємо, {user['first_name']}, у тренажері від Neta School!\n\n"
        f"📊 Твій статус: {status_text}\n"
        f"Запросити друзів та подивитись свій профіль: /profile\n"
        f"⏳ Спроб на сьогодні: {limits_text}\n\n"
        "👉 Напиши команду /quiz, щоб відкрити меню тестів та обрати варіант!"
    )

# Додатковий обробник для кнопки "Я підписався"
@router.callback_query(F.data == "check_sub_again")
async def check_sub_callback(callback: CallbackQuery, bot: Bot):
    if await check_subscription(bot, callback.from_user.id):
        await callback.message.delete()
        # Якщо підписався, викликаємо стартове вітання
        await cmd_start(callback.message, bot)
    else:
        await callback.answer("❌ Ти все ще не підписався на канал! Будь ласка, підпишись.", show_alert=True)
