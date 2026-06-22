import csv
import io
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from config import ADMIN_ID
from database.db_client import supabase

router = Router()

class AdminStates(StatesGroup):
    waiting_for_broadcast_msg = State()

@router.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: Message):
    total_users = supabase.table("users").select("id", count="exact").execute().count
    premium_users = supabase.table("users").select("id", count="exact").eq("is_premium", True).execute().count
    total_tasks = supabase.table("tasks").select("id", count="exact").execute().count
    
    await message.answer(
        "⚙️ **Адмін-панель NetaNMT**\n\n"
        f"👥 Всього користувачів: `{total_users}`\n"
        f"💎 З них Premium: `{premium_users}`\n"
        f"📚 Тестів у базі: `{total_tasks}`\n\n"
        "📢 /broadcast — Надіслати сповіщення всім користувачам\n"
        "📥 Надішли мені `.csv` для завантаження нових тестів."
    )

# --- БЕЗПЕЧНА РОЗСИЛКА ---
@router.message(Command("broadcast"), F.from_user.id == ADMIN_ID)
async def start_broadcast(message: Message, state: FSMContext):
    await message.answer("📝 Введіть текст повідомлення для розсилки всім користувачам бота:")
    await state.set_state(AdminStates.waiting_for_broadcast_msg)

@router.message(AdminStates.waiting_for_broadcast_msg, F.from_user.id == ADMIN_ID)
async def do_broadcast(message: Message, bot: Bot, state: FSMContext):
    broadcast_text = message.text
    await state.clear()
    
    # Витягуємо тільки ID користувачів потоком (заощаджуємо оперативку)
    res = supabase.table("users").select("id").execute()
    user_ids = [u['id'] for u in res.data]
    
    status_msg = await message.answer(f"🚀 Розсилку розпочато для {len(user_ids)} користувачів...")
    
    success = 0
    blocked = 0
    
    for uid in user_ids:
        try:
            await bot.send_message(chat_id=uid, text=broadcast_text, parse_mode="Markdown")
            success += 1
        except Exception:
            # Сюди потрапляють ті, хто заблокував бота або видалив чат. Бот НЕ падає!
            blocked += 1
            
        # Захист від лімітів Telegram API (макс 30 повідомлень на секунду)
        # Робимо паузу кожні 25 повідомлень
        if (success + blocked) % 25 == 0:
            await asyncio.sleep(1)
            
    await status_msg.edit_text(
        "✅ **Розсилку завершено!**\n\n"
        f"📥 Успішно доставлено: `{success}`\n"
        f"❌ Заблокували бота: `{blocked}`"
    )

# --- ОБРОБНИК ЗАВАНТАЖЕННЯ CSV ---
@router.message(F.document, F.from_user.id == ADMIN_ID)
async def handle_csv_upload(message: Message):
    if not message.document.file_name.endswith('.csv'):
        await message.answer("❌ Будь ласка, надішли файл у форматі `.csv`")
        return

    file_info = await message.bot.get_file(message.document.file_id)
    file_content = await message.bot.download_file(file_info.file_path)
    
    csv_file = io.TextIOWrapper(file_content, encoding='utf-8')
    reader = csv.DictReader(csv_file)
    
    tasks_to_insert = []
    for row in reader:
        options_raw = row.get('options')

        if not options_raw:
            continue  # пропускає зламані рядки

        options_list = [opt.strip() for opt in options_raw.split(';')]
        tasks_to_insert.append({
            "category": row.get('category', 'author').strip(),
            "sub_category": row.get('sub_category', 'general').strip(),
            "section": row['section'].strip(),
            "question_text": row['question_text'].strip(),
            "options": options_list,
            "correct_answer": row['correct_answer'].strip(),
            "explanation": row['explanation'].strip()
        })
        
    if tasks_to_insert:
        supabase.table("tasks").insert(tasks_to_insert).execute()
        await message.answer(f"✅ Успішно завантажено тестів: {len(tasks_to_insert)} шт.")
