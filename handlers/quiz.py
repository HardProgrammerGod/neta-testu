from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from database.db_client import get_or_create_user, get_random_task, decrease_test_limit, save_attempt
from handlers.start import check_subscription

router = Router()

@router.message(F.text == "/quiz")
async def start_quiz(message: Message, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("❌ Будь ласка, спочатку підпишись на наш канал!")
        return

    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    # Перевірка лімітів та виставлення рахунку в Telegram Stars (валюта XTR)
    if not user["is_premium"] and user["daily_tests_left"] <= 0:
        prices = [LabeledPrice(label="Premium 30 днів", amount=100)] # 50 Stars
        await bot.send_invoice(
            chat_id=message.chat.id,
            title="💎 Перехід на Premium допуск",
            description="У тебе закінчились безкоштовні спроби на сьогодні! Отримай повний безліміт на місяць всього за 50 Telegram Stars.",
            payload="premium_sub",
            provider_token="", # Для Telegram Stars залишаємо ПУСТИМ
            currency="XTR",
            prices=prices
        )
        return

    task = await get_random_task()
    if not task:
        await message.answer("📝 База тестів зараз оновлюється адміном. Спробуй через кілька хвилин!")
        return

    if not user["is_premium"]:
        await decrease_test_limit(message.from_user.id, user["daily_tests_left"])

    buttons = []
    for opt in task["options"]:
        # Безпечно передаємо ID та відповідь користувача у callback_data
        buttons.append([InlineKeyboardButton(text=opt, callback_data=f"ans_{task['id']}_{opt[0]}")])
        
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(f"❓ **Завдання:**\n\n{task['question_text']}", reply_markup=kb)

@router.callback_query(F.data.startswith("ans_"))
async def handle_answer(callback: CallbackQuery):
    _, task_id, selected = callback.data.split("_")
    
    from database.db_client import supabase
    task = supabase.table("tasks").select("*").eq("id", int(task_id)).execute().data[0]
    
    is_correct = (selected == task["correct_answer"])
    await save_attempt(callback.from_user.id, int(task_id), selected, is_correct)
    
    if is_correct:
        text = "🎉 **Правильно! +1 бал**"
    else:
        text = (
            f"❌ **Неправильно.**\n\n"
            f"Правильна відповідь: `{task['correct_answer']}`\n\n"
            f"💡 **Пояснення:**\n{task['explanation']}"
        )
        
    # Захист: додаємо кнопку для наступного квізу відразу
    next_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Наступне питання ➡️", callback_data="next_quiz")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=next_kb)
    await callback.answer()

@router.callback_query(F.data == "next_quiz")
async def next_quiz_trigger(callback: CallbackQuery, bot: Bot):
    await callback.message.delete()
    # Імітуємо команду /quiz для виклику наступного завдання
    await start_quiz(callback.message, bot)
    await callback.answer()

# Процес оплати Зірок
@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def success_payment(message: Message):
    from database.db_client import supabase
    supabase.table("users").update({"is_premium": True}).eq("id", message.from_user.id).execute()
    await message.answer("💎 **Преміум активовано!** Тобі відкрито безлімітний доступ до всіх тестів тренажера. Успішного навчання!")
