"""Подключение журнала действий: «+журнал <id>», «+журнал» (ответом на пересланное из канала), «-журнал», «журнал»."""
import html
import re

from aiogram import F, Router
from aiogram.types import Message

from bot import ux
from bot import mod_service as ms
from bot.db import Database
from bot.ranks import need_rank

router = Router(name="logchat")
_ADD = re.compile(r"^\+журнал(?:\s+(-?\d{5,}))?$", re.IGNORECASE)
_DEL = re.compile(r"^-журнал$", re.IGNORECASE)
_SHOW = re.compile(r"^журнал$", re.IGNORECASE)


def _match(t: str | None) -> bool:
    t = (t or "").strip()
    return bool(_ADD.match(t) or _DEL.match(t) or _SHOW.match(t))


def _forwarded_chat_id(reply) -> int | None:
    if reply is None:
        return None
    origin = getattr(reply, "forward_origin", None)
    chat = getattr(origin, "chat", None) if origin is not None else None
    return chat.id if chat is not None else None


async def connect_log_chat(bot, db: Database, chat: int, chat_title: str, actor: int, dest: int) -> tuple[bool, str]:
    """Подключить журнал чата chat к dest. Подключающий должен быть админом dest, бот — уметь туда писать."""
    try:
        m = await bot.get_chat_member(dest, actor)
        is_admin = m.status in ("administrator", "creator")
    except Exception:
        is_admin = False
    if not is_admin:
        return False, "Вы должны быть админом чата/канала, куда пойдёт журнал, а бот — состоять в нём."
    try:
        await bot.send_message(dest, f"✅ Журнал действий чата «{html.escape(chat_title)}» подключён.")
    except Exception:
        return False, "Не могу писать туда: сделайте бота админом с правом публикации сообщений."
    await db.set_setting(chat, "log_chat_id", dest, actor=actor)
    return True, "📜 Журнал подключён: действия модерации, смена настроек и рангов будут приходить туда."


@router.message(F.text.func(_match))
async def log_cmd(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    chat, me = message.chat.id, message.from_user.id
    text = message.text.strip()
    cfg = await db.get_settings(chat)
    if _SHOW.match(text):
        dest = cfg["log_chat_id"]
        await message.reply((f"📜 Журнал подключён: <code>{dest}</code>\nОтключить: <code>-журнал</code>" if dest else
                             "📜 Журнал не подключён.\nПодключить: <code>+журнал id</code> (чат или канал)"))
        return
    need = need_rank(await db.get_access(chat), "настройки чата")
    if await ms.effective_rank(bot, db, chat, me) < need:
        await ux.tell(message, f"⚠️ Настройка журнала доступна с ранга {need}.")
        return
    if _DEL.match(text):
        await db.set_setting(chat, "log_chat_id", 0, actor=me)
        await message.reply("📜 Журнал отключён.")
        return
    raw = _ADD.match(text).group(1)
    dest = int(raw) if raw else _forwarded_chat_id(ms.real_reply(message))
    if dest is None:
        await message.reply("⚠️ Укажите id чата/канала: <code>+журнал -1001234567890</code> — "
                            "или ответьте командой на сообщение, пересланное из канала.")
        return
    ok, info = await connect_log_chat(bot, db, chat, message.chat.title or str(chat), me, dest)
    await message.reply(info)
