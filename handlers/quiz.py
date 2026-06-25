from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database.db_client import get_or_create_user, decrease_test_limit, save_attempt, supabase
from handlers.start import check_subscription

router = Router()

class QuizSession(StatesGroup):
    in_progress = State()


# 1. Головне меню вибору категорії
@router.message(F.text == "/quiz")
async def start_quiz_menu(message: Message, bot: Bot, state: FSMContext):
    await state.clear()  # Очищуємо старі сесії перед стартом нового тесту
    
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("❌ Будь ласка, спочатку підпишись на наш канал!")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Авторські тести", callback_data="viewcat_author")],
        [InlineKeyboardButton(text="🔥 Зливи НМТ", callback_data="viewcat_leak")],
        [InlineKeyboardButton(text="📝 Пробні варіанти", callback_data="viewcat_mock")]
    ])
    await message.answer("🎯 Вибери категорію тестування:", reply_markup=kb)


# 2. Динамічне підменю тестів
@router.callback_query(F.data.startswith("viewcat_"))
async def show_subcategories(callback: CallbackQuery):
    category = callback.data.split("_")[1]
    
    res = supabase.table("tasks").select("sub_category").eq("category", category).execute()
    
    if not res.data:
        await callback.message.edit_text("📝 У цій категорії ще немає завантажених тестів. Адмін скоро додасть їх!")
        return
    
    sub_categories = sorted(list(set(item['sub_category'] for item in res.data)))
    
    buttons = []
    for sub in sub_categories:
        display_name = sub.replace("_", " ").capitalize()
        buttons.append([InlineKeyboardButton(text=display_name, callback_data=f"startset_{category}_{sub}")])
        
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text("📅 Вибери конкретний варіант/тест із бази:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "back_to_main_menu")
async def back_to_main(callback: CallbackQuery, bot: Bot, state: FSMContext):
    try:
        await callback.message.delete()
    except Exception:
        pass
    await start_quiz_menu(callback.message, bot, state)
    await callback.answer()


# 3. Ініціалізація та старт обраного тесту (ОПТИМІЗОВАНО)
@router.callback_query(F.data.startswith("startset_"))
async def start_specific_test(callback: CallbackQuery, bot: Bot, state: FSMContext):
    user = await get_or_create_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    
    if not user["is_premium"] and user["daily_tests_left"] <= 0:
        prices = [LabeledPrice(label="Premium допуск (250 Stars)", amount=250)]
        await bot.send_invoice(
            chat_id=callback.message.chat.id,
            title="💎 Активація Premium доступу",
            description="Отримай повний безліміт на тести, унікальні авторські завдання та розбори помилок за 250 Telegram Stars!",
            payload="premium_sub",
            provider_token="",
            currency="XTR",
            prices=prices
        )
        await callback.answer()
        return

    _, category, sub_category = callback.data.split("_")
    
    # Забираємо ОДНИМ запитом усі завдання цього варіанту
    res = supabase.table("tasks")\
        .select("*")\
        .eq("category", category)\
        .eq("sub_category", sub_category)\
        .order("id")\
        .execute()
    
    if not res.data:
        await callback.message.answer("❌ Сталася помилка завантаження структури тесту або варіант порожній.")
        await callback.answer()
        return
        
    all_tasks = res.data
    
    if not user["is_premium"]:
        await decrease_test_limit(callback.from_user.id, user["daily_tests_left"])
        
    # Зберігаємо всі завдання в пам'ять FSM кешу
    await state.update_data(
        tasks=all_tasks,
        current_index=0,
        correct_count=0,
        category=category,
        sub_category=sub_category
    )
    await state.set_state(QuizSession.in_progress)
    
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Передаємо перший об'єкт таски безпосередньо з локального масиву
    await send_next_question_ui(callback.message, all_tasks[0], 0, len(all_tasks), edit=False)
    await callback.answer()


async def send_next_question_ui(message: Message, task: dict, index: int, total: int, edit: bool = False):
    """Генерує інтерфейс питання. Працює локально, не навантажує мережу."""
    buttons = []
    for opt in task["options"]:
        buttons.append([InlineKeyboardButton(text=opt, callback_data=f"select_{opt[0]}")])
        
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    text = (
        f"📝 **Завдання {index + 1} з {total}**\n"
        f"Розділ: #{task['section']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{task['question_text']}"
    )
    
    if edit:
        await message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)


# 4. Обробка відповіді (ОПТИМІЗОВАНО)
@router.callback_query(QuizSession.in_progress, F.data.startswith("select_"))
async def handle_session_answer(callback: CallbackQuery, state: FSMContext):
    selected = callback.data.split("_")[1]
    
    session_data = await state.get_data()
    tasks = session_data.get("tasks", [])
    current_index = session_data.get("current_index", 0)
    correct_count = session_data.get("correct_count", 0)
    
    if not tasks or current_index >= len(tasks):
        await state.clear()
        await callback.answer("❌ Сесія тестування застаріла.", show_alert=True)
        return
        
    task = tasks[current_index]
    user = await get_or_create_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    
    is_correct = (selected == task["correct_answer"])
    
    # Зберігаємо спробу в БД
    await save_attempt(callback.from_user.id, task["id"], selected, is_correct)
    
    # Оновлюємо загальний лічильник пройдених тестів користувача (+1)
    new_passed = user.get("total_tests_passed", 0) + 1
    supabase.table("users").update({"total_tests_passed": new_passed}).eq("id", callback.from_user.id).execute()
    
    if is_correct:
        correct_count += 1
        await state.update_data(correct_count=correct_count)
        result_text = "🎉 Правильно!"
    else:
        result_text = f"❌ Неправильно.\n\nПравильна відповідь: `{task['correct_answer']}`\n\n"
        if user["is_premium"]:
            if task.get("explanation"):
                result_text += f"💡 Пояснення:\n{task['explanation']}"
            else:
                result_text += "💡 Адмін ще не додав пояснення до цього завдання."
        else:
            result_text += "🔒 Пояснення цієї помилки доступне тільки для Premium користувачів."
            
    next_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Наступне питання ➡️", callback_data="session_next_step")]
    ])
    
    await callback.message.edit_text(
        f"{callback.message.text}\n\n📊 Твій вибір: *{selected}*\n\n{result_text}", 
        parse_mode="Markdown",
        reply_markup=next_kb
    )
    await callback.answer()


# 5. Крок вперед (Безпечний перехід)
@router.callback_query(QuizSession.in_progress, F.data == "session_next_step")
async def process_next_step_click(callback: CallbackQuery, state: FSMContext):
    session_data = await state.get_data()
    tasks = session_data.get("tasks", [])
    current_index = session_data.get("current_index", 0)
    
    next_index = current_index + 1
    await state.update_data(current_index=next_index)
    
    if next_index < len(tasks):
        # Оновлюємо повідомлення локальними даними з пам'яті
        await send_next_question_ui(callback.message, tasks[next_index], next_index, len(tasks), edit=True)
    else:
        correct_count = session_data.get("correct_count", 0)
        await state.clear()
        success_pct = int((correct_count / len(tasks)) * 100) if tasks else 0
        
        await callback.message.edit_text(
            f"🏁 ТЕСТ ЗАВЕРШЕНО!\n\n"
            f"📊 Твій підсумковий результат:\n"
            f"✅ Правильних відповідей: `{correct_count}` з `{len(tasks)}`\n"
            f"📈 Успішність: `{success_pct}%`\n\n"
            f"👉 Напиши /quiz, щоб відкрити каталог та спробувати інший тест!",
            parse_mode="Markdown"
        )
    await callback.answer()


# --- Системні хендлери оплати Stars ---
@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(F.successful_payment)
async def success_payment(message: Message, bot: Bot):
    user_id = message.from_user.id
    user_data = supabase.table("users").select("referred_by", "is_premium").eq("id", user_id).execute().data[0]
    
    if not user_data["is_premium"]:
        referrer_id = user_data.get("referred_by")
        if referrer_id:
            ref_user = supabase.table("users").select("premium_referrals_count", "referral_balance").eq("id", referrer_id).execute()
            if ref_user.data:
                new_premium_count = ref_user.data[0]["premium_referrals_count"] + 1
                new_balance = ref_user.data[0]["referral_balance"] + 100 
                
                supabase.table("users").update({
                    "premium_referrals_count": new_premium_count,
                    "referral_balance": new_balance
                }).eq("id", referrer_id).execute()
                
                try:
                    await bot.send_message(
                        chat_id=referrer_id,
                        text="💎 Твій реферал купив Premium!\nТобі нараховано бонус на баланс профілю. Перевір через /profile"
                    )
                except Exception:
                    pass

    supabase.table("users").update({"is_premium": True}).eq("id", user_id).execute()
    await message.answer("💎 Преміум активовано! Тобі відкрито безлімітний доступ до всіх тестів тренажера та авторських пояснень. Успішного навчання!")
