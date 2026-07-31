import csv
import io
import html
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter, TelegramForbiddenError
from config import ADMIN_ID
from database.db_client import supabase
from services.cleaner import audit_and_purge_blocked_users

router = Router()

# --- СТАНИ АДМІНКИ ---
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()


# --- СТАТИЧНІ КЛАВІАТУРИ ---
KB_ADMIN_MAIN = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="📊 Оновити статку", callback_data="admin_refresh"),
        InlineKeyboardButton(text="📢 Масова розсилка", callback_data="admin_broadcast")
    ],
    [
        InlineKeyboardButton(text="🧹 Очистити мертвих юзерів", callback_data="admin_cleanup_db"),
        InlineKeyboardButton(text="📎 Завантажити CSV-шаблон", callback_data="admin_download_template")
    ]
])


def build_admin_text(total_users: int, active_users: int, tasks_count: int) -> str:
    """Генерує адмін-панель."""
    blocked_users = total_users - active_users
    return (
        f"⚙️ <b>ПАНЕЛЬ КЕРУВАННЯ NetaNMT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Усього користувачів у системі: <b>{total_users}</b>\n"
        f"✅ Активні: <b>{active_users}</b>\n"
        f"🚫 Заблокували бота: <b>{blocked_users}</b>\n"
        f"📚 Завантажено питань у базу: <b>{tasks_count}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📥 <b>Імпорт контенту:</b> Надішли <code>.csv</code> файл для завантаження нових тестів."
    )


async def get_stats_safely():
    """Безпечний підрахунок аналітики без завантаження об'єктів у RAM."""
    def _db_op():
        total = supabase.table("users").select("id", count="exact").execute().count or 0
        active = supabase.table("users").select("id", count="exact").eq("is_active", True).execute().count or 0
        tasks = supabase.table("tasks").select("id", count="exact").execute().count or 0
        return total, active, tasks

    return await asyncio.to_thread(_db_op)


# --- ХЕНДЛЕРИ КОМАНД ТА КЛІКІВ ---

@router.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: Message, state: FSMContext):
    await state.clear()
    total, active, tasks = await get_stats_safely()
    await message.answer(build_admin_text(total, active, tasks), reply_markup=KB_ADMIN_MAIN, parse_mode="HTML")


@router.callback_query(F.data == "admin_refresh", F.from_user.id == ADMIN_ID)
async def admin_refresh_stats(callback: CallbackQuery):
    total, active, tasks = await get_stats_safely()
    try:
        await callback.message.edit_text(build_admin_text(total, active, tasks), reply_markup=KB_ADMIN_MAIN, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("📊 Статистика оновлена!")


# --- МАСОВА РОЗСИЛКА ---

@router.callback_query(F.data == "admin_broadcast", F.from_user.id == ADMIN_ID)
async def start_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_broadcast)
    kb_cancel = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_refresh")]])
    await callback.message.edit_text(
        "📢 <b>РЕЖИМ МАСОВОЇ РОЗСИЛКИ</b>\n\n"
        "Повідомлення буде надіслано тільки <b>активним</b> користувачам.\n"
        "Заблоковані профілі автоматично змінять статус на 'неактивний'.",
        parse_mode="HTML",
        reply_markup=kb_cancel
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast, F.from_user.id == ADMIN_ID)
async def process_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    broadcast_text = message.text
    await state.clear()

    total, active, _ = await get_stats_safely()
    if active == 0:
        await message.answer("❌ У базі даних немає активних користувачів для розсилки.")
        return

    status_msg = await message.answer(f"⏳ <b>Розсилка розпочата...</b>\nЦільова аудиторія: ~{active} юзерів.", parse_mode="HTML")

    success = 0
    blocked_count = 0
    page_size = 500
    offset = 0

    while True:
        def _fetch_users():
            return supabase.table("users").select("id").eq("is_active", True).range(offset, offset + page_size - 1).execute().data or []

        users_chunk = await asyncio.to_thread(_fetch_users)
        if not users_chunk:
            break

        blocked_now = []

        for user in users_chunk:
            user_id = user["id"]
            try:
                await bot.send_message(chat_id=user_id, text=broadcast_text, parse_mode="HTML")
                success += 1
                await asyncio.sleep(0.04)  # Захист від флуд-ліміту (~25 повідомлень/сек)
            except TelegramForbiddenError:
                blocked_now.append(user_id)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                try:
                    await bot.send_message(chat_id=user_id, text=broadcast_text, parse_mode="HTML")
                    success += 1
                except Exception:
                    blocked_now.append(user_id)
            except TelegramAPIError:
                blocked_now.append(user_id)

            if len(blocked_now) >= 50:
                def _update_blocked(b_list):
                    supabase.table("users").update({"is_active": False}).in_("id", b_list).execute()

                await asyncio.to_thread(_update_blocked, list(blocked_now))
                blocked_count += len(blocked_now)
                blocked_now.clear()

        if blocked_now:
            def _update_blocked(b_list):
                supabase.table("users").update({"is_active": False}).in_("id", b_list).execute()

            await asyncio.to_thread(_update_blocked, list(blocked_now))
            blocked_count += len(blocked_now)

        offset += page_size

    await status_msg.edit_text(
        f"🏁 <b>РОЗСИЛКА ЗАВЕРШЕНА!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Успішно доставлено: <b>{success}</b>\n"
        f"🚫 Виявлено нових блокувань: <b>{blocked_count}</b>\n\n"
        f"<i>Статуси користувачів оновлено в БД.</i>",
        parse_mode="HTML"
    )


# --- ОЧИЩЕННЯ БАЗИ ---

@router.callback_query(F.data == "admin_cleanup_db", F.from_user.id == ADMIN_ID)
async def admin_cleanup_db(callback: CallbackQuery, bot: Bot):
    await callback.answer("⏳ Перевірка запущена...")
    status_msg = await callback.message.answer("🔄 <b>Сканування користувачів на наявність блокувань...</b>", parse_mode="HTML")
    
    purged = await audit_and_purge_blocked_users(bot)

    await status_msg.edit_text(
        f"🧹 <b>ОЧИЩЕННЯ ЗАВЕРШЕНО!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📉 Переведено в статус неактивних: <b>{purged}</b>\n\n"
        f"Тепер вони не враховуються в активній статистиці та розсилках!",
        parse_mode="HTML"
    )


# --- ШАБЛОН ТА ІМПОРТ CSV ---

@router.callback_query(F.data == "admin_download_template", F.from_user.id == ADMIN_ID)
async def admin_download_template(callback: CallbackQuery):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=",")
    writer.writerow(["category", "sub_category", "section", "question_text", "options", "correct_answer", "explanation"])
    writer.writerow(["author", "leak_2025", "grammar", "Choose correct form: She ___ to school yesterday.", "go;goes;went;gone", "C", "Yesterday вказує на Past Simple, тому використовуємо went."])

    file_data = output.getvalue().encode('utf-8')
    output.close()

    buffered_file = BufferedInputFile(file_data, filename="nmt_template.csv")

    await callback.message.answer_document(
        buffered_file,
        caption="📋 <b>Шаблон для імпорту питань:</b>\nРозділювач варіантів відповідей (options) — крапка з комою (<b>;</b>).\nУ полі correct_answer вказуй літеру (A, B, C, D чи E).",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(F.document, F.from_user.id == ADMIN_ID)
async def upload_csv(message: Message):
    if not message.document.file_name.lower().endswith(".csv"):
        await message.answer("❌ Помилка: підтримуються тільки файли з розширенням <b>.csv</b>", parse_mode="HTML")
        return

    status_msg = await message.answer("⏳ <b>Читання та валідація файлу...</b>", parse_mode="HTML")

    try:
        file = await message.bot.get_file(message.document.file_id)
        content = await message.bot.download_file(file.file_path)

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

                if len(tasks_chunk) >= 100:
                    def _insert_chunk(data):
                        supabase.table("tasks").insert(data).execute()

                    await asyncio.to_thread(_insert_chunk, list(tasks_chunk))
                    total_uploaded += len(tasks_chunk)
                    tasks_chunk.clear()
                    await asyncio.sleep(0.01)

            except Exception:
                errors += 1
                continue

        if tasks_chunk:
            def _insert_chunk(data):
                supabase.table("tasks").insert(data).execute()

            await asyncio.to_thread(_insert_chunk, list(tasks_chunk))
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
