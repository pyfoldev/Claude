import asyncio
import re
import time

from aiogram import F, Router
from aiogram.types import Message

from bot.db import Database
from bot.targets import listed
from bot.fmt import pre_table
from bot.emoji import emoji
from bot.games.slots import slots_payout
from bot import ux

router = Router(name="games")

_SLOTS_RE = re.compile(r"^слоты(?:\s+(\d{1,9}|все|всё))?$", re.IGNORECASE)
DEFAULT_BET = 10


async def _games_on(db: Database, chat_id: int) -> bool:
    return bool((await db.get_settings(chat_id))["games_on"])


async def _top_text(bot, db: Database, chat_id: int, rows, title: str, unit: str, users=None) -> str:
    if not rows:
        return f"{title}\nПока пусто."
    users = users if users is not None else await db.users_by_ids([uid for uid, _ in rows])
    table = pre_table([(str(i), listed(uid, (users.get(uid) or {}).get("name") or f"id{uid}", 28), str(n)) for i, (uid, n) in enumerate(rows, 1)],
                      header=("#", "Участник", unit.capitalize()), align="llr", maxw=(3, 20, 8))
    return f"{title}\n{table}"


async def _send_top(message: Message, db: Database, rows, plain_title: str, html_title: str, unit: str) -> None:
    """Топ — настоящей таблицей (rich), а если не вышло — прежним текстом."""
    from bot.db import USERNAMES
    users = await db.users_by_ids([uid for uid, _ in rows])
    table_rows = []
    for i, (uid, n) in enumerate(rows, 1):
        name = ((users.get(uid) or {}).get("name") or f"id{uid}")[:28]
        table_rows.append([str(i), (name, f"https://t.me/{USERNAMES[uid]}" if USERNAMES.get(uid) else f"tg://user?id={uid}"), str(n)])
    await ux.table_or_text(message, plain_title, ["#", "Участник", unit.capitalize()], table_rows,
                           await _top_text(message.bot, db, message.chat.id, rows, html_title, unit, users),
                           aligns=["center", "left", "right"], reply=False)


@router.message(F.text.func(lambda t: bool(t) and _SLOTS_RE.match(t.strip()) is not None))
async def slots(message: Message, db: Database) -> None:
    chat_id, uid = message.chat.id, message.from_user.id
    if not await _games_on(db, chat_id):
        return
    arg = _SLOTS_RE.match(message.text.strip()).group(1)
    balance = await db.get_balance(chat_id, uid)
    bet = balance if arg and arg.lower() in ("все", "всё") else int(arg) if arg else DEFAULT_BET
    if bet < 1:
        await ux.tell(message, "Ставка должна быть от 1 монеты.")
        return
    if not await db.try_spend(chat_id, uid, bet):  # атомарное списание
        await ux.tell(message, f"{emoji('fail')} Не хватает монет. Баланс: {balance} {emoji('coin')}")
        return
    try:
        dice = await message.answer_dice(emoji="🎰")
    except Exception:
        await db.change_balance(chat_id, uid, bet)  # бросок не состоялся — возвращаем ставку
        return
    net = slots_payout(dice.dice.value, bet)
    if net > 0:
        await db.change_balance(chat_id, uid, bet + net)
        text = f"{emoji('ok')} Выигрыш <b>+{net}</b> {emoji('coin')}"
    else:
        text = f"{emoji('fail')} Проигрыш <b>-{bet}</b> {emoji('coin')}"
    bal = await db.get_balance(chat_id, uid)
    await asyncio.sleep(2.5)  # анимация не должна задерживать начисление выигрыша
    await message.reply(f"{text}\nБаланс: {bal} {emoji('coin')}")


@router.message(F.text.lower() == "баланс")
async def balance(message: Message, db: Database) -> None:
    bal = await db.get_balance(message.chat.id, message.from_user.id)
    await message.reply(f"{emoji('coin')} Ваш баланс: <b>{bal}</b>")      # обычным ответом: не удаляется


@router.message(F.text.lower() == "бонус")
async def bonus(message: Message, db: Database) -> None:
    got = await db.claim_bonus(message.chat.id, message.from_user.id, int(time.time()))
    if got is None:
        await ux.tell(message, "Бонус уже получен сегодня. Приходите завтра!")
    else:
        await message.reply(f"{emoji('ok')} Ежедневный бонус: <b>+{got}</b> {emoji('coin')}")


@router.message(F.text.lower() == "топ")
async def top(message: Message, bot, db: Database) -> None:
    rows = await db.top_balances(message.chat.id)
    await _send_top(message, db, rows, "Богатейшие", f"{emoji('trophy')} <b>Богатейшие</b>", "монет")


@router.message(F.text.lower() == "рейтинг дуэлей")
async def rating(message: Message, bot, db: Database) -> None:
    rows = await db.top_wins(message.chat.id)
    await _send_top(message, db, rows, "Победы в дуэлях", f"{emoji('duel')} <b>Победы в дуэлях</b>", "поб.")
