from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database.db_client import get_or_create_user, decrease_test_limit, save_attempt, supabase
from handlers.start import check_subscription

router = Router()

# Стейт для збереження ходу тестування
class QuizSession(StatesGroup):
    in_progress = State()


# 1. Головне меню вибору категорії
@router.message(F.text == "/quiz")
async def start_quiz_menu(message: Message, bot: Bot, state: FSMContext):
    await state.clear() # Скидаємо старі сесії, якщо вони були
    
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("❌ Будь ласка, спочатку підпишись на наш канал!")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Авторські тести", callback_data="viewcat_author")],
        [InlineKeyboardButton(text="🔥 Зливи НМТ", callback_data="viewcat_leak")],
        [InlineKeyboardButton(text="📝 Пробні варіанти", callback_data="viewcat_mock")]
    ])
    await message.answer("🎯 **Вибери категорію тестування:**", reply_markup=kb)


# 2. Динамічне підменю доступних тестів із бази даних
@router.callback_query(F.data.startswith("viewcat_"))
async def show_subcategories(callback: CallbackQuery):
    category = callback.data.split("_")[1]
    
    # Робимо швидкий SELECT DISTINCT (групування) в Supabase, щоб знайти унікальні підкатегорії
    # Зі списку завдань витягуються унікальні назви на кшталт "17_june", "mock_1" тощо.
    res = supabase.table("tasks").select("sub_category").eq("category", category).execute()
    
    if not res.data:
        await callback.message.edit_text("📝 У цій категорії ще немає завантажених тестів. Адмін скоро додасть їх!")
        return
    
    # Очищаємо дублікати підкатегорій в Python
    sub_categories = sorted(list(set(item['sub_category'] for item in res.data)))
    
    buttons = []
    for sub in sub_categories:
        # Красиво форматуємо назву для кнопки (наприклад, "17_june" -> "17 june")
        display_name = sub.replace("_", " ").capitalize()
        buttons.append([InlineKeyboardButton(text=display_name, callback_data=f"startset_{category}_{sub}")])
        
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text("📅 **Вибери конкретний варіант/тест із бази:**", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "back_to_main_menu")
async def back_to_main(callback: CallbackQuery, bot: Bot, state: FSMContext):
    await callback.message.delete()
    await start_quiz_menu(callback.message, bot, state)
    await callback.answer()


# 3. Ініціалізація та старт обраного тесту
@router.callback_query(F.data.startswith("startset_"))
async def start_specific_test(callback: CallbackQuery, bot: Bot, state: FSMContext):
    user = await get_or_create_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    
    # Перевірка щоденних лімітів для безкоштовних користувачів
    if not user["is_premium"] and user["daily_tests_left"] <= 0:
        prices = [LabeledPrice(label="Premium допуск (500 Stars)", amount=500)] # 250 Stars
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
    
    # Витягуємо ТІЛЬКИ ID завдань для цього тесту. Сортуємо по ID, щоб вони йшли по черзі
    res = supabase.table("tasks").select("id").eq("category", category).eq("sub_category", sub_category).order("id").execute()
    
    if not res.data:
        await callback.message.answer("❌ Сталася помилка завантаження структури тесту.")
        await callback.answer()
        return
        
    task_ids = [item['id'] for item in res.data]
    
    if not user["is_premium"]:
        await decrease_test_limit(callback.from_user.id, user["daily_tests_left"])
        
    # Зберігаємо в пам'ять тільки ID-шники (це займає мізерні байти)
    await state.update_data(
        task_ids=task_ids,
        current_index=0,
        correct_count=0,
        category=category,
        sub_category=sub_category
    )
    await state.set_state(QuizSession.in_progress)
    
    # Завантажуємо та показуємо перше питання
    await send_next_question_ui(callback.message, task_ids[0], 0, len(task_ids))
    await callback.answer()


async def send_next_question_ui(message: Message, task_id: int, index: int, total: int):
    """Швидко дістає одне питання з БД по ID та рендерить кнопки."""
    res = supabase.table("tasks").select("*").eq("id", task_id).execute()
    task = res.data[0]
    
    buttons = []
    for opt in task["options"]:
        # Передаємо тільки індекс відповіді, щоб не перевищити ліміт у 64 байти в callback_data
        buttons.append([InlineKeyboardButton(text=opt, callback_data=f"select_{opt[0]}")])
        
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        f"📝 **Завдання {index + 1} з {total}**\n"
        f"Розділ: #{task['section']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{task['question_text']}",
        reply_markup=kb
    )


# 4. Обробка відповіді користувача всередині активної сесії
@router.callback_query(QuizSession.in_progress, F.data.startswith("select_"))
async def handle_session_answer(callback: CallbackQuery, state: FSMContext):
    selected = callback.data.split("_")[1]
    
    # Отримуємо дані поточного тесту з FSM
    session_data = await state.get_data()
    task_ids = session_data["task_ids"]
    current_index = session_data["current_index"]
    correct_count = session_data["correct_count"]
    
    current_task_id = task_ids[current_index]
    
    # Беремо дані питання з бази
    task = supabase.table("tasks").select("*").eq("id", current_task_id).execute().data[0]
    user = await get_or_create_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    
    is_correct = (selected == task["correct_answer"])
    await save_attempt(callback.from_user.id, current_task_id, selected, is_correct)
    
    if is_correct:
        correct_count += 1
        await state.update_data(correct_count=correct_count)
        result_text = "🎉 **Правильно!**"
    else:
        result_text = f"❌ **Неправильно.**\n\nПравильна відповідь: `{task['correct_answer']}`\n\n"
        # 🔒 Перевірка преміуму на показ пояснення
        if user["is_premium"]:
            if task.get("explanation"):
                result_text += f"💡 **Пояснення:**\n{task['explanation']}"
            else:
                result_text += "💡 *Адмін ще не додав пояснення до цього завдання.*"
        else:
            result_text += "🔒 *Пояснення цієї помилки доступне тільки для Premium користувачів.*"
            
    # Прибираємо інтерактивні кнопки, щоб зафіксувати вибір
    await callback.message.edit_text(
        f"{callback.message.text}\n\n📊 Твій вибір: *{selected}*\n\n{result_text}", 
        parse_mode="Markdown"
    )
    await callback.answer()
    
    # Розрахунок наступного кроку
    next_index = current_index + 1
    await state.update_data(current_index=next_index)
    
    if next_index < len(task_ids):
        # Якщо є наступне питання — виводимо його
        await send_next_question_ui(callback.message, task_ids[next_index], next_index, len(task_ids))
    else:
        # Тест завершено
        await state.clear()
        success_pct = int((correct_count / len(task_ids)) * 100)
        
        await callback.message.answer(
            f"🏁 **ТЕСТ ЗАВЕРШЕНО!**\n\n"
            f"📊 Твій підсумковий результат:\n"
            f"✅ Правильних відповідей: `{correct_count}` з `{len(task_ids)}`\n"
            f"📈 Успішність: `{success_pct}%`\n\n"
            f"👉 Напиши /quiz, щоб відкрити каталог та спробувати інший тест!"
        )


# --- Стандартна логіка оплати 250 Telegram Stars (XTR) ---
@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def success_payment(message: Message):
    supabase.table("users").update({"is_premium": True}).eq("id", message.from_user.id).execute()
    await message.answer("💎 **Преміум активовано за 250 Stars!** Тобі відкрито безліміт на всі тести та повні пояснення до помилок. Успіху на НМТ!")
