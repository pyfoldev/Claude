"""Правила чата без обращения к Telegram и БД: типы сообщений, триггеры «событие → наказание», FAQ, фейс-контроль,
ночное окно. Всё чистые функции — их легко проверять тестами."""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bot.parsing import _parse_span

# ---------- события ----------
# название для людей -> ключ настройки «удалять …» (None — только триггеры)
EVENTS: dict[str, str | None] = {
    "капс": "del_caps", "стикер": "del_sticker", "гиф": "del_gif", "голосовое": "del_voice", "кружок": "del_note",
    "пересылка": "del_forward", "упоминание": "del_mention", "эмодзи": "del_emoji", "сторис": "del_story",
    "кубик": "del_dice", "форматирование": "del_format", "инлайн": "del_via", "опрос": "del_poll",
    "ссылка": None, "фото": None, "видео": None, "документ": None,
}
EVENT_ALIASES = {
    "caps": "капс", "стикеры": "стикер", "sticker": "стикер", "гифка": "гиф", "гифки": "гиф", "gif": "гиф",
    "голосовые": "голосовое", "гс": "голосовое", "voice": "голосовое", "кружки": "кружок", "кружочек": "кружок",
    "пересылки": "пересылка", "форвард": "пересылка", "упоминания": "упоминание", "тег": "упоминание",
    "кастомные": "эмодзи", "сториз": "сторис", "кубики": "кубик", "игра": "кубик", "жирный": "форматирование",
    "оформление": "форматирование", "инлайн-бот": "инлайн", "опросы": "опрос", "ссылки": "ссылка", "link": "ссылка",
    "картинка": "фото", "фотки": "фото", "видос": "видео", "файл": "документ",
}
ACTIONS = {"удалить": "delete", "удаление": "delete", "варн": "warn", "предупреждение": "warn", "мут": "mute",
           "кик": "kick", "бан": "ban", "чс": "ban"}
ACTION_RU = {"delete": "удалить", "warn": "варн", "mute": "мут", "kick": "кик", "ban": "бан"}
_SEVERITY = {"delete": 0, "warn": 1, "mute": 2, "kick": 3, "ban": 4}
MAX_TRIGGERS_PER_EVENT = 3
MAX_TRIGGERS = 40

_CAPS_MIN_LETTERS = 8
_CAPS_RATIO = 0.7
_FORMAT_TYPES = {"bold", "italic", "underline", "strikethrough", "spoiler", "code", "pre", "blockquote",
                 "expandable_blockquote"}
_TME_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/", re.IGNORECASE)


def is_caps(text: str | None) -> bool:
    letters = [c for c in (text or "") if c.isalpha()]
    if len(letters) < _CAPS_MIN_LETTERS:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) >= _CAPS_RATIO


def detect_events(m) -> set[str]:
    """Какие из событий есть в сообщении. Работает с любым объектом, похожим на aiogram.types.Message."""
    out: set[str] = set()
    text = getattr(m, "text", None) or getattr(m, "caption", None) or ""
    ents = list(getattr(m, "entities", None) or []) + list(getattr(m, "caption_entities", None) or [])
    if is_caps(text):
        out.add("капс")
    if getattr(m, "sticker", None):
        out.add("стикер")
    if getattr(m, "animation", None):
        out.add("гиф")
    if getattr(m, "voice", None):
        out.add("голосовое")
    if getattr(m, "video_note", None):
        out.add("кружок")
    if getattr(m, "photo", None):
        out.add("фото")
    if getattr(m, "video", None):
        out.add("видео")
    if getattr(m, "document", None) and not getattr(m, "animation", None):
        out.add("документ")
    if getattr(m, "poll", None):
        out.add("опрос")
    if getattr(m, "dice", None):
        out.add("кубик")
    if getattr(m, "story", None):
        out.add("сторис")
    if getattr(m, "forward_origin", None) or getattr(m, "forward_date", None):
        out.add("пересылка")
    if getattr(m, "via_bot", None):
        out.add("инлайн")
    for e in ents:
        t = getattr(e, "type", "")
        if t in ("url", "text_link"):
            out.add("ссылка")
        elif t in ("mention", "text_mention"):
            out.add("упоминание")
        elif t == "custom_emoji":
            out.add("эмодзи")
        elif t in _FORMAT_TYPES:
            out.add("форматирование")
    if _TME_RE.search(text):
        out.add("ссылка")
    return out


def normalize_event(word: str) -> str | None:
    w = (word or "").lower().strip()
    w = EVENT_ALIASES.get(w, w)
    return w if w in EVENTS else None


# ---------- триггеры ----------
class TriggerError(ValueError):
    pass


def parse_trigger(arg: str) -> tuple[str, str, int, str]:
    """«капс варн» / «ссылка мут 10м спам» / «стикер удалить» -> (событие, действие, секунд, причина).
    Причину можно писать в кавычках или просто текстом после срока."""
    arg = (arg or "").strip()
    if not arg:
        raise TriggerError("Формат: +триггер событие действие [срок] [причина]")
    head, _, rest = arg.partition(" ")
    event = normalize_event(head)
    if event is None:
        raise TriggerError("Не знаю такого события. Доступны: " + ", ".join(EVENTS))
    word, _, rest = rest.strip().partition(" ")
    action = ACTIONS.get(word.lower())
    if action is None:
        raise TriggerError("Действие: удалить, варн, мут, кик или бан")
    rest = rest.strip()
    reason = ""
    qm = re.search(r'"([^"]+)"|«([^»]+)»|“([^”]+)”', rest)
    if qm:
        reason = next(g for g in qm.groups() if g).strip()
        rest = (rest[:qm.start()] + " " + rest[qm.end():]).strip()
    secs = 0
    toks = rest.split()
    # срок — первые одно-два слова: «10м», «на час», «2 дня»
    for take in (2, 1):
        if len(toks) >= take:
            span = _parse_span(toks[:take])
            if span is not None and span[0] == "span":
                secs = int(span[1].total_seconds())
                toks = toks[take:]
                break
    if secs and action not in ("mute", "ban", "warn"):
        raise TriggerError("Срок можно указать только для варна, мута и бана")
    if not reason:
        reason = " ".join(toks).strip()
    if len(reason) > 200:
        raise TriggerError("Причина слишком длинная (до 200 символов)")
    return event, action, secs, reason


def describe_trigger(t: dict) -> str:
    dur = ""
    if t.get("secs"):
        s = t["secs"]
        dur = f" {s // 86400}д" if s % 86400 == 0 else f" {s // 3600}ч" if s % 3600 == 0 else f" {max(s // 60, 1)}м"
    return f"#{t['id']} {t['event']} → {ACTION_RU.get(t['action'], t['action'])}{dur}" + (f" · {t['reason']}" if t.get("reason") else "")


def strongest(triggers: list[dict]) -> dict | None:
    """Из сработавших триггеров берём самый строгий: одно сообщение — одно наказание."""
    return max(triggers, key=lambda t: (_SEVERITY.get(t["action"], 0), -t["id"]), default=None)


# ---------- FAQ ----------
_BUTTON_RE = re.compile(r"^кнопка:\s*(.+?)\s*\|\s*(https?://\S+|tg://\S+)\s*$", re.IGNORECASE)


def split_faq_answer(answer: str) -> tuple[str, list[tuple[str, str]]]:
    """Строки «кнопка: Текст | https://…» превращаются в кнопки, остальное — текст ответа."""
    text, buttons = [], []
    for line in (answer or "").split("\n"):
        m = _BUTTON_RE.match(line.strip())
        if m:
            buttons.append((m.group(1)[:60], m.group(2)))
        else:
            text.append(line)
    return "\n".join(text).strip(), buttons[:6]


def parse_faq(arg: str) -> tuple[str, str]:
    """«слово = ответ» или «слово | ответ» -> (ключевое слово, ответ)."""
    m = re.match(r"^(.{2,40}?)\s*[=|]\s*(.+)$", (arg or "").strip(), re.DOTALL)
    if not m:
        raise TriggerError("Формат: +faq слово = ответ (кнопка — строкой «кнопка: Текст | https://…»)")
    return m.group(1).strip().lower(), m.group(2).strip()


def faq_match(text: str, items: list[dict]) -> dict | None:
    t = (text or "").lower()
    if not t or len(t) > 400:
        return None
    for it in items:
        kw = it["keyword"]
        if re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", t):
            return it
    return None


# ---------- фейс-контроль ----------
# Telegram не отдаёт дату регистрации, но id растёт со временем. Оценка грубая (±несколько месяцев):
# опорные точки (id, год-месяц) взяты из открытых наблюдений; для крупных чатов этого достаточно.
_ID_ANCHORS = [(100_000_000, (2015, 3)), (300_000_000, (2016, 11)), (500_000_000, (2017, 12)),
               (800_000_000, (2019, 3)), (1_000_000_000, (2019, 12)), (1_500_000_000, (2020, 11)),
               (2_000_000_000, (2021, 8)), (5_000_000_000, (2021, 11)), (6_000_000_000, (2022, 8)),
               (7_000_000_000, (2024, 3)), (8_000_000_000, (2025, 2))]


def estimate_age_days(user_id: int, now: float | None = None) -> int:
    """Примерный возраст аккаунта в днях по его id."""
    now = now if now is not None else time.time()
    pts = [(i, datetime(y, mo, 1, tzinfo=timezone.utc).timestamp()) for i, (y, mo) in _ID_ANCHORS]
    if user_id <= pts[0][0]:
        born = pts[0][1]
    elif user_id >= pts[-1][0]:
        born = pts[-1][1] + (user_id - pts[-1][0]) / 1_000_000_000 * 365 * 86400   # за последней точкой — вперёд
    else:
        born = pts[-1][1]
        for (i1, t1), (i2, t2) in zip(pts, pts[1:]):
            if i1 <= user_id <= i2:
                born = t1 + (t2 - t1) * (user_id - i1) / (i2 - i1)
                break
    return max(0, int((now - born) // 86400))


def face_reasons(user, s: dict, has_photo: bool | None, now: float | None = None) -> list[str]:
    """Почему новичок не проходит фейс-контроль. has_photo=None — не знаем (запрос не удался): тогда не наказываем."""
    out = []
    if s.get("fc_photo") and has_photo is False:
        out.append("нет фото профиля")
    if s.get("fc_username") and not getattr(user, "username", None):
        out.append("нет @username")
    if s.get("fc_premium") and not getattr(user, "is_premium", False):
        out.append("нет Telegram Premium")
    days = int(s.get("fc_age") or 0)
    if days and estimate_age_days(user.id, now) < days:
        out.append(f"аккаунт моложе ~{days} дн.")
    return out


# ---------- ночной режим ----------
def in_night(hour: int, start: int, end: int) -> bool:
    """Ночь с start до end (по часам, окно может переходить через полночь)."""
    if start == end:
        return False
    return start <= hour < end if start < end else (hour >= start or hour < end)


def local_hour(tz_name: str, now: float | None = None) -> int:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    return datetime.fromtimestamp(now if now is not None else time.time(), tz).hour


def parse_night(arg: str) -> tuple[int, int] | None:
    """«23-7», «с 23 до 7», «23:00-07:00» -> (23, 7)."""
    m = re.search(r"(\d{1,2})(?::\d{2})?\s*(?:-|—|до)\s*(\d{1,2})(?::\d{2})?", arg or "")
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    return (a, b) if 0 <= a <= 23 and 0 <= b <= 23 and a != b else None


# ---------- повторяющиеся сообщения ----------
MIN_EVERY = 600
MAX_PERIODIC = 20


def parse_periodic(arg: str) -> tuple[int, str]:
    """«6ч текст» / «каждые 2 часа текст» / «1д текст» -> (секунд, текст)."""
    arg = re.sub(r"^(?:каждые|каждый|каждую|раз в)\s+", "", (arg or "").strip(), flags=re.IGNORECASE)
    for take in (2, 1):
        parts = arg.split(None, take)
        if len(parts) < take:
            continue
        span = _parse_span([p.lower() for p in parts[:take]])
        if span is None or span[0] != "span":
            continue
        secs = int(span[1].total_seconds())
        text = parts[take].strip() if len(parts) > take else ""
        if secs < MIN_EVERY:
            raise TriggerError("Не чаще раза в 10 минут")
        if not text:
            raise TriggerError("Напишите текст после срока")
        return secs, text
    raise TriggerError("Формат: +повтор 6ч текст сообщения")
