"""Развлечения: инфа, выбери, данет, жребий, монетка, скажи, шипперим, пейринг, погода."""
import html
import random
import re
import time

from aiogram import F, Router
from aiogram.types import Message

from bot import ux
from bot.db import Database
from bot.targets import mention
from bot.weather import fetch_weather, valid_city

router = Router(name="entertainment")
_rng = random.Random()
COOLDOWN = 3
MAX_SAY = 300
_last: dict[tuple, float] = {}

_PATTERNS = [
    ("info", r"^инфа\s+(.+)$"), ("choose", r"^выбери\s+(.+\s+или\s+.+)$"), ("yesno", r"^данет\s+(.+)$"),
    ("lot", r"^жребий$"), ("coin", r"^монетка$"), ("say", r"^!скажи\s+(.+)$"),
    ("ship", r"^шипперим$"), ("pair", r"^пейринг$"), ("weather", r"^(?:!погода\s+(?:в\s+)?|погода\s+в\s+)(.+)$"),
]
_COMPILED = [(k, re.compile(p, re.IGNORECASE | re.DOTALL)) for k, p in _PATTERNS]
_YESNO = ["Да ✅", "Нет ❌", "Скорее да 🙂", "Скорее нет 🤔", "Определённо да 💯", "Даже не думай 🚫",
          "Вероятно 🤷", "Звёзды говорят «нет» ✨"]


def parse(text: str | None):
    t = re.sub(r"[ \t]+", " ", (text or "").strip())
    for kind, rx in _COMPILED:
        m = rx.match(t)
        if m:
            return kind, (m.group(1).strip() if m.groups() else None)
    return None


def split_options(text: str) -> list[str] | None:
    """«чай или кофе или сок» → ['чай', 'кофе', 'сок']; нужно от 2 до 6 непустых вариантов."""
    opts = [o.strip(" ,.;!?") for o in re.split(r"\s+или\s+", text, flags=re.IGNORECASE)]
    opts = [o for o in opts if o]
    return opts if 2 <= len(opts) <= 6 else None


def sanitize_say(text: str) -> str | None:
    """Чтобы «скажи» нельзя было использовать для пингов и чужих команд: @ ломается, ведущие / и ! убираются."""
    text = re.sub(r"@(?=\w)", "@\u200b", text.strip())
    text = text.lstrip("/!.")
    text = re.sub(r"\s+", " ", text)[:MAX_SAY]
    return text or None


def _throttled(key: tuple) -> bool:
    now = time.time()
    if now - _last.get(key, 0) < COOLDOWN:
        return True
    _last[key] = now
    return False


@router.message(F.text.func(lambda t: parse(t) is not None))
async def entertain(message: Message, db: Database, http=None) -> None:
    if message.chat.type not in ("group", "supergroup"):
        return
    chat, uid = message.chat.id, message.from_user.id
    if not (await db.get_settings(chat))["fun_on"] or _throttled((chat, uid)):
        return
    kind, arg = parse(message.text)
    me = mention(uid, message.from_user.full_name)

    if kind == "info":
        n = _rng.randint(0, 100)
        note = " (сотка!)" if n == 100 else (" (ноль)" if n == 0 else "")
        await message.reply(f"📊 Инфа «{html.escape(arg[:200])}» — <b>{n}%</b>{note}")
    elif kind == "choose":
        opts = split_options(arg)
        if opts:
            await message.reply(f"🎯 Выбираю: <b>{html.escape(_rng.choice(opts))}</b>")
    elif kind == "yesno":
        await message.reply(f"🔮 {_rng.choice(_YESNO)}")
    elif kind == "coin":
        await message.reply("🪙 " + _rng.choice(["Орёл", "Решка"]))
    elif kind == "lot":
        pick = await db.random_member(chat)
        if pick:
            await message.reply(f"🎲 Жребий пал на {mention(*pick)}")
    elif kind == "say":
        text = sanitize_say(arg)
        if text:
            await message.answer(f"🗣 {html.escape(text)}\n— {me}")
    elif kind == "ship":
        pair = await db.random_members(chat, 2)
        if len(pair) < 2:
            await ux.tell(message, "⚠️ Я пока знаю слишком мало людей в этом чате 🤷")
        else:
            await message.reply(f"💘 Шипперим: {mention(*pair[0])} + {mention(*pair[1])}")
    elif kind == "pair":
        pair = await db.random_members(chat, 1, exclude=(uid,))
        await message.reply(f"💞 Ваша пара на сегодня: {mention(*pair[0])}" if pair else
                            "Пока не вижу тут никого, кроме вас 🤷")
    elif kind == "weather":
        if not valid_city(arg):
            await ux.tell(message, "⚠️ Укажите город, например: <code>погода Москва</code>")
            return
        text = await fetch_weather(http, arg) if http is not None else None
        await message.reply(f"🌤 {html.escape(text)}" if text else "Не нашёл такой город или сервис погоды недоступен.")
