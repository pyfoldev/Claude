"""Коллекционные карточки: «карточка» (раз в 12 часов), «альбом», «каталог», «топ карточек», «обмен 12 на 15» ответом."""
from __future__ import annotations

import html
import re
import time
import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import collectibles as col
from bot import ux
from bot.db import Database
from bot.mod_service import real_reply
from bot.targets import listed, mention, resolve_user
from bot.toggles import Enabled

router = Router(name="collect")
router.message.filter(Enabled("cards_on"))

_T = r"(@\w+|\d{5,})"
_PATTERNS = [
    ("find", r"^(?:карточка|кк)$"),
    ("album", r"^альбом(?:\s+" + _T + ")?$"),
    ("catalog", r"^каталог(?:\s+карточек)?(?:\s+(.+))?$"),
    ("top", r"^топ карточек$"),
    ("view", r"^карточка\s+(.+)$"),
    ("trade", r"^обмен\s+#?(\d{1,3})\s+на\s+#?(\d{1,3})$"),
]
_COMPILED = [(k, re.compile(p, re.IGNORECASE)) for k, p in _PATTERNS]
OFFER_TTL = 120
_offers: dict[str, dict] = {}


def parse(text: str | None):
    t = re.sub(r"\s+", " ", (text or "").strip())
    for kind, rx in _COMPILED:
        m = rx.match(t)
        if m:
            return kind, m.groups()
    return None


def _fmt_wait(sec: int) -> str:
    return f"{sec // 3600} ч {sec % 3600 // 60} мин" if sec >= 3600 else f"{max(sec // 60, 1)} мин"


def render_album(owned: dict[int, int]) -> str:
    lines = []
    for s, (title, items) in enumerate(col.SERIES.items()):
        row = ""
        for i, (emoji_, _) in enumerate(items):
            cid = s * 10 + i + 1
            row += (emoji_ if owned.get(cid, 0) else "▫️")
        have = sum(1 for i in range(len(items)) if owned.get(s * 10 + i + 1, 0))
        lines.append(f"{title} {have}/{len(items)}\n{row}")
    uniq = sum(1 for n in owned.values() if n)
    return f"📚 Собрано {uniq}/{col.TOTAL}\n\n" + "\n".join(lines)


@router.message(F.text.func(lambda t: parse(t) is not None))
async def on_cards(message: Message, db: Database) -> None:
    if message.from_user is None:
        return
    kind, g = parse(message.text)
    uid, now = message.from_user.id, int(time.time())

    if kind == "find":
        cid = col.draw()
        wait = await db.cards_try_find(uid, cid, now, col.COOLDOWN)
        if wait is not None:
            await ux.tell(message, f"🕐 Следующая карточка через {_fmt_wait(wait)}.")
            return
        owned = await db.cards_of(uid)
        extra = "" if owned.get(cid, 0) <= 1 else f"\n♻️ Это дубль (у вас {owned[cid]}) — можно обменять: <code>обмен {cid} на …</code>"
        await message.reply(f"🃏 Вам выпала карточка!\n<b>{html.escape(col.label(cid))}</b>\n"
                            f"<i>{col.RARITY_NAME[col.CARDS[cid]['rarity']]} · серия {html.escape(col.CARDS[cid]['series'])}</i>{extra}")
    elif kind == "album":
        reply = real_reply(message)
        target = await resolve_user(db, g[0], reply) if (g[0] or reply) else (uid, message.from_user.full_name)
        if target is None:
            await ux.tell(message, "⚠️ Не нашёл такого участника.")
            return
        tid, name = target
        owned = await db.cards_of(tid)
        spare = sum(n - 1 for n in owned.values() if n > 1)
        await message.reply(f"{listed(tid, name)}\n{render_album(owned)}\n♻️ Запасных копий: {spare}",
                            disable_web_page_preview=True)
    elif kind == "catalog":
        arg = (g[0] or "").strip().lower()
        if not arg:
            owned = await db.cards_of(uid)
            lines = [f"{t}: {h}/{n}" for t, h, n in col.series_progress(owned)]
            await message.reply("🗂 <b>Каталог карточек</b>\n" + "\n".join(lines) +
                                "\n<i>Серия подробно: </i><code>каталог космос</code>\n"
                                f"<i>Шансы: {', '.join(f'{r[1]} {r[0]} {r[2]}%' for r in col.RARITY)}</i>")
            return
        title = next((t for t in col.SERIES if arg in t.lower()), None)
        if title is None:
            await ux.tell(message, "⚠️ Нет такой серии. Список — <code>каталог</code>.")
            return
        owned = await db.cards_of(uid)
        s = list(col.SERIES).index(title)
        lines = []
        for i in range(len(col.SERIES[title])):
            cid = s * 10 + i + 1
            mark = "✅" if owned.get(cid, 0) else "▫️"
            lines.append(f"{mark} {col.label(cid)}" + (f" ×{owned[cid]}" if owned.get(cid, 0) > 1 else ""))
        await message.reply(f"🗂 <b>{html.escape(title)}</b>\n" + "\n".join(lines))
    elif kind == "top":
        rows = await db.cards_top(10)
        if not rows:
            await message.reply("🏆 Коллекционеров пока нет — начните с команды <code>карточка</code>.")
            return
        lines = []
        for i, r in enumerate(rows, 1):
            name = (await db.user_name(r["user_id"])) or f"id{r['user_id']}"
            lines.append(f"{i}. {listed(r['user_id'], name, 24)} — {r['uniq']}/{col.TOTAL} (всего {r['total']})")
        await message.reply("🏆 <b>Топ коллекционеров</b>\n" + "\n".join(lines), disable_web_page_preview=True)
    elif kind == "view":
        cid = col.find(g[0])
        if cid is None:
            await ux.tell(message, "⚠️ Не нашёл такую карточку (укажите номер или точное название).")
            return
        owned = (await db.cards_of(uid)).get(cid, 0)
        c = col.CARDS[cid]
        await message.reply(f"🃏 <b>{html.escape(col.label(cid))}</b>\n{col.RARITY_NAME[c['rarity']]} · {html.escape(c['series'])}\n"
                            f"У вас: {owned}")
    elif kind == "trade":
        reply = real_reply(message)
        if reply is None or reply.from_user is None or reply.from_user.is_bot or reply.from_user.id == uid:
            await ux.tell(message, "⚠️ Напишите <code>обмен 12 на 15</code> ответом на сообщение того, с кем меняетесь.")
            return
        give, get = int(g[0]), int(g[1])
        other = reply.from_user.id
        why = col.can_trade(await db.cards_of(uid), give, await db.cards_of(other), get)
        if why:
            await ux.tell(message, f"⚠️ Обмен невозможен: {why}.")
            return
        if len(_offers) > 500:
            for k in [k for k, v in _offers.items() if v["exp"] < now]:
                _offers.pop(k, None)
        oid = uuid.uuid4().hex[:8]
        _offers[oid] = {"a": uid, "b": other, "give": give, "get": get, "chat": message.chat.id, "exp": now + OFFER_TTL}
        kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="✅ Согласен", callback_data=f"ctr:{oid}:y"),
                                                    B(text="❌ Нет", callback_data=f"ctr:{oid}:n")]])
        await message.reply(f"🔁 {mention(uid, message.from_user.full_name)} предлагает {mention(other, reply.from_user.full_name)} обмен:\n"
                            f"отдаёт {html.escape(col.label(give))}\nхочет {html.escape(col.label(get))}", reply_markup=kb)


@router.callback_query(F.data.startswith("ctr:"))
async def on_trade(cb: CallbackQuery, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or cb.message is None:
        await cb.answer()
        return
    offer = _offers.get(parts[1])
    now = int(time.time())
    if offer is None or offer["exp"] < now:
        _offers.pop(parts[1], None)
        await cb.answer("Предложение устарело.", show_alert=True)
        return
    uid = cb.from_user.id
    if parts[2] == "n":
        if uid not in (offer["a"], offer["b"]):
            await cb.answer("Это не ваш обмен.", show_alert=True)
            return
        _offers.pop(parts[1], None)
        await cb.message.edit_text("❌ Обмен отменён.", reply_markup=None)
        await cb.answer()
        return
    if uid != offer["b"]:
        await cb.answer("Согласиться может только тот, кому предложили.", show_alert=True)
        return
    _offers.pop(parts[1], None)                       # одно предложение — один обмен, даже при быстром двойном нажатии
    ok = await db.cards_swap(offer["a"], offer["give"], offer["b"], offer["get"])
    await cb.message.edit_text("✅ Обмен состоялся!" if ok else "⚠️ Не вышло: у кого-то уже нет запасной копии.", reply_markup=None)
    await cb.answer()
