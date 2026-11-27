"""ШАБЛОН: команда для модераторов с рангом, ДК (доступ команд) и записью в журнал.

Ранги: 0 участник · 1–2 модератор · 3 админ · 4 старший · 5 создатель. Значения по умолчанию — ranks.DEFAULT_ACCESS,
чат может переопределить их командой «дк». Новая защищённая команда:
   1) "замечание": 2  → ranks.DEFAULT_ACCESS;  2) в хендлере — need_rank(access, "замечание").
"""
import re

from aiogram import F, Router
from aiogram.types import Message

from bot import mod_service as ms, ux
from bot.ranks import need_rank
from bot.targets import mention, resolve_user

router = Router(name="note")
_RE = re.compile(r"^замечание(?:\s+(@\w+|\d{5,}))?(?:\s+(.+))?$", re.IGNORECASE | re.DOTALL)


@router.message(F.text.func(lambda t: bool(t) and _RE.match(t.strip()) is not None))
async def note_cmd(message: Message, bot, db) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    chat, me = message.chat.id, message.from_user.id
    access = await db.get_access(chat)                              # ДК чата: {"команда": ранг}
    if await ms.effective_rank(bot, db, chat, me) < need_rank(access, "замечание"):
        return                                                       # нет прав → тишина (команда как будто не существует)
    m = _RE.match(message.text.strip())
    target = await resolve_user(db, m.group(1), ms.real_reply(message))
    if target is None:
        await ux.tell(message, "⚠️ Укажите @ник или ответьте на сообщение.")
        return
    tid, tname = target
    # can_act → (можно?, причина отказа). Передаём db и имя команды — тогда учитывается система рангов и ДК.
    ok, why = await ms.can_act(bot, chat, me, tid, "can_restrict_members", db, "замечание")
    if not ok:
        await ux.tell(message, why or "⚠️ Нельзя применить к этому участнику.")
        return
    reason = (m.group(2) or "").strip()
    # ... действие ...
    await message.reply(f"📝 Замечание для {mention(tid, tname)}" + (f": {reason}" if reason else ""))
