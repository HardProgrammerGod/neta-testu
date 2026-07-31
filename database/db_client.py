import asyncio
from datetime import date
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


async def get_or_create_user(tg_id: int, username: str, first_name: str) -> dict:
    """Асинхронно отримує або створює користувача в БД Supabase."""
    today = str(date.today())

    def _db_op():
        res = supabase.table("users").select("*").eq("id", tg_id).execute()

        if not res.data:
            user = {
                "id": tg_id,
                "username": username or "",
                "first_name": first_name or "Учень",
                "daily_tests_left": 3,
                "last_test_date": today,
                "is_premium": False,
                "is_active": True,
                "total_tests_passed": 0,
                "referral_count": 0,
                "premium_referrals_count": 0,
                "referral_balance": 0
            }
            supabase.table("users").insert(user).execute()

            # Інкрементуємо лічильник реєстрацій
            try:
                stats = supabase.table("global_stats").select("total_users_count").eq("id", 1).execute()
                if stats.data:
                    current_total = stats.data[0].get("total_users_count", 0)
                    supabase.table("global_stats").update({"total_users_count": current_total + 1}).eq("id", 1).execute()
            except Exception:
                pass

            return user

        user = res.data[0]
        updates = {}

        # Відновлюємо статус активності, якщо користувач повернувся
        if not user.get("is_active", True):
            updates["is_active"] = True
            user["is_active"] = True

        # Перевірка та оновлення денного ліміту
        if user.get("last_test_date") != today:
            updates["daily_tests_left"] = 3
            updates["last_test_date"] = today
            user["daily_tests_left"] = 3
            user["last_test_date"] = today

        if updates:
            supabase.table("users").update(updates).eq("id", tg_id).execute()

        return user

    return await asyncio.to_thread(_db_op)


async def mark_user_inactive(user_id: int):
    """Безпечно маркує користувача як неактивного (Soft Delete)."""
    def _db_op():
        try:
            supabase.table("users").update({"is_active": False}).eq("id", user_id).execute()
        except Exception as e:
            print(f"Error marking user {user_id} inactive: {e}")

    await asyncio.to_thread(_db_op)


async def get_full_test_tasks(category: str, sub_category: str) -> list:
    """Достає пул питань за 1 запит без перевантаження RAM."""
    def _db_op():
        res = supabase.table("tasks") \
            .select("id, category, sub_category, section, question_text, options, correct_answer, explanation") \
            .eq("category", category) \
            .eq("sub_category", sub_category) \
            .order("id") \
            .execute()
        return res.data or []

    return await asyncio.to_thread(_db_op)


async def decrease_test_limit(tg_id: int, current_left: int):
    """Зменшує ліміт спроб користувача."""
    def _db_op():
        supabase.table("users").update({
            "daily_tests_left": max(0, current_left - 1)
        }).eq("id", tg_id).execute()

    await asyncio.to_thread(_db_op)


async def save_attempt(user_id: int, task_id: int, answer: str, is_correct: bool):
    """Фіксує відповідь користувача."""
    def _db_op():
        supabase.table("user_attempts").insert({
            "user_id": user_id,
            "task_id": task_id,
            "selected_answer": answer,
            "is_correct": is_correct
        }).execute()

    await asyncio.to_thread(_db_op)
