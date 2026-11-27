"""Защита чата: антиспам по тексту и фильтр 18+ по медиа. Нарушителю сообщение удаляется и до хендлеров не доходит."""
from __future__ import annotations

import asyncio
import html
import logging
import time
from collections import deque

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot import mod_service as ms
from bot import nsfw as nsfw_mod
from bot import guestbots, phishing
from bot.aimod import CATEGORY_RU, Cache, prefilter
from bot.emoji import emoji
from bot.filters import FilterSet
from bot.keyboards import undo_keyboard
from bot.links import extract_hosts, host_allowed
from bot.db import Database
from bot.middlewares.tracker import SERVICE_IDS
from bot.spam import MsgInfo, SpamGuard

NEWBIE_SECONDS = 86400
NEWBIE_AI_MESSAGES = 5      # ИИ-проверка новичка: столько его первых сообщений смотрит ИИ
NEWBIE_AI_DAILY = 200       # лимит таких проверок в сутки на чат
NEWBIE_AI_CONF = 80         # с какой уверенности ИИ наказываем (%)
NEWBIE_AI_BAD = {"spam", "scam", "ads", "adult"}   # что ищем у новичков; оскорбления и угрозы — дело ИИ-модерации
NEWBIE_AI_MIN_LEN = 6
NOTICE_TTL = 0          # 0 — сообщения бота сами не удаляются
UNDO_NOTICE_TTL = 0   # уведомление о муте/варне с кнопкой «Отменить» живёт дольше, чтобы модератор успел
NSFW_AI_LOW = 25        # ниже — явно безопасно, ИИ не зовём
NSFW_AI_DAILY = 100     # лимит внешних проверок картинок в сутки на чат
AIMOD_DAILY = 300       # лимит ИИ-проверок текста в сутки на чат
AIMOD_NOTICE_TTL = 0  # сколько живёт уведомление с кнопкой «Это ошибка»
CHANNEL_BOT_ID = 136817688   # Channel_Bot: так Telegram подписывает сообщения, отправленные «от имени канала»
LINKED_TTL = 600        # сколько помним привязанный к группе канал обсуждений
NOTICE_EVERY = 30       # уведомление «сообщение удалено» одному нарушителю — не чаще раза в 30 с (иначе бот сам флудит)


def channel_sender(m: Message) -> int | None:
    """id канала, от имени которого участник написал в группу (кнопка «отправить как канал»), иначе None.
    Автопересылки из привязанного канала и анонимные админы (sender_chat = сама группа) сюда не попадают."""
    u, sc = m.from_user, getattr(m, "sender_chat", None)
    if u is None or u.id != CHANNEL_BOT_ID or sc is None or sc.id == m.chat.id:
        return None
    if getattr(m, "is_automatic_forward", False):
        return None
    return sc.id


class AdminCache:
    def __init__(self, ttl: float = 120):
        self.ttl = ttl
        self._c: dict[tuple[int, int], tuple[float, bool]] = {}

    def prune(self) -> None:
        now = time.time()
        for k in [k for k, v in self._c.items() if now - v[0] >= self.ttl]:
            self._c.pop(k, None)

    async def is_admin(self, bot, chat_id: int, user_id: int) -> bool:
        hit = self._c.get((chat_id, user_id))
        if hit and time.time() - hit[0] < self.ttl:
            return hit[1]
        try:
            val = await ms.is_admin(bot, chat_id, user_id)
        except Exception:
            return True  # не смогли проверить — на всякий случай не наказываем
        self._c[(chat_id, user_id)] = (time.time(), val)
        return val


def describe(m: Message, allow: set[str] | None = None) -> MsgInfo:
    text = m.text or m.caption or ""
    ents = (m.entities or []) + (m.caption_entities or [])
    allow = allow or set()
    links = sum(1 for h in extract_hosts(text, ents) if not host_allowed(h, allow))  # без белого списка чата
    mentions = sum(1 for e in ents if e.type in ("mention", "text_mention"))
    return MsgInfo(text, links, mentions, getattr(m, "forward_origin", None) is not None,
                   getattr(m, "media_group_id", None))


class GuardMiddleware(BaseMiddleware):
    def __init__(self, db: Database, spam: SpamGuard | None = None, detector=None, ai=None, rt=None):
        self.db = db
        self.rt = rt
        self.spam = spam or SpamGuard()
        self.detector = detector
        self.ai = ai
        self.admins = AdminCache()
        self._tasks: set[asyncio.Task] = set()
        self._nsfw_sem = asyncio.Semaphore(2)       # не больше двух проверок картинок одновременно
        self._nsfw_cache: dict[str, float] = {}     # file_unique_id -> оценка
        self._nsfw_ai_cache: dict[str, bool] = {}   # file_unique_id -> вердикт ИИ
        self._ai_seen: dict[tuple[int, int], int] = {}
        self._aimod_cache = Cache()
        self._newbie_cache = Cache()
        self._filters: dict[int, tuple[int, FilterSet]] = {}   # чат -> (версия списка, скомпилированные фильтры)
        self._allow: dict[int, tuple[int, set[str]]] = {}       # чат -> (версия, белый список доменов)
        self._linked: dict[int, tuple[float, int | None]] = {}  # чат -> (когда узнали, id привязанного канала)
        self._guest_times: dict[tuple[int, int], deque] = {}      # (чат, вызывающий) -> когда отвечали гостевые боты
        self._guest_strikes: dict[tuple[int, int], deque] = {}    # (чат, вызывающий) -> когда удаляли сообщения гостевых ботов
        self._noticed: dict[tuple[int, int], float] = {}         # (чат, нарушитель) -> когда последний раз писали

    def _notice_allowed(self, chat_id: int, sender: int) -> bool:
        now = time.time()
        if now - self._noticed.get((chat_id, sender), 0) < NOTICE_EVERY:
            return False
        if len(self._noticed) > 5000:
            for k in [k for k, t in self._noticed.items() if now - t >= NOTICE_EVERY]:
                self._noticed.pop(k, None)
        self._noticed[(chat_id, sender)] = now
        return True

    def prune(self) -> None:
        self.spam.prune(time.time())
        self.admins.prune()
        if len(self._ai_seen) > 5000:
            self._ai_seen.clear()
        self._linked.clear()
        now = int(time.time())
        for d in (self._guest_times, self._guest_strikes):
            for k in [k for k, q in d.items() if not q or now - q[-1] > 3600]:
                d.pop(k, None)

    async def _is_linked_channel(self, bot, chat_id: int, channel_id: int) -> bool:
        """Канал обсуждений группы пишет от своего имени законно (это делают админы канала)."""
        hit = self._linked.get(chat_id)
        if hit is None or time.time() - hit[0] >= LINKED_TTL:
            try:
                linked = getattr(await bot.get_chat(chat_id), "linked_chat_id", None)
            except Exception:
                return True   # не смогли проверить — не наказываем (как и с админами)
            hit = (time.time(), linked)
            self._linked[chat_id] = hit
        return hit[1] == channel_id

    async def _filter_set(self, chat_id: int) -> FilterSet:
        v = self.db.lists_version(chat_id)
        hit = self._filters.get(chat_id)
        if hit is None or hit[0] != v:
            hit = (v, FilterSet(await self.db.list_filters(chat_id)))
            self._filters[chat_id] = hit
        return hit[1]

    async def _allow_set(self, chat_id: int) -> set[str]:
        v = self.db.lists_version(chat_id)
        hit = self._allow.get(chat_id)
        if hit is None or hit[0] != v:
            hit = (v, await self.db.link_allow_set(chat_id))
            self._allow[chat_id] = hit
        return hit[1]

    async def _guest(self, m: Message, data) -> bool:
        """Сообщение гостевого бота. True — сообщение удалено (дальше не идёт)."""
        s = await self.db.get_settings(m.chat.id)
        mode = s.get("guest_mode", "check")
        if mode == "off":
            return False
        bot, chat, now = data["bot"], m.chat.id, int(time.time())
        gb, caller = m.from_user, m.guest_bot_caller_user
        bid = gb.id if gb is not None else (m.sender_chat.id if m.sender_chat else 0)
        uname = (gb.username if gb is not None else None) or (m.sender_chat.username if m.sender_chat else None)
        status = await self.db.guest_seen(chat, bid, uname, now)
        if status == guestbots.STATUS_ALLOWED:
            return False                                           # доверенный бот — без проверок
        exempt = False
        if caller is not None:
            exempt = await self.admins.is_admin(bot, chat, caller.id) or await self.db.get_rank(chat, caller.id) > 0
        reason = None
        if status == guestbots.STATUS_BLOCKED:
            reason = "бот запрещён в этом чате"
        elif exempt:
            return False
        elif mode == "block":
            reason = "гостевые боты запрещены"
        elif mode == "allowlist":
            reason = "бота нет в белом списке"
        else:
            reason = await self._guest_content(m, s, caller.id if caller is not None else bid, now)
        if reason is None:
            return False
        await self._guest_violation(bot, m, reason, uname, caller, now)
        return True

    async def _guest_content(self, m: Message, s: dict, who: int, now: int) -> str | None:
        times = self._guest_times.setdefault((m.chat.id, who), deque())
        times.append(now)
        while times and now - times[0] >= guestbots.FLOOD_SEC:
            times.popleft()
        if len(times) > guestbots.FLOOD_N:
            return "флуд гостевыми ботами"
        text = m.text or m.caption or ""
        if not text:
            return None
        filters = await self._filter_set(m.chat.id)
        if filters and filters.first_match(text) is not None:
            return "запрещённое слово"
        if s["phish_on"]:
            reason = await self._phishing(m, text, s)
            if reason:
                return f"фишинг: {reason}"
        if s["links_mode"] == "all":
            info = describe(m, await self._allow_set(m.chat.id))
            if info.links > 0:
                return "ссылка не из белого списка"
        return None

    async def _guest_violation(self, bot, m: Message, reason: str, uname: str | None, caller, now: int) -> None:
        try:
            await bot.delete_message(m.chat.id, m.message_id)
        except Exception:
            logging.warning("guard: не смог удалить сообщение гостевого бота (нет права удалять?)")
            return
        who = caller.id if caller is not None else 0
        try:
            await self.db.log_action(m.chat.id, (await bot.me()).id, who or None, "удаление", f"гостевой бот: {reason}", now)
            if self._notice_allowed(m.chat.id, who or -1):
                name = f"@{html.escape(uname)}" if uname else "гостевого бота"
                notice = await bot.send_message(m.chat.id, f"{emoji('fail')} Сообщение {name} удалено ({html.escape(reason)})")
                self._spawn(self._delete_later(bot, m.chat.id, notice.message_id, NOTICE_TTL))
            if caller is not None:                                  # повторные нарушения — мут того, кто зовёт бота
                q = self._guest_strikes.setdefault((m.chat.id, caller.id), deque())
                q.append(now)
                while q and now - q[0] > guestbots.STRIKE_WINDOW:
                    q.popleft()
                if len(q) >= guestbots.STRIKES:
                    q.clear()
                    text = await ms.punish(bot, self.db, m.chat.id, caller.id, "mute", "злоупотребление гостевыми ботами", now)
                    notice = await bot.send_message(m.chat.id, text)
                    self._spawn(self._delete_later(bot, m.chat.id, notice.message_id, UNDO_NOTICE_TTL))
        except Exception:
            logging.exception("guard: уведомление о гостевом боте не отправилось")

    async def __call__(self, handler, m: Message, data):
        if m.chat.type in ("group", "supergroup") and guestbots.is_guest_message(m):
            if await self._guest(m, data):
                return None
            return await handler(m, data)
        u = m.from_user
        channel = channel_sender(m) if m.chat.type in ("group", "supergroup") else None
        if channel is None and (m.chat.type not in ("group", "supergroup") or not u or u.is_bot
                                or u.id in SERVICE_IDS or getattr(m, "is_automatic_forward", False)):
            return await handler(m, data)
        s = await self.db.get_settings(m.chat.id)
        media_check = bool(s["nsfw_on"] and self.detector and (self.rt is None or self.rt.flag("nsfw"))
                           and nsfw_mod.has_checkable_media(m))
        text_now = m.text or m.caption or ""
        filters = await self._filter_set(m.chat.id) if text_now else None
        aimod_wanted = bool(text_now and s["ai_mod"] != "off" and self.ai is not None
                            and hasattr(self.ai, "moderate") and (self.rt is None or self.rt.flag("aimod")))
        if not (s["spam_on"] or s["phish_on"] or media_check or filters or aimod_wanted):
            return await handler(m, data)
        bot = data["bot"]
        if channel is not None:
            # «от имени канала»: у канала нет статуса админа и ранга, а раньше такие сообщения проходили мимо всей защиты
            if await self._is_linked_channel(bot, m.chat.id, channel):
                return await handler(m, data)
            sender, ranked = channel, False
        else:
            if await self.admins.is_admin(bot, m.chat.id, u.id):
                return await handler(m, data)
            sender = u.id
            ranked = ((await self.db.get_rank(m.chat.id, u.id) > 0 or await self.db.is_trusted(m.chat.id, u.id))
                      if (filters or aimod_wanted or s["spam_on"] or s["phish_on"]) else False)   # «доверенные» — как модераторы
        now = int(time.time())

        if filters and not ranked:                                     # модераторов с рангом фильтры не трогают
            if filters.first_match(text_now) is not None:
                await self._violation(bot, m, s["filter_action"], "запрещённое слово", now)
                return None

        if s["phish_on"] and not ranked and text_now:                  # фишинговые ссылки — для всех, кроме модераторов
            reason = await self._phishing(m, text_now, s)
            if reason:
                await self._violation(bot, m, s["phish_action"], f"фишинг: {reason}", now)
                return None

        newbie = None
        aimod_go = False
        if s["spam_on"] and not ranked:                                # модераторам с рангом антиспам не мешает:
            newbie = await self._is_newbie(m.chat.id, sender, channel, now)   # иначе «+ссылка домен» удалялась бы как ссылка
            info = describe(m, await self._allow_set(m.chat.id) if s["links_mode"] != "off" else None)
            reason = self.spam.check(m.chat.id, sender, info, now, s, newbie)
            if reason:
                await self._violation(bot, m, s["spam_action"], reason, now)
                return None
        if aimod_wanted and not ranked:
            if newbie is None:
                newbie = await self._is_newbie(m.chat.id, sender, channel, now)
            aimod_go = prefilter(text_now, newbie, s["ai_mod"])
            if aimod_go:
                self._spawn(self._aimod_job(bot, m, s, text_now, now))   # в фоне: сообщение не ждёт ответа ИИ
        if (newbie and s["spam_on"] and s["spam_ai"] and not aimod_go and len(text_now.strip()) >= NEWBIE_AI_MIN_LEN
                and self.ai is not None and hasattr(self.ai, "moderate") and (self.rt is None or self.rt.flag("ai"))):
            key = (m.chat.id, sender)                                  # ИИ-проверка первых сообщений новичка — тоже в фоне
            if self._ai_seen.get(key, 0) < NEWBIE_AI_MESSAGES:
                self._ai_seen[key] = self._ai_seen.get(key, 0) + 1
                self._spawn(self._newbie_ai_job(bot, m, s, text_now, sender, channel, now))
        if media_check:
            self._spawn(self._nsfw_job(bot, m, s, now))
        return await handler(m, data)

    async def _phishing(self, m: Message, text: str, s: dict) -> str | None:
        ents = (m.entities or []) + (m.caption_entities or [])
        allow = await self._allow_set(m.chat.id)
        hosts = {h for h in extract_hosts(text, ents) if not host_allowed(h, allow)}
        if not hosts:
            return None
        reason = phishing.assess_many(hosts)
        session = getattr(self.ai, "session", None)
        if reason is None and session is not None and await phishing.safe_browsing(session, [f"http://{h}/" for h in sorted(hosts)]):
            reason = "ссылка в базе Google Safe Browsing"
        return reason

    async def _is_newbie(self, chat_id: int, sender: int, channel: int | None, now: int) -> bool:
        if channel is not None:
            return True    # канал не «вступает» в группу: правила для новичков (ссылки, пересылки) действуют всегда
        joined = await self.db.member_joined_at(chat_id, sender)
        return joined is not None and now - joined < NEWBIE_SECONDS

    async def _channel_violation(self, bot, m: Message, reason: str, now: int) -> None:
        """Сообщение от имени канала: ограничить канал как участника нельзя, поэтому только удаляем и сообщаем."""
        try:
            await bot.delete_message(m.chat.id, m.message_id)
        except Exception:
            logging.warning("guard: не смог удалить сообщение канала (нет права удалять?)")
            return
        sc = m.sender_chat
        title = html.escape(sc.title or sc.username or str(sc.id))
        try:
            await self.db.log_action(m.chat.id, (await bot.me()).id, sc.id, "удаление", f"канал: {reason}", now)
            if not self._notice_allowed(m.chat.id, sc.id):
                return
            notice = await bot.send_message(m.chat.id, f"{emoji('fail')} Сообщение от канала «{title}» удалено "
                                                       f"({html.escape(reason)})")
            self._spawn(self._delete_later(bot, m.chat.id, notice.message_id, NOTICE_TTL))
        except Exception:
            logging.exception("guard: уведомление о канале не отправилось")

    def _spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def _violation(self, bot, m: Message, action: str, reason: str, now: int) -> None:
        if channel_sender(m) is not None:
            await self._channel_violation(bot, m, reason, now)
            return
        try:
            await bot.delete_message(m.chat.id, m.message_id)
        except Exception:
            logging.warning("guard: не смог удалить сообщение (нет права удалять?)")
            if action == "delete":
                return  # ничего не удалили — не пишем «сообщение удалено»
        try:
            text = await ms.punish(bot, self.db, m.chat.id, m.from_user.id, action, reason, now)
            undo = {"warn": "warn", "mute": "mute"}.get(action)
            if undo is None and not self._notice_allowed(m.chat.id, m.from_user.id):
                return   # удалено и записано в журнал; повторное «удалено» тому же человеку не пишем
            notice = await bot.send_message(m.chat.id, text, reply_markup=undo_keyboard(undo, m.from_user.id) if undo else None)
            self._spawn(self._delete_later(bot, m.chat.id, notice.message_id, UNDO_NOTICE_TTL if undo else NOTICE_TTL))
        except Exception:
            logging.exception("guard: наказание не применилось")

    async def _author_context(self, m: Message, sender: int, channel: int | None, now: int) -> str:
        """Признаки автора для ИИ: спамеры обычно — свежие аккаунты без юзернейма, сразу со ссылкой."""
        from bot.mog import registered_at
        parts = []
        joined = None if channel is not None else await self.db.member_joined_at(m.chat.id, sender)
        if channel is not None:
            parts.append("пишет от имени канала")
        elif joined is not None:
            mins = max((now - joined) // 60, 0)
            parts.append(f"в чате {mins} мин" if mins < 120 else f"в чате {mins // 60} ч")
        if channel is None and m.from_user is not None:
            days = max((now - registered_at(sender, now)) // 86400, 0)
            parts.append(f"аккаунт Telegram ≈{days} дн. (оценка)" if days < 365 else f"аккаунт Telegram ≈{days // 365} г.")
            parts.append("юзернейм есть" if m.from_user.username else "без юзернейма")
            if getattr(m.from_user, "is_premium", False):
                parts.append("Telegram Premium")
        info = describe(m)
        if info.links:
            parts.append(f"ссылок: {info.links}")
        if info.mentions:
            parts.append(f"упоминаний: {info.mentions}")
        if info.forwarded:
            parts.append("сообщение переслано")
        if m.photo or m.video or m.document:
            parts.append("с вложением")
        return "; ".join(parts)

    async def _newbie_ai_job(self, bot, m: Message, s: dict, text: str, sender: int, channel: int | None, now: int) -> None:
        """ИИ-проверка новичка: первые сообщения недавно вошедшего — на спам, рекламу, мошенничество и 18+ (с учётом
        признаков автора). Нарушение — действие антиспама; модератору — кнопка «Это ошибка»."""
        try:
            context = await self._author_context(m, sender, channel, now)
            res = self._newbie_cache.get(text, context)
            if res is None:
                if not await self.db.take_quota(m.chat.id, "newbieai", now, NEWBIE_AI_DAILY):
                    return
                res = await self.ai.moderate(text, context)
                if res is None:                                    # сбой или мусор — fail-open, лимит возвращаем
                    await self.db.refund_quota(m.chat.id, "newbieai", now)
                    return
                self._newbie_cache.put(text, res, context)
            if res.category not in NEWBIE_AI_BAD or res.confidence * 100 < NEWBIE_AI_CONF:
                return
            await self._aimod_violation(bot, m, s["spam_action"], res, text, now, source="ИИ-проверка новичка")
        except Exception:
            logging.exception("newbie ai job failed")

    async def _aimod_job(self, bot, m: Message, s: dict, text: str, now: int) -> None:
        try:
            res = self._aimod_cache.get(text)
            if res is None:
                if not await self.db.take_quota(m.chat.id, "aimod", now, AIMOD_DAILY):
                    return
                res = await self.ai.moderate(text)
                if res is None:                                    # ошибка/таймаут: fail-open и не тратим лимит
                    await self.db.refund_quota(m.chat.id, "aimod", now)
                    return
                self._aimod_cache.put(text, res)
            if res.category == "ok" or res.confidence * 100 < s["ai_mod_conf"]:
                return
            await self._aimod_violation(bot, m, s["ai_mod_action"], res, text, now)
        except Exception:
            logging.exception("aimod job failed")

    async def _aimod_violation(self, bot, m: Message, action: str, res, text: str, now: int, source: str = "ИИ") -> None:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        from bot.handlers.reports import post_report_card
        reason = f"{source}: {CATEGORY_RU.get(res.category, res.category)} ({int(res.confidence * 100)}%)" + (
            f" — {res.explain}" if res.explain else "")
        chat, uid = m.chat.id, m.from_user.id
        # Маркер связывает наказание с конкретным сообщением для безопасной отмены.
        reason += f" [ai-msg:{m.message_id}]"
        channel = channel_sender(m)
        if action == "report":                                     # без наказания: только жалоба модераторам
            name = (m.sender_chat.title or str(channel)) if channel is not None else m.from_user.full_name
            await post_report_card(bot, self.db, chat, (await bot.me()).id, "🤖 ИИ-модерация", channel or uid,
                                   name, m.message_id, text[:300], reason, now)
            return
        if channel is not None:
            await self._channel_violation(bot, m, reason, now)
            return
        try:
            await bot.delete_message(chat, m.message_id)
        except Exception:
            logging.warning("aimod: не смог удалить сообщение (нет права удалять?)")
            if action == "delete":
                return
        notice_text = await ms.punish(bot, self.db, chat, uid, action, reason, now)
        eid = await self.db.add_aimod_event(chat, uid, m.message_id, res.category, int(res.confidence * 100),
                                            action, text, now)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Это ошибка", callback_data=f"aimod:{eid}")]])
        notice = await bot.send_message(chat, notice_text, reply_markup=kb)
        self._spawn(self._delete_later(bot, chat, notice.message_id, AIMOD_NOTICE_TTL))

    async def _ai_second_opinion(self, bot, m: Message, key: str | None, images: list[bytes] | None,
                                 now: int) -> bool:
        """Для сомнительной оценки спрашиваем мультимодальный ИИ. Сбой/лимит/«безопасно» = не нарушение."""
        if key and key in self._nsfw_ai_cache:
            return self._nsfw_ai_cache[key]
        if not await self.db.take_quota(m.chat.id, "nsfwai", now, NSFW_AI_DAILY):
            return False
        if images is None:
            async with self._nsfw_sem:
                images = await nsfw_mod.images_from_message(bot, m)
        if not images:
            return False
        verdict = await self.ai.vision_is_nsfw(images[0]) is True
        if key:
            if len(self._nsfw_ai_cache) > 1000:
                self._nsfw_ai_cache.clear()
            self._nsfw_ai_cache[key] = verdict
        return verdict

    async def _delete_later(self, bot, chat_id: int, message_id: int, ttl: float = NOTICE_TTL) -> None:
        if not ttl:                                      # бот свои сообщения не удаляет
            return
        await asyncio.sleep(ttl)
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            pass

    async def _nsfw_job(self, bot, m: Message, s: dict, now: int) -> None:
        try:
            key = nsfw_mod.media_key(m)
            score = self._nsfw_cache.get(key) if key else None
            images: list[bytes] | None = None
            if score is None:
                async with self._nsfw_sem:
                    images = await nsfw_mod.images_from_message(bot, m)
                    score = await self.detector.score_images(images)
                if key:
                    if len(self._nsfw_cache) > 1000:
                        self._nsfw_cache.clear()
                    self._nsfw_cache[key] = score
            threshold = s["nsfw_threshold"]
            if NSFW_AI_LOW <= score < threshold and s.get("nsfw_ai") and self.ai is not None \
                    and hasattr(self.ai, "vision_is_nsfw"):
                if await self._ai_second_opinion(bot, m, key, images, now):
                    score = float(threshold)
            logging.info("nsfw: чат %s, оценка %.1f%% (порог %s%%), %s", m.chat.id, score, s["nsfw_threshold"],
                         "нарушение" if score >= s["nsfw_threshold"] else "ок")
            if score >= s["nsfw_threshold"]:
                await self._violation(bot, m, s["nsfw_action"], f"18+ контент ({int(score)}%)", now)
        except Exception:
            logging.exception("nsfw job failed")
