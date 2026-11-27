"""ШАБЛОН: подтверждение «Да / Нет» перед опасным действием (по образцу дуэлей и «очистить чат»).

Паттерн: команда → сообщение с двумя кнопками (id инициатора в callback_data) → по «Да» выполняем.
Подключение: роутер в main.py (ROUTERS).
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import mod_service as ms

router = Router(name="dangerous")
PREFIX = "dng"


@router.message(F.text.lower() == "опасная команда")
async def ask(message: Message, bot, db) -> None:
    if await ms.effective_rank(bot, db, message.chat.id, message.from_user.id) < 4:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        B(text="✅ Да", callback_data=f"{PREFIX}:yes:{message.from_user.id}"),
        B(text="❌ Нет", callback_data=f"{PREFIX}:no:{message.from_user.id}")]])
    await message.reply("⚠️ Точно выполнить? Это нельзя отменить.", reply_markup=kb)


@router.callback_query(F.data.startswith(f"{PREFIX}:"))
async def answer(cb: CallbackQuery, bot, db) -> None:
    _, choice, owner = cb.data.split(":")
    if cb.from_user.id != int(owner):
        await cb.answer("Не ваша кнопка")
        return
    if choice == "yes":
        # ... опасное действие ...
        await cb.message.edit_text("✅ Выполнено.")
    else:
        await cb.message.edit_text("Отменено.")
    await cb.answer()
