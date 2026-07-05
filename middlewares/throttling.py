import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, CallbackQuery

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, slow_down_rate: float = 0.4):
        # Храним {user_id: timestamp_последнего_клика}
        self.cache: Dict[int, float] = {}
        self.slow_down_rate = slow_down_rate
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Защищаем только CallbackQuery (клики по кнопкам), сообщения пропускаем без задержек
        if isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            current_time = time.time()
            
            # Проверяем, сколько времени прошло с прошлого клика
            last_click = self.cache.get(user_id, 0.0)
            if current_time - last_click < self.slow_down_rate:
                # Всплывающее уведомление (не блокирует экран)
                await event.answer("⚠️ Не спам кнопочками, зачекай секунду.", show_alert=False)
                return
            
            # Записываем время текущего клика ДО выполнения тяжелого хэндлера
            self.cache[user_id] = current_time
            
            # Чистим старый хлам из кэша, чтобы RAM не забивался (очистка раз в 50 кликов)
            if len(self.cache) > 100:
                self._clean_old_cache(current_time)

        return await handler(event, data)

    def _clean_old_cache(self, current_time: float):
        """Безопасная очистка кэша от "мертвых" записей, чтобы не росла память."""
        keys_to_remove = [
            uid for uid, ts in self.cache.items() 
            if current_time - ts > self.slow_down_rate * 2
        ]
        for uid in keys_to_remove:
            self.cache.pop(uid, None)
