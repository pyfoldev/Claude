"""«история @ник» — все наказания участника: когда, кто, срок, причина; активные сейчас; страницы по 10."""
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot.toggles import Enabled
from bot import mod_service as ms
from bot.db import Database
from bot.fmt import pre_table
from bot.ranks import need_rank
from bot.targets import resolve_user, listed

router = Router(name="history")
router.message.filter(Enabled("mod_on"))   # группу команд можно выключить в настройках → «Команды»
PER_PAGE = 10
_T = r"(@\w+|\d{5,})"
_RE = re.compile(r"^история(?:\s+" + _T + ")?$", re.IGNORECASE)


def _fmt_dur(sec: int | None) -> str:
    if not sec:
        return ""
    if sec % 86400 == 0:
        return f" на {sec // 86400} дн."
    if sec % 3600 == 0:
        return f" на {sec // 3600} ч."
    return f" на {max(sec // 60, 1)} мин."


def _short_dur(sec: int | None) -> str:
    if not sec:
        return ""
    if sec % 86400 == 0:
        return f" {sec // 86400} д"
    if sec % 3600 == 0:
        return f" {sec // 3600} ч"
    return f" {max(sec // 60, 1)} мин"


def _tz(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


async def render(bot, db: Database, chat: int, uid: int, page: int, now: int) -> tuple[str, InlineKeyboardMarkup | None]:
    cfg = await db.get_settings(chat)
    tz = _tz(cfg["tz"])
    total = await db.count_mod_history(chat, uid)
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    page = min(max(page, 0), pages - 1)
    name = listed(uid, (await db.user_name(uid)) or f"id{uid}")
    lines = [f"📜 <b>История: {name}</b> · <code>{uid}</code>"]
    active = []
    warns = await db.get_warns(chat, uid, now)
    if warns:
        active.append(f"варнов {warns}/{cfg['warn_limit']}")
    for kind, label in (("ban", "бан"), ("mute", "мут")):
        st = await db.get_state(chat, uid, kind, now)
        if st:
            left = "бессрочно" if st["until"] is None else "до " + datetime.fromtimestamp(st["until"], tz).strftime("%d.%m %H:%M")
            active.append(f"{label} {left}")
    lines.append("⚡️ Сейчас: " + "; ".join(active) if active else "✅ Сейчас без наказаний")
    reports_total, reports_open = await db.count_reports_against(chat, uid)
    if reports_total:
        lines.append(f"📣 Жалоб: {reports_total} (открытых {reports_open})")
    if not total:
        lines.append("В журнале чисто.")
        return "\n".join(lines), None
    rows = []
    for r in await db.list_mod_history(chat, uid, PER_PAGE, page * PER_PAGE):
        by = listed(r["actor_id"], (await db.user_name(r["actor_id"])) or f"id{r['actor_id']}", 14) if r["actor_id"] else "—"
        what = r["action"] + _short_dur(r["duration"]) + (f" · {r['reason']}" if r["reason"] else "")
        rows.append((datetime.fromtimestamp(r["ts"], tz).strftime("%d.%m %H:%M"), what, by))
    lines.append(pre_table(rows, header=("Когда", "Что", "Кто"), maxw=(11, 18, 9)))
    lines.append(f"<i>Записей {total} · стр. {page + 1}/{pages}</i>")
    kb = None
    if pages > 1:
        row = []
        if page > 0:
            row.append(B(text="◀️", callback_data=f"hist:{uid}:{page - 1}"))
        if page < pages - 1:
            row.append(B(text="▶️", callback_data=f"hist:{uid}:{page + 1}"))
        kb = InlineKeyboardMarkup(inline_keyboard=[row])
    return "\n".join(lines), kb


async def _allowed(bot, db: Database, chat: int, user: int) -> bool:
    rank = await ms.effective_rank(bot, db, chat, user)
    return rank >= need_rank(await db.get_access(chat), "история")


@router.message(F.text.func(lambda t: bool(t) and _RE.match(t.strip()) is not None))
async def history_cmd(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    token = _RE.match(message.text.strip()).group(1)
    target = await resolve_user(db, token, ms.real_reply(message))
    if target is None:
        return  # «история» без цели — просто слово
    chat = message.chat.id
    if not await _allowed(bot, db, chat, message.from_user.id):
        return
    text, kb = await render(bot, db, chat, target[0], 0, int(time.time()))
    await message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("hist:"))
async def history_page(cb: CallbackQuery, bot, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or not parts[1].lstrip("-").isdigit() or not parts[2].isdigit() or cb.message is None:
        await cb.answer()
        return
    chat = cb.message.chat.id
    if not await _allowed(bot, db, chat, cb.from_user.id):
        await cb.answer("Нужен ранг модератора", show_alert=True)
        return
    text, kb = await render(bot, db, chat, int(parts[1]), int(parts[2]), int(time.time()))
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass
    await cb.answer()
