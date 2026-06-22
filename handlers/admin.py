import csv
import io
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command
from config import ADMIN_ID
from database.db_client import supabase

router = Router()


@router.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: Message):
    users = supabase.table("users").select("id", count="exact").execute().count
    tasks = supabase.table("tasks").select("id", count="exact").execute().count

    await message.answer(
        f"⚙️ Admin\n👥 {users}\n📚 {tasks}\n\n📥 CSV upload ready"
    )


@router.message(F.document, F.from_user.id == ADMIN_ID)
async def upload_csv(message: Message):
    if not message.document.file_name.endswith(".csv"):
        await message.answer("❌ Тільки CSV")
        return

    file = await message.bot.get_file(message.document.file_id)
    content = await message.bot.download_file(file.file_path)

    csv_file = io.TextIOWrapper(content, encoding="utf-8")
    reader = csv.DictReader(csv_file)

    tasks = []
    errors = 0

    for i, row in enumerate(reader):

        try:
            options_raw = row.get("options", "")

            if not options_raw or ";" not in options_raw:
                errors += 1
                continue

            options = [o.strip() for o in options_raw.split(";")]

            if len(options) < 2:
                errors += 1
                continue

            tasks.append({
                "category": row.get("category", "author"),
                "sub_category": row.get("sub_category", "general"),
                "section": row.get("section", "general"),
                "question_text": row.get("question_text", ""),
                "options": options,
                "correct_answer": row.get("correct_answer", ""),
                "explanation": row.get("explanation", "")
            })

        except:
            errors += 1
            continue

        if len(tasks) >= 500:
            break

    if tasks:
        supabase.table("tasks").insert(tasks).execute()

    await message.answer(
        f"✅ Завантажено: {len(tasks)}\n❌ Помилки: {errors}"
    )
