"""Правила чата с сохранением оформления: текст хранится вместе с entities Telegram (жирный, курсив, цитаты, спойлеры,
ссылки, премиум-эмодзи…), а команда «правила» отдаёт их тем же текстом и теми же entities — отступы, переносы строк и
эмодзи выглядят ровно так, как их написал админ.

Формат хранения (строка в chat_texts): {"v":2,"text":"…","entities":[{"type":"bold","offset":0,"length":5},…]}.
Старые правила — просто строка без JSON — продолжают работать (показываются прежним способом)."""
from __future__ import annotations

import html
import json
import re

from aiogram.types import MessageEntity
from aiogram.utils.text_decorations import html_decoration

MAX_LEN = 3500                                    # символов: в сообщение влезает 4096, остальное — запас на приветствие
_SET_RE = re.compile(r"^\s*\+правила(?:[ \t]*\n|[ \t]+|$)", re.IGNORECASE)


def _u16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def _cut_entities(entities, cut: int) -> list[MessageEntity]:
    """Сдвигает entities на cut единиц UTF-16 влево (часть текста слева отрезана); вылезающие за границу обрезаются."""
    out = []
    for e in entities or []:
        start, end = e.offset, e.offset + e.length
        if end <= cut:
            continue
        new_start = max(start - cut, 0)
        new_len = end - cut - new_start
        if new_len > 0:
            out.append(e.model_copy(update={"offset": new_start, "length": new_len}))
    return out


def extract(message, reply=None) -> tuple[str, list[MessageEntity]] | None:
    """Откуда берём правила: текст после «+правила» в самом сообщении (с его оформлением) или, если после команды ничего
    нет, сообщение, на которое ответили. None — правил нет."""
    raw = message.text or ""
    m = _SET_RE.match(raw)
    if m and raw[m.end():].strip():
        text = raw[m.end():]
        return text.rstrip(), _cut_entities(message.entities, _u16(raw[:m.end()]))[:]
    if reply is not None:
        src = reply.text or reply.caption
        if src and src.strip():
            ents = reply.entities if reply.text else reply.caption_entities
            return src.rstrip(), list(ents or [])
    return None


def _trim(text: str, entities: list[MessageEntity]) -> tuple[str, list[MessageEntity]]:
    """Конечные пробелы убираем (entities за границей текста отбрасываем/обрезаем)."""
    end_u16 = _u16(text)
    fixed = []
    for e in entities:
        if e.offset >= end_u16:
            continue
        fixed.append(e if e.offset + e.length <= end_u16 else e.model_copy(update={"length": end_u16 - e.offset}))
    return text, fixed


def dump(text: str, entities: list[MessageEntity]) -> str:
    text, entities = _trim(text, entities)
    return json.dumps({"v": 2, "text": text, "entities": [e.model_dump(exclude_none=True, mode="json") for e in entities]},
                      ensure_ascii=False, separators=(",", ":"))


def load(stored: str | None) -> tuple[str, list[MessageEntity] | None] | None:
    """(текст, entities) — entities None для старых правил без оформления. None — правил нет."""
    if not stored:
        return None
    if stored.lstrip().startswith("{"):
        try:
            data = json.loads(stored)
            if isinstance(data, dict) and data.get("v") == 2:
                return data["text"], [MessageEntity.model_validate(e) for e in data.get("entities", [])]
        except (ValueError, KeyError, TypeError):
            pass
    return stored, None


def to_plain(stored: str | None) -> str:
    got = load(stored)
    return got[0] if got else ""


def to_html(stored: str | None) -> str:
    """Правила как HTML (для приветствия с {rules}): оформление и премиум-эмодзи сохраняются."""
    got = load(stored)
    if not got:
        return ""
    text, entities = got
    return html_decoration.unparse(text, entities) if entities else html.escape(text)


def summary(entities) -> tuple[int, int]:
    """(премиум-эмодзи, остальных стилей) среди entities."""
    ents = entities or []
    premium = sum(1 for e in ents if e.type == "custom_emoji")
    return premium, len(ents) - premium


def too_long(text: str) -> bool:
    return len(text) > MAX_LEN
