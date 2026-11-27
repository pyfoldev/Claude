"""ШАБЛОН: команда с целью — «похвалить @ник» или ответом на сообщение.

ПОДКЛЮЧЕНИЕ: bot/handlers/<имя>.py → main.py (import + ROUTERS).
Ключевые помощники: targets.resolve_user (кто цель), mod_service.real_reply (ответ без служебных),
targets.mention (кликабельное имя), gender.say (согласование по полу: ⟦сделал|сделала⟧).
"""
import re
import time

from aiogram import F, Router
from aiogram.types import Message

from bot import gender, ux
from bot.mod_service import real_reply
from bot.targets import mention, resolve_user

router = Router(name="praise")

COOLDOWN = 10                                   # пауза, сек (правьте)
# «похвалить» + необязательная цель (@ник или числовой id)
_RE = re.compile(r"^похвалить(?:\s+(@\w+|\d{5,}))?$", re.IGNORECASE)
_last: dict[tuple[int, int], float] = {}


@router.message(F.text.func(lambda t: bool(t) and _RE.match(t.strip()) is not None))
async def praise(message: Message, bot, db) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    token = _RE.match(message.text.strip()).group(1)             # '@ник' | '12345' | None
    target = await resolve_user(db, token, real_reply(message))   # None → цели нет → это просто слова
    if target is None:
        return
    tid, tname = target
    me = message.from_user.id
    if tid == me:
        await ux.tell(message, "🙃 Себя хвалить неловко — выберите другого человека.")
        return
    key = (message.chat.id, me)
    if time.time() - _last.get(key, 0) < COOLDOWN:                # кулдаун: молча игнорируем
        return
    _last[key] = time.time()
    verb = await gender.say(db, me, "⟦похвалил|похвалила⟧")        # подставляет форму по полу автора
    await message.reply(f"👏 {mention(me, message.from_user.full_name)} {verb} {mention(tid, tname)}")
