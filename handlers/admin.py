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
    # Використовуємо head-запит для точного і швидкого підрахунку кількості рядків
    users = supabase.table("users").select("id", count="exact").execute().count
    tasks = supabase.table("tasks").select("id", count="exact").execute().count

    await message.answer(
        f"⚙️ Admin Panel\n👥 Користувачі: {users}\n📚 Питання в базі: {tasks}\n\n📥 Надішли мені .csv файл для імпорту нових завдань."
    )


@router.message(F.document, F.from_user.id == ADMIN_ID)
async def upload_csv(message: Message):
    if not message.document.file_name.endswith(".csv"):
        await message.answer("❌ Помилка: підтримуються тільки файли з розширенням .csv")
        return

    file = await message.bot.get_file(message.document.file_id)
    content = await message.bot.download_file(file.file_path)

    csv_file = io.TextIOWrapper(content, encoding="utf-8")
    reader = csv.DictReader(csv_file)

    tasks_chunk = []
    errors = 0
    total_uploaded = 0

    for row in reader:
        try:
            options_raw = row.get("options", "")

            if not options_raw or ";" not in options_raw:
                errors += 1
                continue

            options = [o.strip() for o in options_raw.split(";")]

            if len(options) < 2:
                errors += 1
                continue

            tasks_chunk.append({
                "category": row.get("category", "author"),
                "sub_category": row.get("sub_category", "general"),
                "section": row.get("section", "general"),
                "question_text": row.get("question_text", ""),
                "options": options,
                "correct_answer": row.get("correct_answer", ""),
                "explanation": row.get("explanation", "")
            })

            # Пакетне завантаження пачками по 500 штук для економії пам'яті
            if len(tasks_chunk) >= 500:
                supabase.table("tasks").insert(tasks_chunk).execute()
                total_uploaded += len(tasks_chunk)
                tasks_chunk.clear()

        except Exception:
            errors += 1
            continue

    # Завантажуємо залишок, якщо він менший за 500 рядків
    if tasks_chunk:
        supabase.table("tasks").insert(tasks_chunk).execute()
        total_uploaded += len(tasks_chunk)

    await message.answer(
        f"✅ Успішно імпортовано питань: {total_uploaded}\n❌ Рядочків з помилками: {errors}"
    )
