"""Конкурсы (розыгрыши): разбор времени из сообщений владельца и честный выбор победителей. Без Telegram и БД — легко тестировать."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bot.parsing import parse_period

MAX_PUBLISH_AHEAD = 30 * 86400     # опубликовать — не позже чем через 30 дней
MIN_DURATION = 5 * 60              # конкурс идёт минимум 5 минут
MAX_DURATION = 60 * 86400          # и максимум 60 дней
MAX_WINNERS = 10
TEXT_MAX = 3000                    # текст объявления без фото
CAPTION_MAX = 800                  # с фото (у подписи лимит Telegram 1024, нужен запас под строку с итогами)

_NOW = re.compile(r"^(?:сейчас|сразу|now)$", re.IGNORECASE)
_IN = re.compile(r"^через\s+(.+)$", re.IGNORECASE)
_TIME = re.compile(r"^(?:(сегодня|завтра|послезавтра)\s+)?(?:в\s+)?(\d{1,2})[:.](\d{2})$", re.IGNORECASE)
_DATE = re.compile(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{2}|\d{4}))?\s+(?:в\s+)?(\d{1,2})[:.](\d{2})$", re.IGNORECASE)
_DAY_SHIFT = {None: 0, "сегодня": 0, "завтра": 1, "послезавтра": 2}


def tz_of(name: str | None):
    try:
        return ZoneInfo(name or "Europe/Moscow")
    except Exception:
        return timezone.utc


def parse_when(text: str, now: int, tz, base: int | None = None) -> int | None:
    """Момент времени (unix) из «сейчас», «через 2 часа», «20:00», «завтра 18:30», «25.12 18:00», «25.12.2026 18:00».
    base — от чего считать «через …» (для конца конкурса — от публикации). None — не понял."""
    t = re.sub(r"\s+", " ", (text or "").strip().lower())
    if _NOW.match(t):
        return now
    m = _IN.match(t)
    if m:
        span = parse_period(m.group(1))
        return None if span is None else (base if base is not None else now) + int(span.total_seconds())
    local = datetime.fromtimestamp(now, tz)
    m = _TIME.match(t)
    if m:
        h, mi = int(m.group(2)), int(m.group(3))
        if h > 23 or mi > 59:
            return None
        day = local.date() + timedelta(days=_DAY_SHIFT[m.group(1)])
        ts = int(datetime(day.year, day.month, day.day, h, mi, tzinfo=tz).timestamp())
        if m.group(1) is None and ts <= now:     # «20:00», а уже 21:00 — значит завтра
            ts = int((datetime(day.year, day.month, day.day, h, mi, tzinfo=tz) + timedelta(days=1)).timestamp())
        return ts
    m = _DATE.match(t)
    if m:
        d, mo, y, h, mi = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4)), int(m.group(5))
        year = (int(y) + 2000 if len(y) == 2 else int(y)) if y else local.year
        try:
            ts = int(datetime(year, mo, d, h, mi, tzinfo=tz).timestamp())
            if not y and ts <= now:                  # «05.01 12:00» в декабре — это следующий год
                ts = int(datetime(year + 1, mo, d, h, mi, tzinfo=tz).timestamp())
        except ValueError:
            return None
        return ts
    return None


def check_publish(ts: int, now: int) -> str | None:
    """Текст ошибки или None."""
    if ts < now - 60:
        return "Это время уже прошло."
    if ts > now + MAX_PUBLISH_AHEAD:
        return "Опубликовать можно не позже чем через 30 дней."
    return None


def check_end(ts: int, publish_at: int) -> str | None:
    if ts < publish_at + MIN_DURATION:
        return "Конкурс должен идти хотя бы 5 минут после публикации."
    if ts > publish_at + MAX_DURATION:
        return "Конкурс может идти не дольше 60 дней."
    return None


def fmt_time(ts: int, tz) -> str:
    return datetime.fromtimestamp(ts, tz).strftime("%d.%m %H:%M")


def shuffled(user_ids: list[int]) -> list[int]:
    """Случайный порядок участников (криптографический генератор: исход нельзя предсказать или подогнать).
    Победители — первые из этого порядка, кто всё ещё в чате."""
    out = list(dict.fromkeys(user_ids))
    secrets.SystemRandom().shuffle(out)
    return out
