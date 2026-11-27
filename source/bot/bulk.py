"""Массовый бан списка людей: id и @ники вперемешку.

Неизвестный бот ник не отклоняется: если Telegram не отдаёт его id, бан запоминается («отложенный бан») и
выполняется, как только бот впервые увидит этого человека (см. fulfil_pending и bot.middlewares.tracker).
Неизвестный числовой id банится сразу — Telegram банит по id и без знакомства — а бот запоминает его в базе."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from bot import mod_service as ms
from bot.db import Database
from bot.parsing import ModCommand

MAX_BULK = 50
CONCURRENCY = 3
_SPLIT = re.compile(r"[\s,;]+")
_ID_RE = re.compile(r"^\d{5,15}$")
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
_TME_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:t|telegram)\.me/([A-Za-z][A-Za-z0-9_]{3,31})/?$", re.IGNORECASE)


class BulkError(ValueError):
    pass


@dataclass(frozen=True)
class Target:
    raw: str
    uid: int | None = None
    name: str | None = None       # ник без @, в нижнем регистре


@dataclass
class Outcome:
    target: str
    status: str                   # ok | pending | skipped | failed
    detail: str
    user_id: int | None = None
    name: str = ""


def parse_targets(raw) -> tuple[list[Target], list[str]]:
    """Строка (через пробел/запятую/перевод строки) или список → (цели без повторов, нераспознанные куски).
    Распознаёт: 123456789, @ник, ник, t.me/ник."""
    if isinstance(raw, str):
        tokens = _SPLIT.split(raw.strip())
    elif isinstance(raw, list) and all(isinstance(x, (str, int)) and not isinstance(x, bool) for x in raw):
        tokens = [t for x in raw for t in _SPLIT.split(str(x).strip())]
    else:
        raise BulkError("Ожидался текст или список id и @ников")
    targets: list[Target] = []
    invalid: list[str] = []
    seen: set = set()
    for tok in tokens:
        if not tok:
            continue
        key: Target | None = None
        if _ID_RE.match(tok):
            key = Target(tok, uid=int(tok))
        else:
            m = _TME_RE.match(tok)
            name = m.group(1) if m else tok.lstrip("@")
            if (tok.startswith("@") or m or _NAME_RE.match(tok)) and _NAME_RE.match(name):
                key = Target(tok, name=name.lower())
        if key is None:
            invalid.append(tok[:40])
            continue
        ident = key.uid if key.uid is not None else key.name
        if ident in seen:
            continue
        seen.add(ident)
        targets.append(key)
    if len(targets) > MAX_BULK:
        raise BulkError(f"За один раз можно не больше {MAX_BULK} человек")
    return targets, invalid[:20]


async def _resolve_name(bot, db: Database, name: str) -> int | None:
    uid = await db.find_user(name)
    if uid is not None:
        return uid
    try:                                          # запасной путь: Telegram иногда отдаёт пользователя по нику
        chat = await bot.get_chat("@" + name)
        if chat.type == "private":
            await db.remember_user(chat.id, getattr(chat, "username", None) or name,
                                   getattr(chat, "full_name", None) or "@" + name)
            return chat.id
    except Exception:
        pass
    return None


async def _remember_id(bot, db: Database, uid: int) -> None:
    """Неизвестного человека запоминаем: настоящее имя, если Telegram его отдаёт, иначе «id…»."""
    if await db.user_name(uid) is not None:
        return
    name, username = f"id{uid}", None
    try:
        chat = await bot.get_chat(uid)
        name = getattr(chat, "full_name", None) or name
        username = getattr(chat, "username", None)
    except Exception:
        pass
    await db.remember_user(uid, username, name)


_ACTIONS = ("бан", "разбан", "мут", "кик")


async def _act_one(bot, db: Database, chat_id: int, actor: int, t: Target, action: str, reason: str,
                   duration: timedelta | None, now: int, owner: bool, protected: frozenset) -> Outcome:
    uid = t.uid if t.uid is not None else await _resolve_name(bot, db, t.name)
    if uid is None:
        if action != "бан":
            return Outcome(t.raw, "skipped", "Не нашёл такой ник. Пришлите id.")
        await db.add_pending_ban(chat_id, t.name, int(duration.total_seconds()) if duration else None,
                                 reason, actor, now, forced=owner)
        return Outcome(t.raw, "pending", "Запомнил — забаню, как только появится.")
    name = (await db.user_name(uid)) or f"id{uid}"
    if uid in protected:
        return Outcome(t.raw, "skipped", "Владельцев и самого бота трогать нельзя.", uid, name)
    if not owner:                         # владелец бота действует вне рангов чата; остальные — по правам и рангам
        ok, why = await ms.can_act(bot, chat_id, actor, uid, "restrict", db=db, command=action, allow_unknown=True)
        if not ok:
            return Outcome(t.raw, "skipped", why or "Недостаточно прав", uid, name)
    try:
        if t.uid is not None:
            await _remember_id(bot, db, uid)
        await ms.apply(bot, db, ModCommand(action, None, duration, reason), chat_id, actor, uid, now, gif=False)
    except Exception as e:                # у бота нет права, неверный id и т. п.
        return Outcome(t.raw, "failed", f"Не получилось: {e}"[:160], uid, name)
    return Outcome(t.raw, "ok", {"бан": "Забанен", "разбан": "Разбанен", "мут": "В муте", "кик": "Исключён"}[action],
                   uid, (await db.user_name(uid)) or name)


async def bulk_action(bot, db: Database, chat_id: int, actor: int, targets: list[Target], action: str,
                      reason: str, duration: timedelta | None, now: int, *, owner: bool = False,
                      protected: frozenset = frozenset()) -> list[Outcome]:
    """Действие (бан/разбан/мут/кик) над списком. owner=True — владелец бота: проверки рангов чата не нужны,
    защищены только owner_ids/бот (protected). Иначе права автора проверяются на «массовый бан» и на каждую цель.
    Порядок результатов — как в списке."""
    if action not in _ACTIONS:
        raise ValueError(action)
    if not owner:
        ok, why = await ms.can_act(bot, chat_id, actor, None, "restrict", db=db,
                                   command="массовый бан" if action == "бан" else action)
        if not ok:
            raise PermissionError(why or "Недостаточно прав")
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(t: Target) -> Outcome:
        async with sem:
            try:
                return await _act_one(bot, db, chat_id, actor, t, action, reason, duration, now, owner, protected)
            except Exception as e:
                logging.exception("bulk %s %s", action, t.raw)
                return Outcome(t.raw, "failed", f"Ошибка: {e}"[:160])
    return list(await asyncio.gather(*(one(t) for t in targets)))


async def bulk_ban(bot, db: Database, chat_id: int, actor: int, targets: list[Target],
                   reason: str, duration: timedelta | None, now: int) -> list[Outcome]:
    return await bulk_action(bot, db, chat_id, actor, targets, "бан", reason, duration, now)


async def fulfil_pending(bot, db: Database, uid: int, username: str, now: int) -> int:
    """Бот впервые увидел человека, на которого стоит отложенный бан: баним. Права автора проверяются заново —
    если его за это время понизили, бан не выполняется. Возвращает число выполненных."""
    done = 0
    for r in await db.pop_pending_bans(username, now):
        try:
            if uid == (await bot.me()).id:
                continue
            if not r.get("forced"):          # бан владельца бота выполняется без рангов чата
                ok, why = await ms.can_act(bot, r["chat_id"], r["actor"], uid, "restrict", db=db, command="бан",
                                           allow_unknown=True)
                if not ok:
                    logging.info("pending ban %s in %s skipped: %s", username, r["chat_id"], why)
                    continue
            await _remember_id(bot, db, uid)
            dur = timedelta(seconds=r["duration"]) if r["duration"] else None
            await ms.apply(bot, db, ModCommand("бан", None, dur, r["reason"] or "отложенный бан"),
                           r["chat_id"], r["actor"], uid, now, gif=False)
            done += 1
        except Exception:
            logging.exception("pending ban %s in %s failed", username, r["chat_id"])
    return done
