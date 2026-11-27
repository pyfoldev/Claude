"""ШАБЛОН: команда с монетами — «ставка 50» (списание, шанс, награда).

Правила денег (важно!):
  • любые списания+начисления, которые должны пройти вместе — в `async with db.atomic():`;
  • сначала проверяйте баланс, потом списывайте; никогда не доверяйте числам из текста без лимитов;
  • монеты хранятся ПО ЧАТАМ: db.get_balance(chat_id, user_id), db.change_balance(chat_id, user_id, ±N).
"""
import random
import re
import time

from aiogram import F, Router
from aiogram.types import Message

from bot import ux
from bot.emoji import emoji                     # emoji("coin") — значок монеты (кастомный/обычный)

router = Router(name="bet")
_rng = random.Random()

# ===== БАЛАНС (меняйте числа) =====
MIN_STAKE = 10
MAX_STAKE = 10_000
WIN_CHANCE = 0.45            # шанс выигрыша 0..1
PAYOUT = 2                   # выигрыш = ставка * PAYOUT (чистая прибыль = ставка * (PAYOUT-1))
COOLDOWN = 5

_RE = re.compile(r"^ставка\s+(\d{1,9})$", re.IGNORECASE)
_cool: dict[tuple[int, int], float] = {}


@router.message(F.text.func(lambda t: bool(t) and _RE.match(t.strip()) is not None))
async def bet(message: Message, db) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    if not (await db.get_settings(message.chat.id))["games_on"]:     # группа «игры» включена в чате?
        return
    chat, me = message.chat.id, message.from_user.id
    stake = int(_RE.match(message.text.strip()).group(1))
    coin = emoji("coin")
    if not MIN_STAKE <= stake <= MAX_STAKE:
        await ux.tell(message, f"⚠️ Ставка — от {MIN_STAKE} до {MAX_STAKE} {coin}.")
        return
    if time.time() - _cool.get((chat, me), 0) < COOLDOWN:
        return
    _cool[(chat, me)] = time.time()
    async with db.atomic():                                          # всё или ничего
        if await db.get_balance(chat, me) < stake:
            await ux.tell(message, f"❌ Не хватает монет. Баланс: {await db.get_balance(chat, me)} {coin}")
            return
        if _rng.random() < WIN_CHANCE:
            await db.change_balance(chat, me, stake * (PAYOUT - 1))
            text = f"🎉 Победа! <b>+{stake * (PAYOUT - 1)}</b> {coin}"
        else:
            await db.change_balance(chat, me, -stake)
            text = f"💸 Проигрыш: <b>-{stake}</b> {coin}"
    await message.reply(text)
