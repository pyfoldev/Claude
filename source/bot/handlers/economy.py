"""Экономика и азарт: ферма, переводы, рулетка, кубы со ставкой."""
import random
import re
import time
import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery, ChatPermissions, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import gender, ux
from bot import mod_service as ms
from bot.db import Database
from bot.emoji import emoji
from bot.targets import mention, resolve_user

router = Router(name="economy")
_rng = random.Random()

# ===== БАЛАНС ИГРЫ (меняйте числа здесь) =====
FARM_COOLDOWN = 4 * 3600   # «ферма» раз в 4 часа
FARM_AMOUNT = 40           # сколько монет приносит ферма
ROULETTE_COOLDOWN = 60     # пауза между «рулетками», сек
ROULETTE_REWARD = 20       # награда за выживание
ROULETTE_PENALTY = 50      # штраф при «выстреле»
ROULETTE_MUTE = 600        # мут при проигрыше, сек
DICE_TTL = 120             # сколько действует вызов «кубы», сек
MAX_STAKE = 100_000        # максимальная ставка
_T = r"(@\w+|\d{5,})"   # «цель»: @ник или числовой id
# ТАБЛИЦА КОМАНД: (вид, регулярка). Новая команда: добавьте строку сюда и ветку `elif kind == "...":` в economy_cmd.
# Группы регулярки () попадают в g[0], g[1]… в обработчике.
_PATTERNS = [
    ("farm", r"^ферма$"),
    ("transfer", r"^передать\s+(\d{1,9})(?:\s+" + _T + ")?$"),
    ("roulette", r"^(?:русская\s+)?рулетка$"),
    ("dice", r"^кубы(?:\s+(\d{1,6}))?(?:\s+" + _T + ")?$"),
    ("dice_target_first", r"^кубы\s+" + _T + r"\s+(\d{1,6})$"),
]
_COMPILED = [(k, re.compile(p, re.IGNORECASE)) for k, p in _PATTERNS]
_cool: dict[tuple, float] = {}   # кулдауны: (вид, чат, пользователь) -> время; чистится в main.rollup_loop
_dice: dict[str, dict] = {}


PAIR_WINS_PER_HOUR = 3
_pair_wins: dict[tuple, list[float]] = {}


def _pair_win_allowed(chat: int, a: int, b: int, now: float | None = None) -> bool:
    """Рейтинг побед нельзя накрутить, играя вдвоём: между одной парой — не больше 3 зачтённых побед в час."""
    now = time.time() if now is None else now
    key = (chat, min(a, b), max(a, b))
    recent = [t for t in _pair_wins.get(key, []) if now - t < 3600]
    if len(recent) >= PAIR_WINS_PER_HOUR:
        _pair_wins[key] = recent
        return False
    recent.append(now)
    _pair_wins[key] = recent
    if len(_pair_wins) > 5000:
        for k in [k for k, v in _pair_wins.items() if not v or now - v[-1] > 3600]:
            _pair_wins.pop(k, None)
    return True


# Разбор текста в (вид_команды, группы) или None, если это не команда
def parse(text: str | None):
    t = re.sub(r"\s+", " ", (text or "").strip())
    for kind, rx in _COMPILED:
        m = rx.match(t)
        if m:
            g = m.groups()
            if kind == "dice_target_first":
                kind, g = "dice", (g[1], g[0])  # «кубы @ник 50» / «кубы 12345 50» → (ставка, цель)
            return kind, g
    return None


def _fmt_wait(sec: int) -> str:
    h, m = divmod(max(sec, 0) // 60, 60)
    return f"{h} ч {m} мин" if h else f"{max(m, 1)} мин"


# Группа «игры» включена в настройках чата (games_on)? В личке команды не работают
async def _enabled(db: Database, m: Message) -> bool:
    return m.chat.type in ("group", "supergroup") and bool((await db.get_settings(m.chat.id))["games_on"])


@router.message(F.text.func(lambda t: parse(t) is not None))
# ЕДИНЫЙ ХЕНДЛЕР всех команд экономики: разбор → проверка настройки → ветка по виду команды (farm/transfer/roulette/dice)
async def economy_cmd(message: Message, bot, db: Database) -> None:
    if not await _enabled(db, message):
        return
    kind, g = parse(message.text)
    chat, me = message.chat.id, message.from_user.id
    now = int(time.time())
    reply = ms.real_reply(message)
    coin = emoji("coin")

    if kind == "farm":
        got, wait = await db.claim_farm(chat, me, now, FARM_COOLDOWN, FARM_AMOUNT)
        await message.reply(f"🪴 Ферма принесла <b>+{got}</b> {coin}. Следующий сбор через 4 часа." if got
                            else f"🪴 Урожай ещё не созрел. Загляните через {_fmt_wait(wait)}.")
    elif kind == "transfer":
        amount = int(g[0])
        target = await resolve_user(db, g[1], reply)
        if target is None:
            await ux.tell(message, "⚠️ Ответьте командой на сообщение получателя или укажите @ник.")
            return
        tid, tname = target
        if amount < 1 or tid == me or tid == (await bot.me()).id:
            await ux.tell(message, "⚠️ Так перевести нельзя: нужен другой человек и сумма от 1.")
            return
        if not await db.transfer(chat, me, tid, amount):
            await message.reply(f"{emoji('fail')} Не хватает монет. Баланс: {await db.get_balance(chat, me)} {coin}")
            return
        await message.reply(f"{emoji('ok')} {mention(me, message.from_user.full_name)} {await gender.say(db, me, '⟦передал|передала⟧')} "
                            f"<b>{amount}</b> {coin} → {mention(tid, tname)}")
    elif kind == "roulette":
        key = ("r", chat, me)
        if time.time() - _cool.get(key, 0) < ROULETTE_COOLDOWN:
            return
        _cool[key] = time.time()
        if _rng.randint(1, 6) != 1:
            await db.change_balance(chat, me, ROULETTE_REWARD)
            await message.reply(f"🔫 Щёлк! Вы выжили. +{ROULETTE_REWARD} {coin}")
            return
        async with db.atomic():
            lost = min(ROULETTE_PENALTY, await db.get_balance(chat, me))
            if lost > 0:
                await db.try_spend(chat, me, lost)
        try:
            await bot.restrict_chat_member(chat, me, permissions=ChatPermissions(can_send_messages=False),
                                           until_date=now + ROULETTE_MUTE)
            await message.reply(f"💥 БАХ! Проигрыш: −{lost} {coin} и мут на 10 минут.")
        except Exception:
            await message.reply(f"💥 БАХ! Проигрыш: −{lost} {coin}. Мут не получился: админов не трогаю.")
    elif kind == "dice":
        await _dice_offer(message, bot, db, g, reply)


# ---------- кубы ----------

async def _dice_offer(message: Message, bot, db: Database, g: tuple, reply) -> None:
    chat, me = message.chat.id, message.from_user.id
    stake = int(g[0]) if g[0] else 0
    target = await resolve_user(db, g[1], reply)
    if target is None:
        await ux.tell(message, "⚠️ Ответьте командой на сообщение соперника или укажите @ник: <code>кубы 50 @ник</code>")
        return
    tid, tname = target
    if tid == me or tid == (await bot.me()).id:
        await ux.tell(message, "⚠️ Нужен живой соперник, не вы сами и не я.")
        return
    if stake > MAX_STAKE:
        await ux.tell(message, f"⚠️ Максимальная ставка — {MAX_STAKE}.")
        return
    if stake and await db.get_balance(chat, me) < stake:
        await ux.tell(message, "⚠️ У вас не хватает монет на такую ставку.")
        return
    now = time.time()
    for k in [k for k, v in _dice.items() if v["expires"] < now]:
        _dice.pop(k, None)
    if any(v["chat"] == chat and {me, tid} & {v["a"], v["b"]} for v in _dice.values()):
        await ux.tell(message, "⚠️ У одного из вас уже есть незавершённый вызов.")
        return
    did = uuid.uuid4().hex[:8]
    _dice[did] = {"chat": chat, "a": me, "b": tid, "stake": stake, "expires": now + DICE_TTL,
                  "an": message.from_user.full_name, "bn": tname}
    try:
        await message.answer(
            f"🎲 {mention(me, message.from_user.full_name)} вызывает {mention(tid, tname)} на кубы"
            + (f" со ставкой <b>{stake}</b> {emoji('coin')}" if stake else "") + "!\nПринимаете?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                B(text="🎲 Принять", callback_data=f"dice:{did}:yes"), B(text="Отказаться", callback_data=f"dice:{did}:no")]]))
    except BaseException:
        _dice.pop(did, None)
        raise


@router.callback_query(F.data.startswith("dice:"))
async def dice_cb(cb: CallbackQuery, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or parts[2] not in ("yes", "no"):
        await cb.answer()
        return
    _, did, op = parts
    d = _dice.get(did)
    if d is None or cb.message is None or d["chat"] != cb.message.chat.id or d["expires"] < time.time():
        _dice.pop(did, None)
        await cb.answer("Вызов устарел.", show_alert=True)
        return
    uid = cb.from_user.id
    if uid not in (d["a"], d["b"]) or (op == "yes" and uid != d["b"]):
        await cb.answer("Это не ваш вызов.", show_alert=True)
        return
    _dice.pop(did, None)  # защита от двойного нажатия
    if op == "no":
        await cb.message.edit_text("🎲 Вызов отклонён.")
        await cb.answer()
        return
    chat, stake = d["chat"], d["stake"]
    A, Bm = mention(d["a"], d["an"]), mention(d["b"], d["bn"])
    ra, rb = _rng.randint(1, 6) + _rng.randint(1, 6), _rng.randint(1, 6) + _rng.randint(1, 6)
    winner = d["a"] if ra > rb else d["b"] if rb > ra else None
    insufficient = await _settle_dice(db, chat, d["a"], d["b"], stake, winner)
    if insufficient:
        who = A if insufficient == d["a"] else Bm
        await cb.message.edit_text(f"{emoji('fail')} У {who} уже не хватает монет. Вызов отменён.")
        await cb.answer()
        return
    line = f"🎲 {A}: <b>{ra}</b>  vs  {Bm}: <b>{rb}</b>\n"
    if winner is None:
        await cb.message.edit_text(line + "🤝 Ничья, ставки возвращены.")
    else:
        await cb.message.edit_text(line + f"{emoji('trophy')} Победил {A if winner == d['a'] else Bm}"
                                   + (f", выигрыш <b>{stake}</b> {emoji('coin')}" if stake else "") + "!")
    await cb.answer()


async def _settle_dice(db: Database, chat: int, a: int, b: int, stake: int, winner: int | None) -> int | None:
    """Проверить обе ставки и передать выигрыш одной транзакцией; вернуть id без средств."""
    if not stake:
        return None
    async with db.atomic():
        for uid in (a, b):
            if await db.get_balance(chat, uid) < stake:
                return uid
        if winner is not None:
            loser = b if winner == a else a
            if not await db.transfer(chat, loser, winner, stake):
                return loser
            if _pair_win_allowed(chat, a, b):
                await db.add_win(chat, winner)
    return None
