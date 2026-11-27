"""Активность чата: норма сообщений в неделю (автокик), «подъём молчунов» и самостоятельные реплики Нори в тихом чате.

Всё включается в настройках («📅 Активность»). Везде, где пишет ИИ, — характер Нори из chatmind (грубая, по-свойски), независимо
от стиля «живого общения».

Неделя — календарная, с понедельника 00:00 по часовому поясу чата. Норма считается только за недели, которые целиком прошли
ПОСЛЕ включения (первая проверка — в понедельник после первой полной недели), чтобы включение не выкинуло людей за прошлое.
Не кикаются: админы, модераторы бота, боты и те, кто вошёл в чат уже в течение проверяемой недели. Если под кик попадает слишком
много людей (больше трети чата или 50) — бот не кикает, а пишет об этом в чат: скорее всего, норма выставлена слишком высокой."""
from __future__ import annotations

import asyncio
import html
import json
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bot import chatmind, gender
from bot.db import Database
from bot.targets import mention

DAY = 86400
WEEK = 7 * DAY
TICK = 600                        # как часто смотрим чаты, сек
FIRST_DELAY = 120
KICK_HOUR = 10                    # проверка прошлой недели — в понедельник после этого часа (по времени чата)
WARN_POINTS = ((5, 12, 1), (6, 18, 2))       # (день недели 0=пн, час, номер напоминания): суббота 12:00 и воскресенье 18:00
KICK_PAUSE = 0.1
MAX_KICK_SHARE = 1 / 3
MAX_KICK_ABS = 50
LIST_LIMIT = 15
NEWBIE_DAYS = 3                   # «подъём» не тегает тех, кто в чате меньше
QUIET_MAX = 5                     # молчун: столько сообщений за последние 7 дней и меньше
WAKE_COOLDOWN = 4 * 3600          # между подъёмами в одном чате
WAKE_USER_COOLDOWN = 3 * DAY      # одного и того же человека не тегаем чаще
WAKE_CHANCE = 0.12                # на каждый тик в «разрешённые» часы
IDLE_STREAK_MAX = 3               # столько реплик в тишине подряд, пока никто не ответил
DAILY_AI = 40                     # лимит ИИ-реплик этой функции на чат в сутки
SPEAK_FROM, SPEAK_TO = 10, 23     # самостоятельно пишем только в эти часы (время чата)
STATE_KEY = "activity_state"


# ---------- чистая логика (тестируется без Telegram) ----------
def chat_tz(name: str | None):
    try:
        return ZoneInfo(name or "Europe/Moscow")
    except Exception:
        return timezone(timedelta(hours=3))


def week_start(now: float, tz) -> int:
    """Unix-время понедельника 00:00 (по tz) той недели, в которую попадает now."""
    local = datetime.fromtimestamp(now, tz)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(monday.timestamp())


def next_week_start(ws: int, tz) -> int:
    """Начало следующей недели (учёт перевода часов: не просто +7 суток)."""
    return week_start(ws + WEEK + 12 * 3600, tz)


def prev_week_start(ws: int, tz) -> int:
    return week_start(ws - 12 * 3600, tz)


def below_norm(members: list[dict], counts: dict[int, int], exempt: set[int], norm: int, joined_after: int) -> list[tuple[int, int]]:
    """[(user_id, сообщений)] тех, кто не дотянул до нормы, от самых молчаливых. Не считаются: exempt и вошедшие позже joined_after
    (у них не было полной недели)."""
    out = []
    for m in members:
        uid = m["user_id"]
        if uid in exempt:
            continue
        since = m.get("joined_at") or m.get("first_seen")
        if since is not None and since > joined_after:
            continue
        n = counts.get(uid, 0)
        if n < norm:
            out.append((uid, n))
    out.sort(key=lambda x: (x[1], x[0]))
    return out


def kick_allowed(candidates: int, members: int) -> bool:
    """Защита от массового кика из-за слишком высокой нормы."""
    return candidates <= MAX_KICK_ABS and candidates <= max(5, int(members * MAX_KICK_SHARE))


def pick_quiet(members: list[dict], week_counts: dict[int, int], exempt: set[int], now: float, poked: dict[str, float],
               rnd: random.Random | None = None) -> int | None:
    """Случайный молчун: в чате дольше NEWBIE_DAYS, за неделю написал не больше QUIET_MAX, давно не тегали."""
    pool = []
    for m in members:
        uid = m["user_id"]
        if uid in exempt:
            continue
        since = m.get("joined_at") or m.get("first_seen")
        if since is not None and now - since < NEWBIE_DAYS * DAY:
            continue
        if week_counts.get(uid, 0) > QUIET_MAX or now - poked.get(str(uid), 0) < WAKE_USER_COOLDOWN:
            continue
        pool.append(uid)
    return (rnd or random).choice(pool) if pool else None


def speak_hour_ok(now: float, tz) -> bool:
    return SPEAK_FROM <= datetime.fromtimestamp(now, tz).hour < SPEAK_TO


def idle_due(last_activity: float | None, state: dict, now: float, hours: float) -> bool:
    """Пора ли Нори самой написать: чат молчит дольше hours часов, с её прошлой реплики тоже прошло hours, и подряд без ответа
    людей она написала меньше IDLE_STREAK_MAX раз."""
    last_activity = last_activity or 0
    if now - last_activity < hours * 3600 or now - state.get("idle_last", 0) < hours * 3600:
        return False
    if last_activity <= state.get("idle_last", 0) and state.get("idle_streak", 0) >= IDLE_STREAK_MAX:
        return False
    return True


# ---------- состояние (в chat_texts, без новых таблиц) ----------
async def load_state(db: Database, chat: int) -> dict:
    try:
        return json.loads(await db.get_text(chat, STATE_KEY) or "{}")
    except ValueError:
        return {}


async def save_state(db: Database, chat: int, st: dict) -> None:
    await db.set_text(chat, STATE_KEY, json.dumps(st, ensure_ascii=False))


# ---------- данные чата ----------
async def exempt_ids(bot, db: Database, chat: int) -> set[int] | None:
    """Кого нельзя трогать: админы Telegram, модераторы бота, сам бот. None — список админов получить не удалось."""
    ids = {(await bot.me()).id} | {r["user_id"] for r in await db.list_ranks(chat)}
    try:
        ids |= {a.user.id for a in await bot.get_chat_administrators(chat)}
    except Exception:
        return None
    return ids


async def week_counts(db: Database, chat: int, start: int, end: int | None = None) -> dict[int, int]:
    """Сообщения по людям за [start, end). Счётчики хранятся по часам/дням, поэтому берём «с start» и вычитаем «с end»."""
    _, a = await db.count_by_user(chat, start, limit=1_000_000)
    out = dict(a)
    if end is not None:
        _, b = await db.count_by_user(chat, end, limit=1_000_000)
        for uid, n in b:
            out[uid] = max(out.get(uid, 0) - n, 0)
    return out


def _names(db_names: dict[int, str], pairs: list[tuple[int, int]], norm: int, limit: int = LIST_LIMIT) -> str:
    lines = [f"• {mention(uid, db_names[uid])} — {n}/{norm}" for uid, n in pairs[:limit]]
    if len(pairs) > limit:
        lines.append(f"…и ещё {len(pairs) - limit}")
    return "\n".join(lines)


async def _name_map(db: Database, ids) -> dict[int, str]:
    return {u: (await db.user_name(u)) or f"id{u}" for u in ids}


# ---------- норма сообщений ----------
async def quota_step(bot, db: Database, chat: int, s: dict, st: dict, now: float) -> bool:
    """Один тик нормы. True — состояние изменилось."""
    tz = chat_tz(s.get("tz"))
    norm = int(s["quota_min"])
    ws = week_start(now, tz)
    since = int(s.get("quota_since") or 0)
    if not since:                                     # только что включили: считаем со следующего понедельника
        await db.set_setting(chat, "quota_since", next_week_start(ws, tz))
        return False
    changed = False
    local = datetime.fromtimestamp(now, tz)

    # проверка прошедшей недели
    prev = prev_week_start(ws, tz)
    if prev >= since and st.get("kick_week") != ws and local.hour >= KICK_HOUR and local.weekday() == 0:
        st["kick_week"] = ws
        changed = True
        await _kick_week(bot, db, chat, norm, prev, ws, st)

    # напоминания в конце текущей недели
    if s.get("quota_warn") and ws >= since:
        for wd, hour, num in WARN_POINTS:
            done = st["warn_week"][1] if st.get("warn_week") and st["warn_week"][0] == ws else 0
            if local.weekday() == wd and local.hour >= hour and done < num:
                st["warn_week"] = [ws, num]
                changed = True
                await _warn(bot, db, chat, norm, ws, num, tz, now)
                break
    return changed


async def _warn(bot, db: Database, chat: int, norm: int, ws: int, num: int, tz, now: float) -> None:
    exempt = await exempt_ids(bot, db, chat)
    if exempt is None:
        return
    lag = below_norm(await db.members_info(chat), await week_counts(db, chat, ws), exempt, norm, ws)
    if not lag:
        return
    names = await _name_map(db, [u for u, _ in lag[:LIST_LIMIT]])
    left = int((next_week_start(ws, tz) - now) // 3600)
    head = ("⏰ Эй, неделя почти кончилась" if num == 2 else "👀 Напоминаю про норму") + (
        f": до понедельника ~{left} ч, а норма — <b>{norm}</b> сообщений за неделю. Кто не добрал, в понедельник вылетает:")
    try:
        await bot.send_message(chat, head + "\n" + _names(names, lag, norm), disable_web_page_preview=True)
    except Exception as e:
        logging.info("норма: напоминание не отправилось (%s)", e)


async def _kick_week(bot, db: Database, chat: int, norm: int, start: int, end: int, st: dict) -> None:
    exempt = await exempt_ids(bot, db, chat)
    if exempt is None:
        logging.info("норма: не получил список админов в %s — проверка пропущена", chat)
        return
    members = await db.members_info(chat)
    lag = below_norm(members, await week_counts(db, chat, start, end), exempt, norm, start)
    if not lag:
        try:
            await bot.send_message(chat, f"🏆 Неделя закрыта: все набрали норму ({norm}). Живёте.")
        except Exception:
            pass
        return
    if not kick_allowed(len(lag), len(members)):
        names = await _name_map(db, [u for u, _ in lag[:LIST_LIMIT]])
        try:
            await bot.send_message(
                chat, f"🛑 Не набрали норму ({norm}) аж {len(lag)} из {len(members)} — это слишком много, никого не кикаю. "
                      f"Админы, проверьте, не завышена ли норма (<code>норма 100</code>):\n" + _names(names, lag, norm),
                disable_web_page_preview=True)
        except Exception:
            pass
        return
    names = await _name_map(db, [u for u, _ in lag])
    kicked, failed = [], 0
    for uid, n in lag:
        try:
            await bot.ban_chat_member(chat, uid)
            await bot.unban_chat_member(chat, uid)          # кик с возвратом: зайти по ссылке можно
            await db.set_member_active(chat, uid, False)
            kicked.append((uid, n))
        except Exception:
            failed += 1
        await asyncio.sleep(KICK_PAUSE)
    await db.log_action(chat, 0, 0, "автокик нормы", f"{len(kicked)}/{len(lag)}, норма {norm}", int(time.time()))
    text = f"🧹 Неделя закрыта. Не набрали норму ({norm}) и вылетают:\n" + _names(names, kicked, norm, limit=40) if kicked else ""
    if failed:
        text += f"\n⚠️ Не получилось исключить: {failed} (проверьте у бота право «Блокировка участников»)."
    if text:
        try:
            await bot.send_message(chat, text, disable_web_page_preview=True)
        except Exception:
            pass


# ---------- ИИ-реплики (всегда характер Нори) ----------
async def _nori_say(ai, system_extra: str, prompt: str) -> str | None:
    """Реплика грубой Нори по заданию; None — ИИ недоступен или ответил SKIP."""
    try:
        raw = await ai.converse(chatmind.persona("casual") + "\n" + system_extra, prompt)
    except Exception as e:
        logging.info("активность: ИИ не ответил (%s)", e)
        return None
    return chatmind.sanitize_reply(raw, casual=True)


async def wake_step(bot, db: Database, ai, chat: int, s: dict, st: dict, now: float, rnd: random.Random | None = None) -> bool:
    rnd = rnd or random
    tz = chat_tz(s.get("tz"))
    if not speak_hour_ok(now, tz) or now - st.get("wake_last", 0) < WAKE_COOLDOWN or rnd.random() > WAKE_CHANCE:
        return False
    exempt = await exempt_ids(bot, db, chat)
    if exempt is None:
        return False
    ws = now - WEEK
    uid = pick_quiet(await db.members_info(chat), await week_counts(db, chat, int(ws)), exempt, now,
                     st.setdefault("poked", {}), rnd)
    if uid is None or not await db.take_quota(chat, "activity", int(now), DAILY_AI):
        return False
    name = (await db.user_name(uid)) or "молчун"
    g = await gender.get(db, uid)
    who = {"m": "парень (пиши о нём в мужском роде)", "f": "девушка (пиши о ней в женском роде)"}.get(g, "пол неизвестен (обращайся на «ты», без рода)")
    text = await _nori_say(
        ai, "Сейчас ты подкалываешь молчуна, который почти не пишет в чате. Одна-две короткие фразы, до 140 символов, смешно и грубо, "
            "без пинга и ссылок.",
        f"Молчуна зовут {name}, это {who}. Он(а) за последние дни почти ничего не написал(а). Напиши ЕМУ(ЕЙ) короткую смешную "
        "грубоватую подколку на тему «почему ты молчишь» (придумай свою версию причины: сдох, подписан на тишину, бот-шпион и т.п.). "
        "Обращайся прямо к нему на «ты». Имя в текст не вставляй — его добавят сами.")
    if not text:
        await db.refund_quota(chat, "activity", int(now))
        return False
    try:
        await bot.send_message(chat, f"{mention(uid, name)}, {html.escape(text[:200])}", disable_web_page_preview=True)
    except Exception as e:
        logging.info("подъём: не отправилось (%s)", e)
        await db.refund_quota(chat, "activity", int(now))
        return False
    st["wake_last"] = now
    st["poked"][str(uid)] = now
    st["poked"] = {k: v for k, v in st["poked"].items() if now - v < 30 * DAY}
    return True


KINDS = (
    ("шутку", "Расскажи короткую смешную шутку или анекдот (свой, придуманный на ходу), без вступлений."),
    ("вопрос", "Задай чату один провокационный, смешной или странный вопрос, на который хочется ответить. Только сам вопрос."),
    ("факт", "Расскажи один неожиданный реальный факт (наука, история, животные, космос) в одном-двух предложениях. Без выдумок."),
)


async def idle_step(bot, db: Database, ai, chat: int, s: dict, st: dict, now: float, last_activity: float | None,
                    rnd: random.Random | None = None) -> bool:
    rnd = rnd or random
    tz = chat_tz(s.get("tz"))
    if not speak_hour_ok(now, tz) or not idle_due(last_activity, st, now, float(s["idle_hours"])):
        return False
    if not await db.take_quota(chat, "activity", int(now), DAILY_AI):
        return False
    label, task = rnd.choice(KINDS)
    recent = st.get("idle_recent", [])
    avoid = ("\nНе повторяй уже сказанное: " + " | ".join(recent[-4:])) if recent else ""
    text = await _nori_say(
        ai, "Сейчас в чате тишина, и ты сама решила что-то написать. Коротко (до 220 символов), без пинга и ссылок, без «всем привет».",
        f"Напиши {label} для тихого чата друзей. {task}{avoid}")
    if not text:
        await db.refund_quota(chat, "activity", int(now))
        return False
    try:
        sent = await bot.send_message(chat, html.escape(text), disable_web_page_preview=True)
    except Exception as e:
        logging.info("тишина: не отправилось (%s)", e)
        await db.refund_quota(chat, "activity", int(now))
        return False
    chatmind.MEMORY.add(chat, chatmind.BOT_UID, "Нори", text, bot=True, msg_id=getattr(sent, "message_id", None))
    streak = st.get("idle_streak", 0) + 1 if (last_activity or 0) <= st.get("idle_last", 0) else 1
    st.update(idle_last=now, idle_streak=streak, idle_recent=(recent + [text[:80]])[-6:])
    return True


async def chat_last_activity(db: Database, chat: int) -> float | None:
    """Время последнего сообщения людей в чате по счётчикам (с точностью до часа, считаем до конца часа)."""
    cur = await db.conn.execute("SELECT MAX(hour_ts) AS t FROM msg_hourly WHERE chat_id=?", (chat,))
    row = await cur.fetchone()
    return (row["t"] + 3599) if row and row["t"] else None            # конец часа: не считаем чат тише, чем он есть


# ---------- цикл ----------
async def activity_chat(bot, db: Database, ai, chat: int, now: float | None = None) -> None:
    now = now or time.time()
    s = await db.get_settings(chat)
    ai_ok = ai is not None and getattr(ai, "has_river", False) and s.get("ai_on")
    if not s.get("quota_on") and s.get("quota_since"):
        await db.set_setting(chat, "quota_since", 0)      # выключили норму: при следующем включении счёт начнётся заново
    if not (s.get("quota_on") or (s.get("wake_on") and ai_ok) or (s.get("idle_on") and ai_ok)):
        return
    st = await load_state(db, chat)
    changed = False
    if s.get("quota_on"):
        changed |= await quota_step(bot, db, chat, s, st, now)
    if s.get("wake_on") and ai_ok:
        changed |= await wake_step(bot, db, ai, chat, s, st, now)
    if s.get("idle_on") and ai_ok:
        changed |= await idle_step(bot, db, ai, chat, s, st, now, await chat_last_activity(db, chat))
    if changed:
        await save_state(db, chat, st)


async def activity_loop(bot, db: Database, ai) -> None:
    await asyncio.sleep(FIRST_DELAY)
    while True:
        for c in await db.list_chats(0, 10000, active_only=True):
            if c["chat_id"] >= 0:
                continue
            try:
                await activity_chat(bot, db, ai, c["chat_id"])
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("активность: сбой в чате %s", c["chat_id"])
        await asyncio.sleep(TICK)
