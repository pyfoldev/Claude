import html
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message, ReplyParameters

from bot import rich_ui
from bot.db import USERNAMES
from bot.rich_ui import Btn, Screen

from bot.toggles import Enabled
from bot.db import Database
from bot.emoji import emoji
from bot.fmt import pre_table
from bot.keyboards import stats_keyboard
from bot.mod_service import real_reply
from bot.parsing import parse_stats_command
from bot.targets import mention, listed

router = Router(name="stats")
router.message.filter(Enabled("stats_on"))   # группу команд можно выключить в настройках → «Команды»


def period_title(key: str) -> str:
    if key == "all":
        return "за всё время"
    if key == "24":
        return "за 24 часа"
    if key == "168":
        return "за неделю"
    if key == "720":
        return "за месяц"
    return f"за {key} ч."


def format_stats(total: int, top: list[tuple[str, int]], title: str) -> str:
    head = f"{emoji('stats')} <b>Статистика {title}</b>"
    if total == 0:
        return head + "\nПока нет сообщений."
    table = pre_table([(str(i), name, str(n)) for i, (name, n) in enumerate(top, 1)],
                      header=("#", "Участник", "Сообщ."), align="llr", maxw=(3, 20, 7), quoted=False)   # статистика — обычным текстом, без цитаты
    return f"{head} · {total}\n{table}"


async def _name(bot, db: Database, chat_id: int, user_id: int) -> str:
    name = await db.user_name(user_id)
    if not name:
        try:
            name = (await bot.get_chat_member(chat_id, user_id)).user.full_name
        except Exception:
            name = f"id{user_id}"
    return name


async def stats_rows(bot, db: Database, chat_id: int, key: str):
    """(заголовок периода, всего сообщений, [(uid, имя, число)])."""
    since = None if key == "all" else int(time.time()) - int(key) * 3600
    total, top = await db.count_by_user(chat_id, since)
    return period_title(key), total, [(uid, await _name(bot, db, chat_id, uid), n) for uid, n in top]


PERIODS = [("2 часа", "2"), ("День", "24"), ("Вся", "all")]


async def stats_screen(bot, db: Database, chat_id: int, key: str) -> Screen:
    """Статистика: таблица участников и кнопки периодов внутри rich-сообщения; для обычного — прежний текст."""
    title, total, rows = await stats_rows(bot, db, chat_id, key)
    pills = [[Btn(("• " if k == key else "") + label, cb=f"stats:{k}", style="primary" if k == key else None)
              for label, k in PERIODS]]
    classic = await build_stats(bot, db, chat_id, key)
    if not total:
        return Screen(f"📊 Статистика {title}", ["Пока нет сообщений."], pills, classic=classic)
    table = [[str(i), f'<a href="https://t.me/{USERNAMES[uid]}">{html.escape(name[:28])}</a>' if USERNAMES.get(uid)
              else f'<a href="tg://user?id={uid}">{html.escape(name[:28])}</a>', str(n)]
             for i, (uid, name, n) in enumerate(rows, 1)]
    return Screen(f"📊 Статистика {title} · {total}", [("rows", ["#", "Участник", "Сообщ."], table)], pills, classic=classic)


async def send_stats(bot, db: Database, chat_id: int, key: str, reply_to: int | None = None, thread_id: int | None = None) -> None:
    await rich_ui.send(bot, chat_id, await stats_screen(bot, db, chat_id, key), thread_id=thread_id, reply_to=reply_to)


async def build_stats(bot, db: Database, chat_id: int, key: str) -> str:
    since = None if key == "all" else int(time.time()) - int(key) * 3600
    total, top = await db.count_by_user(chat_id, since)
    named = [(listed(uid, await _name(bot, db, chat_id, uid), 28), n) for uid, n in top]   # имя — ссылка + @ник
    return format_stats(total, named, period_title(key))


@router.message(F.text.func(lambda t: bool(t) and parse_stats_command(t) is not None))
async def stats_cmd(message: Message, bot, db: Database) -> None:
    p = parse_stats_command(message.text)
    key = "all" if p.kind == "all" else str(p.hours)
    r = real_reply(message)
    if r and r.from_user:
        u = r.from_user
        since = None if key == "all" else int(time.time()) - int(key) * 3600
        n = await db.user_total(message.chat.id, u.id, since)
        await message.answer(
            f"{emoji('stats')} {mention(u.id, u.full_name)} {period_title(key)}: <b>{n}</b> сообщ.")
        return
    await send_stats(bot, db, message.chat.id, key,
                     thread_id=message.message_thread_id if message.is_topic_message else None)


@router.callback_query(F.data.startswith("stats:"))
async def stats_cb(cb: CallbackQuery, bot, db: Database) -> None:
    key = cb.data.split(":", 1)[1]
    if key != "all" and not key.isdigit():
        await cb.answer()
        return
    await cb.answer()
    await rich_ui.show(cb, await stats_screen(bot, db, cb.message.chat.id, key))
