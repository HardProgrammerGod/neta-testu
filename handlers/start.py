import html
from aiogram import Router, Bot, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, CommandObject
from database.db_client import get_or_create_user, supabase
from config import CHANNEL_ID

router = Router()

CHANNEL_LINK = "https://t.me/nedo_english"


async def check_subscription(bot: Bot, user_id: int) -> bool:
    """Перевіряє підписку користувача на обов'язковий канал."""
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        # Якщо сталася помилка (наприклад, бот не адмін у каналі), пропускаємо користувача
        return True


async def send_welcome(message: Message, user: dict):
    """Надсилає красиве вітальне повідомлення."""
    status = "Premium 💎" if user.get("is_premium") else "Безкоштовний 🆓"
    limit = "∞" if user.get("is_premium") else user.get("daily_tests_left", 0)
    
    # Захист від збою HTML-розмітки через специфічні нікнейми
    clean_name = html.escape(user.get('first_name') or "Користувач")

    await message.answer(
        f"👋 <b>Привіт, {clean_name}!</b>\n\n"
        f"📊 Твій статус: <b>{status}</b>\n"
        f"⏳ Доступно тестів на сьогодні: <b>{limit}</b>\n\n"
        f"🎯 Швидше переходь до завдань та перевір свої знання!\n"
        f"👉 Напиши /quiz, щоб почати тест.",
        parse_mode="HTML"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, command: CommandObject):
    user_id = message.from_user.id
    args = command.args  # Витягуємо параметри з посилання (наприклад, ?start=12345)

    # 1. Спершу отримуємо або створюємо користувача в локальній сесії
    user = await get_or_create_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name
    )

    # 2. РЕФЕРАЛЬНА ЛОГІКА ДЛЯ НОВИХ КОРИСТУВАЧІВ
    # Зв'язуємо реферала тільки якщо у користувача ще НЕМАЄ реферера (referred_by IS NULL)
    if args and args.isdigit() and not user.get("referred_by"):
        referrer_id = int(args)
        
        # Перевірка безпеки: не можна запросити самого себе
        if referrer_id != user_id:
            # Перевіряємо, чи існує реферер у базі даних
            ref_check = supabase.table("users").select("referral_count").eq("id", referrer_id).execute()
            
            if ref_check.data:
                # Оновлюємо дані поточного користувача: записуємо хто його запросив
                supabase.table("users").update({"referred_by": referrer_id}).eq("id", user_id).execute()
                user["referred_by"] = referrer_id  # Синхронізуємо локальний об'єкт
                
                # Інкрементуємо (referral_count + 1) рефереру в один швидкий крок
                current_ref_count = ref_check.data[0].get("referral_count", 0) or 0
                supabase.table("users").update({
                    "referral_count": current_ref_count + 1
                }).eq("id", referrer_id).execute()
                
                # Надсилаємо сповіщення рефереру про успішну реєстрацію друга
                try:
                    await bot.send_message(
                        chat_id=referrer_id,
                        text=f"👤 За твоїм посиланням зареєструвався новий користувач! Коли він придбає Premium, ти отримаєш зірки ⭐"
                    )
                except Exception:
                    pass

    # 3. ПЕРЕВІРКА ОБОВ'ЯЗКОВОЇ ПІДПИСКИ
    if not await check_subscription(bot, user_id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Підписатися на канал", url=CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Перевірити підписку", callback_data="check_sub")]
        ])

        await message.answer(
            "⚠️ <b>Доступ обмежено!</b>\n\n"
            "Для використання безкоштовного тренажера НМТ та збереження прогресу, будь ласка, підпишись на наш офіційний канал.", 
            reply_markup=kb,
            parse_mode="HTML"
        )
        return

    # Якщо підписка є — показуємо головне вітальне вікно
    await send_welcome(message, user)


@router.callback_query(F.data == "check_sub")
async def check_sub(callback: CallbackQuery, bot: Bot):
    if await check_subscription(bot, callback.from_user.id):
        # Видаляємо старе повідомлення-попередження, щоб не забивати чат
        try:
            await callback.message.delete()
        except Exception:
            pass
            
        # Імітуємо виклик команди /start, передаючи порожній CommandObject, щоб не дублювати логіку
        # Користувач уже створений у базі, тому рефералка повторно не спрацює — це безпечно
        from aiogram.filters import CommandObject
        fake_command = CommandObject(prefix="/", command="start", args=None)
        await cmd_start(callback.message, bot, fake_command)
    else:
        await callback.answer("❌ Ти ще не підписався на канал. Спробуй ще раз!", show_alert=True)
