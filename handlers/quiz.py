import html
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database.db_client import get_or_create_user, decrease_test_limit, save_attempt, supabase
from handlers.start import check_subscription

router = Router()

class QuizSession(StatesGroup):
    in_progress = State()


# --- ФУНКЦІЯ СТВОРЕННЯ ПРОГРЕС-БАРУ (ВІЗУАЛ) ---
def generate_progress_bar(current_index: int, total: int) -> str:
    """Генерує красивий динамічний рядок прогресу іспиту."""
    # Довжина шкали — 10 символів
    bar_length = 10
    progress = int((current_index / total) * bar_length) if total > 0 else 0
    
    # 🟦 — пройдено, ⬜ — залишилось
    bar = "🟦" * progress + "⬜" * (bar_length - progress)
    return f"<code>{bar}</code> ({current_index}/{total})"


# 1. Головне меню вибору категорії
@router.message(F.text == "/quiz")
async def start_quiz_menu(message: Message, bot: Bot, state: FSMContext):
    await state.clear()  # Очищуємо старі сесії
    
    if not await check_subscription(bot, message.from_user.id):
        await message.answer("❌ Будь ласка, спочатку підпишись на наш канал!")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Авторські тести", callback_data="viewcat_author")],
        [InlineKeyboardButton(text="🔥 Зливи НМТ", callback_data="viewcat_leak")],
        [InlineKeyboardButton(text="📝 Пробні варіанти", callback_data="viewcat_mock")]
    ])
    await message.answer("🎯 <b>Вибери категорію тестування:</b>", reply_markup=kb, parse_mode="HTML")


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
    
    await callback.message.edit_text("📅 <b>Вибери конкретний варіант/тест із бази:</b>", reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "back_to_main_menu")
async def back_to_main(callback: CallbackQuery, bot: Bot, state: FSMContext):
    try:
        await callback.message.delete()
    except Exception:
        pass
    await start_quiz_menu(callback.message, bot, state)
    await callback.answer()


# 3. Ініціалізація та старт обраного тесту
@router.callback_query(F.data.startswith("startset_"))
async def start_specific_test(callback: CallbackQuery, bot: Bot, state: FSMContext):
    user = await get_or_create_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
    
    # ПЕРЕВІРКА ЛІМІТІВ (Маркетинговий прогрів на покупку Stars)
    if not user["is_premium"] and user["daily_tests_left"] <= 0:
        prices = [LabeledPrice(label="Premium допуск (250 Stars)", amount=250)]
        await bot.send_invoice(
            chat_id=callback.message.chat.id,
            title="💎 Активація Premium доступу",
            description="Закінчилися безкоштовні спроби! Отримай повний безліміт на тести, унікальні завдання та розбори помилок за 250 Telegram Stars!",
            payload="premium_sub",
            provider_token="",
            currency="XTR",
            prices=prices
        )
        await callback.answer()
        return

    _, category, sub_category = callback.data.split("_", maxsplit=2)
    
    # ОДИН запит до БД для економії пам'яті
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

    await send_next_question_ui(callback.message, all_tasks[0], 0, len(all_tasks), edit=False)
    await callback.answer()


async def send_next_question_ui(message: Message, task: dict, index: int, total: int, edit: bool = False):
    """Генерує інтерфейс питання. Додано динамічний PROGRESS BAR."""
    buttons = []
    for opt in task["options"]:
        buttons.append([InlineKeyboardButton(text=opt, callback_data=f"select_{opt[0]}")])
        
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    clean_question = html.escape(task['question_text'])
    clean_section = html.escape(task['section'].upper())
    
    progress_bar = generate_progress_bar(index + 1, total)
    
    text = (
        f"📝 <b>ЗАВДАННЯ {index + 1} з {total}</b>\n"
        f"Прогрес: {progress_bar}\n"
        f"Розділ: <code>#{clean_section}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{clean_question}"
    )
    
    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)


# 4. Обробка відповіді (МАРКЕТИНГОВИЙ ПРОГРІВ PREMIUM & FOMO)
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
    
    # Запис у БД
    await save_attempt(callback.from_user.id, task["id"], selected, is_correct)
    
    # Швидкий інкремент лічильника пройдених тестів
    new_passed = user.get("total_tests_passed", 0) + 1
    supabase.table("users").update({"total_tests_passed": new_passed}).eq("id", callback.from_user.id).execute()
    
    buttons = []
    
    if is_correct:
        correct_count += 1
        await state.update_data(correct_count=correct_count)
        result_text = "🎉 <b>Правильно! Чудова робота.</b>"
    else:
        result_text = f"❌ <b>Неправильно.</b>\n\nПравильна відповідь: <code>{html.escape(task['correct_answer'])}</code>\n\n"
        
        # --- МАРКЕТИНГОВИЙ ХІД (Байт на покупку преміуму) ---
        if user["is_premium"]:
            if task.get("explanation"):
                result_text += f"💡 <b>Пояснення помилки:</b>\n{html.escape(task['explanation'])}"
            else:
                result_text += "💡 Адмін ще не додав розгорнуте пояснення до цього завдання."
        else:
            # Якщо преміуму немає, показуємо обрізаний тизер пояснення (якщо воно є в базі)
            if task.get("explanation"):
                full_exp = task['explanation']
                # Беремо перші 45 символів як приманку
                teaser = full_exp[:45] + "..." if len(full_exp) > 45 else full_exp
                result_text += (
                    f"💡 <b>Пояснення помилки (Тизер):</b>\n<i>{html.escape(teaser)}</i>\n\n"
                    f"🔒 <b>Повний аналітика правила доступна лише Premium учням!</b> "
                    f"Не втрачай бали на реальному НМТ через прості правила."
                )
            else:
                result_text += "🔒 <b>Пояснення цієї помилки доступне тільки для Premium користувачів.</b>"
            
            # Додаємо кнопку покупки ПЕРШОЮ
            buttons.append([InlineKeyboardButton(text="💎 Відкрити пояснення (250 ⭐)", callback_data="quiz_buy_premium")])
            
    # Кнопка переходу
    buttons.append([InlineKeyboardButton(text="Наступне питання ➡️", callback_data="session_next_step")])
    next_kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # Екрануємо старе питання, щоб уникнути конфліктів HTML
    clean_old_text = html.escape(callback.message.text).split("━━━━━━━━━━━━━━━━━━━━")[1]
    progress_bar = generate_progress_bar(current_index + 1, len(tasks))

    await callback.message.edit_text(
        f"📝 <b>ПИТАННЯ {current_index + 1} ОПРАЦЬОВАНО</b>\n"
        f"Прогрес: {progress_bar}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
        f"{clean_old_text}\n\n"
        f"📊 Твій вибір: <b>{selected}</b>\n\n"
        f"{result_text}", 
        parse_mode="HTML",
        reply_markup=next_kb
    )
    await callback.answer()


@router.callback_query(QuizSession.in_progress, F.data == "quiz_buy_premium")
async def process_inline_buy_premium(callback: CallbackQuery, bot: Bot):
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


# 5. Крок вперед (Безпечний перехід)
@router.callback_query(QuizSession.in_progress, F.data == "session_next_step")
async def process_next_step_click(callback: CallbackQuery, state: FSMContext):
    session_data = await state.get_data()
    tasks = session_data.get("tasks", [])
    current_index = session_data.get("current_index", 0)
    
    next_index = current_index + 1
    await state.update_data(current_index=next_index)
    
    if next_index < len(tasks):
        await send_next_question_ui(callback.message, tasks[next_index], next_index, len(tasks), edit=True)
    else:
        correct_count = session_data.get("correct_count", 0)
        await state.clear()
        success_pct = int((correct_count / len(tasks)) * 100) if tasks else 0
        
        # Визначаємо фінальний вердикт за шкалою успішності
        if success_pct >= 90:
            rating = "🔥 Ідеальний результат! Ти повністю готовий до НМТ."
        elif success_pct >= 70:
            rating = "⚡️ Гарний результат, але є слабкі місця. Повтори правила!"
        else:
            rating = "⚠️ Треба підтягнути знання. Premium розбори допоможуть закрити прогалини."

        await callback.message.edit_text(
            f"🏁 <b>ТЕСТ ЗАВЕРШЕНО!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 <b>Твій підсумковий результат:</b>\n"
            f"✅ Правильних відповідей: <code>{correct_count}</code> з <code>{len(tasks)}</code>\n"
            f"📈 Успішність: <b><code>{success_pct}%</code></b>\n\n"
            f"📋 Вердикт: <i>{rating}</i>\n\n"
            f"👉 Напиши /quiz, щоб відкрити каталог та спробувати інший тест!",
            parse_mode="HTML"
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
