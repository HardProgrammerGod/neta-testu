import asyncio
import logging
from openai import AsyncOpenAI
from config import GROK_API_KEY
from database.db_client import supabase

logger = logging.getLogger(__name__)

# Ініціалізація клієнта Groq (використовує OpenAI SDK)
client = AsyncOpenAI(
    api_key=GROK_API_KEY,  # Твій ключ від Groq Cloud (починається на gsk_...)
    base_url="https://api.groq.com/openai/v1"
)

SYSTEM_PROMPT = (
    "Ти — NetaGPT, персональний AI-методист із підготовки до НМТ з англійської мови від Neta School. "
    "Твоє завдання — пояснювати граматику, сленг, лексику та помилки НМТ коротко, зрозуміло, стисло та дружньо. "
    "КРИТИЧНІ ПРАВИЛА:\n"
    "1. НІКОЛИ не кажи, що ти Llama, Meta, Groq, OpenAI чи ChatGPT. Ти виключно NetaGPT!\n"
    "2. Відповідай УКРАЇНСЬКОЮ мовою.\n"
    "3. Будь максимально лаконічним (максимум 150-200 слів), без 'води', давай тільки суть і приклади.\n"
    "4. Використовуй емодзі для розставиння акцентів."
)

FOOTER_MARKETING = "\n\n📍 <i>Детальний тренажер для цих тем доступний на нашій інтерактивній веб-платформі Neta School.</i>"

async def clean_old_ai_chats(user_id: int):
    """Видаляє повідомлення чату, старші за 1 годину (асинхронно)."""
    def _delete():
        supabase.table("ai_chats") \
            .delete() \
            .eq("user_id", user_id) \
            .lt("created_at", "now() - interval '1 hour'") \
            .execute()
    try:
        await asyncio.to_thread(_delete)
    except Exception as e:
        logger.error(f"Error cleaning old AI chats: {e}")

async def get_grok_tutor_response(user_id: int, user_message: str) -> str:
    """Чат-асистент AI-Tutor з урахуванням останнього контексту."""
    await clean_old_ai_chats(user_id)
    
    def _fetch_history():
        return supabase.table("ai_chats") \
            .select("role", "content") \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .limit(2) \
            .execute()

    try:
        history_res = await asyncio.to_thread(_fetch_history)
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        if history_res and history_res.data:
            for msg in reversed(history_res.data):
                messages.append({"role": msg["role"], "content": msg["content"]})
                
        messages.append({"role": "user", "content": user_message})

        # Запит до Groq API з моделлю Llama 3.3 70B
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=400,
            temperature=0.4
        )
        ans_text = response.choices[0].message.content.strip() + FOOTER_MARKETING
        
        def _save_history():
            supabase.table("ai_chats").insert([
                {"user_id": user_id, "role": "user", "content": user_message},
                {"user_id": user_id, "role": "assistant", "content": ans_text}
            ]).execute()

        await asyncio.to_thread(_save_history)
        
        return ans_text
    except Exception as e:
        logger.error(f"Groq API Error for user {user_id}: {e}", exc_info=True)
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
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            max_tokens=250,
            temperature=0.3
        )
        return response.choices[0].message.content.strip() + FOOTER_MARKETING
    except Exception as e:
        logger.error(f"Generate Study Plan Error: {e}")
        return "📍 <i>Повтори зазначені теми та опрацюй їх у нашому тренажері!</i>"
