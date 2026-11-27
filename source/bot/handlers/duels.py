"""Дуэли: крестики-нолики и камень-ножницы-бумага."""
import asyncio
from weakref import WeakValueDictionary
import logging
import time
import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import ux
from bot.db import Database
from bot.targets import mention
from bot.emoji import emoji
from bot.games import rps, tictactoe
from bot.handlers.economy import _pair_win_allowed
from bot.mod_service import real_reply

router = Router(name="duels")

TIMEOUT = 120
_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
_challenge_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()
RPS_CODES = {"rock": "камень", "scissors": "ножницы", "paper": "бумага"}
MARK_ICON = {"X": "❌", "O": "⭕", " ": "🔘"}
GAME_NAME = {"ttt": "Крестики-нолики", "rps": "Камень-ножницы-бумага"}


def _lock(duel_id: str) -> asyncio.Lock:
    return _locks.setdefault(duel_id, asyncio.Lock())


def _name(p: dict) -> str:
    return str(mention(p["id"], p["name"]))


def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text=t, callback_data=d) for t, d in row] for row in rows])


def _pick_kb(d: dict) -> InlineKeyboardMarkup:
    return _kb([[("❌⭕ Крестики-нолики", f"duel:{d['id']}:pick:ttt")],
                [("✊✌️🖐 Камень-ножницы-бумага", f"duel:{d['id']}:pick:rps")],
                [("Отмена", f"duel:{d['id']}:decline")]])


def _accept_kb(d: dict) -> InlineKeyboardMarkup:
    return _kb([[("⚔️ Принять вызов", f"duel:{d['id']}:accept"),
                 ("Отказаться", f"duel:{d['id']}:decline")]])


def _ttt_kb(d: dict) -> InlineKeyboardMarkup:
    b = d["board"]
    return _kb([[(MARK_ICON[b[r * 3 + c]], f"duel:{d['id']}:m:{r * 3 + c}") for c in range(3)]
                for r in range(3)])


def _rps_kb(d: dict) -> InlineKeyboardMarkup:
    return _kb([[(f"{rps.ICONS[n]} {n}", f"duel:{d['id']}:r:{code}")
                 for code, n in RPS_CODES.items()]])


def _marks(d: dict) -> dict:
    return {"X": d["challenger"], "O": d["opponent"]}


def _turn_text(d: dict) -> str:
    if d["game"] == "ttt":
        mark = d["turn"]
        return (f"{emoji('duel')} <b>Крестики-нолики</b>\n❌ {_name(d['challenger'])}  vs  "
                f"⭕ {_name(d['opponent'])}\nХод: {MARK_ICON[mark]} {_name(_marks(d)[mark])}")
    return (f"{emoji('duel')} <b>Камень-ножницы-бумага</b>\n{_name(d['challenger'])}  vs  "
            f"{_name(d['opponent'])}\nОба выбирают ход (выбор скрыт).")


async def _finish(message, db: Database, d: dict, text: str, winner: dict | None) -> None:
    async with db.atomic():
        if not await db.delete_duel(d["id"]):
            return
        if winner and _pair_win_allowed(d["chat_id"], d["challenger"]["id"], d["opponent"]["id"]):
            await db.add_win(d["chat_id"], winner["id"])
    if winner:
        text += f"\n{emoji('trophy')} Победил {_name(winner)}!"
    await message.edit_text(text, reply_markup=None)


@router.message(F.text.lower() == "дуэль")
async def challenge(message: Message, db: Database) -> None:
    r = real_reply(message)
    if message.chat.type not in ("group", "supergroup"):
        await ux.tell(message, "⚠️ Дуэли работают только в группах.")
        return
    if not (await db.get_settings(message.chat.id))["games_on"]:
        return
    if not r or not r.from_user:
        await ux.tell(message, "⚠️ Напишите <code>дуэль</code> ответом на сообщение соперника.")
        return
    a, b = message.from_user, r.from_user
    if b.is_bot or b.id == a.id:
        await ux.tell(message, "⚠️ Выберите живого соперника, не себя и не бота 🙂")
        return
    async with _challenge_locks.setdefault(message.chat.id, asyncio.Lock()):
        for d in await db.chat_duels(message.chat.id):
            if {d["challenger"]["id"], d["opponent"]["id"]} & {a.id, b.id}:
                await ux.tell(message, "⚠️ У одного из вас уже есть активная дуэль.")
                return
        d = {
            "id": uuid.uuid4().hex[:8], "chat_id": message.chat.id, "game": None, "state": "pick",
            "challenger": {"id": a.id, "name": a.full_name}, "opponent": {"id": b.id, "name": b.full_name},
            "expires_at": int(time.time()) + TIMEOUT,
        }
        m = await message.answer(
            f"{emoji('duel')} {_name(d['challenger'])} вызывает {_name(d['opponent'])}!\n"
            "Вызывающий, выберите игру:", reply_markup=_pick_kb(d))
        d["message_id"] = m.message_id
        await db.save_duel(d)


@router.callback_query(F.data.startswith("duel:"))
async def duel_cb(cb: CallbackQuery, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) < 3 or cb.message is None:
        await cb.answer()
        return
    duel_id, op = parts[1], parts[2]
    arg = parts[3] if len(parts) > 3 else None
    async with _lock(duel_id):
        d = await db.get_duel(duel_id)
        if d is None:
            await cb.answer("Дуэль уже завершена.", show_alert=True)
            return
        if cb.message.chat.id != d["chat_id"] or cb.message.message_id != d["message_id"]:
            await cb.answer("Эта кнопка относится к другой дуэли.", show_alert=True)
            return
        if d["expires_at"] <= int(time.time()):
            await cb.answer("Время дуэли вышло.", show_alert=True)
            return
        uid = cb.from_user.id
        ch, op_ = d["challenger"], d["opponent"]
        msg = cb.message
        now = int(time.time())

        if op == "decline":
            if uid not in (ch["id"], op_["id"]):
                await cb.answer("Это не ваша дуэль.", show_alert=True)
                return
            await _finish(msg, db, d, f"{emoji('fail')} Дуэль отменена.", None)
            await cb.answer()
            return

        if op == "pick":
            if d["state"] != "pick" or uid != ch["id"] or arg not in GAME_NAME:
                await cb.answer("Выбирает вызывающий.", show_alert=True)
                return
            d.update(game=arg, state="invite", expires_at=now + TIMEOUT)
            await db.save_duel(d)
            await msg.edit_text(
                f"{emoji('duel')} {_name(ch)} вызывает {_name(op_)} на «{GAME_NAME[arg]}»!",
                reply_markup=_accept_kb(d))
            await cb.answer()
            return

        if op == "accept":
            if d["state"] != "invite" or uid != op_["id"]:
                await cb.answer("Принять может только вызванный игрок.", show_alert=True)
                return
            d["state"] = "play"
            d["expires_at"] = now + TIMEOUT
            if d["game"] == "ttt":
                d.update(board=tictactoe.new_board(), turn="X")
            else:
                d["moves"] = {}
            await db.save_duel(d)
            await msg.edit_text(_turn_text(d),
                                reply_markup=_ttt_kb(d) if d["game"] == "ttt" else _rps_kb(d))
            await cb.answer()
            return

        if d["state"] != "play":
            await cb.answer("Дуэль ещё не началась.", show_alert=True)
            return
        if uid not in (ch["id"], op_["id"]):
            await cb.answer("Вы не участвуете в этой дуэли.", show_alert=True)
            return

        if op == "m" and d["game"] == "ttt":
            mark = d["turn"]
            if _marks(d)[mark]["id"] != uid:
                await cb.answer("Сейчас не ваш ход.", show_alert=True)
                return
            if not isinstance(arg, str) or not arg.isascii() or not arg.isdigit() or not tictactoe.move(d["board"], int(arg), mark):
                await cb.answer("Клетка занята.", show_alert=True)
                return
            res = tictactoe.winner(d["board"])
            if res is None:
                d["turn"] = "O" if mark == "X" else "X"
                d["expires_at"] = now + TIMEOUT
                await db.save_duel(d)
                await msg.edit_text(_turn_text(d), reply_markup=_ttt_kb(d))
            else:
                board = "\n".join("".join(MARK_ICON[c] for c in d["board"][i:i + 3]) for i in (0, 3, 6))
                if res == "draw":
                    await _finish(msg, db, d, f"{board}\n🤝 Ничья!", None)
                else:
                    await _finish(msg, db, d, board, _marks(d)[res])
            await cb.answer()
            return

        if op == "r" and d["game"] == "rps" and arg in RPS_CODES:
            if str(uid) in d["moves"]:
                await cb.answer("Вы уже сделали выбор.", show_alert=True)
                return
            d["moves"][str(uid)] = RPS_CODES[arg]
            if len(d["moves"]) < 2:
                d["expires_at"] = now + TIMEOUT
                await db.save_duel(d)
                await cb.answer("Выбор принят, ждём соперника.")
                return
            a, b = d["moves"][str(ch["id"])], d["moves"][str(op_["id"])]
            r = rps.judge(a, b)
            line = (f"{_name(ch)} {rps.ICONS[a]} vs {rps.ICONS[b]} {_name(op_)}")
            await _finish(msg, db, d, line + ("\n🤝 Ничья!" if r == 0 else ""),
                          None if r == 0 else (ch if r == 1 else op_))
            await cb.answer()
            return
        await cb.answer()


async def duel_watchdog(bot, db: Database) -> None:
    """Раз в 15 секунд закрывает просроченные дуэли (ожидающий побеждает)."""
    while True:
        await asyncio.sleep(15)
        try:
            for d in await db.expired_duels(int(time.time())):
                async with _lock(d["id"]):
                    d = await db.get_duel(d["id"])
                    if d is None or d["expires_at"] > int(time.time()):
                        continue
                    text, winner = f"{emoji('fail')} Время вышло, дуэль закрыта.", None
                    if d["state"] == "play":
                        if d["game"] == "ttt":
                            winner = d["opponent"] if d["turn"] == "X" else d["challenger"]
                        elif len(d["moves"]) == 1:
                            uid = int(next(iter(d["moves"])))
                            winner = d["challenger"] if d["challenger"]["id"] == uid else d["opponent"]
                    async with db.atomic():
                        if not await db.delete_duel(d["id"]):
                            continue
                        if winner and _pair_win_allowed(d["chat_id"], d["challenger"]["id"], d["opponent"]["id"]):
                            await db.add_win(d["chat_id"], winner["id"])
                    if winner:
                        text += f"\n{emoji('trophy')} Победил {_name(winner)} (соперник не ответил)."
                    try:
                        await bot.edit_message_text(text, chat_id=d["chat_id"],
                                                    message_id=d["message_id"], reply_markup=None)
                    except Exception:
                        pass
        except Exception:
            logging.exception("duel watchdog")
