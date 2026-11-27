"""Темы форума: «темы» — список, «стата темы» — где пишут больше всего, «+тихая тема» / «-тихая тема» — в этой теме бот
не отвечает на команды обычных участников (защита от спама и модерация продолжают работать)."""
import re
import time

from aiogram import F, Router
from aiogram.types import Message

from bot import mod_service as ms
from bot import style, ux
from bot.db import Database
from bot.ranks import need_rank

router = Router(name="topics")
_STATS = re.compile(r"^стата\s+темы(?:\s+(неделя|месяц|сутки))?$", re.IGNORECASE)
_LIST = re.compile(r"^темы$", re.IGNORECASE)
_QUIET = re.compile(r"^([+-])тихая\s+тема$", re.IGNORECASE)
_PERIOD = {None: (7 * 86400, "за неделю"), "неделя": (7 * 86400, "за неделю"), "месяц": (30 * 86400, "за месяц"),
           "сутки": (86400, "за сутки")}


@router.message(F.chat.type.in_({"group", "supergroup"}),
                F.text.func(lambda t: bool(t) and any(r.match(t.strip()) for r in (_STATS, _LIST, _QUIET))))
async def topics_cmd(message: Message, bot, db: Database) -> None:
    if message.from_user is None:
        return
    t = message.text.strip()
    chat = message.chat.id
    if (m := _QUIET.match(t)):
        thread = message.message_thread_id if message.is_topic_message else 0
        if not thread:
            await ux.tell(message, style.warn("Напишите это внутри нужной темы."))
            return
        if await ms.effective_rank(bot, db, chat, message.from_user.id) < need_rank(await db.get_access(chat), "настройки чата"):
            return
        await db.set_topic_quiet(chat, thread, m.group(1) == "+")
        await message.reply(style.ok("Тема тихая: бот не отвечает участникам." if m.group(1) == "+" else "Тема снова обычная."))
        return
    if _LIST.match(t):
        rows = await db.topic_list(chat)
        if not rows:
            await message.reply("ℹ️ Тем пока не видел: названия подтянутся, когда в них напишут.")
            return
        await message.reply(style.head("🗂", "Темы") + "\n" + "\n".join(
            f"• {name}" + (" 🤫" if quiet else "") for _, name, quiet in rows))
        return
    secs, label = _PERIOD[(_STATS.match(t).group(1) or "").lower() or None]
    top = await db.topic_stats(chat, int(time.time()) - secs)
    if not top:
        await message.reply("ℹ️ Пока нет сообщений по темам.")
        return
    total = sum(n for _, n in top)
    rows = [[str(i), await db.topic_name(chat, th), str(n), f"{round(n * 100 / total)}%"] for i, (th, n) in enumerate(top, 1)]
    fallback = style.head("🗂", f"Темы {label}") + "\n" + "\n".join(
        f"{i}. {r[1]} — <b>{r[2]}</b> ({r[3]})" for i, r in enumerate(rows, 1))
    await ux.table_or_text(message, f"Темы {label}", ["#", "Тема", "Сообщ.", "Доля"], rows, fallback,
                           aligns=["center", "left", "right", "right"])
