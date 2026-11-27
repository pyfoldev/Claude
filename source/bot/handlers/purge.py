"""Очистка чата командой: «очистить чат» → кнопка подтверждения → фоновое удаление всех сообщений (bot.purge)."""
from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import mod_service as ms
from bot import purge
from bot.db import Database
from bot.ranks import need_rank

router = Router(name="purge")
_CMD = re.compile(r"^[!/]?(?:очистить\s+(?:весь\s+)?чат|удалить\s+все\s+сообщения)$", re.IGNORECASE)


async def _allowed(bot, db: Database, chat_id: int, user_id: int) -> tuple[bool, str]:
    rank = await ms.effective_rank(bot, db, chat_id, user_id)
    need = max(need_rank(await db.get_access(chat_id), "очистить чат"), purge.MIN_RANK)
    if rank < need:
        return False, f"Очистка чата доступна с ранга {need}."
    return True, ""


@router.message(F.text.func(lambda t: bool(t) and _CMD.match(t.strip()) is not None))
async def purge_cmd(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    ok, why = await _allowed(bot, db, message.chat.id, message.from_user.id)
    if not ok:
        await message.reply(why)
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🗑 Удалить ВСЕ сообщения", callback_data=f"purge:go:{message.from_user.id}"),
        InlineKeyboardButton(text="Отмена", callback_data=f"purge:no:{message.from_user.id}")]])
    await message.reply("⚠️ Будут удалены <b>все</b> сообщения этого чата. Это необратимо. Подтвердить?",
                        reply_markup=kb)


@router.callback_query(F.data.startswith("purge:"))
async def purge_cb(cb: CallbackQuery, bot, db: Database) -> None:
    parts = (cb.data or "").split(":")
    if len(parts) != 3 or parts[1] not in ("go", "no") or not parts[2].isdigit() or cb.message is None:
        await cb.answer()
        return
    if cb.from_user.id != int(parts[2]):
        await cb.answer("Эта кнопка не для вас.", show_alert=True)
        return
    chat_id = cb.message.chat.id
    try:
        await cb.message.delete()                         # кнопка одноразовая
    except Exception:
        await cb.answer("Уже обработано", show_alert=True)
        return
    if parts[1] == "no":
        await cb.answer("Отменено")
        return
    ok, why = await _allowed(bot, db, chat_id, cb.from_user.id)         # права проверяем ещё раз в момент нажатия
    if not ok:
        await cb.answer(why, show_alert=True)
        return
    try:
        await purge.start_purge(bot, db, chat_id, cb.from_user.id)
    except purge.PurgeError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer("Запущено")
