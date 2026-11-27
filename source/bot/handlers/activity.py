"""Команды нормы сообщений: «норма 300» (задать), «моя норма» (сколько набрал за неделю), «кто не набрал» (список отстающих)."""
from __future__ import annotations

import re
import time

from aiogram import F, Router
from aiogram.types import Message

from bot import activity as act, ux
from bot.db import Database
from bot.handlers.settings import can_configure

router = Router(name="activity")

_SET = re.compile(r"^норма\s+(\d{1,5})$", re.IGNORECASE)
_MINE = re.compile(r"^моя\s+норма$", re.IGNORECASE)
_LIST = re.compile(r"^кто\s+не\s+набрал$", re.IGNORECASE)
MIN_NORM, MAX_NORM = 10, 5000


def _is(rx):
    return F.text.func(lambda t: bool(t) and rx.match(t.strip()) is not None)


async def _week(db: Database, chat: int, s: dict, now: float):
    tz = act.chat_tz(s.get("tz"))
    ws = act.week_start(now, tz)
    return tz, ws, await act.week_counts(db, chat, ws)


@router.message(F.chat.type.in_({"group", "supergroup"}), _is(_SET))
async def set_norm(message: Message, bot, db: Database) -> None:
    if message.from_user is None or not await can_configure(bot, db, message.chat.id, message.from_user.id):
        return                                              # обычная фраза («норма 5»), не команда
    n = int(_SET.match(message.text.strip()).group(1))
    if not MIN_NORM <= n <= MAX_NORM:
        await ux.tell(message, f"⚠️ Норма — от {MIN_NORM} до {MAX_NORM} сообщений в неделю.")
        return
    await db.set_setting(message.chat.id, "quota_min", n, actor=message.from_user.id)
    on = (await db.get_settings(message.chat.id))["quota_on"]
    await message.reply(f"📅 Норма: <b>{n}</b> сообщений в неделю." + ("" if on else "\nАвтокик выключен — включить: «настройки» → «Активность»."))


@router.message(F.chat.type.in_({"group", "supergroup"}), _is(_MINE))
async def my_norm(message: Message, db: Database) -> None:
    if message.from_user is None:
        return
    s = await db.get_settings(message.chat.id)
    _, ws, counts = await _week(db, message.chat.id, s, time.time())
    n, norm = counts.get(message.from_user.id, 0), int(s["quota_min"])
    state = "автокик включён" if s["quota_on"] else "автокик выключен"
    mark = "✅ норма выполнена" if n >= norm else f"осталось {norm - n}"
    await ux.tell(message, f"📅 С понедельника вы написали <b>{n}</b> из {norm} — {mark} ({state}).")


@router.message(F.chat.type.in_({"group", "supergroup"}), _is(_LIST))
async def who_lags(message: Message, bot, db: Database) -> None:
    if message.from_user is None or not await can_configure(bot, db, message.chat.id, message.from_user.id):
        return
    chat = message.chat.id
    s = await db.get_settings(chat)
    exempt = await act.exempt_ids(bot, db, chat)
    if exempt is None:
        await ux.tell(message, "❌ Не смог получить список админов.")
        return
    _, ws, counts = await _week(db, chat, s, time.time())
    norm = int(s["quota_min"])
    lag = act.below_norm(await db.members_info(chat), counts, exempt, norm, ws)
    if not lag:
        await message.reply(f"🏆 Все набирают норму ({norm}) в эту неделю.")
        return
    names = await act._name_map(db, [u for u, _ in lag[:act.LIST_LIMIT]])
    await message.reply(f"📅 Пока не набрали норму ({norm}) с понедельника — {len(lag)} чел.:\n" + act._names(names, lag, norm),
                        disable_web_page_preview=True)
