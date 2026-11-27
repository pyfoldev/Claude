"""Сверка списка участников с Telegram: кто вышел, пока бот не видел (не был админом, был выключен), — убираем.

Telegram присылает событие о выходе только админу и только пока бот работает, поэтому одних событий мало:
список проверяется перед «общим сбором», раз в 12 часов в фоне и по команде «проверить участников»."""
from __future__ import annotations

import asyncio
import logging
import time

from aiogram.exceptions import TelegramBadRequest

from bot.db import Database

SWEEP_EVERY = 12 * 3600
SWEEP_FIRST_DELAY = 600
PAUSE = 0.05            # ~20 запросов в секунду: укладываемся в лимиты Bot API с запасом


def is_present(m) -> bool:
    return m.status in ("member", "administrator", "creator") or (
        m.status == "restricted" and getattr(m, "is_member", True))


async def check(bot, db: Database, chat_id: int, user_id: int) -> bool | None:
    """True — в чате, False — вышел (помечен неактивным), None — не удалось узнать (ничего не меняем)."""
    try:
        m = await bot.get_chat_member(chat_id, user_id)
    except TelegramBadRequest as e:
        # Ошибки чата или прав бота не говорят ничего о конкретном участнике.
        message = str(e).lower()
        if "user not found" in message or "participant_id_invalid" in message:
            await db.set_member_active(chat_id, user_id, False)
            return False
        return None
    except Exception:
        return None
    if is_present(m):
        return True
    await db.set_member_active(chat_id, user_id, False)
    return False


async def sync_chat(bot, db: Database, chat_id: int, pause: float = PAUSE) -> tuple[int, int]:
    """Проверяет всех известных участников чата. (сколько проверено, сколько убрано как вышедших)."""
    removed = checked = 0
    for m in await db.members_info(chat_id):
        res = await check(bot, db, chat_id, m["user_id"])
        if res is not None:
            checked += 1
            removed += res is False
        if pause:
            await asyncio.sleep(pause)
    return checked, removed


async def sweep_loop(bot, db: Database) -> None:
    await asyncio.sleep(SWEEP_FIRST_DELAY)
    while True:
        started, total = time.time(), 0
        for c in await db.list_chats(0, 10000, active_only=True):
            try:
                _, removed = await sync_chat(bot, db, c["chat_id"])
                total += removed
            except Exception:
                logging.exception("members sweep failed for %s", c["chat_id"])
        logging.info("сверка участников: убрано вышедших %s за %.0f с", total, time.time() - started)
        await asyncio.sleep(SWEEP_EVERY)
