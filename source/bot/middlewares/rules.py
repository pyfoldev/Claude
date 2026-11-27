"""Правила чата поверх защиты: удаление по типу сообщения, триггеры «событие → наказание», блок стикеров,
FAQ-ответы, служебные сообщения; фейс-контроль новичков и наказание за быстрый выход.

Админы, модераторы с рангом и «доверенные» (белый список) правилами не затрагиваются."""
from __future__ import annotations

import asyncio
import html
import logging
import time
from datetime import timedelta

from aiogram import BaseMiddleware
from aiogram.types import ChatMemberUpdated, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import mod_service as ms
from bot import rules, wipe
from bot.db import Database
from bot.emoji import emoji
from bot.keyboards import undo_keyboard
from bot.middlewares.guard import AdminCache, channel_sender
from bot.middlewares.tracker import SERVICE_IDS
from bot.parsing import ModCommand

CACHE_TTL = 30
NOTICE_EVERY = 30
FAQ_COOLDOWN = 60
_cache: dict[int, tuple[float, dict]] = {}
_notices: dict[tuple[int, int], float] = {}
_faq_last: dict[tuple[int, int], float] = {}
_PUNISH_NAME = {"warn": "варн", "mute": "мут", "kick": "кик", "ban": "бан"}


def invalidate(chat_id: int) -> None:
    """Команды, меняющие правила чата, сбрасывают кэш: изменение действует сразу."""
    _cache.pop(chat_id, None)


async def chat_rules(db: Database, chat_id: int) -> dict:
    hit = _cache.get(chat_id)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    data = {"triggers": await db.list_triggers(chat_id), "blocked": await db.blocked_stickers(chat_id),
            "faq": await db.list_faq(chat_id)}
    data["by_event"] = {}
    for t in data["triggers"]:
        data["by_event"].setdefault(t["event"], []).append(t)
    if len(_cache) > 3000:
        _cache.clear()
    _cache[chat_id] = (time.time(), data)
    return data


def sticker_keys(m) -> list[tuple[str, str]]:
    st = getattr(m, "sticker", None)
    if st is None:
        return []
    out = [("sticker", st.file_unique_id)]
    if getattr(st, "set_name", None):
        out.append(("set", st.set_name))
    return out


class RulesMiddleware(BaseMiddleware):
    def __init__(self, db: Database):
        self.db = db
        self.admins = AdminCache()
        self._tasks: set[asyncio.Task] = set()

    def _spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    def _notice_allowed(self, chat_id: int, user_id: int) -> bool:
        now = time.time()
        if now - _notices.get((chat_id, user_id), 0) < NOTICE_EVERY:
            return False
        if len(_notices) > 5000:
            for k in [k for k, t in _notices.items() if now - t >= NOTICE_EVERY]:
                _notices.pop(k, None)
        _notices[(chat_id, user_id)] = now
        return True

    async def _delete(self, bot, m: Message) -> bool:
        try:
            await bot.delete_message(m.chat.id, m.message_id)
            return True
        except Exception:
            logging.warning("rules: не смог удалить сообщение (нет права удалять?)")
            return False

    async def __call__(self, handler, m: Message, data):
        if m.chat.type not in ("group", "supergroup"):
            return await handler(m, data)
        s = await self.db.get_settings(m.chat.id)
        bot = data["bot"]
        if s["del_service"] and (m.new_chat_members or m.left_chat_member or m.pinned_message or m.new_chat_title
                                 or m.new_chat_photo or m.delete_chat_photo or m.video_chat_started
                                 or m.video_chat_ended or m.video_chat_participants_invited):
            self._spawn(self._delete(bot, m))
        if s["unpin_channel"] and m.pinned_message is not None and getattr(m.pinned_message, "is_automatic_forward", False):
            self._spawn(self._unpin(bot, m))                 # пост канала закрепился в обсуждении — убираем
        u = m.from_user
        if channel_sender(m) is not None or not u or u.is_bot or u.id in SERVICE_IDS \
                or getattr(m, "is_automatic_forward", False):
            return await handler(m, data)
        now = int(time.time())
        wipe.remember(m.chat.id, u.id, m.message_id, now)
        text = m.text or m.caption or ""
        rules = await chat_rules(self.db, m.chat.id)

        # FAQ отвечает всем, в том числе админам
        if text and rules["faq"] and not text.startswith(("/", "!", ".")):
            hit = rules_faq(text, rules["faq"])
            if hit and time.time() - _faq_last.get((m.chat.id, hit["id"]), 0) >= FAQ_COOLDOWN:
                _faq_last[(m.chat.id, hit["id"])] = time.time()
                self._spawn(self._answer_faq(bot, m, hit))

        events = rules_events(m)
        flagged = {e for e in events if (rules_key(e) and s.get(rules_key(e))) or e in rules["by_event"]}
        blocked = bool(rules["blocked"] and any(k in rules["blocked"] for k in sticker_keys(m)))
        cmd_delete = bool(s["del_cmds"] and text.startswith("/"))
        if not flagged and not blocked and not cmd_delete:
            return await handler(m, data)
        if await self._exempt(bot, m.chat.id, u.id):
            return await handler(m, data)

        if cmd_delete:                                       # сначала команда выполняется, потом сообщение убирается
            res = await handler(m, data)
            await self._delete(bot, m)
            return res
        trig = rules_strongest([t for e in flagged for t in rules["by_event"].get(e, [])])
        silent_del = blocked or any(s.get(rules_key(e)) for e in flagged if rules_key(e))
        if trig is None:
            if silent_del:
                await self._delete(bot, m)
                return None
            return await handler(m, data)
        deleted = await self._delete(bot, m)
        if trig["action"] != "delete":
            self._spawn(self._punish(bot, m, trig, now))
        elif not deleted:
            return await handler(m, data)
        return None

    async def _unpin(self, bot, m: Message) -> None:
        try:
            await bot.unpin_chat_message(m.chat.id, m.pinned_message.message_id)
        except Exception:
            logging.warning("rules: не смог открепить пост канала (нет права закреплять?)")

    async def _exempt(self, bot, chat_id: int, user_id: int) -> bool:
        if await self.admins.is_admin(bot, chat_id, user_id):
            return True
        if await self.db.get_rank(chat_id, user_id) > 0:
            return True
        return await self.db.is_trusted(chat_id, user_id)

    async def _punish(self, bot, m: Message, trig: dict, now: int) -> None:
        reason = trig["reason"] or f"триггер «{trig['event']}»"
        cmd = ModCommand(_PUNISH_NAME[trig["action"]], None, timedelta(seconds=trig["secs"]) if trig["secs"] else None, reason)
        try:
            text = await ms.apply(bot, self.db, cmd, m.chat.id, (await bot.me()).id, m.from_user.id, now, gif=False)
            if not self._notice_allowed(m.chat.id, m.from_user.id):
                return
            undo = {"warn": "warn", "mute": "mute", "ban": "ban"}.get(trig["action"])
            await bot.send_message(m.chat.id, text,
                                   reply_markup=undo_keyboard(undo, m.from_user.id) if undo else None)
        except Exception:
            logging.exception("rules: триггер не сработал (у бота нет прав?)")

    async def _answer_faq(self, bot, m: Message, item: dict) -> None:
        text, buttons = rules.split_faq_answer(item["answer"])
        kb = InlineKeyboardMarkup(inline_keyboard=[[B(text=t, url=u)] for t, u in buttons]) if buttons else None
        try:
            try:
                await bot.send_message(m.chat.id, text or "…", reply_markup=kb, reply_to_message_id=m.message_id)
            except Exception:                                # неверная HTML-разметка в ответе — шлём как есть
                await bot.send_message(m.chat.id, html.escape(text) or "…", reply_markup=kb,
                                       reply_to_message_id=m.message_id)
        except Exception:
            logging.warning("rules: FAQ-ответ не отправился")


# тонкие обёртки: так проще подменять в тестах
def rules_events(m) -> set[str]:
    return rules.detect_events(m)


def rules_key(event: str) -> str | None:
    return rules.EVENTS.get(event)


def rules_strongest(triggers: list[dict]) -> dict | None:
    return rules.strongest(triggers)


def rules_faq(text: str, items: list[dict]) -> dict | None:
    return rules.faq_match(text, items)


class MembershipMiddleware(BaseMiddleware):
    """chat_member: фейс-контроль при входе и наказание за быстрый выход. Остальным обработчикам событие передаётся."""

    def __init__(self, db: Database):
        self.db = db

    async def __call__(self, handler, ev: ChatMemberUpdated, data):
        try:
            res = await self._check(ev, data["bot"])
        except Exception:
            logging.exception("rules: проверка участника не удалась")
            res = False
        if res:
            return None            # участник наказан: капча и приветствие для него не нужны
        return await handler(ev, data)

    async def _check(self, ev: ChatMemberUpdated, bot) -> bool:
        if ev.chat.type not in ("group", "supergroup"):
            return False
        old, new = ev.old_chat_member.status, ev.new_chat_member.status
        user = ev.new_chat_member.user
        if user.is_bot:
            return False
        s = await self.db.get_settings(ev.chat.id)
        now = int(time.time())
        joined = old in ("left", "kicked") and new in ("member", "restricted")
        left = old in ("member", "restricted") and new == "left" and ev.from_user.id == user.id
        if left and s["leave_wipe"]:                         # ушёл сам — убираем его свежие сообщения
            await wipe.wipe(bot, ev.chat.id, user.id, now)
        if joined and s["fc_on"]:
            return await face_control(bot, self.db, ev.chat.id, user, s, now)
        if left and s["leave_on"]:
            at = await self.db.member_joined_at(ev.chat.id, user.id)
            if at is not None and 0 <= now - at <= s["leave_sec"]:
                reason = "быстрый выход из чата"
                cmd = ModCommand("бан", None, timedelta(hours=s["leave_hours"]) if s["leave_hours"] else None, reason)
                await ms.apply(bot, self.db, cmd, ev.chat.id, (await bot.me()).id, user.id, now, gif=False)
                return True
        return False


async def face_control(bot, db: Database, chat_id: int, user, s: dict, now: int) -> bool:
    """Проверка новичка по профилю. True — не прошёл и наказан."""
    if await db.is_trusted(chat_id, user.id):
        return False
    has_photo = None
    if s["fc_photo"]:
        try:
            has_photo = (await bot.get_user_profile_photos(user.id, limit=1)).total_count > 0
        except Exception:
            has_photo = None                                 # не знаем — не наказываем
    reasons = rules.face_reasons(user, s, has_photo, now)
    if not reasons:
        return False
    action = {"ban": "бан", "mute": "мут"}.get(s["fc_action"], "кик")
    cmd = ModCommand(action, None, None, "фейс-контроль: " + ", ".join(reasons))
    try:
        text = await ms.apply(bot, db, cmd, chat_id, (await bot.me()).id, user.id, now, gif=False)
        await bot.send_message(chat_id, f"{emoji('fail')} {text}")
    except Exception:
        logging.warning("фейс-контроль: не удалось применить наказание (нет прав?)")
        return False
    return True
