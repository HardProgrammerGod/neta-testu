import asyncio
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter
from database.db_client import supabase, mark_user_inactive

async def audit_and_purge_blocked_users(bot: Bot):
    """
    Почанкова перевірка активних користувачів на наявність блокувань.
    Захищена від FloodLimit та переповнення пам'яті.
    """
    purged_count = 0
    page_size = 500
    offset = 0

    while True:
        def _fetch_chunk():
            return supabase.table("users") \
                .select("id") \
                .eq("is_active", True) \
                .range(offset, offset + page_size - 1) \
                .execute().data or []

        chunk = await asyncio.to_thread(_fetch_chunk)
        if not chunk:
            break

        dead_pool = []
        for row in chunk:
            uid = row["id"]
            try:
                await bot.send_chat_action(chat_id=uid, action="typing")
                await asyncio.sleep(0.04)  # Захист від лімітів API (до ~25 запитів/сек)
            except TelegramForbiddenError:
                dead_pool.append(uid)
            except TelegramBadRequest as e:
                msg = e.message.lower()
                if "chat not found" in msg or "user is deactivated" in msg:
                    dead_pool.append(uid)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                # Повторна спроба
                try:
                    await bot.send_chat_action(chat_id=uid, action="typing")
                except Exception:
                    dead_pool.append(uid)
            except Exception:
                pass

        if dead_pool:
            def _update_dead():
                supabase.table("users").update({"is_active": False}).in_("id", dead_pool).execute()

            await asyncio.to_thread(_update_dead)
            purged_count += len(dead_pool)

        offset += page_size

    print(f"🧹 Автоматична очистка завершена. Неактивними позначено: {purged_count}")
    return purged_count


async def periodic_cleaner_task(bot: Bot):
    """Фонова задача, яка запускає сканування бази кожні 24 години."""
    while True:
        try:
            await asyncio.sleep(86400)  # Чекаємо 24 години
            await audit_and_purge_blocked_users(bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Помилка фонового очищувача: {e}")
            await asyncio.sleep(3600)  # У разі збою повторюємо через годину
