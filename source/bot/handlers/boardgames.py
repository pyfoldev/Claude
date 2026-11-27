"""Шахматы, шашки и морской бой для двоих: «шахматы» (вызов всем) или «шахматы» ответом на сообщение соперника.
Игра идёт на кнопках в одном сообщении; состояние лежит в БД и переживает перезапуск."""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from weakref import WeakValueDictionary

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import boardgames as bgm
from bot import ux
from bot.db import Database
from bot.emoji import emoji
from bot.games import checkers as ck
from bot.games import chessgame as cg
from bot.games import seabattle as sb
from bot.handlers.economy import _pair_win_allowed
from bot.mod_service import real_reply
from bot.targets import mention

router = Router(name="boardgames")

_CMD = {"chess": r"^(?:шахматы|chess)$", "checkers": r"^(?:шашки|checkers)$", "sea": r"^(?:морской бой|морбой)$"}
_CMD_RE = [(g, re.compile(p, re.IGNORECASE)) for g, p in _CMD.items()]
_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
_chat_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()
_PIECE = {"w": "⚪", "W": "🔆", "b": "🔴", "B": "❤️", " ": ""}


def _name(p: dict) -> str:
    return str(mention(p["id"], p["name"]))


def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text=t, callback_data=c) for t, c in row] for row in rows])


# ---------- отрисовка ----------
def _header(d: dict) -> str:
    p0, p1 = d["players"]
    icons = {"chess": ("⚪", "⚫"), "checkers": ("⚪", "🔴"), "sea": ("🎯", "🎯")}[d["game"]]
    return f"<b>{bgm.TITLES[d['game']]}</b>\n{icons[0]} {_name(p0)}  vs  {icons[1]} {_name(p1)}"


def _status(d: dict) -> str:
    p = d["players"][d["turn"]]
    lines = [f"Ход: {_name(p)}"]
    if d["game"] == "chess" and bgm.chess_in_check(d):
        lines[0] += " — шах!"
    if d["game"] == "checkers" and d["lock"] is not None:
        lines[0] += " — бейте дальше"
    if d["game"] == "sea":
        lines.append("Кораблей осталось: " + " · ".join(
            f"{_name(d['players'][i])} — {sb.ships_left(d['sides'][i])}" for i in (0, 1)))
    if d["last"]:
        lines.append(f"Последний ход: {d['last']}")
    if d["draw"] is not None:
        lines.append(f"🤝 {_name(d['players'][d['draw']])} предлагает ничью")
    if d["game"] == "checkers":
        lines.append("<i>⚪/🔆 белые (дамка), 🔴/❤️ красные (дамка)</i>")
    return "\n".join(lines)


def play_text(d: dict) -> str:
    return f"{_header(d)}\n{_status(d)}"


def play_keyboard(d: dict) -> InlineKeyboardMarkup:
    gid = d["id"]
    rows: list[list[tuple[str, str]]] = []
    if d["game"] == "chess":
        s, sel, targets = bgm.chess_state(d), d.get("sel"), bgm.chess_targets(d)
        for r in range(8):
            row = []
            for c in range(8):
                sq = r * 8 + c
                p = s.board[sq]
                if sq == sel:
                    label = "🔵"
                elif sq in targets:
                    label = "🟥" if p != " " else "🟩"
                else:
                    label = cg.SYMBOL.get(p) or ("▫️" if (r + c) % 2 == 0 else "▪️")
                row.append((label, f"bg:{gid}:s:{sq}"))
            rows.append(row)
    elif d["game"] == "checkers":
        board, sel, targets = bgm.checkers_board(d), d.get("sel"), bgm.checkers_targets(d)
        for r in range(8):
            row = []
            for c in range(8):
                pos = r * 8 + c
                if pos == sel:
                    label = "🔵"
                elif pos in targets:
                    label = "🟩"
                elif board[pos] != " ":
                    label = _PIECE[board[pos]]
                else:
                    label = "▪️" if (r + c) % 2 == 1 else "▫️"
                row.append((label, f"bg:{gid}:s:{pos}"))
            rows.append(row)
    else:
        tgt = bgm.sea_target(d)
        for r in range(sb.SIZE):
            rows.append([(bgm.sea_cell_label(tgt, r * sb.SIZE + c), f"bg:{gid}:s:{r * sb.SIZE + c}") for c in range(sb.SIZE)])
    control = [("🏳️ Сдаться", f"bg:{gid}:res")]
    if d["game"] != "sea":
        control.append(("🤝 Ничья", f"bg:{gid}:dr"))
    rows.append(control)
    return _kb(rows)


def final_text(d: dict, result: dict) -> str:
    p0, p1 = d["players"]
    body = ""
    if d["game"] == "chess":
        s = bgm.chess_state(d)
        body = "\n".join("".join(cg.SYMBOL.get(s.board[r * 8 + c]) or "·" for c in range(8)) for r in range(8))
    elif d["game"] == "checkers":
        b = bgm.checkers_board(d)
        body = "\n".join("".join(_PIECE.get(b[r * 8 + c]) or ("▪️" if (r + c) % 2 else "▫️") for c in range(8)) for r in range(8))
    else:
        body = (f"{_name(p0)}:\n" + "\n".join(bgm.sea_reveal(d["sides"][0])) +
                f"\n\n{_name(p1)}:\n" + "\n".join(bgm.sea_reveal(d["sides"][1])))
    w = result["winner"]
    verdict = (f"{emoji('trophy')} Победил {_name(d['players'][w])} ({result['why']})!" if w is not None
               else f"🤝 Ничья: {result['why']}.")
    return f"{_header(d)}\n{body}\n{verdict}"


def invite_text(d: dict) -> str:
    p0, p1 = d["players"]
    who = f"вызывает {_name(p1)}" if p1 else "ищет соперника"
    return f"{bgm.TITLES[d['game']]}: {_name(p0)} {who}!"


def invite_keyboard(d: dict) -> InlineKeyboardMarkup:
    return _kb([[("⚔️ Принять вызов", f"bg:{d['id']}:acc"), ("Отмена", f"bg:{d['id']}:dec")]])


# ---------- команды ----------
@router.message(F.text.func(lambda t: bool(t) and any(rx.match(t.strip()) for _, rx in _CMD_RE)))
async def challenge(message: Message, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup"):
        await ux.tell(message, "⚠️ Игры для двоих работают в группах.")
        return
    if not (await db.get_settings(message.chat.id))["games_on"]:
        return
    game = next(g for g, rx in _CMD_RE if rx.match(message.text.strip()))
    a, r = message.from_user, real_reply(message)
    b = r.from_user if r is not None and r.from_user is not None else None
    if b is not None and (b.is_bot or b.id == a.id):
        await ux.tell(message, "⚠️ Выберите живого соперника, не себя и не бота 🙂")
        return
    async with _chat_locks.setdefault(message.chat.id, asyncio.Lock()):
        for g in await db.chat_bgames(message.chat.id):
            ids = {p["id"] for p in g["players"] if p}
            if a.id in ids or (b is not None and b.id in ids):
                await ux.tell(message, "⚠️ Вы или соперник уже в игре — доиграйте или сдайтесь.")
                return
        d = bgm.init_game(game)
        d.update(id=uuid.uuid4().hex[:8], chat_id=message.chat.id, state="invite",
                 players=[{"id": a.id, "name": a.full_name}, {"id": b.id, "name": b.full_name} if b else None],
                 expires_at=int(time.time()) + bgm.INVITE_TIMEOUT)
        m = await message.answer(invite_text(d), reply_markup=invite_keyboard(d))
        d["message_id"] = m.message_id
        await db.save_bgame(d)


async def _finish(msg, db: Database, d: dict, result: dict) -> None:
    if not await db.delete_bgame(d["id"]):
        return
    w = result["winner"]
    if w is not None and _pair_win_allowed(d["chat_id"], d["players"][0]["id"], d["players"][1]["id"]):
        await db.add_win(d["chat_id"], d["players"][w]["id"])
    await msg.edit_text(final_text(d, result), reply_markup=None)


def _idx(d: dict, uid: int) -> int | None:
    for i, p in enumerate(d["players"]):
        if p and p["id"] == uid:
            return i
    return None


@router.callback_query(F.data.startswith("bg:"))
async def on_press(cb: CallbackQuery, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) < 3 or cb.message is None:
        await cb.answer()
        return
    gid, op, arg = parts[1], parts[2], (parts[3] if len(parts) > 3 else None)
    async with _locks.setdefault(gid, asyncio.Lock()):
        d = await db.get_bgame(gid)
        if d is None:
            await cb.answer("Игра уже закончилась.", show_alert=True)
            return
        if cb.message.chat.id != d["chat_id"] or cb.message.message_id != d["message_id"]:
            await cb.answer("Эта кнопка относится к другой игре.", show_alert=True)
            return
        uid, now = cb.from_user.id, int(time.time())
        if d["expires_at"] <= now:
            await cb.answer("Время вышло.", show_alert=True)
            return

        if d["state"] == "invite":
            host = d["players"][0]
            if op == "dec":
                if uid != host["id"] and not (d["players"][1] and uid == d["players"][1]["id"]):
                    await cb.answer("Отменить может автор вызова или тот, кого вызвали.", show_alert=True)
                    return
                await db.delete_bgame(gid)
                await cb.message.edit_text(f"{emoji('fail')} Игра отменена.", reply_markup=None)
                await cb.answer()
            elif op == "acc":
                inv = d["players"][1]
                if uid == host["id"] or (inv is not None and uid != inv["id"]):
                    await cb.answer("Принять может только соперник.", show_alert=True)
                    return
                for g in await db.chat_bgames(d["chat_id"]):
                    if g["id"] != gid and uid in {p["id"] for p in g["players"] if p}:
                        await cb.answer("Вы уже играете другую партию.", show_alert=True)
                        return
                d["players"][1] = {"id": uid, "name": cb.from_user.full_name}
                d.update(state="play", expires_at=now + bgm.MOVE_TIMEOUT)
                await db.save_bgame(d)
                await cb.message.edit_text(play_text(d), reply_markup=play_keyboard(d))
                await cb.answer()
            else:
                await cb.answer("Игра ещё не началась.", show_alert=True)
            return

        idx = _idx(d, uid)
        if idx is None:
            await cb.answer("Вы не участвуете в этой игре.", show_alert=True)
            return
        result = None
        try:
            if op == "res":
                result = bgm.resign(d, idx)
            elif op == "dr":
                result = bgm.offer_draw(d, idx)
            elif op == "s" and arg is not None and arg.isascii() and arg.isdigit():
                result = bgm.press(d, idx, int(arg))
            else:
                await cb.answer()
                return
        except bgm.MoveError as e:
            await cb.answer(str(e), show_alert=True)
            return
        if result is not None:
            await _finish(cb.message, db, d, result)
            await cb.answer()
            return
        d["expires_at"] = now + bgm.MOVE_TIMEOUT
        await db.save_bgame(d)
        try:
            await cb.message.edit_text(play_text(d), reply_markup=play_keyboard(d))
        except Exception:
            pass                                        # «сообщение не изменилось» — не ошибка
        await cb.answer()


async def bgame_watchdog(bot, db: Database) -> None:
    """Раз в 15 секунд закрывает просроченные приглашения и партии (кто не ходил — тот проиграл)."""
    while True:
        await asyncio.sleep(15)
        try:
            for g in await db.expired_bgames(int(time.time())):
                async with _locks.setdefault(g["id"], asyncio.Lock()):
                    d = await db.get_bgame(g["id"])
                    if d is None or d["expires_at"] > int(time.time()):
                        continue
                    if d["state"] != "play":
                        await db.delete_bgame(d["id"])
                        text, markup = f"{emoji('fail')} Никто не принял вызов — игра закрыта.", None
                    else:
                        res = bgm.timeout_result(d)
                        if not await db.delete_bgame(d["id"]):
                            continue
                        w = res["winner"]
                        if _pair_win_allowed(d["chat_id"], d["players"][0]["id"], d["players"][1]["id"]):
                            await db.add_win(d["chat_id"], d["players"][w]["id"])
                        text, markup = final_text(d, res), None
                    try:
                        await bot.edit_message_text(text, chat_id=d["chat_id"], message_id=d["message_id"], reply_markup=markup)
                    except Exception:
                        pass
        except Exception:
            logging.exception("bgame watchdog")
