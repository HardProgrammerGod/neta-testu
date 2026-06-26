import asyncio
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, CallbackQuery

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, slow_down_rate: float = 0.6):
        self.cache = {}
        self.slow_down_rate = slow_down_rate
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            if user_id in self.cache:
                await event.answer("⚠️ Занадто швидко! Не спам кнопочками.", show_alert=False)
                return
            
            self.cache[user_id] = True
            try:
                return await handler(event, data)
            finally:
                await asyncio.sleep(self.slow_down_rate)
                self.cache.pop(user_id, None)
        else:
            return await handler(event, data)
