"""Ядро: настройки (.env), состояние, тексты и оформление, ранги, язык (i18n), общие утилиты.

Файл собран из нескольких исходных модулей; каждый начинается с шапки «МОДУЛЬ: bot/<путь>.py».
Ищите по слову «МОДУЛЬ:» (Ctrl+F). Пути вида handlers/xxx.py в комментариях — это такие разделы.
"""
from __future__ import annotations

import aiohttp
import asyncio
import hmac
import html
import json
import logging
import os
import re
import time
from aiogram import BaseMiddleware, Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.dispatcher.event.handler import FilterObject
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Filter
from aiogram.methods import (
    EditMessageCaption,
    EditMessageReplyMarkup,
    EditMessageText,
    SendAnimation,
    SendDocument,
    SendMessage,
    SendPhoto,
    SendRichMessage,
)
from aiogram.types import (
    CallbackQuery,
    EphemeralMessageParameters,
    FSInputFile,
    InlineKeyboardButton as B,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichBlockButtons,
    InputRichBlockDivider,
    InputRichBlockFooter,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    Message,
    ReactionTypeEmoji,
    ReplyKeyboardMarkup,
    ReplyParameters,
    RichBlockTableCell,
    RichMessageButton,
    RichTextBold,
    RichTextCode,
    RichTextCustomEmoji,
    RichTextItalic,
    RichTextUnderline,
    RichTextUrl,
    Update,
    WebAppInfo,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import timedelta
from dotenv import load_dotenv
from functools import partial
from html.parser import HTMLParser
from pathlib import Path
from typing import Awaitable, Callable, Literal
from urllib.parse import quote as quote__i1, urlparse, urlsplit

# имена из более ранних файлов
from bot.data import Database, USERNAMES



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/perf.py
# Ускорение aiogram: синхронные фильтры — сразу в цикле событий, без отдельного потока.
#
# aiogram вызывает любой не-async фильтр (в том числе все `F.text.func(...)`) через asyncio.to_thread. У бота ~65 таких
# фильтров, и обычное сообщение «привет» проходит почти все: это ~65 прыжков в пул потоков на сообщение — основная
# часть времени обработки. Наши фильтры — короткие проверки (регулярки, сравнения), ничего не ждут, поэтому вызываем их
# напрямую. Обработчики (handlers) не трогаем: у бота они все async, а синхронные aiogram по-прежнему увезёт в поток.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
_applied = False


async def _call_inline(self: FilterObject, *args, **kwargs):
    wrapped = partial(self.callback, *args, **self._prepare_kwargs(kwargs))
    if self.awaitable:
        return await wrapped()
    return wrapped()


def apply__perf() -> None:
    global _applied
    if not _applied:
        FilterObject.call = _call_inline
        _applied = True


apply__perf()


# ---------- фоновые «печатает…» ----------

_bg__perf: set = set()


def chat_action(bot, chat_id: int, action: str) -> None:
    """«печатает…» / «отправляет фото…» — в фоне: ответ не ждёт лишний сетевой круг до Telegram."""
    async def _send():
        try:
            await bot.send_chat_action(chat_id, action)
        except Exception:
            pass
    try:
        t = asyncio.get_running_loop().create_task(_send())
    except RuntimeError:
        return
    _bg__perf.add(t)
    t.add_done_callback(_bg__perf.discard)



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/__init__.py
# Пакет бота. Файл .env читается СРАЗУ при импорте: часть модулей (rich_ui, ux, …) читает переключатели вроде RICH_UI или
# EPHEMERAL при загрузке, а load_config() вызывается позже. В Docker (env_file) переменные и так уже в окружении.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
def _load_dotenv(path: str = ".env") -> None:
    # Не подставляем ${...}: секреты и URL читаются буквально, окружение имеет приоритет.
    load_dotenv(path, override=False, interpolate=False)


_load_dotenv()




# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/alerts.py
# Оповещение владельцев о сбоях: необработанные ошибки, падение фоновых задач, старт после сбоя.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
# последние ошибки (время, тип исключения) — для диагностики; текст исключения не храним
RECENT: deque = deque(maxlen=10)


class Alerter:
    def __init__(self, bot, owner_ids, min_interval: float = 300, clock: Callable[[], float] = time.time):
        self.bot = bot
        self.owner_ids = list(owner_ids)
        self.min_interval = min_interval
        self.clock = clock
        self._last: float | None = None
        self._suppressed = 0

    async def alert(self, text: str) -> None:
        now = self.clock()
        if self._last is not None and now - self._last < self.min_interval:
            self._suppressed += 1
            return
        if self._suppressed:
            text += f"\n(ещё {self._suppressed} подобных сообщений пропущено)"
            self._suppressed = 0
        self._last = now
        for oid in self.owner_ids:
            try:
                await self.bot.send_message(oid, text)
            except Exception:
                logging.warning("alert to %s failed", oid)


def make_error_handler(alerter: Alerter):
    async def on_error(event) -> bool:
        exc = event.exception
        logging.error("Unhandled error in update", exc_info=exc)
        RECENT.append((int(time.time()), type(exc).__name__))
        # тип без текста исключения: в нём могут оказаться токены/данные пользователей
        uid = getattr(event.update, "update_id", "?")
        await alerter.alert(f"⚠️ Ошибка в боте: {type(exc).__name__} (update {uid}). Подробности — в логах сервера.")
        return True

    return on_error


# Обёртка фоновых задач из main.py (jobs): запускает, при падении логирует, шлёт алерт владельцам и перезапускает с паузой.
async def supervise(name: str, factory: Callable[[], Awaitable[None]], alerter: Alerter,
                    backoff: float = 5.0) -> None:
    """Запускает фоновую задачу заново после падения и сообщает владельцу."""
    while True:
        try:
            await factory()
            return
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception("background task %s crashed", name)
            RECENT.append((int(time.time()), f"{name}: {type(e).__name__}"))
            await alerter.alert(f"⚠️ Фоновая задача «{name}» упала ({type(e).__name__}) и перезапущена.")
            await asyncio.sleep(backoff)


def set_marker_and_check_crash(path: str) -> bool:
    """Ставит маркер «работаю». True, если он уже был — прошлый запуск не завершился штатно."""
    crashed = os.path.exists(path)
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w") as f:
            f.write(str(int(time.time())))
    except OSError:
        logging.warning("cannot write run marker %s", path)
    return crashed


def clear_marker(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/cleanup.py
# Кого предлагать к массовому исключению (чистая логика).
# ════════════════════════════════════════════════════════════════════════════════════════════════════
MAX_KICK = 200


def activity(m: dict, last_msg: dict[int, int] | None) -> tuple[int | None, bool]:
    """(когда человек был активен, писал ли он вообще). Активность — его собственные сообщения; нет сообщений — отсчёт
    идёт от входа в чат (или от первой встречи ботом). Упоминания и ответы ему активностью не считаются."""
    if last_msg is not None and m["user_id"] in last_msg:
        return last_msg[m["user_id"]], True
    return (m.get("joined_at") or m.get("first_seen")), False


def pick_candidates(kind: str, members: list[dict], writers: set[int], now: int, period: int,
                    exclude: set[int], last_msg: dict[int, int] | None = None) -> list[int]:
    """kind: 'неактив' — не появлялись дольше period; 'новичков' — вошли за последние period (рейд);
    'молчунов' — давно в чате, но не написали ни одного сообщения."""
    out = []
    for m in members:
        uid = m["user_id"]
        if uid in exclude:
            continue
        if kind == "неактив":
            if last_msg is not None:                       # по сообщениям: молчун тоже неактивен, считая от входа
                ts, _ = activity(m, last_msg)
                ok = ts is not None and now - ts > period
            else:
                ok = m["last_seen"] is not None and now - m["last_seen"] > period
        elif kind == "новичков":
            ok = m["joined_at"] is not None and now - m["joined_at"] < period
        else:  # молчунов
            since = m["joined_at"] or m["first_seen"]
            ok = uid not in writers and since is not None and now - since > period
        if ok:
            out.append(uid)
    return out[:MAX_KICK]



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/config.py
# ════════════════════════════════════════════════════════════════════════════════════════════════════
# ======= НАСТРОЙКИ БОТА =======
# Новая настройка из .env — три шага:
#   1) поле в Config ниже (с значением по умолчанию);
#   2) чтение в load_config(): os.environ.get("ИМЯ", ...);
#   3) пример в .env.example (+ проверка в validate(), если нужно).
# Потом в main.py её можно положить в dp["имя"] и получать в хендлерах параметром.
@dataclass
class Config:
    bot_token: str
    webapp_url: str
    owner_id: int
    webhook_secret: str
    db_path: str
    mode: str
    port: int = 8080
    webhook_url: str = ""   # куда Telegram шлёт обновления (порт 88/443/8443); по умолчанию — WEBAPP_URL
    owner_ids: frozenset = frozenset()
    database_url: str = ""
    river_api_key: str = ""
    river_base_url: str = "https://api.river.ai/v1"
    river_model: str = "deepseek-ai/DeepSeek-V4.1-Flash"
    river_vision_model: str = ""
    river_chat_vision_model: str = ""
    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai/v1"
    mistral_stt_model: str = "voxtral-mini-latest"
    update_workers: int = 64   # сколько обновлений обрабатывается одновременно (режим webhook)
    cf_account_id: str = ""        # Cloudflare Workers AI — генерация картинок
    cf_api_token: str = ""
    cf_image_model: str = "@cf/black-forest-labs/flux-1-schnell"
    premium_price: int = 70        # звёзд за 30 дней Premium

    # Проверка значений при старте: бот не запустится с ошибочной конфигурацией (SystemExit с понятным текстом)
    def validate(self) -> None:
        if not self.database_url and not self.db_path:
            raise SystemExit("DB_PATH не должен быть пустым")
        if self.mode not in ("polling", "webhook"):
            raise SystemExit("MODE должен быть polling или webhook")
        if not 1 <= self.port <= 65535:
            raise SystemExit("PORT должен быть от 1 до 65535")
        if self.update_workers < 1 or self.premium_price < 1:
            raise SystemExit("UPDATE_WORKERS и PREMIUM_PRICE должны быть положительными")
        if self.mode == "webhook":
            if not 16 <= len(self.webhook_secret) <= 256 or self.webhook_secret == "change-me-long-random" or not re.fullmatch(r"[A-Za-z0-9_-]+", self.webhook_secret):
                raise SystemExit("В режиме webhook задайте WEBHOOK_SECRET: 16–256 символов A–Z, a–z, 0–9, _ или -")
            try:
                base = self.webhook_url or self.webapp_url
                parsed = urlsplit(base)
                valid = parsed.scheme == "https" and parsed.hostname and parsed.port in (None, 80, 88, 443, 8443) and parsed.username is None and parsed.password is None and not parsed.query and not parsed.fragment and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in base)
            except ValueError:
                valid = False
            if not valid:
                raise SystemExit("WEBHOOK_URL должен быть HTTPS-адресом без пароля, query/fragment, порт 443, 80, 88 или 8443")


def _owner_ids() -> list[int]:
    """OWNER_ID=123 или несколько через запятую: OWNER_ID=123,456"""
    out = []
    for part in os.environ.get("OWNER_ID", "").replace(";", ",").split(","):
        part = part.strip()
        if not part or part == "0":
            continue
        if not re.fullmatch(r"[0-9]{1,19}", part) or not 0 < int(part) < 2**63:
            raise SystemExit("OWNER_ID должен содержать положительные числовые id через запятую")
        uid = int(part)
        if uid not in out:
            out.append(uid)
    return out


# Целое из переменной окружения: _int_env("PORT", 8080); при мусоре — понятная ошибка
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        raise SystemExit(f"{name} должен быть целым числом")


# Читает .env / переменные окружения и собирает Config. СЮДА добавляйте чтение новых переменных.
def load_config() -> Config:
    pass  # (импорт убран: всё в одном модуле)
    _load_dotenv()
    token = os.environ.get("BOT_TOKEN", "")
    if not token:
        raise SystemExit("BOT_TOKEN не задан (см. .env.example)")
    owners = _owner_ids()
    cfg = Config(
        bot_token=token,
        webapp_url=os.environ.get("WEBAPP_URL", "").rstrip("/"),
        owner_id=owners[0] if owners else 0,
        owner_ids=frozenset(owners),
        webhook_secret=os.environ.get("WEBHOOK_SECRET", ""),
        webhook_url=os.environ.get("WEBHOOK_URL", "").rstrip("/"),
        db_path=os.environ.get("DB_PATH", "data/bot.db") or "data/bot.db",
        mode=os.environ.get("MODE", "polling").strip().lower(),
        port=_int_env("PORT", 8080),
        database_url=os.environ.get("DATABASE_URL", ""),
        cf_account_id=os.environ.get("CF_ACCOUNT_ID", ""),
        cf_api_token=os.environ.get("CF_API_TOKEN", ""),
        cf_image_model=os.environ.get("CF_IMAGE_MODEL", "") or "@cf/black-forest-labs/flux-1-schnell",
        premium_price=_int_env("PREMIUM_PRICE", 70),
        river_api_key=os.environ.get("RIVER_API_KEY", ""),
        river_base_url=os.environ.get("RIVER_BASE_URL", "https://api.river.ai/v1").rstrip("/"),
        river_model=os.environ.get("RIVER_MODEL", "deepseek-ai/DeepSeek-V4.1-Flash"),
        river_vision_model=os.environ.get("RIVER_VISION_MODEL", ""),
        river_chat_vision_model=os.environ.get("RIVER_CHAT_VISION_MODEL", ""),
        mistral_api_key=os.environ.get("MISTRAL_API_KEY", ""),
        mistral_base_url=os.environ.get("MISTRAL_BASE_URL", "https://api.mistral.ai/v1").rstrip("/"),
        mistral_stt_model=os.environ.get("MISTRAL_STT_MODEL", "voxtral-mini-latest"),
        update_workers=_int_env("UPDATE_WORKERS", 64),
    )
    cfg.validate()
    return cfg



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/emoji_inject.py
# Автозамена обычных эмодзи на премиум в исходящих сообщениях и кнопках.
#
# Карта берётся из bot/emoji_map.json (строится tools/build_emoji_map.py из паков), плюс ALIASES — близкие по смыслу
# замены для эмодзи, которых в паках нет. Если Telegram отклонит запрос с заменами, сессия повторит его без замен.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
VS16 = "️"
ZWJ = "‍"
KEYCAP = "⃣"
MAX_PER_MESSAGE = 40
_MAP_FILE = Path(__file__).with_name("emoji_map.json")

# эмодзи, которых нет в паках → эмодзи из паков, близкий по смыслу
ALIASES__emoji_inject = {
    "🔨": "🚫", "👢": "⛔", "🎰": "🎁", "⚔": "🔥", "💍": "❤", "💞": "❤", "💔": "❌", "😘": "❤", "🤗": "❤",
    "🥰": "❤", "💖": "❤", "👶": "👤", "🎲": "🎯", "🎭": "🎨", "🤝": "👥", "🔮": "✨", "🕰": "⏱",
    "📖": "📝", "🎣": "🎯", "🧩": "✨", "📚": "📝", "🧠": "✨", "🧹": "🗑", "📝": "✏", "🗳": "📥", "⚖": "🛡", "🔫": "⚡", "🥳": "🎁", "🎉": "🎁",
}


def norm__emoji_inject(e: str) -> str:
    return e.replace(VS16, "")


def load_map() -> dict[str, str]:
    try:
        base = json.loads(_MAP_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    for char, like in ALIASES__emoji_inject.items():
        if char not in base and like in base:
            base[char] = base[like]
    return base


def _emoji_at(text: str, i: int, emap: dict) -> tuple[str, str, int] | None:
    """(исходный фрагмент, id, длина) если в позиции i стоит известный одиночный эмодзи, иначе None."""
    c = text[i]
    j = i + 1
    if c in "0123456789#*":  # keycap: цифра [FE0F] 20E3
        if j < len(text) and text[j] == VS16:
            j += 1
        if j < len(text) and text[j] == KEYCAP:
            key = c + KEYCAP
            return (text[i:j + 1], emap[key], j + 1 - i) if key in emap else None
        return None
    if ord(c) < 0x2000 and c not in "©®":
        return None
    if j < len(text) and text[j] == VS16:
        j += 1
    # составные последовательности (ZWJ, тон кожи) не трогаем целиком — не режем их на части
    if j < len(text) and (text[j] == ZWJ or "\U0001f3fb" <= text[j] <= "\U0001f3ff"):
        return None
    if i > 0 and text[i - 1] == ZWJ:
        return None
    cid = emap.get(norm__emoji_inject(c))
    return (text[i:j], cid, j - i) if cid else None


def _inject_text(text: str, emap: dict, budget: list[int]) -> str:
    out, i = [], 0
    while i < len(text):
        hit = _emoji_at(text, i, emap) if budget[0] > 0 else None
        if hit:
            frag, cid, n = hit
            out.append(f'<tg-emoji emoji-id="{cid}">{frag}</tg-emoji>')
            budget[0] -= 1
            i += n
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


_TAG_RE = re.compile(r"(<[^>]*>)")
_SKIP = {"code", "pre", "tg-emoji"}


def inject_html(html_text: str, emap: dict) -> str:
    """Заменяет эмодзи только в текстовых узлах; внутри <code>, <pre> и уже готовых <tg-emoji> не трогает."""
    if not emap or not html_text:
        return html_text
    budget = [MAX_PER_MESSAGE]
    depth = 0
    parts = []
    for tok in _TAG_RE.split(html_text):
        if tok.startswith("<") and tok.endswith(">"):
            m = re.match(r"<(/?)([a-zA-Z-]+)", tok)
            if m and m.group(2).lower() in _SKIP:
                depth += -1 if m.group(1) else 1
                depth = max(depth, 0)
            parts.append(tok)
        else:
            parts.append(tok if depth else _inject_text(tok, emap, budget))
    return "".join(parts)


def inject_markup(markup, emap: dict):
    """Ведущий эмодзи кнопки → icon_custom_emoji_id (текст без него). Остальные кнопки без изменений."""
    if not isinstance(markup, InlineKeyboardMarkup) or not emap:
        return markup
    rows = []
    for row in markup.inline_keyboard:
        new_row = []
        for b in row:
            hit = _emoji_at(b.text, 0, emap) if b.text and not b.icon_custom_emoji_id else None
            if hit:
                frag, cid, n = hit
                rest = b.text[n:].strip()
                if rest:  # кнопка только из эмодзи остаётся как есть
                    b = b.model_copy(update={"text": rest, "icon_custom_emoji_id": cid})
            new_row.append(b)
        rows.append(new_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _html_mode(method) -> bool:
    pm = method.parse_mode
    if pm is None:
        return False
    # Default("parse_mode") разворачивается позже, в нашем боте по умолчанию HTML
    return str(getattr(pm, "name", pm)).lower() in ("parse_mode", "html")


LONG_TEXT = 700          # обычное сообщение длиннее этого (без разметки): заголовок остаётся, остальное — в раскрывающуюся цитату
LONG_REST = 350


def quote_long(text: str) -> str:
    """Длинный HTML-текст: первая строка отдельно, остальное — <blockquote expandable>. Уже с цитатой/pre — не трогаем."""
    plain = re.sub(r"<[^>]+>", "", text)
    if len(plain) <= LONG_TEXT or "<blockquote" in text or "<pre" in text or "\n" not in text:
        return text
    head, _, rest = text.partition("\n")
    rest = rest.strip("\n")
    if len(re.sub(r"<[^>]+>", "", rest)) < LONG_REST:
        return text
    return f"{head}\n<blockquote expandable>{rest}</blockquote>"


def transform_method(method, emap: dict):
    """Копия метода с автозаменой; None — если менять нечего."""
    if isinstance(method, (SendMessage, EditMessageText)):
        upd = {}
        if _html_mode(method) and method.text:
            long_q = quote_long(method.text)
            if long_q != method.text:
                method = method.model_copy(update={"text": long_q})
                upd["text"] = long_q
            new = inject_html(method.text, emap)
            if new != method.text:
                upd["text"] = new
        mk = inject_markup(method.reply_markup, emap)
        if mk is not method.reply_markup and mk != method.reply_markup:
            upd["reply_markup"] = mk
        return method.model_copy(update=upd) if upd else None
    if isinstance(method, SendRichMessage):          # rich-экраны с inline-кнопками: иконки на кнопках — премиум
        mk = inject_markup(method.reply_markup, emap)
        return method.model_copy(update={"reply_markup": mk}) if mk is not method.reply_markup and mk != method.reply_markup else None
    if isinstance(method, (SendDocument, SendPhoto, SendAnimation, EditMessageCaption)):   # подписи к файлам и правка подписи
        upd = {}
        if _html_mode(method) and method.caption:
            new = inject_html(method.caption, emap)
            if new != method.caption:
                upd["caption"] = new
        mk = inject_markup(method.reply_markup, emap)
        if mk is not method.reply_markup and mk != method.reply_markup:
            upd["reply_markup"] = mk
        return method.model_copy(update=upd) if upd else None
    if isinstance(method, EditMessageReplyMarkup):   # кнопки меняют отдельным запросом (например, «Отменить» → пусто)
        mk = inject_markup(method.reply_markup, emap)
        return method.model_copy(update={"reply_markup": mk}) if mk is not method.reply_markup and mk != method.reply_markup else None
    return None


class EmojiSession(AiohttpSession):
    """HTTP-сессия бота: подменяет эмодзи на премиум; при отказе Telegram отправляет исходный текст."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.emap = load_map()

    FLOOD_RETRIES = 3        # сколько раз ждать и повторять при «слишком часто» от Telegram
    FLOOD_MAX_WAIT = 20.0    # дольше этого не ждём: обработчик не должен висеть минутами
    flood_waits = 0          # сколько раз упирались в лимит (для метрик)

    async def _raw(self, bot, method, timeout):
        return await super().make_request(bot, method, timeout)

    async def _send(self, bot, method, timeout):
        """Telegram режет частоту (≈20 сообщений/мин на группу, массовые удаления/баны тоже): вместо потери действия
        во время рейда ждём указанное сервером время и повторяем."""
        for attempt in range(self.FLOOD_RETRIES + 1):
            try:
                return await self._raw(bot, method, timeout)
            except TelegramRetryAfter as e:
                self.flood_waits += 1
                if attempt == self.FLOOD_RETRIES or e.retry_after > self.FLOOD_MAX_WAIT:
                    raise
                logging.warning("flood control: %s, жду %s с (попытка %s)", type(method).__name__, e.retry_after, attempt + 1)
                await asyncio.sleep(e.retry_after + 0.2)

    async def _with_punish_gif(self, bot, method, timeout):
        """Текст наказания + гифка одним сообщением: гифка уходит с этим текстом в подписи. None — это не такой текст."""
        pass  # (импорт убран: всё в одном модуле)
        if not isinstance(method, SendMessage) or not isinstance(method.chat_id, int):
            return None
        action = take__punish_gifs(method.chat_id, method.text)
        if action is None:
            return None
        anim = SendAnimation(
            chat_id=method.chat_id, animation=source(action), caption=method.text, parse_mode=method.parse_mode,
            reply_markup=method.reply_markup, reply_parameters=method.reply_parameters,
            message_thread_id=method.message_thread_id)
        changed = transform_method(anim, self.emap)
        try:
            res = await self._send(bot, changed or anim, timeout)
            remember__punish_gifs(action, res)
            return res
        except Exception as e:
            if isinstance(e, TelegramRetryAfter):
                raise
            logging.info("гифка с подписью не отправилась (%s) — шлю только текст", e)
            _ids.pop(FILES[action], None)
            return None

    async def make_request(self, bot, method, timeout=None):
        combined = await self._with_punish_gif(bot, method, timeout)
        if combined is not None:
            return combined
        changed = transform_method(method, self.emap)
        if changed is None:
            return await self._send(bot, method, timeout)
        try:
            return await self._send(bot, changed, timeout)
        except TelegramBadRequest as e:
            logging.warning("premium emoji rejected, sending plain: %s", str(e)[:120])
            return await self._send(bot, method, timeout)  # премиум-замена не принята — шлём как было



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/emoji.py
# Премиум-эмодзи.
#
# Чтобы подключить свои: впишите custom_emoji_id в PREMIUM_IDS вместо None.
# Пока id не заданы, используются обычные эмодзи из FALLBACK.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
FALLBACK = {
    "ban": "🔨", "mute": "🔇", "kick": "👢", "warn": "⚠️", "stats": "📊",
    "game": "🎮", "slots": "🎰", "shield": "🛡", "ok": "✅", "fail": "❌",
    "menu": "📋", "settings": "⚙️", "coin": "🪙", "trophy": "🏆", "duel": "⚔️",
    "unmute": "🔊", "pin": "📌",
}

# Единый источник правды — bot/emoji_map.json (строится из tools/emoji_choices.py): так «именованные» эмодзи
# и автозамена в тексте всегда показывают одну и ту же картинку.
_MAP = load_map()
PREMIUM_IDS: dict[str, str | None] = {name: _MAP.get(norm__emoji_inject(ch)) for name, ch in FALLBACK.items()}


def emoji(name: str) -> str:
    base = FALLBACK.get(name)
    if base is None:
        return ""
    pid = PREMIUM_IDS.get(name)
    if pid:
        return f'<tg-emoji emoji-id="{pid}">{base}</tg-emoji>'
    return base



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/fmt.py
# Оформление сообщений: цитаты для длинного и моноширинные таблицы (в Telegram нет настоящих таблиц).
# ════════════════════════════════════════════════════════════════════════════════════════════════════
_ELLIPSIS = "…"
MAX_PRE = 3500   # запас до лимита 4096 с учётом остального текста сообщения


class Html(str):
    """Уже готовый HTML (например, ссылка-упоминание): pre_table и kv_table вставляют его как есть, не экранируя и не обрезая."""


def esc__fmt(value) -> str:
    if isinstance(value, Html):
        return str(value)
    return html.escape(str(value if value is not None else ""))


def escaped_clip(text: str, max_html: int, max_utf16: int | None = None) -> str:
    """Экранировать и ограничить текст, не обрывая HTML-сущности или символы."""
    parts, html_len, utf16_len = [], 0, 0
    for char in str(text):
        piece = html.escape(char)
        units = 2 if ord(char) > 0xFFFF else 1
        if html_len + len(piece) > max_html or (max_utf16 is not None and utf16_len + units > max_utf16):
            break
        parts.append(piece)
        html_len += len(piece)
        utf16_len += units
    return "".join(parts)


def quote__fmt(body_html: str, expandable: bool | None = None) -> str:
    """Цитата вокруг УЖЕ экранированного HTML. Длинное (>300 символов или от 5 строк) сворачивается."""
    if expandable is None:
        expandable = len(body_html) > 300 or body_html.count("\n") >= 4
    open_tag = "<blockquote expandable>" if expandable else "<blockquote>"
    return f"{open_tag}{body_html}</blockquote>"      # закрывающий тег без атрибута — иначе Telegram: «Unclosed end tag»


def _cut(text, width: int) -> str:
    if isinstance(text, Html):
        return text
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: max(width - 1, 1)] + _ELLIPSIS


def _lines_block(lines: list[str], quoted: bool = True) -> str:
    """Строки внутри цитаты (quoted=False — обычным текстом); сворачиваем только действительно длинное."""
    body = "\n".join(lines)
    while len(body) > MAX_PRE and len(lines) > 1:   # слишком длинный список: режем хвост
        lines = lines[:-1]
        body = "\n".join(lines)
    return quote__fmt(body, expandable=len(lines) > 14 or len(body) > 1200) if quoted else body


def pre_table(rows: list[tuple], header: tuple | None = None, align: str = "", maxw: int | tuple = 22,
              gap: int = 2, quoted: bool = True) -> str:
    """«Таблица» цитатой: на телефонах моноширинные блоки ломают выравнивание (кириллица, эмодзи), поэтому
    строки выводятся читаемым списком: «1. Имя — значение · значение». Колонка «#»/«№» превращается в нумерацию,
    при 4+ колонках сверху идёт строка-подсказка. Значения экранируются здесь; align и gap оставлены для совместимости."""
    if not rows:
        return ""
    ncols = len(rows[0])
    caps = list(maxw) if isinstance(maxw, (tuple, list)) else [maxw] * ncols
    caps = [c * 2 for c in caps]                      # в цитате текст переносится — режем мягче
    numbered = bool(header) and header[0] in ("#", "№")
    lines = []
    if header and len([h for h in header if h not in ("#", "№")]) >= 4:
        names = [h for h in header if h not in ("#", "№")]
        lines.append(f"<i>{esc__fmt(names[0])} — " + esc__fmt(" · ".join(n.lower() for n in names[1:])) + "</i>")
    for r in rows:
        cells = [esc__fmt(_cut(c, caps[i])) for i, c in enumerate(r)]
        if numbered:
            head, rest = f"{cells[0]}. {cells[1]}", cells[2:]
        else:
            head, rest = cells[0], cells[1:]
        lines.append(head + (" — " + " · ".join(c for c in rest if c) if any(rest) else ""))
    return _lines_block(lines, quoted)


def kv_table(pairs: list[tuple[str, object]], key_width: int = 14, value_width: int = 24) -> str:
    """Пары «параметр: значение» цитатой."""
    return _lines_block([f"<b>{esc__fmt(_cut(k, key_width * 2))}:</b> {esc__fmt(_cut(v, value_width * 2))}" for k, v in pairs])



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/gender.py
# Пол пользователя для РП, семьи и пары: правильные окончания и местоимения. Пол выбирает сам человек (кнопки), хранится один раз.
#
# В текстах: ⟦ушёл|ушла⟧ — мужской|женский вариант (gz). Пол неизвестен — «ушёл(ла)»-подобная запись «ушёл/ушла».
# ════════════════════════════════════════════════════════════════════════════════════════════════════
_TOKEN = re.compile(r"⟦([^|⟧]*)\|([^⟧]*)⟧")
LABEL = {"m": "👨 Мужской", "f": "👩 Женский"}
_cache__gender: dict[int, str | None] = {}


def gz(text: str, gender: str | None) -> str:
    """Подставить род: m → первый вариант, f → второй, неизвестно → «первый/второй»."""
    def pick(m: re.Match) -> str:
        a, b = m.group(1), m.group(2)
        return a if gender == "m" else b if gender == "f" else f"{a}/{b}"
    return _TOKEN.sub(pick, text)


async def get(db: Database, uid: int) -> str | None:
    if uid in _cache__gender:
        return _cache__gender[uid]
    cur = await db.conn.execute("SELECT gender FROM user_gender WHERE user_id=?", (uid,))
    r = await cur.fetchone()
    g = r["gender"] if r else None
    _cache__gender[uid] = g
    return g


async def put(db: Database, uid: int, gender: str) -> None:
    if gender not in ("m", "f"):
        return
    await db.conn.execute("INSERT INTO user_gender(user_id, gender) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET gender=excluded.gender",
                          (uid, gender))
    await db.conn.commit()
    _cache__gender[uid] = gender


async def say(db: Database, uid: int, text: str) -> str:
    """Текст с ⟦м|ж⟧ по полу этого человека."""
    return gz(text, await get(db, uid))


def kb__gender(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text=LABEL["m"], callback_data=f"gd:{uid}:m"),
                                                  B(text=LABEL["f"], callback_data=f"gd:{uid}:f")]])


async def ensure(message: Message, db: Database) -> bool:
    """True — пол известен, команду можно выполнять. Иначе просим выбрать кнопкой (нажать может только автор команды)."""
    u = message.from_user
    if u is None or await get(db, u.id):
        return True
    await message.reply("Сначала скажи, ты парень или девушка: так я не буду путать окончания и местоимения. "
                        "Потом повтори команду.", reply_markup=kb__gender(u.id))
    return False


async def on_pick(cb: CallbackQuery, db: Database) -> None:
    parts = (cb.data or "").split(":")
    if len(parts) != 3 or not parts[1].isdigit() or parts[2] not in ("m", "f"):
        await cb.answer()
        return
    if cb.from_user.id != int(parts[1]):
        await cb.answer("Это не твой выбор", show_alert=True)
        return
    await put(db, cb.from_user.id, parts[2])
    await cb.answer("Запомнила ✅")
    if cb.message:
        word = "парень" if parts[2] == "m" else "девушка"
        try:
            await cb.message.edit_text(f"✅ Запомнила: {word}. Повтори команду. Поменять можно: <code>мой пол</code>.")
        except Exception:
            pass



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/i18n_en.py
# Английский перевод сообщений бота (подстановка по готовой русской фразе) и веб-панели.
# Ключ — русский текст ровно как в коде (без начального эмодзи), значение — английский. Пополняется вручную.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
MESSAGES = {
    "Баттл начинается!": "The battle begins!",
    "Веб-панель: настройки чатов (для админов и модераторов) и управление ботом (для владельца).": "Web panel: chat settings (admins and moderators) and bot management (owner).",
    "Время на ответ вышло.": "Time to answer is up.", "Вы не участвуете в этой дуэли.": "You are not in this duel.",
    "Вы уже проголосовали.": "You already voted.", "Вы уже сделали выбор.": "You already made your choice.",
    "Выбирает вызывающий.": "The challenger chooses.", "Выбор модели — в Premium.": "Model choice is in Premium.",
    "Выбор принят, ждём соперника.": "Choice accepted, waiting for the opponent.", "Вызов уже принят.": "Challenge already accepted.",
    "Вызов устарел.": "The challenge has expired.", "Голос учтён.": "Vote counted.", "Голосование закончено.": "Voting is over.",
    "Готово, добро пожаловать!": "Done, welcome!", "Дуэль ещё не началась.": "The duel hasn't started yet.",
    "Дуэль уже завершена.": "The duel is already over.", "Жалоба не найдена": "Report not found", "Запись устарела": "Entry is outdated",
    "Запрос устарел.": "Request expired.", "Запущено": "Started", "Исключаю…": "Removing…", "Клетка занята.": "Cell is taken.",
    "Награда снята.": "Award removed.", "Нажмите кнопку и пройдите проверку:": "Press the button and complete the check:",
    "Нашёл:": "Found:", "Не тот. Попробуйте ещё раз.": "Wrong one. Try again.",
    "Нет доступа к предложке этого чата.": "No access to this chat's suggestions.", "Никого не нашёл.": "Nobody found.",
    "Нужен ранг модератора": "Moderator rank required",
    "Откройте панель в личке с ботом (права проверяются при каждом действии):": "Open the panel in a private chat with the bot (permissions are checked on every action):",
    "Отменено": "Cancelled", "Отозвать может только автор.": "Only the author can withdraw this.",
    "Отозвать может только тот, кто вызывал.": "Only the challenger can withdraw this.",
    "Отправить во все активные чаты?": "Send to all active chats?", "Панель работает только в личке с ботом.": "The panel only works in a private chat with the bot.",
    "Панель чата. Видны только те разделы, на которые у вас есть права:": "Chat panel. You only see sections you have rights to:",
    "Подтвердить может только автор команды.": "Only the command author can confirm.", "Попытки закончились.": "No attempts left.",
    "Принято ✅": "Accepted ✅", "Принять может только вызванный игрок.": "Only the challenged player can accept.",
    "Пришлите ссылку на пост из соцсети": "Send a link to a social media post", "Проверка уже закончилась.": "The check is already over.",
    "Против себя голосовать нельзя.": "You can't vote against yourself.", "Сам себя не могнёшь 🗿": "You can't mog yourself 🗿",
    "Сейчас не ваш ход.": "It's not your turn.", "Список моделей обновился — откройте «модель» ещё раз.": "The model list was updated — open “model” again.",
    "Ставка должна быть от 1 монеты.": "The bet must be at least 1 coin.", "Только для модераторов": "Moderators only",
    "У вас больше нет прав на конкурсы в этом чате.": "You no longer have giveaway rights in this chat.", "Удалено": "Deleted",
    "Уже обработано": "Already handled", "Уже отменено": "Already cancelled", "Уже разобрана.": "Already reviewed.",
    "Черновик не найден — начните заново: «+конкурс» в чате.": "Draft not found — start over with “+giveaway” in the chat.",
    "Эта кнопка не для вас.": "This button isn't for you.", "Эта предложка уже удалена.": "This suggestion is already deleted.",
    "Эта проверка не для вас.": "This check isn't for you.", "Это не ваш вызов.": "This isn't your challenge.",
    "Это не ваша дуэль.": "This isn't your duel.", "Это предложение уже недействительно.": "This proposal is no longer valid.",
    "Это решение не за вами.": "This decision isn't yours.", "Этот шаг уже пройден.": "This step is already done.",
    "Активных наказаний нет.": "No active penalties.", "Пока нет сообщений по темам.": "No topic messages yet.",
    "Промокодов нет. Создать:": "No promo codes. Create one:", "Список пуст.": "The list is empty.",
    "Тем пока не видел: названия подтянутся, когда в них напишут.": "No topics seen yet: names appear once someone writes in them.",
    "У этого человека цитат пока нет.": "This person has no quotes yet.", "Фильтров нет. Добавить:": "No filters. Add one:",
    "Цитатник пуст. Ответьте": "The quote book is empty. Reply with", "на чьё-нибудь сообщение 😏": "to someone's message 😏",
    "Таймер поставлен.": "Timer set.", "Доступ команд сброшен к значениям по умолчанию.": "Command access reset to defaults.",
    "Mini App не настроен — обратитесь к администратору бота.": "Mini App is not configured — contact the bot administrator.",
    "WEBAPP_URL не настроен — веб-панель недоступна.": "WEBAPP_URL is not set — web panel unavailable.",
    "WEBAPP_URL не настроен — обратитесь к администратору бота.": "WEBAPP_URL is not set — contact the bot administrator.",
    "Администраторов голосованием наказывать нельзя.": "Admins can't be punished by vote.",
    "Будут удалены <b>все</b> сообщения этого чата. Это необратимо. Подтвердить?": "<b>All</b> messages of this chat will be deleted. This is irreversible. Confirm?",
    "В этом сообщении нет текста — цитировать нечего.": "This message has no text — nothing to quote.",
    "Включать и выключать РП могут только админы.": "Only admins can turn RP on and off.",
    "Владельца заблокировать нельзя.": "The owner can't be blocked.",
    "Все, кого я знал, уже вышли из чата: звать некого": "Everyone I knew has left the chat: nobody to call",
    "Вы исчерпали лимит оценок на сегодня.": "You've used up today's rating limit.",
    "Вы уже активировали этот промокод.": "You already activated this promo code.",
    "Выберите вариант кнопкой выше или напишите «отмена».": "Choose an option with the button above or write “cancel”.",
    "Выберите живого соперника, не себя и не бота": "Pick a live opponent, not yourself or a bot",
    "Голосование против этого человека уже идёт.": "A vote against this person is already running.",
    "Голосования в этом чате остановлены.": "Voting is turned off in this chat.",
    "Для конкурсов нужен WEBAPP_URL (проверка от ботов идёт в Mini App).": "Giveaways need WEBAPP_URL (the bot check runs in the Mini App).",
    "Для конкурсов нужен WEBAPP_URL.": "Giveaways need WEBAPP_URL.", "Дней — от 1 до 3650, активаций — от 1.": "Days: 1 to 3650, activations: at least 1.",
    "Дуэли работают только в группах.": "Duels only work in groups.", "ИИ не настроен.": "AI is not configured.",
    "ИИ не настроен: администратору бота нужно задать RIVER_API_KEY.": "AI is not configured: the bot administrator must set RIVER_API_KEY.",
    "Капча не работает: у бота нет права «ограничивать участников».": "Captcha is not working: the bot lacks the “restrict members” right.",
    "Лимит варнов — от 1 до 20.": "Warn limit: 1 to 20.", "Метрики не подключены.": "Metrics are not connected.",
    "Минимальный ранг — 1: открыть команду всем нельзя, это небезопасно.": "Minimum rank is 1: a command can't be opened to everyone, it's unsafe.",
    "Модераторов голосованием наказывать нельзя.": "Moderators can't be punished by vote.",
    "Модерация работает только в группах.": "Moderation only works in groups.",
    "На админов и модераторов жаловаться нельзя.": "You can't report admins and moderators.",
    "На себя и на бота жаловаться нельзя.": "You can't report yourself or the bot.",
    "На это сообщение уже пожаловались — модераторы в курсе.": "This message was already reported — moderators know.",
    "Напишите": "Write", "ответом на сообщение соперника.": "as a reply to your opponent's message.",
    "Напишите время текстом или нажмите кнопку.": "Type the time or press a button.",
    "Напишите идею сразу после команды:": "Write your idea right after the command:",
    "Нужен другой человек.": "Another person is needed.", "Нужен живой соперник, не вы сами и не я.": "A live opponent is needed — not you, not me.",
    "Нужен ранг %d или выше.": "Rank %d or higher is required.", "Нужен текст: что разыгрывается и условия (фото — по желанию, с подписью).": "Text needed: what's being given away and the conditions (photo optional, as a caption).",
    "Общий лимит бесплатных вопросов к ИИ в этом чате на сегодня исчерпан.": "The shared free AI question limit for this chat is used up for today.",
    "Остынь: вызывать можно раз в 30 секунд.": "Cool down: you can challenge once every 30 seconds.",
    "Ответьте": "Reply with", "на сообщение, которое нужно сохранить.": "to the message you want to save.",
    "Ответьте командой на сообщение получателя или укажите @ник.": "Reply with the command to the recipient's message or give an @username.",
    "Ответьте командой на сообщение соперника или укажите @ник:": "Reply with the command to your opponent's message or give an @username:",
    "Ответьте командой на сообщение человека или укажите @ник.": "Reply with the command to the person's message or give an @username.",
    "Ответьте командой на сообщение, которое нужно закрепить.": "Reply with the command to the message you want to pin.",
    "Ответьте командой на сообщение, которое нужно удалить.": "Reply with the command to the message you want to delete.",
    "Ответьте на сообщение, которое нужно сохранить.": "Reply to the message you want to save.",
    "Перевыбрать можно только после итогов.": "You can re-draw only after the results.", "Предупреждений ни у кого нет.": "Nobody has warnings.",
    "Пришлите текстом: id или @ник.": "Send as text: id or @username.", "Проверка не найдена, уже пройдена или время вышло.": "Check not found, already passed, or time ran out.",
    "Ранг этого человека не ниже вашего: менять его нельзя.": "This person's rank is not lower than yours: you can't change it.",
    "С ботами не могаются 🗿": "You don't mog bots 🗿", "Себе или боту ранг менять нельзя.": "You can't change your own or the bot's rank.",
    "Семейный бонус только для супругов: сначала поженитесь.": "The family bonus is for spouses only: marry first.",
    "Смотреть предложку этого чата может только его владелец.": "Only this chat's owner can view its suggestions.",
    "Создавать конкурсы в этом чате вы не можете.": "You can't create giveaways in this chat.", "Создание конкурса отменено.": "Giveaway creation cancelled.",
    "Список участников недавно проверяли — попробуйте позже.": "The member list was checked recently — try later.",
    "Срок: от 1 минуты до 30 дней, например": "Time: from 1 minute to 30 days, e.g.",
    "Так перевести нельзя: нужен другой человек и сумма от 1.": "Can't transfer that way: another person and an amount of 1 or more are needed.",
    "Такой промокод уже есть.": "This promo code already exists.", "У вас или у этого человека уже есть незавершённое предложение.": "You or this person already has a pending proposal.",
    "У вас не хватает монет на такую ставку.": "You don't have enough coins for this bet.",
    "У вас уже висит вызов — дождитесь ответа или отзовите его.": "You already have a pending challenge — wait for a reply or withdraw it.",
    "У вас уже есть незавершённый вызов.": "You already have a pending challenge.", "У одного из вас уже есть активная дуэль.": "One of you already has an active duel.",
    "Удалить цитату может тот, кто её добавил, её автор или модератор.": "A quote can be deleted by whoever added it, its author, or a moderator.",
    "Укажите id чата/канала:": "Give the chat/channel id:", "Укажите город, например:": "Give a city, e.g.:",
    "Укажите число:": "Give a number:", "(до 100).": "(up to 100).",
    "Этот конкурс уже завершён или не найден.": "This giveaway is already over or not found.", "Этот конкурс уже не идёт.": "This giveaway is no longer running.",
    "Я пока знаю слишком мало людей в этом чате": "I know too few people in this chat yet",
    "Я пока никого здесь не знаю": "I don't know anybody here yet", "звать некого": "nobody to call",
    "Отправлено.": "Sent.", "Правила сохранены.": "Rules saved.",
    "Больше выбрать некого: все участники уже побеждали или вышли из чата.": "No one left to pick: all participants already won or left the chat.",
    "Не знаю такого пользователя.": "I don't know such a user.", "Не знаю такой команды. Список —": "Unknown command. List —",
    "Не нашёл ни одного id или @ника. Пришлите числовые id и @ники, можно несколько.": "No ids or @usernames found. Send numeric ids and @usernames, several allowed.",
    "Не нашёл такого пользователя.": "User not found.", "Не нашёл такого участника в чате.": "Member not found in this chat.",
    "Не получилось получить ответ от ИИ, попробуйте позже.": "Couldn't get an AI answer, try again later.",
    "Не понял время. Примеры:": "Didn't get the time. Examples:", "Не похоже на домен. Пример:": "Doesn't look like a domain. Example:",
    "Не смог получить картинку для проверки (файл слишком большой или формат не поддерживается).": "Couldn't get the image to check (file too large or unsupported format).",
    "Не смог получить список админов — чистка отменена из осторожности.": "Couldn't get the admin list — cleanup cancelled to be safe.",
    "Не удалось отправить жалобу модераторам. Попробуйте позже.": "Couldn't send the report to moderators. Try later.",
    "Нет такого конкурса в этом чате.": "No such giveaway in this chat.",
    "Нечего откатывать: последнее действие уже отменено или наказаний не было.": "Nothing to undo: the last action was already undone or there were no penalties.",
    "Платежей этого пользователя не найдено.": "No payments from this user found.", "Подходящих участников не нашёл.": "No suitable members found.",
    "Слишком много попыток ввести промокод. Попробуйте через час.": "Too many promo code attempts. Try in an hour.",
    "Такого промокода нет или он закончился.": "No such promo code, or it has expired.", "Фильтр 18+ не загружен на этом сервере.": "The 18+ filter isn't loaded on this server.",
    "Сейчас конкурсов нет.": "No giveaways right now.", "Создадим конкурс в личке с ботом — там можно добавить фото и выбрать время.": "Let's create the giveaway in a private chat with the bot — you can add a photo and pick a time there.",
    "Генерация картинок не настроена (нужны CF_ACCOUNT_ID и CF_API_TOKEN).": "Image generation isn't configured (CF_ACCOUNT_ID and CF_API_TOKEN needed).",
    "ИИ временно отключён владельцем бота.": "AI is temporarily disabled by the bot owner.",
    "Общий лимит генерации на сегодня исчерпан, попробуйте завтра.": "The shared generation limit for today is used up, try tomorrow.",
    "Получилось 18+ — такое не отправляю. Попробуйте другое описание.": "That came out 18+ — I won't send it. Try another description.",
    "РП-команды и семья включены.": "RP commands and family are on.", "Сколько победителей?": "How many winners?",
    "Так рассылка будет выглядеть в чатах:": "This is how the broadcast will look in chats:",
    "Журнал отключён.": "Log disconnected.", "Сохранено.": "Saved.", "Жалоба отправлена модераторам.": "Report sent to moderators.",
    "Сверяю список участников с Telegram…": "Checking the member list against Telegram…", "Чат открыт для всех.": "The chat is open to everyone.",
    "Правила удалены.": "Rules deleted.", "Промокод удалён.": "Promo code deleted.", "Таймер удалён.": "Timer deleted.",
    "Фильтр удалён.": "Filter deleted.", "Мог-баттлов ещё не было. Вызов:": "No mog battles yet. Challenge:", "или просто": "or just",
    "Не получилось скачать. Попробуйте позже.": "Couldn't download. Try later.", "Сам себя? Выберите другого человека.": "Yourself? Pick someone else.",
    "ИИ в личке с ботом — в Nori Premium. Бесплатно ИИ работает в группах:": "AI in private chat is in Nori Premium. AI is free in groups:",
    "ИИ выключен в этом чате. Админ может включить его: «настройки» → «ИИ».": "AI is off in this chat. An admin can turn it on: “settings” → “AI”.",
    "Спасибо, но я всего лишь бот.": "Thanks, but I'm just a bot.", "Я всего лишь бот, у меня нет семьи.": "I'm just a bot, I have no family.",
    "для ваших вопросов «ии, …» (первая — по умолчанию):": "for your “ai, …” questions (the first is default):",
    "Выбор модели ИИ — в Nori Premium.": "AI model choice is in Nori Premium.", "Пока ничего не помню. Попросите:": "I don't remember anything yet. Ask:",
    "Очищаю чат… Это может занять время.": "Cleaning the chat… This may take a while.", "Вы сложили полномочия.": "You stepped down.",
    "Гостевые боты отвечают в чате, не будучи его участниками. «Проверять» — стоп-слова, фишинг и флуд к их сообщениям.": "Guest bots reply in the chat without being members. “Check” applies stop words, phishing and flood checks to their messages.",
    "Если бот назначен стражем заявок (настройки чата в Telegram), капча открывается прямо в заявке.": "If the bot is assigned as the join-request guard (Telegram chat settings), the captcha opens right inside the request.",
    "Сообщение гостевого бота": "Message of a guest bot", "гостевые боты запрещены": "guest bots are not allowed",
    "бота нет в белом списке": "bot is not on the allowlist", "бот запрещён в этом чате": "bot is blocked in this chat",
    "флуд гостевыми ботами": "guest-bot flood",
    "Id входящего уходит на api.lols.bot (и на api.cas.chat, если задан CAS_API_KEY); текст и имя не передаются.": "The joiner's id is sent to api.lols.bot (and api.cas.chat if CAS_API_KEY is set); text and name are not shared.",
    "в базе спамеров — забанен.": "is in the spammer database — banned.", "есть в базе спамеров.": "is in the spammer database.",
    "Оставлен: модератор решил, что это не спамер.": "Kept: the moderator decided this is not a spammer.",
    # заголовки
    "О чате": "About the chat", "Таймеры": "Timers", "Конкурсы": "Giveaways", "Промокоды": "Promo codes", "Цитаты": "Quotes",
    "Топ моггеров": "Top moggers", "Модель ИИ": "AI model", "Панель владельца": "Owner panel", "Приветствие": "Welcome",
    "Жалобы": "Reports", "Тарифы": "Plans", "Модераторы": "Moderators", "Доступ команд": "Command access", "Муты": "Mutes", "Баны": "Bans",
    "История:": "History:",
}

# Веб-панель: фрагменты (подстановка по подстроке; длинные первыми) и целые подписи
PANEL = {
    "Сессия устарела — закройте и откройте панель заново.": "Session expired — close and reopen the panel.",
    "Ошибка ": "Error ", " дн.": " d", " мин.": " min", "модератор": "moderator", "старший админ": "senior admin", "админ": "admin", "создатель": "owner",
    "Переключатель": "Switch", "Выбор": "Choice", "Точно? Нажмите ещё раз": "Sure? Tap again",
    "Настройки": "Settings", "Капча, антиспам, 18+, ИИ и другое": "Captcha, anti-spam, 18+, AI and more",
    "Жалобы": "Reports", "Очередь жалоб участников и ИИ": "Queue of member and AI reports", "История": "History",
    "Наказания участника": "Member penalties", "Статистика": "Statistics", "Активность и самые активные": "Activity and top members",
    "Стоп-слова": "Stop words", "Слова и выражения, которые удаляются": "Words and expressions that get deleted", "Ссылки": "Links",
    "Белый список доменов": "Domain allowlist", "Журнал": "Log", "Копия действий в отдельный чат или канал": "Copy of actions to a separate chat or channel",
    "Ранги": "Ranks", "Модераторы и доступ команд": "Moderators and command access", "Тексты": "Texts", "Правила и приветствие": "Rules and welcome",
    "Владелец": "Owner", "Бот целиком: функции, чаты, пользователи": "The whole bot: features, chats, users", "Ещё": "More",
    "Нет доступа": "No access", "Нужен ранг модератора": "Moderator rank required",
    "У вас нет прав в выбранном чате. Выберите другой чат сверху.": "You have no rights in the selected chat. Pick another chat above.",
    "Не получилось загрузить": "Failed to load", "Повторить": "Retry", "Сохранено": "Saved", "Изменения применяются сразу.": "Changes apply immediately.",
    "слово, фраза или выражение": "word, phrase or expression", "Слово или фраза": "Word or phrase", "Регулярное выражение": "Regular expression", "Тип": "Type",
    "Фильтр добавлен": "Filter added", "Сообщения с этими словами удаляются. Админов и модераторов фильтры не трогают.": "Messages with these words are deleted. Admins and moderators are not affected.",
    "Новый фильтр": "New filter", "Выражения: до 200 символов, без просмотров и вложенных повторов. Действие при срабатывании — в настройках, раздел «Стоп-слова».": "Expressions: up to 200 characters, no lookarounds or nested repeats. The action is set in Settings → “Stop words”.",
    "Добавить": "Add", "Фильтры": "Filters", " из ": " of ", "слово": "word", "Удалить фильтр ": "Delete filter ", "Фильтр удалён": "Filter deleted",
    "Фильтров пока нет": "No filters yet", "Добавьте слово выше — оно начнёт удаляться во всех сообщениях участников.": "Add a word above — it will be deleted from all member messages.",
    " или ": " or ", "Домен добавлен": "Domain added", "Ссылки разрешены всем": "Links allowed for everyone", "Ссылки запрещены новичкам": "Links blocked for newcomers",
    "Ссылки запрещены всем": "Links blocked for everyone", "Домены из этого списка разрешены всегда, даже если ссылки запрещены.": "Domains on this list are always allowed, even if links are blocked.",
    "Режим меняется в настройках, раздел «Антиспам». Работает при включённом антиспаме.": "The mode is changed in Settings → “Anti-spam”. Works while anti-spam is on.",
    "Добавить домен": "Add domain", "«*.домен» разрешает и поддомены.": "“*.domain” also allows subdomains.", "Разрешённые": "Allowed", "Убрать ": "Remove ",
    "Домен убран": "Domain removed", "Список пуст": "The list is empty", "Добавьте домены, ссылки на которые нужно разрешать.": "Add domains whose links should be allowed.",
    "Нужен числовой id чата или канала": "A numeric chat or channel id is needed", "Журнал подключён": "Log connected",
    "Копия действий модерации, смены настроек и рангов в отдельный чат или канал.": "A copy of moderation actions, settings and rank changes in a separate chat or channel.",
    "Подключён": "Connected", "Не подключён": "Not connected", "Чат или канал ": "Chat or channel ", "Действия сейчас нигде не дублируются": "Actions are not duplicated anywhere now",
    "Подключить": "Connect", "Вы должны быть админом того чата или канала, а бот — уметь туда писать: он отправит пробное сообщение.": "You must be an admin of that chat or channel and the bot must be able to post there: it will send a test message.",
    "Отключить журнал": "Disconnect log", "Журнал отключён": "Log disconnected", "Ранг ": "Rank ", "id пользователя": "user id",
    "Ваш ранг: ": "Your rank: ", ". Админы Telegram получают ранг 3, создатель — 5.": ". Telegram admins get rank 3, the owner — 5.", "Модераторы": "Moderators",
    "Ранг изменён": "Rank changed", "ранг ": "rank ", "Снять ранг у ": "Remove rank from ", "Ранг снят": "Rank removed", "Пока никого": "Nobody yet",
    "Админы Telegram считаются модераторами автоматически.": "Telegram admins count as moderators automatically.", "Назначить модератора": "Appoint a moderator",
    "Выдать можно ранг ниже вашего, но не выше 4.": "You can grant a rank below yours, up to 4.", "Назначить": "Appoint", "Нужен числовой id": "A numeric id is needed",
    "Модератор назначен": "Moderator appointed", "Доступ команд": "Command access", "Минимальный ранг для каждой команды. Открыть команду всем нельзя — это небезопасно.": "Minimum rank for each command. A command can't be opened to everyone — it's unsafe.",
    "изменено": "changed", "Сбросить доступ к умолчанию": "Reset access to defaults", "Доступ сброшен": "Access reset", "Пока пусто": "Empty for now", "Сохранить": "Save",
    "Правила": "Rules", "Показываются по команде «правила».": "Shown by the “rules” command.", "Приветствие": "Welcome", "{name} заменяется на имя вошедшего.": "{name} is replaced by the joiner's name.",
    "открыта": "open", "сообщение удалено": "message deleted", "мут": "mute", "бан": "ban", "отклонена": "dismissed", "Открытые": "Open", "Все": "All", "Фильтр жалоб": "Report filter",
    "Жалоба №": "Report #", "От ": "From ", " на": " against", "Причина: ": "Reason: ", "Удалить": "Delete", "Сообщение удалено": "Message deleted", "Мут 1 ч": "Mute 1 h",
    "Мут выдан": "Muted", "Бан": "Ban", "Бан выдан": "Banned", "Отклонить": "Dismiss", "Жалоба отклонена": "Report dismissed", "Жалоб не было": "No reports",
    "Очередь пуста": "Queue is empty", "Когда участник пожалуется или ИИ найдёт нарушение, карточка появится здесь.": "When a member reports or AI finds a violation, a card will appear here.",
    "кик": "kick", "варн": "warn", "снять варн": "remove warn", "разбан": "unban", "размут": "unmute", "удаление": "deletion", "ранг": "rank", "жалоба": "report", "ошибка ИИ": "AI error",
    "@ник или id участника": "@username or member id", "варнов: ": "warns: ", "бан ": "ban ", "мут ": "mute ", "до ": "until ", "бессрочно": "forever", "жалоб: ": "reports: ", "чисто": "clean",
    "Записи": "Records", "В журнале чисто": "The log is clean", "У этого участника не было наказаний.": "This member has had no penalties.", "Назад": "Back", "Дальше": "Next",
    "Все наказания участника: когда, кто, на какой срок и за что.": "All member penalties: when, by whom, for how long and why.", "Найти": "Search",
    "пн": "Mon", "вт": "Tue", "ср": "Wed", "чт": "Thu", "пт": "Fri", "сб": "Sat", "вс": "Sun", "Когда пишут": "When people write", "Сообщения по часам суток за 30 дней": "Messages by hour of day, 30 days",
    "Сообщения по часам суток": "Messages by hour of day", "По дням недели": "By day of week", "Сообщения по дням недели": "Messages by day of week", "Новые участники": "New members",
    "Сейчас в чате: ": "In the chat now: ", "24 ч": "24 h", "7 дн": "7 d", "30 дн": "30 d", "90 дн": "90 d", " сообщений за ": " messages in ", " часа": " hours", " дней": " days",
    "Период": "Period", "Сообщения": "Messages", "Самые активные": "Top members", "Данных пока нет": "No data yet", "Статистика копится по мере того, как участники пишут.": "Stats accumulate as members write.",
    "Нет данных": "No data", "График сообщений, максимум ": "Message chart, max ", " за час": " per hour", " за день": " per day", "пик ": "peak ", " д ": " d ", " ч": " h",
    "Найти: @ник, id или имя": "Search: @username, id or name", "Разбанить": "Unban", "Разбанен": "Unbanned", "Бан в боте": "Ban in bot", "Забанен в боте": "Banned in bot",
    "Никого не нашёл": "Nobody found", "Управление ботом целиком.": "Manage the whole bot.", "Статус": "Status", "Работает": "Uptime", "Пользователей": "Users", "Чатов": "Chats", "База": "Database",
    " КБ": " KB", "ИИ / расшифровка": "AI / transcription", "да": "yes", "нет": "no", "В блок-листе": "Blocklisted", " польз. · ": " users · ", "Функции": "Features",
    "Действуют сразу во всех чатах.": "Apply to all chats immediately.", "Чаты": "Chats", " участн.": " members", "заблокирован": "blocked", "активен": "active", "неактивен": "inactive",
    "Пользователи": "Users", "Резервная копия": "Backup", "Файл содержит данные всех чатов — храните его так же бережно, как токен.": "The file contains data of all chats — keep it as safe as the token.",
    "Скачать копию базы": "Download database copy", "Копия скачана": "Copy downloaded", "Панель": "Panel", "Откройте из Telegram": "Open from Telegram",
    "Панель работает как мини-приложение: нажмите кнопку «Открыть веб-панель» в чате с ботом.": "The panel is a mini app: press “Open web panel” in the chat with the bot.",
    "Не удалось войти": "Sign-in failed", "Закройте панель и откройте её заново.": "Close the panel and open it again.", "Нет чатов": "No chats", "Выбрать чат": "Choose chat", "Разделы": "Sections",
    # данные с сервера (подписи настроек и флагов)
    "ИИ (команда «ии»)": "AI (the “ai” command)", "Расшифровка голосовых": "Voice transcription", "Фильтр 18+": "18+ filter", "ИИ-модерация": "AI moderation", "Режим обслуживания": "Maintenance mode",
}



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/i18n.py
# Английский интерфейс. Язык задаётся настройкой чата «Язык» (в личке — по языку Telegram пользователя).
#
# Как это работает: тексты бота написаны по-русски; на выходе (запрос к Telegram) они проходят через словарь фраз,
# если у чата язык en. Переводятся меню, настройки, мастер настройки, статистика, опросы, память, основные статусы и
# сообщения об ошибках. В английских чатах работают и английские команды: ban, mute, stats, balance… (см. ALIASES).
# Тексты, которых нет в словаре, остаются русскими — словарь можно пополнять.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
# ---------- команды ----------
# английская фраза -> русская команда. Длинные проверяются первыми.
# ДОБАВИТЬ АНГЛИЙСКУЮ КОМАНДУ: "english phrase": "русская команда" (бот всё равно понимает только русские хендлеры).
ALIASES__i18n = {
    "unban": "разбан", "ban": "бан", "kick": "кик", "unmute": "размут", "mute": "мут",
    "remove warn": "снять варн", "unwarn": "снять варн", "warns": "варны", "warn": "варн",
    "history": "история", "stats": "стата", "stat": "стата", "balance": "баланс", "bonus": "бонус", "top": "топ",
    "menu": "меню", "help": "помощь", "settings": "настройки", "poll": "опрос", "report": "жалоба",
    "delete": "удалить", "unpin": "открепить", "pin": "закреп", "purge": "чистка", "clean": "чистка",
    "rules": "правила", "reputation": "репутация", "rep": "репутация", "rating": "рейтинг", "who is inactive": "кто неактив",
    "inactive": "кто неактив", "web panel": "веб-панель", "panel": "веб-панель", "topics": "темы",
    "remember": "запомни", "what do you remember": "что ты помнишь", "forget": "забудь", "memory on": "память вкл",
    "memory off": "память выкл", "slots": "слоты", "roulette": "рулетка", "duel": "дуэль", "garden": "огород",
    "marry": "брак", "divorce": "развод", "my family": "моя семья", "who am i": "кто я", "my profile": "моя анкета",
    "ask,": "ии,", "ai,": "ии,", "diagnostics": "диагностика",
}
_ARG = {"week": "неделя", "month": "месяц", "all": "вся", "forever": "навсегда", "topics": "темы", "day": "сутки"}
_ARG_FORGET = {"all": "все", "everything": "всё"}
_ARG_BACK = {"неделя": "week", "месяц": "month", "вся": "all", "навсегда": "forever", "темы": "topics", "сутки": "day",
             "все": "all", "всё": "all"}
_DUR_BACK = re.compile(r"\b(\d+)([мчд])\b")
_DUR_BACK_MAP = {"м": "m", "ч": "h", "д": "d"}
_DUR = re.compile(r"^(\d+)([mhd])$")
_DUR_RU = {"m": "м", "h": "ч", "d": "д"}
_ALIAS_ORDER = sorted(ALIASES__i18n, key=len, reverse=True)
_REVERSE = {ru: en for en, ru in sorted(ALIASES__i18n.items(), key=lambda kv: -len(kv[0])) if ru not in ("ии,",)}
_REVERSE.update({"стата": "stats", "чистка": "purge", "репутация": "reputation", "кто неактив": "inactive",
                 "веб-панель": "web panel", "снять варн": "remove warn", "что ты помнишь": "what do you remember"})


def alias_to_ru(text: str) -> str | None:
    """«ban @vasya 1d spam» → «бан @vasya 1д spam»; не команда → None."""
    t = text.strip()
    low = t.lower()
    for en in _ALIAS_ORDER:
        if low == en or low.startswith(en + " ") or (en.endswith(",") and low.startswith(en)):
            rest = t[len(en):].strip()
            toks = []
            for w in rest.split(" "):
                lw = w.lower()
                m = _DUR.match(lw)
                if m:
                    toks.append(f"{m.group(1)}{_DUR_RU[m.group(2)]}")
                elif en == "forget":
                    toks.append(_ARG_FORGET.get(lw, w))
                elif en in ("stats", "stat", "ban", "mute", "topics"):
                    toks.append(_ARG.get(lw, w))
                else:
                    toks.append(w)
            return (ALIASES__i18n[en] + (" " + " ".join(toks) if toks else "")).strip()
    return None


# ---------- интерфейс ----------
# подстроки (достаточно длинные и специфичные, чтобы не портить чужой текст)
# ДОБАВИТЬ ПЕРЕВОД ТЕКСТА: "русский фрагмент": "English fragment". Большие списки — в bot/i18n_en.py (MESSAGES).
PHRASES = {
    "Меню Chat Helper": "Chat Helper menu", "Выберите раздел": "Choose a section",
    "Настройки чата": "Chat settings", "К разделам": "Back to sections", "В меню": "To menu", "Открыть как приложение": "Open as app",
    "Открыть веб-панель": "Open web panel", "Веб-панель": "Web panel", "Меню команд": "Command menu",
    "Добавить в чат": "Add to chat", "Первая настройка": "First setup",
    "Включите нужное (только админы). Остальное — в разделе «Все настройки».": "Turn on what you need (admins only). Everything else is in “All settings”.",
    "Все настройки": "All settings",
    "Ответом на сообщение или с @ником.": "Reply to a message or add an @username.",
    "Дайте боту права админа: удаление, ограничение участников, приглашения, закрепление.": "Give the bot admin rights: delete messages, restrict members, invite users, pin messages.",
    "Включается в": "Turn on in",
    "антиспам · антирейд · фильтр 18+ · стоп-слова · капча · ИИ-модерация · расшифровка голосовых": "anti-spam · anti-raid · 18+ filter · stop words · captcha · AI moderation · voice transcription",
    "Привет! Я Chat Helper — помощник для чатов.": "Hi! I'm Chat Helper — an assistant for chats.",
    "Модерация, защита от спама, статистика, игры и ИИ.": "Moderation, spam protection, stats, games and AI.",
    "Как начать": "Getting started",
    "Добавьте меня в чат — кнопка ниже сама выдаст нужные права.": "Add me to a chat — the button below requests the right permissions.",
    "В чате появится мастер первой настройки: включите капчу, антиспам и приветствие.": "A setup wizard will appear in the chat: enable captcha, anti-spam and the welcome message.",
    "Все команды — ": "All commands — ", "настройки — ": "settings — ",
    "Подсказки по командам в любом чате: напишите @имя_бота и слово — например, «бан».": "Command hints in any chat: type @botname and a word, e.g. “ban”.",
    "@ник": "@username", "Вопрос | да | нет": "Question | yes | no", "диагностика": "diagnostics", "владельцу": "owner only",
    "Модерация": "Moderation", "Игры и фан": "Games & fun", "РП и семья": "RP & family", "Ранги и профиль": "Ranks & profile",
    "Защита": "Protection", "Помощь": "Help",
    # статусы и ошибки
    "Готово.": "Done.", "Запомнил.": "Got it.", "Всё забыл.": "Forgot everything.", "Забыл.": "Forgotten.",
    "Нужен ранг": "Rank required:", "Нужен другой человек": "Another person is needed",
    "Не хватает монет": "Not enough coins", "Баланс": "Balance", "Ваш баланс": "Your balance",
    "Бонус уже получен сегодня. Приходите завтра!": "Daily bonus already claimed. Come back tomorrow!",
    "Ежедневный бонус": "Daily bonus", "Подождите": "Please wait", "С Premium — без ожидания.": "No waiting with Premium.",
    "Вы исчерпали лимит оценок на сегодня.": "You've used up today's rating limit.",
    "Вы уже оценивали этого человека за последний час.": "You already rated this person in the last hour.",
    "Нет доступа": "No access", "Только для админов": "Admins only", "Сохранено": "Saved",
    "Не нашёл": "Couldn't find", "Не получилось": "Failed",
    "Настройки доступны в группе.": "Settings are available in a group chat.",
    "Настройки только для админов и модераторов с нужным рангом.": "Settings are for admins and moderators with the required rank only.",
    "Только для админов и модераторов с нужным рангом": "Admins and moderators with the required rank only",
    # модерация
    "забанен": "banned", "разбанен": "unbanned", "в муте на": "muted for", "может писать снова": "can write again",
    "исключён": "removed", "предупреждение": "warning", "предупреждений": "warnings", "Лимит достигнут — мут на 1 дн.": "Limit reached — muted for 1 day.",
    "сообщение удалено": "message deleted", "Исключить": "Remove", "Отмена": "Cancel", "Отменено.": "Cancelled.",
    "Забанить": "Ban", "Это не он": "Not him", "Оставлен: модератор решил, что это не двойник.": "Kept: the moderator decided it's not a duplicate.",
    "похож на забаненного": "looks like banned user", "сходство": "similarity", "Решает модератор.": "A moderator decides.",
    "Неактивные": "Inactive", "Кик всех": "Kick all", "Неактивных": "Inactive", "дн.": "d",
    # статистика и таблицы
    "Статистика": "Statistics", "за 24 часа": "for 24 hours", "за неделю": "for a week", "за месяц": "for a month",
    "за всё время": "for all time", "Участник": "Member", "Сообщ.": "Msgs", "Пока нет сообщений.": "No messages yet.",
    "Предупреждения": "Warnings", "Рейдинг репутации": "Reputation ranking", "Рейтинг репутации": "Reputation ranking",
    "Репутация": "Reputation", "Богатейшие": "Richest", "Победы в дуэлях": "Duel wins", "Темы": "Topics", "Тема": "Topic", "Доля": "Share",
    "Досье": "File", "видно модераторам": "visible to moderators", "Сейчас": "Now", "без наказаний": "no penalties",
    "Наказаний за всё время": "Penalties in total", "Сообщений": "Messages", "Все записи": "All records",
    # опросы / память / темы
    "Формат:": "Format:", "Ключи в конце:": "Options at the end:", "Вопрос — от 1 до 300 символов.": "Question: 1 to 300 characters.",
    "Нужно от 2 до": "Need 2 to", "вариантов.": "options.", "Что я помню о вас": "What I remember about you",
    "Пока ничего не помню.": "I don't remember anything yet.", "Память выключена.": "Memory is off.",
    "Память включена.": "Memory is on.", "Удалить:": "Delete:", "для ответов ИИ": "for AI replies",
    "Тема тихая: бот не отвечает участникам.": "Quiet topic: the bot won't answer members here.",
    "Тема снова обычная.": "Topic is back to normal.", "Пока нет сообщений по темам.": "No topic messages yet.",
    "Напишите это внутри нужной темы.": "Send this inside the topic you want.",
    # капча
    "Проверка пройдена": "Verification passed", "Добро пожаловать": "Welcome",
}

PHRASES.update(MESSAGES)
# целиком совпадающие подписи кнопок (после снятия эмодзи/отметок)
# ПОДПИСИ КНОПОК (целиком): "Русская кнопка": "English button"
EXACT = {
    "Модерация": "Moderation", "Статистика": "Statistics", "Игры и фан": "Games & fun", "Защита": "Protection",
    "РП и семья": "RP & family", "Настройки": "Settings", "Ранги и профиль": "Ranks & profile", "Помощь": "Help",
    "Капча": "Captcha", "Капча для новичков": "Captcha for newcomers", "Время": "Time", "1 мин": "1 min", "3 мин": "3 min",
    "5 мин": "5 min", "10 мин": "10 min", "Повторно": "Repeat", "Нет": "No", "Без @ника": "No @username", "Всем": "Everyone",
    "Антиспам": "Anti-spam", "Флуд, сообщ.": "Flood, msgs", "за, сек": "per, sec", "Одинаковые сообщения": "Duplicate messages",
    "Ссылки": "Links", "Всем можно": "Allowed", "Новичкам нет": "Not for newcomers", "Всем нет": "Not allowed",
    "Упоминаний макс.": "Max mentions", "Пересылки от новичков": "Forwards from newcomers", "ИИ-проверка новичков": "AI check of newcomers",
    "Действие": "Action", "Удалить": "Delete", "Варн": "Warn", "Мут": "Mute", "Фишинг": "Phishing", "Фишинг-ссылки": "Phishing links",
    "Стоп-слова": "Stop words", "Антирейд": "Anti-raid", "Двойники забаненных": "Banned-user lookalikes", "Входов": "Joins",
    "Новичкам": "Newcomers", "Кик": "Kick", "Режим, мин": "Mode, min", "Фильтр 18+": "18+ filter", "Строгость": "Strictness",
    "Строго": "Strict", "Средне": "Medium", "Мягко": "Soft", "ИИ-проверка (картинка уходит во внешний ИИ)": "AI check (image goes to an external AI)",
    "Расшифровка": "Transcription", "Расшифровка голосовых": "Voice transcription", "Макс. длина": "Max length",
    "ИИ-модерация": "AI moderation", "Проверять": "Check", "Выкл": "Off", "Новичков": "Newcomers", "Подозрительное": "Suspicious",
    "Жалоба": "Report", "Уверенность": "Confidence", "ИИ": "AI", "Команда «ии …»": "“ai …” command", "Живое общение": "Live chat",
    "Отвечает": "Replies", "Болтает": "Chats", "Стиль": "Style", "По-свойски (с матом)": "Casual (with swearing)", "Вежливо": "Polite",
    "Приветствие": "Welcome", "Жалобы": "Reports", "Команда «жалоба»": "“report” command", "Команды": "Commands",
    "Общий сбор": "Rally", "Цитатник": "Quotes", "Мог-баттлы": "Mog battles", "Конкурсы": "Giveaways", "Предложка": "Suggestions",
    "Картинки «нарисуй»": "Image generation", "Скачивание «скачай»": "Downloads", "Скачивание по ссылке": "Auto download",
    "Игры": "Games", "«кто …»": "“who …”", "Репутация": "Reputation", "Варны": "Warns", "Лимит до автомута": "Warns until auto-mute",
    "Срок жизни варна": "Warn lifetime", "7 д": "7 d", "30 д": "30 d", "90 д": "90 d", "Бессрочно": "Forever",
    "База спамеров": "Spammer database", "Новички из базы спамеров": "Newcomers in spammer DB", "Уведомлять": "Notify", "Банить": "Ban",
    "Гостевые боты": "Guest bots", "Режим": "Mode", "Белый список": "Allowlist", "Запретить": "Block",
    "Заявки без капчи": "Requests without captcha", "Админам": "To admins", "Принять": "Approve",
    "Язык": "Language", "Язык / Language": "Language", "Русский": "Русский", "English": "English",
    "В меню": "To menu", "К разделам": "Back to sections", "Меню": "Menu", "Все настройки": "All settings",
    "Исключить": "Remove", "Отмена": "Cancel", "Да": "Yes", "Забанить": "Ban", "Это не он": "Not him",
    "Нори Premium": "Nori Premium", "Бан везде": "Ban everywhere",
}
USER_LANG: dict[int, str] = {}          # user_id -> language_code из Telegram (личные чаты)
_MARK = re.compile(r"^((?:[✅❌•⬅️➡️◀️▶️]\s*)*)(?:([^\w\s«»(]{1,4})\s+)?(.*)$", re.DOTALL)
_BOLD = re.compile(r"<b>([^<>]{1,60})</b>")
_CODE = re.compile(r"<code>(.*?)</code>", re.DOTALL)
_PH_ORDER = sorted(PHRASES, key=len, reverse=True)


def _code_en(m: re.Match) -> str:
    inner = m.group(1)
    low = inner.lower()
    for ru in sorted(_REVERSE, key=len, reverse=True):
        if low == ru or low.startswith(ru + " "):
            rest = _DUR_BACK.sub(lambda mm: mm.group(1) + _DUR_BACK_MAP[mm.group(2)], inner[len(ru):])
            rest = " ".join(_ARG_BACK.get(w, w) for w in rest.split(" "))
            return "<code>" + _REVERSE[ru] + rest + "</code>"
    return m.group(0)


def translate__i18n(text: str | None, lang: str) -> str | None:
    if not text or lang != "en":
        return text
    out = _CODE.sub(_code_en, text)
    out = _BOLD.sub(lambda m: "<b>" + translate_button(m.group(1), lang) + "</b>", out)     # заголовки: «🛡 Капча» → «🛡 Captcha»
    for ru in _PH_ORDER:
        if ru in out:
            out = out.replace(ru, PHRASES[ru])
    return out


def translate_button(label: str, lang: str) -> str:
    if lang != "en" or not label:
        return label
    m = _MARK.match(label)
    lead, emoji, rest = (m.group(1) or "", m.group(2) or "", m.group(3)) if m else ("", "", label)
    if rest in EXACT:
        return lead + (emoji + " " if emoji else "") + EXACT[rest]
    return translate__i18n(label, lang)


def translate_markup(markup, lang: str):
    if lang != "en" or markup is None:
        return markup
    if isinstance(markup, InlineKeyboardMarkup):
        rows = [[b.model_copy(update={"text": translate_button(b.text, lang)}) for b in row] for row in markup.inline_keyboard]
        return markup.model_copy(update={"inline_keyboard": rows})
    return markup


_EMOJI_TAG = r"(?:<tg-emoji[^>]*>[^<]*</tg-emoji>\s*)*"
_INNER = re.compile(r"(<(?:tg-button|h[1-6]|th)\b[^>]*>)(" + _EMOJI_TAG + r")([^<]*)(</(?:tg-button|h[1-6]|th)>)")


def translate_html(text: str, lang: str) -> str:
    """HTML rich-сообщения: подписи кнопок, заголовков и шапки таблиц переводятся целиком (с учётом иконки <tg-emoji>
    слева), остальное — по словарю фраз."""
    if lang != "en" or not text:
        return text
    text = _INNER.sub(lambda m: m.group(1) + m.group(2) + translate_button(m.group(3).strip(), lang) + m.group(4), text)
    return translate__i18n(text, lang)


def _tr_value(v, lang: str):
    if isinstance(v, str):
        core = v.strip()
        lead, trail = v[:len(v) - len(v.lstrip())], v[len(v.rstrip()):]
        out = translate_button(core, lang) if len(core) < 60 else translate__i18n(core, lang)
        return lead + out + trail
    if isinstance(v, list):
        return [_tr_value(x, lang) for x in v]
    if isinstance(v, dict):
        return {k: (_tr_value(x, lang) if k in ("text", "caption") else _walk(x, lang)) for k, x in v.items()}
    return v


def _walk(v, lang: str):
    if isinstance(v, dict):
        return {k: (_tr_value(x, lang) if k in ("text", "caption") else translate_html(x, lang) if k == "html" and isinstance(x, str)
                    else _walk(x, lang)) for k, x in v.items()}
    if isinstance(v, list):
        return [_walk(x, lang) for x in v]
    return v


def translate_rich(msg, lang: str):
    """Переводит тексты внутри rich-сообщения (таблицы статистики и топов): заголовок, шапка, подписи."""
    try:
        return type(msg).model_validate(_walk(msg.model_dump(exclude_none=True), lang))
    except Exception:
        return msg


def pick_lang(setting: str | None, user_code: str | None = None) -> str:
    """Язык чата из настройки; для личек (настройки нет) — по языку Telegram пользователя."""
    if setting in ("ru", "en"):
        return setting
    return "en" if (user_code or "").lower().startswith("en") else "ru"


class TranslateMiddleware(BaseRequestMiddleware):
    """Переводит исходящие тексты и кнопки, если у чата язык en. Ничего не знает про хендлеры — работает на уровне запросов."""

    def __init__(self, db):
        self.db = db

    async def _lang(self, chat_id) -> str:
        if not isinstance(chat_id, int):
            return "ru"
        if chat_id > 0:                                   # личка: язык пользователя из Telegram
            return pick_lang(None, USER_LANG.get(chat_id))
        return pick_lang((await self.db.get_settings(chat_id)).get("lang"))

    async def __call__(self, make_request, bot: Bot, method):
        chat_id = getattr(method, "chat_id", None)
        if chat_id is not None and any(hasattr(method, a) for a in ("text", "caption", "reply_markup", "question")):
            lang = await self._lang(chat_id)
            if lang == "en":
                upd = {}
                for attr in ("text", "caption"):
                    v = getattr(method, attr, None)
                    if isinstance(v, str) and not getattr(method, "entities", None):   # текст с entities (правила чата) — как есть
                        upd[attr] = translate__i18n(v, lang)
                rm = getattr(method, "reply_markup", None)
                if rm is not None:
                    upd["reply_markup"] = translate_markup(rm, lang)
                rich = getattr(method, "rich_message", None)
                if rich is not None:
                    upd["rich_message"] = translate_rich(rich, lang)
                if upd:
                    method = method.model_copy(update=upd)
        return await make_request(bot, method)


class CommandAliasMiddleware(BaseMiddleware):
    """В английских чатах понимает английские команды (ban, mute, stats …): переписывает их в русские до разбора."""

    def __init__(self, db):
        self.db = db

    async def __call__(self, handler, m, data):
        if m.text and m.from_user is not None and not m.text.startswith("/"):
            setting = (await self.db.get_settings(m.chat.id)).get("lang") if m.chat.type in ("group", "supergroup") else None
            if pick_lang(setting, m.from_user.language_code) == "en":
                ru = alias_to_ru(m.text)
                if ru:
                    m = m.model_copy(update={"text": ru, "entities": None})
        return await handler(m, data)



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/keyboards.py
# ════════════════════════════════════════════════════════════════════════════════════════════════════
def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="🛡 Модерация", callback_data="menu:mod"),
         B(text="📊 Статистика", callback_data="menu:stats")],
        [B(text="🎮 Игры и фан", callback_data="menu:games"),
         B(text="🚫 Защита", callback_data="menu:protect")],
        [B(text="🎭 РП и семья", callback_data="menu:rp"),
         B(text="⚙️ Настройки", callback_data="menu:settings")],
        [B(text="🎖 Ранги и профиль", callback_data="menu:ranks"),
         B(text="❓ Помощь", callback_data="menu:help")],
    ])


def section_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="⬅️ В меню", callback_data="menu:home")]
    ])


def stats_keyboard(active: str) -> InlineKeyboardMarkup:
    def b(label: str, key: str) -> B:
        mark = "• " if key == active else ""
        return B(text=mark + label, callback_data=f"stats:{key}", style="primary" if key == active else None)
    return InlineKeyboardMarkup(inline_keyboard=[
        [b("2 часа", "2"), b("День", "24"), b("Вся", "all")]
    ])


def undo_keyboard(action: str, target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="↩️ Отменить", callback_data=f"undo:{action}:{target_id}")]
    ])



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/links.py
# Ссылки в сообщениях: извлечение доменов и проверка по белому списку чата.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
_TLDS = r"(?:com|ru|org|net|io|me|su|xyz|top|site)"
_RE__links = re.compile(
    r"https?://(?P<h1>[^\s/?#]+)"
    r"|(?P<h2>www\.[^\s/?#]+)"
    r"|(?<![@\w.\-])(?P<h3>(?:[\w\-]+\.)+" + _TLDS + r")\b",
    re.IGNORECASE)


def normalize_domain(raw: str) -> str | None:
    """«https://www.Example.com/a» → «example.com»; «*.x.org» сохраняется; мусор → None."""
    s = (raw or "").strip().lower()
    if not s or " " in s:
        return None
    wildcard = s.startswith("*.")
    if wildcard:
        s = s[2:]
    if "://" in s:
        try:
            s = urlparse(s).netloc
        except ValueError:
            return None
    s = s.split("/")[0].split("?")[0].split("#")[0]
    s = s.rsplit("@", 1)[-1].split(":")[0].strip(".,;:!?)(\"'«»")
    if s.startswith("www."):
        s = s[4:]
    if "." not in s or s.startswith(".") or ".." in s:
        return None
    try:
        s = s.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    if len(s) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in s.split(".")):
        return None
    return ("*." if wildcard else "") + s


def extract_hosts(text: str, entities) -> set[str]:
    hosts: set[str] = set()
    for e in entities or []:
        if e.type == "text_link" and e.url:
            d = normalize_domain(e.url)
        elif e.type == "url":
            d = normalize_domain(e.extract_from(text))
        else:
            continue
        if d:
            hosts.add(d)
    for m in _RE__links.finditer(text or ""):
        d = normalize_domain(m.group("h1") or m.group("h2") or m.group("h3"))
        if d:
            hosts.add(d)
    return hosts


def host_allowed(host: str, allow: set[str]) -> bool:
    """Точное совпадение; поддомены — только если в списке явно «*.домен» (он же разрешает и сам домен)."""
    if host in allow:
        return True
    parts = host.split(".")
    return any("*." + ".".join(parts[i:]) in allow for i in range(len(parts) - 1))



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/members.py
# Сверка списка участников с Telegram: кто вышел, пока бот не видел (не был админом, был выключен), — убираем.
#
# Telegram присылает событие о выходе только админу и только пока бот работает, поэтому одних событий мало:
# список проверяется перед «общим сбором», раз в 12 часов в фоне и по команде «проверить участников».
# ════════════════════════════════════════════════════════════════════════════════════════════════════
SWEEP_EVERY = 12 * 3600
SWEEP_FIRST_DELAY = 600
PAUSE__members = 0.05            # ~20 запросов в секунду: укладываемся в лимиты Bot API с запасом


def is_present(m) -> bool:
    return m.status in ("member", "administrator", "creator") or (
        m.status == "restricted" and getattr(m, "is_member", True))


async def check(bot, db: Database, chat_id: int, user_id: int) -> bool | None:
    """True — в чате, False — вышел (помечен неактивным), None — не удалось узнать (ничего не меняем)."""
    try:
        m = await bot.get_chat_member(chat_id, user_id)
    except TelegramBadRequest as e:
        # Ошибки чата или прав бота не говорят ничего о конкретном участнике.
        message = str(e).lower()
        if "user not found" in message or "participant_id_invalid" in message:
            await db.set_member_active(chat_id, user_id, False)
            return False
        return None
    except Exception:
        return None
    if is_present(m):
        return True
    await db.set_member_active(chat_id, user_id, False)
    return False


async def sync_chat(bot, db: Database, chat_id: int, pause: float = PAUSE__members) -> tuple[int, int]:
    """Проверяет всех известных участников чата. (сколько проверено, сколько убрано как вышедших)."""
    removed = checked = 0
    for m in await db.members_info(chat_id):
        res = await check(bot, db, chat_id, m["user_id"])
        if res is not None:
            checked += 1
            removed += res is False
        if pause:
            await asyncio.sleep(pause)
    return checked, removed


async def sweep_loop(bot, db: Database) -> None:
    await asyncio.sleep(SWEEP_FIRST_DELAY)
    while True:
        started, total = time.time(), 0
        for c in await db.list_chats(0, 10000, active_only=True):
            try:
                _, removed = await sync_chat(bot, db, c["chat_id"])
                total += removed
            except Exception:
                logging.exception("members sweep failed for %s", c["chat_id"])
        logging.info("сверка участников: убрано вышедших %s за %.0f с", total, time.time() - started)
        await asyncio.sleep(SWEEP_EVERY)



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/metrics.py
# Лёгкие метрики работы бота: сколько обновлений, как быстро обрабатываются, сколько ошибок, размер БД.
# Живут в памяти (сбрасываются при перезапуске); владельцу доступны командой «метрики» в личке.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
SLOW_MS = 500.0


class Metrics:
    def __init__(self, window: int = 2000):
        self.started = time.time()
        self.total = 0
        self.errors = 0
        self.slow = 0
        self._lat: deque[float] = deque(maxlen=window)      # миллисекунды
        self._stamps: deque[float] = deque(maxlen=20000)    # когда пришли последние обновления

    def record(self, ms: float, ok: bool = True) -> None:
        self.total += 1
        self._lat.append(ms)
        self._stamps.append(time.time())
        if not ok:
            self.errors += 1
        if ms >= SLOW_MS:
            self.slow += 1

    def rate(self, seconds: float = 60.0, now: float | None = None) -> float:
        """Обновлений в секунду за последние seconds секунд."""
        now = time.time() if now is None else now
        n = sum(1 for t in reversed(self._stamps) if now - t <= seconds)
        return n / seconds

    def percentile(self, p: float) -> float:
        if not self._lat:
            return 0.0
        data = sorted(self._lat)
        return data[min(int(len(data) * p), len(data) - 1)]

    def render(self, db_path: str = "", extra: dict | None = None) -> str:
        up = int(time.time() - self.started)
        lines = [
            "📈 <b>Метрики</b>",
            f"Работает: {up // 86400} д {up % 86400 // 3600} ч {up % 3600 // 60} мин",
            f"Обновлений: {self.total} · сейчас {self.rate():.2f}/с (за минуту)",
            f"Время обработки: p50 {self.percentile(.5):.1f} мс · p95 {self.percentile(.95):.1f} мс · p99 {self.percentile(.99):.1f} мс",
            f"Ошибок: {self.errors} · медленных (>{int(SLOW_MS)} мс): {self.slow}",
        ]
        if db_path and os.path.exists(db_path):
            lines.append(f"База: {os.path.getsize(db_path) / 1048576:.1f} МБ")
        for k, v in (extra or {}).items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)


class MetricsMiddleware(BaseMiddleware):
    """Внешний слой на update: замеряет полное время обработки и считает ошибки."""

    def __init__(self, metrics: Metrics):
        self.metrics = metrics

    async def __call__(self, handler, event, data):
        t = time.perf_counter()
        ok = True
        try:
            return await handler(event, data)
        except Exception:
            ok = False
            raise
        finally:
            self.metrics.record((time.perf_counter() - t) * 1000, ok)



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/parsing.py
# ════════════════════════════════════════════════════════════════════════════════════════════════════
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

_SLASH__parsing = {
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
_NAME_RE__parsing = re.compile(
    r"^(" + "|".join(re.escape(n).replace(r"\ ", r"\s+") for n in _NAMES) + r")(?=\s|$)",
    re.IGNORECASE,
)
_TARGET_RE__parsing = re.compile(r"^(@\w+|\d{5,})$")
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
    m = _NAME_RE__parsing.match(text)
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
        if _TARGET_RE__parsing.match(t):
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
    if not m or m.group(1).lower() not in _SLASH__parsing:
        return None
    name = _SLASH__parsing[m.group(1).lower()]
    parts = (m.group(2) or "").strip().split()
    target = duration = None
    if parts and _TARGET_RE__parsing.match(parts[0]):
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


_STATS_RE__parsing = re.compile(r"^(?:стата|статистика)(?:\s+(.+))?$", re.IGNORECASE)
_HOURS_RE = re.compile(r"^(\d+)\s*(?:час|часа|часов|ч)$", re.IGNORECASE)


def parse_stats_command(text: str) -> StatsPeriod | None:
    m = _STATS_RE__parsing.match(text.strip())
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



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/plans.py
# Тарифы: бесплатный и Premium (подписка за звёзды Telegram). Здесь только цифры и «какой тариф у человека».
# ════════════════════════════════════════════════════════════════════════════════════════════════════
PREMIUM_PRICE = 70                 # звёзд за 30 дней (PREMIUM_PRICE в .env)
PREMIUM_DAYS = 30
PREMIUM_PERIOD = PREMIUM_DAYS * 86400   # Telegram принимает для подписок за звёзды только 30 дней


@dataclass(frozen=True)
class Plan:
    name: str
    ai_daily: int          # вопросов к ИИ в сутки (лично)
    ai_cooldown: int       # секунд между вопросами
    ai_max_tokens: int     # длина ответа
    ai_reply_chars: int
    img_daily: int         # картинок в сутки
    img_cooldown: int
    choose_model: bool     # выбор модели ИИ
    ai_private: bool       # ИИ в личке с ботом


FREE = Plan("Бесплатный", ai_daily=25, ai_cooldown=20, ai_max_tokens=800, ai_reply_chars=2000,
            img_daily=5, img_cooldown=45, choose_model=False, ai_private=False)
PREMIUM = Plan("Premium", ai_daily=150, ai_cooldown=0, ai_max_tokens=1600, ai_reply_chars=3500,
               img_daily=30, img_cooldown=0, choose_model=True, ai_private=True)


async def plan_for(db, user_id: int, owner_ids: frozenset = frozenset(), now: int | None = None) -> Plan:
    """Владельцы бота — всегда Premium; остальные — по оплаченной подписке."""
    if user_id in owner_ids:
        return PREMIUM
    until = await db.premium_until(user_id)
    return PREMIUM if until and until > (int(time.time()) if now is None else now) else FREE


def benefits_text(price: int = PREMIUM_PRICE) -> str:
    return (f"⭐ <b>Nori Premium</b> — {price} звёзд в месяц\n"
            f"• ИИ без кулдауна (бесплатно — раз в {FREE.ai_cooldown} с)\n"
            f"• {PREMIUM.ai_daily} вопросов к ИИ в сутки вместо {FREE.ai_daily}, ответы длиннее и подробнее\n"
            "• выбор модели ИИ: <code>модель</code>\n"
            "• ИИ в личке с ботом\n"
            f"• {PREMIUM.img_daily} картинок в сутки вместо {FREE.img_daily}, без ожидания: <code>нарисуй …</code>\n"
            "Подписка продлевается автоматически, отменить можно в любой момент в Telegram.")



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/punish_gifs.py
# Гифки к бану, муту, варну, разбану и размуту: файл грузится один раз, дальше отправляем по file_id.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
ASSETS__punish_gifs = Path(__file__).with_name("assets") / "punish"
FILES = {"бан": "ban.mp4", "разбан": "unban.mp4", "мут": "mute.mp4", "размут": "unmute.mp4", "варн": "warn.mp4"}
MIN_GAP = 20                     # не чаще раза в 20 секунд на чат и вид (рейд, массовые баны — без потока гифок)
PENDING_WAIT = 4                 # столько ждём, пока текст наказания дойдёт до отправки: тогда гифка уйдёт вместе с ним
CAPTION_MAX__punish_gifs = 1000
_ids: dict[str, str] = {}
_pending__punish_gifs: dict[tuple[int, str], str] = {}
_last__punish_gifs: dict[tuple[int, str], float] = {}
_bg__punish_gifs: set = set()


async def send__punish_gifs(bot, chat_id: int, action: str, thread_id: int | None = None, delay: float = 0.6) -> None:
    name = FILES.get(action)
    if name is None:
        return
    now = time.time()
    if now - _last__punish_gifs.get((chat_id, action), 0) < MIN_GAP:
        return
    _last__punish_gifs[(chat_id, action)] = now
    await asyncio.sleep(delay)                       # сначала приходит текст, потом гифка
    path = ASSETS__punish_gifs / name
    try:
        src = _ids.get(name) or FSInputFile(path)
        msg = await bot.send_animation(chat_id, src, message_thread_id=thread_id)
        if name not in _ids and getattr(msg, "animation", None):
            _ids[name] = msg.animation.file_id
    except Exception as e:
        _ids.pop(name, None)                         # id мог устареть — в следующий раз загрузим файл заново
        logging.info("гифка %s не отправилась: %s", action, e)


def spawn(bot, chat_id: int, action: str, thread_id: int | None = None) -> None:
    """В фоне: ответ на команду не ждёт загрузку гифки."""
    if action not in FILES:
        return
    try:
        t = asyncio.get_running_loop().create_task(send__punish_gifs(bot, chat_id, action, thread_id))
    except RuntimeError:
        return
    _bg__punish_gifs.add(t)
    t.add_done_callback(_bg__punish_gifs.discard)


def source(action: str):
    """Что отправлять: file_id (если уже загружали) или сам файл."""
    name = FILES[action]
    return _ids.get(name) or FSInputFile(ASSETS__punish_gifs / name)


def remember__punish_gifs(action: str, msg) -> None:
    name = FILES.get(action)
    anim = getattr(msg, "animation", None)
    if name and anim is not None and name not in _ids:
        _ids[name] = anim.file_id


def arm(bot, chat_id: int, text: str, action: str) -> None:
    """Гифка должна уйти вместе с этим текстом (подписью): сессия бота подменит отправку текста на гифку с подписью.
    Если текст так и не отправили (или его изменили) — через PENDING_WAIT секунд шлём гифку отдельно."""
    if action not in FILES:
        return
    now = time.time()
    if now - _last__punish_gifs.get((chat_id, action), 0) < MIN_GAP:
        return
    if len(text) > CAPTION_MAX__punish_gifs:                      # в подпись не влезает — гифка отдельно, как раньше
        spawn(bot, chat_id, action)
        return
    _last__punish_gifs[(chat_id, action)] = now
    key = (chat_id, text)
    _pending__punish_gifs[key] = action

    async def fallback():
        await asyncio.sleep(PENDING_WAIT)
        if _pending__punish_gifs.pop(key, None) is not None:
            _last__punish_gifs.pop((chat_id, action), None)
            await send__punish_gifs(bot, chat_id, action, delay=0)
    try:
        t = asyncio.get_running_loop().create_task(fallback())
    except RuntimeError:
        _pending__punish_gifs.pop(key, None)
        return
    _bg__punish_gifs.add(t)
    t.add_done_callback(_bg__punish_gifs.discard)


def take__punish_gifs(chat_id: int, text: str | None) -> str | None:
    """Если для этого текста ждёт гифка — забрать (и больше не отправлять отдельно)."""
    return _pending__punish_gifs.pop((chat_id, text), None) if text else None



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/ranks.py
# Ранги модераторов (1–5) и «доступ команд» (ДК): какой минимальный ранг нужен для каждой команды.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
MAX_RANK = 5          # создатель чата
MAX_ASSIGNABLE = 4    # выдать можно ранги до 4; 5 — только у создателя Telegram-чата
TG_ADMIN_RANK = 3     # Telegram-админ с правом ограничивать участников

# ДОСТУП КОМАНД (ДК): какой минимальный ранг нужен. Ранги: 0 участник, 1–4 модераторы, 5 создатель.
# Новая команда с ограничением: добавьте "название": ранг сюда; в хендлере — need_rank(access, "название").
# Админы чата переопределяют значения командой «дк» (хранится в БД), эти — значения по умолчанию.
DEFAULT_ACCESS = {
    "варн": 1, "снять варн": 1, "мут": 1, "размут": 1, "удалить": 1,
    "фильтры": 3, "ссылки": 3,   # стоп-слова и белый список ссылок
    "история": 1,          # просмотр наказаний участника
    "кик": 2, "чистка": 2, "закреп": 2, "открепить": 2,
    "бан": 3, "разбан": 3,
    "амнистия": 4,         # снять баны и муты со всех
    "вайп": 2,             # удалить сообщения участника за 48 часов
    "триггеры": 4, "белый список": 3, "блок стикеров": 3, "фейс-контроль": 4, "faq": 3, "повторы": 4, "сетка": 5,
    "массовый бан": 3,     # бан списка id/@ников из веб-панели
    "очистить чат": 4,     # удаление ВСЕХ сообщений чата (ниже 4 понизить нельзя — см. bot.purge.MIN_RANK)
    "модер": 4,            # выдача и снятие рангов
    "массовый кик": 4,     # кик неактив / новичков / молчунов
    "настройки чата": 4,   # правила, приветствие, +чат / -чат, ДК
    "награды": 3,
    "неактивные": 2,       # список неактивных участников («кто неактив»)
    "общий сбор": 2,       # позвать всех участников чата (с упоминанием)
    "конкурсы": 5,
    "предложка": 5,        # смотреть и разбирать предложку (по умолчанию — владелец чата)         # создавать и отменять розыгрыши (по умолчанию — только владелец чата)
}


# Нужный ранг для команды: сначала настройки чата, затем DEFAULT_ACCESS, иначе 3
def need_rank(access: dict[str, int], command: str) -> int:
    return access.get(command, DEFAULT_ACCESS.get(command, 3))


# Ранг по статусу в Telegram: создатель → 5, админ с правом банить → 3, остальные → 0
def tg_rank(status: str, can_restrict: bool) -> int:
    if status == "creator":
        return MAX_RANK
    if status == "administrator" and can_restrict:
        return TG_ADMIN_RANK
    return 0



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/rich.py
# Богатые сообщения Telegram (Bot API 10.1+): настоящие таблицы вместо моноширинного текста.
# Если Telegram или клиент не принял такое сообщение, вызывающий код получает None и отправляет обычный текст.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
def _cell__rich(text, *, header: bool = False, align: str = "left"):
    return RichBlockTableCell(align=align, valign="middle", text=text, is_header=True if header else None)


async def send_table(bot, chat_id: int, title: str, header: list[str], rows: list[list], *, aligns: list[str] | None = None,
                     reply_markup=None, reply_to: int | None = None, thread_id: int | None = None):
    """rows — списки ячеек; ячейка — строка или (текст, ссылка). Возвращает отправленное сообщение или None."""
    aligns = aligns or ["left"] * len(header)

    def conv(v):
        if isinstance(v, tuple):
            return RichTextUrl(text=v[0], url=v[1]) if v[1] else v[0]
        return v

    cells = [[_cell__rich(RichTextBold(text=h), header=True, align=a) for h, a in zip(header, aligns)]]
    cells += [[_cell__rich(conv(v), align=a) for v, a in zip(r, aligns)] for r in rows]
    msg = InputRichMessage(blocks=[
        InputRichBlockSectionHeading(text=title, size=3),
        InputRichBlockTable(cells=cells, is_bordered=True, is_striped=True)])
    try:
        return await bot.send_rich_message(
            chat_id=chat_id, rich_message=msg, reply_markup=reply_markup, message_thread_id=thread_id,
            reply_parameters=ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None)
    except Exception as e:                       # старый сервер/клиент, лимиты — не страшно, будет текстовая таблица
        logging.info("rich table не отправлена: %s", e)
        return None



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/rich_ui.py
# Экраны в стиле rich-сообщений Telegram: заголовок, текст, таблица команд и кнопки-«таблетки» по центру внутри самого
# сообщения (с премиум-эмодзи в кнопках), а не отдельной клавиатурой под ним.
#
# Один экран (Screen) умеет показываться двумя способами:
#   • rich — настоящее rich-сообщение (Bot API 10.1+): блоки heading / paragraph / table / buttons;
#   • classic — обычное сообщение с HTML-текстом и inline-клавиатурой (если Telegram или клиент rich не принял).
# Выбор автоматический: сначала пробуем rich, при отказе помним об этом 10 минут и отвечаем обычным сообщением.
#
# При нажатии кнопки `show` всегда правит сообщение на месте (rich, а если нельзя — обычным текстом).
# ════════════════════════════════════════════════════════════════════════════════════════════════════
# RICH_UI в .env: hybrid (по умолчанию) — rich-текст и таблицы + обычные inline-кнопки под ними (премиум-иконки на кнопках,
# правка на месте); 1 — кнопки-таблетки внутри rich-сообщения; 0 — только обычные сообщения без rich.
MODE = os.environ.get("RICH_UI", "hybrid").lower()
ENABLED = MODE != "0"
PILLS = MODE == "1"
# В группах Telegram вырезает премиум-эмодзи при ЛЮБОЙ правке rich-сообщения (в личке — нет; проверено пробой), поэтому в группах
# экраны показываются обычными сообщениями (премиум-эмодзи остаются, правка на месте работает). RICH_IN_GROUPS=1 вернёт rich и туда.
RICH_IN_GROUPS = os.environ.get("RICH_IN_GROUPS", "0") == "1"
_off_until__rich_ui = 0.0                         # rich недоступен — до этого момента не пробуем (секунды, time.time)
OFF_FOR__rich_ui = 600
MAX_ROW = 8                              # в одном блоке buttons — до 8 кнопок
_emap: dict | None = None
_use_html = os.environ.get("RICH_FORM", "html") != "blocks"      # html | blocks — в какой форме слать rich


def _has_custom_emoji(obj) -> bool:
    """Есть ли в rich-сообщении (модель или словарь) узлы custom_emoji."""
    try:
        data = obj.model_dump(exclude_none=True) if hasattr(obj, "model_dump") else obj
    except Exception:
        return True
    stack = [data]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if x.get("type") == "custom_emoji":
                return True
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
    return False


def _map() -> dict:
    global _emap
    if _emap is None:
        _emap = load_map()
    return _emap


@dataclass
class Btn:
    """Кнопка экрана. Ровно одно из cb / url / web_app. style: primary | success | danger | link."""
    text: str
    cb: str | None = None
    url: str | None = None
    web_app: str | None = None
    style: str | None = None


@dataclass
class Screen:
    """title — заголовок; body — элементы: строка (абзац, мини-HTML: <b> <i> <code> <a>), ("table", [строки]) где строка —
    (команда, описание) или текст, ("rows", header, rows) — таблица из колонок, "---" — разделитель;
    rows — ряды кнопок; footer — мелкая подпись внизу; classic — готовый HTML для обычного сообщения (если нужен
    свой вид вместо автоматического)."""
    title: str | None = None
    body: list = field(default_factory=list)
    rows: list[list[Btn]] = field(default_factory=list)
    footer: str | None = None
    classic: str | None = None
    classic_rows: list | None = None         # другой набор кнопок для обычного сообщения (если нужен иной порядок)
    quote: bool = False                      # весь текст экрана одной цитатой; длинные абзацы и так сворачиваются в цитату


# ---------- мини-HTML → rich text ----------
class _P(HTMLParser):
    def __init__(self, convert_emoji: bool):
        super().__init__(convert_charrefs=True)
        self.root: list = []
        self.stack: list[tuple[str, list, dict]] = []
        self.cur = self.root
        self.convert_emoji = convert_emoji
        self._skip_emoji_text = 0

    def handle_starttag(self, tag, attrs):
        tag = {"strong": "b", "em": "i"}.get(tag, tag)
        if tag in ("b", "strong", "i", "em", "code", "u", "a", "tg-emoji"):
            self.stack.append((tag, self.cur, dict(attrs)))
            self.cur = []

    def handle_endtag(self, tag):
        if tag == "strong":
            tag = "b"
        if tag == "em":
            tag = "i"
        if not self.stack or self.stack[-1][0] != tag:
            return
        t, parent, attrs = self.stack.pop()
        inner = _simplify(self.cur)
        self.cur = parent
        if t == "b":
            node = RichTextBold(text=inner)
        elif t == "i":
            node = RichTextItalic(text=inner)
        elif t == "code":
            node = RichTextCode(text=inner)
        elif t == "u":
            node = RichTextUnderline(text=inner)
        elif t == "a":
            href = attrs.get("href") or ""
            node = RichTextUrl(text=inner, url=href) if href else inner
        else:                                   # tg-emoji: <tg-emoji emoji-id="..">🛡</tg-emoji>
            cid = attrs.get("emoji-id")
            alt = inner if isinstance(inner, str) else "•"
            node = RichTextCustomEmoji(custom_emoji_id=cid, alternative_text=alt) if cid else inner
        self.cur.append(node)

    def handle_data(self, data):
        if not data:
            return
        inside_code = any(s[0] == "code" for s in self.stack)
        if self.convert_emoji and not inside_code and not any(s[0] == "tg-emoji" for s in self.stack):
            self.cur.extend(_split_emoji(data))
        else:
            self.cur.append(data)


def _split_emoji(text: str) -> list:
    """Известные эмодзи → премиум-эмодзи (как в обычных сообщениях через emoji_inject), остальное — текст."""
    emap = _map()
    if not emap:
        return [text]
    out, buf, i, budget = [], [], 0, 12
    while i < len(text):
        hit = _emoji_at(text, i, emap) if budget > 0 else None
        if hit:
            frag, cid, n = hit
            if buf:
                out.append("".join(buf))
                buf = []
            out.append(RichTextCustomEmoji(custom_emoji_id=cid, alternative_text=frag))
            budget -= 1
            i += n
        else:
            buf.append(text[i])
            i += 1
    if buf:
        out.append("".join(buf))
    return out


def _simplify(parts: list):
    parts = [p for p in parts if p != ""]
    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else parts


def rich_text(html_text: str, convert_emoji: bool = True):
    """'<b>Привет</b> 🛡 мир' → RichText (строка, узлы или список узлов)."""
    p = _P(convert_emoji)
    p.feed(html_text or "")
    p.close()
    while p.stack:                              # незакрытые теги закрываем, чтобы не потерять текст
        p.handle_endtag(p.stack[-1][0])
    return _simplify(p.root)


# ---------- кнопки ----------
def _btn_text(text: str):
    """Ведущий эмодзи кнопки → премиум-эмодзи (как иконка слева на скриншотах)."""
    text = html.unescape(text)
    emap = _map()
    hit = _emoji_at(text, 0, emap) if emap and text else None
    if hit:
        frag, cid, n = hit
        rest = text[n:].lstrip()
        return [RichTextCustomEmoji(custom_emoji_id=cid, alternative_text=frag), " " + rest] if rest else \
            RichTextCustomEmoji(custom_emoji_id=cid, alternative_text=frag)
    return text


def _rich_button(b: Btn) -> RichMessageButton:
    kw = {"text": _btn_text(b.text), "style": b.style}
    if b.url:
        kw["url"] = b.url
    elif b.web_app:
        kw["web_app"] = WebAppInfo(url=b.web_app)
    else:
        kw["callback_data"] = b.cb or "noop"
    return RichMessageButton(**kw)


def _classic_button(b: Btn) -> InlineKeyboardButton:
    kw = {"text": b.text, "style": b.style if b.style in ("primary", "success", "danger") else None}
    if b.url:
        kw["url"] = b.url
    elif b.web_app:
        kw["web_app"] = WebAppInfo(url=b.web_app)
    else:
        kw["callback_data"] = b.cb or "noop"
    return InlineKeyboardButton(**kw)


# ---------- рендеры ----------
def _cell__rich_ui(text, header: bool = False):
    return RichBlockTableCell(align="left", valign="middle", text=text, is_header=True if header else None)


def to_rich(s: Screen) -> InputRichMessage:
    blocks: list = []
    if s.title:
        blocks.append(InputRichBlockSectionHeading(text=rich_text(s.title), size=3))
    for item in s.body:
        if item == "---":
            blocks.append(InputRichBlockDivider())
        elif isinstance(item, str):
            blocks.append(InputRichBlockParagraph(text=rich_text(item)))
        elif item[0] == "table":                 # строки «команда — описание»: одна колонка, команда кодом, описание курсивом
            cells = []
            for row in item[1]:
                if isinstance(row, (tuple, list)):
                    cmd, desc = row
                    cells.append([_cell__rich_ui([RichTextCode(text=cmd), " — ", RichTextItalic(text=rich_text(desc))])])
                else:
                    cells.append([_cell__rich_ui(rich_text(row))])
            blocks.append(InputRichBlockTable(cells=cells, is_bordered=True, is_compact=True))
        elif item[0] == "rows":                  # настоящая таблица из колонок
            _, header, rows = item
            cells = [[_cell__rich_ui(RichTextBold(text=h), True) for h in header]] + [[_cell__rich_ui(rich_text(str(c))) for c in r] for r in rows]
            blocks.append(InputRichBlockTable(cells=cells, is_bordered=True, is_striped=True))
    for row in s.rows:
        for i in range(0, len(row), MAX_ROW):
            blocks.append(InputRichBlockButtons(buttons=[_rich_button(b) for b in row[i:i + MAX_ROW]], align="center"))
    if s.footer:
        blocks.append(InputRichBlockFooter(text=rich_text(s.footer)))
    return InputRichMessage(blocks=blocks)


def _h(text: str) -> str:
    """Мини-HTML экрана → HTML rich-сообщения: известные эмодзи заменяются на <tg-emoji> (как в обычных сообщениях)."""
    return inject_html(text, _map()) if _map() else text


def _attr(v: str) -> str:
    return html.escape(v, quote=True)


def _button_html(b: Btn) -> str:
    label = html.escape(html.unescape(b.text))
    hit = _emoji_at(b.text, 0, _map()) if _map() and b.text else None
    if hit:
        frag, cid, n = hit
        rest = html.escape(html.unescape(b.text[n:].strip()))
        label = f'<tg-emoji emoji-id="{cid}">{html.escape(frag)}</tg-emoji>' + (f" {rest}" if rest else "")
    style = f' style="{b.style}"' if b.style else ""
    if b.url:
        return f'<tg-button type="url"{style} url="{_attr(b.url)}">{label}</tg-button>'
    if b.web_app:
        return f'<tg-button type="web_app"{style} url="{_attr(b.web_app)}">{label}</tg-button>'
    return f'<tg-button type="callback_data"{style} data="{_attr(b.cb or "noop")}">{label}</tg-button>'


LONG_PARA = 250          # абзац длиннее (без разметки) сворачивается в раскрывающуюся цитату


def _plain_len(text: str) -> int:
    return len(re.sub(r"<[^>]+>", "", text))


def _br(text: str) -> str:
    return text.replace("\n", "<br>")


def to_rich_html(s: Screen) -> InputRichMessage:
    """Тот же экран в HTML-форме rich-сообщения (<h3>, <p>, <blockquote>, <table>, <tg-button-row>). Эта форма идёт тем же путём,
    что и обычные сообщения с <tg-emoji>, поэтому премиум-эмодзи сохраняются и при правке на месте."""
    out: list[str] = []
    quoted: list[str] = []

    def flush() -> None:
        if quoted:
            out.append("<blockquote>" + "<br>".join(quoted) + "</blockquote>")
            quoted.clear()

    if s.title:
        out.append(f"<h3>{_h(s.title)}</h3>")
    for item in s.body:
        if item == "---":
            flush()
            out.append("<hr>")
        elif isinstance(item, str):
            if s.quote:
                quoted.append(_br(_h(item)))
            elif _plain_len(item) > LONG_PARA:
                out.append(f"<blockquote expandable>{_br(_h(item))}</blockquote>")
            else:
                out.append(f"<p>{_h(item)}</p>")
        elif item[0] == "table":
            flush()
            rows = []
            for row in item[1]:
                cell = f"<code>{html.escape(row[0])}</code> — <i>{_h(row[1])}</i>" if isinstance(row, (tuple, list)) else _h(row)
                rows.append(f"<tr><td>{cell}</td></tr>")
            out.append(f"<table bordered compact>{''.join(rows)}</table>")
        elif item[0] == "rows":
            flush()
            _, header, rows = item
            head = "".join(f"<th>{html.escape(h)}</th>" for h in header)
            body = "".join("<tr>" + "".join(f"<td>{_h(str(c))}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f"<table bordered striped><tr>{head}</tr>{body}</table>")
    flush()
    for row in s.rows:
        for i in range(0, len(row), MAX_ROW):
            out.append('<tg-button-row align="center">' + "".join(_button_html(b) for b in row[i:i + MAX_ROW]) + "</tg-button-row>")
    if s.footer:
        out.append(f"<footer>{_h(s.footer)}</footer>")
    return InputRichMessage(html="\n".join(out))


def _body_only(s: Screen) -> Screen:
    return Screen(s.title, s.body, [], s.footer)


def to_payload(s: Screen, html_form: bool | None = None) -> InputRichMessage:
    """Какую форму rich отправлять сейчас: HTML (по умолчанию) или блоки (если Telegram не принял HTML-разметку кнопок).
    В hybrid-режиме кнопок внутри нет — они идут обычной inline-клавиатурой (to_markup)."""
    if not PILLS:
        s = _body_only(s)
    return to_rich_html(s) if (_use_html if html_form is None else html_form) else to_rich(s)


def _rich_allowed(chat_id: int) -> bool:
    """rich — в личке всегда; в группах (id < 0) только если RICH_IN_GROUPS=1."""
    return ENABLED and (chat_id > 0 or RICH_IN_GROUPS)


def _emoji_lost(rich: InputRichMessage, res) -> bool:
    """Мы отправили премиум-эмодзи, а в ответе Telegram на правку их нет. Ответ без rich_message (True) — не знаем, не считаем потерей."""
    if res is None or isinstance(res, bool) or getattr(res, "rich_message", None) is None:
        return False
    sent = "<tg-emoji" in (rich.html or "") or _has_custom_emoji(rich)
    return sent and not _has_custom_emoji(res.rich_message)


def _forms() -> tuple:
    """Формы rich для попыток: HTML (сохраняет премиум-эмодзи), а при отказе — блоки только для ЭТОГО запроса.
    Глобально на блоки не переключаемся: одна ошибка (сеть, лишнее поле) раньше навсегда убивала премиум-эмодзи."""
    return (True, False) if _use_html else (False, True)


def to_markup(s: Screen):
    """Inline-клавиатура экрана в hybrid-режиме (в режиме таблеток — None: кнопки уже внутри сообщения)."""
    return None if PILLS else to_classic(s)[1]


def to_classic(s: Screen) -> tuple[str, InlineKeyboardMarkup | None]:
    """Тот же экран обычным сообщением: HTML-текст + inline-клавиатура."""
    brows = s.classic_rows if s.classic_rows is not None else s.rows
    if s.classic is not None:
        kb = InlineKeyboardMarkup(inline_keyboard=[[_classic_button(b) for b in row] for row in brows]) if brows else None
        return s.classic, kb
    lines: list[str] = []
    if s.title:
        lines.append(f"<b>{s.title}</b>")
    quoted: list[str] = []

    def flush() -> None:
        if quoted:
            lines.append("<blockquote>" + "\n".join(quoted) + "</blockquote>")
            quoted.clear()

    for item in s.body:
        if item == "---":
            flush()
            lines.append("")
        elif isinstance(item, str):
            if s.quote:
                quoted.append(item)
            elif _plain_len(item) > LONG_PARA:
                lines.append(f"<blockquote expandable>{item}</blockquote>")
            else:
                lines.append(item)
        elif item[0] == "table":
            flush()
            for row in item[1]:
                lines.append(f"<code>{html.escape(row[0])}</code> — <i>{row[1]}</i>" if isinstance(row, (tuple, list)) else row)
        elif item[0] == "rows":
            flush()
            _, header, rows = item
            lines.extend(" · ".join(str(c) for c in r) for r in rows)
    flush()
    if s.footer:
        lines.append(f"<i>{s.footer}</i>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[_classic_button(b) for b in row] for row in brows]) if brows else None
    return "\n".join(lines), kb


# ---------- отправка ----------
async def send__rich_ui(bot, chat_id: int, s: Screen, *, thread_id: int | None = None, reply_to: int | None = None):
    """Показывает экран: rich, а если не вышло — обычным сообщением. Возвращает отправленное сообщение."""
    global _off_until__rich_ui
    reply = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
    if _rich_allowed(chat_id) and time.time() >= _off_until__rich_ui:
        forms = _forms()
        for form in forms:
            try:
                return await bot.send_rich_message(chat_id=chat_id, rich_message=to_payload(s, form), reply_markup=to_markup(s),
                                                   message_thread_id=thread_id, reply_parameters=reply)
            except Exception as e:
                if form is not forms[-1]:                 # HTML-форма не принята — этот экран пробуем блоками
                    logging.warning("rich в HTML-форме не принят (%s) — пробую блоки", e)
                    continue
                logging.info("rich-экран не отправлен, шлю обычным сообщением: %s", e)
                _off_until__rich_ui = time.time() + OFF_FOR__rich_ui
                break
    text, kb = to_classic(s)
    return await bot.send_message(chat_id, text, reply_markup=kb, message_thread_id=thread_id, reply_parameters=reply,
                                  disable_web_page_preview=True)


async def show(cb, s: Screen) -> None:
    """Переход по кнопке — ВСЕГДА правим сообщение на месте, не удаляя и не присылая новое.
    1) rich-правка (editMessageText + rich_message); 2) обычная правка текста с inline-клавиатурой.
    Новое сообщение + удаление старого — только в крайнем случае: старое rich-сообщение, которое Telegram
    отказывается превращать в обычное, а rich-правка не проходит."""
    msg = cb.message
    if msg is None:
        return
    bot = cb.bot
    is_rich = getattr(msg, "rich_message", None) is not None
    if _rich_allowed(msg.chat.id) and (is_rich or time.time() >= _off_until__rich_ui):
        forms = _forms()
        for form in forms:
            try:
                rich = to_payload(s, form)
                # parse_mode / превью явно None: иначе aiogram подставляет их из DefaultBotProperties, а вместе
                # с rich_message Telegram такую правку отклоняет — и бот уходил в «новое сообщение + удаление старого»
                res = await bot.edit_message_text(chat_id=msg.chat.id, message_id=msg.message_id, rich_message=rich,
                                                  reply_markup=to_markup(s), parse_mode=None, link_preview_options=None,
                                                  disable_web_page_preview=None)
                if _emoji_lost(rich, res):                  # Telegram принял правку, но убрал премиум-эмодзи — повторов не делаем
                    logging.warning("правка rich потеряла премиум-эмодзи (чат %s); ответ Telegram: %s", msg.chat.id,
                                    str(getattr(res, "rich_message", res))[:200])
                return
            except TelegramBadRequest as e:
                if "not modified" in str(e).lower():
                    return
                if form is not forms[-1]:                   # HTML-форма не принята — этот экран пробуем блоками
                    logging.warning("rich-правка в HTML-форме не удалась (%s) — пробую блоки", e)
                    continue
                logging.warning("rich-правка не удалась (%s) — правлю обычным текстом", e)
                break
            except Exception as e:
                logging.warning("rich-правка не удалась (%s) — правлю обычным текстом", e)
                break
    text, kb = to_classic(s)
    try:
        await msg.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        return
    except Exception as e:
        if "not modified" in str(e).lower():
            return
        logging.warning("правка обычным текстом не удалась (%s) — шлю новый экран вместо старого", e)
    # крайний случай: старое сообщение нельзя ни так, ни так отредактировать
    try:
        thread = msg.message_thread_id if getattr(msg, "is_topic_message", False) else None
        sent = await send__rich_ui(bot, msg.chat.id, s, thread_id=thread)
        if sent is not None:
            await msg.delete()
    except Exception:
        pass


def kb__rich_ui(rows: list[list[Btn]]) -> InlineKeyboardMarkup:
    """Обычная inline-клавиатура из рядов Btn (для коротких сообщений-вопросов)."""
    return InlineKeyboardMarkup(inline_keyboard=[[_classic_button(b) for b in row] for row in rows])



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/runtime.py
# Состояние работающего бота: блок-лист, глобальные флаги, запрос на остановку/перезапуск.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
# Runtime — «общая доска» работающего бота. Лежит в dp["rt"] → в хендлере параметр `rt`.
#   rt.flags["ai"|"stt"|"nsfw"|"aimod"] — глобальные выключатели функций (панель владельца)
#   rt.maintenance — режим обслуживания;   rt.banned_users / banned_chats — блок-лист
#   rt.request_stop(restart=True) — штатная остановка/перезапуск (кнопки владельца)
# Новый глобальный флаг: добавьте в GLOBAL_DEFAULTS (db.py), в apply_globals и в self.flags.
class Runtime:
    def __init__(self) -> None:
        self.started_at = time.time()
        self.restart = False
        self.stop_requested = False
        self._event = asyncio.Event()
        self.banned_users: set[int] = set()
        self.banned_chats: set[int] = set()
        self.left_chats: set[int] = set()   # из каких забаненных чатов уже вышли
        self.flags = {"ai": True, "stt": True, "nsfw": True, "aimod": True}
        self.maintenance = False

    def flag(self, name: str) -> bool:
        return self.flags.get(name, True)

    def apply_globals(self, g: dict) -> None:
        self.flags = {"ai": bool(g["g_ai"]), "stt": bool(g["g_stt"]), "nsfw": bool(g["g_nsfw"]),
                      "aimod": bool(g.get("g_aimod", 1))}
        self.maintenance = bool(g["maintenance"])

    async def load(self, db: Database) -> None:
        self.banned_users, self.banned_chats = await db.load_bans()
        self.apply_globals(await db.get_global())

    def request_stop(self, restart: bool = False) -> None:
        self.restart = restart
        self.stop_requested = True
        self._event.set()

    async def wait_stop(self) -> None:
        await self._event.wait()



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/style.py
# Единый стиль текстов бота: заголовки, статусы, подписи. Все новые и переработанные сообщения собираются отсюда,
# чтобы бот выглядел одинаково: «эмодзи + жирный заголовок», пояснение курсивом, статусы ✅ / ⚠️ / ❌.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
# ВСЕ тексты бота лучше собирать этими функциями — единый вид. Пример:
#     style.head("🎲", "Игра", "подсказка") + "\n" + style.kv("Ставка", 50) + "\n" + style.ok("Готово")
def head(icon: str, title: str, hint: str | None = None) -> str:
    """🛡 <b>Заголовок</b> + (необязательно) короткая строка пояснения курсивом."""
    return f"{icon} <b>{title}</b>" + (f"\n<i>{hint}</i>" if hint else "")


def ok(text: str) -> str:
    return f"✅ {text}"


def warn(text: str) -> str:
    return f"⚠️ {text}"


def fail(text: str) -> str:
    return f"❌ {text}"


def kv(label: str, value) -> str:
    """Строка «подпись: значение» — подпись приглушена, значение жирным."""
    return f"{label}: <b>{html.escape(str(value))}</b>"


def bar__style(n: int, limit: int) -> str:
    """Шкала ▰▰▱ — прогресс/лимит."""
    limit = max(limit, 1)
    n = max(0, min(n, limit))
    return "▰" * n + "▱" * (limit - n)


def dur(seconds: int | None) -> str:
    """Срок по-русски: «2 дн.», «3 ч.», «15 мин.»."""
    if not seconds:
        return "навсегда"
    if seconds % 86400 == 0:
        return f"{seconds // 86400} дн."
    if seconds % 3600 == 0:
        return f"{seconds // 3600} ч."
    return f"{max(seconds // 60, 1)} мин."



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/targets.py
# Кто цель команды: явный @ник/id важнее ответа на сообщение (иначе «бан @спамер» в ответ на жалобу забанит жалобщика).
# ════════════════════════════════════════════════════════════════════════════════════════════════════
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{4,32}$")


def _username(user_id: int) -> str | None:
    u = USERNAMES.get(user_id)
    return u if u and _USERNAME_RE.match(u) else None


def mention__targets(user_id: int, name: str, maxlen: int | None = None) -> Html:
    """Кликабельное имя (для списков, статистики, карточек). Ссылка по id (tg://user?id) у людей со скрытым аккаунтом
    в настройках приватности Telegram превращается в простой текст — поэтому, если известен @ник, ссылаемся по нику:
    такая ссылка открывает профиль всегда. maxlen обрезает длинное имя."""
    name = name or f"id{user_id}"
    if maxlen and len(name) > maxlen:
        name = name[: maxlen - 1] + "…"
    u = _username(user_id)
    href = f"https://t.me/{u}" if u else f"tg://user?id={user_id}"
    return Html(f'<a href="{href}">{html.escape(name)}</a>')


def listed(user_id: int, name: str, maxlen: int | None = None) -> Html:
    """Для списков: кликабельное имя и рядом @ник, чтобы было видно, кто именно (одинаковые и эмодзи-имена
    не путаются): «Саша (@sasha_k)». Ника нет — только имя."""
    u = _username(user_id)
    return Html(str(mention__targets(user_id, name, maxlen)) + (f" (@{u})" if u else ""))


def ping(user_id: int, name: str) -> Html:
    """Позвать человека (общий сбор, капча): @ник присылает уведомление всегда; без ника — ссылка по id."""
    u = _username(user_id)
    if u:
        return Html(f"@{u}")
    return Html(f'<a href="tg://user?id={user_id}">{html.escape(name or f"id{user_id}")}</a>')


# ГЛАВНЫЙ помощник «кто цель команды». Используйте в любой команде с @ником / ответом на сообщение:
#     target = await resolve_user(db, token, real_reply(message))   # token — '@ник' | '12345' | None
#     if target is None: return          # цель не найдена — это просто фраза, а не команда
#     uid, name = target
async def resolve_user(db: Database, token: str | None, reply_message) -> tuple[int, str] | None:
    """(id, имя) или None, если цель определить не удалось. reply_message — уже очищенный от сервисных ответов."""
    if token:
        if token.startswith("@"):
            uid = await db.find_user(token)
        else:
            uid = int(token)
            await db.ensure_user(uid)                  # неизвестный id — запоминаем и работаем дальше
        if uid is None:
            return None
        return uid, (await db.user_name(uid)) or f"id{uid}"
    if reply_message is not None and reply_message.from_user is not None:
        u = reply_message.from_user
        await db.ensure_user(u.id, u.username, u.full_name)
        return u.id, u.full_name
    return None



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/toggles.py
# Включение и выключение целых групп команд в чате (настройки → «Команды»).
#
# Фильтр вешается на роутер целиком: `router.message.filter(Enabled("mod_on"))`. Если группа выключена, команды
# этой группы в чате молча игнорируются (полезно, когда модерирует другой бот). В личке фильтр ничего не запрещает;
# кнопки под уже отправленными сообщениями продолжают работать; настройки и веб-панель доступны всегда — включить обратно можно.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
# ключ настройки -> подпись (порядок = порядок в меню настроек)
# ВКЛЮЧАТЕЛИ ГРУПП КОМАНД. Новая группа, которую админ может выключить:
#   1) добавьте "ключ_on": "подпись" сюда;  2) заведите "ключ_on": 1 в DEFAULT_SETTINGS (db.py);
#   3) в вашем роутере: router.message.filter(Enabled("ключ_on"))
GROUPS = {
    "mod_on": "Модерация: бан, мут, кик, варн, чистка, откат, ранги, история, массовый кик",
    "svc_on": "Сервисы: калк, курс, крипто, вики, факт, маршрут, гороскоп",
    "cards_on": "Коллекционные карточки («карточка», «альбом», «обмен»)",
    "stats_on": "Статистика: «стата», топы",
    "rally_on": "«Общий сбор» (зовёт всех)",
    "quotes_on": "Цитатник",
    "mog_on": "Мог-баттлы",
    "giveaway_on": "Конкурсы (новые; идущие доиграют)",
    "suggest_on": "Предложка («+предложка текст»)",
    "img_on": "Генерация картинок («нарисуй …»)",
    "dl_on": "Скачивание видео/фото из соцсетей («скачай ссылка»)",
    "dl_auto": "…и сразу по ссылке на TikTok/Reels/Shorts без команды",
}


# Фильтр роутера: «группа команд включена в этом чате?» (в личке — всегда да)
class Enabled(Filter):
    def __init__(self, key: str):
        if key not in GROUPS:
            raise KeyError(key)
        self.key = key

    async def __call__(self, message: Message, db: Database) -> bool:
        if message.chat.type not in ("group", "supergroup"):
            return True
        return bool((await db.get_settings(message.chat.id))[self.key])


# То же самое для обычного кода: if await enabled(db, chat_id, "mod_on"): ...
async def enabled(db: Database, chat_id: int, key: str) -> bool:
    return bool((await db.get_settings(chat_id))[key])



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/ttl.py
# Очистка словарей-кулдаунов в памяти, чтобы они не росли бесконечно.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
def prune_stale(d: dict, max_age: float, now: float) -> int:
    """Удаляет записи, где значение — время (float/int) старше max_age. Остальные значения не трогает."""
    stale = [k for k, v in d.items() if isinstance(v, (int, float)) and not isinstance(v, bool) and now - v > max_age]
    for k in stale:
        d.pop(k, None)
    return len(stale)



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/updatequeue.py
# Надёжная очередь входящих обновлений (режим webhook).
#
# Проблема: раньше webhook отвечал Telegram «200» сразу и обрабатывал обновление в фоне. Если бот падал или перезапускался
# в этот момент, обновление терялось безвозвратно (Telegram считал его доставленным).
#
# Решение: обновление сначала записывается в БД (группой — один commit на пачку одновременно пришедших), только потом
# Telegram получает «200». Обрабатывают очередь N параллельных воркеров (UPDATE_WORKERS, по умолчанию 64): бот работает
# одинаково при любой нагрузке, а число одновременных обработчиков ограничено и настраивается. После сбоя необработанные
# свежие обновления выполняются заново; «ядовитое» обновление, на котором бот падает, пропускается после нескольких попыток.
# Повторная доставка того же update_id (Telegram ретраит при таймауте) отбрасывается.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
MAX_ATTEMPTS__updatequeue = 3        # сколько раз пробуем обновление, на котором бот падал
REPLAY_MAX_AGE = 300    # старше 5 минут после сбоя не повторяем: поздний бан/выдача монет хуже пропуска
DONE_FLUSH = 0.2        # как часто стираем обработанные из таблицы (окно возможного повтора при падении)
SEEN_LIMIT = 5000       # сколько последних update_id помним для защиты от дублей


class QueueFull(Exception):
    pass


class UpdateQueue:
    def __init__(self, db, dp, bot, workers: int = 64, maxsize: int = 10000):
        self.db, self.dp, self.bot = db, dp, bot
        self.workers = max(1, workers)
        self._q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._tasks: list[asyncio.Task] = []
        self._done: list[int] = []
        self._done_ids: set[int] = set()
        self._seen: OrderedDict[int, None] = OrderedDict()
        self._pending: dict[int, asyncio.Task] = {}
        self._inflight: set[int] = set()
        self._stopping = False
        self._seq = 0            # номер последней вставки
        self._covered = 0        # до какого номера вставки дошёл commit
        self._committing: asyncio.Future | None = None
        self._committing_seq = 0
        self.processed = 0
        self.failed = 0
        self.duplicates = 0
        self.replayed = 0
        self.busy = 0            # сколько воркеров заняты прямо сейчас
        self.peak_busy = 0

    # ---------- приём ----------
    def _remember(self, uid: int) -> bool:
        """False — этот update_id мы уже видели."""
        if uid in self._seen:
            return False
        self._seen[uid] = None
        if len(self._seen) > SEEN_LIMIT:
            self._seen.popitem(last=False)
        return True

    async def put(self, update: Update, raw: str) -> bool:
        """Записать и поставить в очередь. После возврата обновление гарантированно лежит в БД.
        False — дубль (уже принято раньше)."""
        if self._stopping:
            raise QueueFull
        uid = update.update_id
        if uid in self._pending:
            await asyncio.shield(self._pending[uid])
            self.duplicates += 1
            return False
        if uid in self._seen or uid in self._inflight or uid in self._done_ids:
            self.duplicates += 1
            return False
        # Резервируем место до первого await: параллельные запросы не переполнят очередь.
        if self._q.maxsize > 0 and self._q.qsize() + len(self._pending) >= self._q.maxsize:
            raise QueueFull
        task = asyncio.create_task(self._accept(update, raw))
        self._pending[uid] = task
        # При обрыве HTTP приём продолжается до commit и постановки в очередь.
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        return await asyncio.shield(task)

    async def _accept(self, update: Update, raw: str) -> bool:
        try:
            await self.db.conn.execute(
                "INSERT OR IGNORE INTO update_queue(update_id, ts, attempts, payload) VALUES(?,?,?,?)",
                (update.update_id, int(time.time()), 0, raw))
            self._seq += 1
            await self._sync(self._seq)
            self._remember(update.update_id)
            self._inflight.add(update.update_id)
            self._q.put_nowait(update)
            return True
        finally:
            self._pending.pop(update.update_id, None)

    async def _sync(self, seq: int) -> None:
        """Дождаться commit, начатого после нашей вставки (групповой commit: одна запись на пачку обновлений)."""
        while self._covered < seq:
            if self._committing is None:
                self._committing = asyncio.create_task(self._commit(self._seq))
            await asyncio.shield(self._committing)

    async def _commit(self, target: int) -> None:
        try:
            await self.db.conn.commit()
            self._covered = max(self._covered, target)
        finally:
            self._committing = None

    # ---------- обработка ----------
    async def _worker(self) -> None:
        while True:
            update = await self._q.get()
            self.busy += 1
            self.peak_busy = max(self.peak_busy, self.busy)
            try:
                await self.dp.feed_update(self.bot, update)
                self.processed += 1
            except Exception:
                self.failed += 1
                self._done.append(update.update_id)
                self._done_ids.add(update.update_id)
                self._inflight.discard(update.update_id)
                logging.exception("update %s failed", getattr(update, "update_id", "?"))
            else:
                self._done.append(update.update_id)
                self._done_ids.add(update.update_id)
                self._inflight.discard(update.update_id)
            finally:
                self.busy -= 1
                self._q.task_done()

    async def _cleaner(self) -> None:
        while True:
            await asyncio.sleep(DONE_FLUSH)
            await self.flush_done()

    async def flush_done(self) -> None:
        if not self._done:
            return
        ids, self._done = self._done, []
        try:
            # Один запрос на пачку сокращает число обращений к БД и переключений задач.
            for start in range(0, len(ids), 500):
                batch = ids[start:start + 500]
                placeholders = ",".join("?" for _ in batch)
                await self.db.conn.execute(f"DELETE FROM update_queue WHERE update_id IN ({placeholders})", tuple(batch))
            await self.db.conn.commit()
            self._done_ids.difference_update(ids)
        except asyncio.CancelledError:
            self._done = ids + self._done
            raise
        except Exception:
            self._done = ids + self._done
            logging.exception("update queue cleanup failed")

    async def start(self) -> None:
        if self._stopping:
            raise RuntimeError("update queue already stopped")
        if self._tasks:
            raise RuntimeError("update queue already started")
        self._tasks = [asyncio.create_task(self._worker()) for _ in range(self.workers)]
        try:
            await self._recover()
        except BaseException:
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()
            raise
        self._tasks.append(asyncio.create_task(self._cleaner()))

    async def _recover(self) -> None:
        """После сбоя: свежие необработанные обновления выполняем снова, «ядовитые» и старые выбрасываем."""
        now = int(time.time())
        cur = await self.db.conn.execute("SELECT update_id, ts, attempts, payload FROM update_queue ORDER BY update_id")
        rows = [dict(r) for r in await cur.fetchall()]
        for r in rows:
            if r["update_id"] in self._seen:
                continue                      # уже стоит в очереди этого запуска
            if r["attempts"] >= MAX_ATTEMPTS__updatequeue or now - r["ts"] > REPLAY_MAX_AGE:
                await self.db.conn.execute("DELETE FROM update_queue WHERE update_id=?", (r["update_id"],))
                logging.warning("update %s пропущен после сбоя (попыток %s, возраст %s с)",
                                r["update_id"], r["attempts"], now - r["ts"])
                continue
            await self.db.conn.execute("UPDATE update_queue SET attempts=attempts+1 WHERE update_id=?", (r["update_id"],))
            try:
                upd = Update.model_validate_json(r["payload"], context={"bot": self.bot})
            except Exception:
                await self.db.conn.execute("DELETE FROM update_queue WHERE update_id=?", (r["update_id"],))
                continue
            self._remember(upd.update_id)
            self._inflight.add(upd.update_id)
            await self.db.conn.commit()
            await self._q.put(upd)
            self.replayed += 1
        await self.db.conn.commit()
        if self.replayed:
            logging.info("очередь обновлений: повторяю %s необработанных после сбоя", self.replayed)

    async def stop(self, timeout: float = 15.0) -> None:
        """Штатная остановка: дорабатываем то, что принято, и стираем из таблицы."""
        self._stopping = True
        if self._pending:
            await asyncio.gather(*list(self._pending.values()), return_exceptions=True)
        try:
            await asyncio.wait_for(self._q.join(), timeout)
        except asyncio.TimeoutError:
            logging.warning("очередь обновлений: не успели обработать %s шт. за %s с — повторим при старте", self._q.qsize(), timeout)
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.flush_done()
        self._tasks.clear()

    def depth(self) -> int:
        return self._q.qsize()



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/ux.py
# Новые возможности Telegram Bot API одним местом: ephemeral-сообщения, реакции, теги участников, таблицы.
# Всё — «по возможности»: если Telegram или клиент чего-то не поддерживает, функции молча откатываются на обычное поведение.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
# Ephemeral-сообщения (Bot API 10.2) ВЫКЛЮЧЕНЫ: замечания и ответы идут обычным сообщением. Само оно не удаляется (NOTICE_TTL = 0).
# EPHEMERAL=1 в .env включает их обратно (в группе — видит только адресат).
EPHEMERAL = os.environ.get("EPHEMERAL", "0") == "1"
_eph_off_until = 0.0          # ephemeral недоступен (старый сервер/нет прав) — до этого момента не пробуем
_react_off_until = 0.0
NOTICE_TTL__ux = 0                # сколько живёт обычный (не ephemeral) ответ-замечание, сек
_bg__ux: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    t = asyncio.create_task(coro)
    _bg__ux.add(t)
    t.add_done_callback(_bg__ux.discard)


async def _delete_later(bot, chat_id: int, message_id: int, delay: float) -> None:
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


# ВЫБОР СПОСОБА ОТВЕТА:
#   ux.tell(message, text)  — ответ-замечание автору команды (ошибки, кулдауны, «нет прав»);
#   ux.tell_cb(cb, text)    — то же на нажатие inline-кнопки;
#   ux.react(bot, chat, msg_id, "👌") — молча поставить реакцию вместо текста;
#   message.answer / message.reply  — обычное публичное сообщение (результат, который видят все).
async def tell(message, text: str, *, reply_markup=None, ttl: int = NOTICE_TTL__ux):
    """Ответ, который нужен только автору команды (кулдауны, «нет прав», баланс). В группе — ephemeral-сообщение
    (видит один человек, Bot API 10.2); если не вышло — обычный ответ, который удалится сам через ttl секунд."""
    global _eph_off_until
    user = message.from_user
    if EPHEMERAL and message.chat.type in ("group", "supergroup") and user is not None and time.time() >= _eph_off_until:
        try:
            await message.bot.send_message(
                message.chat.id, text, reply_markup=reply_markup, message_thread_id=message.message_thread_id
                if getattr(message, "is_topic_message", False) else None,
                ephemeral_message_parameters=EphemeralMessageParameters(receiver_user_id=user.id))
            return None
        except Exception as e:
            logging.info("ephemeral недоступен: %s", e)
            _eph_off_until = time.time() + 600
    sent = await message.reply(text, reply_markup=reply_markup)
    if message.chat.type in ("group", "supergroup") and ttl:
        _spawn(_delete_later(message.bot, sent.chat.id, sent.message_id, ttl))
    return sent


async def tell_cb(cb, text: str, *, reply_markup=None) -> None:
    """Ответ на нажатие кнопки, который нужен только нажавшему: ephemeral-сообщение (Bot API 10.2, связано с callback_query_id).
    Не вышло — всплывающее окно с тем же текстом без разметки (до 200 символов)."""
    global _eph_off_until
    msg = getattr(cb, "message", None)
    if EPHEMERAL and msg is not None and msg.chat.type in ("group", "supergroup") and time.time() >= _eph_off_until:
        try:
            await cb.bot.send_message(
                msg.chat.id, text, reply_markup=reply_markup,
                ephemeral_message_parameters=EphemeralMessageParameters(callback_query_id=cb.id))
            return
        except Exception as e:
            logging.info("ephemeral (callback) недоступен: %s", e)
            _eph_off_until = time.time() + 600
    plain = re.sub(r"<[^>]+>", "", text)
    try:
        await cb.answer(html.unescape(plain)[:200], show_alert=True)
    except Exception:
        pass


async def react(bot, chat_id: int, message_id: int, emoji: str = "👍") -> bool:
    """Поставить реакцию вместо лишнего текстового ответа (Bot API 7.0+; в чате реакции должны быть разрешены)."""
    global _react_off_until
    if time.time() < _react_off_until:
        return False
    try:
        await bot.set_message_reaction(chat_id, message_id, reaction=[ReactionTypeEmoji(emoji=emoji)])
        return True
    except Exception as e:
        text = str(e).lower()
        if "reaction" in text and ("invalid" in text or "not allowed" in text or "can't" in text):
            return False                                  # в этом чате такой эмодзи запрещён — не повод отключать всё
        _react_off_until = time.time() + 300
        return False


def rank_tag(rank: int) -> str | None:
    """Тег участника для ранга бота (до 16 символов); ранга нет — убрать тег."""
    return {1: "модератор", 2: "мл. админ", 3: "админ", 4: "ст. админ"}.get(rank) if rank > 0 else None


async def sync_tag(bot, chat_id: int, user_id: int, rank: int) -> bool:
    """Показывать ранг бота тегом рядом с ником (Bot API 9.5, нужно право can_manage_tags). Ошибки не критичны."""
    try:
        await bot.set_chat_member_tag(chat_id, user_id, tag=rank_tag(rank))
        return True
    except Exception as e:
        logging.info("тег участника не выставлен: %s", e)
        return False


async def table_or_text(message, title: str, header: list[str], rows: list[list], fallback_html: str, *,
                        aligns: list[str] | None = None, reply_markup=None, reply: bool = True) -> None:
    """Список в виде настоящей таблицы; если Telegram её не принял — тот же список обычным текстом."""
    pass  # (импорт убран: всё в одном модуле)
    if rows:
        sent = await send_table(
            message.bot, message.chat.id, title, header, rows, aligns=aligns, reply_markup=reply_markup,
            reply_to=message.message_id if reply else None,
            thread_id=message.message_thread_id if getattr(message, "is_topic_message", False) else None)
        if sent is not None:
            return
    await message.reply(fallback_html, reply_markup=reply_markup, disable_web_page_preview=True)



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/weather.py
# Погода через wttr.in (без ключа).
# ════════════════════════════════════════════════════════════════════════════════════════════════════
_CITY_RE = re.compile(r"^[\w .,'-]{2,40}$", re.UNICODE)
FORMAT = "%l: %c %t (ощущается %f), ветер %w, влажность %h"


def valid_city(city: str) -> bool:
    return bool(_CITY_RE.match(city.strip()))


async def fetch_weather(session: aiohttp.ClientSession, city: str, base: str = "https://wttr.in") -> str | None:
    city = city.strip()
    if not valid_city(city):
        return None
    try:
        async with session.get(f"{base}/{quote__i1(city)}", params={"format": FORMAT, "lang": "ru"},
                               timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status != 200:
                return None
            text = (await r.text()).strip()
    except (aiohttp.ClientError, TimeoutError):
        return None
    if not text or "Unknown location" in text or len(text) > 300:
        return None
    return text



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/webhook.py
# Режим webhook: приём обновлений от Telegram по HTTPS и наблюдение за тем, что доставка не сломалась.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
ERROR_WINDOW = 600   # ошибки доставки старше 10 минут не считаем


def webhook_target(webhook_url: str, webapp_url: str) -> str:
    """Куда Telegram шлёт обновления: WEBHOOK_URL (порт 88/443/8443 — другие Telegram не принимает), иначе WEBAPP_URL."""
    base = (webhook_url or webapp_url or "").rstrip("/")
    return f"{base}/webhook" if base else ""


def register_webhook(app, dp, bot, secret: str, handle_in_background: bool = True, queue=None) -> None:
    """Маршрут POST /webhook с проверкой секретного заголовка X-Telegram-Bot-Api-Secret-Token.
    С queue (UpdateQueue) обновление сначала сохраняется в БД и только потом подтверждается Telegram."""
    if not secret:
        raise ValueError("webhook secret must not be empty")
    if queue is not None:
        async def handler(request: web.Request) -> web.Response:
            got = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not hmac.compare_digest(got.encode(), secret.encode()):
                return web.Response(status=401, text="Unauthorized")
            try:
                raw = await request.text()
                update = Update.model_validate_json(raw, context={"bot": bot})
            except Exception:
                return web.Response(status=400, text="Bad update")
            try:
                await queue.put(update, raw)
            except QueueFull:
                return web.Response(status=503, text="Busy")     # Telegram повторит позже
            except Exception:
                logging.exception("не удалось сохранить обновление")
                return web.Response(status=503, text="Retry")
            return web.json_response({})

        app.router.add_post("/webhook", handler)
        setup_application(app, dp, bot=bot)
        return
    SimpleRequestHandler(dp, bot, secret_token=secret, handle_in_background=handle_in_background).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)


async def check_webhook_once(bot, alerter, expected_url: str, now: int | None = None) -> bool:
    """True — всё в порядке. Иначе сообщает владельцу: вебхук слетел или Telegram недавно не смог доставить обновления."""
    now = int(time.time()) if now is None else now
    try:
        wi = await bot.get_webhook_info()
    except Exception:
        logging.warning("webhook watch: getWebhookInfo не удался")
        return True   # проблема связи с Telegram — не повод тревожить владельца
    if wi.url != expected_url:
        await alerter.alert(f"⚠️ Webhook не установлен или адрес изменён (ожидался {expected_url}): бот сейчас не получает сообщения.")
        return False
    recent_error = wi.last_error_date and now - int(wi.last_error_date) < ERROR_WINDOW
    if recent_error and wi.pending_update_count > 0:
        await alerter.alert(f"⚠️ Telegram не может доставить обновления на webhook: {wi.last_error_message} "
                            f"(в очереди {wi.pending_update_count}). Проверьте Caddy и сертификат.")
        return False
    return True


async def webhook_watch(bot, alerter, expected_url: str, interval: int = 300, first_delay: int = 60) -> None:
    await asyncio.sleep(first_delay)
    while True:
        await check_webhook_once(bot, alerter, expected_url)
        await asyncio.sleep(interval)



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/wipe.py
# «вайп @ник» — удалить сообщения участника за последние 48 часов.
#
# Bot API не отдаёт историю чата, поэтому бот помнит номера свежих сообщений сам (только в памяти, на время работы):
# последние сообщения каждого участника за 48 часов. После перезапуска то, что было раньше, вайп не увидит.
# Telegram позволяет удалять сообщения не старше 48 часов.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
WINDOW__wipe = 48 * 3600 - 600       # запас на часовые пояса и задержки
PER_USER = 150
MAX_KEYS = 60000

_seen: dict[tuple[int, int], deque] = {}


def remember__wipe(chat_id: int, user_id: int, message_id: int, ts: int) -> None:
    key = (chat_id, user_id)
    q = _seen.get(key)
    if q is None:
        if len(_seen) >= MAX_KEYS:
            prune(ts)
            if len(_seen) >= MAX_KEYS:
                _seen.clear()
        q = _seen[key] = deque(maxlen=PER_USER)
    q.append((message_id, ts))


def prune(now: int) -> None:
    for key in [k for k, q in _seen.items() if not q or now - q[-1][1] > WINDOW__wipe]:
        _seen.pop(key, None)


def take__wipe(chat_id: int, user_id: int, now: int) -> list[int]:
    q = _seen.pop((chat_id, user_id), None)
    return [m for m, ts in (q or ()) if now - ts < WINDOW__wipe]


async def wipe(bot, chat_id: int, user_id: int, now: int) -> int:
    ids = take__wipe(chat_id, user_id, now)
    done = 0
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        try:
            await bot.delete_messages(chat_id, batch)
            done += len(batch)
        except Exception:
            logging.warning("вайп: не удалось удалить пачку сообщений")
    return done
