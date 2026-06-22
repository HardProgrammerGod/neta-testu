from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from database.db_client import get_or_create_user, supabase
from config import ADMIN_ID

router = Router()

@router.message(Command("profile"))
async def show_profile(message: Message, bot: Bot):
    user_id = message.from_user.id
    
    # Отримуємо свіжі дані користувача з бази
    user = await get_or_create_user(user_id, message.from_user.username, message.from_user.first_name)
    
    # s
    ref_link = f"https://t.me/netaNMT_bot?start={user_id}"
    
    status_text = "Premium 💎" if user.get('is_premium') else "Безкоштовний 🆓"
    
    profile_message = (
        "👤 **МІЙ ПРОФІЛЬ NetaNMT**\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"ℹ️ **Ім'я:** {user['first_name']}\n"
        f"📊 **Статус аккаунта:** `{status_text}`\n"
        f"📝 **Пройдено завдань:** `{user.get('total_tests_passed', 0)}` шт.\n\n"
        "👥 **Реферальна система:**\n"
        f"├ Запрошено друзів: `{user.get('referral_count', 0)}`\n"
        f"└ З них купили Premium: `{user.get('premium_referrals_count', 0)}` 💎\n\n"
        f"💰 **Баланс до виведення:** `{user.get('referral_balance', 0)} 🌟`\n\n"
        f"🔗 **Твоє реферальне посилання:**\n`{ref_link}`\n\n"
        "🎁 _Ділися посиланням з друзями! За кожну купівлю Premium твоїм рефералом ти отримуєш відсоток на баланс!_"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Вивести кошти / Задати питання", callback_data="withdraw_req")],
        [InlineKeyboardButton(text="🔄 Оновити профіль", callback_data="refresh_profile")]
    ])
    
    await message.answer(profile_message, parse_mode="Markdown", reply_markup=kb)

@router.callback_query(F.data == "refresh_profile")
async def refresh_profile_callback(callback: CallbackQuery, bot: Bot):
    await callback.message.delete()
    # Імітуємо команду текстового профілю, передаючи об'єкт повідомлення
    await show_profile(callback.message, bot)
    await callback.answer()

@router.callback_query(F.data == "withdraw_req")
async def withdraw_request(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    user_res = supabase.table("users").select("*").eq("id", user_id).execute()
    user = user_res.data[0]
    
    balance = user.get('referral_balance', 0)
    
    if balance <= 0:
        await callback.answer("❌ У тебе на балансі 0. Запрошуй друзів, які купують Premium, щоб заробити!", show_alert=True)
        return
        
    # Безпечне сповіщення адміна про заявку на виведення
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"💰 **ЗАЯВКА НА ВИВЕДЕННЯ КОШТІВ**\n\n"
                 f"👤 Користувач: {user['first_name']} (ID: `{user_id}`)\n"
                 f"Username: @{user['username'] if user['username'] else 'немає'}\n"
                 f"💸 Сума до виведення: `{balance}`"
        )
        await callback.message.answer("✅ **Заявку успішно надіслано адміну!** Очікуй, з тобою зв'яжуться найближчим часом.")
    except Exception:
        await callback.message.answer("⚠️ Помилка зв'язку з адміном. Спробуй написати в підтримку напряму.")
        
    await callback.answer()
