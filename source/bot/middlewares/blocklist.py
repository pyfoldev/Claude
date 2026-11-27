"""Самый внешний фильтр: блок-лист владельца и режим обслуживания. Владельцев не трогает."""
from __future__ import annotations

import logging

from aiogram import BaseMiddleware
from aiogram.types import Update

from bot.runtime import Runtime


# Достаёт (id отправителя, id чата) из апдейта любого вида; новый вид апдейта с чатом — добавьте ветку сюда
def sender_and_chat(update: Update) -> tuple[int | None, int | None]:
    if update.message or update.edited_message:
        m = update.message or update.edited_message
        return (m.from_user.id if m.from_user else None), m.chat.id
    if update.callback_query:
        cb = update.callback_query
        return cb.from_user.id, (cb.message.chat.id if cb.message else None)
    for ev in (update.chat_member, update.my_chat_member):
        if ev:
            return ev.from_user.id, ev.chat.id
    if update.chat_join_request:
        return update.chat_join_request.from_user.id, update.chat_join_request.chat.id
    return None, None


# ┌─ БЛОК-ЛИСТ И РЕЖИМ ОБСЛУЖИВАНИЯ ─────────────────────────────────────────────┐
# │ Подключён самым ПЕРВЫМ (после метрик). Порядок проверок:                      │
# │   1. владелец бота → пропускаем всегда;                                       │
# │   2. чат в блок-листе → бот выходит из него (один раз) и всё игнорирует;      │
# │   3. пользователь в блок-листе ИЛИ режим обслуживания → игнорируем команды,   │
# │      но защита чата (guard) и вход новичков (капча/антирейд) продолжают работать.│
# │ Данные берутся из Runtime (runtime.py): rt.banned_users / banned_chats / maintenance. │
# └────────────────────────────────────────────────────────────────────────────────┘
class BlockMiddleware(BaseMiddleware):
    def __init__(self, rt: Runtime, owner_ids, guard=None):
        self.rt = rt
        self.owner_ids = frozenset(owner_ids)
        self.guard = guard  # антиспам/18+ продолжают работать и против заблокированных в боте

    async def __call__(self, handler, event: Update, data):
        user_id, chat_id = sender_and_chat(event)
        if user_id in self.owner_ids:
            return await handler(event, data)
        if chat_id in self.rt.banned_chats:
            if event.my_chat_member and event.my_chat_member.new_chat_member.status not in ("left", "kicked"):
                self.rt.left_chats.discard(chat_id)  # бота вернули в заблокированный чат — выйдем снова
            if chat_id not in self.rt.left_chats:
                self.rt.left_chats.add(chat_id)
                try:
                    await data["bot"].leave_chat(chat_id)
                except Exception:
                    logging.warning("не смог выйти из заблокированного чата %s", chat_id)
            return None
        if user_id in self.rt.banned_users or self.rt.maintenance:
            if event.chat_member:
                return await handler(event, data)  # вход в чат: капча и антирейд работают всегда
            msg = event.message or event.edited_message
            if msg is not None and self.guard is not None:
                async def _noop(*_a):
                    return None
                try:
                    await self.guard(_noop, msg, data)  # игнорируем команды, но защиту чата не отключаем
                except Exception:
                    logging.exception("guard для заблокированного пользователя")
            return None
        return await handler(event, data)
