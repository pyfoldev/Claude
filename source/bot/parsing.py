from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

MAX_DAYS = 366

_UNITS = {"м": 1 / 1440, "ч": 1 / 24, "д": 1, "н": 7}
_DUR_RE = re.compile(r"^(\d+)\s*([мчдн])$", re.IGNORECASE)


def parse_duration(text: str) -> timedelta | None:
    m = _DUR_RE.match(text.strip())
    if not m:
        return None
    n = int((m.group(1).lstrip("0") or "0")[:8])
    if n <= 0:
        return None
    days = min(n, 10**7) * _UNITS[m.group(2).lower()]
    return timedelta(days=min(days, MAX_DAYS))


# ---------- команды модерации ----------
# Команда — это ТОЛЬКО: слово [@ник|id] [срок] [причина: текст]. Любой лишний текст
# превращает сообщение в обычную болтовню («бан бы дать тебе» — не команда).

_SLASH = {
    "ban": "бан", "unban": "разбан", "mute": "мут", "unmute": "размут",
    "kick": "кик", "warn": "варн", "unwarn": "снять варн", "warns": "варны",
    "del": "удалить", "pin": "закреп", "unpin": "открепить", "purge": "чистка",
}
_ALIASES = {"-смс": "чистка", "пург": "чистка", "!пург": "чистка",
            "чс": "бан", "заткнуть": "мут", "-мут": "размут", "-варн": "снять варн", "-бан": "разбан",
            "unban": "разбан", "unmute": "размут", "ban": "бан", "mute": "мут", "kick": "кик", "warn": "варн"}
# тихие (т…: команда и уведомление не остаются в чате) и «удаляющие» (д…: заодно удаляется сообщение нарушителя) варианты
_SILENT = {"тбан": "бан", "тмут": "мут", "ткик": "кик", "тварн": "варн"}
_DELMSG = {"дбан": "бан", "дмут": "мут", "дкик": "кик", "дварн": "варн"}
_NAMES = ["снять варн", "разбан", "размут", "открепить", "удалить", "закреп", "амнистия", "вайп",
          "чистка", "варны", "варн", "бан", "мут", "кик", "-смс", "!пург", "пург",
          "тбан", "тмут", "ткик", "тварн", "дбан", "дмут", "дкик", "дварн",
          "чс", "заткнуть", "-мут", "-варн", "-бан", "unban", "unmute", "ban", "mute", "kick", "warn"]
_NAME_RE = re.compile(
    r"^(" + "|".join(re.escape(n).replace(r"\ ", r"\s+") for n in _NAMES) + r")(?=\s|$)",
    re.IGNORECASE,
)
_TARGET_RE = re.compile(r"^(@\w+|\d{5,})$")
_QUOTED_RE = re.compile(r'(?:^|\s)(?:"([^"]+)"|«([^»]+)»|“([^”]+)”|„([^“”]+)[“”])(?=\s|$)', re.DOTALL)
_REASON_RE = re.compile(r"(?:^|\s)причина(?::|\s)\s*(.+)$", re.IGNORECASE | re.DOTALL)

_NUM_WORDS = {
    "один": 1, "одну": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5,
    "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10, "пятнадцать": 15,
    "двадцать": 20, "тридцать": 30,
}
_UNIT_WORDS = {
    **dict.fromkeys(["минута", "минуту", "минуты", "минут", "мин"], 1 / 1440),
    **dict.fromkeys(["час", "часа", "часов"], 1 / 24),
    **dict.fromkeys(["день", "дня", "дней", "сутки", "суток"], 1),
    **dict.fromkeys(["неделя", "неделю", "недели", "недель"], 7),
}
_FOREVER = {"навсегда", "перманентно"}
_TIMED = {"бан", "мут", "варн"}  # срок разрешён только им (у варна это срок жизни предупреждения)
_ALLOW_TARGET = {"бан", "разбан", "мут", "размут", "кик", "варн", "снять варн", "варны", "вайп"}
_ALLOW_REASON = {"бан", "мут", "кик", "варн"}


@dataclass
class ModCommand:
    name: str
    target: str | None
    duration: timedelta | None
    reason: str
    silent: bool = False        # «т…»: без уведомления, команда удаляется
    delete_msg: bool = False    # «д…»: удалить и сообщение нарушителя (то, на которое ответили)


def _is_int(t: str) -> bool:
    return t.isascii() and t.isdigit()  # «²» и прочие юникодные цифры — не числа


def _cap(days: float) -> timedelta:
    return timedelta(days=min(days, MAX_DAYS))


def _parse_span(tokens: list[str]):
    """Срок из токенов. Возвращает ('none'|'forever'|'span', timedelta|None) или None, если не срок."""
    if tokens and tokens[0] == "на":
        tokens = tokens[1:]
        if not tokens:
            return None
    if not tokens:
        return "none", None
    if len(tokens) == 1:
        t = tokens[0]
        if t in _FOREVER:
            return "forever", None
        d = parse_duration(t)
        if d is not None:
            return "span", d
        if t in _UNIT_WORDS:  # «на час», «на неделю»
            return "span", _cap(_UNIT_WORDS[t])
        return None
    if len(tokens) == 2 and tokens[1] in _UNIT_WORDS:
        n = int((tokens[0].lstrip("0") or "0")[:8]) if _is_int(tokens[0]) else _NUM_WORDS.get(tokens[0])
        if n and n > 0:
            return "span", _cap(n * _UNIT_WORDS[tokens[1]])
    return None


def parse_period(text: str) -> timedelta | None:
    """«7д», «2 недели», «на месяц» → timedelta; иначе None. Для команд массовой чистки."""
    tokens = text.lower().split()
    res = _parse_span(tokens)
    return res[1] if res and res[0] == "span" else None


def parse_mod_command(text: str) -> ModCommand | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("/"):
        return _parse_slash(text)
    if text[:1] in "!." and text[1:2].isalpha():
        text = text[1:]                      # «!бан», «.бан» — как «бан»
    m = _NAME_RE.match(text)
    if not m:
        return None
    name = re.sub(r"\s+", " ", m.group(1).lower())
    silent = name in _SILENT
    delmsg = name in _DELMSG
    name = _SILENT.get(name) or _DELMSG.get(name) or _ALIASES.get(name, name)
    rest = text[m.end():].strip()
    reason = ""
    if name in _ALLOW_REASON and "\n" in rest:
        first, _, tail = rest.partition("\n")         # причина — со следующей строки (как в Iris)
        if tail.strip() and not _REASON_RE.search(rest):
            reason, rest = tail.strip(), first.strip()
    rm = _REASON_RE.search(rest)
    if rm:
        if name not in _ALLOW_REASON:
            return None
        reason = rm.group(1).strip()
        rest = rest[:rm.start()].strip()
    qm = _QUOTED_RE.search(rest)  # бан @ник 1д "причина" — причина в кавычках
    if qm and not reason:
        if name not in _ALLOW_REASON:
            return None
        reason = next(g for g in qm.groups() if g).strip()
        rest = (rest[:qm.start()] + " " + rest[qm.end():]).strip()
    words = rest.split()
    if name in _TIMED and "остыть" in (w.lower() for w in words):     # «мут остыть» — на 10 минут
        words = [w for w in words if w.lower() != "остыть"] + ["10м"]
    if name in _ALLOW_REASON and "тихо" in (w.lower() for w in words):  # «кик тихо», «бан тихо»
        words = [w for w in words if w.lower() != "тихо"]
        silent = True
    rest = " ".join(words)
    tokens = rest.lower().split()

    if name == "чистка":
        if not tokens:
            return ModCommand(name, None, None, "")
        if len(tokens) == 1 and _is_int(tokens[0]) and int(tokens[0]) >= 1:
            return ModCommand(name, None, None, tokens[0])
        return None

    target = None
    for i, t in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if _is_int(t) and nxt in _UNIT_WORDS:
            continue  # «мут 10000 минут» — это срок, а не id
        if _TARGET_RE.match(t):
            if name not in _ALLOW_TARGET:
                return None
            target = rest.split()[i]  # исходный регистр ника
            tokens.pop(i)
            break
    span = _parse_span(tokens)
    if span is None:
        return None
    kind, delta = span
    if kind != "none" and name not in _TIMED:
        return None
    if kind == "forever":
        if name == "варн":
            return None
        delta = _cap(MAX_DAYS) if name == "мут" else None
    return ModCommand(name, target, delta, reason, silent, delmsg)


def _parse_slash(text: str) -> ModCommand | None:
    """Слэш-форма явная, поэтому там причина — свободный текст."""
    m = re.match(r"^/(\w+)(?:@\w+)?(?:\s+(.*))?$", text, re.DOTALL)
    if not m or m.group(1).lower() not in _SLASH:
        return None
    name = _SLASH[m.group(1).lower()]
    parts = (m.group(2) or "").strip().split()
    target = duration = None
    if parts and _TARGET_RE.match(parts[0]):
        target = parts.pop(0)
    if parts and name in _TIMED:
        d = parse_duration(parts[0])
        if d is not None:
            duration = d
            parts.pop(0)
    reason = " ".join(parts)
    if len(reason) >= 2 and reason[0] + reason[-1] in ('""', "«»", "“”", "„“"):
        reason = reason[1:-1].strip()
    return ModCommand(name, target, duration, reason)


# ---------- статистика ----------

@dataclass
class StatsPeriod:
    kind: Literal["hours", "all"]
    hours: int | None = None


_STATS_RE = re.compile(r"^(?:стата|статистика)(?:\s+(.+))?$", re.IGNORECASE)
_HOURS_RE = re.compile(r"^(\d+)\s*(?:час|часа|часов|ч)$", re.IGNORECASE)


def parse_stats_command(text: str) -> StatsPeriod | None:
    m = _STATS_RE.match(text.strip())
    if not m:
        return None
    arg = (m.group(1) or "").strip().lower()
    if arg in ("", "день", "сутки"):
        return StatsPeriod("hours", 24)
    if arg in ("неделя", "неделю"):
        return StatsPeriod("hours", 168)
    if arg == "месяц":
        return StatsPeriod("hours", 720)
    if arg in ("вся", "всё", "все", "всего"):
        return StatsPeriod("all")
    h = _HOURS_RE.match(arg)
    if h:
        n = int(h.group(1))
        if 1 <= n <= 168:
            return StatsPeriod("hours", n)
    return None
