"""Данные: база (SQLite/PostgreSQL), бэкапы, журнал модерации.

Файл собран из нескольких исходных модулей; каждый начинается с шапки «МОДУЛЬ: bot/<путь>.py».
Ищите по слову «МОДУЛЬ:» (Ctrl+F). Пути вида handlers/xxx.py в комментариях — это такие разделы.
"""
from __future__ import annotations

import aiosqlite
import asyncio
import asyncpg
import html
import json
import logging
import os
import re
import secrets
import sqlite3
import stat
import tempfile
import time
from aiogram.exceptions import TelegramRetryAfter
from collections import deque
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import unquote, urlsplit




# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/audit.py
# Журнал действий в отдельный чат/канал: очередь с ограничением скорости, повтор при flood control.
# Сбой журнала никогда не ломает модерацию: ошибки только пишутся в лог.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
ICONS__audit = {"бан": "🔨", "разбан": "✅", "мут": "🔇", "размут": "🔊", "кик": "👢", "варн": "⚠️",
         "снять варн": "↩️", "удаление": "🗑", "ранг": "🎖", "массовый кик": "🧹", "жалоба": "📣",
         "настройка": "⚙️", "антирейд": "🚨"}
MAX_TEXT__audit = 3500


def _dur__audit(sec: int | None) -> str:
    if not sec:
        return ""
    if sec % 86400 == 0:
        return f" на {sec // 86400} дн."
    if sec % 3600 == 0:
        return f" на {sec // 3600} ч."
    return f" на {max(sec // 60, 1)} мин."


def _escape_clip(value: str, budget: int) -> str:
    escaped = html.escape(value)
    if len(escaped) <= budget:
        return escaped
    out, used = [], 0
    for ch in value:
        fragment = html.escape(ch)
        if used + len(fragment) > budget - 1:
            break
        out.append(fragment)
        used += len(fragment)
    return "".join(out) + "…"


def format_event(chat_title: str, actor: str, target: str | None, action: str, duration: int | None,
                 reason: str, ts: int) -> str:
    lines = [f"{ICONS__audit.get(action, '📝')} <b>{_escape_clip(action, 160)}</b>{_dur__audit(duration)}",
             f"Чат: {_escape_clip(chat_title, 768)}", f"Кто: {_escape_clip(actor, 768)}"]
    if target:
        lines.append(f"Кого: {_escape_clip(target, 768)}")
    timestamp = "🕒 " + time.strftime("%d.%m.%Y %H:%M:%S", time.gmtime(ts)) + " UTC"
    if reason:
        budget = MAX_TEXT__audit - len("\n".join(lines)) - len(timestamp) - len("Причина: ") - 2
        lines.append("Причина: " + _escape_clip(reason, max(1, budget)))
    lines.append(timestamp)
    return "\n".join(lines)


class Auditor:
    def __init__(self, bot, db, interval: float = 1.1, max_queue: int = 500,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.bot, self.db, self.interval, self.max_queue, self._sleep = bot, db, interval, max_queue, sleep
        self._q: deque[tuple[int, str]] = deque()
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._pending: set[asyncio.Task] = set()

    # ---- приём событий ----
    def action_fire_and_forget(self, *args) -> None:
        """Вызывается из Database.log_action: ничего не ждём и ничего не бросаем."""
        try:
            t = asyncio.get_running_loop().create_task(self.record_action(*args))
        except RuntimeError:
            return
        self._pending.add(t)
        t.add_done_callback(self._pending.discard)

    async def _name(self, uid: int | None) -> str:
        if not uid:
            return "—"
        name = await self.db.user_name(uid)
        return f"{name} ({uid})" if name else f"id{uid}"

    async def record_action(self, chat_id: int, actor_id: int, target_id: int | None, action: str,
                            reason: str, ts: int, duration: int | None) -> None:
        try:
            dest = (await self.db.get_settings(chat_id)).get("log_chat_id", 0)
            if not dest:
                return
            chat = await self.db.get_chat(chat_id)
            text = format_event((chat or {}).get("title") or str(chat_id), await self._name(actor_id),
                                await self._name(target_id) if target_id else None, action, duration, reason or "", ts)
            await self.push(dest, text)
        except Exception:
            logging.exception("audit: не смог подготовить запись")

    async def push(self, dest: int, text: str) -> None:
        if len(self._q) >= self.max_queue:
            self._q.popleft()   # переполнение: теряем самое старое
        self._q.append((dest, text))
        self._wake.set()

    # ---- отправка ----
    async def _send_one(self, dest: int, text: str) -> None:
        for _ in range(3):
            try:
                await self.bot.send_message(dest, text, disable_web_page_preview=True)
                return
            except TelegramRetryAfter as e:
                await self._sleep(min(e.retry_after, 60))
            except Exception as e:
                logging.warning("audit: отправка в %s не удалась: %s", dest, type(e).__name__)
                return

    async def drain(self) -> None:
        """Отправить всё из очереди (используется воркером и тестами)."""
        if self._pending:
            await asyncio.shield(asyncio.gather(*list(self._pending), return_exceptions=True))
        first = True
        while self._q:
            dest, text = self._q.popleft()
            try:
                if not first:
                    await self._sleep(self.interval)
                first = False
                await self._send_one(dest, text)
            except asyncio.CancelledError:
                self._q.appendleft((dest, text))
                raise

    async def _worker(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            try:
                await self.drain()
            except Exception:
                logging.exception("audit worker")
            await self._sleep(self.interval)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._worker())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None


    async def aclose(self, timeout: float = 5.0) -> None:
        worker = self._task
        self.stop()
        if worker is not None:
            await asyncio.gather(worker, return_exceptions=True)
        try:
            await asyncio.wait_for(self.drain(), timeout)
        except asyncio.TimeoutError:
            logging.warning("audit: shutdown deadline reached; %s events left", len(self._q))
        finally:
            pending = list(self._pending)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            self._pending.difference_update(pending)
            self._q.clear()



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/backup.py
# Автобэкап БД: копия через sqlite backup API, проверка целостности, ротация, оповещение при ошибке.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
PREFIX = "bot-backup-"


class BackupError(Exception):
    pass


async def _check_pg_dump(path: str) -> None:
    proc = await asyncio.create_subprocess_exec("pg_restore", "--list", path,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        _, error = await asyncio.wait_for(proc.communicate(), 60)
    except BaseException:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
        raise
    if proc.returncode != 0:
        raise BackupError("дамп PostgreSQL не читается: " + error.decode(errors="replace")[:150])


def _check_integrity(path: str) -> None:
    try:
        conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        try:
            res = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as e:
        raise BackupError(f"копия не открывается: {e}") from e
    if not res or res[0] != "ok":
        raise BackupError(f"проверка целостности: {res[0] if res else 'нет ответа'}")


async def make_backup(db, directory: str, now: int | None = None) -> str:
    os.makedirs(directory, mode=0o700, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now if now is not None else time.time()))
    pg = getattr(db, "backend", "sqlite") == "pg"
    path = os.path.join(directory, f"{PREFIX}{ts}-{time.time_ns():020d}-{secrets.token_hex(4)}.{'dump' if pg else 'db'}")
    descriptor, partial = tempfile.mkstemp(prefix=".backup-", suffix=".partial", dir=directory)
    os.close(descriptor)
    try:
        await db.backup_to(partial)
        if pg:
            await _check_pg_dump(partial)
        else:
            await asyncio.to_thread(_check_integrity, partial)
        os.replace(partial, path)  # only validated backups become visible to rotation
    except BaseException:
        if os.path.exists(partial):
            os.remove(partial)
        raise
    return path


def rotate(directory: str, keep: int) -> int:
    pattern = re.compile(r"bot-backup-([0-9]{8}-[0-9]{6})(?:-([0-9]+)-[0-9a-f]+)?\.(?:db|dump)")
    files = []
    with os.scandir(directory) as entries:
        for entry in entries:
            match = pattern.fullmatch(entry.name)
            if match and entry.is_file(follow_symlinks=False):
                files.append(((match[1], int(match[2] or 0)), entry.name))
    files.sort()
    old = files[:-keep] if keep > 0 else files
    for _, name in old:
        os.remove(os.path.join(directory, name))
    return len(old)


async def backup_once(db, directory: str, keep: int, notify: Callable[[str], Awaitable[None]],
                      now: int | None = None) -> bool:
    try:
        await make_backup(db, directory, now=now)
        rotate(directory, keep)
        return True
    except Exception as e:
        logging.exception("backup failed")
        try:
            await notify(f"⚠️ Автоматический бэкап базы не удался: {type(e).__name__}: {e}")
        except Exception:
            logging.exception("backup notify failed")
        return False


async def backup_loop(db, directory: str, keep: int, notify: Callable[[str], Awaitable[None]],
                      interval: int = 86400, first_delay: int = 300) -> None:
    await asyncio.sleep(first_delay)
    while True:
        await backup_once(db, directory, keep, notify)
        await asyncio.sleep(interval)



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/db.py
# ════════════════════════════════════════════════════════════════════════════════════════════════════
# user_id -> @ник без «@» (None — ника нет). Заполняется при каждой встрече с пользователем и при чтении имени;
# нужен упоминаниям: ссылка по нику работает всегда, а ссылка по id — не у всех (см. bot.targets.mention).
USERNAMES: dict[int, str | None] = {}

# ===== КОНСТАНТЫ БД / ЭКОНОМИКИ (меняйте здесь) =====
HOUR = 3600
DAY__db = 86400
ROLLUP_DAYS = 90        # статистика старше N дней сворачивается из почасовой в посуточную
START_BALANCE = 1000    # стартовые монеты нового участника чата
BONUS_AMOUNT = 500      # ежедневный «бонус»

GLOBAL_DEFAULTS = {"g_ai": 1, "g_stt": 1, "g_nsfw": 1, "g_aimod": 1, "maintenance": 0}

CHILD_COLS = [('mood', 'INTEGER DEFAULT 70'), ('mood_at', 'INTEGER DEFAULT 0'), ('fed_at', 'INTEGER DEFAULT 0'), ('play_at', 'INTEGER DEFAULT 0'), ('study_at', 'INTEGER DEFAULT 0'), ('sport_at', 'INTEGER DEFAULT 0'), ('s_int', 'INTEGER DEFAULT 0'), ('s_cre', 'INTEGER DEFAULT 0'), ('s_spo', 'INTEGER DEFAULT 0'), ('grown', 'INTEGER DEFAULT 0'), ('job', "TEXT DEFAULT ''")]
# НАСТРОЙКИ ЧАТА ПО УМОЛЧАНИЮ. Новая настройка: добавьте "ключ": значение сюда (int → число, str → текст),
# затем покажите её в handlers/settings.py (PAGES). Читать: (await db.get_settings(chat_id))["ключ"].
DEFAULT_SETTINGS = {
    "captcha_on": 1,
    "captcha_timeout": 180,
    "captcha_recheck": "off",     # повторная капча: off | susp (аккаунты без @ника) | all
    "warn_limit": 3, "warn_ttl_days": 30, "log_chat_id": 0, "report_on": 1, "welcome_on": 1,
    # ИИ-модерация (по умолчанию выключена: текст уходит во внешний сервис)
    "ai_mod": "off", "ai_mod_action": "delete", "ai_mod_conf": 75,
    "games_on": 1, "mafia_on": 1,
    # группы команд (настройки → «Команды»): 0 — команды группы в чате молча игнорируются
    "mod_on": 1, "svc_on": 1, "cards_on": 1, "stats_on": 1, "rally_on": 1, "quotes_on": 1, "mog_on": 1, "giveaway_on": 1, "suggest_on": 1, "img_on": 1, "dl_on": 1, "dl_auto": 1,
    "fun_on": 1, "rp_on": 1, "rep_on": 1, "pair_intim": 0, "mod_gif": 1, "rp_gifs": 1, "rp_adult": 0,
    "tz": "Europe/Moscow",
    "lang": "ru",                 # язык интерфейса чата: ru | en
    # антиспам
    "spam_on": 0, "spam_flood_n": 5, "spam_flood_sec": 10, "spam_dup": 1, "links_mode": "newbies", "filter_action": "delete",
    "phish_on": 0, "phish_action": "delete",
    "spam_mentions": 5, "spam_forward": 0, "spam_action": "delete", "spam_ai": 0,
    # антирейд
    "dupe_on": 0,
    "cas_mode": "off",            # проверка по базе спамеров CAS: off | warn | ban
    "guest_mode": "check",        # гостевые боты: off | check (проверять содержимое) | allowlist (только разрешённые) | block
    "guard_default": "queue",     # если бот — страж заявок, а капча выключена: queue (админам) | approve

    # удаление по типу сообщения (bot/middlewares/rules.py)
    "del_caps": 0, "del_sticker": 0, "del_gif": 0, "del_voice": 0, "del_note": 0, "del_forward": 0, "del_mention": 0,
    "del_emoji": 0, "del_story": 0, "del_dice": 0, "del_format": 0, "del_via": 0, "del_poll": 0,
    "del_service": 0, "del_cmds": 0, "unpin_channel": 0, "leave_wipe": 0,
    # фейс-контроль новичков
    "fc_on": 0, "fc_photo": 0, "fc_username": 0, "fc_age": 0, "fc_premium": 0, "fc_action": "kick",
    # наказание за быстрый выход, ночной режим
    "leave_on": 0, "leave_sec": 120, "leave_hours": 24,
    "night_on": 0, "night_from": 23, "night_to": 7, "night_closed": 0,
    # сроки по умолчанию и действие при лимите варнов
    "mute_secs": 0, "ban_secs": 0, "warn_action": "mute", "warn_secs": 86400,
    "raid_on": 0, "raid_n": 5, "raid_sec": 60, "raid_action": "captcha", "raid_minutes": 10,
    # 18+
    "nsfw_on": 0, "nsfw_threshold": 55, "nsfw_action": "delete", "nsfw_ai": 0,
    # расшифровка и ИИ
    "transcribe_on": 0, "transcribe_max": 180, "ai_on": 1,
    # «живое» общение ИИ: off | reply (отвечает, когда обращаются) | live (ещё и сам вклинивается в разговор)
    "ai_chat": "off",
    "ai_chat_style": "casual",   # casual — по-свойски, с матом; polite — вежливо
    # активность (bot/activity.py): норма сообщений в неделю с автокиком, подъём молчунов, реплики Нори в тихом чате
    "quota_on": 0, "quota_min": 250, "quota_warn": 1, "quota_since": 0,
    "wake_on": 0, "idle_on": 0, "idle_hours": 6,
}

def _remember_username(user_id: int, username: str | None) -> None:
    if len(USERNAMES) > 200000:
        USERNAMES.clear()
    USERNAMES[user_id] = (username or "").lstrip("@") or None


SCHEMA = """
CREATE TABLE IF NOT EXISTS msg_hourly(
    chat_id INTEGER, user_id INTEGER, hour_ts INTEGER, n INTEGER,
    PRIMARY KEY(chat_id, user_id, hour_ts));
CREATE TABLE IF NOT EXISTS msg_daily(
    chat_id INTEGER, user_id INTEGER, day_ts INTEGER, n INTEGER,
    PRIMARY KEY(chat_id, user_id, day_ts));
CREATE TABLE IF NOT EXISTS warns(
    chat_id INTEGER, user_id INTEGER, n INTEGER,
    PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS mod_log(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, actor_id INTEGER,
    target_id INTEGER, action TEXT, reason TEXT, ts INTEGER, duration INTEGER);
CREATE TABLE IF NOT EXISTS warn_events(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, user_id INTEGER, ts INTEGER,
    expires_at INTEGER, reason TEXT, actor INTEGER);
CREATE INDEX IF NOT EXISTS warn_events_user ON warn_events(chat_id, user_id, expires_at);
CREATE TABLE IF NOT EXISTS reports(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, reporter INTEGER, target INTEGER, message_id INTEGER,
    text TEXT, reason TEXT, status TEXT DEFAULT 'open', ts INTEGER, handled_by INTEGER);
CREATE INDEX IF NOT EXISTS reports_msg ON reports(chat_id, message_id);
CREATE TABLE IF NOT EXISTS filters(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, kind TEXT, pattern TEXT, action TEXT,
    created_by INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS filters_chat ON filters(chat_id);
CREATE TABLE IF NOT EXISTS triggers(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, event TEXT, action TEXT, secs INTEGER DEFAULT 0,
    reason TEXT DEFAULT '', created_by INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS triggers_chat ON triggers(chat_id, event);
CREATE TABLE IF NOT EXISTS trusted(
    chat_id INTEGER, user_id INTEGER, added_by INTEGER, ts INTEGER, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS sticker_block(
    chat_id INTEGER, kind TEXT, key TEXT, PRIMARY KEY(chat_id, kind, key));
CREATE TABLE IF NOT EXISTS faq(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, keyword TEXT, answer TEXT, created_by INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS faq_chat ON faq(chat_id);
CREATE TABLE IF NOT EXISTS periodic(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, every INTEGER, text TEXT, last_sent INTEGER DEFAULT 0,
    created_by INTEGER);
CREATE INDEX IF NOT EXISTS periodic_chat ON periodic(chat_id);
CREATE TABLE IF NOT EXISTS grid_chats(
    chat_id INTEGER PRIMARY KEY, owner_id INTEGER, ts INTEGER);
CREATE TABLE IF NOT EXISTS board_games(
    id TEXT PRIMARY KEY, chat_id INTEGER, data TEXT, expires_at INTEGER);
CREATE INDEX IF NOT EXISTS board_games_chat ON board_games(chat_id);
CREATE TABLE IF NOT EXISTS cards_owned(
    user_id INTEGER, card_id INTEGER, n INTEGER DEFAULT 1, PRIMARY KEY(user_id, card_id));
CREATE TABLE IF NOT EXISTS cards_cooldown(
    user_id INTEGER PRIMARY KEY, last_find INTEGER);
CREATE TABLE IF NOT EXISTS link_allow(
    chat_id INTEGER, domain TEXT, created_by INTEGER, PRIMARY KEY(chat_id, domain));
CREATE TABLE IF NOT EXISTS aimod_events(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, user_id INTEGER, message_id INTEGER, category TEXT,
    confidence INTEGER, action TEXT, text TEXT, status TEXT DEFAULT 'open', ts INTEGER, handled_by INTEGER);
CREATE TABLE IF NOT EXISTS giveaways(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, creator INTEGER, step TEXT, text TEXT, photo TEXT,
    winners INTEGER DEFAULT 1, publish_at INTEGER, ends_at INTEGER, status TEXT DEFAULT 'draft', message_id INTEGER,
    created_at INTEGER, result TEXT, shown_count INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS giveaways_status ON giveaways(status);
CREATE TABLE IF NOT EXISTS giveaway_entries(
    gid INTEGER, user_id INTEGER, ts INTEGER, PRIMARY KEY(gid, user_id));
CREATE TABLE IF NOT EXISTS giveaway_checks(
    gid INTEGER, user_id INTEGER, answer TEXT, attempts INTEGER DEFAULT 0, expires_at INTEGER, PRIMARY KEY(gid, user_id));
CREATE TABLE IF NOT EXISTS quotes(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, author_id INTEGER, author_name TEXT, text TEXT, ts INTEGER,
    added_by INTEGER, added_at INTEGER, message_id INTEGER, card TEXT);
CREATE INDEX IF NOT EXISTS quotes_chat ON quotes(chat_id, author_id);
CREATE TABLE IF NOT EXISTS mog_ratings(
    fp TEXT PRIMARY KEY, avatar INTEGER, name INTEGER, meaning INTEGER, ts INTEGER);
CREATE TABLE IF NOT EXISTS mog_results(
    chat_id INTEGER, winner INTEGER, loser INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS mog_results_chat ON mog_results(chat_id, winner);
CREATE TABLE IF NOT EXISTS suggestions(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, user_id INTEGER, user_name TEXT, text TEXT, ts INTEGER,
    status TEXT DEFAULT 'new', handled_by INTEGER, handled_at INTEGER);
CREATE INDEX IF NOT EXISTS suggestions_chat ON suggestions(chat_id, status);
CREATE TABLE IF NOT EXISTS premium(
    user_id INTEGER PRIMARY KEY, until INTEGER, since INTEGER, payments INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS payments(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, charge_id TEXT, amount INTEGER, ts INTEGER,
    recurring INTEGER DEFAULT 0, refunded INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS payments_charge ON payments(charge_id,id);
CREATE TABLE IF NOT EXISTS payment_receipts(
    charge_id TEXT PRIMARY KEY, ts INTEGER);
CREATE TABLE IF NOT EXISTS payment_effects(
    charge_id TEXT PRIMARY KEY, kind TEXT, target_id INTEGER, previous_until INTEGER, until INTEGER);
CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS user_prefs(
    user_id INTEGER PRIMARY KEY, ai_model TEXT);
CREATE TABLE IF NOT EXISTS promo_codes(
    code TEXT PRIMARY KEY, days INTEGER, uses_left INTEGER, created_by INTEGER, created_at INTEGER);
CREATE TABLE IF NOT EXISTS promo_uses(
    code TEXT, user_id INTEGER, ts INTEGER, PRIMARY KEY(code, user_id));
CREATE TABLE IF NOT EXISTS settings(
    chat_id INTEGER, key TEXT, value TEXT, PRIMARY KEY(chat_id, key));
CREATE TABLE IF NOT EXISTS wallets(
    chat_id INTEGER, user_id INTEGER, balance INTEGER, last_bonus_day INTEGER DEFAULT -1,
    wins INTEGER DEFAULT 0, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS captchas(
    token TEXT PRIMARY KEY, chat_id INTEGER, user_id INTEGER, answer TEXT,
    expires_at INTEGER, message_id INTEGER);
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY, username TEXT, name TEXT);
CREATE INDEX IF NOT EXISTS users_username ON users(username);
CREATE TABLE IF NOT EXISTS chat_members(
    chat_id INTEGER, user_id INTEGER, first_seen INTEGER, last_seen INTEGER,
    joined_at INTEGER, active INTEGER DEFAULT 1, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS chats(
    chat_id INTEGER PRIMARY KEY, title TEXT, type TEXT, username TEXT,
    added_at INTEGER, last_seen INTEGER, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS bot_bans(
    kind TEXT, id INTEGER, reason TEXT, ts INTEGER, PRIMARY KEY(kind, id));
CREATE TABLE IF NOT EXISTS owner_log(
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, owner_id INTEGER, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS marriages(
    chat_id INTEGER, u1 INTEGER, u2 INTEGER, since INTEGER, b1 INTEGER DEFAULT -1, b2 INTEGER DEFAULT -1,
    PRIMARY KEY(chat_id, u1, u2));
CREATE TABLE IF NOT EXISTS relations(
    chat_id INTEGER, u1 INTEGER, u2 INTEGER, since INTEGER, PRIMARY KEY(chat_id, u1, u2));
CREATE TABLE IF NOT EXISTS parents(
    chat_id INTEGER, child INTEGER, parent INTEGER, since INTEGER, PRIMARY KEY(chat_id, child, parent));
CREATE TABLE IF NOT EXISTS pairs(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, u1 INTEGER, u2 INTEGER, stage TEXT DEFAULT 'relation',
    created INTEGER, sparks INTEGER DEFAULT 100, warmth INTEGER DEFAULT 0, level INTEGER DEFAULT 1,
    streak INTEGER DEFAULT 0, streak_day INTEGER DEFAULT 0, day INTEGER DEFAULT 0, mask INTEGER DEFAULT 0,
    n1 INTEGER DEFAULT 0, n2 INTEGER DEFAULT 0, rp1 INTEGER DEFAULT 0, rp2 INTEGER DEFAULT 0,
    act1 INTEGER DEFAULT 0, act2 INTEGER DEFAULT 0, next1 INTEGER DEFAULT 0, next2 INTEGER DEFAULT 0,
    upkeep_at INTEGER DEFAULT 0, state TEXT DEFAULT 'ok', quarrel_until INTEGER DEFAULT 0,
    offended_by INTEGER DEFAULT 0, last_active INTEGER DEFAULT 0, warned_day INTEGER DEFAULT 0,
    topup_day INTEGER DEFAULT 0, topup_sum INTEGER DEFAULT 0, protect INTEGER DEFAULT 1, intim_at INTEGER DEFAULT 0, premium_until INTEGER DEFAULT 0, gift_day INTEGER DEFAULT 0, gift_n INTEGER DEFAULT 0, ended_at INTEGER, ended_reason TEXT, legacy_key TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS pairs_legacy ON pairs(legacy_key);
CREATE INDEX IF NOT EXISTS pairs_chat ON pairs(chat_id, ended_at);
CREATE TABLE IF NOT EXISTS pair_log(
    id INTEGER PRIMARY KEY AUTOINCREMENT, pair_id INTEGER, ts INTEGER, kind TEXT, amount INTEGER, balance INTEGER,
    warmth INTEGER, actor INTEGER, detail TEXT);
CREATE INDEX IF NOT EXISTS pair_log_pair ON pair_log(pair_id, ts);
CREATE TABLE IF NOT EXISTS pair_counters(
    pair_id INTEGER, kind TEXT, n INTEGER DEFAULT 0, PRIMARY KEY(pair_id, kind));
CREATE TABLE IF NOT EXISTS pair_quests(
    pair_id INTEGER, scope TEXT, period INTEGER, slot INTEGER, kind TEXT, goal INTEGER, progress INTEGER DEFAULT 0,
    reward INTEGER, warmth INTEGER, done INTEGER DEFAULT 0, PRIMARY KEY(pair_id, scope, period, slot));
CREATE TABLE IF NOT EXISTS pair_gifts(
    pair_id INTEGER, gift TEXT, n INTEGER DEFAULT 0, PRIMARY KEY(pair_id, gift));
CREATE TABLE IF NOT EXISTS pair_houses(
    pair_id INTEGER PRIMARY KEY, tier TEXT, name TEXT, hoard INTEGER DEFAULT 0, bill_at INTEGER, debt INTEGER DEFAULT 0,
    missed INTEGER DEFAULT 0, arrested INTEGER DEFAULT 0, since INTEGER);
CREATE TABLE IF NOT EXISTS pair_rooms(
    pair_id INTEGER, room TEXT, level INTEGER DEFAULT 1, PRIMARY KEY(pair_id, room));
CREATE TABLE IF NOT EXISTS pair_baby(
    pair_id INTEGER PRIMARY KEY, mother INTEGER DEFAULT 0, started INTEGER, health INTEGER DEFAULT 80, health_at INTEGER,
    twins INTEGER DEFAULT 0, name TEXT DEFAULT '', doc_at INTEGER DEFAULT 0, rest_at INTEGER DEFAULT 0, vit_at INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS pair_children(
    id INTEGER PRIMARY KEY AUTOINCREMENT, pair_id INTEGER, name TEXT, born INTEGER,
    mood INTEGER DEFAULT 70, mood_at INTEGER DEFAULT 0, fed_at INTEGER DEFAULT 0, play_at INTEGER DEFAULT 0, study_at INTEGER DEFAULT 0, sport_at INTEGER DEFAULT 0, s_int INTEGER DEFAULT 0, s_cre INTEGER DEFAULT 0, s_spo INTEGER DEFAULT 0, grown INTEGER DEFAULT 0, job TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS user_gender(
    user_id INTEGER PRIMARY KEY, gender TEXT);
CREATE TABLE IF NOT EXISTS pair_pets(
    id INTEGER PRIMARY KEY AUTOINCREMENT, pair_id INTEGER, species TEXT, rarity TEXT, name TEXT DEFAULT '', egg INTEGER DEFAULT 1,
    hatch_at INTEGER, mood INTEGER DEFAULT 70, mood_at INTEGER DEFAULT 0, fed_at INTEGER DEFAULT 0, play_at INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0, claim_day INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS family_requests(
    id TEXT PRIMARY KEY, chat_id INTEGER, kind TEXT, from_user INTEGER, to_user INTEGER,
    message_id INTEGER, expires_at INTEGER);
CREATE TABLE IF NOT EXISTS ranks(
    chat_id INTEGER, user_id INTEGER, rank INTEGER, by_user INTEGER, ts INTEGER, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS cmd_access(
    chat_id INTEGER, command TEXT, min_rank INTEGER, PRIMARY KEY(chat_id, command));
CREATE TABLE IF NOT EXISTS mod_state(
    chat_id INTEGER, user_id INTEGER, kind TEXT, until INTEGER, reason TEXT, actor INTEGER, ts INTEGER,
    PRIMARY KEY(chat_id, user_id, kind));
CREATE TABLE IF NOT EXISTS pending_bans(
    chat_id INTEGER, username TEXT, duration INTEGER, reason TEXT, actor INTEGER, ts INTEGER, forced INTEGER DEFAULT 0,
    PRIMARY KEY(chat_id, username));
CREATE TABLE IF NOT EXISTS chat_texts(
    chat_id INTEGER, key TEXT, text TEXT, PRIMARY KEY(chat_id, key));
CREATE TABLE IF NOT EXISTS profiles(
    chat_id INTEGER, user_id INTEGER, nick TEXT, title TEXT, motto TEXT, about TEXT, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS reputation(
    chat_id INTEGER, user_id INTEGER, score INTEGER DEFAULT 0, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS rep_log(
    chat_id INTEGER, from_user INTEGER, to_user INTEGER, ts INTEGER);
CREATE TABLE IF NOT EXISTS awards(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, user_id INTEGER, degree INTEGER, by_user INTEGER, ts INTEGER);
CREATE TABLE IF NOT EXISTS notes(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, user_id INTEGER, kind TEXT, text TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS timers(
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, user_id INTEGER, due INTEGER, text TEXT);
CREATE TABLE IF NOT EXISTS family_bonus(
    chat_id INTEGER, user_id INTEGER, day INTEGER, PRIMARY KEY(chat_id, user_id));
CREATE INDEX IF NOT EXISTS mod_log_target ON mod_log(chat_id, target_id, ts);
CREATE INDEX IF NOT EXISTS chat_members_active ON chat_members(chat_id, active, last_seen);
CREATE INDEX IF NOT EXISTS mod_state_until ON mod_state(until);
DROP INDEX IF EXISTS msg_hourly_hour;
CREATE INDEX IF NOT EXISTS msg_hourly_cover ON msg_hourly(chat_id, hour_ts, user_id, n);
CREATE INDEX IF NOT EXISTS rep_log_idx ON rep_log(chat_id, from_user, to_user, ts);
CREATE TABLE IF NOT EXISTS farm(
    chat_id INTEGER, user_id INTEGER, last_ts INTEGER, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS user_memory(
    user_id INTEGER PRIMARY KEY, facts TEXT, enabled INTEGER DEFAULT 1, updated INTEGER);
CREATE TABLE IF NOT EXISTS topic_hourly(
    chat_id INTEGER, thread_id INTEGER, hour_ts INTEGER, n INTEGER, PRIMARY KEY(chat_id, thread_id, hour_ts));
CREATE TABLE IF NOT EXISTS topics(
    chat_id INTEGER, thread_id INTEGER, name TEXT, quiet INTEGER DEFAULT 0, PRIMARY KEY(chat_id, thread_id));
CREATE TABLE IF NOT EXISTS avatar_hash(
    user_id INTEGER PRIMARY KEY, hash TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS cas_allow(
    chat_id INTEGER, user_id INTEGER, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS guard_queries(
    chat_id INTEGER, user_id INTEGER, query_id TEXT, ts INTEGER, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS guest_bots(
    chat_id INTEGER, bot_id INTEGER, username TEXT, status INTEGER DEFAULT 0, last_seen INTEGER,
    PRIMARY KEY(chat_id, bot_id));
CREATE TABLE IF NOT EXISTS usage(
    chat_id INTEGER, kind TEXT, day INTEGER, n INTEGER, PRIMARY KEY(chat_id, kind, day));
CREATE TABLE IF NOT EXISTS garden(
    chat_id INTEGER, user_id INTEGER, data TEXT, PRIMARY KEY(chat_id, user_id));
CREATE TABLE IF NOT EXISTS update_queue(
    update_id INTEGER PRIMARY KEY, ts INTEGER, attempts INTEGER DEFAULT 0, payload TEXT);
CREATE TABLE IF NOT EXISTS duels(
    id TEXT PRIMARY KEY, chat_id INTEGER, data TEXT, expires_at INTEGER);
"""


PENDING_BAN_TTL = 7 * 86400   # отложенный бан по неизвестному нику живёт неделю


class _ConnectionGate:
    """Reentrant for the owning task; child tasks still wait for transaction completion."""
    def __init__(self):
        self._lock = asyncio.Lock()
        self._owner = None
        self._depth = 0

    async def __aenter__(self):
        task = asyncio.current_task()
        if self._owner is not task:
            await self._lock.acquire()
            self._owner = task
        self._depth += 1
        return self

    async def __aexit__(self, *args):
        self._depth -= 1
        if not self._depth:
            self._owner = None
            self._lock.release()


class _FlushingConn:
    """Прокси соединения: перед любым запросом к таблицам users / chat_members пишет накопленные в памяти записи
    (очередь записи, см. Database.remember_user / touch_member). Порядок «записали → прочитали» сохраняется,
    а тысячи мелких коммитов превращаются в одну транзакцию раз в несколько секунд."""

    def __init__(self, conn, db):
        self._conn, self._db = conn, db

    async def execute(self, sql, args=()):
        async with self._db._gate:
            # Buffered identity writes are flushed before an atomic money operation;
            # another task's new buffers must not become part of its rollback.
            if not self._db._atomic_active and self._db._dirty and ("chat_members" in sql or "users" in sql):
                await self._db._flush_users()
            return await self._conn.execute(sql, args)

    async def executemany(self, sql, args):
        async with self._db._gate:
            return await self._conn.executemany(sql, args)

    async def backup(self, target):
        async with self._db._gate:
            if self._db._atomic_active:
                raise RuntimeError("backup cannot run inside an atomic operation")
            await self._conn.commit()
            await self._conn.backup(target)

    async def commit(self):
        async with self._db._gate:
            if not self._db._atomic_active:
                await self._conn.commit()

    async def close(self):
        async with self._db._gate:
            await self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        if name in ("_conn", "_db"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)             # флаги вроде schema_keep относятся к настоящему соединению


# ┌─ КЛАСС Database — ВСЕ запросы к БД живут здесь ─────────────────────────────────────────────┐
# │ Хендлеры получают его параметром `db`. SQL не пишем в хендлерах — добавляем метод сюда.     │
# │ Файл разбит на разделы «# ---------- название ----------» (ищите по ним Ctrl+F):          │
# │   статистика · темы форума · пользователи · чаты · блокировки · участники · модерация ·      │
# │   фильтры · триггеры · ИИ-модерация · жалобы · ранги и ДК · настройки · экономика ·          │
# │   Premium · промокоды · предложка · цитатник · мог-баттлы · конкурсы · капча · карточки ·     │
# │   настольные игры · дуэли.   (Пары/семья — в bot/pair/.)                                      │
# │ Плейсхолдеры в SQL — `?` (для PostgreSQL заменяются автоматически, см. bot/pg.py).         │
# │ Несколько записей, которые должны пройти вместе: `async with db.atomic(): ...`.              │
# └──────────────────────────────────────────────────────────────────────────────────────────────┘
class Database:
    SETTINGS_TTL = 10.0   # кэш настроек чата живёт N сек (сбрасывается при set_setting)

    def __init__(self, conn, path: str = "", backend: str = "sqlite"):
        self._raw = conn
        self._gate = _ConnectionGate()
        self._atomic_active = False
        self._rollback_only = False
        self.conn = _FlushingConn(conn, self)
        self._dirty = False
        self._guest_cache: dict[tuple[int, int], tuple[int, float]] = {}   # (чат, бот) -> (статус, когда проверяли)
        self._topic_buf: dict[tuple[int, int, int], int] = {}      # (чат, тема, час) -> сообщений
        self._topics: dict[tuple[int, int], list] | None = None     # (чат, тема) -> [имя, тихая]; грузится при первом обращении
        self._user_buf: dict[int, tuple] = {}                   # очередь записи: user_id -> (username, name)
        self._member_buf: dict[tuple[int, int], list] = {}      # (чат, юзер) -> [последний раз, вступил или None]
        self.path = path
        self.backend = backend
        self._clock = time.monotonic
        self._settings_cache: dict[int, tuple[float, dict]] = {}
        self.settings_reads = 0
        self._lists_version: dict[int, int] = {}   # растёт при правке фильтров/белого списка — для кэшей
        self.auditor = None   # bot.audit.Auditor: получает записи журнала модерации (если задан)
        self._msg_buf: dict[tuple[int, int, int], int] = {}   # (чат, юзер, час) -> сообщений, ещё не записанных
        self._rank_cache: dict[tuple[int, int], tuple[float, int]] = {}
        self._access_cache: dict[int, tuple[float, dict]] = {}
        self._ensure_window: list = [0.0, 0]
        self._miss: dict[str, float] = {}                      # @ник -> до какого времени не спрашиваем Telegram повторно
        self.bot = None
        self._joined_cache: dict[tuple[int, int], tuple[float, int | None]] = {}
        self._user_cache: dict[int, tuple] = {}               # user_id -> (username, name), уже лежит в БД
        self._pending_names: set[str] = set()                 # ники с отложенным баном (проверка без запроса к БД)

    @classmethod
    async def connect(cls, path: str, schema: str | None = None) -> "Database":
        """path — файл SQLite или postgresql://… (schema — отдельная схема PG, нужна тестам)."""
        if path.startswith(("postgresql://", "postgres://")):
            pass  # (импорт убран: всё в одном модуле)
            conn = await connect__pg(path, schema)
            try:
                await conn.executescript(SCHEMA)
                await conn.execute("ALTER TABLE pairs ADD COLUMN IF NOT EXISTS gift_day INTEGER DEFAULT 0")
                for _c, _t in CHILD_COLS:
                    await conn.execute(f"ALTER TABLE pair_children ADD COLUMN IF NOT EXISTS {_c} {_t}")
                await conn.execute("ALTER TABLE pairs ADD COLUMN IF NOT EXISTS gift_n INTEGER DEFAULT 0")
                await conn.execute("ALTER TABLE pairs ADD COLUMN IF NOT EXISTS protect INTEGER DEFAULT 1")
                await conn.execute("ALTER TABLE pairs ADD COLUMN IF NOT EXISTS premium_until INTEGER DEFAULT 0")
                await conn.execute("ALTER TABLE pairs ADD COLUMN IF NOT EXISTS intim_at INTEGER DEFAULT 0")
                await conn.execute("ALTER TABLE captchas ADD COLUMN IF NOT EXISTS kind TEXT DEFAULT 'member'")
                await conn.execute("ALTER TABLE mod_log ADD COLUMN IF NOT EXISTS duration BIGINT")
                await conn.execute("ALTER TABLE captchas ADD COLUMN IF NOT EXISTS level INTEGER DEFAULT 0")
                await conn.execute("ALTER TABLE captchas ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0")
                await conn.execute("ALTER TABLE pending_bans ADD COLUMN IF NOT EXISTS forced BIGINT DEFAULT 0")
                await conn.commit()
                db = cls(conn, path, backend="pg")
                await db._migrate_payment_receipts()
                await db.migrate_legacy_warns()
                await db.load_pending_names()
                return db
            except BaseException:
                await conn.close()
                raise
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        if path and path != ":memory:" and not path.startswith("file:"):
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                metadata = os.stat(path)
                if not stat.S_ISREG(metadata.st_mode):
                    raise ValueError("SQLite database path must be a regular file")
                # Keep owner/group policy, but never expose database contents to everyone.
                if os.name == "posix" and metadata.st_mode & 0o007:
                    os.chmod(path, stat.S_IMODE(metadata.st_mode) & ~0o007)
            else:
                os.close(descriptor)
        conn = await aiosqlite.connect(path)
        try:
            conn.row_factory = aiosqlite.Row
            await conn.create_function("lower_py", 1, lambda s: s.lower() if isinstance(s, str) else s)
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.executescript(SCHEMA)
            cols = [r[1] for r in await (await conn.execute("PRAGMA table_info(captchas)")).fetchall()]
            if "kind" not in cols:  # миграция существующих баз
                await conn.execute("ALTER TABLE captchas ADD COLUMN kind TEXT DEFAULT 'member'")
            if "level" not in cols:   # сложность капчи (0 обычная, 1 повышенная, 2 усиленная)
                await conn.execute("ALTER TABLE captchas ADD COLUMN level INTEGER DEFAULT 0")
            if "attempts" not in cols:  # неверные попытки капчи: в БД, чтобы перезапуск бота их не обнулял
                await conn.execute("ALTER TABLE captchas ADD COLUMN attempts INTEGER DEFAULT 0")
            cols = [r[1] for r in await (await conn.execute("PRAGMA table_info(pair_children)")).fetchall()]
            for _c, _t in CHILD_COLS:
                if _c not in cols:
                    await conn.execute(f"ALTER TABLE pair_children ADD COLUMN {_c} {_t}")
            cols = [r[1] for r in await (await conn.execute("PRAGMA table_info(pairs)")).fetchall()]
            for col in ("gift_day", "gift_n", "intim_at"):
                if col not in cols:
                    await conn.execute(f"ALTER TABLE pairs ADD COLUMN {col} INTEGER DEFAULT 0")
            if "premium_until" not in cols:
                await conn.execute("ALTER TABLE pairs ADD COLUMN premium_until INTEGER DEFAULT 0")
            if "protect" not in cols:
                await conn.execute("ALTER TABLE pairs ADD COLUMN protect INTEGER DEFAULT 1")
            cols = [r[1] for r in await (await conn.execute("PRAGMA table_info(pending_bans)")).fetchall()]
            if "forced" not in cols:
                await conn.execute("ALTER TABLE pending_bans ADD COLUMN forced INTEGER DEFAULT 0")
            cols = [r[1] for r in await (await conn.execute("PRAGMA table_info(mod_log)")).fetchall()]
            if "duration" not in cols:
                await conn.execute("ALTER TABLE mod_log ADD COLUMN duration INTEGER")
            await conn.commit()
            db = cls(conn, path)
            await db._migrate_payment_receipts()
            await db.migrate_legacy_warns()
            await db.load_pending_names()
            await db.optimize()
            return db

        except BaseException:
            await conn.close()
            raise

    @asynccontextmanager
    async def atomic(self):
        """Exclusive DB transaction for composed operations; do not call external services here.

        Inner commit() calls are deferred. Nested failures mark the outer transaction
        for rollback even if a caller catches the inner exception. Identity buffers
        are flushed before entry, and are not consumed by queries inside this scope.
        """
        async with self._gate:
            if self._atomic_active:
                try:
                    yield
                except BaseException:
                    self._rollback_only = True
                    raise
                return
            await self._flush_users()
            await self._raw.commit()
            self._atomic_active = True
            self._rollback_only = False
            try:
                if self.backend == "pg":
                    await self._raw.begin()
                else:
                    await self._raw.execute("BEGIN IMMEDIATE")
                yield
                if self._rollback_only:
                    raise RuntimeError("nested transaction failed")
                await self._raw.commit()
            except BaseException:
                # Repeated cancellation must not release the gate before rollback finishes.
                cleanup = asyncio.create_task(self._raw.rollback())
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        continue
                cleanup.result()
                raise
            finally:
                self._atomic_active = False
                self._rollback_only = False

    async def _migrate_payment_receipts(self):
        async with self.atomic():
            cur = await self.conn.execute("SELECT 1 FROM schema_migrations WHERE name=?", ("payment_receipts_v1",))
            if await cur.fetchone():
                return
            # Keep historical rows intact; duplicate legacy charges acquire one receipt.
            await self.conn.execute(
                "INSERT OR IGNORE INTO payment_receipts(charge_id,ts) "
                "SELECT charge_id,MIN(ts) FROM payments WHERE charge_id IS NOT NULL GROUP BY charge_id")
            await self.conn.execute("INSERT OR IGNORE INTO schema_migrations(name) VALUES(?)", ("payment_receipts_v1",))

    async def close(self) -> None:
        try:
            await self.flush_messages()
        finally:
            await self.conn.close()

    # ---------- память о собеседнике ----------
    async def memory_get(self, user_id: int) -> dict:
        cur = await self.conn.execute("SELECT facts, enabled FROM user_memory WHERE user_id=?", (user_id,))
        r = await cur.fetchone()
        facts = [f for f in (r["facts"] if r else "").split("\n") if f.strip()]
        return {"facts": facts, "enabled": bool(r["enabled"]) if r else True}

    async def memory_set(self, user_id: int, facts: list[str], enabled: bool, now: int) -> None:
        await self.conn.execute(
            "INSERT INTO user_memory(user_id,facts,enabled,updated) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
            "facts=excluded.facts, enabled=excluded.enabled, updated=excluded.updated",
            (user_id, "\n".join(facts), 1 if enabled else 0, now))
        await self.conn.commit()

    # ---------- статистика ----------
    # ---------- темы форума ----------
    async def _topics_loaded(self) -> dict:
        if self._topics is None:
            cur = await self.conn.execute("SELECT chat_id, thread_id, name, quiet FROM topics")
            self._topics = {(r["chat_id"], r["thread_id"]): [r["name"], bool(r["quiet"])] for r in await cur.fetchall()}
        return self._topics

    def record_topic_message(self, chat_id: int, thread_id: int, ts: int) -> None:
        k = (chat_id, thread_id, ts // HOUR * HOUR)
        self._topic_buf[k] = self._topic_buf.get(k, 0) + 1

    async def topic_seen(self, chat_id: int, thread_id: int, name: str | None) -> None:
        """Запоминаем название темы (из служебных сообщений Telegram); пишем в БД только при изменении."""
        topics = await self._topics_loaded()
        cur = topics.get((chat_id, thread_id))
        if cur is not None and (not name or cur[0] == name):
            return
        quiet = cur[1] if cur else False
        topics[(chat_id, thread_id)] = [name or (cur[0] if cur else None), quiet]
        await self.conn.execute(
            "INSERT INTO topics(chat_id,thread_id,name,quiet) VALUES(?,?,?,?) ON CONFLICT(chat_id,thread_id) DO UPDATE SET name=COALESCE(excluded.name, topics.name)",
            (chat_id, thread_id, name, 1 if quiet else 0))
        await self.conn.commit()

    async def set_topic_quiet(self, chat_id: int, thread_id: int, quiet: bool) -> None:
        topics = await self._topics_loaded()
        cur = topics.get((chat_id, thread_id), [None, False])
        topics[(chat_id, thread_id)] = [cur[0], quiet]
        await self.conn.execute(
            "INSERT INTO topics(chat_id,thread_id,name,quiet) VALUES(?,?,?,?) ON CONFLICT(chat_id,thread_id) DO UPDATE SET quiet=excluded.quiet",
            (chat_id, thread_id, cur[0], 1 if quiet else 0))
        await self.conn.commit()

    async def topic_quiet(self, chat_id: int, thread_id: int) -> bool:
        topics = await self._topics_loaded()
        cur = topics.get((chat_id, thread_id))
        return bool(cur and cur[1])

    async def topic_name(self, chat_id: int, thread_id: int) -> str:
        topics = await self._topics_loaded()
        cur = topics.get((chat_id, thread_id))
        return (cur[0] if cur and cur[0] else ("Общая" if thread_id == 0 else f"Тема {thread_id}"))

    async def topic_stats(self, chat_id: int, since_ts: int, limit: int = 15) -> list[tuple[int, int]]:
        await self.flush_messages()
        cur = await self.conn.execute(
            "SELECT thread_id, SUM(n) AS n FROM topic_hourly WHERE chat_id=? AND hour_ts>=? GROUP BY thread_id "
            "ORDER BY n DESC, thread_id LIMIT ?", (chat_id, since_ts // HOUR * HOUR, limit))
        return [(r["thread_id"], r["n"]) for r in await cur.fetchall()]

    async def topic_list(self, chat_id: int) -> list[tuple[int, str, bool]]:
        topics = await self._topics_loaded()
        return sorted(((t, v[0] or f"Тема {t}", v[1]) for (c, t), v in topics.items() if c == chat_id))

    async def record_message(self, chat_id: int, user_id: int, ts: int) -> None:
        """Счётчик копится в памяти и пишется пачкой (flush_messages): одна транзакция вместо коммита на каждое сообщение."""
        k = (chat_id, user_id, ts // HOUR * HOUR)
        self._msg_buf[k] = self._msg_buf.get(k, 0) + 1

    async def _flush_users(self) -> None:
        """Записать очередь пользователей и участников одной транзакцией (идёт мимо прокси — без рекурсии)."""
        async with self._gate:
            if self._atomic_active:
                raise RuntimeError("flush identities before entering an atomic operation")
            users, members = self._user_buf, self._member_buf
            self._user_buf, self._member_buf, self._dirty = {}, {}, False
            if not users and not members:
                return
            try:
                # Не смешиваем буфер с незавершёнными записями других операций.
                await self._raw.commit()
                if users:
                    await self._raw.executemany(
                        "INSERT INTO users VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
                        "username=excluded.username, name=excluded.name",
                        [(uid, username, name) for uid, (username, name) in users.items()])
                if members:
                    await self._raw.executemany(
                        "INSERT INTO chat_members(chat_id,user_id,first_seen,last_seen,joined_at,active) "
                        "VALUES(?,?,?,?,?,1) ON CONFLICT(chat_id,user_id) DO UPDATE SET last_seen=excluded.last_seen, "
                        "active=1, joined_at=CASE WHEN ?=1 THEN excluded.joined_at ELSE chat_members.joined_at END",
                        [(chat_id, uid, first, ts, joined, 1 if joined is not None else 0)
                         for (chat_id, uid), (ts, joined, first) in members.items()])
                await self._raw.commit()
            except BaseException:
                # Дождаться отката даже при повторной отмене задачи, прежде чем
                # освободить соединение и вернуть записи в буфер.
                rollback = asyncio.create_task(self._raw.rollback())
                while not rollback.done():
                    try:
                        await asyncio.shield(rollback)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                try:
                    rollback.result()
                finally:
                    for uid, v in users.items():
                        self._user_buf.setdefault(uid, v)
                    for k, v in members.items():
                        self._member_buf.setdefault(k, v)
                    self._dirty = True
                raise

    async def flush_messages(self) -> None:
        if self._atomic_active and self._gate._owner is asyncio.current_task():
            if self._dirty or self._topic_buf or self._msg_buf:
                raise RuntimeError("flush counters before entering an atomic operation")
            return
        if self._dirty:
            await self._flush_users()
        if not self._topic_buf and not self._msg_buf:
            return
        tbuf, buf = {}, {}
        try:
            async with self.atomic():
                tbuf, self._topic_buf = self._topic_buf, {}
                buf, self._msg_buf = self._msg_buf, {}
                if tbuf:
                    await self.conn.executemany(
                        "INSERT INTO topic_hourly VALUES(?,?,?,?) ON CONFLICT(chat_id,thread_id,hour_ts) DO UPDATE SET n=topic_hourly.n+excluded.n",
                        [(chat_id, thread, hour, n) for (chat_id, thread, hour), n in tbuf.items()])
                if buf:
                    await self.conn.executemany(
                        "INSERT INTO msg_hourly VALUES(?,?,?,?) "
                        "ON CONFLICT(chat_id,user_id,hour_ts) DO UPDATE SET n=msg_hourly.n+excluded.n",
                        [(chat_id, user_id, hour, n) for (chat_id, user_id, hour), n in buf.items()])
        except BaseException:
            for k, n in tbuf.items():
                self._topic_buf[k] = self._topic_buf.get(k, 0) + n
            for k, n in buf.items():
                self._msg_buf[k] = self._msg_buf.get(k, 0) + n
            raise

    async def count_by_user(
        self, chat_id: int, since_ts: int | None, limit: int = 15
    ) -> tuple[int, list[tuple[int, int]]]:
        await self.flush_messages()
        since_h = -1 if since_ts is None else since_ts // HOUR * HOUR
        since_d = -1 if since_ts is None else since_ts
        cur = await self.conn.execute(
            "SELECT user_id, SUM(n) AS n FROM ("
            " SELECT user_id, n FROM msg_hourly WHERE chat_id=? AND hour_ts>=?"
            " UNION ALL"
            " SELECT user_id, n FROM msg_daily WHERE chat_id=? AND day_ts>=?"
            ") GROUP BY user_id ORDER BY n DESC, user_id",
            (chat_id, since_h, chat_id, since_d),
        )
        rows = await cur.fetchall()
        total = sum(r["n"] for r in rows)
        return total, [(r["user_id"], r["n"]) for r in rows[:limit]]

    async def activity_series(self, chat_id: int, since_ts: int, bucket: int) -> list[tuple[int, int]]:
        """Сообщения чата по корзинам: bucket=HOUR для почасовых, DAY — для дневных (часы старше 90 дней свёрнуты в дни)."""
        await self.flush_messages()
        cur = await self.conn.execute(
            "SELECT ts, SUM(n) AS n FROM ("
            " SELECT hour_ts/? *? AS ts, n FROM msg_hourly WHERE chat_id=? AND hour_ts>=?"
            " UNION ALL"
            " SELECT day_ts/? *? AS ts, n FROM msg_daily WHERE chat_id=? AND day_ts>=?"
            ") t GROUP BY ts ORDER BY ts",
            (bucket, bucket, chat_id, since_ts // HOUR * HOUR, bucket, bucket, chat_id, since_ts))
        return [(int(r["ts"]), int(r["n"])) for r in await cur.fetchall()]

    async def charts_data(self, chat_id: int, since_ts: int, tz_offset: int) -> dict:
        """Данные для графиков мини-приложения: сообщения по часам суток и дням недели (по времени чата) и приток участников по дням."""
        await self.flush_messages()
        cur = await self.conn.execute(
            "SELECT hour_ts, SUM(n) AS n FROM msg_hourly WHERE chat_id=? AND hour_ts>=? GROUP BY hour_ts", (chat_id, since_ts))
        by_hour, by_wd = [0] * 24, [0] * 7
        for r in await cur.fetchall():
            local = r["hour_ts"] + tz_offset
            by_hour[(local // 3600) % 24] += r["n"]
            by_wd[((local // 86400) + 3) % 7] += r["n"]            # 1 янв 1970 — четверг; 0 = понедельник
        cur = await self.conn.execute(
            "SELECT (COALESCE(joined_at, first_seen)+?)/86400 AS d, COUNT(*) AS n FROM chat_members "
            "WHERE chat_id=? AND COALESCE(joined_at, first_seen)>=? GROUP BY d ORDER BY d", (tz_offset, chat_id, since_ts))
        joins = [[r["d"] * 86400 - tz_offset, r["n"]] for r in await cur.fetchall()]
        return {"by_hour": by_hour, "by_weekday": by_wd, "joins": joins}

    async def user_total(self, chat_id: int, user_id: int, since_ts: int | None) -> int:
        await self.flush_messages()
        since_h = -1 if since_ts is None else since_ts // HOUR * HOUR
        since_d = -1 if since_ts is None else since_ts
        cur = await self.conn.execute(
            "SELECT COALESCE(SUM(n),0) FROM ("
            " SELECT n FROM msg_hourly WHERE chat_id=? AND user_id=? AND hour_ts>=?"
            " UNION ALL"
            " SELECT n FROM msg_daily WHERE chat_id=? AND user_id=? AND day_ts>=?)",
            (chat_id, user_id, since_h, chat_id, user_id, since_d),
        )
        return (await cur.fetchone())[0]

    async def rollup_old(self, now: int) -> None:
        await self.flush_messages()
        border = now - ROLLUP_DAYS * DAY__db
        await self.conn.execute(
            "INSERT INTO msg_daily SELECT chat_id, user_id, day, SUM(n) FROM ("
            "SELECT chat_id, user_id, hour_ts/? *? AS day, n FROM msg_hourly WHERE hour_ts<?) t "
            "GROUP BY chat_id, user_id, day "
            "ON CONFLICT(chat_id,user_id,day_ts) DO UPDATE SET n=msg_daily.n+excluded.n",
            (DAY__db, DAY__db, border),
        )
        await self.conn.execute("DELETE FROM msg_hourly WHERE hour_ts<?", (border,))
        await self.conn.commit()

    async def optimize(self) -> None:
        """Статистика для планировщика запросов SQLite (без неё он, например, выбирает для «сообщений человека» не тот
        индекс — в 30 раз медленнее). Дёшево; в PostgreSQL статистику собирает сам сервер (autovacuum)."""
        if self.backend != "sqlite":
            return
        await self.conn.execute("PRAGMA optimize=0x10002")
        await self.conn.commit()

    async def prune_old(self, now: int) -> None:
        """Чистка таблиц, которые иначе растут бесконечно: журнал репутации (кулдаун — часы) и суточные лимиты."""
        await self.conn.execute("DELETE FROM rep_log WHERE ts<?", (now - 2 * DAY__db,))
        await self.conn.execute("DELETE FROM usage WHERE day<?", (now // DAY__db - 7,))
        await self.conn.execute("DELETE FROM aimod_events WHERE ts<?", (now - 7 * DAY__db,))   # тексты хранятся неделю
        await self.conn.execute("DELETE FROM pending_bans WHERE ts<?", (now - PENDING_BAN_TTL,))
        await self.load_pending_names()
        await self.gw_prune(now)
        await self.conn.commit()

    # ---------- пользователи (для поиска по @username) ----------
    async def remember_user(self, user_id: int, username: str | None, name: str) -> None:
        val = ((username or "").lstrip("@").lower() or None, name)
        _remember_username(user_id, username)
        if self._user_cache.get(user_id) == val:
            return                                   # ничего не изменилось — не пишем в БД на каждое сообщение
        if len(self._user_cache) > 50000:
            self._user_cache.clear()
        self._user_cache[user_id] = val
        self._user_buf[user_id] = val                # пишется пачкой в _flush_users (раз в несколько секунд)
        self._dirty = True

    async def ensure_user(self, user_id: int, username: str | None = None, name: str | None = None) -> None:
        """Запомнить пользователя при любом контакте. Если данных нет — запись по одному id; уже известные имя и ник
        пустыми значениями не затираются."""
        if user_id in self._user_cache and not (username or name):
            return
        if not 0 < user_id < 10**13:                 # заведомо не id пользователя Telegram
            return
        if not (username or name):                   # id из текста команды: записей по голому id — не больше 60 в минуту
            now = self._clock()
            if now - self._ensure_window[0] > 60:
                self._ensure_window = [now, 0]
            if self._ensure_window[1] >= 60:
                return
            self._ensure_window[1] += 1
        cur = await self.conn.execute("SELECT username, name FROM users WHERE user_id=?", (user_id,))
        r = await cur.fetchone()
        if r is None:
            await self.remember_user(user_id, username, name or f"id{user_id}")
        elif username or (name and (not r["name"] or r["name"] == f"id{user_id}")):
            await self.remember_user(user_id, username or r["username"], name or r["name"] or f"id{user_id}")
        else:
            self._user_cache[user_id] = (r["username"], r["name"])

    async def get_username(self, user_id: int) -> str | None:
        hit = self._user_cache.get(user_id)
        if hit is not None:
            return hit[0]
        cur = await self.conn.execute("SELECT username FROM users WHERE user_id=?", (user_id,))
        r = await cur.fetchone()
        return r["username"] if r and r["username"] else None

    async def find_user(self, username: str) -> int | None:
        cur = await self.conn.execute(
            "SELECT user_id FROM users WHERE username=?", (username.lstrip("@").lower(),)
        )
        r = await cur.fetchone()
        if r:
            return r["user_id"]
        bot = getattr(self, "bot", None)
        key = username.lstrip("@").lower()
        if self._miss.get(key, 0) > self._clock():   # недавно уже спрашивали Telegram и не нашли — не спрашиваем снова
            return None
        if bot is not None:                          # бот мог не видеть человека, но Telegram иногда отдаёт его по нику
            try:
                chat = await bot.get_chat("@" + username.lstrip("@"))
                if chat.type == "private":
                    await self.remember_user(chat.id, getattr(chat, "username", None) or username,
                                             getattr(chat, "full_name", None) or f"id{chat.id}")
                    return chat.id
            except Exception:
                pass
            if len(self._miss) > 5000:
                self._miss.clear()
            self._miss[key] = self._clock() + 600
        return None

    async def user_name(self, user_id: int) -> str | None:
        hit = self._user_cache.get(user_id)
        if hit is not None and hit[1]:                # имя уже в памяти — без запроса к БД (раньше был запрос на каждого в списке)
            _remember_username(user_id, hit[0])
            return hit[1]
        cur = await self.conn.execute("SELECT name, username FROM users WHERE user_id=?", (user_id,))
        r = await cur.fetchone()
        if r is None:
            return None
        _remember_username(user_id, r["username"])
        return r["name"]

    # ---------- чаты (для панели владельца) ----------
    async def users_by_ids(self, user_ids) -> dict[int, dict]:
        """Имена и ники пачками вместо двух запросов на каждого участника."""
        ids = list(dict.fromkeys(user_ids))
        out = {uid: {"user_id": uid, "username": self._user_cache[uid][0], "name": self._user_cache[uid][1]}
               for uid in ids if uid in self._user_cache}
        ids = [uid for uid in ids if uid not in out]
        for start in range(0, len(ids), 900):
            batch = ids[start:start + 900]
            placeholders = ",".join("?" for _ in batch)
            cur = await self.conn.execute(
                f"SELECT user_id, name, username FROM users WHERE user_id IN ({placeholders})", tuple(batch))
            out.update((r["user_id"], dict(r)) for r in await cur.fetchall())
        for uid, user in out.items():
            _remember_username(uid, user["username"])
        return out

    async def upsert_chat(self, chat_id: int, title: str | None, ctype: str, username: str | None, ts: int) -> None:
        await self.conn.execute(
            "INSERT INTO chats(chat_id,title,type,username,added_at,last_seen,active) VALUES(?,?,?,?,?,?,1) "
            "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, type=excluded.type, "
            "username=excluded.username, last_seen=excluded.last_seen, active=1",
            (chat_id, title, ctype, username, ts, ts))
        await self.conn.commit()

    async def set_chat_active(self, chat_id: int, active: bool) -> None:
        await self.conn.execute("UPDATE chats SET active=? WHERE chat_id=?", (1 if active else 0, chat_id))
        await self.conn.commit()

    async def count_chats(self, active_only: bool = False) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) FROM chats" + (" WHERE active=1" if active_only else ""))
        return (await cur.fetchone())[0]

    async def list_chats(self, offset: int, limit: int, active_only: bool = False) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT * FROM chats" + (" WHERE active=1" if active_only else "")
            + " ORDER BY last_seen DESC, chat_id LIMIT ? OFFSET ?", (limit, offset))
        return [dict(r) for r in await cur.fetchall()]

    async def get_chat(self, chat_id: int) -> dict | None:
        cur = await self.conn.execute("SELECT * FROM chats WHERE chat_id=?", (chat_id,))
        r = await cur.fetchone()
        return dict(r) if r else None

    # ---------- поиск пользователей ----------
    async def count_users(self) -> int:
        cur = await self.conn.execute("SELECT COUNT(*) FROM users")
        return (await cur.fetchone())[0]

    async def search_users(self, query: str, limit: int = 10, offset: int = 0) -> list[dict]:
        q = query.strip().lstrip("@").lower()[:64]
        if not q:                                    # пустой запрос — все известные боту пользователи
            cur = await self.conn.execute(
                "SELECT user_id, username, name FROM users ORDER BY user_id DESC LIMIT ? OFFSET ?", (limit, offset))
            return [dict(r) for r in await cur.fetchall()]
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        cur = await self.conn.execute(
            "SELECT user_id, username, name FROM users WHERE user_id=? OR username LIKE ? ESCAPE '\\' "
            "OR lower_py(name) LIKE ? ESCAPE '\\' ORDER BY user_id LIMIT ? OFFSET ?",
            (int(q) if q.isdigit() else -1, f"%{esc}%", f"%{esc}%", limit, offset))
        return [dict(r) for r in await cur.fetchall()]

    async def user_card(self, user_id: int) -> dict | None:
        cur = await self.conn.execute("SELECT user_id, username, name FROM users WHERE user_id=?", (user_id,))
        r = await cur.fetchone()
        if not r:
            return None
        card = dict(r)
        await self.flush_messages()
        cur = await self.conn.execute("SELECT COUNT(*) FROM chat_members WHERE user_id=?", (user_id,))
        card["chats"] = (await cur.fetchone())[0]
        cur = await self.conn.execute(
            "SELECT (SELECT COALESCE(SUM(n),0) FROM msg_hourly WHERE user_id=?) + "
            "(SELECT COALESCE(SUM(n),0) FROM msg_daily WHERE user_id=?)", (user_id, user_id))
        card["messages"] = (await cur.fetchone())[0]
        return card

    # ---------- блокировки в боте, глобальные флаги, журнал владельца ----------
    async def bot_ban(self, kind: str, id_: int, reason: str, ts: int) -> None:
        await self.conn.execute(
            "INSERT INTO bot_bans VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET reason=excluded.reason, ts=excluded.ts",
            (kind, id_, reason, ts))
        await self.conn.commit()

    async def bot_unban(self, kind: str, id_: int) -> None:
        await self.conn.execute("DELETE FROM bot_bans WHERE kind=? AND id=?", (kind, id_))
        await self.conn.commit()

    async def list_bot_bans(self, kind: str) -> list[dict]:
        cur = await self.conn.execute("SELECT * FROM bot_bans WHERE kind=? ORDER BY ts DESC", (kind,))
        return [dict(r) for r in await cur.fetchall()]

    async def load_bans(self) -> tuple[set[int], set[int]]:
        cur = await self.conn.execute("SELECT kind, id FROM bot_bans")
        rows = await cur.fetchall()
        return ({r["id"] for r in rows if r["kind"] == "user"}, {r["id"] for r in rows if r["kind"] == "chat"})

    async def get_global(self) -> dict:
        cur = await self.conn.execute("SELECT key, value FROM settings WHERE chat_id=0")
        out = dict(GLOBAL_DEFAULTS)
        for r in await cur.fetchall():
            if r["key"] in out:
                out[r["key"]] = int(r["value"])
        return out

    async def set_global(self, key: str, value: int) -> None:
        if key not in GLOBAL_DEFAULTS:
            raise KeyError(key)
        await self.conn.execute(
            "INSERT INTO settings VALUES(0,?,?) ON CONFLICT(chat_id,key) DO UPDATE SET value=excluded.value",
            (key, str(int(value))))
        await self.conn.commit()

    async def log_owner(self, owner_id: int, action: str, detail: str, ts: int) -> None:
        await self.conn.execute(
            "INSERT INTO owner_log(ts,owner_id,action,detail) VALUES(?,?,?,?)", (ts, owner_id, action, detail))
        await self.conn.commit()

    async def recent_owner_log(self, limit: int = 15) -> list[dict]:
        cur = await self.conn.execute("SELECT * FROM owner_log ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]

    async def size_bytes(self) -> int:
        if self.backend == "pg":
            cur = await self.conn.execute("SELECT pg_database_size(current_database()) AS n")
            return int((await cur.fetchone())["n"])
        try:
            return os.path.getsize(self.path)
        except (OSError, TypeError):
            return 0

    async def backup_to(self, path: str) -> None:
        if self._atomic_active and self._gate._owner is asyncio.current_task():
            raise RuntimeError("backup cannot run inside an atomic operation")
        await self.flush_messages()
        if self.backend == "pg":
            pass  # (импорт убран: всё в одном модуле)
            await pg_dump(self.path, path)
            return
        import sqlite3
        dest = sqlite3.connect(path)
        task = asyncio.create_task(self.conn.backup(dest))
        try:
            await asyncio.shield(task)
        finally:
            # SQLite's worker thread may still be using the destination after cancellation.
            try:
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        continue
            finally:
                dest.close()
            if not task.cancelled():
                task.result()

    # ---------- участники чатов ----------
    async def touch_member(self, chat_id: int, user_id: int, ts: int, joined: bool = False) -> None:
        self._joined_cache.pop((chat_id, user_id), None)
        k = (chat_id, user_id)
        prev = self._member_buf.get(k)
        self._member_buf[k] = [max(ts, prev[0]) if prev else ts, (ts if joined else None) or (prev[1] if prev else None),
                               min(ts, prev[2]) if prev else ts]
        self._dirty = True

    async def set_member_active(self, chat_id: int, user_id: int, active: bool) -> None:
        await self.conn.execute(
            "UPDATE chat_members SET active=? WHERE chat_id=? AND user_id=?",
            (1 if active else 0, chat_id, user_id),
        )
        await self.conn.commit()

    async def member_joined_at(self, chat_id: int, user_id: int) -> int | None:
        hit = self._joined_cache.get((chat_id, user_id))
        if hit and self._clock() - hit[0] < self.HOT_TTL:
            return hit[1]
        cur = await self.conn.execute(
            "SELECT joined_at FROM chat_members WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
        r = await cur.fetchone()
        val = r["joined_at"] if r else None
        self._hot_put(self._joined_cache, (chat_id, user_id), val)
        return val

    async def random_member(self, chat_id: int) -> tuple[int, str] | None:
        """Случайный участник именно этого чата (кого бот видел и кто не вышел)."""
        cur = await self.conn.execute(
            "SELECT m.user_id, COALESCE(u.name, 'id'||m.user_id) AS name FROM chat_members m "
            "LEFT JOIN users u ON u.user_id=m.user_id WHERE m.chat_id=? AND m.active=1 "
            "ORDER BY RANDOM() LIMIT 1", (chat_id,))
        r = await cur.fetchone()
        return (r["user_id"], r["name"]) if r else None

    async def random_members(self, chat_id: int, n: int, exclude: tuple = ()) -> list[tuple[int, str]]:
        clause = f" AND m.user_id NOT IN ({','.join('?' * len(exclude))})" if exclude else ""
        cur = await self.conn.execute(
            "SELECT m.user_id, COALESCE(u.name, 'id'||m.user_id) AS name FROM chat_members m "
            "LEFT JOIN users u ON u.user_id=m.user_id WHERE m.chat_id=? AND m.active=1"
            + clause + " ORDER BY RANDOM() LIMIT ?", (chat_id, *exclude, n))
        return [(r["user_id"], r["name"]) for r in await cur.fetchall()]

    async def claim_farm(self, chat_id: int, user_id: int, now: int, cooldown: int, amount: int) -> tuple[int | None, int]:
        """(начислено или None, сколько секунд ждать). Проверка и запись — одним запросом, без гонок."""
        async with self.atomic():
            cur = await self.conn.execute(
                "INSERT INTO farm VALUES(?,?,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET last_ts=excluded.last_ts "
                "WHERE farm.last_ts<=?", (chat_id, user_id, now, now - cooldown))
            await self.conn.commit()
            if cur.rowcount == 1:
                await self.change_balance(chat_id, user_id, amount)
                return amount, 0
            cur = await self.conn.execute("SELECT last_ts FROM farm WHERE chat_id=? AND user_id=?", (chat_id, user_id))
            r = await cur.fetchone()
            return None, max(cooldown - (now - r["last_ts"]), 1)

    async def member_count(self, chat_id: int) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) FROM chat_members WHERE chat_id=? AND active=1", (chat_id,))
        return (await cur.fetchone())[0]

    # ---------- суточные лимиты платных функций ----------
    async def take_quota(self, chat_id: int, kind: str, now: int, limit: int) -> bool:
        """Списать 1 единицу суточного лимита чата. False — лимит исчерпан."""
        if type(limit) is not int or limit <= 0:
            return False
        cur = await self.conn.execute(
            "INSERT INTO usage VALUES(?,?,?,1) ON CONFLICT(chat_id,kind,day) DO UPDATE SET n=usage.n+1 "
            "WHERE usage.n<?", (chat_id, kind, now // DAY__db, limit))
        await self.conn.commit()
        return cur.rowcount == 1

    async def refund_quota(self, chat_id: int, kind: str, now: int) -> None:
        await self.conn.execute(
            "UPDATE usage SET n=n-1 WHERE chat_id=? AND kind=? AND day=? AND n>0", (chat_id, kind, now // DAY__db))
        await self.conn.commit()

    # ---------- огород ----------
    async def get_garden(self, chat_id: int, user_id: int) -> dict | None:
        cur = await self.conn.execute(
            "SELECT data FROM garden WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        r = await cur.fetchone()
        return json.loads(r["data"]) if r else None

    async def save_garden(self, chat_id: int, user_id: int, data: dict) -> None:
        await self.conn.execute(
            "INSERT INTO garden VALUES(?,?,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET data=excluded.data",
            (chat_id, user_id, json.dumps(data)))
        await self.conn.commit()

    # ---------- модерация ----------
    async def add_warn(self, chat_id: int, user_id: int, now: int | None = None, ttl: int | None = None,
                       reason: str = "", actor: int = 0) -> int:
        """Новое предупреждение; ttl — секунды жизни (None — бессрочно). Возвращает число активных."""
        now = int(time.time()) if now is None else now
        await self.conn.execute(
            "INSERT INTO warn_events(chat_id,user_id,ts,expires_at,reason,actor) VALUES(?,?,?,?,?,?)",
            (chat_id, user_id, now, None if ttl is None else now + ttl, reason, actor))
        await self.conn.commit()
        return await self.get_warns(chat_id, user_id, now)

    async def remove_warn(self, chat_id: int, user_id: int, now: int | None = None) -> int:
        """Снимает самое свежее активное предупреждение (событие остаётся в истории с моментом снятия)."""
        now = int(time.time()) if now is None else now
        await self.conn.execute(
            "UPDATE warn_events SET expires_at=? WHERE id=(SELECT MAX(id) FROM warn_events WHERE chat_id=? "
            "AND user_id=? AND (expires_at IS NULL OR expires_at>?))", (now, chat_id, user_id, now))
        await self.conn.commit()
        return await self.get_warns(chat_id, user_id, now)

    async def remove_ai_warn(self, chat_id: int, user_id: int, actor: int, marker: str, now: int) -> bool:
        """Снять только активное предупреждение конкретного сообщения ИИ."""
        cur = await self.conn.execute(
            "UPDATE warn_events SET expires_at=? WHERE id=(SELECT MAX(id) FROM warn_events "
            "WHERE chat_id=? AND user_id=? AND actor=? AND reason LIKE ? "
            "AND (expires_at IS NULL OR expires_at>?))", (now, chat_id, user_id, actor, "%" + marker, now))
        await self.conn.commit()
        return cur.rowcount == 1

    async def reset_warns(self, chat_id: int, user_id: int, now: int | None = None) -> None:
        now = int(time.time()) if now is None else now
        await self.conn.execute(
            "UPDATE warn_events SET expires_at=? WHERE chat_id=? AND user_id=? AND (expires_at IS NULL OR expires_at>?)",
            (now, chat_id, user_id, now))
        await self.conn.commit()

    async def get_warns(self, chat_id: int, user_id: int, now: int | None = None) -> int:
        now = int(time.time()) if now is None else now
        cur = await self.conn.execute(
            "SELECT COUNT(*) AS n FROM warn_events WHERE chat_id=? AND user_id=? AND (expires_at IS NULL OR expires_at>?)",
            (chat_id, user_id, now))
        return (await cur.fetchone())["n"]

    async def migrate_legacy_warns(self, now: int | None = None) -> None:
        """Старая таблица warns(n) → n бессрочных событий (однократно: после переноса строки удаляются)."""
        now = int(time.time()) if now is None else now
        cur = await self.conn.execute("SELECT chat_id, user_id, n FROM warns WHERE n>0")
        for r in await cur.fetchall():
            for _ in range(r["n"]):
                await self.conn.execute(
                    "INSERT INTO warn_events(chat_id,user_id,ts,expires_at,reason,actor) VALUES(?,?,?,NULL,?,0)",
                    (r["chat_id"], r["user_id"], now, "перенесено из старой версии"))
        await self.conn.execute("DELETE FROM warns")
        await self.conn.commit()

    async def log_action(
        self, chat_id: int, actor_id: int, target_id: int, action: str, reason: str, ts: int,
        duration: int | None = None,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO mod_log(chat_id,actor_id,target_id,action,reason,ts,duration) VALUES(?,?,?,?,?,?,?)",
            (chat_id, actor_id, target_id, action, reason, ts, duration),
        )
        await self.conn.commit()
        if self.auditor is not None:
            self.auditor.action_fire_and_forget(chat_id, actor_id, target_id, action, reason, ts, duration)

    # ---------- фильтры слов и белый список ссылок ----------
    def lists_version(self, chat_id: int) -> int:
        return self._lists_version.get(chat_id, 0)

    def _bump(self, chat_id: int) -> None:
        self._lists_version[chat_id] = self._lists_version.get(chat_id, 0) + 1

    async def add_filter(self, chat_id: int, kind: str, pattern: str, created_by: int, ts: int,
                         limit: int = 50) -> int | None:
        cur = await self.conn.execute("SELECT kind, pattern FROM filters WHERE chat_id=?", (chat_id,))
        rows = await cur.fetchall()
        if len(rows) >= limit or any(r["kind"] == kind and r["pattern"] == pattern for r in rows):
            return None
        cur = await self.conn.execute(
            "INSERT INTO filters(chat_id,kind,pattern,action,created_by,ts) VALUES(?,?,?,'',?,?)",
            (chat_id, kind, pattern, created_by, ts))
        await self.conn.commit()
        self._bump(chat_id)
        return cur.lastrowid

    async def list_filters(self, chat_id: int) -> list[dict]:
        cur = await self.conn.execute("SELECT * FROM filters WHERE chat_id=? ORDER BY id", (chat_id,))
        return [dict(r) for r in await cur.fetchall()]

    async def delete_filter(self, chat_id: int, filter_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM filters WHERE chat_id=? AND id=?", (chat_id, filter_id))
        await self.conn.commit()
        if cur.rowcount == 1:
            self._bump(chat_id)
        return cur.rowcount == 1

    async def add_link(self, chat_id: int, domain: str, created_by: int) -> bool:
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO link_allow(chat_id,domain,created_by) VALUES(?,?,?)", (chat_id, domain, created_by))
        await self.conn.commit()
        if cur.rowcount == 1:
            self._bump(chat_id)
        return cur.rowcount == 1

    async def remove_link(self, chat_id: int, domain: str) -> bool:
        cur = await self.conn.execute("DELETE FROM link_allow WHERE chat_id=? AND domain=?", (chat_id, domain))
        await self.conn.commit()
        if cur.rowcount == 1:
            self._bump(chat_id)
        return cur.rowcount == 1

    async def link_allow_set(self, chat_id: int) -> set[str]:
        cur = await self.conn.execute("SELECT domain FROM link_allow WHERE chat_id=?", (chat_id,))
        return {r["domain"] for r in await cur.fetchall()}

    # ---------- триггеры, доверенные, блок стикеров, FAQ, повторы, сетка ----------
    async def add_trigger(self, chat_id: int, event: str, action: str, secs: int, reason: str, by: int, ts: int) -> int:
        cur = await self.conn.execute(
            "INSERT INTO triggers(chat_id,event,action,secs,reason,created_by,ts) VALUES(?,?,?,?,?,?,?)",
            (chat_id, event, action, secs, reason, by, ts))
        await self.conn.commit()
        return cur.lastrowid

    async def list_triggers(self, chat_id: int) -> list[dict]:
        cur = await self.conn.execute("SELECT * FROM triggers WHERE chat_id=? ORDER BY id", (chat_id,))
        return [dict(r) for r in await cur.fetchall()]

    async def count_triggers(self, chat_id: int, event: str) -> int:
        cur = await self.conn.execute("SELECT COUNT(*) AS n FROM triggers WHERE chat_id=? AND event=?", (chat_id, event))
        return (await cur.fetchone())["n"]

    async def del_trigger(self, chat_id: int, key: str) -> int:
        """key — номер триггера или название события (удалит все его триггеры)."""
        if key.isdigit():
            cur = await self.conn.execute("DELETE FROM triggers WHERE chat_id=? AND id=?", (chat_id, int(key)))
        else:
            cur = await self.conn.execute("DELETE FROM triggers WHERE chat_id=? AND event=?", (chat_id, key))
        await self.conn.commit()
        return cur.rowcount

    async def add_trusted(self, chat_id: int, user_id: int, by: int, ts: int) -> bool:
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO trusted(chat_id,user_id,added_by,ts) VALUES(?,?,?,?)", (chat_id, user_id, by, ts))
        await self.conn.commit()
        return cur.rowcount == 1

    async def remove_trusted(self, chat_id: int, user_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM trusted WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await self.conn.commit()
        return cur.rowcount == 1

    async def is_trusted(self, chat_id: int, user_id: int) -> bool:
        cur = await self.conn.execute("SELECT 1 AS x FROM trusted WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        return await cur.fetchone() is not None

    async def list_trusted(self, chat_id: int) -> list[int]:
        cur = await self.conn.execute("SELECT user_id FROM trusted WHERE chat_id=? ORDER BY ts", (chat_id,))
        return [r["user_id"] for r in await cur.fetchall()]

    async def block_sticker(self, chat_id: int, kind: str, key: str) -> bool:
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO sticker_block(chat_id,kind,key) VALUES(?,?,?)", (chat_id, kind, key))
        await self.conn.commit()
        return cur.rowcount == 1

    async def unblock_sticker(self, chat_id: int, kind: str, key: str) -> bool:
        cur = await self.conn.execute("DELETE FROM sticker_block WHERE chat_id=? AND kind=? AND key=?", (chat_id, kind, key))
        await self.conn.commit()
        return cur.rowcount == 1

    async def blocked_stickers(self, chat_id: int) -> set[tuple[str, str]]:
        cur = await self.conn.execute("SELECT kind, key FROM sticker_block WHERE chat_id=?", (chat_id,))
        return {(r["kind"], r["key"]) for r in await cur.fetchall()}

    async def add_faq(self, chat_id: int, keyword: str, answer: str, by: int, ts: int) -> int:
        cur = await self.conn.execute(
            "INSERT INTO faq(chat_id,keyword,answer,created_by,ts) VALUES(?,?,?,?,?)", (chat_id, keyword, answer, by, ts))
        await self.conn.commit()
        return cur.lastrowid

    async def list_faq(self, chat_id: int) -> list[dict]:
        cur = await self.conn.execute("SELECT * FROM faq WHERE chat_id=? ORDER BY id", (chat_id,))
        return [dict(r) for r in await cur.fetchall()]

    async def del_faq(self, chat_id: int, faq_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM faq WHERE chat_id=? AND id=?", (chat_id, faq_id))
        await self.conn.commit()
        return cur.rowcount == 1

    async def add_periodic(self, chat_id: int, every: int, text: str, by: int, now: int) -> int:
        cur = await self.conn.execute(
            "INSERT INTO periodic(chat_id,every,text,last_sent,created_by) VALUES(?,?,?,?,?)", (chat_id, every, text, now, by))
        await self.conn.commit()
        return cur.lastrowid

    async def list_periodic(self, chat_id: int | None = None) -> list[dict]:
        if chat_id is None:
            cur = await self.conn.execute("SELECT * FROM periodic ORDER BY id")
        else:
            cur = await self.conn.execute("SELECT * FROM periodic WHERE chat_id=? ORDER BY id", (chat_id,))
        return [dict(r) for r in await cur.fetchall()]

    async def del_periodic(self, chat_id: int, pid: int) -> bool:
        cur = await self.conn.execute("DELETE FROM periodic WHERE chat_id=? AND id=?", (chat_id, pid))
        await self.conn.commit()
        return cur.rowcount == 1

    async def touch_periodic(self, pid: int, now: int) -> None:
        await self.conn.execute("UPDATE periodic SET last_sent=? WHERE id=?", (now, pid))
        await self.conn.commit()

    async def grid_add(self, chat_id: int, owner_id: int, ts: int) -> None:
        await self.conn.execute("DELETE FROM grid_chats WHERE chat_id=?", (chat_id,))
        await self.conn.execute("INSERT INTO grid_chats(chat_id,owner_id,ts) VALUES(?,?,?)", (chat_id, owner_id, ts))
        await self.conn.commit()

    async def grid_remove(self, chat_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM grid_chats WHERE chat_id=?", (chat_id,))
        await self.conn.commit()
        return cur.rowcount == 1

    async def grid_owner(self, chat_id: int) -> int | None:
        cur = await self.conn.execute("SELECT owner_id FROM grid_chats WHERE chat_id=?", (chat_id,))
        r = await cur.fetchone()
        return r["owner_id"] if r else None

    async def grid_chats(self, owner_id: int) -> list[int]:
        cur = await self.conn.execute("SELECT chat_id FROM grid_chats WHERE owner_id=? ORDER BY ts", (owner_id,))
        return [r["chat_id"] for r in await cur.fetchall()]

    async def night_chats(self) -> list[int]:
        cur = await self.conn.execute("SELECT chat_id FROM settings WHERE key='night_on' AND value='1'")
        return [r["chat_id"] for r in await cur.fetchall()]

    # ---------- ИИ-модерация ----------
    async def add_aimod_event(self, chat_id: int, user_id: int, message_id: int | None, category: str,
                              confidence: int, action: str, text: str, ts: int) -> int:
        cur = await self.conn.execute(
            "INSERT INTO aimod_events(chat_id,user_id,message_id,category,confidence,action,text,status,ts) "
            "VALUES(?,?,?,?,?,?,?,'open',?)",
            (chat_id, user_id, message_id, category, confidence, action, text[:300], ts))
        await self.conn.commit()
        return cur.lastrowid

    async def get_aimod_event(self, event_id: int) -> dict | None:
        cur = await self.conn.execute("SELECT * FROM aimod_events WHERE id=?", (event_id,))
        r = await cur.fetchone()
        return dict(r) if r else None

    async def mark_aimod_false(self, event_id: int, by: int) -> bool:
        cur = await self.conn.execute(
            "UPDATE aimod_events SET status='false', handled_by=? WHERE id=? AND status='open'", (by, event_id))
        await self.conn.commit()
        return cur.rowcount == 1

    async def aimod_stats(self, chat_id: int, since: int) -> tuple[int, int]:
        """(срабатываний с момента since, из них отмеченных модераторами как ошибка)."""
        cur = await self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN status='false' THEN 1 ELSE 0 END), 0) AS f "
            "FROM aimod_events WHERE chat_id=? AND ts>=?", (chat_id, since))
        r = await cur.fetchone()
        return int(r["n"]), int(r["f"])

    # ---------- жалобы ----------
    async def add_report(self, chat_id: int, reporter: int, target: int, message_id: int | None, text: str,
                         reason: str, ts: int) -> int:
        cur = await self.conn.execute(
            "INSERT INTO reports(chat_id,reporter,target,message_id,text,reason,status,ts) VALUES(?,?,?,?,?,?,'open',?)",
            (chat_id, reporter, target, message_id, text, reason, ts))
        await self.conn.commit()
        return cur.lastrowid

    async def get_report(self, report_id: int) -> dict | None:
        cur = await self.conn.execute("SELECT * FROM reports WHERE id=?", (report_id,))
        r = await cur.fetchone()
        return dict(r) if r else None

    async def report_exists(self, chat_id: int, message_id: int | None) -> bool:
        if message_id is None:
            return False
        cur = await self.conn.execute("SELECT 1 FROM reports WHERE chat_id=? AND message_id=?", (chat_id, message_id))
        return await cur.fetchone() is not None

    async def claim_report(self, report_id: int, status: str, by: int) -> bool:
        """Взять открытую жалобу в обработку (только один модератор, только один раз)."""
        cur = await self.conn.execute(
            "UPDATE reports SET status=?, handled_by=? WHERE id=? AND status='open'", (status, by, report_id))
        await self.conn.commit()
        return cur.rowcount == 1

    async def reopen_report(self, report_id: int) -> None:
        await self.conn.execute("UPDATE reports SET status='open', handled_by=NULL WHERE id=?", (report_id,))
        await self.conn.commit()

    async def list_reports(self, chat_id: int, limit: int = 50) -> list[dict]:
        cur = await self.conn.execute("SELECT * FROM reports WHERE chat_id=? ORDER BY id DESC LIMIT ?", (chat_id, limit))
        return [dict(r) for r in await cur.fetchall()]

    async def count_rejected_reports(self, chat_id: int, reporter: int) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) AS n FROM reports WHERE chat_id=? AND reporter=? AND status='dismissed'",
            (chat_id, reporter))
        return (await cur.fetchone())["n"]

    async def count_reports_against(self, chat_id: int, target: int) -> tuple[int, int]:
        """(всего жалоб на участника, из них открытых)."""
        cur = await self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN status='open' THEN 1 ELSE 0 END), 0) AS o "
            "FROM reports WHERE chat_id=? AND target=?", (chat_id, target))
        r = await cur.fetchone()
        return int(r["n"]), int(r["o"])

    async def count_mod_history(self, chat_id: int, target_id: int) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) AS n FROM mod_log WHERE chat_id=? AND target_id=?", (chat_id, target_id))
        return (await cur.fetchone())["n"]

    async def list_mod_history(self, chat_id: int, target_id: int, limit: int = 10, offset: int = 0) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT * FROM mod_log WHERE chat_id=? AND target_id=? ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?",
            (chat_id, target_id, limit, offset))
        return [dict(r) for r in await cur.fetchall()]

    # ---------- ранги, доступ команд, активные наказания ----------
    HOT_TTL = 30.0

    def _hot_put(self, cache: dict, key, value) -> None:
        if len(cache) > 20000:
            cache.clear()
        cache[key] = (self._clock(), value)

    async def get_rank(self, chat_id: int, user_id: int) -> int:
        """Читается на каждое сообщение (антиспам) — короткий кэш; set_rank его сбрасывает."""
        hit = self._rank_cache.get((chat_id, user_id))
        if hit and self._clock() - hit[0] < self.HOT_TTL:
            return hit[1]
        cur = await self.conn.execute("SELECT rank FROM ranks WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        r = await cur.fetchone()
        val = r["rank"] if r else 0
        self._hot_put(self._rank_cache, (chat_id, user_id), val)
        return val

    async def set_rank(self, chat_id: int, user_id: int, rank: int, by_user: int, ts: int) -> None:
        old = await self.get_rank(chat_id, user_id)
        self._rank_cache.pop((chat_id, user_id), None)
        if old != max(rank, 0):                          # журнал рангов: «модер лог»
            await self.conn.execute(
                "INSERT INTO mod_log(chat_id,actor_id,target_id,action,reason,ts) VALUES(?,?,?,?,?,?)",
                (chat_id, by_user, user_id, "ранг", f"{old} → {max(rank, 0)}", ts))
        if rank <= 0:
            await self.conn.execute("DELETE FROM ranks WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        else:
            await self.conn.execute(
                "INSERT INTO ranks VALUES(?,?,?,?,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET "
                "rank=excluded.rank, by_user=excluded.by_user, ts=excluded.ts", (chat_id, user_id, rank, by_user, ts))
        await self.conn.commit()

    async def list_log_actions(self, chat_id: int, actions: tuple[str, ...], limit: int = 20) -> list[dict]:
        marks = ",".join("?" for _ in actions)
        cur = await self.conn.execute(
            f"SELECT actor_id, target_id, action, reason, ts FROM mod_log WHERE chat_id=? AND action IN ({marks}) "
            "ORDER BY id DESC LIMIT ?", (chat_id, *actions, limit))
        return [dict(r) for r in await cur.fetchall()]

    async def list_ranks(self, chat_id: int) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT * FROM ranks WHERE chat_id=? ORDER BY rank DESC, ts", (chat_id,))
        return [dict(r) for r in await cur.fetchall()]

    async def get_access(self, chat_id: int) -> dict[str, int]:
        """Читается при каждой команде модерации — короткий кэш; set_access/reset_access его сбрасывают."""
        hit = self._access_cache.get(chat_id)
        if hit and self._clock() - hit[0] < self.HOT_TTL:
            return dict(hit[1])
        cur = await self.conn.execute("SELECT command, min_rank FROM cmd_access WHERE chat_id=?", (chat_id,))
        out = {r["command"]: r["min_rank"] for r in await cur.fetchall()}
        self._hot_put(self._access_cache, chat_id, out)
        return dict(out)

    async def set_access(self, chat_id: int, command: str, min_rank: int) -> None:
        self._access_cache.pop(chat_id, None)
        await self.conn.execute(
            "INSERT INTO cmd_access VALUES(?,?,?) ON CONFLICT(chat_id,command) DO UPDATE SET min_rank=excluded.min_rank",
            (chat_id, command, min_rank))
        await self.conn.commit()

    async def reset_access(self, chat_id: int) -> None:
        self._access_cache.pop(chat_id, None)
        await self.conn.execute("DELETE FROM cmd_access WHERE chat_id=?", (chat_id,))
        await self.conn.commit()

    async def set_state(self, chat_id: int, user_id: int, kind: str, until: int | None, reason: str,
                        actor: int, ts: int) -> None:
        await self.conn.execute(
            "INSERT INTO mod_state VALUES(?,?,?,?,?,?,?) ON CONFLICT(chat_id,user_id,kind) DO UPDATE SET "
            "until=excluded.until, reason=excluded.reason, actor=excluded.actor, ts=excluded.ts",
            (chat_id, user_id, kind, until, reason, actor, ts))
        await self.conn.commit()

    async def clear_state(self, chat_id: int, user_id: int, kind: str) -> None:
        await self.conn.execute(
            "DELETE FROM mod_state WHERE chat_id=? AND user_id=? AND kind=?", (chat_id, user_id, kind))
        await self.conn.commit()

    # ---------- отложенные баны: ник, которого бот ещё не знает ----------
    async def load_pending_names(self) -> None:
        cur = await self.conn.execute("SELECT DISTINCT username FROM pending_bans")
        self._pending_names = {r["username"] for r in await cur.fetchall()}

    def has_pending(self, username: str | None) -> bool:
        return bool(username) and username.lstrip("@").lower() in self._pending_names

    async def add_pending_ban(self, chat_id: int, username: str, duration: int | None, reason: str,
                              actor: int, now: int, forced: bool = False) -> None:
        """forced — бан поставил владелец бота: права по рангам при исполнении не проверяются."""
        name = username.lstrip("@").lower()
        await self.conn.execute(
            "INSERT INTO pending_bans(chat_id,username,duration,reason,actor,ts,forced) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(chat_id,username) DO UPDATE SET duration=excluded.duration, reason=excluded.reason, "
            "actor=excluded.actor, ts=excluded.ts, forced=excluded.forced",
            (chat_id, name, duration, reason, actor, now, 1 if forced else 0))
        await self.conn.commit()
        self._pending_names.add(name)

    async def list_pending_bans(self, chat_id: int, now: int) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT * FROM pending_bans WHERE chat_id=? AND ts>=? ORDER BY ts DESC", (chat_id, now - PENDING_BAN_TTL))
        return [dict(r) for r in await cur.fetchall()]

    async def remove_pending_ban(self, chat_id: int, username: str) -> bool:
        name = username.lstrip("@").lower()
        cur = await self.conn.execute("DELETE FROM pending_bans WHERE chat_id=? AND username=?", (chat_id, name))
        await self.conn.commit()
        await self.load_pending_names()
        return cur.rowcount == 1

    async def pop_pending_bans(self, username: str, now: int) -> list[dict]:
        """Забрать (и удалить) все неисполненные баны по этому нику — вызывается, когда бот впервые увидел человека."""
        name = username.lstrip("@").lower()
        cur = await self.conn.execute(
            "SELECT * FROM pending_bans WHERE username=? AND ts>=?", (name, now - PENDING_BAN_TTL))
        rows = [dict(r) for r in await cur.fetchall()]
        await self.conn.execute("DELETE FROM pending_bans WHERE username=?", (name,))
        await self.conn.commit()
        self._pending_names.discard(name)
        return rows

    async def last_mod_action(self, chat_id: int, names: tuple[str, ...], target_id: int | None = None) -> dict | None:
        """Последнее действие модерации из names (по журналу); target_id=None — по всему чату."""
        marks = ",".join("?" for _ in names)
        sql = f"SELECT * FROM mod_log WHERE chat_id=? AND action IN ({marks})"
        args: list = [chat_id, *names]
        if target_id is not None:
            sql += " AND target_id=?"
            args.append(target_id)
        cur = await self.conn.execute(sql + " ORDER BY id DESC LIMIT 1", tuple(args))
        r = await cur.fetchone()
        return dict(r) if r else None

    async def list_state(self, chat_id: int, kind: str, now: int) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT * FROM mod_state WHERE chat_id=? AND kind=? AND (until IS NULL OR until>?) ORDER BY ts DESC",
            (chat_id, kind, now))
        return [dict(r) for r in await cur.fetchall()]

    # ---------- исключения из проверки CAS ----------
    async def cas_allow(self, chat_id: int, user_id: int) -> None:
        await self.conn.execute("INSERT OR IGNORE INTO cas_allow(chat_id,user_id) VALUES(?,?)", (chat_id, user_id))
        await self.conn.commit()

    async def cas_allowed(self, chat_id: int, user_id: int) -> bool:
        cur = await self.conn.execute("SELECT 1 FROM cas_allow WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        return await cur.fetchone() is not None

    # ---------- заявки через бота-стража ----------
    async def guard_query_set(self, chat_id: int, user_id: int, query_id: str, ts: int) -> None:
        await self.conn.execute(
            "INSERT INTO guard_queries(chat_id,user_id,query_id,ts) VALUES(?,?,?,?) ON CONFLICT(chat_id,user_id) "
            "DO UPDATE SET query_id=excluded.query_id, ts=excluded.ts", (chat_id, user_id, query_id, ts))
        await self.conn.commit()

    async def guard_query_pop(self, chat_id: int, user_id: int) -> str | None:
        cur = await self.conn.execute("SELECT query_id FROM guard_queries WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        r = await cur.fetchone()
        if r is None:
            return None
        await self.conn.execute("DELETE FROM guard_queries WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        await self.conn.commit()
        return r["query_id"]

    # ---------- гостевые боты ----------
    # status: 0 — замечен, 1 — разрешён, 2 — запрещён
    async def guest_seen(self, chat_id: int, bot_id: int, username: str | None, now: int) -> int:
        """Запоминает гостевого бота и возвращает его статус (0 — новый/замечен)."""
        key = (chat_id, bot_id)
        hit = self._guest_cache.get(key)
        if hit is not None and now - hit[1] < 600:
            return hit[0]
        cur = await self.conn.execute("SELECT status FROM guest_bots WHERE chat_id=? AND bot_id=?", key)
        r = await cur.fetchone()
        status = r["status"] if r else 0
        if r is None or hit is None:
            await self.conn.execute(
                "INSERT INTO guest_bots(chat_id,bot_id,username,status,last_seen) VALUES(?,?,?,0,?) ON CONFLICT(chat_id,bot_id) "
                "DO UPDATE SET username=COALESCE(excluded.username, guest_bots.username), last_seen=excluded.last_seen",
                (chat_id, bot_id, username, now))
            await self.conn.commit()
        if len(self._guest_cache) > 5000:
            self._guest_cache.clear()
        self._guest_cache[key] = (status, now)
        return status

    async def guest_set_status(self, chat_id: int, bot_id: int, username: str | None, status: int, now: int) -> None:
        await self.conn.execute(
            "INSERT INTO guest_bots(chat_id,bot_id,username,status,last_seen) VALUES(?,?,?,?,?) ON CONFLICT(chat_id,bot_id) "
            "DO UPDATE SET status=excluded.status, username=COALESCE(excluded.username, guest_bots.username)",
            (chat_id, bot_id, username, status, now))
        await self.conn.commit()
        self._guest_cache[(chat_id, bot_id)] = (status, now)

    async def guest_list(self, chat_id: int, limit: int = 30) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT bot_id, username, status, last_seen FROM guest_bots WHERE chat_id=? ORDER BY last_seen DESC LIMIT ?",
            (chat_id, limit))
        return [dict(r) for r in await cur.fetchall()]

    async def avatar_hash_get(self, user_id: int) -> int | None:
        cur = await self.conn.execute("SELECT hash FROM avatar_hash WHERE user_id=?", (user_id,))
        r = await cur.fetchone()
        return int(r["hash"], 16) if r and r["hash"] else None

    async def avatar_hash_set(self, user_id: int, h: int, ts: int) -> None:
        await self.conn.execute(
            "INSERT INTO avatar_hash(user_id,hash,ts) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET hash=excluded.hash, ts=excluded.ts",
            (user_id, f"{h:016x}", ts))
        await self.conn.commit()

    async def avatar_hashes(self, user_ids: list[int]) -> dict[int, int]:
        if not user_ids:
            return {}
        out: dict[int, int] = {}
        for i in range(0, len(user_ids), 200):
            chunk = user_ids[i:i + 200]
            cur = await self.conn.execute(
                f"SELECT user_id, hash FROM avatar_hash WHERE user_id IN ({','.join('?' * len(chunk))})", tuple(chunk))
            out.update({r["user_id"]: int(r["hash"], 16) for r in await cur.fetchall() if r["hash"]})
        return out

    async def banned_ids(self, chat_id: int, since: int, limit: int = 300) -> list[int]:
        """Кого в этом чате банили после since (самые свежие первыми)."""
        cur = await self.conn.execute(
            "SELECT target_id, MAX(ts) AS t FROM mod_log WHERE chat_id=? AND action='бан' AND ts>=? AND target_id IS NOT NULL "
            "GROUP BY target_id ORDER BY t DESC LIMIT ?", (chat_id, since, limit))
        return [r["target_id"] for r in await cur.fetchall()]

    async def get_state(self, chat_id: int, user_id: int, kind: str, now: int) -> dict | None:
        cur = await self.conn.execute(
            "SELECT * FROM mod_state WHERE chat_id=? AND user_id=? AND kind=? AND (until IS NULL OR until>?)",
            (chat_id, user_id, kind, now))
        r = await cur.fetchone()
        return dict(r) if r else None

    async def list_warns(self, chat_id: int, now: int | None = None) -> list[tuple[int, int]]:
        now = int(time.time()) if now is None else now
        cur = await self.conn.execute(
            "SELECT user_id, COUNT(*) AS n FROM warn_events WHERE chat_id=? AND (expires_at IS NULL OR expires_at>?) "
            "GROUP BY user_id ORDER BY n DESC, user_id", (chat_id, now))
        return [(r["user_id"], r["n"]) for r in await cur.fetchall()]

    async def members_info(self, chat_id: int) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT user_id, first_seen, last_seen, joined_at FROM chat_members WHERE chat_id=? AND active=1",
            (chat_id,))
        return [dict(r) for r in await cur.fetchall()]

    async def last_messages(self, chat_id: int) -> dict[int, int]:
        """user_id -> время последнего сообщения (с точностью до часа; по счётчикам). Нет в словаре — ни разу не писал."""
        await self.flush_messages()
        cur = await self.conn.execute(
            "SELECT user_id, MAX(t) AS t FROM ("
            " SELECT user_id, MAX(hour_ts) AS t FROM msg_hourly WHERE chat_id=? GROUP BY user_id"
            " UNION ALL"
            " SELECT user_id, MAX(day_ts) AS t FROM msg_daily WHERE chat_id=? GROUP BY user_id) x GROUP BY user_id",
            (chat_id, chat_id))
        return {r["user_id"]: r["t"] for r in await cur.fetchall()}

    async def writers(self, chat_id: int) -> set[int]:
        await self.flush_messages()
        cur = await self.conn.execute(
            "SELECT DISTINCT user_id FROM msg_hourly WHERE chat_id=? UNION SELECT DISTINCT user_id FROM msg_daily WHERE chat_id=?",
            (chat_id, chat_id))
        return {r["user_id"] for r in await cur.fetchall()}

    # ---------- тексты чата, профили, репутация, награды, заметки, таймеры ----------
    async def get_text(self, chat_id: int, key: str) -> str | None:
        cur = await self.conn.execute("SELECT text FROM chat_texts WHERE chat_id=? AND key=?", (chat_id, key))
        r = await cur.fetchone()
        return r["text"] if r else None

    async def set_text(self, chat_id: int, key: str, text: str | None) -> None:
        if text is None:
            await self.conn.execute("DELETE FROM chat_texts WHERE chat_id=? AND key=?", (chat_id, key))
        else:
            await self.conn.execute(
                "INSERT INTO chat_texts VALUES(?,?,?) ON CONFLICT(chat_id,key) DO UPDATE SET text=excluded.text",
                (chat_id, key, text))
        await self.conn.commit()

    async def get_profile(self, chat_id: int, user_id: int) -> dict:
        cur = await self.conn.execute("SELECT * FROM profiles WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        r = await cur.fetchone()
        return dict(r) if r else {"nick": None, "title": None, "motto": None, "about": None}

    async def set_profile_field(self, chat_id: int, user_id: int, field: str, value: str | None) -> None:
        if field not in ("nick", "title", "motto", "about"):
            raise KeyError(field)
        await self.conn.execute("INSERT OR IGNORE INTO profiles(chat_id,user_id) VALUES(?,?)", (chat_id, user_id))
        await self.conn.execute(f"UPDATE profiles SET {field}=? WHERE chat_id=? AND user_id=?",
                                (value, chat_id, user_id))
        await self.conn.commit()

    async def get_rep(self, chat_id: int, user_id: int) -> int:
        cur = await self.conn.execute("SELECT score FROM reputation WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        r = await cur.fetchone()
        return r["score"] if r else 0

    async def change_rep(self, chat_id: int, from_user: int, to_user: int, delta: int, now: int,
                         cooldown: int = 3600) -> int | None:
        """Новая репутация или None, если этот человек уже менял её цели в последний `cooldown` (атомарно)."""
        cur = await self.conn.execute(
            "INSERT INTO rep_log SELECT CAST(? AS BIGINT),CAST(? AS BIGINT),CAST(? AS BIGINT),CAST(? AS BIGINT) WHERE NOT EXISTS ("
            "SELECT 1 FROM rep_log WHERE chat_id=? AND from_user=? AND to_user=? AND ts>?)",
            (chat_id, from_user, to_user, now, chat_id, from_user, to_user, now - cooldown))
        if cur.rowcount != 1:
            await self.conn.commit()
            return None
        await self.conn.execute(
            "INSERT INTO reputation VALUES(?,?,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET score=reputation.score+?",
            (chat_id, to_user, delta, delta))
        await self.conn.commit()
        return await self.get_rep(chat_id, to_user)

    async def top_rep(self, chat_id: int, limit: int = 10) -> list[tuple[int, int]]:
        cur = await self.conn.execute(
            "SELECT user_id, score FROM reputation WHERE chat_id=? AND score<>0 ORDER BY score DESC, user_id LIMIT ?",
            (chat_id, limit))
        return [(r["user_id"], r["score"]) for r in await cur.fetchall()]

    async def add_award(self, chat_id: int, user_id: int, degree: int, by_user: int, ts: int) -> None:
        await self.conn.execute("INSERT INTO awards(chat_id,user_id,degree,by_user,ts) VALUES(?,?,?,?,?)",
                                (chat_id, user_id, degree, by_user, ts))
        await self.conn.commit()

    async def list_awards(self, chat_id: int, user_id: int) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT * FROM awards WHERE chat_id=? AND user_id=? ORDER BY id", (chat_id, user_id))
        return [dict(r) for r in await cur.fetchall()]

    async def remove_last_award(self, chat_id: int, user_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM awards WHERE id=(SELECT MAX(id) FROM awards WHERE chat_id=? AND user_id=?)", (chat_id, user_id))
        await self.conn.commit()
        return cur.rowcount == 1

    async def add_note(self, chat_id: int, user_id: int, kind: str, text: str, ts: int, limit: int = 20) -> bool:
        cur = await self.conn.execute(
            "SELECT COUNT(*) FROM notes WHERE chat_id=? AND user_id=? AND kind=?", (chat_id, user_id, kind))
        if (await cur.fetchone())[0] >= limit:
            return False
        await self.conn.execute("INSERT INTO notes(chat_id,user_id,kind,text,ts) VALUES(?,?,?,?,?)",
                                (chat_id, user_id, kind, text, ts))
        await self.conn.commit()
        return True

    async def list_notes(self, chat_id: int, user_id: int, kind: str) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT * FROM notes WHERE chat_id=? AND user_id=? AND kind=? ORDER BY id", (chat_id, user_id, kind))
        return [dict(r) for r in await cur.fetchall()]

    async def delete_note(self, chat_id: int, user_id: int, kind: str, note_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM notes WHERE id=? AND chat_id=? AND user_id=? AND kind=?", (note_id, chat_id, user_id, kind))
        await self.conn.commit()
        return cur.rowcount == 1

    async def add_timer(self, chat_id: int, user_id: int, due: int, text: str, limit: int = 10) -> int | None:
        cur = await self.conn.execute("SELECT COUNT(*) FROM timers WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        if (await cur.fetchone())[0] >= limit:
            return None
        cur = await self.conn.execute("INSERT INTO timers(chat_id,user_id,due,text) VALUES(?,?,?,?)",
                                      (chat_id, user_id, due, text))
        await self.conn.commit()
        return cur.lastrowid

    async def list_timers(self, chat_id: int, user_id: int) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT * FROM timers WHERE chat_id=? AND user_id=? ORDER BY due", (chat_id, user_id))
        return [dict(r) for r in await cur.fetchall()]

    async def delete_timer(self, timer_id: int, user_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM timers WHERE id=? AND user_id=?", (timer_id, user_id))
        await self.conn.commit()
        return cur.rowcount == 1

    async def due_timers(self, now: int) -> list[dict]:
        cur = await self.conn.execute("SELECT * FROM timers WHERE due<=? ORDER BY due", (now,))
        return [dict(r) for r in await cur.fetchall()]

    async def pop_timer(self, timer_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM timers WHERE id=?", (timer_id,))
        await self.conn.commit()
        return cur.rowcount == 1

    async def oldest_members(self, chat_id: int, limit: int = 10) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT user_id, first_seen FROM chat_members WHERE chat_id=? AND active=1 ORDER BY first_seen LIMIT ?",
            (chat_id, limit))
        return [dict(r) for r in await cur.fetchall()]

    async def newest_members(self, chat_id: int, limit: int = 10) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT user_id, COALESCE(joined_at, first_seen) AS t FROM chat_members WHERE chat_id=? AND active=1 "
            "ORDER BY t DESC LIMIT ?", (chat_id, limit))
        return [dict(r) for r in await cur.fetchall()]

    async def online_members(self, chat_id: int, now: int, window: int = 600) -> list[int]:
        cur = await self.conn.execute(
            "SELECT user_id FROM chat_members WHERE chat_id=? AND active=1 AND last_seen>? ORDER BY last_seen DESC",
            (chat_id, now - window))
        return [r["user_id"] for r in await cur.fetchall()]

    # ---------- настройки ----------
    async def get_settings(self, chat_id: int) -> dict:
        hit = self._settings_cache.get(chat_id)
        if hit and self._clock() - hit[0] < self.SETTINGS_TTL:
            return dict(hit[1])
        self.settings_reads += 1
        cur = await self.conn.execute(
            "SELECT key, value FROM settings WHERE chat_id=?", (chat_id,)
        )
        out = dict(DEFAULT_SETTINGS)
        stored = set()
        for r in await cur.fetchall():
            stored.add(r["key"])
            default = DEFAULT_SETTINGS.get(r["key"])
            out[r["key"]] = int(r["value"]) if isinstance(default, int) else r["value"]
        if "links_mode" not in stored and str(out.get("spam_links", "1")) == "0":
            out["links_mode"] = "off"   # старая настройка «ссылки от новичков: выкл»
        self._settings_cache[chat_id] = (self._clock(), out)
        return dict(out)

    async def set_setting(self, chat_id: int, key: str, value, actor: int | None = None) -> None:
        if key not in DEFAULT_SETTINGS:
            raise KeyError(key)
        await self.conn.execute(
            "INSERT INTO settings VALUES(?,?,?) ON CONFLICT(chat_id,key) DO UPDATE SET value=excluded.value",
            (chat_id, key, str(value)),
        )
        await self.conn.commit()
        self._settings_cache.pop(chat_id, None)
        if actor is not None and self.auditor is not None and key != "log_chat_id":
            self.auditor.action_fire_and_forget(chat_id, actor, None, "настройка", f"{key} = {value}",
                                                int(time.time()), None)

    # ---------- экономика ----------
    async def _ensure_wallet(self, chat_id: int, user_id: int) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO wallets(chat_id,user_id,balance) VALUES(?,?,?)",
            (chat_id, user_id, START_BALANCE),
        )

    async def get_balance(self, chat_id: int, user_id: int) -> int:
        cur = await self.conn.execute(
            "SELECT balance FROM wallets WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
        r = await cur.fetchone()
        if r is not None:
            return r["balance"]                      # чтение не пишет в БД
        await self._ensure_wallet(chat_id, user_id)
        await self.conn.commit()
        return START_BALANCE

    async def change_balance(self, chat_id: int, user_id: int, delta: int) -> int:
        await self._ensure_wallet(chat_id, user_id)
        await self.conn.execute(
            "UPDATE wallets SET balance=balance+? WHERE chat_id=? AND user_id=?",
            (delta, chat_id, user_id),
        )
        await self.conn.commit()
        return await self.get_balance(chat_id, user_id)

    async def transfer(self, chat_id: int, src: int, dst: int, amount: int) -> bool:
        """Перевод монет одной транзакцией: либо списалось и зачислилось, либо ничего."""
        if type(amount) is not int or not 1 <= amount < 2**63 or src == dst:
            return False
        async with self.atomic():
            await self._ensure_wallet(chat_id, src)
            await self._ensure_wallet(chat_id, dst)
            cur = await self.conn.execute(
                "UPDATE wallets SET balance=balance-? WHERE chat_id=? AND user_id=? AND balance>=?",
                (amount, chat_id, src, amount))
            if cur.rowcount != 1:
                await self.conn.commit()
                return False
            await self.conn.execute(
                "UPDATE wallets SET balance=balance+? WHERE chat_id=? AND user_id=?", (amount, chat_id, dst))
            await self.conn.commit()
            return True

    async def try_spend(self, chat_id: int, user_id: int, amount: int) -> bool:
        """Атомарно списать amount, если хватает баланса."""
        if type(amount) is not int or not 1 <= amount < 2**63:
            return False
        await self._ensure_wallet(chat_id, user_id)
        cur = await self.conn.execute(
            "UPDATE wallets SET balance=balance-? WHERE chat_id=? AND user_id=? AND balance>=?",
            (amount, chat_id, user_id, amount),
        )
        await self.conn.commit()
        return cur.rowcount == 1

    async def claim_bonus(self, chat_id: int, user_id: int, now: int) -> int | None:
        await self._ensure_wallet(chat_id, user_id)
        day = now // DAY__db
        cur = await self.conn.execute(
            "UPDATE wallets SET balance=balance+?, last_bonus_day=? "
            "WHERE chat_id=? AND user_id=? AND last_bonus_day<?",
            (BONUS_AMOUNT, day, chat_id, user_id, day),
        )
        await self.conn.commit()
        return BONUS_AMOUNT if cur.rowcount == 1 else None

    async def top_balances(self, chat_id: int, limit: int = 10) -> list[tuple[int, int]]:
        cur = await self.conn.execute(
            "SELECT user_id, balance FROM wallets WHERE chat_id=? ORDER BY balance DESC LIMIT ?",
            (chat_id, limit),
        )
        return [(r["user_id"], r["balance"]) for r in await cur.fetchall()]

    async def add_win(self, chat_id: int, user_id: int) -> None:
        await self._ensure_wallet(chat_id, user_id)
        await self.conn.execute(
            "UPDATE wallets SET wins=wins+1 WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
        await self.conn.commit()

    async def top_wins(self, chat_id: int, limit: int = 10) -> list[tuple[int, int]]:
        cur = await self.conn.execute(
            "SELECT user_id, wins FROM wallets WHERE chat_id=? AND wins>0 "
            "ORDER BY wins DESC LIMIT ?",
            (chat_id, limit),
        )
        return [(r["user_id"], r["wins"]) for r in await cur.fetchall()]

    # ---------- Premium и платежи ----------
    async def premium_until(self, user_id: int) -> int | None:
        cur = await self.conn.execute("SELECT until FROM premium WHERE user_id=?", (user_id,))
        r = await cur.fetchone()
        return r["until"] if r else None

    async def premium_lock_until(self, user_id: int, now: int) -> int:
        """Read the previous entitlement while an outer transaction holds its row."""
        if not self._atomic_active or self._gate._owner is not asyncio.current_task():
            raise RuntimeError("premium_lock_until requires an atomic operation")
        await self.conn.execute("INSERT OR IGNORE INTO premium(user_id,until,since,payments) VALUES(?,0,?,0)", (user_id, now))
        suffix = " FOR UPDATE" if self.backend == "pg" else ""
        cur = await self.conn.execute("SELECT until FROM premium WHERE user_id=?" + suffix, (user_id,))
        return (await cur.fetchone())[0] or 0

    async def premium_grant(self, user_id: int, until: int, now: int) -> None:
        """Продлить до until (никогда не укорачивает уже оплаченное)."""
        await self.conn.execute(
            "INSERT INTO premium(user_id,until,since,payments) VALUES(?,?,?,1) ON CONFLICT(user_id) DO UPDATE SET "
            "until=CASE WHEN excluded.until>premium.until THEN excluded.until ELSE premium.until END, "
            "payments=premium.payments+1", (user_id, until, now))
        await self.conn.commit()

    async def premium_revoke(self, user_id: int) -> None:
        async with self.atomic():
            await self.conn.execute("DELETE FROM premium WHERE user_id=?", (user_id,))
            await self.conn.execute("UPDATE payment_effects SET until=-1 WHERE kind='user' AND target_id=?", (user_id,))

    async def payment_add(self, user_id: int, charge_id: str, amount: int, ts: int, recurring: bool) -> bool:
        """False — этот платёж уже записан (Telegram может прислать дубль)."""
        if not isinstance(charge_id, str) or not charge_id or type(amount) is not int or amount <= 0:
            raise ValueError("invalid payment receipt")
        async with self.atomic():
            cur = await self.conn.execute("INSERT OR IGNORE INTO payment_receipts(charge_id,ts) VALUES(?,?)", (charge_id, ts))
            if cur.rowcount != 1:
                return False
            await self.conn.execute("INSERT INTO payments(user_id,charge_id,amount,ts,recurring) VALUES(?,?,?,?,?)",
                                    (user_id, charge_id, amount, ts, 1 if recurring else 0))
            return True

    async def payment_effect(self, charge_id: str, kind: str, target_id: int, previous_until: int, until: int) -> None:
        if kind not in ("user", "pair"):
            raise ValueError("invalid payment effect")
        await self.conn.execute("INSERT INTO payment_effects VALUES(?,?,?,?,?)",
                                (charge_id, kind, target_id, previous_until, until))
        await self.conn.commit()

    async def payment_get_effect(self, charge_id: str) -> dict | None:
        cur = await self.conn.execute("SELECT * FROM payment_effects WHERE charge_id=?", (charge_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def payment_claim_refund(self, user_id: int) -> dict | None:
        """Resume a pending refund; otherwise pick the latest charge, including completed refunds."""
        async with self.atomic():
            cur = await self.conn.execute(
                "SELECT * FROM payments WHERE user_id=? "
                "ORDER BY CASE WHEN refunded=2 THEN 0 ELSE 1 END, id DESC LIMIT 1", (user_id,))
            row = await cur.fetchone()
            if row is None:
                return None
            payment = dict(row)
            if payment["refunded"] != 1:
                await self.conn.execute("UPDATE payments SET refunded=2 WHERE charge_id=? AND refunded<>1", (payment["charge_id"],))
                payment["refunded"] = 2
            return payment

    async def payment_finish_refund(self, payment_id: int, now: int) -> tuple[bool, str]:
        """Finalize once; restore the previous entitlement only when its state is unambiguous."""
        async with self.atomic():
            cur = await self.conn.execute("SELECT * FROM payments WHERE id=?", (payment_id,))
            payment = await cur.fetchone()
            if payment is None:
                return False, "unknown"
            cur = await self.conn.execute(
                "UPDATE payments SET refunded=1 WHERE charge_id=? AND refunded=2", (payment["charge_id"],))
            if cur.rowcount == 0:
                return False, "unknown"
            cur = await self.conn.execute("SELECT * FROM payment_effects WHERE charge_id=?", (payment["charge_id"],))
            effect = await cur.fetchone()
            if effect is None:
                return True, "unknown"
            # Lock the entitlement before checking newer effects: a concurrent new
            # subscription must not be erased even when both expirations coincide.
            if effect["kind"] == "user":
                await self.premium_lock_until(effect["target_id"], now)
            else:
                suffix = " FOR UPDATE" if self.backend == "pg" else ""
                await self.conn.execute("SELECT premium_until FROM pairs WHERE id=?" + suffix, (effect["target_id"],))
            cur = await self.conn.execute(
                "SELECT 1 FROM payment_effects e JOIN payments p ON p.charge_id=e.charge_id "
                "WHERE e.kind=? AND e.target_id=? AND p.id>? AND p.refunded<>1 LIMIT 1",
                (effect["kind"], effect["target_id"], payment["id"]))
            if await cur.fetchone():
                return True, effect["kind"] + "_manual"
            if effect["kind"] == "user":
                cur = await self.conn.execute(
                    "UPDATE premium SET until=? WHERE user_id=? AND until=?",
                    (effect["previous_until"], effect["target_id"], effect["until"]))
                if cur.rowcount == 0:
                    cur = await self.conn.execute("SELECT until FROM premium WHERE user_id=?", (effect["target_id"],))
                    current = await cur.fetchone()
                    if current and current[0] > now:
                        return True, "user_manual"
            else:
                cur = await self.conn.execute(
                    "UPDATE pairs SET premium_until=? WHERE id=? AND premium_until=?",
                    (effect["previous_until"], effect["target_id"], effect["until"]))
                if cur.rowcount == 0:
                    cur = await self.conn.execute("SELECT premium_until FROM pairs WHERE id=?", (effect["target_id"],))
                    current = await cur.fetchone()
                    if current and current[0] > now:
                        return True, "pair_manual"
            return True, effect["kind"]

    async def payment_last(self, user_id: int) -> dict | None:
        cur = await self.conn.execute(
            "SELECT * FROM payments WHERE user_id=? AND refunded=0 ORDER BY id DESC LIMIT 1", (user_id,))
        r = await cur.fetchone()
        return dict(r) if r else None

    async def payment_refunded(self, pid: int) -> None:
        await self.conn.execute("UPDATE payments SET refunded=1 WHERE id=?", (pid,))
        await self.conn.commit()

    async def premium_stats(self, now: int) -> tuple[int, int]:
        """(активных подписчиков, звёзд получено всего без возвратов)."""
        cur = await self.conn.execute("SELECT COUNT(*) AS n FROM premium WHERE until>?", (now,))
        active = (await cur.fetchone())["n"]
        cur = await self.conn.execute(
            "SELECT COALESCE(SUM(p.amount),0) AS s FROM payments p WHERE "
            "(p.charge_id IS NULL AND p.refunded<>1) OR p.id IN "
            "(SELECT MIN(id) FROM payments WHERE charge_id IS NOT NULL GROUP BY charge_id "
            "HAVING MAX(CASE WHEN refunded=1 THEN 1 ELSE 0 END)=0)")
        return active, int((await cur.fetchone())["s"])

    async def get_ai_model(self, user_id: int) -> str | None:
        cur = await self.conn.execute("SELECT ai_model FROM user_prefs WHERE user_id=?", (user_id,))
        r = await cur.fetchone()
        return r["ai_model"] if r else None

    async def set_ai_model(self, user_id: int, model: str | None) -> None:
        await self.conn.execute("INSERT INTO user_prefs(user_id,ai_model) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET "
                                "ai_model=excluded.ai_model", (user_id, model))
        await self.conn.commit()

    # ---------- промокоды ----------
    async def promo_create(self, code: str, days: int, uses: int, by: int, now: int) -> bool:
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO promo_codes(code,days,uses_left,created_by,created_at) VALUES(?,?,?,?,?)",
            (code, days, uses, by, now))
        await self.conn.commit()
        return cur.rowcount == 1

    async def promo_delete(self, code: str) -> bool:
        cur = await self.conn.execute("DELETE FROM promo_codes WHERE code=?", (code,))
        await self.conn.commit()
        return cur.rowcount == 1

    async def promo_list(self) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT c.code, c.days, c.uses_left, (SELECT COUNT(*) FROM promo_uses u WHERE u.code=c.code) AS used "
            "FROM promo_codes c ORDER BY c.created_at DESC LIMIT 50")
        return [dict(r) for r in await cur.fetchall()]

    async def promo_redeem(self, code: str, user_id: int, now: int) -> tuple[str, int]:
        """('ok', дней) | ('used', 0) — этот человек уже активировал | ('none', 0) — нет кода или кончились активации.
        Активация списывается атомарно: последнюю не получат двое одновременно."""
        cur = await self.conn.execute("SELECT 1 FROM promo_uses WHERE code=? AND user_id=?", (code, user_id))
        if await cur.fetchone():
            return "used", 0
        cur = await self.conn.execute("SELECT days FROM promo_codes WHERE code=?", (code,))
        r = await cur.fetchone()
        if r is None:
            return "none", 0
        cur = await self.conn.execute("UPDATE promo_codes SET uses_left=uses_left-1 WHERE code=? AND uses_left>0", (code,))
        if cur.rowcount != 1:
            await self.conn.commit()
            return "none", 0
        cur = await self.conn.execute("INSERT OR IGNORE INTO promo_uses(code,user_id,ts) VALUES(?,?,?)", (code, user_id, now))
        if cur.rowcount != 1:                                   # параллельная повторная попытка того же человека
            await self.conn.execute("UPDATE promo_codes SET uses_left=uses_left+1 WHERE code=?", (code,))
            await self.conn.commit()
            return "used", 0
        await self.conn.commit()
        return "ok", r["days"]

    # ---------- предложка ----------
    async def sugg_add(self, chat_id: int, user_id: int, user_name: str, text: str, ts: int) -> int:
        cur = await self.conn.execute(
            "INSERT INTO suggestions(chat_id,user_id,user_name,text,ts,status) VALUES(?,?,?,?,?,'new')",
            (chat_id, user_id, user_name, text, ts))
        await self.conn.commit()
        return cur.lastrowid

    async def sugg_get(self, sid: int) -> dict | None:
        cur = await self.conn.execute("SELECT * FROM suggestions WHERE id=?", (sid,))
        r = await cur.fetchone()
        return dict(r) if r else None

    async def sugg_list(self, chat_id: int, only_new: bool) -> list[dict]:
        """Новые сверху. only_new — только необработанные."""
        sql = "SELECT * FROM suggestions WHERE chat_id=?" + (" AND status='new'" if only_new else "")
        cur = await self.conn.execute(sql + " ORDER BY id DESC LIMIT 500", (chat_id,))
        return [dict(r) for r in await cur.fetchall()]

    async def sugg_counts(self, chat_id: int) -> tuple[int, int]:
        """(новых, всего)."""
        cur = await self.conn.execute(
            "SELECT COUNT(*) AS t, SUM(CASE WHEN status='new' THEN 1 ELSE 0 END) AS n FROM suggestions WHERE chat_id=?",
            (chat_id,))
        r = await cur.fetchone()
        return int(r["n"] or 0), int(r["t"] or 0)

    async def sugg_decide(self, sid: int, status: str, by: int, ts: int) -> bool:
        """new → accepted/rejected ровно один раз (двойное нажатие или два модератора — второе не сработает)."""
        cur = await self.conn.execute(
            "UPDATE suggestions SET status=?, handled_by=?, handled_at=? WHERE id=? AND status='new'", (status, by, ts, sid))
        await self.conn.commit()
        return cur.rowcount == 1

    async def sugg_delete(self, sid: int) -> bool:
        cur = await self.conn.execute("DELETE FROM suggestions WHERE id=?", (sid,))
        await self.conn.commit()
        return cur.rowcount == 1

    # ---------- цитатник ----------
    async def quote_add(self, chat_id: int, author_id: int, author_name: str, text: str, ts: int, added_by: int,
                        added_at: int, message_id: int | None) -> int | None:
        """Номер новой цитаты; None — это сообщение уже в цитатнике."""
        if message_id is not None:
            cur = await self.conn.execute("SELECT id FROM quotes WHERE chat_id=? AND message_id=?", (chat_id, message_id))
            if await cur.fetchone():
                return None
        cur = await self.conn.execute(
            "INSERT INTO quotes(chat_id,author_id,author_name,text,ts,added_by,added_at,message_id) VALUES(?,?,?,?,?,?,?,?)",
            (chat_id, author_id, author_name, text, ts, added_by, added_at, message_id))
        await self.conn.commit()
        return cur.lastrowid

    async def quote_by_message(self, chat_id: int, message_id: int) -> dict | None:
        cur = await self.conn.execute("SELECT * FROM quotes WHERE chat_id=? AND message_id=?", (chat_id, message_id))
        r = await cur.fetchone()
        return dict(r) if r else None

    async def quote_get(self, chat_id: int, qid: int) -> dict | None:
        cur = await self.conn.execute("SELECT * FROM quotes WHERE chat_id=? AND id=?", (chat_id, qid))
        r = await cur.fetchone()
        return dict(r) if r else None

    async def quote_random(self, chat_id: int, author_id: int | None = None) -> dict | None:
        sql, args = "SELECT * FROM quotes WHERE chat_id=?", [chat_id]
        if author_id is not None:
            sql += " AND author_id=?"
            args.append(author_id)
        cur = await self.conn.execute(sql + " ORDER BY RANDOM() LIMIT 1", tuple(args))
        r = await cur.fetchone()
        return dict(r) if r else None

    async def quote_list(self, chat_id: int, author_id: int | None = None, limit: int = 15) -> list[dict]:
        sql, args = "SELECT * FROM quotes WHERE chat_id=?", [chat_id]
        if author_id is not None:
            sql += " AND author_id=?"
            args.append(author_id)
        cur = await self.conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*args, limit))
        return [dict(r) for r in await cur.fetchall()]

    async def quote_stats(self, chat_id: int, limit: int = 5) -> tuple[int, list[tuple[int, str, int]]]:
        cur = await self.conn.execute("SELECT COUNT(*) AS n FROM quotes WHERE chat_id=?", (chat_id,))
        total = (await cur.fetchone())["n"]
        cur = await self.conn.execute(
            "SELECT author_id, MAX(author_name) AS name, COUNT(*) AS n FROM quotes WHERE chat_id=? "
            "GROUP BY author_id ORDER BY n DESC LIMIT ?", (chat_id, limit))
        return total, [(r["author_id"], r["name"], r["n"]) for r in await cur.fetchall()]

    async def quote_delete(self, chat_id: int, qid: int) -> bool:
        cur = await self.conn.execute("DELETE FROM quotes WHERE chat_id=? AND id=?", (chat_id, qid))
        await self.conn.commit()
        return cur.rowcount == 1

    async def quote_set_card(self, qid: int, file_id: str | None) -> None:
        await self.conn.execute("UPDATE quotes SET card=? WHERE id=?", (file_id, qid))
        await self.conn.commit()

    # ---------- мог-баттлы ----------
    async def mog_rating_get(self, fp: str, now: int, max_age: int = 30 * 86400) -> dict | None:
        """Запомненная оценка профиля (тот же профиль — те же баллы) или None."""
        cur = await self.conn.execute("SELECT avatar, name, meaning, ts FROM mog_ratings WHERE fp=?", (fp,))
        r = await cur.fetchone()
        if r is None or now - r["ts"] > max_age:
            return None
        return {"avatar": r["avatar"], "name": r["name"], "meaning": r["meaning"]}

    async def mog_rating_put(self, fp: str, rating: dict, now: int) -> None:
        await self.conn.execute(
            "INSERT INTO mog_ratings(fp,avatar,name,meaning,ts) VALUES(?,?,?,?,?) ON CONFLICT(fp) DO UPDATE SET "
            "avatar=excluded.avatar, name=excluded.name, meaning=excluded.meaning, ts=excluded.ts",
            (fp, rating["avatar"], rating["name"], rating["meaning"], now))
        await self.conn.commit()

    async def mog_add(self, chat_id: int, winner: int, loser: int, ts: int) -> None:
        await self.conn.execute("INSERT INTO mog_results(chat_id,winner,loser,ts) VALUES(?,?,?,?)", (chat_id, winner, loser, ts))
        await self.conn.commit()

    async def mog_top(self, chat_id: int, limit: int = 10) -> list[tuple[int, int, int]]:
        """[(user_id, победы, поражения)] по числу побед."""
        cur = await self.conn.execute(
            "SELECT u, SUM(w) AS w, SUM(l) AS l FROM ("
            "SELECT winner AS u, 1 AS w, 0 AS l FROM mog_results WHERE chat_id=? "
            "UNION ALL SELECT loser AS u, 0 AS w, 1 AS l FROM mog_results WHERE chat_id=?) t "
            "GROUP BY u ORDER BY w DESC, l ASC LIMIT ?", (chat_id, chat_id, limit))
        return [(r["u"], r["w"], r["l"]) for r in await cur.fetchall()]

    # ---------- конкурсы ----------
    GW_FIELDS = {"step", "text", "photo", "winners", "publish_at", "ends_at", "status", "message_id", "result",
                 "shown_count", "chat_id"}

    async def gw_new_draft(self, chat_id: int, creator: int, now: int) -> int:
        """Новый черновик (старые черновики этого автора удаляются: мастер ведёт один конкурс за раз)."""
        await self.conn.execute("DELETE FROM giveaways WHERE creator=? AND status='draft'", (creator,))
        cur = await self.conn.execute(
            "INSERT INTO giveaways(chat_id,creator,step,status,created_at,winners) VALUES(?,?,'text','draft',?,1)",
            (chat_id, creator, now))
        await self.conn.commit()
        return cur.lastrowid

    async def gw_draft(self, creator: int) -> dict | None:
        cur = await self.conn.execute(
            "SELECT * FROM giveaways WHERE creator=? AND status='draft' ORDER BY id DESC LIMIT 1", (creator,))
        r = await cur.fetchone()
        return dict(r) if r else None

    async def gw_get(self, gid: int) -> dict | None:
        cur = await self.conn.execute("SELECT * FROM giveaways WHERE id=?", (gid,))
        r = await cur.fetchone()
        return dict(r) if r else None

    async def gw_update(self, gid: int, **fields) -> None:
        bad = set(fields) - self.GW_FIELDS
        if bad:
            raise KeyError(bad)
        sets = ",".join(f"{k}=?" for k in fields)
        await self.conn.execute(f"UPDATE giveaways SET {sets} WHERE id=?", (*fields.values(), gid))
        await self.conn.commit()

    async def gw_delete_draft(self, creator: int) -> bool:
        cur = await self.conn.execute("DELETE FROM giveaways WHERE creator=? AND status='draft'", (creator,))
        await self.conn.commit()
        return cur.rowcount > 0

    async def gw_claim(self, gid: int, old: str, new: str) -> bool:
        """Атомарный переход статуса: только один обработчик (и только один раз) публикует или подводит итоги."""
        cur = await self.conn.execute("UPDATE giveaways SET status=? WHERE id=? AND status=?", (new, gid, old))
        await self.conn.commit()
        return cur.rowcount == 1

    async def gw_due(self, status: str, column: str, now: int) -> list[dict]:
        if column not in ("publish_at", "ends_at"):
            raise KeyError(column)
        cur = await self.conn.execute(
            f"SELECT * FROM giveaways WHERE status=? AND {column}<=? ORDER BY {column}", (status, now))
        return [dict(r) for r in await cur.fetchall()]

    async def gw_list(self, chat_id: int | None, statuses: tuple[str, ...]) -> list[dict]:
        marks = ",".join("?" for _ in statuses)
        sql, args = f"SELECT * FROM giveaways WHERE status IN ({marks})", list(statuses)
        if chat_id is not None:
            sql += " AND chat_id=?"
            args.append(chat_id)
        cur = await self.conn.execute(sql + " ORDER BY id", tuple(args))
        return [dict(r) for r in await cur.fetchall()]

    async def gw_join(self, gid: int, user_id: int, now: int) -> bool:
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO giveaway_entries(gid,user_id,ts) "
            "SELECT id,?,? FROM giveaways WHERE id=? AND status='active' AND ends_at>?",
            (user_id, now, gid, now))
        await self.conn.commit()
        return cur.rowcount == 1

    async def gw_joined(self, gid: int, user_id: int) -> bool:
        cur = await self.conn.execute("SELECT 1 FROM giveaway_entries WHERE gid=? AND user_id=?", (gid, user_id))
        return await cur.fetchone() is not None

    async def gw_entries(self, gid: int) -> list[int]:
        cur = await self.conn.execute("SELECT user_id FROM giveaway_entries WHERE gid=? ORDER BY ts", (gid,))
        return [r["user_id"] for r in await cur.fetchall()]

    async def gw_count(self, gid: int) -> int:
        cur = await self.conn.execute("SELECT COUNT(*) AS n FROM giveaway_entries WHERE gid=?", (gid,))
        return (await cur.fetchone())["n"]

    async def gw_check_get(self, gid: int, user_id: int) -> dict | None:
        cur = await self.conn.execute("SELECT * FROM giveaway_checks WHERE gid=? AND user_id=?", (gid, user_id))
        r = await cur.fetchone()
        return dict(r) if r else None

    async def gw_check_new(self, gid: int, user_id: int, answer: str, expires_at: int, now: int) -> None:
        # Параллельные запросы изображения не должны сбрасывать активную капчу и её попытки.
        await self.conn.execute(
            "INSERT INTO giveaway_checks(gid,user_id,answer,attempts,expires_at) VALUES(?,?,?,0,?) "
            "ON CONFLICT(gid,user_id) DO UPDATE SET answer=excluded.answer, attempts=0, expires_at=excluded.expires_at "
            "WHERE giveaway_checks.expires_at<=?", (gid, user_id, answer, expires_at, now))
        await self.conn.commit()

    async def gw_check_attempt(self, gid: int, user_id: int, limit: int, answer: str, now: int) -> bool:
        """Занять попытку именно у прочитанной, ещё действующей капчи."""
        cur = await self.conn.execute(
            "UPDATE giveaway_checks SET attempts=attempts+1 WHERE gid=? AND user_id=? AND attempts<? "
            "AND answer=? AND expires_at>?", (gid, user_id, limit, answer, now))
        await self.conn.commit()
        return cur.rowcount == 1

    async def gw_check_done(self, gid: int, user_id: int) -> None:
        await self.conn.execute("DELETE FROM giveaway_checks WHERE gid=? AND user_id=?", (gid, user_id))
        await self.conn.commit()

    async def gw_prune(self, now: int) -> None:
        await self.conn.execute("DELETE FROM giveaway_checks WHERE expires_at<?", (now - 86400,))
        await self.conn.execute("DELETE FROM giveaways WHERE status='draft' AND created_at<?", (now - 2 * 86400,))
        await self.conn.commit()

    # ---------- капча ----------
    async def create_captcha(
        self, token: str, chat_id: int, user_id: int, answer,
        expires_at: int, message_id: int, kind: str = "member", level: int = 0,
    ) -> None:
        """kind: 'member' — вошедший участник (сообщение в чате), 'join_request' — заявка на вступление (сообщение в личке)."""
        await self.conn.execute(
            "INSERT INTO captchas(token,chat_id,user_id,answer,expires_at,message_id,kind,level) VALUES(?,?,?,?,?,?,?,?)",
            (token, chat_id, user_id, json.dumps(answer), expires_at, message_id, kind, level),
        )
        await self.conn.commit()

    @staticmethod
    def _captcha(r) -> dict:
        d = dict(r)
        d["answer"] = json.loads(d["answer"])
        return d

    async def get_captcha(self, token: str) -> dict | None:
        cur = await self.conn.execute("SELECT * FROM captchas WHERE token=?", (token,))
        r = await cur.fetchone()
        return self._captcha(r) if r else None

    async def get_captcha_for_user(self, chat_id: int, user_id: int) -> dict | None:
        cur = await self.conn.execute(
            "SELECT * FROM captchas WHERE chat_id=? AND user_id=?", (chat_id, user_id)
        )
        r = await cur.fetchone()
        return self._captcha(r) if r else None

    async def take_captcha_attempt(self, token: str, limit: int) -> bool:
        """Атомарно занять одну попытку ответа. False — попытки кончились (параллельные запросы лимит не обходят)."""
        cur = await self.conn.execute(
            "UPDATE captchas SET attempts=COALESCE(attempts,0)+1 WHERE token=? AND COALESCE(attempts,0)<?", (token, limit))
        await self.conn.commit()
        return cur.rowcount == 1

    async def consume_captcha(self, token: str) -> bool:
        cur = await self.conn.execute("DELETE FROM captchas WHERE token=?", (token,))
        await self.conn.commit()
        return cur.rowcount == 1

    async def expired_captchas(self, now: int) -> list[dict]:
        cur = await self.conn.execute("SELECT * FROM captchas WHERE expires_at<=?", (now,))
        return [self._captcha(r) for r in await cur.fetchall()]

    # ---------- коллекционные карточки ----------
    async def cards_of(self, user_id: int) -> dict[int, int]:
        cur = await self.conn.execute("SELECT card_id, n FROM cards_owned WHERE user_id=? AND n>0", (user_id,))
        return {r["card_id"]: r["n"] for r in await cur.fetchall()}

    async def cards_try_find(self, user_id: int, card_id: int, now: int, cooldown: int) -> int | None:
        """Записывает находку, если с прошлой прошло не меньше cooldown. None — найдено; иначе сколько секунд ждать."""
        async with self.atomic():
            cur = await self.conn.execute("SELECT last_find FROM cards_cooldown WHERE user_id=?", (user_id,))
            r = await cur.fetchone()
            if r and now - r["last_find"] < cooldown:
                return cooldown - (now - r["last_find"])
            await self.conn.execute(
                "INSERT INTO cards_cooldown VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET last_find=excluded.last_find",
                (user_id, now))
            await self.conn.execute(
                "INSERT INTO cards_owned VALUES(?,?,1) ON CONFLICT(user_id,card_id) DO UPDATE SET n=cards_owned.n+1",
                (user_id, card_id))
        return None

    async def cards_swap(self, a: int, give: int, b: int, get: int) -> bool:
        """Атомарный обмен запасными копиями: a отдаёт give, b отдаёт get."""
        async with self.atomic():
            for user, card in ((a, give), (b, get)):
                cur = await self.conn.execute("SELECT n FROM cards_owned WHERE user_id=? AND card_id=?", (user, card))
                r = await cur.fetchone()
                if not r or r["n"] < 2:
                    return False
            for user, card, delta in ((a, give, -1), (b, get, -1), (a, get, 1), (b, give, 1)):
                await self.conn.execute(
                    "INSERT INTO cards_owned VALUES(?,?,?) ON CONFLICT(user_id,card_id) DO UPDATE SET n=cards_owned.n+?",
                    (user, card, max(delta, 0), delta))
        return True

    async def cards_top(self, limit: int = 10) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT user_id, COUNT(*) AS uniq, SUM(n) AS total FROM cards_owned WHERE n>0 GROUP BY user_id "
            "ORDER BY uniq DESC, total DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]

    # ---------- настольные игры (шахматы, шашки, морской бой) ----------
    async def save_bgame(self, game: dict) -> None:
        await self.conn.execute(
            "INSERT INTO board_games VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "data=excluded.data, expires_at=excluded.expires_at",
            (game["id"], game["chat_id"], json.dumps(game), game["expires_at"]))
        await self.conn.commit()

    async def get_bgame(self, game_id: str) -> dict | None:
        cur = await self.conn.execute("SELECT data FROM board_games WHERE id=?", (game_id,))
        r = await cur.fetchone()
        return json.loads(r["data"]) if r else None

    async def delete_bgame(self, game_id: str) -> bool:
        cur = await self.conn.execute("DELETE FROM board_games WHERE id=?", (game_id,))
        await self.conn.commit()
        return cur.rowcount == 1

    async def chat_bgames(self, chat_id: int) -> list[dict]:
        cur = await self.conn.execute("SELECT data FROM board_games WHERE chat_id=?", (chat_id,))
        return [json.loads(r["data"]) for r in await cur.fetchall()]

    async def expired_bgames(self, now: int) -> list[dict]:
        cur = await self.conn.execute("SELECT data FROM board_games WHERE expires_at<=?", (now,))
        return [json.loads(r["data"]) for r in await cur.fetchall()]

    # ---------- дуэли ----------
    async def save_duel(self, duel: dict) -> None:
        await self.conn.execute(
            "INSERT INTO duels VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "data=excluded.data, expires_at=excluded.expires_at",
            (duel["id"], duel["chat_id"], json.dumps(duel), duel["expires_at"]),
        )
        await self.conn.commit()

    async def get_duel(self, duel_id: str) -> dict | None:
        cur = await self.conn.execute("SELECT data FROM duels WHERE id=?", (duel_id,))
        r = await cur.fetchone()
        return json.loads(r["data"]) if r else None

    async def delete_duel(self, duel_id: str) -> bool:
        cur = await self.conn.execute("DELETE FROM duels WHERE id=?", (duel_id,))
        await self.conn.commit()
        return cur.rowcount == 1

    async def chat_duels(self, chat_id: int) -> list[dict]:
        cur = await self.conn.execute("SELECT data FROM duels WHERE chat_id=?", (chat_id,))
        return [json.loads(r["data"]) for r in await cur.fetchall()]

    async def expired_duels(self, now: int) -> list[dict]:
        cur = await self.conn.execute("SELECT data FROM duels WHERE expires_at<=?", (now,))
        return [json.loads(r["data"]) for r in await cur.fetchall()]



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/pg.py
# PostgreSQL-адаптер: даёт asyncpg тот же интерфейс, что aiosqlite (execute/commit/курсор), и переводит
# SQLite-диалект запросов Database в PostgreSQL. Публичные методы Database при этом не меняются.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
AUTOINC_TABLES = {"mod_log", "owner_log", "awards", "notes", "timers", "warn_events", "reports", "filters", "aimod_events", "giveaways", "quotes", "suggestions", "payments", "pairs", "pair_log", "pair_children", "pair_pets", "triggers", "faq", "periodic"}
# для INSERT OR REPLACE: первичный ключ таблицы
REPLACE_KEYS = {"marriages": ("chat_id", "u1", "u2"), "relations": ("chat_id", "u1", "u2")}


def _number_placeholders(sql: str) -> str:
    out, n, quote = [], 0, False
    for ch in sql:
        if ch == "'":
            quote = not quote
        if ch == "?" and not quote:
            n += 1
            out.append(f"${n}")
        else:
            out.append(ch)
    return "".join(out)


@lru_cache(maxsize=1024)
def translate__pg(sql: str) -> tuple[str, bool]:
    """(SQL для PostgreSQL, нужно ли вернуть id вставленной строки)."""
    s = sql.strip().rstrip(";")
    returning = False
    m = re.match(r"INSERT OR IGNORE INTO", s, re.I)
    if m:
        s = "INSERT INTO" + s[m.end():] + " ON CONFLICT DO NOTHING"
    m = re.match(r"INSERT OR REPLACE INTO\s+(\w+)\s*\(([^)]*)\)", s, re.I)
    if m:
        table, cols = m.group(1), [c.strip() for c in m.group(2).split(",")]
        key = REPLACE_KEYS[table]
        upd = ",".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in key)
        s = "INSERT INTO" + s[len("INSERT OR REPLACE INTO"):] + f" ON CONFLICT ({','.join(key)}) DO UPDATE SET {upd}"
    s = re.sub(r"\bRANDOM\(\)", "random()", s, flags=re.I)
    s = s.replace("lower_py(", "lower(")
    m = re.match(r"INSERT INTO\s+(\w+)", s, re.I)
    if m and m.group(1).lower() in AUTOINC_TABLES and "ON CONFLICT" not in s.upper():
        s += " RETURNING id"
        returning = True
    return _number_placeholders(s), returning


def translate_ddl(ddl: str) -> str:
    ddl = ddl.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    return re.sub(r"\bINTEGER\b", "BIGINT", ddl)


class PgRow:
    """Строка, ведущая себя как sqlite3.Row: row["col"], row[0], dict(row), распаковка."""
    __slots__ = ("_keys", "_vals")

    def __init__(self, record: asyncpg.Record):
        self._keys = list(record.keys())
        self._vals = [_norm__pg(v) for v in record.values()]

    def keys(self):
        return self._keys

    def __getitem__(self, k):
        return self._vals[k if isinstance(k, int) else self._keys.index(k)]

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)


def _norm__pg(v: Any) -> Any:
    from decimal import Decimal
    return int(v) if isinstance(v, Decimal) and v == v.to_integral_value() else v


class PgCursor:
    def __init__(self, rows: list[PgRow], rowcount: int, lastrowid: int | None):
        self._rows, self.rowcount, self.lastrowid = rows, rowcount, lastrowid

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return list(self._rows)


class PgConn:
    """Одно соединение, как у SQLite: запросы идут по очереди, транзакция открывается на первой записи
    и закрывается commit(). SELECT вне транзакции не держит её открытой."""

    def __init__(self, conn: asyncpg.Connection, schema: str | None = None):
        self._c = conn
        self._lock = asyncio.Lock()
        self._in_tx = False
        self.schema = schema

    async def execute(self, sql: str, args=()) -> PgCursor:
        pg_sql, returning = translate__pg(sql)
        is_read = bool(re.match(r"\s*(SELECT|WITH)\b", pg_sql, re.I))
        async with self._lock:
            try:
                if not is_read and not self._in_tx:
                    await self._c.execute("BEGIN")
                    self._in_tx = True
                if is_read or returning:
                    recs = await self._c.fetch(pg_sql, *args)
                    rows = [PgRow(r) for r in recs]
                    last = rows[0]["id"] if returning and rows else None
                    return PgCursor(rows, len(rows) if not is_read else -1, last)
                status = await self._c.execute(pg_sql, *args)
                return PgCursor([], int(status.split()[-1]) if status.split()[-1].isdigit() else 0, None)
            except Exception:
                if self._in_tx:  # в PG упавший запрос ломает всю транзакцию — откатываем, как «чистый лист»
                    await self._c.execute("ROLLBACK")
                    self._in_tx = False
                raise

    async def executemany(self, sql: str, args) -> None:
        """Batch writes under the same transaction and lock as execute()."""
        pg_sql, returning = translate__pg(sql)
        if returning:
            raise ValueError("executemany does not support generated IDs")
        async with self._lock:
            try:
                if not self._in_tx:
                    await self._c.execute("BEGIN")
                    self._in_tx = True
                await self._c.executemany(pg_sql, args)
            except BaseException:
                if self._in_tx:
                    await self._c.execute("ROLLBACK")
                    self._in_tx = False
                raise

    async def begin(self) -> None:
        async with self._lock:
            if not self._in_tx:
                self._in_tx = True
                await self._c.execute("BEGIN")

    async def rollback(self) -> None:
        async with self._lock:
            if self._in_tx:
                await self._c.execute("ROLLBACK")
                self._in_tx = False

    async def commit(self) -> None:
        async with self._lock:
            if self._in_tx:
                await self._c.execute("COMMIT")
                self._in_tx = False

    async def executescript(self, script: str) -> None:
        async with self._lock:
            for stmt in (x.strip() for x in translate_ddl(script).split(";")):
                if stmt:
                    await self._c.execute(stmt)

    async def close(self) -> None:
        async with self._lock:
            if self._in_tx:
                await self._c.execute("ROLLBACK")
            if self.schema and not getattr(self, 'schema_keep', False):
                await self._c.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
            await self._c.close()


async def connect__pg(url: str, schema: str | None = None) -> PgConn:
    if schema:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", schema):
            raise ValueError("invalid PostgreSQL schema name")
        boot = await asyncpg.connect(url)
        try:
            await boot.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        finally:
            await boot.close()
        conn = await asyncpg.connect(url, server_settings={"search_path": schema})
    else:
        conn = await asyncpg.connect(url)
    return PgConn(conn, schema)


def _dump_connection(url: str) -> tuple[str, dict]:
    """Keep libpq passwords out of process arguments; other URI options stay literal."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("postgresql", "postgres") or parsed.fragment:
        raise ValueError("PostgreSQL backup requires a valid database URI")
    environment = dict(os.environ)
    netloc = parsed.netloc
    if parsed.password is not None:
        userinfo, host = netloc.rsplit("@", 1)
        netloc = userinfo.split(":", 1)[0] + "@" + host
        environment["PGPASSWORD"] = unquote(parsed.password)
    query = []
    for item in parsed.query.split("&") if parsed.query else []:
        key, _, value = item.partition("=")
        if unquote(key).lower() == "password":
            environment["PGPASSWORD"] = unquote(value)
        else:
            query.append(item)
    clean = f"{parsed.scheme}://{netloc}{parsed.path}"
    if query:
        clean += "?" + "&".join(query)
    return clean, environment


async def pg_dump(url: str, path: str, timeout: float = 300) -> None:
    """Custom-format dump; reap pg_dump on cancellation or timeout."""
    clean_url, environment = _dump_connection(url)
    proc = await asyncio.create_subprocess_exec(
        "pg_dump", "--format=custom", "--file", path, "--dbname", clean_url, env=environment,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except BaseException:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
        raise
    if proc.returncode != 0:
        raise RuntimeError("pg_dump: " + err.decode(errors="replace")[:200])
