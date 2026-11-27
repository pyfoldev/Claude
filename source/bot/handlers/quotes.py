"""Цитатник: «+цитата» ответом на сообщение — карточка-картинка с аватаркой; «цитата», «цитата 5», «цитата @ник»,
«цитаты», «цитаты @ник», «-цитата 5». Выключается в настройках → «Команды»."""
from __future__ import annotations

import asyncio
import html
import re
import time
from datetime import datetime

from aiogram import F, Router
from aiogram.types import BufferedInputFile, Message

from bot import ux
from bot.toggles import Enabled
from bot import cards, media
from bot import mod_service as ms
from bot.db import Database
from bot.giveaway import tz_of
from bot.targets import listed

router = Router(name="quotes")
router.message.filter(Enabled("quotes_on"))   # группу команд можно выключить в настройках → «Команды»
MAX_QUOTE = 700
SHOW_COOLDOWN = 5          # «цитата» в одном чате — не чаще раза в 5 с
_last: dict[int, float] = {}

_ADD = re.compile(r"^\+(?:цитата|цитатка|quote)$", re.IGNORECASE)
_SHOW = re.compile(r"^цитата(?:\s+(\d{1,7}|@\w+))?$", re.IGNORECASE)
_LIST = re.compile(r"^цитаты(?:\s+(@\w+))?$", re.IGNORECASE)
_DEL = re.compile(r"^-цитата\s+(\d{1,7})$", re.IGNORECASE)


def _parse(text: str | None):
    t = (text or "").strip()
    for kind, rx in (("add", _ADD), ("show", _SHOW), ("list", _LIST), ("del", _DEL)):
        m = rx.match(t)
        if m:
            return kind, (m.group(1) if m.groups() else None)
    return None


def _author(reply: Message) -> tuple[int, str]:
    """Кого цитируем: у пересланного — исходного автора, у сообщения от имени канала — канал."""
    origin = getattr(reply, "forward_origin", None)
    if origin is not None:
        u = getattr(origin, "sender_user", None)
        if u is not None:
            return u.id, u.full_name
        name = getattr(origin, "sender_user_name", None)
        if name:
            return 0, name
        ch = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
        if ch is not None:
            return ch.id, ch.title or "канал"
    if reply.sender_chat is not None and reply.sender_chat.id != reply.chat.id:
        return reply.sender_chat.id, reply.sender_chat.title or "канал"
    u = reply.from_user
    return (u.id, u.full_name) if u else (0, "аноним")


async def _send_card(message: Message, bot, db: Database, q: dict) -> None:
    caption = f"💬 Цитата №{q['id']}"
    if q.get("card"):                                   # уже рисовали — повторно отправляем тот же файл, без рендера
        try:
            await message.reply_photo(q["card"], caption=caption)
            return
        except Exception:
            await db.quote_set_card(q["id"], None)
    tz = tz_of((await db.get_settings(message.chat.id))["tz"])
    av = await media.avatar(bot, q["author_id"]) if q["author_id"] > 0 else None
    png = await asyncio.to_thread(
        cards.quote_card, q["text"], q["author_name"], q["author_id"], av,
        datetime.fromtimestamp(q["ts"], tz).strftime("%d.%m.%Y %H:%M"), message.chat.title or "", q["id"])
    sent = await message.reply_photo(BufferedInputFile(png, f"quote{q['id']}.jpg"), caption=caption)
    if sent and getattr(sent, "photo", None):
        await db.quote_set_card(q["id"], sent.photo[-1].file_id)


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: _parse(t) is not None))
async def quotes_cmd(message: Message, bot, db: Database) -> None:
    if message.from_user is None:
        return
    kind, arg = _parse(message.text)
    chat, me, now = message.chat.id, message.from_user.id, int(time.time())

    if kind == "add":
        reply = ms.real_reply(message)
        if reply is None:
            await ux.tell(message, "⚠️ Ответьте <code>+цитата</code> на сообщение, которое нужно сохранить.")
            return
        text = (reply.text or reply.caption or "").strip()
        if not text:
            await ux.tell(message, "⚠️ В этом сообщении нет текста — цитировать нечего.")
            return
        if len(text) > MAX_QUOTE:
            text = text[:MAX_QUOTE - 1].rstrip() + "…"
        aid, aname = _author(reply)
        qid = await db.quote_add(chat, aid, aname, text, int(reply.date.timestamp()), me, now, reply.message_id)
        if qid is None:
            old = await db.quote_by_message(chat, reply.message_id)
            await message.reply(f"Это уже в цитатнике: №{old['id']}." if old else "Это уже в цитатнике.")
            return
        await _send_card(message, bot, db, await db.quote_get(chat, qid))
        return

    if kind == "show":
        if time.time() - _last.get(chat, 0) < SHOW_COOLDOWN:
            return
        _last[chat] = time.time()
        if arg and arg.isdigit():
            q = await db.quote_get(chat, int(arg))
            if q is None:
                await ux.tell(message, f"❌ Цитаты №{arg} нет.")
                return
        else:
            uid = await db.find_user(arg) if arg else None
            if arg and uid is None:
                await ux.tell(message, "❌ Не нашёл такого пользователя.")
                return
            q = await db.quote_random(chat, uid)
            if q is None:
                await message.reply("ℹ️ Цитатник пуст. Ответьте <code>+цитата</code> на чьё-нибудь сообщение 😏")
                return
        await _send_card(message, bot, db, q)
        return

    if kind == "list":
        uid = await db.find_user(arg) if arg else None
        if arg and uid is None:
            await ux.tell(message, "❌ Не знаю такого пользователя.")
            return
        if uid is None:
            total, top = await db.quote_stats(chat)
            if not total:
                await message.reply("ℹ️ Цитатник пуст. Ответьте <code>+цитата</code> на чьё-нибудь сообщение 😏")
                return
            lines = [f"{i}. {listed(a, (await db.user_name(a)) or n or f'id{a}') if a > 0 else html.escape(n or '?')} — {c}"
                     for i, (a, n, c) in enumerate(top, 1)]
            await message.reply(f"💬 <b>Цитатник</b> · {total}\nЧаще всех цитируют:\n" + "\n".join(lines)
                                + "\n<i>Случайная — <code>цитата</code>, по номеру — <code>цитата 5</code></i>")
            return
        rows = await db.quote_list(chat, uid)
        if not rows:
            await message.reply("ℹ️ У этого человека цитат пока нет.")
            return
        lines = [f"№{r['id']}: {html.escape(cards.fit(' '.join(r['text'].split()), cards.font(20), 520))}" for r in rows]
        await message.reply("💬 <b>Цитаты</b>\n" + "\n".join(lines))
        return

    # del: удалить может тот, кто добавил, автор цитаты или модератор
    q = await db.quote_get(chat, int(arg))
    if q is None:
        await ux.tell(message, f"❌ Цитаты №{arg} нет.")
        return
    if me not in (q["added_by"], q["author_id"]) and await ms.effective_rank(bot, db, chat, me) < 1:
        await ux.tell(message, "⚠️ Удалить цитату может тот, кто её добавил, её автор или модератор.")
        return
    await db.quote_delete(chat, q["id"])
    await message.reply(f"🗑 Цитата №{q['id']} удалена.")
