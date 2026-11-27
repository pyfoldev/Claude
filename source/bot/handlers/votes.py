"""Голосование за временный мут нарушителя: «гб @ник» / «гб» ответом."""
import datetime
import html
import re
import time
import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import ux
from bot import mod_service as ms
from bot.db import Database
from bot.parsing import ModCommand
from bot.targets import mention, resolve_user

router = Router(name="votes")
VOTES_NEEDED = 5
VOTER_MIN_MESSAGES = 10
VOTE_TTL = 600
MUTE_SECONDS = 86400
_RE = re.compile(r"^гб(?:\s+(@\w+|\d{5,}|стоп))?$", re.IGNORECASE)
_votes: dict[str, dict] = {}


def _kb(vid: str, n: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        B(text=f"🗳 За мут на сутки ({n}/{VOTES_NEEDED})", callback_data=f"vote:{vid}:y")]])


@router.message(F.text.func(lambda t: bool(t) and _RE.match(t.strip()) is not None))
async def start_vote(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup"):
        return
    chat, me = message.chat.id, message.from_user.id
    token = _RE.match(message.text.strip()).group(1)
    now = time.time()
    for k in [k for k, v in _votes.items() if v["expires"] < now]:
        _votes.pop(k, None)
    if token == "стоп":
        if await ms.effective_rank(bot, db, chat, me) >= 1:
            for k in [k for k, v in _votes.items() if v["chat"] == chat]:
                _votes.pop(k)
            await ux.tell(message, "⚠️ Голосования в этом чате остановлены.")
        return
    target = await resolve_user(db, token, ms.real_reply(message))
    if target is None:
        return  # «гб» без цели — просто буквы
    tid, tname = target
    if await db.user_total(chat, me, None) < VOTER_MIN_MESSAGES:
        await ux.tell(message, f"⚠️ Начинать голосование можно после {VOTER_MIN_MESSAGES} сообщений в чате.")
        return
    if tid == me or tid == (await bot.me()).id:
        await ux.tell(message, "⚠️ Нужен другой человек.")
        return
    try:
        tm = await ms.get_member(bot, chat, tid)
    except Exception:
        await ux.tell(message, "❌ Не нашёл такого участника в чате.")
        return
    if tm.status in ("left", "kicked") or (tm.status == "restricted" and not getattr(tm, "is_member", False)):
        await ux.tell(message, "⚠️ Этот человек больше не участвует в чате.")
        return
    if tm.status in ("administrator", "creator"):
        await ux.tell(message, "⚠️ Администраторов голосованием наказывать нельзя.")
        return
    if await db.get_rank(chat, tid):
        await ux.tell(message, "⚠️ Модераторов голосованием наказывать нельзя.")
        return
    if any(v["chat"] == chat and v["target"] == tid for v in _votes.values()):
        await ux.tell(message, "⚠️ Голосование против этого человека уже идёт.")
        return
    vid = uuid.uuid4().hex[:8]
    _votes[vid] = {"chat": chat, "target": tid, "tname": tname, "voters": {me}, "expires": now + VOTE_TTL}
    try:
        await message.answer(
            f"⚖️ Голосование: {mention(tid, tname)} — мут на сутки?\nНужно {VOTES_NEEDED} голосов за 10 минут. "
            "Голосуют участники, написавшие в чате не меньше 10 сообщений.", reply_markup=_kb(vid, 1))
    except BaseException:
        _votes.pop(vid, None)
        raise


@router.callback_query(F.data.startswith("vote:"))
async def vote_cb(cb: CallbackQuery, bot, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or parts[2] != "y":
        await cb.answer()
        return
    _, vid, _op = parts
    v = _votes.get(vid)
    if v is None or cb.message is None or v["chat"] != cb.message.chat.id or v["expires"] < time.time():
        _votes.pop(vid, None)
        await cb.answer("Голосование закончено.", show_alert=True)
        return
    uid = cb.from_user.id
    if uid == v["target"]:
        await cb.answer("Против себя голосовать нельзя.", show_alert=True)
        return
    if uid in v["voters"]:
        await cb.answer("Вы уже проголосовали.", show_alert=True)
        return
    try:
        member = await bot.get_chat_member(v["chat"], uid)
        if member.status in ("left", "kicked") or (member.status == "restricted" and not getattr(member, "is_member", False)):
            await cb.answer("Голосовать могут только участники чата.", show_alert=True)
            return
    except Exception:
        await cb.answer("Не удалось проверить участие в чате. Попробуйте ещё раз.", show_alert=True)
        return
    if await db.user_total(v["chat"], uid, None) < VOTER_MIN_MESSAGES:
        await cb.answer(f"Голосовать могут те, у кого от {VOTER_MIN_MESSAGES} сообщений в чате.", show_alert=True)
        return
    v["voters"].add(uid)
    if len(v["voters"]) < VOTES_NEEDED:
        await cb.message.edit_reply_markup(reply_markup=_kb(vid, len(v["voters"])))
        await cb.answer("Голос учтён.")
        return
    if _votes.pop(vid, None) is None:  # второе одновременное нажатие на пороге не должно мутить повторно
        await cb.answer()
        return
    now = int(time.time())
    try:
        target = await bot.get_chat_member(v["chat"], v["target"])
        if (target.status in ("administrator", "creator", "left", "kicked") or
                (target.status == "restricted" and not getattr(target, "is_member", False)) or
                await db.get_rank(v["chat"], v["target"])):
            await cb.message.edit_text("⚖️ Голосование закрыто: участник вышел из чата или получил полномочия.")
            await cb.answer()
            return
        await ms.apply(bot, db, ModCommand("мут", None, datetime.timedelta(seconds=MUTE_SECONDS),
                                           "решение голосования"), v["chat"], (await bot.me()).id, v["target"], now)
        await cb.message.edit_text(f"⚖️ Голосование завершено: {mention(v['target'], v['tname'])} в муте на сутки.")
    except Exception as e:
        await cb.message.edit_text(f"⚖️ Голосов достаточно, но мут не получился: {html.escape(str(e))}")
    await cb.answer()

