"""Фоновые задачи правил: повторяющиеся сообщения и ночной режим."""
from __future__ import annotations

import asyncio
import json
import logging
import time

from aiogram.types import ChatPermissions

from bot import mod_service as ms
from bot import rules
from bot.db import Database
from bot.middlewares.rules import chat_rules  # noqa: F401  (кэш правил общий с мидлварью)

TICK = 60


async def _send_periodic(bot, db: Database, now: int) -> None:
    for p in await db.list_periodic():
        if now - p["last_sent"] < p["every"]:
            continue
        await db.touch_periodic(p["id"], now)            # сначала отметка: сбой отправки не должен зациклить повторы
        try:
            try:
                await bot.send_message(p["chat_id"], p["text"])
            except Exception:
                import html
                await bot.send_message(p["chat_id"], html.escape(p["text"]))
        except Exception as e:
            logging.warning("повтор #%s в чат %s не отправился: %s", p["id"], p["chat_id"], e)


async def _night_step(bot, db: Database, chat: int, now: float) -> None:
    s = await db.get_settings(chat)
    night = rules.in_night(rules.local_hour(s["tz"], now), s["night_from"], s["night_to"])
    if night and not s["night_closed"]:
        try:
            if await db.get_text(chat, "perms_backup") is None:      # запоминаем права, чтобы вернуть их утром
                cur = (await bot.get_chat(chat)).permissions
                if cur is not None:
                    await db.set_text(chat, "perms_backup", json.dumps(cur.model_dump(exclude_none=True)))
            await bot.set_chat_permissions(chat, permissions=ChatPermissions(can_send_messages=False))
            await db.set_setting(chat, "night_closed", 1)
            await bot.send_message(chat, f"🌙 Ночной режим: до {s['night_to']}:00 пишут только админы.")
        except Exception as e:
            logging.warning("ночной режим: не удалось закрыть чат %s: %s", chat, e)
    elif not night and s["night_closed"]:
        await _open(bot, db, chat)


async def _open(bot, db: Database, chat: int) -> None:
    try:
        saved = await db.get_text(chat, "perms_backup")
        perms = ChatPermissions(**json.loads(saved)) if saved else ms._FULL
        if saved and not perms.can_send_messages:
            perms = ChatPermissions(**{**json.loads(saved), "can_send_messages": True})
        await bot.set_chat_permissions(chat, permissions=perms)
        await db.set_text(chat, "perms_backup", None)
        await db.set_setting(chat, "night_closed", 0)
        await bot.send_message(chat, "☀️ Ночной режим закончился — чат снова открыт.")
    except Exception as e:
        logging.warning("ночной режим: не удалось открыть чат %s: %s", chat, e)


async def scheduler_loop(bot, db: Database) -> None:
    while True:
        now = time.time()
        try:
            await _send_periodic(bot, db, int(now))
            for chat in await db.night_chats():
                await _night_step(bot, db, chat, now)
            # ночной режим выключили, пока чат был закрыт, — открываем
            cur = await db.conn.execute("SELECT chat_id FROM settings WHERE key='night_closed' AND value='1'")
            for r in await cur.fetchall():
                if not (await db.get_settings(r["chat_id"]))["night_on"]:
                    await _open(bot, db, r["chat_id"])
        except Exception:
            logging.exception("scheduler step failed")
        await asyncio.sleep(TICK)
