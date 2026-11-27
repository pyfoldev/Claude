"""Гифки для РП, семьи и пары через Gifukai (https://api.gifukai.com/v1, бесплатно, без ключа). Пол актёра и цели учитывается:
параметр pairing = первая буква — кто делает, вторая — кому (f — девушка, m — парень). Любой сбой — просто текст без гифки."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time

import aiohttp
from aiogram.types import FSInputFile
from pathlib import Path

GIFS_DIR = Path(os.environ.get("GIFS_DIR", "data/gifs"))   # локальная библиотека (tools/fetch_gifukai.py); нет папки — только API
BASE = os.environ.get("GIFUKAI_URL", "https://api.gifukai.com/v1").rstrip("/")
TIMEOUT = aiohttp.ClientTimeout(total=3.5)
_off_until = 0.0                  # сервис не отвечает — не мучаем запросами и не тормозим РП
OFF_FOR = 120

# фраза РП → (действие Gifukai, тип | None)
RP_MAP: dict[str, tuple[str, str | None]] = {
    "обнять": ("hug", None), "обнять крепко": ("hug", None), "прижать к себе": ("cuddle", None), "укрыть пледом": ("cuddle", None),
    "погладить": ("pat", None), "погладить по голове": ("pat", None), "пожалеть": ("pat", None),
    "поцеловать в щёку": ("kiss", "cheek"), "поцеловать в лоб": ("kiss", "forehead"),
    "взять за руку": ("handhold", None), "накормить": ("feed", None), "подарить цветы": ("blush", None),
    "подарить сердечко": ("blowkiss", None), "пожать руку": ("handshake", None), "дать пять": ("highfive", None),
    "поприветствовать": ("hi", None), "поблагодарить": ("happy", None), "похвалить": ("clap", None), "поздравить": ("yay", None),
    "поддержать": ("thumbsup", None), "подбодрить": ("thumbsup", None), "угостить чаем": ("sip", None),
    "угостить кофе": ("sip", None), "подмигнуть": ("wink", None), "помахать": ("wave", None), "поклониться": ("salute", None),
    "пощекотать": ("tickle", None), "ущипнуть": ("poke", None), "подразнить": ("taunt", None), "толкнуть": ("poke", None),
    "показать язык": ("bleh", None), "дать щелбан": ("poke", None), "кинуть подушкой": ("bonk", None),
    "осыпать конфетти": ("yay", None), "догнать": ("run", None), "ударить": ("punch", None), "пнуть": ("kick", None),
    "дать подзатыльник": ("bonk", None), "кинуть тапком": ("yeet", None), "укусить": ("bite", None), "выгнать": ("yeet", None),
    "потрепать по голове": ("pat", None), "почесать за ушком": ("pat", None), "завернуть в одеяло": ("cuddle", None),
    "уложить спать": ("sleep", None), "накормить с ложечки": ("feed", None), "запрыгнуть на руки": ("carry", None),
    "спеть песню": ("sing", None), "налить чай": ("sip", None), "дать печеньку": ("feed", None), "почесать спинку": ("pat", None),
    "сделать комплимент": ("blush", None), "пригласить на танец": ("dance", None), "рассказать анекдот": ("laugh", None),
    "рассмешить": ("laugh", None), "кивнуть": ("nod", None), "кинуть снежком": ("bonk", None), "погрозить пальцем": ("taunt", None),
    "закатить глаза": ("facepalm", None), "устроить подушечный бой": ("bonk", None), "пофлиртовать": ("wink", None),
    "прыгнуть сзади": ("hug", None), "поцеловать в губы": ("kiss", "mouth"), "обнять за талию": ("hug", None),
    "соблазнить": ("wink", None), "станцевать приватный танец": ("dance", None), "показать фак": ("taunt", None),
    "дать по ебалу": ("punch", None), "наорать": ("angry", None), "обозвать": ("taunt", None), "сказать заткнись": ("angry", None),
}
# РП пары (handlers/pair.py → data.PairRp.key)
PAIR_MAP: dict[str, tuple[str, str | None]] = {
    "обнять": ("hug", None), "поцеловать": ("kiss", None), "кусь": ("bite", None), "шлёп": ("slap", None),
    "погладить": ("pat", None), "щелбан": ("poke", None), "потанцевать": ("dance", None), "укрыть": ("cuddle", None),
    "накормить": ("feed", None), "комплимент": ("blush", None), "массаж": ("pat", None), "щекотать": ("tickle", None),
    "подмигнуть": ("wink", None), "серенада": ("sing", None), "за руку": ("handhold", None), "носить на руках": ("carry", None),
}
# семейные события
FAMILY_MAP: dict[str, tuple[str, str | None]] = {
    "marry": ("kiss", None), "relation": ("handhold", None), "adopt": ("pat", None), "breakup": ("cry", None),
    "divorce": ("cry", None), "disown": ("bye", None),
}


def pairing(actor: str | None, target: str | None, rnd: random.Random | None = None) -> str | None:
    """Параметр pairing по полам. Неизвестна цель — подбираем случайно; неизвестен актёр — не указываем (любая гифка)."""
    if actor not in ("m", "f"):
        return None
    t = target if target in ("m", "f") else (rnd or random).choice("mf")
    return actor + t


async def fetch(http, action: str, typ: str | None = None, pair: str | None = None) -> str | None:
    """Ссылка на случайную гифку или None. Нет гифки для пары полов — пробуем без пары."""
    global _off_until
    if time.time() < _off_until or http is None:
        return None
    for pr in ((pair, None) if pair else (None,)):
        params = {k: v for k, v in (("pairing", pr), ("type", typ)) if v}
        try:
            async with http.get(f"{BASE}/{action}", params=params, timeout=TIMEOUT, headers={"User-Agent": "ChatHelperBot/1.0"}) as r:
                if r.status == 200:
                    url = (await r.json()).get("url")
                    if url and url.startswith("https://"):
                        return url
                elif r.status >= 500:
                    _off_until = time.time() + OFF_FOR
                    return None
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            _off_until = time.time() + OFF_FOR
            return None
    return None


_index: dict | None = None
_file_ids: dict[str, str] = {}        # файл → file_id в Telegram: после первой отправки гифка повторно не загружается


def _load_index() -> dict:
    """manifest.json → {(действие, тип): [записи]}. Нет манифеста — пусто (работаем через API)."""
    global _index
    if _index is None:
        _index = {}
        try:
            for it in json.loads((GIFS_DIR / "manifest.json").read_text("utf-8")).get("items", []):
                _index.setdefault((it["action"], it.get("type")), []).append(it)
        except (OSError, ValueError, KeyError):
            pass
    return _index


def local_pick(action: str, typ: str | None, pair: str | None, rnd: random.Random | None = None) -> str | None:
    """Случайная локальная гифка (относительный путь) для действия, типа и пары полов. Нет такой пары — берём любую
    из действия (как и API); нет файла на диске — None."""
    items = _load_index().get((action, typ)) or (_load_index().get((action, None)) if typ else None) or []
    exact = [i for i in items if pair and i["pairing"] == pair]
    for pool in (exact, items):
        pool = [i for i in pool if (GIFS_DIR / i["file"]).is_file()]
        if pool:
            return (rnd or random).choice(pool)["file"]
    return None


async def _source(http, mapped: tuple[str, str | None], pair: str | None):
    """Что слать в send_animation: (file_id | файл | URL, ключ локального файла | None). Сначала локальная библиотека."""
    rel = local_pick(mapped[0], mapped[1], pair)
    if rel:
        return _file_ids.get(rel) or FSInputFile(GIFS_DIR / rel), rel
    return await fetch(http, mapped[0], mapped[1], pair), None


async def _send(bot, chat_id: int, src, key: str | None, **kw) -> bool:
    try:
        msg = await bot.send_animation(chat_id, src, **kw)
    except Exception as e:
        if key and key in _file_ids:                      # file_id мог устареть — забываем, в следующий раз загрузим файл
            _file_ids.pop(key, None)
        logging.info("gifs: гифка не отправилась (%s)", e)
        return False
    if key and key not in _file_ids and getattr(msg, "animation", None):
        _file_ids[key] = msg.animation.file_id
    return True


async def reply_gif(bot, http, message, text: str, mapped: tuple[str, str | None] | None, actor_g: str | None,
                    target_g: str | None, *, reply_to: int | None = None, enabled: bool = True) -> bool:
    """РП-ответ гифкой с текстом в подписи. False — гифки нет (отключено, сбой): тогда вызывающий шлёт обычный текст."""
    if not enabled or mapped is None:
        return False
    src, key = await _source(http, mapped, pairing(actor_g, target_g))
    if src is None:
        return False
    return await _send(bot, message.chat.id, src, key, caption=text, reply_to_message_id=reply_to,
                       message_thread_id=message.message_thread_id if getattr(message, "is_topic_message", False) else None)


async def extra_gif(bot, http, chat_id: int, mapped: tuple[str, str | None] | None, actor_g: str | None, target_g: str | None) -> None:
    """Гифка отдельным сообщением после текста (семейные события)."""
    if mapped is None:
        return
    src, key = await _source(http, mapped, pairing(actor_g, target_g))
    if src is not None:
        await _send(bot, chat_id, src, key)
