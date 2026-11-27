"""Обращение по имени: «нори <команда или вопрос>». Сначала пробуем как обычную команду, иначе отвечает ИИ."""
import re

from aiogram import BaseMiddleware
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import Message

_RE = re.compile(r"^\s*(?:нори|nori)\b[\s,:;!.\-—–]*(.*)$", re.IGNORECASE | re.DOTALL)


def strip_prefix(text: str | None) -> str | None:
    """«Нори, баланс» → «баланс»; «нори» → «меню»; сообщение без обращения → None."""
    m = _RE.match(text or "")
    if not m:
        return None
    return m.group(1).strip() or "меню"


# MIDDLEWARE обращения по имени. Имя бота меняется в регулярке _RE выше (нори|nori → своё).
class NoriPrefixMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data):
        rest = strip_prefix(event.text)
        if rest is None:
            return await handler(event, data)
        # entities сдвинулись бы вместе с префиксом — упоминания и так разбираются по тексту
        # nori_addressed: к боту обратились по имени — «живое» общение отвечает, даже если слова «нори» в тексте уже нет
        res = await handler(event.model_copy(update={"text": rest, "entities": None}), {**data, "nori_addressed": True})
        if res is UNHANDLED:  # ни одна команда не подошла — это вопрос к ИИ
            res = await handler(event.model_copy(update={"text": f"ии, {rest}", "entities": None}), data)
        return res
