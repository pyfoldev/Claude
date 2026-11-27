"""Защита от гостевых ботов (Bot API 10.0). Гостевой бот отвечает в чате, не будучи его участником: человек пишет
«@бот запрос», и ответ бота появляется в вашем чате. Такие сообщения не проходили ни антиспам, ни фильтры (боты пропускались).

Режимы чата (настройки → «Гостевые боты»): off — не вмешиваться; check — проверять содержимое (стоп-слова, фишинг, ссылки,
флуд); allowlist — разрешены только боты из белого списка; block — запрещены все. Модераторы и админы как вызывающие не
ограничиваются. Для каждого бота можно задать статус: «+гостевой @бот» — доверенный (без проверок), «-гостевой @бот» — запрещён.
Три нарушения за 10 минут — мут вызвавшего на час: он сам зовёт бота, чтобы засорять чат."""
from __future__ import annotations

import html
import re
import time

from aiogram import F, Router
from aiogram.types import Message

from bot import mod_service as ms
from bot import style, ux
from bot.db import Database
from bot.ranks import need_rank

router = Router(name="guestbots")

STATUS_SEEN, STATUS_ALLOWED, STATUS_BLOCKED = 0, 1, 2
STATUS_TEXT = {STATUS_SEEN: "замечен", STATUS_ALLOWED: "доверенный", STATUS_BLOCKED: "запрещён"}
FLOOD_N, FLOOD_SEC = 6, 60            # больше 6 ответов гостевых ботов за минуту от одного вызывающего — флуд
STRIKES, STRIKE_WINDOW = 3, 600       # три нарушения за 10 минут — мут вызвавшего


def is_guest_message(m) -> bool:
    """Сообщение гостевого бота: Telegram указывает, кто и откуда его вызвал."""
    return bool(getattr(m, "guest_bot_caller_user", None) or getattr(m, "guest_bot_caller_chat", None))


_ADD = re.compile(r"^([+-])гостевой\s+@?(\w{4,32})$", re.IGNORECASE)
_RESET = re.compile(r"^сброс\s+гостевого\s+@?(\w{4,32})$", re.IGNORECASE)
_LIST = re.compile(r"^гостевые(?:\s+боты)?$", re.IGNORECASE)


def _match(t: str | None) -> bool:
    t = (t or "").strip()
    return bool(_ADD.match(t) or _RESET.match(t) or _LIST.match(t))


async def _bot_id(bot, db: Database, chat_id: int, username: str) -> int | None:
    """id бота по @нику: сначала среди замеченных в этом чате, потом спросим Telegram."""
    for r in await db.guest_list(chat_id, 200):
        if (r["username"] or "").lower() == username.lower():
            return r["bot_id"]
    try:
        c = await bot.get_chat("@" + username)
        return c.id if c.type == "private" else None
    except Exception:
        return None


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(_match))
async def guest_cmd(message: Message, bot, db: Database) -> None:
    if message.from_user is None:
        return
    chat, t, now = message.chat.id, message.text.strip(), int(time.time())
    if await ms.effective_rank(bot, db, chat, message.from_user.id) < need_rank(await db.get_access(chat), "настройки чата"):
        return
    if _LIST.match(t):
        rows = await db.guest_list(chat)
        mode = (await db.get_settings(chat)).get("guest_mode", "check")
        mode_ru = {"off": "выключена", "check": "проверка содержимого", "allowlist": "белый список", "block": "запрещены все"}[mode]
        if not rows:
            await message.reply(style.head("🤖", "Гостевые боты", f"защита: {mode_ru}") + "\nПока ни один гостевой бот не отвечал в этом чате.")
            return
        body = "\n".join(f"• @{html.escape(r['username'] or str(r['bot_id']))} — {STATUS_TEXT[r['status']]}" for r in rows)
        await message.reply(style.head("🤖", "Гостевые боты", f"защита: {mode_ru}") + "\n" + body +
                            "\n\n<i>Разрешить: <code>+гостевой @бот</code> · запретить: <code>-гостевой @бот</code> · сброс: <code>сброс гостевого @бот</code></i>")
        return
    m = _ADD.match(t)
    reset = _RESET.match(t)
    username = (m or reset).group(2 if m else 1)
    bid = await _bot_id(bot, db, chat, username)
    if bid is None:
        await ux.tell(message, f"❌ Не нашёл бота @{html.escape(username)}.")
        return
    status = STATUS_SEEN if reset else (STATUS_ALLOWED if m.group(1) == "+" else STATUS_BLOCKED)
    await db.guest_set_status(chat, bid, username, status, now)
    await message.reply(style.ok(f"@{html.escape(username)}: {STATUS_TEXT[status]}."))
