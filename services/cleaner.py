import asyncio
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from database.db_client import supabase, purge_blocked_user

async def audit_and_purge_blocked_users(bot: Bot):
    """
    Фонова перевірка всіх користувачів.
    Якщо юзер заблокував бота — видаляємо його з БД.
    """
    res = supabase.table("users").select("id").execute()
    if not res.data:
        return 0

    purged_count = 0
    for row in res.data:
        uid = row["id"]
        try:
            # Надсилаємо легку дію (відповідає "typing..."), яка перевіряє доступність чату
            await bot.send_chat_action(chat_id=uid, action="typing")
            await asyncio.sleep(0.05) # Захист від флуд-ліміту Telegram API
        except TelegramForbiddenError:
            await purge_blocked_user(uid)
            purged_count += 1
        except TelegramBadRequest as e:
            if "chat not found" in e.message.lower() or "user is deactivated" in e.message.lower():
                await purge_blocked_user(uid)
                purged_count += 1
        except Exception:
            pass

    print(f"🧹 Фонова очистка завершена. Видалено заблокованих акаунтів: {purged_count}")
    return purged_count
