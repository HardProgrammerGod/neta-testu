import csv
import io
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from config import ADMIN_ID
from database.db_client import supabase

router = Router()

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
        "📥 **Як завантажити нові тести:**\n"
        "Надішли мені `.csv` файл. Структура стовпців:\n"
        "`category,sub_category,section,question_text,options,correct_answer,explanation`\n\n"
        "💡 *Категорії:* `author`, `leak`, `mock`\n"
        "💡 *Підкатегорії:* наприклад, `17_june` або `general`"
    )

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
        options_list = [opt.strip() for opt in row['options'].split(';')]
        
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
    else:
        await message.answer("❌ Файл порожній або структура невірна.")
