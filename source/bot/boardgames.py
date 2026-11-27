"""Логика настольных игр для двух игроков (шахматы, шашки, морской бой) без Telegram: состояние — словарь,
который целиком кладётся в JSON. Хендлер (bot/handlers/boardgames.py) только рисует кнопки и вызывает эти функции.

Состояние игры d: {"game", "turn": 0|1, "sel": клетка|None, "last": текст последнего хода, "draw": кто предложил ничью,
...данные игры}. Игрок 0 — белые / первый стреляет, игрок 1 — чёрные / второй."""
from __future__ import annotations

import random

from bot.games import checkers as ck
from bot.games import chessgame as cg
from bot.games import seabattle as sb

TITLES = {"chess": "♟ Шахматы", "checkers": "⚪ Шашки", "sea": "🚢 Морской бой"}
MOVE_TIMEOUT = 600
INVITE_TIMEOUT = 180
SIDE = ("w", "b")


class MoveError(Exception):
    """Ход отклонён; текст показывается игроку во всплывающем окне."""


def init_game(game: str, rng: random.Random | None = None) -> dict:
    d: dict = {"game": game, "turn": 0, "sel": None, "last": "", "draw": None}
    if game == "chess":
        d["pos"] = cg.State().dump()
    elif game == "checkers":
        d.update(board="".join(ck.new_board()), lock=None, quiet=0)
    elif game == "sea":
        d["sides"] = [sb.new_side(rng), sb.new_side(rng)]
    else:
        raise ValueError(game)
    return d


# ---------- общий ввод ----------
def press(d: dict, idx: int, cell: int) -> dict | None:
    """Нажатие на клетку игроком idx. None — игра продолжается; иначе итог: {"winner": 0|1|None, "why": текст}.
    MoveError — ход не принят (игра не изменилась)."""
    if idx != d["turn"]:
        raise MoveError("Сейчас не ваш ход.")
    if d["game"] == "chess":
        return _press_chess(d, idx, cell)
    if d["game"] == "checkers":
        return _press_checkers(d, idx, cell)
    return _press_sea(d, idx, cell)


def resign(d: dict, idx: int) -> dict:
    return {"winner": 1 - idx, "why": "соперник сдался"}


def offer_draw(d: dict, idx: int) -> dict | None:
    """Ничья по согласию: первый нажимает — предлагает, второй — принимает; повторное нажатие отзывает предложение."""
    if d["game"] == "sea":
        raise MoveError("В морском бое ничьей не бывает.")
    if d["draw"] is None:
        d["draw"] = idx
        return None
    if d["draw"] == idx:
        d["draw"] = None
        return None
    return {"winner": None, "why": "ничья по согласию"}


def timeout_result(d: dict) -> dict:
    return {"winner": 1 - d["turn"], "why": "время на ход вышло"}


# ---------- шахматы ----------
def chess_state(d: dict) -> cg.State:
    return cg.State.load(d["pos"])


def chess_targets(d: dict) -> set[int]:
    sel = d.get("sel")
    if sel is None:
        return set()
    return {to for frm, to, _ in cg.legal_moves(chess_state(d)) if frm == sel}


def _press_chess(d: dict, idx: int, sq: int) -> dict | None:
    s = chess_state(d)
    moves = cg.legal_moves(s)
    piece = s.board[sq] if 0 <= sq < 64 else " "
    mine = piece != " " and piece.isupper() == (idx == 0)
    sel = d.get("sel")
    if mine:
        if sel == sq:
            d["sel"] = None
            return None
        if not any(frm == sq for frm, _, _ in moves):
            raise MoveError("Эта фигура сейчас не может ходить.")
        d["sel"] = sq
        return None
    if sel is None:
        raise MoveError("Сначала выберите свою фигуру.")
    mv = next((m for m in moves if m[0] == sel and m[1] == sq), None)
    if mv is None:
        raise MoveError("Так ходить нельзя.")
    d["last"] = f"{cg.square_name(mv[0])}–{cg.square_name(mv[1])}"
    n = cg.make_move(s, mv)
    d["pos"], d["sel"], d["draw"] = n.dump(), None, None
    d["turn"] = 1 - idx
    res = cg.outcome(n)
    if res in ("w", "b"):
        return {"winner": 0 if res == "w" else 1, "why": "мат"}
    if res:
        return {"winner": None, "why": {"stalemate": "пат", "draw50": "правило 50 ходов", "draw3": "троекратное повторение",
                                        "insufficient": "недостаточно материала"}[res]}
    return None


def chess_in_check(d: dict) -> bool:
    return cg.in_check(chess_state(d))


# ---------- шашки ----------
def checkers_board(d: dict) -> list[str]:
    return list(d["board"])


def checkers_targets(d: dict) -> set[int]:
    sel = d.get("sel")
    if sel is None:
        return set()
    return {to for to, _ in ck.legal_moves(checkers_board(d), SIDE[d["turn"]], d["lock"]).get(sel, [])}


def _press_checkers(d: dict, idx: int, pos: int) -> dict | None:
    board, side = checkers_board(d), SIDE[idx]
    if not 0 <= pos < 64:
        raise MoveError("Вне доски.")
    moves = ck.legal_moves(board, side, d["lock"])
    sel = d.get("sel")
    if ck.side_of(board[pos]) == side:
        if d["lock"] is not None and pos != d["lock"]:
            raise MoveError("Продолжайте бить той же шашкой.")
        if sel == pos and d["lock"] is None:
            d["sel"] = None
            return None
        if pos not in moves:
            raise MoveError("Этой шашкой ходить нельзя" + (" — есть обязательное взятие." if any(
                c is not None for ms in moves.values() for _, c in ms) else "."))
        d["sel"] = pos
        return None
    if sel is None:
        raise MoveError("Сначала выберите свою шашку.")
    try:
        info = ck.apply_move(board, side, sel, pos, d["lock"])
    except ck.IllegalMove:
        raise MoveError("Так ходить нельзя.")
    d["board"] = "".join(board)
    d["quiet"] = 0 if (info["captured"] or info["quiet_man"]) else d["quiet"] + 1
    d["last"] = f"{_cell(sel)}→{_cell(pos)}" + (" (взятие)" if info["captured"] else "") + (" · дамка!" if info["promoted"] else "")
    d["draw"] = None
    if info["lock"] is not None:                       # серия взятий: тот же игрок бьёт дальше
        d["lock"], d["sel"] = info["lock"], info["lock"]
        return None
    d["lock"], d["sel"] = None, None
    d["turn"] = 1 - idx
    res = ck.result(board, SIDE[d["turn"]], None, d["quiet"])
    if res == "draw":
        return {"winner": None, "why": "ничья: долго без взятий"}
    if res in ("w", "b"):
        return {"winner": SIDE.index(res), "why": "у соперника нет ходов"}
    return None


def _cell(pos: int) -> str:
    return "abcdefgh"[pos % 8] + str(8 - pos // 8)


# ---------- морской бой ----------
def sea_target(d: dict) -> dict:
    """Поле, по которому сейчас стреляют (поле соперника игрока, чей ход)."""
    return d["sides"][1 - d["turn"]]


def _press_sea(d: dict, idx: int, cell: int) -> dict | None:
    target = d["sides"][1 - idx]
    try:
        r = sb.shoot(target, cell)
    except ValueError as e:
        raise MoveError(str(e).capitalize() + ".")
    name = f"{'abcdefgh'[cell % 8]}{cell // 8 + 1}"
    if sb.all_sunk(target):
        d["last"] = f"{name}: потоплен последний корабль"
        return {"winner": idx, "why": "весь флот потоплен"}
    if r["result"] == "miss":
        d["last"] = f"{name}: мимо"
        d["turn"] = 1 - idx
    elif r["result"] == "hit":
        d["last"] = f"{name}: попадание! Стреляйте ещё"
    else:
        d["last"] = f"{name}: корабль потоплен! Стреляйте ещё"
    return None


def sea_cell_label(side: dict, cell: int) -> str:
    v = side["shots"].get(str(cell))
    return {sb.MISS: "🌊", sb.HIT: "💥"}.get(v, "⬜")


def sea_reveal(side: dict) -> list[str]:
    """Строки поля с кораблями (для финального сообщения)."""
    rows = []
    for r in range(sb.SIZE):
        line = ""
        for c in range(sb.SIZE):
            cell = r * sb.SIZE + c
            ship = any(cell in s for s in side["ships"])
            v = side["shots"].get(str(cell))
            line += "💥" if (ship and v == sb.HIT) else "🚢" if ship else "🌊" if v == sb.MISS else "⬜"
        rows.append(line)
    return rows
