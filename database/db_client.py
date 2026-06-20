from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY
from datetime import date

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def get_or_create_user(tg_id: int, username: str, first_name: str):
    """Безпечно отримує або реєструє користувача з оновленням щоденних лімітів."""
    res = supabase.table("users").select("*").eq("id", tg_id).execute()
    current_date_str = str(date.today())
    
    if not res.data:
        user_data = {
            "id": tg_id,
            "username": username,
            "first_name": first_name,
            "daily_tests_left": 3,
            "last_test_date": current_date_str,
            "is_premium": False
        }
        supabase.table("users").insert(user_data).execute()
        return user_data
    
    user = res.data[0]
    if user["last_test_date"] != current_date_str:
        supabase.table("users").update({
            "daily_tests_left": 3, 
            "last_test_date": current_date_str
        }).eq("id", tg_id).execute()
        user["daily_tests_left"] = 3
    return user

async def get_random_task():
    """Витягує випадкове завдання через RPC функцію для максимальної швидкості."""
    try:
        # Спершу викликаємо збережену функцію випадкового вибору в Postgres
        res = supabase.rpc("get_random_task").execute()
        if res.data:
            return res.data[0]
    except Exception:
        # Фалбек, якщо функцію RPC не налаштували в Supabase
        import random
        res = supabase.table("tasks").select("*").limit(100).execute()
        return random.choice(res.data) if res.data else None

async def decrease_test_limit(tg_id: int, current_left: int):
    supabase.table("users").update({"daily_tests_left": max(0, current_left - 1)}).eq("id", tg_id).execute()

async def save_attempt(user_id: int, task_id: int, answer: str, is_correct: bool):
    supabase.table("user_attempts").insert({
        "user_id": user_id,
        "task_id": task_id,
        "selected_answer": answer,
        "is_correct": is_correct
    }).execute()
