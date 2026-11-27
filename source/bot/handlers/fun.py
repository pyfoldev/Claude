"""Развлечения: «вероятность …» и «кто …» (случайный участник именно этого чата)."""
import hashlib
import html
import re
import time
from datetime import date

from aiogram import F, Router
from aiogram.types import Message

from bot import ux
from bot.db import Database
from bot.targets import mention

router = Router(name="fun")

_PROB_RE = re.compile(r"^(?:вероятность|шанс)(?:[,:]|\s)\s*(?:того,?\s+)?(?:что,?\s+)?(.+?)\s*[?!.]*$",
                      re.IGNORECASE | re.DOTALL)
_WHO_RE = re.compile(r"^кто\s+(.+?)\s*[?!.]*$", re.IGNORECASE | re.DOTALL)
_WORD_RE = re.compile(r"^[\w-]{2,25}$")
_STOP = {"это", "тут", "здесь", "там", "где", "такой", "такая", "такие", "был", "была", "будет", "что",
         "как", "когда", "почему", "зачем", "ты", "вы", "я"}
COOLDOWN = 3
_last: dict[tuple, float] = {}


def parse_probability(text: str | None) -> str | None:
    m = _PROB_RE.match((text or "").strip())
    if not m:
        return None
    body = m.group(1).strip()
    return body if 2 <= len(body) <= 200 else None


def parse_who(text: str | None) -> str | None:
    m = _WHO_RE.match((text or "").strip())
    if not m:
        return None
    words = m.group(1).split()
    if not 1 <= len(words) <= 3 or not all(_WORD_RE.match(w) for w in words):
        return None
    if all(w.lower() in _STOP for w in words):
        return None
    return " ".join(words)


def probability(chat_id: int, user_id: int, text: str, day: str) -> int:
    """0..100. Один и тот же вопрос от одного человека в течение суток даёт один и тот же ответ."""
    norm = re.sub(r"\s+", " ", text.lower()).strip()
    h = hashlib.sha256(f"{chat_id}|{user_id}|{norm}|{day}".encode()).digest()
    return int.from_bytes(h[:4], "big") % 101


def _throttled(key: tuple) -> bool:
    now = time.time()
    if now - _last.get(key, 0) < COOLDOWN:
        return True
    _last[key] = now
    return False


async def _enabled(db: Database, message: Message) -> bool:
    return message.chat.type in ("group", "supergroup") and bool((await db.get_settings(message.chat.id))["fun_on"])


@router.message(F.text.func(lambda t: parse_probability(t) is not None))
async def probability_cmd(message: Message, db: Database) -> None:
    if not await _enabled(db, message) or _throttled(("p", message.chat.id, message.from_user.id)):
        return
    what = parse_probability(message.text)
    n = probability(message.chat.id, message.from_user.id, what, date.today().isoformat())
    await message.reply(f"🎲 «{html.escape(what)}» — вероятность <b>{n}%</b>")


@router.message(F.text.func(lambda t: parse_who(t) is not None))
async def who_cmd(message: Message, db: Database) -> None:
    if not await _enabled(db, message) or _throttled(("w", message.chat.id)):
        return
    phrase = parse_who(message.text)
    pick = await db.random_member(message.chat.id)
    if pick is None:
        await ux.tell(message, "⚠️ Я пока никого здесь не знаю 🤷")
        return
    uid, name = pick
    await db.user_name(uid)   # подтягивает @ник для ссылки
    await message.reply(f'🎯 Кто {html.escape(phrase)}? Однозначно {mention(uid, name)}')
