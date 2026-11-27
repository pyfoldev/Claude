"""Анкеты, репутация, награды, заметки, закладки и таймеры."""
import asyncio
import html
import logging
import re
import time

from aiogram import F, Router
from aiogram.types import Message

from bot import ux
from bot import mod_service as ms
from bot.db import Database
from bot.fmt import kv_table, quote
from bot.family import Family
from bot.parsing import parse_period
from bot.ranks import need_rank
from bot.targets import listed, mention, resolve_user

router = Router(name="social")
_T = r"(@\w+|\d{5,})"
LIMITS = {"nick": 24, "title": 32, "motto": 64, "about": 300}
REP_DAILY = 30
MEDALS = {1: "🥉", 2: "🥈", 3: "🥇"}
MIN_TIMER, MAX_TIMER = 60, 30 * 86400
_PATTERNS = [
    ("set_field", r"^\+(ник|звание|девиз)\s+(.+)$"), ("set_about", r"^\+о себе\s+(.+)$"),
    ("del_field", r"^-(ник|звание|девиз)$"), ("del_about", r"^-о себе$"),
    ("my_profile", r"^моя анкета$"), ("profile", r"^анкета(?:\s+" + _T + ")?$"), ("who", r"^(?:кто ты|ты кто)(?:\s+" + _T + ")?$"), ("whoami", r"^кто я$"),
    ("rep_give", r"^([+-])\s?1?$"), ("rep_show", r"^репутация(?:\s+" + _T + ")?$"), ("rep_top", r"^рейтинг$"),
    ("award", r"^наградить(?:\s+([1-3]))?(?:\s+" + _T + ")?$"), ("awards", r"^награды(?:\s+" + _T + ")?$"),
    ("unaward", r"^снять награду(?:\s+" + _T + ")?$"),
    ("note_add", r"^\+заметка\s+(.+)$"), ("notes", r"^заметки$"), ("note_del", r"^-заметка\s+(\d{1,3})$"),
    ("bm_add", r"^\+закладка$"), ("bms", r"^закладки$"), ("bm_del", r"^-закладка\s+(\d{1,3})$"),
    ("timer_add1", r"^таймер\s+через\s+(час|минуту|день|сутки|неделю)\s+(.+)$"),
    ("timer_add", r"^таймер\s+через\s+(\S+)\s+(\S+)\s+(.+)$"), ("timers", r"^таймеры$"),
    ("timer_del", r"^-таймер\s+(\d{1,3})$"),
]
_COMPILED = [(k, re.compile(p, re.IGNORECASE | re.DOTALL)) for k, p in _PATTERNS]


def parse(text: str | None):
    t = (text or "").strip()
    for kind, rx in _COMPILED:
        m = rx.match(t)
        if m:
            return kind, m.groups()
    return None


def timer_delay(num: str, unit: str) -> int | None:
    """«5» «минут» → 300 секунд; None — если не срок или вне 1 мин … 30 дней."""
    d = parse_period(f"{num} {unit}")
    if d is None:
        return None
    sec = int(d.total_seconds())
    return sec if MIN_TIMER <= sec <= MAX_TIMER else None


def chat_link(chat_id: int, message_id: int) -> str | None:
    s = str(chat_id)
    return f"https://t.me/c/{s[4:]}/{message_id}" if s.startswith("-100") else None


async def _m(db: Database, uid: int) -> str:
    return mention(uid, (await db.user_name(uid)) or f"id{uid}")


@router.message(F.text.func(lambda t: parse(t) is not None))
async def social_cmd(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup"):
        return
    kind, g = parse(message.text)
    chat, me = message.chat.id, message.from_user.id
    now = int(time.time())
    reply = ms.real_reply(message)
    cfg = await db.get_settings(chat)

    # ---- профиль ----
    if kind in ("set_field", "set_about", "del_field", "del_about"):
        field = {"ник": "nick", "звание": "title", "девиз": "motto"}.get(g[0].lower(), "about") \
            if kind in ("set_field", "del_field") else "about"
        value = None if kind.startswith("del") else (g[1] if kind == "set_field" else g[0]).strip()
        if value and len(value) > LIMITS[field]:
            await ux.tell(message, f"❌ Слишком длинно: максимум {LIMITS[field]} символов.")
            return
        await db.set_profile_field(chat, me, field, value)
        await message.reply("✅ Сохранено." if value else "🗑 Удалено.")
        return
    if kind in ("my_profile", "whoami", "profile", "who"):
        token = g[0] if kind in ("profile", "who") else None
        if kind in ("profile", "who") and not token and reply is None:
            return  # «анкета»/«кто ты» без цели — просто слова
        target = (me, message.from_user.full_name) if kind in ("my_profile", "whoami") \
            else await resolve_user(db, token, reply)
        if target is None:
            return
        await message.reply(await _profile(bot, db, chat, target[0], target[1], now), disable_web_page_preview=True)
        return

    # ---- репутация ----
    if kind == "rep_give":
        if not cfg["rep_on"] or reply is None or reply.from_user is None:
            return
        tgt = reply.from_user
        if tgt.id == me or tgt.is_bot:
            return
        if not await db.take_quota(chat, f"rep{me}", now, REP_DAILY):
            await ux.tell(message, "⚠️ Вы исчерпали лимит оценок на сегодня.")
            return
        score = await db.change_rep(chat, me, tgt.id, 1 if g[0] == "+" else -1, now)
        if score is None:
            await db.refund_quota(chat, f"rep{me}", now)  # отказ по кулдауну не должен тратить дневной лимит
            await ux.tell(message, "⚠️ Вы уже оценивали этого человека за последний час.")
            return
        await ux.react(bot, chat, reply.message_id, "👍" if g[0] == "+" else "👎")      # реакция на сообщение вместо лишнего текста
        await message.answer(f"{'⭐' if g[0] == '+' else '👎'} Репутация {mention(tgt.id, tgt.full_name)}: <b>{score}</b>")
        return
    if kind == "rep_show":
        t = await resolve_user(db, g[0], reply) or (me, message.from_user.full_name)
        from bot import profile_card
        await message.reply(await profile_card.build(bot, db, chat, t[0], t[1], me, now), disable_web_page_preview=True)
        return
    if kind == "rep_top":
        rows = await db.top_rep(chat)
        body = "\n".join([f"{i}. {listed(u, (await db.user_name(u)) or f'id{u}')} — {s}" for i, (u, s) in enumerate(rows, 1)]) or "пока ни у кого"
        from bot.db import USERNAMES
        trows = [[str(i), ((await db.user_name(u)) or f"id{u}", f"https://t.me/{USERNAMES[u]}" if USERNAMES.get(u) else f"tg://user?id={u}"), str(s)]
                 for i, (u, s) in enumerate(rows, 1)]
        await ux.table_or_text(message, "Рейтинг репутации", ["#", "Участник", "Репутация"], trows,
                               "🏆 <b>Рейтинг репутации</b>\n" + body, aligns=["center", "left", "right"])
        return

    # ---- награды ----
    if kind in ("award", "unaward", "awards"):
        token = g[1] if kind == "award" else g[0]
        if kind == "awards":
            t = await resolve_user(db, token, reply) or (me, message.from_user.full_name)
            rows = await db.list_awards(chat, t[0])
            await message.reply(f"🏅 Награды {mention(*t)}: " + (" ".join(MEDALS[a["degree"]] for a in rows[-20:]) or "нет"))
            return
        need = need_rank(await db.get_access(chat), "награды")
        if await ms.effective_rank(bot, db, chat, me) < need:
            await ux.tell(message, f"⚠️ Награждать можно с ранга {need}.")
            return
        t = await resolve_user(db, token, reply)
        if t is None or t[0] == me:
            return
        if kind == "award":
            degree = int(g[0]) if g[0] else 1
            await db.add_award(chat, t[0], degree, me, now)
            await message.reply(f"{MEDALS[degree]} {mention(*t)} награждён!")
        else:
            await message.reply("Награда снята." if await db.remove_last_award(chat, t[0]) else "У него нет наград.")
        return

    # ---- заметки и закладки ----
    if kind in ("note_add", "bm_add"):
        k = "note" if kind == "note_add" else "bookmark"
        if k == "note":
            text = g[0].strip()[:300]
        else:
            if reply is None:
                await ux.tell(message, "⚠️ Ответьте на сообщение, которое нужно сохранить.")
                return
            snippet = (reply.text or reply.caption or "[медиа]").replace("\n", " ")[:80]
            link = chat_link(chat, reply.message_id)
            text = f"{snippet}" + (f"\n{link}" if link else "")
        ok = await db.add_note(chat, me, k, text, now)
        await message.reply("📝 Сохранено." if ok else "Слишком много записей (максимум 20): удалите лишние.")
        return
    if kind in ("notes", "bms"):
        k = "note" if kind == "notes" else "bookmark"
        rows = await db.list_notes(chat, me, k)
        body = "\n".join(f"{i}. {html.escape(r['text'])}" for i, r in enumerate(rows, 1)) or "пусто"
        await message.reply(("📝 <b>Заметки</b>\n" if k == "note" else "🔖 <b>Закладки</b>\n") + body,
                            disable_web_page_preview=True)
        return
    if kind in ("note_del", "bm_del"):
        k = "note" if kind == "note_del" else "bookmark"
        rows = await db.list_notes(chat, me, k)
        i = int(g[0])
        ok = 1 <= i <= len(rows) and await db.delete_note(chat, me, k, rows[i - 1]["id"])
        await message.reply("🗑 Удалено." if ok else "Нет записи с таким номером.")
        return

    # ---- таймеры ----
    if kind in ("timer_add", "timer_add1"):
        if kind == "timer_add1":  # «через час …» = «через 1 час …»
            g = ("1", g[0], g[1])
        sec = timer_delay(g[0], g[1])
        if sec is None:
            await ux.tell(message, "⚠️ Срок: от 1 минуты до 30 дней, например <code>таймер через 2 часа позвонить маме</code>.")
            return
        tid = await db.add_timer(chat, me, now + sec, g[2].strip()[:200])
        await message.reply("⏰ Таймер поставлен." if tid else "Слишком много таймеров (максимум 10).")
        return
    if kind == "timers":
        rows = await db.list_timers(chat, me)
        body = "\n".join(f"{i}. через {max((r['due'] - now) // 60, 0)} мин — {html.escape(r['text'])}"
                         for i, r in enumerate(rows, 1)) or "нет"
        await message.reply("⏰ <b>Таймеры</b>\n" + body)
        return
    if kind == "timer_del":
        rows = await db.list_timers(chat, me)
        i = int(g[0])
        ok = 1 <= i <= len(rows) and await db.delete_timer(rows[i - 1]["id"], me)
        await message.reply("🗑 Таймер удалён." if ok else "Нет таймера с таким номером.")


_STATUS_RU = {"creator": "Создатель чата", "administrator": "Администратор", "member": "Участник",
              "restricted": "Ограничен", "left": "Не в чате", "kicked": "Забанен"}


async def _tg_status(bot, chat: int, uid: int) -> str | None:
    try:
        m = await bot.get_chat_member(chat, uid)
    except Exception:
        return None
    if m.status == "restricted" and getattr(m, "can_send_messages", False):
        return _STATUS_RU["member"]   # после «размут» Telegram оставляет restricted, хотя писать можно
    return _STATUS_RU.get(m.status)


async def _profile(bot, db: Database, chat: int, uid: int, name: str, now: int) -> str:
    p = await db.get_profile(chat, uid)
    rank = await ms.effective_rank(bot, db, chat, uid)
    awards = "".join(MEDALS[a["degree"]] for a in (await db.list_awards(chat, uid))[-20:])
    sp = await Family(db).spouse(chat, uid)
    joined = await db.member_joined_at(chat, uid)
    uname = await db.get_username(uid)
    head = f"👤 <b>{mention(uid, name)}</b>" + (f" «{html.escape(p['nick'])}»" if p["nick"] else "")
    if p["title"]:
        head += f"\n<i>{html.escape(p['title'])}</i>"
    quote_lines = [x for x in ((f"💬 {html.escape(p['motto'])}" if p["motto"] else ""),
                               (f"📄 {html.escape(p['about'])}" if p["about"] else "")) if x]
    rows = [("ID", str(uid))]
    if uname:
        rows.append(("Ник", "@" + uname))
    status = await _tg_status(bot, chat, uid)
    if status:
        rows.append(("Статус", status))
    rows += [("Ранг", str(rank)), ("Репутация", str(await db.get_rep(chat, uid))),
             ("Сообщений", str(await db.user_total(chat, uid, None)))]
    warns = await db.get_warns(chat, uid)
    if warns:
        rows.append(("Варнов", str(warns)))
    if joined:
        rows.append(("В чате с", time.strftime("%d.%m.%Y", time.localtime(joined))))
    parts = [head]
    if quote_lines:
        parts.append(quote("\n".join(quote_lines), expandable=False))
    parts.append(kv_table(rows, key_width=10, value_width=24))
    if sp:
        parts.append(f"💍 В браке с {await _m(db, sp['partner'])}")
    if awards:
        parts.append(awards)
    return "\n".join(parts)


async def timer_watchdog(bot, db: Database) -> None:
    """Раз в 20 секунд доставляет сработавшие таймеры."""
    while True:
        await asyncio.sleep(20)
        try:
            for t in await db.due_timers(int(time.time())):
                if not await db.pop_timer(t["id"]):
                    continue
                try:
                    await bot.send_message(
                        t["chat_id"], f"⏰ {await _m(db, t['user_id'])}, напоминание: {html.escape(t['text'])}")
                except Exception:
                    pass
        except Exception:
            logging.exception("timer watchdog")
