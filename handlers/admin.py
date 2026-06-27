import csv
import io
import html
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from config import ADMIN_ID
from database.db_client import supabase

router = Router()

# --- СТАНЫ АДМІНКИ ---
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()


# --- СТАТИЧНІ КЛАВІАТУРИ (Оптимізація RAM) ---
KB_ADMIN_MAIN = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="📊 Оновити статку", callback_data="admin_refresh"),
        InlineKeyboardButton(text="📢 Масова розсилка", callback_data="admin_broadcast")
    ],
    [
        InlineKeyboardButton(text="📎 Завантажити CSV-шаблон", callback_data="admin_download_template")
    ]
])


def build_admin_text(users_count: int, tasks_count: int) -> str:
    """Генерує красиву адмін-картку."""
    return (
        f"⚙️ <b>ПАГЕЛЬ КЕРУВАННЯ NetaNMT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Усього користувачів у системі: <b>{users_count}</b>\n"
        f"📚 Завантажено питань у базу: <b>{tasks_count}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 <b>Імпорт контенту:</b> Просто надішли мені <code>.csv</code> файл для пакетного завантаження нових тестів у Supabase."
    )


# --- ХЕНДЛЕРИ КОМАНД ТА КЛІКІВ ---

@router.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: Message, state: FSMContext):
    await state.clear()
    
    # Використовуємо head-запит (count="exact") без витягування самих рядків — нуль навантаження на мережу
    users = supabase.table("users").select("id", count="exact").execute().count or 0
    tasks = supabase.table("tasks").select("id", count="exact").execute().count or 0

    await message.answer(build_admin_text(users, tasks), reply_markup=KB_ADMIN_MAIN, parse_mode="HTML")


@router.callback_query(F.data == "admin_refresh", F.from_user.id == ADMIN_ID)
async def admin_refresh_stats(callback: CallbackQuery):
    """Швидке динамічне оновлення лічильників."""
    users = supabase.table("users").select("id", count="exact").execute().count or 0
    tasks = supabase.table("tasks").select("id", count="exact").execute().count or 0
    
    try:
        await callback.message.edit_text(build_admin_text(users, tasks), reply_markup=KB_ADMIN_MAIN, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("📊 Статистика оновлена!")


@router.callback_query(F.data == "admin_download_template", F.from_user.id == ADMIN_ID)
async def admin_download_template(callback: CallbackQuery):
    """Генерує та надсилає чистий правильний CSV шаблон, щоб адмін не помилявся зі стовпчиками."""
    output = io.StringIO()
    writer = csv.writer(output, delimiter=",")
    writer.writerow(["category", "sub_category", "section", "question_text", "options", "correct_answer", "explanation"])
    writer.writerow(["author", "leak_2025", "grammar", "Choose correct form: She ___ to school yesterday.", "go;goes;went;gone", "C", "Yesterday вказує на Past Simple, тому використовуємо went."])
    
    file_data = output.getvalue().encode('utf-8')
    output.close()
    
    input_file = io.BytesIO(file_data)
    input_file.name = "nmt_template.csv"
    
    from aiogram.types import BufferedInputFile
    buffered_file = BufferedInputFile(file_data, filename="nmt_template.csv")
    
    await callback.message.answer_document(buffered_file, caption="📋 <b>Шаблон для імпорту питань:</b>\nРозділювач варіантів відповідей (options) — крапка з комою (<b>;</b>).\nУ полі correct_answer вказуй літеру (A, B, C, D чи E).")
    await callback.answer()


# --- МОДУЛЬ МАСОВОЇ РОЗСИЛКИ (МАРКЕТИНГ/ПРОГРІВ) ---

@router.callback_query(F.data == "admin_broadcast", F.from_user.id == ADMIN_ID)
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_broadcast)
    kb_cancel = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_refresh")]])
    await callback.message.edit_text(
        "📢 <b>РЕЖИМ МАСОВОЇ РОЗСИЛКИ</b>\n\n"
        "Напиши повідомлення (підтримується HTML-розмітка), яке отримають <b>абсолютно всі</b> користувачі твого бота.\n"
        "<i>Будь обережний, дію не можна скасувати після відправки!</i>",
        parse_mode="HTML",
        reply_markup=kb_cancel
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast, F.from_user.id == ADMIN_ID)
async def process_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    broadcast_text = message.text
    await state.clear()
    
    # Витягуємо тільки ID активних юзерів
    res = supabase.table("users").select("id").execute()
    if not res.data:
        await message.answer("❌ У базі даних немає користувачів для розсилки.")
        return
        
    users = res.data
    status_msg = await message.answer(f"⏳ <b>Розсилка розпочата...</b>\nЗнайдено отримувачів: {len(users)}", parse_mode="HTML")
    
    success = 0
    blocked = 0
    
    for user in users:
        try:
            await bot.send_message(chat_id=user["id"], text=broadcast_text, parse_mode="HTML")
            success += 1
        except Exception:
            # Якщо користувач заблокував бота
            blocked += 1
            
        # Асинхронна пауза (таймаут) 0.05 сек, щоб Telegram не заблокував самого бота за флуд лімітами (макс 30 пов/сек)
        await asyncio.sleep(0.05)
        
    await status_msg.edit_text(
        f"🏁 <b>РОЗСИЛКА ЗАВЕРШЕНА!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Доставлено успішно: <b>{success}</b>\n"
        f"🚫 Заблокували бота: <b>{blocked}</b>"
    )


# --- ОБРОБКА ТА ІМПОРТ CSV ФАЙЛІВ ---

@router.message(F.document, F.from_user.id == ADMIN_ID)
async def upload_csv(message: Message):
    if not message.document.file_name.lower().endswith(".csv"):
        await message.answer("❌ Помилка: підтримуються тільки файли з розширенням <b>.csv</b>", parse_mode="HTML")
        return

    status_msg = await message.answer("⏳ <b>Читання та валідація файлу...</b>", parse_mode="HTML")

    try:
        file = await message.bot.get_file(message.document.file_id)
        content = await message.bot.download_file(file.file_path)
        
        # Декодуємо з безпечним ігноруванням помилок кодування
        csv_file = io.TextIOWrapper(content, encoding="utf-8", errors="ignore")
        reader = csv.DictReader(csv_file)
        
        tasks_chunk = []
        errors = 0
        total_uploaded = 0
        
        for row in reader:
            try:
                options_raw = row.get("options", "")
                question_text = row.get("question_text", "").strip()
                correct_ans = row.get("correct_answer", "").strip().upper()
                
                # Валідація критичних полів
                if not question_text or not correct_ans or not options_raw or ";" not in options_raw:
                    errors += 1
                    continue
                    
                options = [o.strip() for o in options_raw.split(";")]
                if len(options) < 2:
                    errors += 1
                    continue
                    
                tasks_chunk.append({
                    "category": row.get("category", "author").strip().lower(),
                    "sub_category": row.get("sub_category", "general").strip().lower(),
                    "section": row.get("section", "general").strip().lower(),
                    "question_text": question_text,
                    "options": options,
                    "correct_answer": correct_ans,
                    "explanation": row.get("explanation", "").strip()
                })
                
                # ОПТИМІЗАЦІЯ: Чанки по 100 елементів економлять оперативку без ризику вильоту OOM
                if len(tasks_chunk) >= 100:
                    supabase.table("tasks").insert(tasks_chunk).execute()
                    total_uploaded += len(tasks_chunk)
                    tasks_chunk.clear()
                    # Даємо серверу "вдихнути"
                    await asyncio.sleep(0.01)
                    
            except Exception:
                errors += 1
                continue
                
        # Завантажуємо залишок
        if tasks_chunk:
            supabase.table("tasks").insert(tasks_chunk).execute()
            total_uploaded += len(tasks_chunk)
            
        csv_file.close()
        content.close()
        
        await status_msg.edit_text(
            f"✅ <b>ІМПОРТ ЗАВЕРШЕНО!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📥 Успішно додано питань: <b>{total_uploaded}</b>\n"
            f"⚠️ Пропущено рядків з помилками: <b>{errors}</b>",
            parse_mode="HTML"
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Критична помилка обробки файлу:</b>\n<code>{html.escape(str(e))}</code>", parse_mode="HTML")
