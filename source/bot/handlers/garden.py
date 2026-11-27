"""Игра «Огород»: сажаем, поливаем, собираем урожай за монеты (общий баланс со слотами)."""
import asyncio
from weakref import WeakValueDictionary
import re
import time

from aiogram import F, Router
from aiogram.types import Message

from bot.db import Database
from bot.fmt import pre_table
from bot.emoji import emoji
from bot.games import garden as g

router = Router(name="garden")

_PLANT_RE = re.compile(r"^посадить\s+(\S+)(?:\s+(\d{1,2}))?$", re.IGNORECASE)
_EXACT = {"огород", "магазин", "полить", "собрать", "расширить"}
_locks: WeakValueDictionary[tuple[int, int], asyncio.Lock] = WeakValueDictionary()


def _now() -> int:
    return int(time.time())


def _is_garden(t: str | None) -> bool:
    if not t:
        return False
    t = t.strip().lower()
    return t in _EXACT or t == "посадить" or _PLANT_RE.match(t) is not None


def _shop() -> str:
    table = pre_table([(f"{c.emoji} {c.name}", str(c.cost), g.fmt_left(c.seconds), str(c.reward)) for c in g.CROPS.values()],
                      header=("Культура", "Семена", "Растёт", "Урожай"), align="llrr", maxw=(14, 6, 10, 6))
    return ("🛒 <b>Магазин семян</b> (цены в монетах)\n" + table +
            "\nПосадить: <code>посадить морковь</code> (или <code>посадить морковь 3</code>)")


@router.message(F.text.func(_is_garden))
async def garden_cmd(message: Message, db: Database) -> None:
    chat_id, uid = message.chat.id, message.from_user.id
    if message.chat.type in ("group", "supergroup") and not (await db.get_settings(chat_id))["games_on"]:
        return
    text = message.text.strip().lower()
    async with _locks.setdefault((chat_id, uid), asyncio.Lock()):
        # Состояние грядок и баланс должны фиксироваться вместе.
        async with db.atomic():
            gd = await db.get_garden(chat_id, uid) or g.new_garden()
            now = _now()
            reply, changed = await _handle(db, chat_id, uid, text, gd, now)
            if changed:
                await db.save_garden(chat_id, uid, gd)
    await message.reply(reply)


async def _handle(db: Database, chat_id: int, uid: int, text: str, gd: dict, now: int) -> tuple[str, bool]:
    if text == "магазин":
        return _shop(), False
    if text == "огород":
        bal = await db.get_balance(chat_id, uid)
        return (f"🌱 <b>Ваш огород</b>\n{g.render(gd, now)}\n\nБаланс: {bal} {emoji('coin')}\n"
                "<code>посадить морковь</code> · <code>полить</code> · <code>собрать</code> · "
                "<code>магазин</code> · <code>расширить</code>"), False
    if text == "полить":
        n, wait = g.water(gd, now)
        if n:
            return f"💧 Полито грядок: {n}. Рост ускорен на {int(g.WATER_BOOST * 100)}%.", True
        if wait:
            return f"💧 Земля ещё влажная. Полить снова можно через {g.fmt_left(wait)}.", False
        return "Поливать нечего: на грядках ничего не растёт.", False
    if text == "собрать":
        got = g.harvest(gd, now)
        if not got:
            return "Пока нечего собирать: урожай ещё не созрел.", False
        total = sum(r for _, r in got)
        await db.change_balance(chat_id, uid, total)
        names = ", ".join(f"{g.CROPS[c].emoji} {c}" for c, _ in got)
        return f"{emoji('ok')} Собрано: {names}\nВыручка: <b>+{total}</b> {emoji('coin')}", True
    if text == "расширить":
        cost = g.expand_cost(gd)
        if cost is None:
            return f"У вас уже максимум грядок ({g.MAX_SLOTS}).", False
        if not await db.try_spend(chat_id, uid, cost):
            return f"{emoji('fail')} Новая грядка стоит {cost} {emoji('coin')} — не хватает монет.", False
        g.expand(gd)
        return f"{emoji('ok')} Куплена грядка №{gd['slots']} за {cost} {emoji('coin')}.", True
    # посадить
    m = _PLANT_RE.match(text)
    if not m:
        return "Что посадить? " + _shop(), False
    crop = g.find_crop(m.group(1))
    if crop is None:
        return "Не знаю такой культуры.\n" + _shop(), False
    free = sum(1 for p in gd["plots"] if p is None)
    if free == 0:
        return "Свободных грядок нет. Соберите урожай или купите грядку: <code>расширить</code>.", False
    want = int(m.group(2)) if m.group(2) else 1
    n = max(1, min(want, free))
    cost = g.CROPS[crop].cost * n
    if not await db.try_spend(chat_id, uid, cost):
        return f"{emoji('fail')} Не хватает монет: {n} × {crop} стоит {cost} {emoji('coin')}.", False
    for _ in range(n):
        g.plant(gd, crop, now)
    c = g.CROPS[crop]
    return (f"{c.emoji} Посажено: {crop} × {n} за {cost} {emoji('coin')}. "
            f"Созреет через {g.fmt_left(c.seconds)}."), True
