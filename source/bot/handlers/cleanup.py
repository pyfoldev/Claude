"""Массовая чистка чата: «кик неактив 30д», «кик новичков 1д», «кик молчунов 14д» — только с подтверждением."""
import asyncio
import re
import time
import uuid
from datetime import timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import ux
from bot.toggles import Enabled
from bot import mod_service as ms
from bot.cleanup import activity, pick_candidates
from bot.db import Database
from bot.parsing import parse_period
from bot.ranks import need_rank
from bot.targets import listed

router = Router(name="cleanup")
router.message.filter(Enabled("mod_on"))   # группу команд можно выключить в настройках → «Команды»
_RE = re.compile(r"^кик\s+(неактив|новичков|молчунов)\s+(.+)$", re.IGNORECASE)
_LIST_RE = re.compile(r"^кто\s+неактив(?:ные|ных)?(?:\s+(.+))?$", re.IGNORECASE)
_BARE_DAYS = re.compile(r"^(\d{1,4})$")
DEFAULT_DAYS = 1
LIST_LIMIT = 15
BUCKETS = (1, 3, 7, 14, 30, 90)
_pending: dict[str, dict] = {}
TTL = 120
KICK_DELAY = 0.05


def _period(text: str):
    """«30д», «2 недели» или просто «30» (дни) → timedelta; иначе None."""
    b = _BARE_DAYS.match(text.strip())
    if b:
        d = int(b.group(1))
        return timedelta(days=d) if 1 <= d <= 366 else None
    return parse_period(text)


def _parse(text: str | None):
    m = _RE.match((text or "").strip())
    if not m:
        return None
    period = _period(m.group(2))
    return (m.group(1).lower(), period) if period else None


def _parse_list(text: str | None):
    """«кто неактив» (30 дней) / «кто неактив 14» / «кто неактив 2 недели» → timedelta; не наша фраза → None."""
    m = _LIST_RE.match((text or "").strip())
    if not m:
        return None
    return _period(m.group(1)) if m.group(1) else timedelta(days=DEFAULT_DAYS)


@router.message(F.text.func(lambda t: _parse_list(t) is not None))
async def inactive_list(message: Message, bot, db: Database) -> None:
    """«кто неактив [срок]» — учёт неактивных: сводка по срокам и список тех, кто давно не появлялся (самые давние первыми)."""
    if message.chat.type not in ("group", "supergroup"):
        return
    chat, me = message.chat.id, message.from_user.id
    if await ms.effective_rank(bot, db, chat, me) < need_rank(await db.get_access(chat), "неактивные"):
        return                                   # «кто неактив» без прав — обычная фраза, не отвечаем
    period = _parse_list(message.text)
    now = int(time.time())
    exclude = {(await bot.me()).id} | {r["user_id"] for r in await db.list_ranks(chat)}
    try:
        exclude |= {a.user.id for a in await bot.get_chat_administrators(chat)}
    except Exception:
        pass
    members = [m for m in await db.members_info(chat) if m["user_id"] not in exclude]
    last_msg = await db.last_messages(chat)
    info: dict[int, int] = {}                      # uid -> сколько дней без сообщений
    for m in members:
        ts, _ = activity(m, last_msg)              # последнее сообщение, а если не писал — момент входа
        if ts is not None:
            info[m["user_id"]] = (now - ts) // 86400
    limit = max(int(period.total_seconds()) // 86400, 1)
    rows = sorted(((d, uid) for uid, d in info.items() if d >= limit), reverse=True)
    if not rows:
        await message.reply(f"🕰 Неактивных {limit}+ дн. нет.")
        return
    lines = []
    for i, (d, uid) in enumerate(rows[:LIST_LIMIT], 1):
        lines.append(f"{i}. {listed(uid, (await db.user_name(uid)) or f'id{uid}')} — {d} дн.")
    more = f"\n…и ещё {len(rows) - LIST_LIMIT}" if len(rows) > LIST_LIMIT else ""
    await message.reply(
        f"🕰 <b>Неактивные {limit}+ дн.:</b> {len(rows)}\n" + "\n".join(lines) + more
        + f"\n\nКик всех: <code>кик неактив {limit}д</code>")


@router.message(F.text.func(lambda t: _parse(t) is not None))
async def mass_kick(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup"):
        return
    kind, period = _parse(message.text)
    chat, me = message.chat.id, message.from_user.id
    need = need_rank(await db.get_access(chat), "массовый кик")
    if await ms.effective_rank(bot, db, chat, me) < need:
        await ux.tell(message, f"⚠️ Массовая чистка доступна с ранга {need}.")
        return
    now = int(time.time())
    exclude = {me, (await bot.me()).id} | {r["user_id"] for r in await db.list_ranks(chat)}
    try:
        exclude |= {a.user.id for a in await bot.get_chat_administrators(chat)}
    except Exception:
        await ux.tell(message, "❌ Не смог получить список админов — чистка отменена из осторожности.")
        return
    ids = pick_candidates(kind, await db.members_info(chat), await db.writers(chat), now,
                          int(period.total_seconds()), exclude, last_msg=await db.last_messages(chat))
    if not ids:
        await ux.tell(message, "❌ Подходящих участников не нашёл.")
        return
    for k in [k for k, v in _pending.items() if v["expires"] < now]:
        _pending.pop(k, None)
    pid = uuid.uuid4().hex[:8]
    _pending[pid] = {"chat": chat, "actor": me, "ids": ids, "expires": now + TTL}
    preview = ", ".join([listed(u, (await db.user_name(u)) or f"id{u}") for u in ids[:10]])
    await message.reply(
        f"⚠️ Исключить <b>{len(ids)}</b> чел.: {preview}" + (" …" if len(ids) > 10 else ""),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            B(text="✅ Исключить", callback_data=f"cln:{pid}:yes", style="danger"), B(text="Отмена", callback_data=f"cln:{pid}:no")]]),
        disable_web_page_preview=True)


@router.callback_query(F.data.startswith("cln:"))
async def confirm(cb: CallbackQuery, bot, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or parts[2] not in ("yes", "no"):
        await cb.answer()
        return
    _, pid, op = parts
    p = _pending.get(pid)
    if p is None or cb.message is None or p["chat"] != cb.message.chat.id or p["expires"] < time.time():
        _pending.pop(pid, None)
        await cb.answer("Запрос устарел.", show_alert=True)
        return
    if cb.from_user.id != p["actor"]:
        await cb.answer("Подтвердить может только автор команды.", show_alert=True)
        return
    _pending.pop(pid, None)
    if op == "no":
        await cb.message.edit_text("Отменено.")
        await cb.answer()
        return
    need = need_rank(await db.get_access(p["chat"]), "массовый кик")
    if await ms.effective_rank(bot, db, p["chat"], cb.from_user.id) < need:   # ранг могли снять, пока висел запрос
        await cb.message.edit_text("Отменено: у автора больше нет прав на массовую чистку.")
        await cb.answer()
        return
    await cb.answer("Исключаю…")
    ok = 0
    for uid in p["ids"]:
        try:
            # С момента составления списка участник мог получить ранг или уже выйти.
            if await db.get_rank(p["chat"], uid):
                continue
            member = await bot.get_chat_member(p["chat"], uid)
            if member.status not in ("member", "restricted") or (member.status == "restricted" and not getattr(member, "is_member", False)):
                continue
            await bot.ban_chat_member(p["chat"], uid)
            await bot.unban_chat_member(p["chat"], uid)
            await db.set_member_active(p["chat"], uid, False)
            ok += 1
        except Exception:
            pass
        await asyncio.sleep(KICK_DELAY)
    await db.log_action(p["chat"], p["actor"], 0, "массовый кик", f"{ok}/{len(p['ids'])}", int(time.time()))
    await cb.message.edit_text(f"🧹 Исключено {ok} из {len(p['ids'])}.")
