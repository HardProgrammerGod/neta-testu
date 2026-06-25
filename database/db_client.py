from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY
from datetime import date

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def get_or_create_user(tg_id: int, username: str, first_name: str):
    res = supabase.table("users").select("*").eq("id", tg_id).execute()
    today = str(date.today())

    if not res.data:
        user = {
            "id": tg_id,
            "username": username,
            "first_name": first_name,
            "daily_tests_left": 3,
            "last_test_date": today,
            "is_premium": False,
            "total_tests_passed": 0,
            "referral_count": 0,
            "premium_referrals_count": 0,
            "referral_balance": 0
        }
        supabase.table("users").insert(user).execute()
        return user

    user = res.data[0]

    if user.get("last_test_date") != today:
        supabase.table("users").update({
            "daily_tests_left": 3,
            "last_test_date": today
        }).eq("id", tg_id).execute()
        user["daily_tests_left"] = 3

    return user

async def get_full_test_tasks(category: str, sub_category: str):
    """Достает сразу весь пул вопросов для конкретного варианта за 1 запрос"""
    res = supabase.table("tasks") \
        .select("*") \
        .eq("category", category) \
        .eq("sub_category", sub_category) \
        .order("id") \
        .execute()
    return res.data

async def decrease_test_limit(tg_id: int, current_left: int):
    supabase.table("users").update({
        "daily_tests_left": max(0, current_left - 1)
    }).eq("id", tg_id).execute()

async def save_attempt(user_id: int, task_id: int, answer: str, is_correct: bool):
    supabase.table("user_attempts").insert({
        "user_id": user_id,
        "task_id": task_id,
        "selected_answer": answer,
        "is_correct": is_correct
    }).execute()
