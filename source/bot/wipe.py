"""«вайп @ник» — удалить сообщения участника за последние 48 часов.

Bot API не отдаёт историю чата, поэтому бот помнит номера свежих сообщений сам (только в памяти, на время работы):
последние сообщения каждого участника за 48 часов. После перезапуска то, что было раньше, вайп не увидит.
Telegram позволяет удалять сообщения не старше 48 часов."""
from __future__ import annotations

import logging
from collections import deque

WINDOW = 48 * 3600 - 600       # запас на часовые пояса и задержки
PER_USER = 150
MAX_KEYS = 60000

_seen: dict[tuple[int, int], deque] = {}


def remember(chat_id: int, user_id: int, message_id: int, ts: int) -> None:
    key = (chat_id, user_id)
    q = _seen.get(key)
    if q is None:
        if len(_seen) >= MAX_KEYS:
            prune(ts)
            if len(_seen) >= MAX_KEYS:
                _seen.clear()
        q = _seen[key] = deque(maxlen=PER_USER)
    q.append((message_id, ts))


def prune(now: int) -> None:
    for key in [k for k, q in _seen.items() if not q or now - q[-1][1] > WINDOW]:
        _seen.pop(key, None)


def take(chat_id: int, user_id: int, now: int) -> list[int]:
    q = _seen.pop((chat_id, user_id), None)
    return [m for m, ts in (q or ()) if now - ts < WINDOW]


async def wipe(bot, chat_id: int, user_id: int, now: int) -> int:
    ids = take(chat_id, user_id, now)
    done = 0
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        try:
            await bot.delete_messages(chat_id, batch)
            done += len(batch)
        except Exception:
            logging.warning("вайп: не удалось удалить пачку сообщений")
    return done
