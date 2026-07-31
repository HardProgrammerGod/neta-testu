import html
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database.db_client import get_or_create_user, supabase
from services.grok_service import get_grok_tutor_response
from handlers.start import check_subscription

router = Router()

class AITutorState(StatesGroup):
    waiting_for_question = State()

KB_CANCEL_AI = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="❌ Завершити діалог", callback_data="exit_ai_tutor")]
])

@router.message(F.text == "/ai")
@router.callback_query(F.data == "start_ai_tutor")
async def cmd_ai_tutor(event: Message | CallbackQuery, bot: Bot, state: FSMContext):
    user_id = event.from_user.id
    message = event if isinstance(event, Message) else event.message

    if not await check_subscription(bot, user_id):
        await message.answer("❌ Будь ласка, спочатку підпишись на наш канал!")
        return

    user = await get_or_create_user(user_id, event.from_user.username, event.from_user.first_name)
    
    ai_left = user.get("ai_requests_left", 3)
    is_premium = user.get("is_premium", False)

    if not is_premium and ai_left <= 0:
        text = (
            "🔒 <b>Твої безкоштовні AI-запити на сьогодні вичерпано!</b>\n\n"
            "Отримай <b>Premium</b>, щоб користуватися NetaGPT без обмежень "
            "та отримувати повні розбори всіх правил!"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купити Premium (250 ⭐)", callback_data="quiz_buy_premium")]
        ])
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            await event.answer()
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    limit_str = "безліміт" if is_premium else f"{ai_left} з 3"
    intro_text = (
        f"🧠 <b>NetaGPT — твій AI-Tutor з англійської!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Поставиш будь-яке питання щодо граматики, правил, різниці між словами чи конструкціями НМТ.\n\n"
        f"📊 Твій залишок запитів на сьогодні: <b>{limit_str}</b>\n\n"
        f"👇 <i>Напиши своє запитання нижче у повідомленні:</i>"
    )

    await state.set_state(AITutorState.waiting_for_question)
    
    if isinstance(event, CallbackQuery):
        await message.edit_text(intro_text, parse_mode="HTML", reply_markup=KB_CANCEL_AI)
        await event.answer()
    else:
        await message.answer(intro_text, parse_mode="HTML", reply_markup=KB_CANCEL_AI)

@router.callback_query(F.data == "exit_ai_tutor")
async def exit_ai(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("👍 Двері AI-Tutor зачинено. Якщо виникнуть питання — тисни /ai!")
    await callback.answer()

@router.message(AITutorState.waiting_for_question)
async def process_ai_question(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    user_text = message.text.strip()

    if user_text.startswith("/"):
        await state.clear()
        await message.answer("⚠️ Введення перервано командою.")
        return

    wait_msg = await message.answer("🧠 <b>NetaGPT аналізує твій запит...</b>\n<i>Зачекай кілька секунд.</i>", parse_mode="HTML")
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    answer = await get_grok_tutor_response(user_id, user_text)

    # Списання ліміту для Free користувачів (асинхронно)
    user = await get_or_create_user(user_id, message.from_user.username, message.from_user.first_name)
    if not user.get("is_premium"):
        def _decrease_limit():
            supabase.rpc("decrease_ai_limit", {"p_user_id": user_id}).execute()
        await asyncio.to_thread(_decrease_limit)

    await state.clear()
    await wait_msg.edit_text(answer, parse_mode="HTML", reply_markup=KB_CANCEL_AI)
