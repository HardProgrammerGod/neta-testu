import asyncio
from openai import AsyncOpenAI
from config import GROK_API_KEY
from database.db_client import supabase

# xAI Grok сумісний з OpenAI SDK
client = AsyncOpenAI(
    api_key=GROK_API_KEY,
    base_url="https://api.x.ai/v1"
)

SYSTEM_PROMPT = (
    "Ти — NetaGPT, персональний AI-методист із підготовки до НМТ з англійської мови від Neta School. "
    "Твоє завдання — пояснювати граматику, сленг, лексику та помилки НМТ коротко, зрозуміло, стисло та дружньо. "
    "КРИТИЧНІ ПРАВИЛА:\n"
    "1. НІКОЛИ не кажи, що ти Grok, xAI, OpenAI чи ChatGPT. Ти виключно NetaGPT!\n"
    "2. Відповідай УКРАЇНСЬКОЮ мовою.\n"
    "3. Будь максимально лаконічним (максимум 150-200 слів), без 'води', давай тільки суть і приклади.\n"
    "4. Використовуй емодзі для розставиння акцентів."
)

FOOTER_MARKETING = "\n\n📍 <i>Детальний тренажер для цих тем доступний на нашій інтерактивній веб-платформі Neta School.</i>"

async def clean_old_ai_chats(user_id: int):
    """Видаляє повідомлення чату, старші за 1 годину (захист пам'яті Supabase)."""
    try:
        # PostgreSQL syntax: created_at < NOW() - INTERVAL '1 hour'
        supabase.table("ai_chats") \
            .delete() \
            .eq("user_id", user_id) \
            .lt("created_at", "now() - interval '1 hour'") \
            .execute()
    except Exception:
        pass

async def get_grok_tutor_response(user_id: int, user_message: str) -> str:
    """Чат-асистент AI-Tutor з урахуванням 1 останнього контексту."""
    await clean_old_ai_chats(user_id)
    
    # Витягуємо останні 2 повідомлення (для економії токенів)
    history_res = supabase.table("ai_chats") \
        .select("role", "content") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .limit(2) \
        .execute()
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if history_res.data:
        for msg in reversed(history_res.data):
            messages.append({"role": msg["role"], "content": msg["content"]})
            
    messages.append({"role": "user", "content": user_message})

    try:
        response = await client.chat.completions.create(
            model="grok-beta", # або актуальна версія grok-2-mini
            messages=messages,
            max_tokens=300, # Суворе обмеження токенів
            temperature=0.4
        )
        ans_text = response.choices[0].message.content.strip() + FOOTER_MARKETING
        
        # Зберігаємо лише поточний діалог у БД
        supabase.table("ai_chats").insert([
            {"user_id": user_id, "role": "user", "content": user_message},
            {"user_id": user_id, "role": "assistant", "content": ans_text}
        ]).execute()
        
        return ans_text
    except Exception as e:
        return "⚠️ Вибач, NetaGPT зараз перевантажений. Спробуй поставити запитання трохи пізніше!"

async def generate_study_plan(user_id: int, wrong_topics: list) -> str:
    """Генерація короткої дорожньої карти після тесту."""
    topics_str = ", ".join(wrong_topics)
    prompt = (
        f"Учень зробив помилки в темах НМТ: [{topics_str}]. "
        f"Напиши коротку дорожню карту з 3 чітких кроків (до 100 слів), що йому вивчити в першу чергу."
    )
    
    try:
        response = await client.chat.completions.create(
            model="grok-beta",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            max_tokens=250,
            temperature=0.3
        )
        return response.choices[0].message.content.strip() + FOOTER_MARKETING
    except Exception:
        return "📍 <i>Повтори зазначені теми та опрацюй їх у нашому тренажері!</i>"
