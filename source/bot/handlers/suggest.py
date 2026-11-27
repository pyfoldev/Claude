"""Предложка: «+предложка текст» в чате → владелец смотрит в личке бота («предложки»), принимает, отклоняет, удаляет.

Смотреть может тот, у кого в чате ранг из ДК «предложка» (по умолчанию 5 — владелец чата), и владелец бота.
О новой предложке владелец чата получает сообщение в личку (если запускал бота); автор — о решении."""
from __future__ import annotations

import html
import re
import time
from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import ux
from bot import mod_service as ms
from bot.db import Database
from bot.fmt import quote
from bot.giveaway import tz_of
from bot.ranks import need_rank
from bot.targets import listed
from bot.toggles import Enabled

router = Router(name="suggest")
router.message.filter(Enabled("suggest_on"))   # группу команд можно выключить в настройках → «Команды»
ACCESS_KEY = "предложка"
DAILY = 3                 # предложек в сутки от одного человека в одном чате
MIN_LEN, MAX_LEN = 3, 1000
STATUS = {"new": "🆕 новая", "accepted": "✅ принята", "rejected": "❌ отклонена"}

_ADD = re.compile(r"^\+предложк[аи](?:\s+(.+))?$", re.IGNORECASE | re.DOTALL)
_VIEW = re.compile(r"^(?:предложк[аи]|/suggestions(?:@\w+)?)$", re.IGNORECASE)
_START = re.compile(r"^/start sugg_(-?\d{1,20})$")


async def can_view(bot, db: Database, chat_id: int, user_id: int, owner_ids: frozenset) -> bool:
    if user_id in owner_ids:
        return True
    try:
        rank = await ms.effective_rank(bot, db, chat_id, user_id)
    except Exception:
        return False
    return rank >= need_rank(await db.get_access(chat_id), ACCESS_KEY)


async def _notify(bot, user_id: int, text: str, kb: InlineKeyboardMarkup | None = None) -> None:
    try:
        await bot.send_message(user_id, text, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        pass                              # человек не запускал бота — молча


# ---------- в чате ----------

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: bool(t) and _ADD.match(t.strip()) is not None))
async def add_cmd(message: Message, bot, db: Database) -> None:
    u = message.from_user
    if u is None or u.is_bot:
        return
    chat, now = message.chat.id, int(time.time())
    text = (_ADD.match(message.text.strip()).group(1) or "").strip()
    if len(text) < MIN_LEN:
        await ux.tell(message, "⚠️ Напишите идею сразу после команды: <code>+предложка сделать ночной режим в чате</code>")
        return
    if len(text) > MAX_LEN:
        await ux.tell(message, f"❌ Слишком длинно: до {MAX_LEN} символов.")
        return
    if not await db.take_quota(chat, f"sugg{u.id}", now, DAILY):
        await ux.tell(message, f"⚠️ Лимит предложек на сегодня — {DAILY}. Завтра можно ещё 🙂")
        return
    sid = await db.sugg_add(chat, u.id, u.full_name, text, now)
    await message.reply(f"📤 Предложка №{sid} отправлена владельцу чата. Спасибо!")
    try:                                                  # владельцу чата — сразу в личку, с кнопками
        creator = next(a.user.id for a in await bot.get_chat_administrators(chat) if a.status == "creator")
    except Exception:
        creator = None
    if creator and creator != u.id:
        await _notify(bot, creator, f"📤 Новая предложка №{sid} в «{html.escape(message.chat.title or 'чат')}» "
                                    f"от {listed(u.id, u.full_name)}:\n" + quote(html.escape(text), expandable=len(text) > 300),
                      _actions_kb(sid, chat, 0, "new", single=True))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: bool(t) and _VIEW.match(t.strip()) is not None))
async def view_in_group(message: Message, bot, db: Database, owner_ids: frozenset = frozenset()) -> None:
    if message.from_user is None or not await can_view(bot, db, message.chat.id, message.from_user.id, owner_ids):
        return                                            # остальным — просто слово
    new, total = await db.sugg_counts(message.chat.id)
    username = (await bot.me()).username
    await message.reply(f"📤 Предложка: новых {new}, всего {total}. Разбирать — в личке с ботом:",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                            B(text="📤 Открыть предложку", url=f"https://t.me/{username}?start=sugg_{message.chat.id}")]]))


# ---------- в личке ----------

def _actions_kb(sid: int, chat: int, idx: int, flt: str, single: bool = False, has_prev: bool = False,
                has_next: bool = False, is_new: bool = True) -> InlineKeyboardMarkup:
    tail = f"{chat}:{idx}:{flt}"
    rows = []
    if is_new:
        rows.append([B(text="✅ Принять", callback_data=f"sga:{sid}:acc:{tail}"),
                     B(text="❌ Отклонить", callback_data=f"sga:{sid}:rej:{tail}")])
    if single:
        rows.append([B(text="📤 Вся предложка", callback_data=f"sg:{chat}:0:new")])
        return InlineKeyboardMarkup(inline_keyboard=rows)
    nav = []
    if has_prev:
        nav.append(B(text="◀️", callback_data=f"sg:{chat}:{idx - 1}:{flt}"))
    nav.append(B(text="🗑 Удалить", callback_data=f"sga:{sid}:del:{tail}"))
    if has_next:
        nav.append(B(text="▶️", callback_data=f"sg:{chat}:{idx + 1}:{flt}"))
    rows.append(nav)
    rows.append([B(text="Показать все" if flt == "new" else "Только новые",
                   callback_data=f"sg:{chat}:0:{'all' if flt == 'new' else 'new'}"),
                 B(text="⬅️ Чаты", callback_data="sg:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _card(db: Database, chat: int, idx: int, flt: str) -> tuple[str, InlineKeyboardMarkup]:
    items = await db.sugg_list(chat, only_new=(flt == "new"))
    title = (await db.get_chat(chat) or {}).get("title") or str(chat)
    new, total = await db.sugg_counts(chat)
    if not items:
        empty = "Новых предложек нет 🎉" if flt == "new" else "Предложек пока нет."
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            B(text="Показать все" if flt == "new" else "Только новые", callback_data=f"sg:{chat}:0:{'all' if flt == 'new' else 'new'}"),
            B(text="⬅️ Чаты", callback_data="sg:list")]])
        return f"📤 <b>Предложка · {html.escape(title)}</b>\n{empty}\n<i>Новых {new}, всего {total}.</i>", kb
    idx = max(0, min(idx, len(items) - 1))
    s = items[idx]
    tz = tz_of((await db.get_settings(chat))["tz"])
    when = datetime.fromtimestamp(s["ts"], tz).strftime("%d.%m %H:%M")
    head = f"📤 <b>Предложка №{s['id']}</b> · {html.escape(title)}\n"
    author = listed(s["user_id"], (await db.user_name(s["user_id"])) or s["user_name"] or f"id{s['user_id']}")
    author += f" · <code>{s['user_id']}</code>"
    body = (f"от {author} · {when}\n"
            + quote(html.escape(s["text"]), expandable=len(s["text"]) > 400)
            + f"\nСтатус: {STATUS.get(s['status'], s['status'])}"
            + f"\n<i>{idx + 1} из {len(items)} · {'только новые' if flt == 'new' else 'все'} · новых {new}, всего {total}</i>")
    kb = _actions_kb(s["id"], chat, idx, flt, has_prev=idx > 0, has_next=idx < len(items) - 1, is_new=s["status"] == "new")
    return head + body, kb


async def _chats_view(bot, db: Database, uid: int, owner_ids: frozenset) -> tuple[str, InlineKeyboardMarkup | None, list[int]]:
    rows, ids = [], []
    for c in await db.list_chats(0, 500, active_only=True):
        if not await can_view(bot, db, c["chat_id"], uid, owner_ids):
            continue
        new, total = await db.sugg_counts(c["chat_id"])
        if uid in owner_ids and not total and not await _is_chat_admin(bot, c["chat_id"], uid):
            continue                     # владельцу бота не показываем чужие чаты, где предложек нет вовсе
        ids.append(c["chat_id"])
        label = (c["title"] or str(c["chat_id"]))[:40] + (f" · 🆕 {new}" if new else f" · {total}")
        rows.append([B(text=label, callback_data=f"sg:{c['chat_id']}:0:new")])
    if not rows:
        return ("📤 Нет чатов, где вы можете смотреть предложку. Её разбирает владелец чата "
                "(или ранг из «дк» → «предложка»)."), None, ids
    return "📤 <b>Предложка</b> — выберите чат:", InlineKeyboardMarkup(inline_keyboard=rows[:50]), ids


async def _is_chat_admin(bot, chat: int, uid: int) -> bool:
    try:
        return (await ms.get_member(bot, chat, uid)).status in ("administrator", "creator")
    except Exception:
        return False


@router.message(F.chat.type == "private", F.text.func(lambda t: bool(t) and (_VIEW.match(t.strip()) or _START.match(t.strip())) is not None))
async def view_private(message: Message, bot, db: Database, owner_ids: frozenset = frozenset()) -> None:
    uid = message.from_user.id
    m = _START.match(message.text.strip())
    if m:
        chat = int(m.group(1))
        if not await can_view(bot, db, chat, uid, owner_ids):
            await ux.tell(message, "⚠️ Смотреть предложку этого чата может только его владелец.")
            return
        text, kb = await _card(db, chat, 0, "new")
        await message.answer(text, reply_markup=kb, disable_web_page_preview=True)
        return
    text, kb, ids = await _chats_view(bot, db, uid, owner_ids)
    if len(ids) == 1:                                        # один чат — сразу открываем
        text, kb = await _card(db, ids[0], 0, "new")
    await message.answer(text, reply_markup=kb, disable_web_page_preview=True)


@router.callback_query(F.data.startswith("sg:"))
async def nav_cb(cb: CallbackQuery, bot, db: Database, owner_ids: frozenset = frozenset()) -> None:
    parts = cb.data.split(":")
    if cb.message is None:
        await cb.answer()
        return
    if parts[1] == "list":
        text, kb, _ = await _chats_view(bot, db, cb.from_user.id, owner_ids)
    else:
        if len(parts) != 4 or not parts[2].isdigit() or parts[3] not in ("new", "all"):
            await cb.answer()
            return
        chat = int(parts[1])
        if not await can_view(bot, db, chat, cb.from_user.id, owner_ids):
            await cb.answer("Нет доступа к предложке этого чата.", show_alert=True)
            return
        text, kb = await _card(db, chat, int(parts[2]), parts[3])
    try:
        await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        await ux.tell_cb(cb, text, reply_markup=kb)
        return
    await cb.answer()


@router.callback_query(F.data.startswith("sga:"))
async def action_cb(cb: CallbackQuery, bot, db: Database, owner_ids: frozenset = frozenset()) -> None:
    parts = cb.data.split(":")
    if len(parts) != 6 or not parts[1].isdigit() or parts[2] not in ("acc", "rej", "del") or cb.message is None:
        await cb.answer()
        return
    s = await db.sugg_get(int(parts[1]))
    if s is None:
        await cb.answer("Эта предложка уже удалена.", show_alert=True)
        return
    if not await can_view(bot, db, s["chat_id"], cb.from_user.id, owner_ids):   # права — по чату самой предложки
        await cb.answer("Нет доступа к предложке этого чата.", show_alert=True)
        return
    now = int(time.time())
    title = (await db.get_chat(s["chat_id"]) or {}).get("title") or "чат"
    op = parts[2]
    if op == "del":
        await db.sugg_delete(s["id"])
        await cb.answer("Удалено")
    else:
        status = "accepted" if op == "acc" else "rejected"
        if not await db.sugg_decide(s["id"], status, cb.from_user.id, now):
            await cb.answer("Уже разобрана.", show_alert=True)
        else:
            await cb.answer("Принято ✅" if op == "acc" else "Отклонено")
            await _notify(bot, s["user_id"], (f"✅ Ваша предложка №{s['id']} в «{html.escape(title)}» принята! Спасибо 💜"
                                              if op == "acc" else
                                              f"Ваша предложка №{s['id']} в «{html.escape(title)}» отклонена. Не сдавайтесь 🙂"))
    try:
        # Данные навигации могут устареть или быть подменены: используем чат самой предложки.
        idx, flt = int(parts[4]), parts[5]
        text, kb = await _card(db, s["chat_id"], idx, flt if flt in ("new", "all") else "new")
        await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        pass
