"""Сообщество: игры, пары и семья, мафия, РП, экономика и развлекательные команды.

Файл собран из нескольких исходных модулей; каждый начинается с шапки «МОДУЛЬ: bot/<путь>.py».
Ищите по слову «МОДУЛЬ:» (Ctrl+F). Пути вида handlers/xxx.py в комментариях — это такие разделы.
"""
from __future__ import annotations

import asyncio
import datetime as datetime__i2
import hashlib
import html
import json
import logging
import random
import re
import time
import uuid
from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ChatPermissions,
    FSInputFile,
    InlineKeyboardButton as B,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from dataclasses import dataclass, field
from datetime import date, datetime as datetime__i1
from pathlib import Path
from weakref import WeakValueDictionary

# имена из более ранних файлов
from bot.data import DAY__db, Database, USERNAMES
from bot.core import (
    Btn,
    Enabled,
    Html,
    ModCommand,
    Screen,
    check,
    emoji,
    ensure,
    fetch_weather,
    get,
    gz,
    kb__gender,
    kb__rich_ui,
    kv_table,
    listed,
    mention__targets,
    need_rank,
    on_pick,
    ping,
    pre_table,
    resolve_user,
    say,
    send__rich_ui,
    show,
    table_or_text,
    tell,
    to_classic,
    valid_city,
)
from bot.services import (
    ABORT_UNTIL_WEEK,
    ACTIONS__data,
    BADGE,
    BIRTH_WARMTH,
    CAPTION_MAX__giveaway,
    CARDS,
    CARE__baby,
    CARE__kids,
    CARE__pets,
    COINS,
    COOLDOWN__collectibles,
    CRITERIA,
    CalcError,
    DAY_TOGETHER_WARMTH,
    EGG_PRICE,
    FAMILY_MAP,
    Family,
    GIFTS,
    HOUSES,
    KID_UPKEEP,
    MAX_PETS,
    MAX_WINNERS,
    PAIR_MAP,
    PETS_MAX,
    PRICE,
    PairService,
    QUARREL_HOURS__pair_economy,
    QUARREL_HOURS__pair_premium,
    RARITY,
    RARITY_NAME,
    REQUEST_TTL,
    ROOMS,
    ROOM_MAX,
    RP_MAP,
    SECTIONS,
    SERIES,
    SKILL_NAMES,
    TEXT_MAX,
    TOTAL,
    WARMTH_PCT,
    WEEKS,
    active,
    avatar__media,
    avatar_info,
    best_action,
    calc,
    can_trade,
    catalog,
    check_end,
    check_publish,
    clean_verdict,
    collectible_usernames,
    convert,
    draw,
    effective_streak,
    extra_gif,
    fact_of_day,
    fetch_crypto,
    fetch_rates,
    find__collectibles,
    find_action,
    find_house,
    find_rp,
    fingerprint,
    fit,
    fmt_duration,
    fmt_num,
    fmt_time,
    font,
    income,
    is_adult,
    is_sleeping,
    label,
    level_name,
    level_step,
    mog_card,
    next_action,
    norm__data,
    normalized_jpeg,
    parse_crypto,
    parse_money,
    parse_rating,
    parse_route,
    parse_rp,
    parse_sign,
    parse_when,
    partner_of,
    payload,
    prestige__gifts,
    quote_card,
    rank_name,
    rate_prompt,
    reply_gif,
    room_cost,
    route,
    rule_rating,
    scores_from,
    series_progress,
    shuffled,
    side_of__service,
    since_text,
    stage,
    streak_bonus,
    text,
    threshold,
    total,
    trimester,
    tz_of,
    unlocked,
    upkeep_amount,
    upkeep_base,
    verdict_prompt,
    verdict_system,
    warmth__gifts,
    wiki,
    winner__mog,
)
from bot.moderation import apply__mod_service, can_configure, effective_rank, get_member, is_admin__mod_service, real_reply



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/games/checkers.py
# Русские шашки: обязательное взятие, взятие назад, дамки ходят и бьют через всю диагональ, серия взятий одной шашкой.
#
# Доска — список из 64 клеток (индекс = ряд*8 + столбец, ряд 0 — сверху). Чёрные стоят сверху и ходят вниз,
# белые снизу и ходят вверх. Фигуры: w, W (дамка), b, B (дамка), пробел — пусто.
# Упрощение: взятая шашка снимается сразу, а не в конце хода — на практике разница видна лишь в редких позициях.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
DIRS = ((-1, -1), (-1, 1), (1, -1), (1, 1))
NO_PROGRESS_LIMIT = 60          # полуходов без взятия и без хода простой шашкой — ничья


def new_board__checkers() -> list[str]:
    b = [" "] * 64
    for r in range(8):
        for c in range(8):
            if (r + c) % 2 == 1:
                if r < 3:
                    b[r * 8 + c] = "b"
                elif r > 4:
                    b[r * 8 + c] = "w"
    return b


def side_of__checkers(p: str) -> str | None:
    return None if p == " " else p.lower()


def _inside(r: int, c: int) -> bool:
    return 0 <= r < 8 and 0 <= c < 8


def captures_from(board: list[str], pos: int) -> list[tuple[int, int]]:
    """Все взятия фигуры с клетки pos: [(куда встать, номер клетки со взятой фигурой)]."""
    p = board[pos]
    if p == " ":
        return []
    me, king = side_of__checkers(p), p.isupper()
    r0, c0 = divmod(pos, 8)
    out = []
    for dr, dc in DIRS:
        r, c = r0 + dr, c0 + dc
        if king:
            while _inside(r, c) and board[r * 8 + c] == " ":
                r, c = r + dr, c + dc
        if not _inside(r, c):
            continue
        victim = board[r * 8 + c]
        if victim == " " or side_of__checkers(victim) == me:
            continue
        lr, lc = r + dr, c + dc
        while _inside(lr, lc) and board[lr * 8 + lc] == " ":
            out.append((lr * 8 + lc, r * 8 + c))
            if not king:
                break
            lr, lc = lr + dr, lc + dc
    return out


def _simple_moves(board: list[str], pos: int) -> list[int]:
    p = board[pos]
    me, king = side_of__checkers(p), p.isupper()
    r0, c0 = divmod(pos, 8)
    out = []
    for dr, dc in DIRS:
        if not king and dr != (-1 if me == "w" else 1):
            continue
        r, c = r0 + dr, c0 + dc
        while _inside(r, c) and board[r * 8 + c] == " ":
            out.append(r * 8 + c)
            if not king:
                break
            r, c = r + dr, c + dc
    return out


def legal_moves__checkers(board: list[str], side: str, lock: int | None = None) -> dict[int, list[tuple[int, int | None]]]:
    """{откуда: [(куда, взятая клетка или None)]}. Есть взятие — разрешены только взятия; lock — серия одной шашкой."""
    caps: dict[int, list] = {}
    for pos, p in enumerate(board):
        if side_of__checkers(p) == side and (lock is None or lock == pos):
            c = captures_from(board, pos)
            if c:
                caps[pos] = c
    if caps or lock is not None:
        return caps
    quiet = {}
    for pos, p in enumerate(board):
        if side_of__checkers(p) == side:
            m = _simple_moves(board, pos)
            if m:
                quiet[pos] = [(to, None) for to in m]
    return quiet


class IllegalMove(ValueError):
    pass


def apply_move(board: list[str], side: str, src: int, dst: int, lock: int | None = None) -> dict:
    """Ход одной шашки. Меняет board. Возвращает {'captured': bool, 'lock': int|None (серия продолжается),
    'promoted': bool, 'quiet_man': bool}. Исключение IllegalMove — ход запрещён."""
    options = legal_moves__checkers(board, side, lock).get(src, [])
    step = next(((to, cap) for to, cap in options if to == dst), None)
    if step is None:
        raise IllegalMove("так ходить нельзя")
    piece = board[src]
    was_man = piece.islower()
    board[src] = " "
    cap = step[1]
    if cap is not None:
        board[cap] = " "
    promoted = False
    if was_man and ((side == "w" and dst // 8 == 0) or (side == "b" and dst // 8 == 7)):
        piece, promoted = piece.upper(), True
    board[dst] = piece
    more = bool(cap is not None and captures_from(board, dst))
    return {"captured": cap is not None, "lock": dst if more else None, "promoted": promoted,
            "quiet_man": cap is None and was_man}


def count(board: list[str], side: str) -> int:
    return sum(1 for p in board if side_of__checkers(p) == side)


def result(board: list[str], to_move: str, lock: int | None, quiet_plies: int) -> str | None:
    """'w' / 'b' — победитель, 'draw' — ничья, None — игра идёт."""
    if not legal_moves__checkers(board, to_move, lock):
        return "b" if to_move == "w" else "w"
    if quiet_plies >= NO_PROGRESS_LIMIT:
        return "draw"
    return None



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/games/chessgame.py
# Шахматы: полные правила (рокировка, взятие на проходе, превращение пешки, мат, пат, ничьи).
#
# Позиция хранится строкой из 64 символов (ряд 0 — восьмая горизонталь), так её легко класть в JSON.
# Превращение пешки — всегда в ферзя (кнопка выбора фигуры сильно усложнила бы доску в чате).
# ════════════════════════════════════════════════════════════════════════════════════════════════════
START = "rnbqkbnr" + "pppppppp" + " " * 32 + "PPPPPPPP" + "RNBQKBNR"
KNIGHT = ((-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1))
KING = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
BISHOP = ((-1, -1), (-1, 1), (1, -1), (1, 1))
ROOK = ((-1, 0), (1, 0), (0, -1), (0, 1))
SYMBOL = {"K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
          "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟"}


PROMOTIONS = "q"            # в игре только ферзь; тесты включают "qrbn", чтобы сверить число ходов с эталоном


class State:
    __slots__ = ("board", "turn", "castling", "ep", "half", "full", "seen")

    def __init__(self, board=START, turn="w", castling="KQkq", ep=-1, half=0, full=1, seen=None):
        self.board = list(board)
        self.turn, self.castling, self.ep, self.half, self.full = turn, castling, ep, half, full
        self.seen: dict[str, int] = dict(seen or {})
        if not self.seen:
            self.seen[self.key()] = 1

    def key(self) -> str:
        return "".join(self.board) + self.turn + self.castling + str(self.ep)

    def copy(self) -> "State":
        s = State.__new__(State)
        s.board, s.turn, s.castling, s.ep, s.half, s.full = list(self.board), self.turn, self.castling, self.ep, self.half, self.full
        s.seen = dict(self.seen)
        return s

    def dump(self) -> dict:
        return {"b": "".join(self.board), "t": self.turn, "c": self.castling, "e": self.ep, "h": self.half,
                "f": self.full, "s": self.seen}

    @staticmethod
    def load(d: dict) -> "State":
        return State(d["b"], d["t"], d["c"], d["e"], d["h"], d["f"], d["s"])


def _own(p: str, side: str) -> bool:
    return p != " " and (p.isupper() == (side == "w"))


def _enemy(p: str, side: str) -> bool:
    return p != " " and (p.isupper() != (side == "w"))


def attacked(board: list[str], sq: int, by: str) -> bool:
    """Бьёт ли сторона by клетку sq."""
    r0, c0 = divmod(sq, 8)
    pawn = "P" if by == "w" else "p"
    pr = r0 + 1 if by == "w" else r0 - 1                  # откуда пешка стороны by бьёт в sq
    for dc in (-1, 1):
        if 0 <= pr < 8 and 0 <= c0 + dc < 8 and board[pr * 8 + c0 + dc] == pawn:
            return True
    kn, ki = ("N", "K") if by == "w" else ("n", "k")
    for dr, dc in KNIGHT:
        r, c = r0 + dr, c0 + dc
        if 0 <= r < 8 and 0 <= c < 8 and board[r * 8 + c] == kn:
            return True
    for dr, dc in KING:
        r, c = r0 + dr, c0 + dc
        if 0 <= r < 8 and 0 <= c < 8 and board[r * 8 + c] == ki:
            return True
    for dirs, pieces in ((BISHOP, "BQ" if by == "w" else "bq"), (ROOK, "RQ" if by == "w" else "rq")):
        for dr, dc in dirs:
            r, c = r0 + dr, c0 + dc
            while 0 <= r < 8 and 0 <= c < 8:
                p = board[r * 8 + c]
                if p != " ":
                    if p in pieces:
                        return True
                    break
                r, c = r + dr, c + dc
    return False


def _king_sq(board: list[str], side: str) -> int:
    return board.index("K" if side == "w" else "k")


def in_check(s: State) -> bool:
    return attacked(s.board, _king_sq(s.board, s.turn), "b" if s.turn == "w" else "w")


def _promos(frm: int, to: int) -> list[tuple[int, int, str]]:
    return [(frm, to, x) for x in PROMOTIONS]


def _pseudo(s: State) -> list[tuple[int, int, str]]:
    """(откуда, куда, флаг) без проверки шаха; флаг: '' | 'q' (превращение) | 'ep' | 'oo' | 'ooo' | 'dp' (двойной ход)."""
    b, side = s.board, s.turn
    out = []
    for sq, p in enumerate(b):
        if not _own(p, side):
            continue
        r0, c0 = divmod(sq, 8)
        kind = p.upper()
        if kind == "P":
            d = -1 if side == "w" else 1
            start, last = (6, 0) if side == "w" else (1, 7)
            r = r0 + d
            if 0 <= r < 8 and b[r * 8 + c0] == " ":
                out.extend(_promos(sq, r * 8 + c0) if r == last else [(sq, r * 8 + c0, "")])
                r2 = r0 + 2 * d
                if r0 == start and b[r2 * 8 + c0] == " ":
                    out.append((sq, r2 * 8 + c0, "dp"))
            for dc in (-1, 1):
                c = c0 + dc
                if 0 <= r < 8 and 0 <= c < 8:
                    t = r * 8 + c
                    if _enemy(b[t], side):
                        out.extend(_promos(sq, t) if r == last else [(sq, t, "")])
                    elif t == s.ep:
                        out.append((sq, t, "ep"))
        elif kind in "NK":
            for dr, dc in (KNIGHT if kind == "N" else KING):
                r, c = r0 + dr, c0 + dc
                if 0 <= r < 8 and 0 <= c < 8 and not _own(b[r * 8 + c], side):
                    out.append((sq, r * 8 + c, ""))
        else:
            dirs = BISHOP if kind == "B" else ROOK if kind == "R" else BISHOP + ROOK
            for dr, dc in dirs:
                r, c = r0 + dr, c0 + dc
                while 0 <= r < 8 and 0 <= c < 8:
                    t = r * 8 + c
                    if _own(b[t], side):
                        break
                    out.append((sq, t, ""))
                    if b[t] != " ":
                        break
                    r, c = r + dr, c + dc
    # рокировка: король и ладья не ходили, поля между пусты, король не под шахом и не проходит через бой
    enemy = "b" if side == "w" else "w"
    home = 60 if side == "w" else 4
    if b[home] == ("K" if side == "w" else "k") and not attacked(b, home, enemy):
        rook = "R" if side == "w" else "r"
        k_right, k_left = ("K", "Q") if side == "w" else ("k", "q")
        if k_right in s.castling and b[home + 3] == rook and b[home + 1] == b[home + 2] == " " \
                and not attacked(b, home + 1, enemy) and not attacked(b, home + 2, enemy):
            out.append((home, home + 2, "oo"))
        if k_left in s.castling and b[home - 4] == rook and b[home - 1] == b[home - 2] == b[home - 3] == " " \
                and not attacked(b, home - 1, enemy) and not attacked(b, home - 2, enemy):
            out.append((home, home - 2, "ooo"))
    return out


def make_move(s: State, mv: tuple[int, int, str]) -> State:
    """Новая позиция после хода (ход должен быть из legal_moves)."""
    frm, to, flag = mv
    n = s.copy()
    b = n.board
    p = b[frm]
    capture = b[to] != " " or flag == "ep"
    b[frm] = " "
    b[to] = p
    if flag in ("q", "r", "b", "n"):
        b[to] = flag.upper() if s.turn == "w" else flag
    elif flag == "ep":
        b[to + (8 if s.turn == "w" else -8)] = " "
    elif flag == "oo":
        b[to - 1], b[to + 1] = b[to + 1], " "
    elif flag == "ooo":
        b[to + 1], b[to - 2] = b[to - 2], " "
    n.ep = (frm + to) // 2 if flag == "dp" else -1
    cs = n.castling
    for sq, ch in ((60, "KQ"), (4, "kq"), (63, "K"), (56, "Q"), (7, "k"), (0, "q")):
        if frm == sq or to == sq:
            for x in ch:
                cs = cs.replace(x, "")
    n.castling = cs
    n.half = 0 if (p.upper() == "P" or capture) else s.half + 1
    if s.turn == "b":
        n.full += 1
    n.turn = "b" if s.turn == "w" else "w"
    k = n.key()
    n.seen = {} if (p.upper() == "P" or capture) else n.seen     # после необратимого хода старые позиции не повторятся
    n.seen[k] = n.seen.get(k, 0) + 1
    return n


def legal_moves__chessgame(s: State) -> list[tuple[int, int, str]]:
    out = []
    enemy = "b" if s.turn == "w" else "w"
    for mv in _pseudo(s):
        n = make_move(s, mv)
        if not attacked(n.board, _king_sq(n.board, s.turn), enemy):
            out.append(mv)
    return out


def insufficient(board: list[str]) -> bool:
    rest = [p.upper() for p in board if p not in (" ", "K", "k")]
    if not rest:
        return True
    if len(rest) == 1 and rest[0] in "BN":
        return True
    return False


def outcome(s: State) -> str | None:
    """'w' / 'b' — победа, 'mate' не нужен; 'stalemate', 'draw50', 'draw3', 'insufficient' — ничья; None — игра идёт."""
    if not legal_moves__chessgame(s):
        if in_check(s):
            return "b" if s.turn == "w" else "w"
        return "stalemate"
    if insufficient(s.board):
        return "insufficient"
    if s.half >= 100:
        return "draw50"
    if s.seen.get(s.key(), 0) >= 3:
        return "draw3"
    return None


def square_name(sq: int) -> str:
    return "abcdefgh"[sq % 8] + str(8 - sq // 8)


def perft(s: State, depth: int) -> int:
    if depth == 0:
        return 1
    return sum(perft(make_move(s, m), depth - 1) for m in legal_moves__chessgame(s))



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/games/seabattle.py
# Морской бой 8×8 с автоматической расстановкой: корабли не касаются друг друга даже углами.
#
# Флот: 4, 3, 2, 2, 1, 1, 1 клеток. Игрок стреляет по полю соперника; попал — стреляет снова.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
SIZE = 8
FLEET = (4, 3, 2, 2, 1, 1, 1)
WATER, SHIP, MISS, HIT = ".", "S", "o", "x"


def _neighbours(cell: int):
    r, c = divmod(cell, SIZE)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            rr, cc = r + dr, c + dc
            if 0 <= rr < SIZE and 0 <= cc < SIZE:
                yield rr * SIZE + cc


def place_fleet(rng: random.Random | None = None) -> list[list[int]]:
    """Список кораблей — каждый список клеток. Расстановка всегда находится (повторные попытки)."""
    rng = rng or random.Random()
    for _ in range(200):
        ships: list[list[int]] = []
        taken: set[int] = set()
        ok = True
        for size in FLEET:
            placed = False
            for _ in range(300):
                horizontal = rng.random() < 0.5
                r = rng.randrange(SIZE if horizontal else SIZE - size + 1)
                c = rng.randrange(SIZE - size + 1 if horizontal else SIZE)
                cells = [r * SIZE + c + (i if horizontal else i * SIZE) for i in range(size)]
                if any(n in taken for cell in cells for n in _neighbours(cell)):
                    continue
                ships.append(cells)
                taken.update(cells)
                placed = True
                break
            if not placed:
                ok = False
                break
        if ok:
            return ships
    raise RuntimeError("не удалось расставить флот")


def new_side(rng: random.Random | None = None) -> dict:
    """Поле одного игрока: его корабли и выстрелы по нему."""
    return {"ships": place_fleet(rng), "shots": {}}      # shots: {клетка(str): 'o' | 'x'}


def shoot(side: dict, cell: int) -> dict:
    """Выстрел по полю side. {'result': 'miss'|'hit'|'sunk', 'sunk_cells': [...]}; ValueError — уже стреляли."""
    if not 0 <= cell < SIZE * SIZE:
        raise ValueError("вне поля")
    key = str(cell)
    if key in side["shots"]:
        raise ValueError("сюда уже стреляли")
    ship = next((s for s in side["ships"] if cell in s), None)
    if ship is None:
        side["shots"][key] = MISS
        return {"result": "miss", "sunk_cells": []}
    side["shots"][key] = HIT
    if all(str(c) in side["shots"] for c in ship):
        for c in ship:                                    # вокруг потопленного корабля — вода: стрелять туда незачем
            for n in _neighbours(c):
                side["shots"].setdefault(str(n), MISS)
        return {"result": "sunk", "sunk_cells": list(ship)}
    return {"result": "hit", "sunk_cells": []}


def ships_left(side: dict) -> int:
    return sum(1 for s in side["ships"] if not all(str(c) in side["shots"] for c in s))


def all_sunk(side: dict) -> bool:
    return ships_left(side) == 0



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/boardgames.py
# Логика настольных игр для двух игроков (шахматы, шашки, морской бой) без Telegram: состояние — словарь,
# который целиком кладётся в JSON. Хендлер (bot/handlers/boardgames.py) только рисует кнопки и вызывает эти функции.
#
# Состояние игры d: {"game", "turn": 0|1, "sel": клетка|None, "last": текст последнего хода, "draw": кто предложил ничью,
# ...данные игры}. Игрок 0 — белые / первый стреляет, игрок 1 — чёрные / второй.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
TITLES = {"chess": "♟ Шахматы", "checkers": "⚪ Шашки", "sea": "🚢 Морской бой"}
MOVE_TIMEOUT = 600
INVITE_TIMEOUT = 180
SIDE = ("w", "b")


class MoveError(Exception):
    """Ход отклонён; текст показывается игроку во всплывающем окне."""


def init_game(game: str, rng: random.Random | None = None) -> dict:
    d: dict = {"game": game, "turn": 0, "sel": None, "last": "", "draw": None}
    if game == "chess":
        d["pos"] = State().dump()
    elif game == "checkers":
        d.update(board="".join(new_board__checkers()), lock=None, quiet=0)
    elif game == "sea":
        d["sides"] = [new_side(rng), new_side(rng)]
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
def chess_state(d: dict) -> State:
    return State.load(d["pos"])


def chess_targets(d: dict) -> set[int]:
    sel = d.get("sel")
    if sel is None:
        return set()
    return {to for frm, to, _ in legal_moves__chessgame(chess_state(d)) if frm == sel}


def _press_chess(d: dict, idx: int, sq: int) -> dict | None:
    s = chess_state(d)
    moves = legal_moves__chessgame(s)
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
    d["last"] = f"{square_name(mv[0])}–{square_name(mv[1])}"
    n = make_move(s, mv)
    d["pos"], d["sel"], d["draw"] = n.dump(), None, None
    d["turn"] = 1 - idx
    res = outcome(n)
    if res in ("w", "b"):
        return {"winner": 0 if res == "w" else 1, "why": "мат"}
    if res:
        return {"winner": None, "why": {"stalemate": "пат", "draw50": "правило 50 ходов", "draw3": "троекратное повторение",
                                        "insufficient": "недостаточно материала"}[res]}
    return None


def chess_in_check(d: dict) -> bool:
    return in_check(chess_state(d))


# ---------- шашки ----------
def checkers_board(d: dict) -> list[str]:
    return list(d["board"])


def checkers_targets(d: dict) -> set[int]:
    sel = d.get("sel")
    if sel is None:
        return set()
    return {to for to, _ in legal_moves__checkers(checkers_board(d), SIDE[d["turn"]], d["lock"]).get(sel, [])}


def _press_checkers(d: dict, idx: int, pos: int) -> dict | None:
    board, side = checkers_board(d), SIDE[idx]
    if not 0 <= pos < 64:
        raise MoveError("Вне доски.")
    moves = legal_moves__checkers(board, side, d["lock"])
    sel = d.get("sel")
    if side_of__checkers(board[pos]) == side:
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
        info = apply_move(board, side, sel, pos, d["lock"])
    except IllegalMove:
        raise MoveError("Так ходить нельзя.")
    d["board"] = "".join(board)
    d["quiet"] = 0 if (info["captured"] or info["quiet_man"]) else d["quiet"] + 1
    d["last"] = f"{_cell__boardgames(sel)}→{_cell__boardgames(pos)}" + (" (взятие)" if info["captured"] else "") + (" · дамка!" if info["promoted"] else "")
    d["draw"] = None
    if info["lock"] is not None:                       # серия взятий: тот же игрок бьёт дальше
        d["lock"], d["sel"] = info["lock"], info["lock"]
        return None
    d["lock"], d["sel"] = None, None
    d["turn"] = 1 - idx
    res = result(board, SIDE[d["turn"]], None, d["quiet"])
    if res == "draw":
        return {"winner": None, "why": "ничья: долго без взятий"}
    if res in ("w", "b"):
        return {"winner": SIDE.index(res), "why": "у соперника нет ходов"}
    return None


def _cell__boardgames(pos: int) -> str:
    return "abcdefgh"[pos % 8] + str(8 - pos // 8)


# ---------- морской бой ----------
def sea_target(d: dict) -> dict:
    """Поле, по которому сейчас стреляют (поле соперника игрока, чей ход)."""
    return d["sides"][1 - d["turn"]]


def _press_sea(d: dict, idx: int, cell: int) -> dict | None:
    target = d["sides"][1 - idx]
    try:
        r = shoot(target, cell)
    except ValueError as e:
        raise MoveError(str(e).capitalize() + ".")
    name = f"{'abcdefgh'[cell % 8]}{cell // 8 + 1}"
    if all_sunk(target):
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
    return {MISS: "🌊", HIT: "💥"}.get(v, "⬜")


def sea_reveal(side: dict) -> list[str]:
    """Строки поля с кораблями (для финального сообщения)."""
    rows = []
    for r in range(SIZE):
        line = ""
        for c in range(SIZE):
            cell = r * SIZE + c
            ship = any(cell in s for s in side["ships"])
            v = side["shots"].get(str(cell))
            line += "💥" if (ship and v == HIT) else "🚢" if ship else "🌊" if v == MISS else "⬜"
        rows.append(line)
    return rows



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/games/garden.py
# Огород: чистая логика (без Telegram и БД). Состояние игрока — обычный dict, его хранит Database.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
H = 3600
START_SLOTS = 3
MAX_SLOTS = 9
WATER_COOLDOWN = H
WATER_BOOST = 0.10   # полив сокращает оставшееся время роста на 10 %
EXPAND_STEP = 300    # цена: 300 × (число уже купленных расширений + 1)


@dataclass(frozen=True)
class Crop:
    name: str
    emoji: str
    cost: int
    seconds: int
    reward: int


CROPS: dict[str, Crop] = {c.name: c for c in (
    Crop("морковь", "🌻", 20, 2 * H, 45),
    Crop("клубника", "🍓", 80, 4 * H, 200),
    Crop("картошка", "🥔", 50, 6 * H, 130),
    Crop("тыква", "🎃", 150, 24 * H, 420),
)}
_STEMS = {"морков": "морковь", "клубник": "клубника", "картош": "картошка", "тыкв": "тыква"}


def find_crop(word: str) -> str | None:
    w = word.strip().lower()
    for stem, name in _STEMS.items():
        if w.startswith(stem):
            return name
    return None


def new_garden() -> dict:
    return {"slots": START_SLOTS, "plots": [None] * START_SLOTS, "last_water": None}


def plant(g: dict, crop: str, now: int) -> int | None:
    """Посадить в первую свободную грядку. Возвращает номер грядки или None, если места нет."""
    for i, p in enumerate(g["plots"]):
        if p is None:
            g["plots"][i] = {"crop": crop, "planted": now, "ready": now + CROPS[crop].seconds}
            return i
    return None


def harvest(g: dict, now: int) -> list[tuple[str, int]]:
    out = []
    for i, p in enumerate(g["plots"]):
        if p and p["ready"] <= now:
            out.append((p["crop"], CROPS[p["crop"]].reward))
            g["plots"][i] = None
    return out


def water(g: dict, now: int) -> tuple[int, int]:
    """Полить всё растущее. Возвращает (сколько грядок полито, секунд до следующего полива)."""
    growing = [p for p in g["plots"] if p and p["ready"] > now]
    if not growing:
        return 0, 0  # поливать нечего — кулдаун не тратим
    if g["last_water"] is not None:
        wait = g["last_water"] + WATER_COOLDOWN - now
        if wait > 0:
            return 0, wait
    for p in growing:
        p["ready"] = now + int((p["ready"] - now) * (1 - WATER_BOOST))
    g["last_water"] = now
    return len(growing), 0


def expand_cost(g: dict) -> int | None:
    if g["slots"] >= MAX_SLOTS:
        return None
    return EXPAND_STEP * (g["slots"] - START_SLOTS + 1)


def expand(g: dict) -> bool:
    if g["slots"] >= MAX_SLOTS:
        return False
    g["slots"] += 1
    g["plots"].append(None)
    return True


def fmt_left(seconds: int) -> str:
    seconds = max(int(seconds), 0)
    h, m = divmod(seconds // 60, 60)
    if h:
        return f"{h} ч {m} мин"
    return f"{max(m, 1)} мин"


def render__games_garden(g: dict, now: int) -> str:
    lines = []
    for i, p in enumerate(g["plots"], 1):
        if p is None:
            lines.append(f"{i}. 🔘 пусто")
            continue
        c = CROPS[p["crop"]]
        if p["ready"] <= now:
            lines.append(f"{i}. {c.emoji} {c.name} — готово ✅")
        else:
            lines.append(f"{i}. 🌱 {c.name} — осталось {fmt_left(p['ready'] - now)}")
    return "\n".join(lines)



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/games/rps.py
# ════════════════════════════════════════════════════════════════════════════════════════════════════
CHOICES = ("камень", "ножницы", "бумага")
_BEATS = {"камень": "ножницы", "ножницы": "бумага", "бумага": "камень"}
ICONS__rps = {"камень": "✊", "ножницы": "✌️", "бумага": "🖐"}


def judge(a: str, b: str) -> int:
    """1 — побеждает a, -1 — b, 0 — ничья."""
    if a == b:
        return 0
    return 1 if _BEATS[a] == b else -1



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/games/slots.py
# Выплаты слотов Telegram (🎰, значения 1..64).
# ════════════════════════════════════════════════════════════════════════════════════════════════════
JACKPOT = 64          # 777
TRIPLES = (1, 22, 43)  # BAR, виноград, лимон


def slots_payout(dice_value: int, bet: int) -> int:
    """Чистый результат ставки: +выигрыш или -bet при проигрыше."""
    if dice_value == JACKPOT:
        return bet * 9   # возврат ×10
    if dice_value in TRIPLES:
        return bet * 4   # возврат ×5
    return -bet



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/games/tictactoe.py
# ════════════════════════════════════════════════════════════════════════════════════════════════════
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def new_board__tictactoe() -> list[str]:
    return [" "] * 9


def move(board: list[str], idx: int, mark: str) -> bool:
    if not 0 <= idx < 9 or board[idx] != " ":
        return False
    board[idx] = mark
    return True


def winner__tictactoe(board: list[str]) -> str | None:
    for a, b, c in LINES:
        if board[a] != " " and board[a] == board[b] == board[c]:
            return board[a]
    return "draw" if " " not in board else None



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/economy.py
# Экономика и азарт: ферма, переводы, рулетка, кубы со ставкой.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__handlers_economy = Router(name="economy")
_rng__handlers_economy = random.Random()

# ===== БАЛАНС ИГРЫ (меняйте числа здесь) =====
FARM_COOLDOWN = 4 * 3600   # «ферма» раз в 4 часа
FARM_AMOUNT = 40           # сколько монет приносит ферма
ROULETTE_COOLDOWN = 60     # пауза между «рулетками», сек
ROULETTE_REWARD = 20       # награда за выживание
ROULETTE_PENALTY = 50      # штраф при «выстреле»
ROULETTE_MUTE = 600        # мут при проигрыше, сек
DICE_TTL = 120             # сколько действует вызов «кубы», сек
MAX_STAKE = 100_000        # максимальная ставка
_T__handlers_economy = r"(@\w+|\d{5,})"   # «цель»: @ник или числовой id
# ТАБЛИЦА КОМАНД: (вид, регулярка). Новая команда: добавьте строку сюда и ветку `elif kind == "...":` в economy_cmd.
# Группы регулярки () попадают в g[0], g[1]… в обработчике.
_PATTERNS__handlers_economy = [
    ("farm", r"^ферма$"),
    ("transfer", r"^передать\s+(\d{1,9})(?:\s+" + _T__handlers_economy + ")?$"),
    ("roulette", r"^(?:русская\s+)?рулетка$"),
    ("dice", r"^кубы(?:\s+(\d{1,6}))?(?:\s+" + _T__handlers_economy + ")?$"),
    ("dice_target_first", r"^кубы\s+" + _T__handlers_economy + r"\s+(\d{1,6})$"),
]
_COMPILED__handlers_economy = [(k, re.compile(p, re.IGNORECASE)) for k, p in _PATTERNS__handlers_economy]
_cool__handlers_economy: dict[tuple, float] = {}   # кулдауны: (вид, чат, пользователь) -> время; чистится в main.rollup_loop
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
def parse__handlers_economy(text: str | None):
    t = re.sub(r"\s+", " ", (text or "").strip())
    for kind, rx in _COMPILED__handlers_economy:
        m = rx.match(t)
        if m:
            g = m.groups()
            if kind == "dice_target_first":
                kind, g = "dice", (g[1], g[0])  # «кубы @ник 50» / «кубы 12345 50» → (ставка, цель)
            return kind, g
    return None


def _fmt_wait__handlers_economy(sec: int) -> str:
    h, m = divmod(max(sec, 0) // 60, 60)
    return f"{h} ч {m} мин" if h else f"{max(m, 1)} мин"


# Группа «игры» включена в настройках чата (games_on)? В личке команды не работают
async def _enabled__handlers_economy(db: Database, m: Message) -> bool:
    return m.chat.type in ("group", "supergroup") and bool((await db.get_settings(m.chat.id))["games_on"])


@router__handlers_economy.message(F.text.func(lambda t: parse__handlers_economy(t) is not None))
# ЕДИНЫЙ ХЕНДЛЕР всех команд экономики: разбор → проверка настройки → ветка по виду команды (farm/transfer/roulette/dice)
async def economy_cmd(message: Message, bot, db: Database) -> None:
    if not await _enabled__handlers_economy(db, message):
        return
    kind, g = parse__handlers_economy(message.text)
    chat, me = message.chat.id, message.from_user.id
    now = int(time.time())
    reply = real_reply(message)
    coin = emoji("coin")

    if kind == "farm":
        got, wait = await db.claim_farm(chat, me, now, FARM_COOLDOWN, FARM_AMOUNT)
        await message.reply(f"🪴 Ферма принесла <b>+{got}</b> {coin}. Следующий сбор через 4 часа." if got
                            else f"🪴 Урожай ещё не созрел. Загляните через {_fmt_wait__handlers_economy(wait)}.")
    elif kind == "transfer":
        amount = int(g[0])
        target = await resolve_user(db, g[1], reply)
        if target is None:
            await tell(message, "⚠️ Ответьте командой на сообщение получателя или укажите @ник.")
            return
        tid, tname = target
        if amount < 1 or tid == me or tid == (await bot.me()).id:
            await tell(message, "⚠️ Так перевести нельзя: нужен другой человек и сумма от 1.")
            return
        if not await db.transfer(chat, me, tid, amount):
            await message.reply(f"{emoji('fail')} Не хватает монет. Баланс: {await db.get_balance(chat, me)} {coin}")
            return
        await message.reply(f"{emoji('ok')} {mention__targets(me, message.from_user.full_name)} {await say(db, me, '⟦передал|передала⟧')} "
                            f"<b>{amount}</b> {coin} → {mention__targets(tid, tname)}")
    elif kind == "roulette":
        key = ("r", chat, me)
        if time.time() - _cool__handlers_economy.get(key, 0) < ROULETTE_COOLDOWN:
            return
        _cool__handlers_economy[key] = time.time()
        if _rng__handlers_economy.randint(1, 6) != 1:
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
        await tell(message, "⚠️ Ответьте командой на сообщение соперника или укажите @ник: <code>кубы 50 @ник</code>")
        return
    tid, tname = target
    if tid == me or tid == (await bot.me()).id:
        await tell(message, "⚠️ Нужен живой соперник, не вы сами и не я.")
        return
    if stake > MAX_STAKE:
        await tell(message, f"⚠️ Максимальная ставка — {MAX_STAKE}.")
        return
    if stake and await db.get_balance(chat, me) < stake:
        await tell(message, "⚠️ У вас не хватает монет на такую ставку.")
        return
    now = time.time()
    for k in [k for k, v in _dice.items() if v["expires"] < now]:
        _dice.pop(k, None)
    if any(v["chat"] == chat and {me, tid} & {v["a"], v["b"]} for v in _dice.values()):
        await tell(message, "⚠️ У одного из вас уже есть незавершённый вызов.")
        return
    did = uuid.uuid4().hex[:8]
    _dice[did] = {"chat": chat, "a": me, "b": tid, "stake": stake, "expires": now + DICE_TTL,
                  "an": message.from_user.full_name, "bn": tname}
    try:
        await message.answer(
            f"🎲 {mention__targets(me, message.from_user.full_name)} вызывает {mention__targets(tid, tname)} на кубы"
            + (f" со ставкой <b>{stake}</b> {emoji('coin')}" if stake else "") + "!\nПринимаете?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                B(text="🎲 Принять", callback_data=f"dice:{did}:yes"), B(text="Отказаться", callback_data=f"dice:{did}:no")]]))
    except BaseException:
        _dice.pop(did, None)
        raise


@router__handlers_economy.callback_query(F.data.startswith("dice:"))
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
    A, Bm = mention__targets(d["a"], d["an"]), mention__targets(d["b"], d["bn"])
    ra, rb = _rng__handlers_economy.randint(1, 6) + _rng__handlers_economy.randint(1, 6), _rng__handlers_economy.randint(1, 6) + _rng__handlers_economy.randint(1, 6)
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



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/boardgames.py
# Шахматы, шашки и морской бой для двоих: «шахматы» (вызов всем) или «шахматы» ответом на сообщение соперника.
# Игра идёт на кнопках в одном сообщении; состояние лежит в БД и переживает перезапуск.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__handlers_boardgames = Router(name="boardgames")

_CMD__handlers_boardgames = {"chess": r"^(?:шахматы|chess)$", "checkers": r"^(?:шашки|checkers)$", "sea": r"^(?:морской бой|морбой)$"}
_CMD_RE__handlers_boardgames = [(g, re.compile(p, re.IGNORECASE)) for g, p in _CMD__handlers_boardgames.items()]
_locks__handlers_boardgames: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
_chat_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()
_PIECE = {"w": "⚪", "W": "🔆", "b": "🔴", "B": "❤️", " ": ""}


def _name__handlers_boardgames(p: dict) -> str:
    return str(mention__targets(p["id"], p["name"]))


def _kb__handlers_boardgames(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text=t, callback_data=c) for t, c in row] for row in rows])


# ---------- отрисовка ----------
def _header(d: dict) -> str:
    p0, p1 = d["players"]
    icons = {"chess": ("⚪", "⚫"), "checkers": ("⚪", "🔴"), "sea": ("🎯", "🎯")}[d["game"]]
    return f"<b>{TITLES[d['game']]}</b>\n{icons[0]} {_name__handlers_boardgames(p0)}  vs  {icons[1]} {_name__handlers_boardgames(p1)}"


def _status(d: dict) -> str:
    p = d["players"][d["turn"]]
    lines = [f"Ход: {_name__handlers_boardgames(p)}"]
    if d["game"] == "chess" and chess_in_check(d):
        lines[0] += " — шах!"
    if d["game"] == "checkers" and d["lock"] is not None:
        lines[0] += " — бейте дальше"
    if d["game"] == "sea":
        lines.append("Кораблей осталось: " + " · ".join(
            f"{_name__handlers_boardgames(d['players'][i])} — {ships_left(d['sides'][i])}" for i in (0, 1)))
    if d["last"]:
        lines.append(f"Последний ход: {d['last']}")
    if d["draw"] is not None:
        lines.append(f"🤝 {_name__handlers_boardgames(d['players'][d['draw']])} предлагает ничью")
    if d["game"] == "checkers":
        lines.append("<i>⚪/🔆 белые (дамка), 🔴/❤️ красные (дамка)</i>")
    return "\n".join(lines)


def play_text(d: dict) -> str:
    return f"{_header(d)}\n{_status(d)}"


def play_keyboard(d: dict) -> InlineKeyboardMarkup:
    gid = d["id"]
    rows: list[list[tuple[str, str]]] = []
    if d["game"] == "chess":
        s, sel, targets = chess_state(d), d.get("sel"), chess_targets(d)
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
                    label = SYMBOL.get(p) or ("▫️" if (r + c) % 2 == 0 else "▪️")
                row.append((label, f"bg:{gid}:s:{sq}"))
            rows.append(row)
    elif d["game"] == "checkers":
        board, sel, targets = checkers_board(d), d.get("sel"), checkers_targets(d)
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
        tgt = sea_target(d)
        for r in range(SIZE):
            rows.append([(sea_cell_label(tgt, r * SIZE + c), f"bg:{gid}:s:{r * SIZE + c}") for c in range(SIZE)])
    control = [("🏳️ Сдаться", f"bg:{gid}:res")]
    if d["game"] != "sea":
        control.append(("🤝 Ничья", f"bg:{gid}:dr"))
    rows.append(control)
    return _kb__handlers_boardgames(rows)


def final_text__handlers_boardgames(d: dict, result: dict) -> str:
    p0, p1 = d["players"]
    body = ""
    if d["game"] == "chess":
        s = chess_state(d)
        body = "\n".join("".join(SYMBOL.get(s.board[r * 8 + c]) or "·" for c in range(8)) for r in range(8))
    elif d["game"] == "checkers":
        b = checkers_board(d)
        body = "\n".join("".join(_PIECE.get(b[r * 8 + c]) or ("▪️" if (r + c) % 2 else "▫️") for c in range(8)) for r in range(8))
    else:
        body = (f"{_name__handlers_boardgames(p0)}:\n" + "\n".join(sea_reveal(d["sides"][0])) +
                f"\n\n{_name__handlers_boardgames(p1)}:\n" + "\n".join(sea_reveal(d["sides"][1])))
    w = result["winner"]
    verdict = (f"{emoji('trophy')} Победил {_name__handlers_boardgames(d['players'][w])} ({result['why']})!" if w is not None
               else f"🤝 Ничья: {result['why']}.")
    return f"{_header(d)}\n{body}\n{verdict}"


def invite_text(d: dict) -> str:
    p0, p1 = d["players"]
    who = f"вызывает {_name__handlers_boardgames(p1)}" if p1 else "ищет соперника"
    return f"{TITLES[d['game']]}: {_name__handlers_boardgames(p0)} {who}!"


def invite_keyboard(d: dict) -> InlineKeyboardMarkup:
    return _kb__handlers_boardgames([[("⚔️ Принять вызов", f"bg:{d['id']}:acc"), ("Отмена", f"bg:{d['id']}:dec")]])


# ---------- команды ----------
@router__handlers_boardgames.message(F.text.func(lambda t: bool(t) and any(rx.match(t.strip()) for _, rx in _CMD_RE__handlers_boardgames)))
async def challenge__handlers_boardgames(message: Message, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup"):
        await tell(message, "⚠️ Игры для двоих работают в группах.")
        return
    if not (await db.get_settings(message.chat.id))["games_on"]:
        return
    game = next(g for g, rx in _CMD_RE__handlers_boardgames if rx.match(message.text.strip()))
    a, r = message.from_user, real_reply(message)
    b = r.from_user if r is not None and r.from_user is not None else None
    if b is not None and (b.is_bot or b.id == a.id):
        await tell(message, "⚠️ Выберите живого соперника, не себя и не бота 🙂")
        return
    async with _chat_locks.setdefault(message.chat.id, asyncio.Lock()):
        for g in await db.chat_bgames(message.chat.id):
            ids = {p["id"] for p in g["players"] if p}
            if a.id in ids or (b is not None and b.id in ids):
                await tell(message, "⚠️ Вы или соперник уже в игре — доиграйте или сдайтесь.")
                return
        d = init_game(game)
        d.update(id=uuid.uuid4().hex[:8], chat_id=message.chat.id, state="invite",
                 players=[{"id": a.id, "name": a.full_name}, {"id": b.id, "name": b.full_name} if b else None],
                 expires_at=int(time.time()) + INVITE_TIMEOUT)
        m = await message.answer(invite_text(d), reply_markup=invite_keyboard(d))
        d["message_id"] = m.message_id
        await db.save_bgame(d)


async def _finish__handlers_boardgames(msg, db: Database, d: dict, result: dict) -> None:
    if not await db.delete_bgame(d["id"]):
        return
    w = result["winner"]
    if w is not None and _pair_win_allowed(d["chat_id"], d["players"][0]["id"], d["players"][1]["id"]):
        await db.add_win(d["chat_id"], d["players"][w]["id"])
    await msg.edit_text(final_text__handlers_boardgames(d, result), reply_markup=None)


def _idx(d: dict, uid: int) -> int | None:
    for i, p in enumerate(d["players"]):
        if p and p["id"] == uid:
            return i
    return None


@router__handlers_boardgames.callback_query(F.data.startswith("bg:"))
async def on_press(cb: CallbackQuery, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) < 3 or cb.message is None:
        await cb.answer()
        return
    gid, op, arg = parts[1], parts[2], (parts[3] if len(parts) > 3 else None)
    async with _locks__handlers_boardgames.setdefault(gid, asyncio.Lock()):
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
                d.update(state="play", expires_at=now + MOVE_TIMEOUT)
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
                result = resign(d, idx)
            elif op == "dr":
                result = offer_draw(d, idx)
            elif op == "s" and arg is not None and arg.isascii() and arg.isdigit():
                result = press(d, idx, int(arg))
            else:
                await cb.answer()
                return
        except MoveError as e:
            await cb.answer(str(e), show_alert=True)
            return
        if result is not None:
            await _finish__handlers_boardgames(cb.message, db, d, result)
            await cb.answer()
            return
        d["expires_at"] = now + MOVE_TIMEOUT
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
                async with _locks__handlers_boardgames.setdefault(g["id"], asyncio.Lock()):
                    d = await db.get_bgame(g["id"])
                    if d is None or d["expires_at"] > int(time.time()):
                        continue
                    if d["state"] != "play":
                        await db.delete_bgame(d["id"])
                        text, markup = f"{emoji('fail')} Никто не принял вызов — игра закрыта.", None
                    else:
                        res = timeout_result(d)
                        if not await db.delete_bgame(d["id"]):
                            continue
                        w = res["winner"]
                        if _pair_win_allowed(d["chat_id"], d["players"][0]["id"], d["players"][1]["id"]):
                            await db.add_win(d["chat_id"], d["players"][w]["id"])
                        text, markup = final_text__handlers_boardgames(d, res), None
                    try:
                        await bot.edit_message_text(text, chat_id=d["chat_id"], message_id=d["message_id"], reply_markup=markup)
                    except Exception:
                        pass
        except Exception:
            logging.exception("bgame watchdog")



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/collect.py
# Коллекционные карточки: «карточка» (раз в 12 часов), «альбом», «каталог», «топ карточек», «обмен 12 на 15» ответом.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__collect = Router(name="collect")
router__collect.message.filter(Enabled("cards_on"))

_T__collect = r"(@\w+|\d{5,})"
_PATTERNS__collect = [
    ("find", r"^(?:карточка|кк)$"),
    ("album", r"^альбом(?:\s+" + _T__collect + ")?$"),
    ("catalog", r"^каталог(?:\s+карточек)?(?:\s+(.+))?$"),
    ("top", r"^топ карточек$"),
    ("view", r"^карточка\s+(.+)$"),
    ("trade", r"^обмен\s+#?(\d{1,3})\s+на\s+#?(\d{1,3})$"),
]
_COMPILED__collect = [(k, re.compile(p, re.IGNORECASE)) for k, p in _PATTERNS__collect]
OFFER_TTL = 120
_offers: dict[str, dict] = {}


def parse__collect(text: str | None):
    t = re.sub(r"\s+", " ", (text or "").strip())
    for kind, rx in _COMPILED__collect:
        m = rx.match(t)
        if m:
            return kind, m.groups()
    return None


def _fmt_wait__collect(sec: int) -> str:
    return f"{sec // 3600} ч {sec % 3600 // 60} мин" if sec >= 3600 else f"{max(sec // 60, 1)} мин"


def render_album(owned: dict[int, int]) -> str:
    lines = []
    for s, (title, items) in enumerate(SERIES.items()):
        row = ""
        for i, (emoji_, _) in enumerate(items):
            cid = s * 10 + i + 1
            row += (emoji_ if owned.get(cid, 0) else "▫️")
        have = sum(1 for i in range(len(items)) if owned.get(s * 10 + i + 1, 0))
        lines.append(f"{title} {have}/{len(items)}\n{row}")
    uniq = sum(1 for n in owned.values() if n)
    return f"📚 Собрано {uniq}/{TOTAL}\n\n" + "\n".join(lines)


@router__collect.message(F.text.func(lambda t: parse__collect(t) is not None))
async def on_cards(message: Message, db: Database) -> None:
    if message.from_user is None:
        return
    kind, g = parse__collect(message.text)
    uid, now = message.from_user.id, int(time.time())

    if kind == "find":
        cid = draw()
        wait = await db.cards_try_find(uid, cid, now, COOLDOWN__collectibles)
        if wait is not None:
            await tell(message, f"🕐 Следующая карточка через {_fmt_wait__collect(wait)}.")
            return
        owned = await db.cards_of(uid)
        extra = "" if owned.get(cid, 0) <= 1 else f"\n♻️ Это дубль (у вас {owned[cid]}) — можно обменять: <code>обмен {cid} на …</code>"
        await message.reply(f"🃏 Вам выпала карточка!\n<b>{html.escape(label(cid))}</b>\n"
                            f"<i>{RARITY_NAME[CARDS[cid]['rarity']]} · серия {html.escape(CARDS[cid]['series'])}</i>{extra}")
    elif kind == "album":
        reply = real_reply(message)
        target = await resolve_user(db, g[0], reply) if (g[0] or reply) else (uid, message.from_user.full_name)
        if target is None:
            await tell(message, "⚠️ Не нашёл такого участника.")
            return
        tid, name = target
        owned = await db.cards_of(tid)
        spare = sum(n - 1 for n in owned.values() if n > 1)
        await message.reply(f"{listed(tid, name)}\n{render_album(owned)}\n♻️ Запасных копий: {spare}",
                            disable_web_page_preview=True)
    elif kind == "catalog":
        arg = (g[0] or "").strip().lower()
        if not arg:
            owned = await db.cards_of(uid)
            lines = [f"{t}: {h}/{n}" for t, h, n in series_progress(owned)]
            await message.reply("🗂 <b>Каталог карточек</b>\n" + "\n".join(lines) +
                                "\n<i>Серия подробно: </i><code>каталог космос</code>\n"
                                f"<i>Шансы: {', '.join(f'{r[1]} {r[0]} {r[2]}%' for r in RARITY)}</i>")
            return
        title = next((t for t in SERIES if arg in t.lower()), None)
        if title is None:
            await tell(message, "⚠️ Нет такой серии. Список — <code>каталог</code>.")
            return
        owned = await db.cards_of(uid)
        s = list(SERIES).index(title)
        lines = []
        for i in range(len(SERIES[title])):
            cid = s * 10 + i + 1
            mark = "✅" if owned.get(cid, 0) else "▫️"
            lines.append(f"{mark} {label(cid)}" + (f" ×{owned[cid]}" if owned.get(cid, 0) > 1 else ""))
        await message.reply(f"🗂 <b>{html.escape(title)}</b>\n" + "\n".join(lines))
    elif kind == "top":
        rows = await db.cards_top(10)
        if not rows:
            await message.reply("🏆 Коллекционеров пока нет — начните с команды <code>карточка</code>.")
            return
        lines = []
        for i, r in enumerate(rows, 1):
            name = (await db.user_name(r["user_id"])) or f"id{r['user_id']}"
            lines.append(f"{i}. {listed(r['user_id'], name, 24)} — {r['uniq']}/{TOTAL} (всего {r['total']})")
        await message.reply("🏆 <b>Топ коллекционеров</b>\n" + "\n".join(lines), disable_web_page_preview=True)
    elif kind == "view":
        cid = find__collectibles(g[0])
        if cid is None:
            await tell(message, "⚠️ Не нашёл такую карточку (укажите номер или точное название).")
            return
        owned = (await db.cards_of(uid)).get(cid, 0)
        c = CARDS[cid]
        await message.reply(f"🃏 <b>{html.escape(label(cid))}</b>\n{RARITY_NAME[c['rarity']]} · {html.escape(c['series'])}\n"
                            f"У вас: {owned}")
    elif kind == "trade":
        reply = real_reply(message)
        if reply is None or reply.from_user is None or reply.from_user.is_bot or reply.from_user.id == uid:
            await tell(message, "⚠️ Напишите <code>обмен 12 на 15</code> ответом на сообщение того, с кем меняетесь.")
            return
        give, get = int(g[0]), int(g[1])
        other = reply.from_user.id
        why = can_trade(await db.cards_of(uid), give, await db.cards_of(other), get)
        if why:
            await tell(message, f"⚠️ Обмен невозможен: {why}.")
            return
        if len(_offers) > 500:
            for k in [k for k, v in _offers.items() if v["exp"] < now]:
                _offers.pop(k, None)
        oid = uuid.uuid4().hex[:8]
        _offers[oid] = {"a": uid, "b": other, "give": give, "get": get, "chat": message.chat.id, "exp": now + OFFER_TTL}
        kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="✅ Согласен", callback_data=f"ctr:{oid}:y"),
                                                    B(text="❌ Нет", callback_data=f"ctr:{oid}:n")]])
        await message.reply(f"🔁 {mention__targets(uid, message.from_user.full_name)} предлагает {mention__targets(other, reply.from_user.full_name)} обмен:\n"
                            f"отдаёт {html.escape(label(give))}\nхочет {html.escape(label(get))}", reply_markup=kb)


@router__collect.callback_query(F.data.startswith("ctr:"))
async def on_trade(cb: CallbackQuery, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or cb.message is None:
        await cb.answer()
        return
    offer = _offers.get(parts[1])
    now = int(time.time())
    if offer is None or offer["exp"] < now:
        _offers.pop(parts[1], None)
        await cb.answer("Предложение устарело.", show_alert=True)
        return
    uid = cb.from_user.id
    if parts[2] == "n":
        if uid not in (offer["a"], offer["b"]):
            await cb.answer("Это не ваш обмен.", show_alert=True)
            return
        _offers.pop(parts[1], None)
        await cb.message.edit_text("❌ Обмен отменён.", reply_markup=None)
        await cb.answer()
        return
    if uid != offer["b"]:
        await cb.answer("Согласиться может только тот, кому предложили.", show_alert=True)
        return
    _offers.pop(parts[1], None)                       # одно предложение — один обмен, даже при быстром двойном нажатии
    ok = await db.cards_swap(offer["a"], offer["give"], offer["b"], offer["get"])
    await cb.message.edit_text("✅ Обмен состоялся!" if ok else "⚠️ Не вышло: у кого-то уже нет запасной копии.", reply_markup=None)
    await cb.answer()



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/duels.py
# Дуэли: крестики-нолики и камень-ножницы-бумага.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__duels = Router(name="duels")

TIMEOUT__duels = 120
_locks__duels: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
_challenge_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()
RPS_CODES = {"rock": "камень", "scissors": "ножницы", "paper": "бумага"}
MARK_ICON = {"X": "❌", "O": "⭕", " ": "🔘"}
GAME_NAME = {"ttt": "Крестики-нолики", "rps": "Камень-ножницы-бумага"}


def _lock__duels(duel_id: str) -> asyncio.Lock:
    return _locks__duels.setdefault(duel_id, asyncio.Lock())


def _name__duels(p: dict) -> str:
    return str(mention__targets(p["id"], p["name"]))


def _kb__duels(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text=t, callback_data=d) for t, d in row] for row in rows])


def _pick_kb(d: dict) -> InlineKeyboardMarkup:
    return _kb__duels([[("❌⭕ Крестики-нолики", f"duel:{d['id']}:pick:ttt")],
                [("✊✌️🖐 Камень-ножницы-бумага", f"duel:{d['id']}:pick:rps")],
                [("Отмена", f"duel:{d['id']}:decline")]])


def _accept_kb(d: dict) -> InlineKeyboardMarkup:
    return _kb__duels([[("⚔️ Принять вызов", f"duel:{d['id']}:accept"),
                 ("Отказаться", f"duel:{d['id']}:decline")]])


def _ttt_kb(d: dict) -> InlineKeyboardMarkup:
    b = d["board"]
    return _kb__duels([[(MARK_ICON[b[r * 3 + c]], f"duel:{d['id']}:m:{r * 3 + c}") for c in range(3)]
                for r in range(3)])


def _rps_kb(d: dict) -> InlineKeyboardMarkup:
    return _kb__duels([[(f"{ICONS__rps[n]} {n}", f"duel:{d['id']}:r:{code}")
                 for code, n in RPS_CODES.items()]])


def _marks(d: dict) -> dict:
    return {"X": d["challenger"], "O": d["opponent"]}


def _turn_text(d: dict) -> str:
    if d["game"] == "ttt":
        mark = d["turn"]
        return (f"{emoji('duel')} <b>Крестики-нолики</b>\n❌ {_name__duels(d['challenger'])}  vs  "
                f"⭕ {_name__duels(d['opponent'])}\nХод: {MARK_ICON[mark]} {_name__duels(_marks(d)[mark])}")
    return (f"{emoji('duel')} <b>Камень-ножницы-бумага</b>\n{_name__duels(d['challenger'])}  vs  "
            f"{_name__duels(d['opponent'])}\nОба выбирают ход (выбор скрыт).")


async def _finish__duels(message, db: Database, d: dict, text: str, winner: dict | None) -> None:
    async with db.atomic():
        if not await db.delete_duel(d["id"]):
            return
        if winner and _pair_win_allowed(d["chat_id"], d["challenger"]["id"], d["opponent"]["id"]):
            await db.add_win(d["chat_id"], winner["id"])
    if winner:
        text += f"\n{emoji('trophy')} Победил {_name__duels(winner)}!"
    await message.edit_text(text, reply_markup=None)


@router__duels.message(F.text.lower() == "дуэль")
async def challenge__duels(message: Message, db: Database) -> None:
    r = real_reply(message)
    if message.chat.type not in ("group", "supergroup"):
        await tell(message, "⚠️ Дуэли работают только в группах.")
        return
    if not (await db.get_settings(message.chat.id))["games_on"]:
        return
    if not r or not r.from_user:
        await tell(message, "⚠️ Напишите <code>дуэль</code> ответом на сообщение соперника.")
        return
    a, b = message.from_user, r.from_user
    if b.is_bot or b.id == a.id:
        await tell(message, "⚠️ Выберите живого соперника, не себя и не бота 🙂")
        return
    async with _challenge_locks.setdefault(message.chat.id, asyncio.Lock()):
        for d in await db.chat_duels(message.chat.id):
            if {d["challenger"]["id"], d["opponent"]["id"]} & {a.id, b.id}:
                await tell(message, "⚠️ У одного из вас уже есть активная дуэль.")
                return
        d = {
            "id": uuid.uuid4().hex[:8], "chat_id": message.chat.id, "game": None, "state": "pick",
            "challenger": {"id": a.id, "name": a.full_name}, "opponent": {"id": b.id, "name": b.full_name},
            "expires_at": int(time.time()) + TIMEOUT__duels,
        }
        m = await message.answer(
            f"{emoji('duel')} {_name__duels(d['challenger'])} вызывает {_name__duels(d['opponent'])}!\n"
            "Вызывающий, выберите игру:", reply_markup=_pick_kb(d))
        d["message_id"] = m.message_id
        await db.save_duel(d)


@router__duels.callback_query(F.data.startswith("duel:"))
async def duel_cb(cb: CallbackQuery, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) < 3 or cb.message is None:
        await cb.answer()
        return
    duel_id, op = parts[1], parts[2]
    arg = parts[3] if len(parts) > 3 else None
    async with _lock__duels(duel_id):
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
            await _finish__duels(msg, db, d, f"{emoji('fail')} Дуэль отменена.", None)
            await cb.answer()
            return

        if op == "pick":
            if d["state"] != "pick" or uid != ch["id"] or arg not in GAME_NAME:
                await cb.answer("Выбирает вызывающий.", show_alert=True)
                return
            d.update(game=arg, state="invite", expires_at=now + TIMEOUT__duels)
            await db.save_duel(d)
            await msg.edit_text(
                f"{emoji('duel')} {_name__duels(ch)} вызывает {_name__duels(op_)} на «{GAME_NAME[arg]}»!",
                reply_markup=_accept_kb(d))
            await cb.answer()
            return

        if op == "accept":
            if d["state"] != "invite" or uid != op_["id"]:
                await cb.answer("Принять может только вызванный игрок.", show_alert=True)
                return
            d["state"] = "play"
            d["expires_at"] = now + TIMEOUT__duels
            if d["game"] == "ttt":
                d.update(board=new_board__tictactoe(), turn="X")
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
            if not isinstance(arg, str) or not arg.isascii() or not arg.isdigit() or not move(d["board"], int(arg), mark):
                await cb.answer("Клетка занята.", show_alert=True)
                return
            res = winner__tictactoe(d["board"])
            if res is None:
                d["turn"] = "O" if mark == "X" else "X"
                d["expires_at"] = now + TIMEOUT__duels
                await db.save_duel(d)
                await msg.edit_text(_turn_text(d), reply_markup=_ttt_kb(d))
            else:
                board = "\n".join("".join(MARK_ICON[c] for c in d["board"][i:i + 3]) for i in (0, 3, 6))
                if res == "draw":
                    await _finish__duels(msg, db, d, f"{board}\n🤝 Ничья!", None)
                else:
                    await _finish__duels(msg, db, d, board, _marks(d)[res])
            await cb.answer()
            return

        if op == "r" and d["game"] == "rps" and arg in RPS_CODES:
            if str(uid) in d["moves"]:
                await cb.answer("Вы уже сделали выбор.", show_alert=True)
                return
            d["moves"][str(uid)] = RPS_CODES[arg]
            if len(d["moves"]) < 2:
                d["expires_at"] = now + TIMEOUT__duels
                await db.save_duel(d)
                await cb.answer("Выбор принят, ждём соперника.")
                return
            a, b = d["moves"][str(ch["id"])], d["moves"][str(op_["id"])]
            r = judge(a, b)
            line = (f"{_name__duels(ch)} {ICONS__rps[a]} vs {ICONS__rps[b]} {_name__duels(op_)}")
            await _finish__duels(msg, db, d, line + ("\n🤝 Ничья!" if r == 0 else ""),
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
                async with _lock__duels(d["id"]):
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
                        text += f"\n{emoji('trophy')} Победил {_name__duels(winner)} (соперник не ответил)."
                    try:
                        await bot.edit_message_text(text, chat_id=d["chat_id"],
                                                    message_id=d["message_id"], reply_markup=None)
                    except Exception:
                        pass
        except Exception:
            logging.exception("duel watchdog")



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/entertainment.py
# Развлечения: инфа, выбери, данет, жребий, монетка, скажи, шипперим, пейринг, погода.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__entertainment = Router(name="entertainment")
_rng__entertainment = random.Random()
COOLDOWN__entertainment = 3
MAX_SAY = 300
_last__entertainment: dict[tuple, float] = {}

_PATTERNS__entertainment = [
    ("info", r"^инфа\s+(.+)$"), ("choose", r"^выбери\s+(.+\s+или\s+.+)$"), ("yesno", r"^данет\s+(.+)$"),
    ("lot", r"^жребий$"), ("coin", r"^монетка$"), ("say", r"^!скажи\s+(.+)$"),
    ("ship", r"^шипперим$"), ("pair", r"^пейринг$"), ("weather", r"^(?:!погода\s+(?:в\s+)?|погода\s+в\s+)(.+)$"),
]
_COMPILED__entertainment = [(k, re.compile(p, re.IGNORECASE | re.DOTALL)) for k, p in _PATTERNS__entertainment]
_YESNO = ["Да ✅", "Нет ❌", "Скорее да 🙂", "Скорее нет 🤔", "Определённо да 💯", "Даже не думай 🚫",
          "Вероятно 🤷", "Звёзды говорят «нет» ✨"]


def parse__entertainment(text: str | None):
    t = re.sub(r"[ \t]+", " ", (text or "").strip())
    for kind, rx in _COMPILED__entertainment:
        m = rx.match(t)
        if m:
            return kind, (m.group(1).strip() if m.groups() else None)
    return None


def split_options(text: str) -> list[str] | None:
    """«чай или кофе или сок» → ['чай', 'кофе', 'сок']; нужно от 2 до 6 непустых вариантов."""
    opts = [o.strip(" ,.;!?") for o in re.split(r"\s+или\s+", text, flags=re.IGNORECASE)]
    opts = [o for o in opts if o]
    return opts if 2 <= len(opts) <= 6 else None


def sanitize_say(text: str) -> str | None:
    """Чтобы «скажи» нельзя было использовать для пингов и чужих команд: @ ломается, ведущие / и ! убираются."""
    text = re.sub(r"@(?=\w)", "@\u200b", text.strip())
    text = text.lstrip("/!.")
    text = re.sub(r"\s+", " ", text)[:MAX_SAY]
    return text or None


def _throttled__entertainment(key: tuple) -> bool:
    now = time.time()
    if now - _last__entertainment.get(key, 0) < COOLDOWN__entertainment:
        return True
    _last__entertainment[key] = now
    return False


@router__entertainment.message(F.text.func(lambda t: parse__entertainment(t) is not None))
async def entertain(message: Message, db: Database, http=None) -> None:
    if message.chat.type not in ("group", "supergroup"):
        return
    chat, uid = message.chat.id, message.from_user.id
    if not (await db.get_settings(chat))["fun_on"] or _throttled__entertainment((chat, uid)):
        return
    kind, arg = parse__entertainment(message.text)
    me = mention__targets(uid, message.from_user.full_name)

    if kind == "info":
        n = _rng__entertainment.randint(0, 100)
        note = " (сотка!)" if n == 100 else (" (ноль)" if n == 0 else "")
        await message.reply(f"📊 Инфа «{html.escape(arg[:200])}» — <b>{n}%</b>{note}")
    elif kind == "choose":
        opts = split_options(arg)
        if opts:
            await message.reply(f"🎯 Выбираю: <b>{html.escape(_rng__entertainment.choice(opts))}</b>")
    elif kind == "yesno":
        await message.reply(f"🔮 {_rng__entertainment.choice(_YESNO)}")
    elif kind == "coin":
        await message.reply("🪙 " + _rng__entertainment.choice(["Орёл", "Решка"]))
    elif kind == "lot":
        pick = await db.random_member(chat)
        if pick:
            await message.reply(f"🎲 Жребий пал на {mention__targets(*pick)}")
    elif kind == "say":
        text = sanitize_say(arg)
        if text:
            await message.answer(f"🗣 {html.escape(text)}\n— {me}")
    elif kind == "ship":
        pair = await db.random_members(chat, 2)
        if len(pair) < 2:
            await tell(message, "⚠️ Я пока знаю слишком мало людей в этом чате 🤷")
        else:
            await message.reply(f"💘 Шипперим: {mention__targets(*pair[0])} + {mention__targets(*pair[1])}")
    elif kind == "pair":
        pair = await db.random_members(chat, 1, exclude=(uid,))
        await message.reply(f"💞 Ваша пара на сегодня: {mention__targets(*pair[0])}" if pair else
                            "Пока не вижу тут никого, кроме вас 🤷")
    elif kind == "weather":
        if not valid_city(arg):
            await tell(message, "⚠️ Укажите город, например: <code>погода Москва</code>")
            return
        text = await fetch_weather(http, arg) if http is not None else None
        await message.reply(f"🌤 {html.escape(text)}" if text else "Не нашёл такой город или сервис погоды недоступен.")



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/family.py
# Семья в чате: брак, отношения, дети. Предложения подтверждаются кнопками.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__handlers_family = Router(name="family")

_T__handlers_family = r"(?:\s+(@\w+|\d{5,}))?"
# (вид, regex, «молчать, если цели нет»): одиночные слова могут быть просто болтовнёй — тогда не отвечаем
_PATTERNS__handlers_family = [
    ("marry", r"^(?:брак)" + _T__handlers_family + "$", False),
    ("marry", r"^(?:предложить брак|пожениться|жениться|выйти замуж)" + _T__handlers_family + "$", False),
    ("my_marriage", r"^(?:мой брак)$", False),
    ("divorce", r"^(?:развод|развестись)$", True),
    ("relation", r"^(?:отношения)" + _T__handlers_family + "$", False),
    ("relation", r"^(?:предложить отношения|встречаться)" + _T__handlers_family + "$", False),
    ("my_relation", r"^(?:мои отношения)$", False),
    ("breakup", r"^расстаться$", True),
    ("adopt", r"^(?:усыновить|удочерить)" + _T__handlers_family + "$", False),
    ("disown", r"^отречься" + _T__handlers_family + "$", False),
    ("leave", r"^уйти из семьи$", True),
    ("my_family", r"^(?:моя семья)$", False),
    ("family", r"^семья" + _T__handlers_family + "$", True),
    ("marriages", r"^браки$", False),
    ("top", r"^топ браков$", False),
    ("bonus", r"^семейный бонус$", False),
]
_COMPILED__handlers_family = [(k, re.compile(p, re.IGNORECASE), quiet) for k, p, quiet in _PATTERNS__handlers_family]
_SINGLE_WORDS = {"пожениться", "жениться", "встречаться", "усыновить", "удочерить", "брак", "отношения"}


@dataclass
class FamCmd:
    kind: str
    target: str | None
    quiet: bool  # если цели нет — не отвечать


def parse_family(text: str | None) -> FamCmd | None:
    t = re.sub(r"\s+", " ", (text or "").strip())
    for kind, rx, quiet in _COMPILED__handlers_family:
        m = rx.match(t)
        if m:
            target = m.group(1) if m.groups() else None
            single = t.lower() in _SINGLE_WORDS
            return FamCmd(kind, target, quiet or single)
    return None


def _kb__handlers_family(rid: str, yes: str, no: str, cancel: bool = True) -> InlineKeyboardMarkup:
    row = [B(text=yes, callback_data=f"fam:{rid}:yes"), B(text=no, callback_data=f"fam:{rid}:no")]
    rows = [row]
    if cancel:
        rows.append([B(text="↩️ Отозвать", callback_data=f"fam:{rid}:x")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _age(since: int, now: int) -> str:
    days = max((now - since) // DAY__db, 0)
    return f"{time.strftime('%d.%m.%Y', time.localtime(since))} ({days} дн.)"


async def _m__handlers_family(db: Database, uid: int) -> str:
    return mention__targets(uid, (await db.user_name(uid)) or f"id{uid}")


# ---------- команды ----------

@router__handlers_family.message(F.text.func(lambda t: parse_family(t) is not None))
async def family_cmd(message: Message, bot, db: Database, http=None) -> None:
    if message.chat.type not in ("group", "supergroup") or not (await db.get_settings(message.chat.id))["rp_on"]:
        return
    cmd = parse_family(message.text)
    chat, me = message.chat.id, message.from_user.id
    if cmd.kind not in ("family", "marriages", "top", "bonus", "my_family", "my_marriage", "my_relation") \
            and not (cmd.quiet and cmd.target is None and real_reply(message) is None) \
            and not await ensure(message, db):
        return
    fam = Family(db)
    now = int(time.time())
    kind = cmd.kind

    if kind in ("marry", "relation", "adopt", "disown", "family"):
        target = await resolve_user(db, cmd.target, real_reply(message))
        if target is None:
            if kind == "family" and cmd.quiet:
                return
            if not cmd.quiet:
                await tell(message, "⚠️ Ответьте командой на сообщение человека или укажите @ник.")
            return
        tid, tname = target
        if kind == "family":
            await message.reply(await _render_family(db, fam, chat, tid, now), disable_web_page_preview=True)
            return
        if tid == (await bot.me()).id:
            await message.reply("🤖 Я всего лишь бот, у меня нет семьи.")
            return
        if kind == "disown":
            ok = await fam.disown(chat, me, tid)
            await message.reply(f"💔 {await _m__handlers_family(db, tid)} больше не ваш ребёнок." if ok
                                else "Этот человек не ваш ребёнок.")
            return
        await _propose(message, bot, db, fam, kind, tid, now)
        return

    if kind == "divorce":
        sp = await fam.spouse(chat, me)
        if not sp:
            return  # «развод» без брака — просто слово в разговоре
        rid = await fam.create_request(chat, "divorce", me, me, 0, now + REQUEST_TTL)
        m = await message.reply(f"💔 {await _m__handlers_family(db, me)}, вы действительно хотите развестись с "
                                f"{await _m__handlers_family(db, sp['partner'])}?", reply_markup=_kb__handlers_family(rid, "Да, развестись", "Отмена", False))
        await fam.set_request_message(rid, m.message_id)
    elif kind == "breakup":
        other = await fam.end_relation(chat, me)
        if other:
            await message.reply(f"💔 {await _m__handlers_family(db, me)} и {await _m__handlers_family(db, other)} больше не пара.")
            await extra_gif(bot, http, chat, FAMILY_MAP["breakup"], await get(db, me), await get(db, other))
    elif kind == "leave":
        if await fam.leave_family(chat, me):
            await message.reply(f"🚪 {await _m__handlers_family(db, me)} {await say(db, me, '⟦ушёл|ушла⟧')} из семьи.")
    elif kind == "my_marriage":
        sp = await fam.spouse(chat, me)
        await message.reply(f"💍 Вы в браке с {await _m__handlers_family(db, sp['partner'])} с {_age(sp['since'], now)}." if sp
                            else "Вы не состоите в браке.")
    elif kind == "my_relation":
        p = await fam.partner(chat, me)
        await message.reply(f"💞 Вы в отношениях с {await _m__handlers_family(db, p['partner'])} с {_age(p['since'], now)}." if p
                            else "У вас нет отношений.")
    elif kind == "my_family":
        await message.reply(await _render_family(db, fam, chat, me, now), disable_web_page_preview=True)
    elif kind in ("marriages", "top"):
        await message.reply(await _render_marriages(db, fam, chat, now, newest=(kind == "marriages")),
                            disable_web_page_preview=True)
    elif kind == "bonus":
        sp = await fam.spouse(chat, me)
        if not sp:
            await tell(message, "⚠️ Семейный бонус только для супругов: сначала поженитесь.")
            return
        got = await fam.claim_bonus(chat, me, now)
        await message.reply(f"{emoji('coin')} Семейный бонус: <b>+{got}</b> монет. Чем больше детей, тем он больше!"
                            if got else "Свой бонус вы сегодня уже получили.")


async def _propose(message: Message, bot, db: Database, fam: Family, kind: str, tid: int, now: int) -> None:
    chat, me = message.chat.id, message.from_user.id
    checker = {"marry": fam.check_marry, "relation": fam.check_relation, "adopt": fam.check_adopt}[kind]
    a, b = await _m__handlers_family(db, me), await _m__handlers_family(db, tid)
    async with db.atomic():
        err = await checker(chat, me, tid)
        busy = not err and (await fam.has_pending(chat, me, now) or await fam.has_pending(chat, tid, now))
        rid = None if err or busy else await fam.create_request(chat, kind, me, tid, 0, now + REQUEST_TTL)
    if err:
        await message.reply(f"{emoji('fail')} {err}")
        return
    if busy:
        await tell(message, "⚠️ У вас или у этого человека уже есть незавершённое предложение.")
        return
    text, yes, no = {
        "marry": (f"💍 {a} делает предложение {b}!\n{b}, вы согласны?", "💍 Да", "💔 Нет"),
        "relation": (f"💞 {a} предлагает {b} встречаться!\n{b}, что скажете?", "💞 Да", "💔 Нет"),
        "adopt": (f"👶 {a} хочет взять {b} в свою семью!\n{b}, вы согласны?", "👨‍👩‍👧 Да", "Нет"),
    }[kind]
    try:
        sent = await message.answer(text, reply_markup=_kb__handlers_family(rid, yes, no))
        await fam.set_request_message(rid, sent.message_id)
    except Exception:
        await fam.delete_request(rid)
        raise


# ---------- кнопки ----------

@router__handlers_family.callback_query(F.data.startswith("fam:"))
async def family_cb(cb: CallbackQuery, db: Database, http=None) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or parts[2] not in ("yes", "no", "x"):
        await cb.answer()
        return
    _, rid, op = parts
    fam = Family(db)
    req = await fam.get_request(rid)
    if (req is None or cb.message is None or req["chat_id"] != cb.message.chat.id
            or req["message_id"] != cb.message.message_id):
        await cb.answer("Это предложение уже недействительно.", show_alert=True)
        return
    uid, now = cb.from_user.id, int(time.time())
    if req["expires_at"] < now:
        await fam.delete_request(rid)
        await cb.answer("Время на ответ вышло.", show_alert=True)
        return
    a, b, chat, kind = req["from_user"], req["to_user"], req["chat_id"], req["kind"]
    decider = a if kind == "divorce" else b

    if op == "x":
        if uid != a:
            await cb.answer("Отозвать может только автор.", show_alert=True)
            return
        await fam.delete_request(rid)
        await cb.message.edit_text("↩️ Предложение отозвано.")
    elif op == "no":
        if uid != decider:
            await cb.answer("Это решение не за вами.", show_alert=True)
            return
        await fam.delete_request(rid)
        await cb.message.edit_text("💔 Отказ." if kind != "divorce" else "Развод отменён.")
    elif op == "yes":
        if uid != decider:
            await cb.answer("Это решение не за вами.", show_alert=True)
            return
        if kind == "divorce":
            # Завершение пары берёт собственную блокировку; не держим перед ней блокировку БД.
            deleted = await fam.delete_request(rid)
            text = await _apply(db, fam, kind, chat, a, b, now) if deleted else ""
        else:
            # При сбое предложение остаётся доступным для повторного подтверждения.
            async with db.atomic():
                deleted = await fam.delete_request(rid)
                text = await _apply(db, fam, kind, chat, a, b, now) if deleted else ""
        if not deleted:
            await cb.answer()
            return
        await cb.message.edit_text(text)
        if "теперь" in text or "больше не" in text:                      # получилось — к тексту добавляем гифку
            await extra_gif(cb.bot, http, chat, FAMILY_MAP.get(kind), await get(db, a), await get(db, b))
    await cb.answer()


async def _apply(db: Database, fam: Family, kind: str, chat: int, a: int, b: int, now: int) -> str:
    A, Bm = await _m__handlers_family(db, a), await _m__handlers_family(db, b)
    if kind == "divorce":
        other = await fam.divorce(chat, a)
        return f"💔 {A} и {await _m__handlers_family(db, other)} больше не в браке." if other else "Вы уже не в браке."
    async with db.atomic():
        check = {"marry": fam.check_marry, "relation": fam.check_relation, "adopt": fam.check_adopt}[kind]
        err = await check(chat, a, b)  # пока ждали ответа, всё могло измениться
        if err:
            return f"{emoji('fail')} Не получилось: {err}"
        if kind == "marry":
            await fam.marry(chat, a, b, now)
            return f"💒 {A} и {Bm} теперь в браке! Совет да любовь 💍\n🔥 Искры, уровень и тепло остаются с вами: <code>пара</code>"
        if kind == "relation":
            await fam.start_relation(chat, a, b, now)
            return (f"💞 {A} и {Bm} теперь пара!\n"
                    "🔥 У вас 100 искр на двоих, раз в сутки часть уходит на жизнь. Пополняйте их делами: <code>пара действия</code>.")
        await fam.adopt(chat, a, b, now)
        return f"👨‍👩‍👧 {Bm} теперь в семье {A}!"


# ---------- отображение ----------

async def _plain__handlers_family(db: Database, uid: int):
    return listed(uid, (await db.user_name(uid)) or f"id{uid}", 28)


async def _render_family(db: Database, fam: Family, chat: int, uid: int, now: int) -> str:
    v = await fam.view(chat, uid)

    async def names(ids):
        return Html(", ".join([await _plain__handlers_family(db, i) for i in ids]) or "—")
    rows = [("Супруг(а)", Html(f"{await _plain__handlers_family(db, v['spouse']['partner'])} · {html.escape(_age(v['spouse']['since'], now))}") if v["spouse"] else "—")]
    if v["partner"]:
        rows.append(("Пара", Html(f"{await _plain__handlers_family(db, v['partner']['partner'])} · {html.escape(_age(v['partner']['since'], now))}")))
    rows += [("Родители", await names(v["parents"])), ("Дети", await names(v["children"]))]
    if v["siblings"]:
        rows.append(("Братья/сёстры", await names(sorted(v["siblings"]))))
    return f"👨‍👩‍👧‍👦 <b>Семья · {await _plain__handlers_family(db, uid)}</b>\n" + kv_table(rows, key_width=13, value_width=34)


async def _render_marriages(db: Database, fam: Family, chat: int, now: int, newest: bool) -> str:
    total = await fam.count_marriages(chat)
    if not total:
        return "💍 В этом чате пока нет браков."
    rows = await fam.list_marriages(chat, 10, max(total - 10, 0) if newest else 0)
    if newest:
        rows = rows[::-1]
    title = "💍 <b>Новые браки</b>" if newest else "🏆 <b>Самые долгие браки</b>"
    table = pre_table([(str(i), Html(f"{await _plain__handlers_family(db, r['u1'])} + {await _plain__handlers_family(db, r['u2'])}"), f"{max((now - r['since']) // DAY__db, 0)} дн.")
                       for i, r in enumerate(rows, 1)], header=("#", "Пара", "Вместе"), align="llr", maxw=(3, 26, 8))
    return f"{title} · всего {total}\n{table}"


async def family_watchdog(bot, db: Database) -> None:
    """Просроченные предложения закрываются сами."""
    fam = Family(db)
    while True:
        await asyncio.sleep(30)
        try:
            for r in await fam.expired_requests(int(time.time())):
                if await fam.delete_request(r["id"]) and r["message_id"]:
                    try:
                        await bot.edit_message_text("⌛ Время вышло, предложение отменено.",
                                                    chat_id=r["chat_id"], message_id=r["message_id"])
                    except Exception:
                        pass
        except Exception:
            logging.exception("family watchdog")



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/fun.py
# Развлечения: «вероятность …» и «кто …» (случайный участник именно этого чата).
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__fun = Router(name="fun")

_PROB_RE = re.compile(r"^(?:вероятность|шанс)(?:[,:]|\s)\s*(?:того,?\s+)?(?:что,?\s+)?(.+?)\s*[?!.]*$",
                      re.IGNORECASE | re.DOTALL)
_WHO_RE = re.compile(r"^кто\s+(.+?)\s*[?!.]*$", re.IGNORECASE | re.DOTALL)
_WORD_RE = re.compile(r"^[\w-]{2,25}$")
_STOP__fun = {"это", "тут", "здесь", "там", "где", "такой", "такая", "такие", "был", "была", "будет", "что",
         "как", "когда", "почему", "зачем", "ты", "вы", "я"}
COOLDOWN__fun = 3
_last__fun: dict[tuple, float] = {}


def parse_probability(text: str | None) -> str | None:
    m = _PROB_RE.match((text or "").strip())
    if not m:
        return None
    body = m.group(1).strip()
    return body if 2 <= len(body) <= 200 else None


def parse_who(text: str | None) -> str | None:
    m = _WHO_RE.match((text or "").strip())
    if not m:
        return None
    words = m.group(1).split()
    if not 1 <= len(words) <= 3 or not all(_WORD_RE.match(w) for w in words):
        return None
    if all(w.lower() in _STOP__fun for w in words):
        return None
    return " ".join(words)


def probability(chat_id: int, user_id: int, text: str, day: str) -> int:
    """0..100. Один и тот же вопрос от одного человека в течение суток даёт один и тот же ответ."""
    norm = re.sub(r"\s+", " ", text.lower()).strip()
    h = hashlib.sha256(f"{chat_id}|{user_id}|{norm}|{day}".encode()).digest()
    return int.from_bytes(h[:4], "big") % 101


def _throttled__fun(key: tuple) -> bool:
    now = time.time()
    if now - _last__fun.get(key, 0) < COOLDOWN__fun:
        return True
    _last__fun[key] = now
    return False


async def _enabled__fun(db: Database, message: Message) -> bool:
    return message.chat.type in ("group", "supergroup") and bool((await db.get_settings(message.chat.id))["fun_on"])


@router__fun.message(F.text.func(lambda t: parse_probability(t) is not None))
async def probability_cmd(message: Message, db: Database) -> None:
    if not await _enabled__fun(db, message) or _throttled__fun(("p", message.chat.id, message.from_user.id)):
        return
    what = parse_probability(message.text)
    n = probability(message.chat.id, message.from_user.id, what, date.today().isoformat())
    await message.reply(f"🎲 «{html.escape(what)}» — вероятность <b>{n}%</b>")


@router__fun.message(F.text.func(lambda t: parse_who(t) is not None))
async def who_cmd(message: Message, db: Database) -> None:
    if not await _enabled__fun(db, message) or _throttled__fun(("w", message.chat.id)):
        return
    phrase = parse_who(message.text)
    pick = await db.random_member(message.chat.id)
    if pick is None:
        await tell(message, "⚠️ Я пока никого здесь не знаю 🤷")
        return
    uid, name = pick
    await db.user_name(uid)   # подтягивает @ник для ссылки
    await message.reply(f'🎯 Кто {html.escape(phrase)}? Однозначно {mention__targets(uid, name)}')



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/games.py
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__handlers_games = Router(name="games")

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
    pass  # (импорт убран: всё в одном модуле)
    users = await db.users_by_ids([uid for uid, _ in rows])
    table_rows = []
    for i, (uid, n) in enumerate(rows, 1):
        name = ((users.get(uid) or {}).get("name") or f"id{uid}")[:28]
        table_rows.append([str(i), (name, f"https://t.me/{USERNAMES[uid]}" if USERNAMES.get(uid) else f"tg://user?id={uid}"), str(n)])
    await table_or_text(message, plain_title, ["#", "Участник", unit.capitalize()], table_rows,
                           await _top_text(message.bot, db, message.chat.id, rows, html_title, unit, users),
                           aligns=["center", "left", "right"], reply=False)


@router__handlers_games.message(F.text.func(lambda t: bool(t) and _SLOTS_RE.match(t.strip()) is not None))
async def slots(message: Message, db: Database) -> None:
    chat_id, uid = message.chat.id, message.from_user.id
    if not await _games_on(db, chat_id):
        return
    arg = _SLOTS_RE.match(message.text.strip()).group(1)
    balance = await db.get_balance(chat_id, uid)
    bet = balance if arg and arg.lower() in ("все", "всё") else int(arg) if arg else DEFAULT_BET
    if bet < 1:
        await tell(message, "Ставка должна быть от 1 монеты.")
        return
    if not await db.try_spend(chat_id, uid, bet):  # атомарное списание
        await tell(message, f"{emoji('fail')} Не хватает монет. Баланс: {balance} {emoji('coin')}")
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


@router__handlers_games.message(F.text.lower() == "баланс")
async def balance(message: Message, db: Database) -> None:
    bal = await db.get_balance(message.chat.id, message.from_user.id)
    await message.reply(f"{emoji('coin')} Ваш баланс: <b>{bal}</b>")      # обычным ответом: не удаляется


@router__handlers_games.message(F.text.lower() == "бонус")
async def bonus(message: Message, db: Database) -> None:
    got = await db.claim_bonus(message.chat.id, message.from_user.id, int(time.time()))
    if got is None:
        await tell(message, "Бонус уже получен сегодня. Приходите завтра!")
    else:
        await message.reply(f"{emoji('ok')} Ежедневный бонус: <b>+{got}</b> {emoji('coin')}")


@router__handlers_games.message(F.text.lower() == "топ")
async def top(message: Message, bot, db: Database) -> None:
    rows = await db.top_balances(message.chat.id)
    await _send_top(message, db, rows, "Богатейшие", f"{emoji('trophy')} <b>Богатейшие</b>", "монет")


@router__handlers_games.message(F.text.lower() == "рейтинг дуэлей")
async def rating(message: Message, bot, db: Database) -> None:
    rows = await db.top_wins(message.chat.id)
    await _send_top(message, db, rows, "Победы в дуэлях", f"{emoji('duel')} <b>Победы в дуэлях</b>", "поб.")



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/garden.py
# Игра «Огород»: сажаем, поливаем, собираем урожай за монеты (общий баланс со слотами).
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__handlers_garden = Router(name="garden")

_PLANT_RE = re.compile(r"^посадить\s+(\S+)(?:\s+(\d{1,2}))?$", re.IGNORECASE)
_EXACT = {"огород", "магазин", "полить", "собрать", "расширить"}
_locks__handlers_garden: WeakValueDictionary[tuple[int, int], asyncio.Lock] = WeakValueDictionary()


def _now() -> int:
    return int(time.time())


def _is_garden(t: str | None) -> bool:
    if not t:
        return False
    t = t.strip().lower()
    return t in _EXACT or t == "посадить" or _PLANT_RE.match(t) is not None


def _shop() -> str:
    table = pre_table([(f"{c.emoji} {c.name}", str(c.cost), fmt_left(c.seconds), str(c.reward)) for c in CROPS.values()],
                      header=("Культура", "Семена", "Растёт", "Урожай"), align="llrr", maxw=(14, 6, 10, 6))
    return ("🛒 <b>Магазин семян</b> (цены в монетах)\n" + table +
            "\nПосадить: <code>посадить морковь</code> (или <code>посадить морковь 3</code>)")


@router__handlers_garden.message(F.text.func(_is_garden))
async def garden_cmd(message: Message, db: Database) -> None:
    chat_id, uid = message.chat.id, message.from_user.id
    if message.chat.type in ("group", "supergroup") and not (await db.get_settings(chat_id))["games_on"]:
        return
    text = message.text.strip().lower()
    async with _locks__handlers_garden.setdefault((chat_id, uid), asyncio.Lock()):
        # Состояние грядок и баланс должны фиксироваться вместе.
        async with db.atomic():
            gd = await db.get_garden(chat_id, uid) or new_garden()
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
        return (f"🌱 <b>Ваш огород</b>\n{render__games_garden(gd, now)}\n\nБаланс: {bal} {emoji('coin')}\n"
                "<code>посадить морковь</code> · <code>полить</code> · <code>собрать</code> · "
                "<code>магазин</code> · <code>расширить</code>"), False
    if text == "полить":
        n, wait = water(gd, now)
        if n:
            return f"💧 Полито грядок: {n}. Рост ускорен на {int(WATER_BOOST * 100)}%.", True
        if wait:
            return f"💧 Земля ещё влажная. Полить снова можно через {fmt_left(wait)}.", False
        return "Поливать нечего: на грядках ничего не растёт.", False
    if text == "собрать":
        got = harvest(gd, now)
        if not got:
            return "Пока нечего собирать: урожай ещё не созрел.", False
        total = sum(r for _, r in got)
        await db.change_balance(chat_id, uid, total)
        names = ", ".join(f"{CROPS[c].emoji} {c}" for c, _ in got)
        return f"{emoji('ok')} Собрано: {names}\nВыручка: <b>+{total}</b> {emoji('coin')}", True
    if text == "расширить":
        cost = expand_cost(gd)
        if cost is None:
            return f"У вас уже максимум грядок ({MAX_SLOTS}).", False
        if not await db.try_spend(chat_id, uid, cost):
            return f"{emoji('fail')} Новая грядка стоит {cost} {emoji('coin')} — не хватает монет.", False
        expand(gd)
        return f"{emoji('ok')} Куплена грядка №{gd['slots']} за {cost} {emoji('coin')}.", True
    # посадить
    m = _PLANT_RE.match(text)
    if not m:
        return "Что посадить? " + _shop(), False
    crop = find_crop(m.group(1))
    if crop is None:
        return "Не знаю такой культуры.\n" + _shop(), False
    free = sum(1 for p in gd["plots"] if p is None)
    if free == 0:
        return "Свободных грядок нет. Соберите урожай или купите грядку: <code>расширить</code>.", False
    want = int(m.group(2)) if m.group(2) else 1
    n = max(1, min(want, free))
    cost = CROPS[crop].cost * n
    if not await db.try_spend(chat_id, uid, cost):
        return f"{emoji('fail')} Не хватает монет: {n} × {crop} стоит {cost} {emoji('coin')}.", False
    for _ in range(n):
        plant(gd, crop, now)
    c = CROPS[crop]
    return (f"{c.emoji} Посажено: {crop} × {n} за {cost} {emoji('coin')}. "
            f"Созреет через {fmt_left(c.seconds)}."), True



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/giveaway.py
# Конкурсы (розыгрыши).
#
# Группа: «+конкурс» (по умолчанию — владелец чата, ДК «конкурсы») → кнопка в личку; «конкурсы» — список;
# «-конкурс N» — отменить; «реролл N» — выбрать другого победителя.
# Личка: пошаговый мастер — текст (можно с фото) → когда опубликовать → когда закончить → сколько победителей → предпросмотр.
# В назначенное время Нори публикует объявление с кнопкой «Участвовать»: она ведёт в личку бота, оттуда открывается Mini App
# с капчей (кнопки Mini App в группах Telegram не разрешает). В конце Нори случайно выбирает победителей среди тех, кто
# всё ещё в чате, и объявляет итоги ответом на объявление.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__handlers_giveaway = Router(name="giveaway")
router__handlers_giveaway.message.filter(Enabled("giveaway_on"))   # группу команд можно выключить в настройках → «Команды»
ACCESS_KEY__handlers_giveaway = "конкурсы"
WATCH_EVERY = 10            # как часто сторож публикует / подводит итоги
COUNT_EDIT_EVERY = 20       # счётчик участников на кнопке обновляем не чаще, чем раз в 20 с
_count_edited: dict[int, float] = {}

_GROUP__handlers_giveaway = re.compile(r"^(?:\+конкурс|\+розыгрыш)$|^(конкурсы|розыгрыши)$|^-(?:конкурс|розыгрыш)\s+(\d{1,9})$"
                    r"|^(?:реролл|перевыбрать)\s+(\d{1,9})$", re.IGNORECASE)
_START_NEW = re.compile(r"^/start gw_(-?\d{1,20})$")
_START_JOIN = re.compile(r"^/start gwj_(\d{1,9})$")
STATUS_RU = {"scheduled": "ждёт публикации", "active": "идёт", "finished": "завершён", "cancelled": "отменён",
             "failed": "не опубликован"}


def _parse_group(text: str | None):
    m = _GROUP__handlers_giveaway.match((text or "").strip())
    if not m:
        return None
    if m.group(1):
        return "list", None
    if m.group(2):
        return "cancel", int(m.group(2))
    if m.group(3):
        return "reroll", int(m.group(3))
    return "new", None


async def _can_manage(bot, db: Database, chat_id: int, user_id: int) -> bool:
    return await effective_rank(bot, db, chat_id, user_id) >= need_rank(await db.get_access(chat_id), ACCESS_KEY__handlers_giveaway)


async def _tz__handlers_giveaway(db: Database, chat_id: int):
    return tz_of((await db.get_settings(chat_id))["tz"])


# ---------- объявление и итоги ----------

def _join_kb(username: str, gid: int, count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text=f"🎟 Участвовать ({count})",
                                                    url=f"https://t.me/{username}?start=gwj_{gid}")]])


def announcement(g: dict, tz) -> str:
    n = g["winners"]
    return (f"{g['text']}\n\n🎁 <b>Конкурс №{g['id']}</b> · победител{'ь' if n == 1 else 'ей'}: <b>{n}</b>\n"
            f"⏰ Итоги: <b>{fmt_time(g['ends_at'], tz)}</b>\n"
            "<i>Нажмите «Участвовать» и пройдите проверку от ботов.</i>")


async def publish(bot, db: Database, g: dict) -> bool:
    """Отправить объявление в чат. Только один раз (статус scheduled → active)."""
    if not await db.gw_claim(g["id"], "scheduled", "publishing"):
        return False
    tz = await _tz__handlers_giveaway(db, g["chat_id"])
    kb = _join_kb((await bot.me()).username, g["id"], 0)
    try:
        if g["photo"]:
            m = await bot.send_photo(g["chat_id"], g["photo"], caption=announcement(g, tz), reply_markup=kb)
        else:
            m = await bot.send_message(g["chat_id"], announcement(g, tz), reply_markup=kb)
    except Exception as e:
        logging.warning("giveaway %s: publish failed: %s", g["id"], e)
        await db.gw_update(g["id"], status="failed")
        await _notify__handlers_giveaway(bot, g["creator"], f"⚠️ Конкурс №{g['id']} не удалось опубликовать: {html.escape(str(e))[:200]}\n"
                                         "Проверьте, что бот есть в чате и может писать.")
        return False
    await db.gw_update(g["id"], status="active", message_id=m.message_id, shown_count=0)
    return True


async def _pick(bot, db: Database, chat_id: int, candidates: list[int], n: int, exclude: set[int]) -> list[int]:
    """Первые n из случайного порядка, кто ещё в чате (вышедших пропускаем и убираем из списка участников чата)."""
    out = []
    for uid in shuffled(candidates):
        if uid in exclude:
            continue
        if await check(bot, db, chat_id, uid) is False:
            continue
        out.append(uid)
        if len(out) >= n:
            break
    return out


async def _names__handlers_giveaway(db: Database, ids: list[int]) -> str:
    return ", ".join([str(ping(u, (await db.user_name(u)) or f"id{u}")) for u in ids])


async def finish(bot, db: Database, g: dict) -> bool:
    if not await db.gw_claim(g["id"], "active", "finishing"):
        return False
    entries = await db.gw_entries(g["id"])
    winners = await _pick(bot, db, g["chat_id"], entries, g["winners"], set())
    await db.gw_update(g["id"], status="finished", result=json.dumps(winners))
    if winners:
        text = (f"🎉 <b>Итоги конкурса №{g['id']}</b>\nУчастников: {len(entries)}\n"
                f"{'Победитель' if len(winners) == 1 else 'Победители'}: {await _names__handlers_giveaway(db, winners)}\nПоздравляем! 🥳")
    else:
        text = f"🎁 Конкурс №{g['id']} завершён: участников не было — победителя нет."
    try:
        await bot.edit_message_reply_markup(chat_id=g["chat_id"], message_id=g["message_id"], reply_markup=None)
    except Exception:
        pass
    try:
        await bot.send_message(g["chat_id"], text, reply_to_message_id=g["message_id"], allow_sending_without_reply=True)
    except Exception as e:
        logging.warning("giveaway %s: results not sent: %s", g["id"], e)
    await _notify__handlers_giveaway(bot, g["creator"], text)
    await db.log_action(g["chat_id"], (await bot.me()).id, winners[0] if winners else None, "конкурс",
                        f"№{g['id']}: участников {len(entries)}, победителей {len(winners)}", int(time.time()))
    return True


async def _notify__handlers_giveaway(bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text)
    except Exception:
        pass


async def _refresh_count(bot, db: Database, g: dict, username: str) -> None:
    n = await db.gw_count(g["id"])
    if n == g["shown_count"] or time.time() - _count_edited.get(g["id"], 0) < COUNT_EDIT_EVERY:
        return
    _count_edited[g["id"]] = time.time()
    try:
        await bot.edit_message_reply_markup(chat_id=g["chat_id"], message_id=g["message_id"],
                                            reply_markup=_join_kb(username, g["id"], n))
        await db.gw_update(g["id"], shown_count=n)
    except Exception:
        pass


async def tick(bot, db: Database, now: int | None = None) -> None:
    now = int(time.time()) if now is None else now
    for g in await db.gw_due("scheduled", "publish_at", now):
        await publish(bot, db, g)
    for g in await db.gw_due("active", "ends_at", now):
        await finish(bot, db, g)
    active = await db.gw_list(None, ("active",))
    if active:
        username = (await bot.me()).username
        for g in active:
            await _refresh_count(bot, db, g, username)


async def giveaway_watchdog(bot, db: Database) -> None:
    while True:
        await asyncio.sleep(WATCH_EVERY)
        try:
            await tick(bot, db)
        except Exception:
            logging.exception("giveaway watchdog")


# ---------- группа ----------

@router__handlers_giveaway.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: _parse_group(t) is not None))
async def group_cmd__handlers_giveaway(message: Message, bot, db: Database, webapp_url: str = "") -> None:
    if message.from_user is None:
        return
    kind, gid = _parse_group(message.text)
    chat, me = message.chat.id, message.from_user.id
    tz = await _tz__handlers_giveaway(db, chat)
    if kind == "list":
        rows = await db.gw_list(chat, ("scheduled", "active"))
        if not rows:
            await message.reply("🎁 Сейчас конкурсов нет.")
            return
        lines = []
        for g in rows:
            when = (f"публикация {fmt_time(g['publish_at'], tz)}" if g["status"] == "scheduled"
                    else f"участников {await db.gw_count(g['id'])}")
            lines.append(f"№{g['id']} — {STATUS_RU[g['status']]}, {when}, итоги {fmt_time(g['ends_at'], tz)}")
        await message.reply("🎁 <b>Конкурсы</b>\n" + "\n".join(lines))
        return
    if not await _can_manage(bot, db, chat, me):
        if kind == "new":
            await tell(message, f"⚠️ Создавать конкурсы может владелец чата (ранг {need_rank(await db.get_access(chat), ACCESS_KEY__handlers_giveaway)}+).")
        return
    if kind == "new":
        if not webapp_url:
            await tell(message, "⚠️ Для конкурсов нужен WEBAPP_URL (проверка от ботов идёт в Mini App).")
            return
        username = (await bot.me()).username
        await message.reply("🎁 Создадим конкурс в личке с ботом — там можно добавить фото и выбрать время.",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                                B(text="✍️ Создать конкурс", url=f"https://t.me/{username}?start=gw_{chat}")]]))
        return
    g = await db.gw_get(gid)
    if g is None or g["chat_id"] != chat:
        await tell(message, "❌ Нет такого конкурса в этом чате.")
        return
    if kind == "cancel":
        if g["status"] not in ("scheduled", "active") or not await db.gw_claim(g["id"], g["status"], "cancelled"):
            await tell(message, "⚠️ Этот конкурс уже не идёт.")
            return
        if g["message_id"]:
            try:
                await bot.edit_message_reply_markup(chat_id=chat, message_id=g["message_id"], reply_markup=None)
            except Exception:
                pass
        await db.log_action(chat, me, None, "конкурс", f"№{gid} отменён", int(time.time()))
        await message.reply(f"🚫 Конкурс №{gid} отменён.")
        return
    # reroll
    if g["status"] != "finished":
        await tell(message, "⚠️ Перевыбрать можно только после итогов.")
        return
    old = json.loads(g["result"] or "[]")
    new = await _pick(bot, db, chat, await db.gw_entries(gid), 1, set(old))
    if not new:
        await tell(message, "❌ Больше выбрать некого: все участники уже побеждали или вышли из чата.")
        return
    await db.gw_update(gid, result=json.dumps(old + new))
    await db.log_action(chat, me, new[0], "конкурс", f"№{gid}: перевыбор", int(time.time()))
    await message.reply(f"🔁 Конкурс №{gid}, новый победитель: {await _names__handlers_giveaway(db, new)} 🎉")


# ---------- участие (личка → Mini App) ----------

@router__handlers_giveaway.message(F.chat.type == "private", F.text.func(lambda t: bool(t) and _START_JOIN.match(t.strip()) is not None))
async def start_join(message: Message, db: Database, webapp_url: str = "") -> None:
    gid = int(_START_JOIN.match(message.text.strip()).group(1))
    g = await db.gw_get(gid)
    if g is None or g["status"] != "active" or g["ends_at"] <= time.time():
        await tell(message, "⚠️ Этот конкурс уже завершён или не найден.")
        return
    if await db.gw_joined(gid, message.from_user.id):
        await message.answer(f"✅ Вы уже участвуете в конкурсе №{gid}. Удачи!")
        return
    if not webapp_url:
        await tell(message, "⚠️ Mini App не настроен — обратитесь к администратору бота.")
        return
    await message.answer(f"🎁 Конкурс №{gid}. Чтобы участвовать, пройдите короткую проверку от ботов:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                             B(text="🎟 Участвовать", web_app=WebAppInfo(url=f"{webapp_url}/giveaway?id={gid}"))]]))


# ---------- мастер создания (личка) ----------

def _kb__handlers_giveaway(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text=t, callback_data=d) for t, d in row] for row in rows])


CANCEL_ROW = [("✖️ Отмена", "gw:cancel")]
PUBLISH_KB = _kb__handlers_giveaway([[("Сейчас", "gw:p:0"), ("Через 1 ч", "gw:p:3600")], CANCEL_ROW])
END_KB = _kb__handlers_giveaway([[("1 час", "gw:e:3600"), ("1 день", "gw:e:86400")], [("3 дня", "gw:e:259200"), ("7 дней", "gw:e:604800")],
              CANCEL_ROW])
WINNERS_KB = _kb__handlers_giveaway([[(str(n), f"gw:w:{n}") for n in (1, 2, 3, 5)], CANCEL_ROW])
CONFIRM_KB = _kb__handlers_giveaway([[("✅ Опубликовать", "gw:ok")], CANCEL_ROW])
ASK_TEXT = ("✍️ Пришлите текст конкурса: что разыгрывается и условия. Можно фото с подписью — фото по желанию.\n"
            "Отменить — «отмена».")


def _ask_publish(tz) -> str:
    return ("⏰ Когда опубликовать в чате? Нажмите кнопку или напишите: <code>20:00</code>, <code>завтра 18:30</code>, "
            f"<code>25.12 12:00</code>, <code>через 2 часа</code>. Время чата — {tz}.")


def _ask_end(g: dict, tz) -> str:
    return (f"🏁 Когда подвести итоги? Публикация: {fmt_time(g['publish_at'], tz)}.\nКнопки и «через …» — от момента "
            "публикации; можно точное время: <code>завтра 21:00</code>, <code>31.12 23:00</code>.")


async def _draft_filter(message: Message, db: Database) -> bool:
    if message.chat.type != "private" or message.from_user is None:
        return False
    if (message.text or "").startswith("/start"):
        return False
    return await db.gw_draft(message.from_user.id) is not None


@router__handlers_giveaway.message(F.chat.type == "private", F.text.func(lambda t: bool(t) and _START_NEW.match(t.strip()) is not None))
async def start_new(message: Message, bot, db: Database, webapp_url: str = "") -> None:
    chat_id = int(_START_NEW.match(message.text.strip()).group(1))
    if await db.get_chat(chat_id) is None or not await _can_manage(bot, db, chat_id, message.from_user.id):
        await tell(message, "⚠️ Создавать конкурсы в этом чате вы не можете.")
        return
    if not webapp_url:
        await tell(message, "⚠️ Для конкурсов нужен WEBAPP_URL.")
        return
    await db.gw_new_draft(chat_id, message.from_user.id, int(time.time()))
    title = (await db.get_chat(chat_id)).get("title") or str(chat_id)
    await message.answer(f"🎁 Новый конкурс для «{html.escape(title)}».\n\n" + ASK_TEXT, reply_markup=_kb__handlers_giveaway([CANCEL_ROW]))


async def _preview(message: Message, db: Database, g: dict) -> None:
    tz = await _tz__handlers_giveaway(db, g["chat_id"])
    text = announcement(g, tz)
    if g["photo"]:
        await message.answer_photo(g["photo"], caption=text)
    else:
        await message.answer(text)
    await message.answer(f"👆 Так будет выглядеть объявление. Публикация: <b>{fmt_time(g['publish_at'], tz)}</b>, "
                         f"итоги: <b>{fmt_time(g['ends_at'], tz)}</b>.", reply_markup=CONFIRM_KB)


@router__handlers_giveaway.message(_draft_filter)
async def wizard_message(message: Message, bot, db: Database) -> None:
    uid = message.from_user.id
    g = await db.gw_draft(uid)
    if (message.text or "").strip().lower() in ("отмена", "/cancel"):
        await db.gw_delete_draft(uid)
        await tell(message, "⚠️ Создание конкурса отменено.")
        return
    tz = await _tz__handlers_giveaway(db, g["chat_id"])
    now = int(time.time())
    step = g["step"]
    if step == "text":
        photo = message.photo[-1].file_id if message.photo else None
        body = (message.html_text or "").strip()
        if not body:
            await tell(message, "⚠️ Нужен текст: что разыгрывается и условия (фото — по желанию, с подписью).")
            return
        limit = CAPTION_MAX__giveaway if photo else TEXT_MAX
        if len(body) > limit:
            await tell(message, f"❌ Слишком длинно: до {limit} символов{' с фото' if photo else ''}.")
            return
        await db.gw_update(g["id"], text=body, photo=photo, step="publish")
        await message.answer(_ask_publish(tz), reply_markup=PUBLISH_KB)
    elif step in ("publish", "end"):
        if not message.text:
            await tell(message, "⚠️ Напишите время текстом или нажмите кнопку.")
            return
        base = g["publish_at"] if step == "end" else None
        ts = parse_when(message.text, now, tz, base=base)
        if ts is None:
            await message.answer("❌ Не понял время. Примеры: <code>20:00</code>, <code>завтра 18:30</code>, "
                                 "<code>25.12 12:00</code>, <code>через 2 часа</code>.")
            return
        await _set_time(message, db, g, step, ts, now, tz)
    else:
        await tell(message, "⚠️ Выберите вариант кнопкой выше или напишите «отмена».")


async def _set_time(message: Message, db: Database, g: dict, step: str, ts: int, now: int, tz) -> None:
    if step == "publish":
        err = check_publish(ts, now)
        if err:
            await message.answer(err)
            return
        ts = max(ts, now)
        await db.gw_update(g["id"], publish_at=ts, step="end")
        g["publish_at"] = ts
        await message.answer(_ask_end(g, tz), reply_markup=END_KB)
    else:
        err = check_end(ts, g["publish_at"])
        if err:
            await message.answer(err)
            return
        await db.gw_update(g["id"], ends_at=ts, step="winners")
        await message.answer("🏆 Сколько победителей?", reply_markup=WINNERS_KB)


@router__handlers_giveaway.callback_query(F.data.startswith("gw:"))
async def wizard_cb(cb: CallbackQuery, bot, db: Database) -> None:
    parts = cb.data.split(":")
    g = await db.gw_draft(cb.from_user.id)
    if g is None or cb.message is None:
        await cb.answer("Черновик не найден — начните заново: «+конкурс» в чате.", show_alert=True)
        return
    now = int(time.time())
    tz = await _tz__handlers_giveaway(db, g["chat_id"])
    op = parts[1]
    if op == "cancel":
        await db.gw_delete_draft(cb.from_user.id)
        await cb.message.answer("⚠️ Создание конкурса отменено.")
    elif op in ("p", "e") and len(parts) == 3 and parts[2].isdigit():
        want = "publish" if op == "p" else "end"
        if g["step"] != want:
            await cb.answer("Этот шаг уже пройден.")
            return
        base = now if op == "p" else g["publish_at"]
        await _set_time(cb.message, db, g, want, base + int(parts[2]), now, tz)
    elif op == "w" and len(parts) == 3 and parts[2].isdigit() and g["step"] == "winners":
        n = min(max(int(parts[2]), 1), MAX_WINNERS)
        await db.gw_update(g["id"], winners=n, step="confirm")
        g.update(winners=n)
        await _preview(cb.message, db, g)
    elif op == "ok" and g["step"] == "confirm":
        if not await _can_manage(bot, db, g["chat_id"], cb.from_user.id):     # права могли отобрать, пока шёл мастер
            await cb.answer("У вас больше нет прав на конкурсы в этом чате.", show_alert=True)
            return
        if not await db.gw_claim(g["id"], "draft", "scheduled"):
            await cb.answer()
            return
        g["status"] = "scheduled"
        if g["publish_at"] <= now:
            ok = await publish(bot, db, g)
            await cb.message.answer(f"✅ Конкурс №{g['id']} опубликован!" if ok else "⚠️ Опубликовать не получилось.")
        else:
            await cb.message.answer(f"✅ Конкурс №{g['id']} запланирован на {fmt_time(g['publish_at'], tz)}. "
                                    f"Отменить: <code>-конкурс {g['id']}</code> в чате.")
        await db.log_action(g["chat_id"], cb.from_user.id, None, "конкурс", f"№{g['id']} создан", now)
    else:
        await cb.answer("Этот шаг уже пройден.")
        return
    await cb.answer()



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/mafia.py
# Мафия: ведущий-бот для классической игры в группе (набор → роли в личке → ночь → день → голосование → итог).
#
# Состояние игры живёт в памяти (игра идёт минуты; после перезапуска бота идущая игра прекращается). Всё, что решает ход игры
# (роли, ночь, подсчёт голосов, победа), — обычные синхронные методы `Game`: их можно проверять без Telegram. Связь с Telegram — функции
# `run_game` и вспомогательные ниже; команды и кнопки подключены в bot/handlers/mafia.py.
#
# Роли: Мирный житель, Мафия, Дон (глава мафии), Доктор, Комиссар. Минимум 4 игрока: Дон, Доктор и двое мирных.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
MIN_PLAYERS = 4
MAX_PLAYERS = 25
REG_SECONDS = 120          # сколько идёт набор, если ведущий не начал раньше
NIGHT_SECONDS = 60
DAY_SECONDS = 90           # обсуждение
VOTE_SECONDS = 45
CONFIRM_SECONDS = 25       # «Вы точно хотите линчевать?»
LAST_WORDS_MAX = 200
COUNTDOWN_STEP = 20
ASSETS__mafia = Path(__file__).with_name("assets") / "mafia"

ROLES = {
    "civ": ("Мирный житель", "👨🏼"),
    "mafia": ("Мафия", "🤵🏽"),
    "don": ("Дон", "🤵🏻"),
    "doc": ("Доктор", "👨🏼‍⚕️"),
    "com": ("Комиссар", "🕵🏼"),
}
MAFIA = {"mafia", "don"}
ROLE_ORDER = ("don", "mafia", "doc", "com", "civ")
ROLE_TEXT = {
    "civ": "Ты - {e} Мирный житель.\nТвоя задача вычислить мафию и на городском собрании линчевать засранцев",
    "don": "Ты - {e} Дон (глава мафии)!\nТебе решать кто не проснётся этой ночью...",
    "mafia": "Ты - {e} Мафия!\nТвоя задача - вместе с Доном избавиться от всех мирных жителей. По ночам вы голосуете за жертву.",
    "doc": "Ты - {e} Доктор!\nТебе решать кого спасти этой ночью...",
    "com": "Ты - {e} Комиссар!\nТебе решать кого проверить этой ночью: ты узнаешь, мафия это или нет.",
}


def role_name(role: str) -> str:
    return ROLES[role][0]


def role_plan(n: int) -> list[str]:
    """Набор ролей на n игроков: мафии n//4 (первая — Дон), Доктор, с 5 игроков — Комиссар, остальные — мирные."""
    if n < MIN_PLAYERS:
        raise ValueError("мало игроков")
    roles = ["don"] + ["mafia"] * (max(1, n // 4) - 1) + ["doc"]
    if n >= 5:
        roles.append("com")
    return roles + ["civ"] * (n - len(roles))


@dataclass
class Player:
    uid: int
    name: str
    num: int
    role: str = "civ"
    alive: bool = True
    can_speak: bool = False        # убит и ещё может прислать предсмертное сообщение


@dataclass
class Game:
    chat_id: int
    title: str
    host: int
    players: dict[int, Player] = field(default_factory=dict)
    phase: str = "reg"             # reg | night | day | vote | confirm | done
    day: int = 0
    created: float = field(default_factory=time.time)
    started: float = 0.0
    cancelled: bool = False
    # ночь
    mafia_votes: dict[int, int] = field(default_factory=dict)
    doc_pick: int | None = None
    com_pick: int | None = None
    last_heal: int | None = None
    # день
    votes: dict[int, int] = field(default_factory=dict)
    accused: int | None = None
    confirm: dict[int, bool] = field(default_factory=dict)
    # служебное
    reg_msg: int | None = None
    start_event: asyncio.Event = field(default_factory=asyncio.Event)
    step_event: asyncio.Event = field(default_factory=asyncio.Event)       # все нужные игроки сходили — фазу можно закончить
    task: asyncio.Task | None = None
    night_result: dict = field(default_factory=dict)

    # ----- игроки -----
    def mention(self, uid: int) -> str:
        return str(mention__targets(uid, self.players[uid].name))

    def alive(self) -> list[Player]:
        return [p for p in self.players.values() if p.alive]

    def alive_ids(self, role: set[str] | None = None) -> list[int]:
        return [p.uid for p in self.alive() if role is None or p.role in role]

    def join(self, uid: int, name: str) -> str | None:
        """None — присоединился; иначе причина отказа."""
        if self.phase != "reg":
            return "Набор в игру уже закончен."
        if uid in self.players:
            return "Ты уже в игре."
        if len(self.players) >= MAX_PLAYERS:
            return f"В игре уже максимум игроков ({MAX_PLAYERS})."
        self.players[uid] = Player(uid, name or f"id{uid}", len(self.players) + 1)
        return None

    def leave(self, uid: int) -> bool:
        if self.phase != "reg" or uid not in self.players:
            return False
        del self.players[uid]
        for i, p in enumerate(self.players.values(), 1):
            p.num = i
        return True

    def assign(self, rnd: random.Random | None = None) -> None:
        rnd = rnd or random
        roles = role_plan(len(self.players))
        rnd.shuffle(roles)
        for p, r in zip(self.players.values(), roles):
            p.role = r
        self.started = time.time()

    # ----- ночь -----
    def begin_night(self) -> None:
        self.phase = "night"
        self.mafia_votes.clear()
        self.doc_pick = self.com_pick = None
        self.step_event.clear()

    def night_actors(self) -> list[int]:
        return [p.uid for p in self.alive() if p.role in MAFIA or p.role in ("doc", "com")]

    def night_options(self, uid: int) -> list[int]:
        """Кого можно выбрать этой ночью (пусто — роль без ночного действия)."""
        p = self.players.get(uid)
        if p is None or not p.alive:
            return []
        if p.role in MAFIA:
            return [x for x in self.alive_ids() if self.players[x].role not in MAFIA]
        if p.role == "doc":
            return [x for x in self.alive_ids() if x != self.last_heal]
        if p.role == "com":
            return [x for x in self.alive_ids() if x != uid]
        return []

    def night_pick(self, uid: int, target: int) -> str | None:
        """None — выбор принят; иначе причина отказа."""
        if self.phase != "night":
            return "Сейчас не ночь."
        p = self.players.get(uid)
        if p is None or not p.alive:
            return "Ты не в игре."
        if target not in self.night_options(uid):
            return "Этого игрока выбрать нельзя."
        if p.role in MAFIA:
            if uid in self.mafia_votes:
                return "Ты уже сделал выбор."
            self.mafia_votes[uid] = target
        elif p.role == "doc":
            if self.doc_pick is not None:
                return "Ты уже сделал выбор."
            self.doc_pick = target
        elif p.role == "com":
            if self.com_pick is not None:
                return "Ты уже сделал выбор."
            self.com_pick = target
        else:
            return "Ночью тебе делать нечего. Спи."
        self._check_night_done()
        return None

    def _check_night_done(self) -> None:
        mafia_done = all(u in self.mafia_votes for u in self.alive_ids(MAFIA))
        doc_done = all(self.doc_pick is not None for _ in self.alive_ids({"doc"}))
        com_done = all(self.com_pick is not None for _ in self.alive_ids({"com"}))
        if mafia_done and doc_done and com_done:
            self.step_event.set()

    def mafia_target(self, rnd: random.Random | None = None) -> int | None:
        """Жертва мафии: больше всего голосов; при равенстве решает Дон, а если его нет — случай."""
        if not self.mafia_votes:
            return None
        count: dict[int, int] = {}
        for t in self.mafia_votes.values():
            count[t] = count.get(t, 0) + 1
        top = max(count.values())
        tied = [t for t, n in count.items() if n == top]
        if len(tied) == 1:
            return tied[0]
        for uid, t in self.mafia_votes.items():
            if self.players[uid].role == "don" and t in tied:
                return t
        return (rnd or random).choice(tied)

    def resolve_night(self, rnd: random.Random | None = None) -> dict:
        """Итог ночи: {"victim": uid|None (выбранная мафией), "saved": bool, "killed": uid|None, "check": (uid, is_mafia)|None}."""
        victim = self.mafia_target(rnd)
        saved = victim is not None and victim == self.doc_pick
        killed = None if saved else victim
        check = None
        if self.com_pick is not None:
            check = (self.com_pick, self.players[self.com_pick].role in MAFIA)
        self.last_heal = self.doc_pick
        if killed is not None:
            self.kill(killed)
        self.day += 1
        return {"victim": victim, "saved": saved, "killed": killed, "check": check}

    def kill(self, uid: int) -> None:
        p = self.players[uid]
        p.alive = False
        p.can_speak = True

    # ----- день -----
    def begin_vote(self) -> None:
        self.phase = "vote"
        self.votes.clear()
        self.accused = None
        self.step_event.clear()

    def vote_options(self, uid: int) -> list[int]:
        return [x for x in self.alive_ids() if x != uid]

    def cast_vote(self, voter: int, target: int) -> str | None:
        if self.phase != "vote":
            return "Сейчас не голосование."
        p = self.players.get(voter)
        if p is None or not p.alive:
            return "Ты не в игре."
        if target not in self.vote_options(voter):
            return "Этого игрока выбрать нельзя."
        if voter in self.votes:
            return "Ты уже проголосовал."
        self.votes[voter] = target
        if all(u in self.votes for u in self.alive_ids()):
            self.step_event.set()
        return None

    def tally(self) -> int | None:
        """Кого линчевать: больше всего голосов у одного игрока; ничья или никто не голосовал — None."""
        if not self.votes:
            return None
        count: dict[int, int] = {}
        for t in self.votes.values():
            count[t] = count.get(t, 0) + 1
        top = max(count.values())
        tied = [t for t, n in count.items() if n == top]
        return tied[0] if len(tied) == 1 else None

    def begin_confirm(self, accused: int) -> None:
        self.phase = "confirm"
        self.accused = accused
        self.confirm.clear()
        self.step_event.clear()

    def confirm_voters(self) -> list[int]:
        return [u for u in self.alive_ids() if u != self.accused]

    def cast_confirm(self, voter: int, yes: bool) -> str | None:
        if self.phase != "confirm":
            return "Голосование уже закончено."
        if voter not in self.confirm_voters():
            return "Голосовать могут только живые игроки (кроме обвиняемого)."
        if voter in self.confirm:
            return "Ты уже проголосовал."
        self.confirm[voter] = yes
        if all(u in self.confirm for u in self.confirm_voters()):
            self.step_event.set()
        return None

    def confirm_result(self) -> tuple[int, int, bool]:
        yes = sum(1 for v in self.confirm.values() if v)
        no = len(self.confirm) - yes
        return yes, no, yes > no

    # ----- победа -----
    def winner(self) -> str | None:
        mafia = len(self.alive_ids(MAFIA))
        town = len(self.alive()) - mafia
        if mafia == 0:
            return "town"
        if mafia >= town:
            return "mafia"
        return None


# ---------- тексты ----------
def alive_list(g: Game) -> str:
    return "Живые игроки:\n" + "\n".join(f"{p.num}. {g.mention(p.uid)}" for p in g.alive())


def role_summary(g: Game) -> str:
    """«👨🏼 Мирный житель - 2, 🤵🏻 Дон»: кто остался, без имён."""
    count: dict[str, int] = {}
    for p in g.alive():
        count[p.role] = count.get(p.role, 0) + 1
    parts = [f"{ROLES[r][1]} {ROLES[r][0]}" + (f" - {count[r]}" if count[r] > 1 else "") for r in ROLE_ORDER if r in count]
    return ", ".join(parts)


def left_text(seconds: float) -> str:
    s = max(int(seconds + 0.5), 0)
    return f"{round(s / 60)} мин." if s >= 60 else f"{s} сек."


def duration_text(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60} мин. {s % 60} сек." if s >= 60 else f"{s} сек."


def final_text__mafia(g: Game, winner: str) -> str:
    win_side = (lambda p: p.role in MAFIA) if winner == "mafia" else (lambda p: p.role not in MAFIA)
    winners = [p for p in g.players.values() if win_side(p)]
    others = [p for p in g.players.values() if not win_side(p)]

    def line(p: Player) -> str:
        return f"    {g.mention(p.uid)} - {ROLES[p.role][1]} {ROLES[p.role][0]}"
    text = f"Игра окончена!\nПобедили: {'Мафия' if winner == 'mafia' else 'Мирные жители'}\n\nПобедители:\n" + "\n".join(map(line, winners))
    if others:
        text += "\n\nОстальные участники:\n" + "\n".join(map(line, others))
    return text + f"\n\nИгра длилась: {duration_text(time.time() - g.started)}."


# ---------- Telegram ----------
_file_ids__mafia: dict[str, str] = {}
_games: dict[int, Game] = {}               # chat_id -> игра
_in_game: dict[int, int] = {}              # user_id -> chat_id (игрок записан в идущую игру)
_bg__mafia: set[asyncio.Task] = set()


def get_game(chat_id: int) -> Game | None:
    return _games.get(chat_id)


ACTIVE_PHASES = {"night", "day", "vote", "confirm"}


def must_delete(chat_id: int, uid: int | None) -> bool:
    """Идёт партия, а автор сообщения не играет или уже убит — его сообщения в чате удаляются (чтобы не подсказывали и не мешали)."""
    g = _games.get(chat_id)
    if g is None or g.phase not in ACTIVE_PHASES:
        return False
    p = g.players.get(uid) if uid is not None else None
    return p is None or not p.alive


def game_of_user(uid: int) -> Game | None:
    chat = _in_game.get(uid)
    return _games.get(chat) if chat is not None else None


def link_kb(username: str, text: str, payload: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text=text, url=f"https://t.me/{username}?start={payload}")]])


async def _say(bot, chat_id: int, text: str, **kw):
    try:
        return await bot.send_message(chat_id, text, disable_web_page_preview=True, **kw)
    except Exception as e:
        logging.info("мафия: сообщение не отправилось (%s)", e)
        return None


async def _gif(bot, chat_id: int, name: str, caption: str, reply_markup=None):
    """Гифка дня или ночи с подписью; не вышла — просто текст."""
    path = ASSETS__mafia / f"{name}.mp4"
    try:
        msg = await bot.send_animation(chat_id, _file_ids__mafia.get(name) or FSInputFile(path), caption=caption, reply_markup=reply_markup)
        if name not in _file_ids__mafia and getattr(msg, "animation", None):
            _file_ids__mafia[name] = msg.animation.file_id
        return msg
    except Exception as e:
        _file_ids__mafia.pop(name, None)
        logging.info("мафия: гифка %s не отправилась (%s)", name, e)
        return await _say(bot, chat_id, caption, reply_markup=reply_markup)


async def _edit__mafia(bot, chat_id: int, message_id: int | None, text: str, reply_markup=None) -> None:
    if message_id is None:
        return
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup,
                                    disable_web_page_preview=True)
    except Exception as e:
        if "not modified" not in str(e).lower():
            logging.info("мафия: правка не удалась (%s)", e)


def pick_kb(prefix: str, chat_id: int, g: Game, options: list[int]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text=g.players[u].name[:40], callback_data=f"mf:{prefix}:{chat_id}:{u}")] for u in options])


def confirm_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text="👍", callback_data=f"mf:c:{chat_id}:1"), B(text="👎", callback_data=f"mf:c:{chat_id}:0")]])


async def _wait(g: Game, seconds: float, on_tick=None) -> None:
    """Ждёт конец фазы: время вышло, все сходили (step_event) или игру остановили. on_tick(осталось_сек) — для обратного отсчёта."""
    end = time.monotonic() + seconds
    while not g.cancelled and not g.step_event.is_set():
        left = end - time.monotonic()
        if left <= 0:
            return
        if on_tick is not None:
            await on_tick(left)
        try:
            await asyncio.wait_for(g.step_event.wait(), timeout=min(left, COUNTDOWN_STEP))
        except asyncio.TimeoutError:
            pass


def _forget(g: Game) -> None:
    for uid in g.players:
        if _in_game.get(uid) == g.chat_id:
            _in_game.pop(uid, None)
    if _games.get(g.chat_id) is g:
        _games.pop(g.chat_id, None)


async def open_registration(bot, chat_id: int, title: str, host: int, host_name: str, username: str):
    """Создаёт игру и сообщение с набором. Возвращает (игра, None) или (None, причина)."""
    if chat_id in _games:
        return None, "В этом чате уже идёт игра."
    if host in _in_game:
        return None, "Ты уже участвуешь в другой игре."
    g = Game(chat_id, title, host)
    _games[chat_id] = g
    err = g.join(host, host_name)
    if err is None:
        _in_game[host] = chat_id
    msg = await _say(bot, chat_id, reg_text(g), reply_markup=link_kb(username, "🤵🏻 Присоединиться", f"mafia_{chat_id}"))
    g.reg_msg = getattr(msg, "message_id", None)
    g.task = asyncio.create_task(run_game(bot, g, username))
    _bg__mafia.add(g.task)
    g.task.add_done_callback(_bg__mafia.discard)
    return g, None


def reg_text(g: Game) -> str:
    names = ", ".join(g.mention(u) for u in g.players) or "пока никого"
    return (f"Ведётся набор в игру\n\nЗарегистрировались: {names}\n\nИтого {len(g.players)} чел.\n"
            f"<i>Начать: /startgame (нужно минимум {MIN_PLAYERS}). Присоединиться — кнопкой ниже.</i>")


async def join(bot, g: Game, uid: int, name: str, username: str) -> str | None:
    """Вызывается из личного /start mafia_<chat>. None — присоединился."""
    if uid in _in_game and _in_game[uid] != g.chat_id:
        return "Ты уже участвуешь в другой игре."
    err = g.join(uid, name)
    if err is None:
        _in_game[uid] = g.chat_id
        await _edit__mafia(bot, g.chat_id, g.reg_msg, reg_text(g),
                    link_kb(username, "🤵🏻 Присоединиться", f"mafia_{g.chat_id}"))
    return err


def request_start(g: Game) -> str | None:
    """Ведущий просит начать досрочно. None — игра начнётся; иначе причина."""
    if g.phase != "reg":
        return "Игра уже идёт."
    if len(g.players) < MIN_PLAYERS:
        return f"Нужно минимум {MIN_PLAYERS} игрока, сейчас {len(g.players)}."
    g.start_event.set()
    return None


def stop(g: Game) -> None:
    g.cancelled = True
    g.start_event.set()
    g.step_event.set()


async def run_game(bot, g: Game, username: str) -> None:
    try:
        await _run__mafia(bot, g, username)
    except asyncio.CancelledError:
        raise
    except Exception:
        logging.exception("мафия: игра в %s упала", g.chat_id)
        await _say(bot, g.chat_id, "⚠️ В игре что-то сломалось, игра остановлена.")
    finally:
        g.phase = "done"
        _forget(g)


async def _run__mafia(bot, g: Game, username: str) -> None:
    # ----- набор -----
    try:
        await asyncio.wait_for(g.start_event.wait(), timeout=REG_SECONDS)
    except asyncio.TimeoutError:
        pass
    if g.cancelled:
        await _edit__mafia(bot, g.chat_id, g.reg_msg, "Набор в игру отменён.")
        return
    if len(g.players) < MIN_PLAYERS:
        await _edit__mafia(bot, g.chat_id, g.reg_msg, f"Набор закончен: нужно минимум {MIN_PLAYERS} игрока, а пришло {len(g.players)}. Игра не состоялась.")
        return
    g.assign()
    g.phase = "night"
    await _edit__mafia(bot, g.chat_id, g.reg_msg, reg_text(g).split("\n<i>")[0] + "\n\nНабор закончен.")
    await _say(bot, g.chat_id, "Игра начинается!\n\nВ течение нескольких секунд бот пришлёт вам личное сообщение с ролью и её описанием.",
               reply_markup=link_kb(username, "Посмотреть роль", "mafia_role"))
    await _warn_if_cannot_delete(bot, g)
    blocked = await _send_roles(bot, g)
    if blocked:
        names = ", ".join(g.mention(u) for u in blocked)
        await _say(bot, g.chat_id, f"⚠️ Не могу написать в личку: {names}. Нажмите «Присоединиться» → Start у бота и начните заново.")
        g.cancelled = True
        return

    # ----- игровой цикл -----
    while not g.cancelled:
        await _night(bot, g, username)
        if g.cancelled:
            break
        await _day(bot, g, username)                         # утром объявляет погибшего и проверяет победу
        if g.cancelled or await _finish_if_won(bot, g):
            return
    if g.cancelled:
        await _say(bot, g.chat_id, "Игра остановлена.")


async def _warn_if_cannot_delete(bot, g: Game) -> None:
    """Сообщения не-игроков и убитых бот удаляет — для этого нужно право админа «Удаление сообщений»."""
    try:
        m = await bot.get_chat_member(g.chat_id, (await bot.me()).id)
        ok = m.status == "creator" or (m.status == "administrator" and getattr(m, "can_delete_messages", False))
    except Exception:
        return
    if not ok:
        await _say(bot, g.chat_id, "⚠️ Дайте боту право админа «Удаление сообщений»: во время игры он удаляет сообщения тех, кто не играет или уже убит.")


async def _send_roles(bot, g: Game) -> list[int]:
    blocked = []
    mafia = [p for p in g.players.values() if p.role in MAFIA]
    for p in g.players.values():
        text = ROLE_TEXT[p.role].format(e=ROLES[p.role][1])
        if p.role in MAFIA and len(mafia) > 1:
            text += "\n\nТвоя команда: " + ", ".join(f"{html.escape(m.name)} ({ROLES[m.role][0]})" for m in mafia if m.uid != p.uid)
        if await _say(bot, p.uid, text) is None:
            blocked.append(p.uid)
    return blocked


async def _finish_if_won(bot, g: Game) -> bool:
    if g.phase == "done":
        return True
    w = g.winner()
    if w is None:
        return False
    g.phase = "done"
    await _say(bot, g.chat_id, final_text__mafia(g, w))
    return True


async def _night(bot, g: Game, username: str) -> None:
    g.begin_night()
    kb = link_kb(username, "Перейти к боту", "mafia_go")
    await _gif(bot, g.chat_id, "night", "🌃 Наступает ночь\nНа улицы города выходят лишь самые отважные и бесстрашные. Утром попробуем сосчитать их головы…", kb)
    timer = await _say(bot, g.chat_id, alive_list(g) + f"\n\nСпать осталось {left_text(NIGHT_SECONDS)}", reply_markup=kb)
    timer_id = getattr(timer, "message_id", None)

    # ночные приглашения в личку (параллельно: до 25 игроков)
    async def invite(p: Player) -> None:
        opts = g.night_options(p.uid)
        if not opts:
            return
        if p.role in MAFIA:
            await _say(bot, p.uid, "Мафия проводит голосование за следующую жертву:", reply_markup=pick_kb("n", g.chat_id, g, opts))
        elif p.role == "doc":
            note = f"\n\nВчера ты лечил {html.escape(g.players[g.last_heal].name)} — сегодня ему придётся продержаться без тебя." \
                if g.last_heal in g.players and g.players[g.last_heal].alive else ""
            await _say(bot, p.uid, "Кого будем лечить?" + note, reply_markup=pick_kb("n", g.chat_id, g, opts))
        else:
            await _say(bot, p.uid, "Кого проверим этой ночью?", reply_markup=pick_kb("n", g.chat_id, g, opts))
    await asyncio.gather(*(invite(p) for p in g.alive()))

    async def tick(left: float) -> None:
        await _edit__mafia(bot, g.chat_id, timer_id, alive_list(g) + f"\n\nСпать осталось {left_text(left)}", kb)
    await _wait(g, NIGHT_SECONDS, tick)
    await _edit__mafia(bot, g.chat_id, timer_id, alive_list(g) + "\n\nНочь закончилась.", kb)
    if g.cancelled:
        return

    had_mafia, had_doc, had_com = bool(g.mafia_votes), g.doc_pick is not None, g.com_pick is not None
    g.night_result = g.resolve_night()
    if had_mafia:
        await _say(bot, g.chat_id, "🤵🏻 Мафия выбрала жертву…")
    if had_doc:
        await _say(bot, g.chat_id, "👨🏼‍⚕️ Доктор вышел на ночное дежурство…")
    if had_com:
        await _say(bot, g.chat_id, "🕵🏼 Комиссар отправился на поиски мафии…")


async def _day(bot, g: Game, username: str) -> None:
    res = g.night_result
    g.phase = "day"
    await _gif(bot, g.chat_id, "day", f"🏙 День {g.day}\nСолнце всходит, подсушивая на тротуарах пролитую ночью кровь…")
    killed = res.get("killed")
    if killed is None:
        await _say(bot, g.chat_id, "🤷‍♂️ Удивительно, но этой ночью все выжили")
    else:
        p = g.players[killed]
        await _say(bot, g.chat_id, f"Сегодня был жестоко убит {ROLES[p.role][1]} {ROLES[p.role][0]} {g.mention(killed)}…")
        await _say(bot, killed, "Тебя убили :(\nТы можешь отправить сюда своё предсмертное сообщение")
    if await _finish_if_won(bot, g):
        return
    await _say(bot, g.chat_id, f"{alive_list(g)}\n\nКто-то из них:\n{role_summary(g)}\nВсего: {len(g.alive())} чел.\n\n"
                               "Сейчас самое время обсудить результаты ночи, разобраться в причинах и следствиях…")
    g.step_event.clear()
    await _wait(g, DAY_SECONDS)
    if g.cancelled:
        return

    # ----- голосование -----
    g.begin_vote()
    await _say(bot, g.chat_id, f"Пришло время определить и наказать виноватых.\nГолосование продлится {VOTE_SECONDS} секунд",
               reply_markup=link_kb(username, "Голосовать", "mafia_go"))
    await asyncio.gather(*(_say(bot, p.uid, "Пришло время искать виноватых!\nКого ты хочешь линчевать?",
                                reply_markup=pick_kb("v", g.chat_id, g, g.vote_options(p.uid))) for p in g.alive()))
    await _wait(g, VOTE_SECONDS)
    if g.cancelled:
        return
    target = g.tally()
    if target is None:
        await _say(bot, g.chat_id, "Голосование окончено\nМнения жителей разошлись…\nРазошлись и сами жители, так никого и не повесив…")
        return

    # ----- подтверждение -----
    g.begin_confirm(target)
    name = g.mention(target)
    msg = await _say(bot, g.chat_id, f"Вы точно хотите линчевать {name}?", reply_markup=confirm_kb(g.chat_id))
    await _wait(g, CONFIRM_SECONDS)
    await _edit__mafia(bot, g.chat_id, getattr(msg, "message_id", None), f"Вы точно хотите линчевать {name}?\n\nГолосование завершено")
    if g.cancelled:
        return
    yes, no, hang = g.confirm_result()
    if not hang:
        await _say(bot, g.chat_id, f"Результаты голосования:\n{yes}👍 | {no}👎\n\n{name} остаётся жить. Пока что…")
        g.accused = None
        return
    await _say(bot, g.chat_id, f"Результаты голосования:\n{yes}👍 | {no}👎\n\nВешаем {name}! :)")
    g.kill(target)
    p = g.players[target]
    await _say(bot, g.chat_id, f"{name} был {ROLES[p.role][1]} {ROLES[p.role][0]}")
    await _say(bot, target, "Тебя повесили :(\nТы можешь отправить сюда своё предсмертное сообщение")
    g.accused = None


# ---------- действия игроков (вызываются из кнопок) ----------
def night_action(g: Game, uid: int, target: int) -> tuple[str, list[tuple[int, str]]]:
    """(что ответить игроку, [(кому ещё, что написать)]). Текст ошибки начинается с «⚠️»."""
    err = g.night_pick(uid, target)
    if err:
        return "⚠️ " + err, []
    p = g.players[uid]
    name = html.escape(g.players[target].name)
    extra: list[tuple[int, str]] = []
    if p.role in MAFIA:
        extra = [(m, f"{html.escape(p.name)} ({ROLES[p.role][0]}) проголосовал за {name}") for m in g.alive_ids(MAFIA) if m != uid]
    if p.role == "com":
        is_m = g.players[target].role in MAFIA
        return f"Ты выбрал {name}\n\n" + (f"🔴 {name} — МАФИЯ!" if is_m else f"🟢 {name} — мирный житель."), []
    return f"Ты выбрал {name}", extra


def vote_action(g: Game, uid: int, target: int) -> tuple[str, str | None]:
    """(ответ игроку, объявление в группу или None)."""
    err = g.cast_vote(uid, target)
    if err:
        return "⚠️ " + err, None
    return f"Ты выбрал {html.escape(g.players[target].name)}", f"{g.mention(uid)} проголосовал за {g.mention(target)}"


def last_words(g: Game, uid: int, text: str) -> str | None:
    """Предсмертное сообщение: текст для группы или None (нельзя / нечего)."""
    p = g.players.get(uid)
    text = " ".join((text or "").split())[:LAST_WORDS_MAX]
    if p is None or p.alive or not p.can_speak or not text or g.phase == "done":
        return None
    p.can_speak = False
    return f"Кто-то из жителей слышал, как {g.mention(uid)} кричал перед смертью:\n<i>{html.escape(text)}</i>"



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/mafia.py
# Мафия: команды в группе, вход по ссылке в личку, кнопки ночи и голосования, предсмертные сообщения. Логика игры — bot/mafia.py.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__handlers_mafia = Router(name="mafia")

_GAME = re.compile(r"^(?:/game(?:@\w+)?|игра мафия|играть в мафию)$", re.IGNORECASE)
_START__handlers_mafia = re.compile(r"^(?:/startgame(?:@\w+)?|начать мафию|начать игру)$", re.IGNORECASE)
_STOP__handlers_mafia = re.compile(r"^(?:/stopgame(?:@\w+)?|стоп мафия|остановить мафию)$", re.IGNORECASE)
_DEEP = re.compile(r"^/start mafia_(-?\d{1,20}|role|go)$")
_GROUP__handlers_mafia = F.chat.type.in_({"group", "supergroup"})


def _is__handlers_mafia(rx):
    return F.text.func(lambda t: bool(t) and rx.match(t.strip()) is not None)


def _name__handlers_mafia(user) -> str:
    return (user.full_name or user.username or f"id{user.id}")[:40]


# Страж чата: на время партии удаляет сообщения тех, кто не играет или убит. Подключается в main.py ПЕРВЫМ роутером,
# чтобы такие сообщения не доходили ни до статистики, ни до ИИ. Команды управления игрой пропускает — ими пользуются ведущий и админы.
guard__handlers_mafia = Router(name="mafia_guard")


def _muted(message: Message) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False
    t = (message.text or "").strip()
    if t and (_START__handlers_mafia.match(t) or _STOP__handlers_mafia.match(t)):
        return False
    return must_delete(message.chat.id, message.from_user.id if message.from_user else None)


@guard__handlers_mafia.message(F.func(_muted))
async def delete_silenced(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass                                                # нет права удалять — бот предупредил об этом при старте игры


@router__handlers_mafia.message(_GROUP__handlers_mafia, _is__handlers_mafia(_GAME))
async def new_game(message: Message, bot, db: Database) -> None:
    if message.from_user is None:
        return
    if not (await db.get_settings(message.chat.id)).get("mafia_on", 1):
        return
    me = await bot.me()
    g, err = await open_registration(bot, message.chat.id, message.chat.title or "чат", message.from_user.id,
                                        _name__handlers_mafia(message.from_user), me.username)
    if err:
        await tell(message, f"⚠️ {err}")


@router__handlers_mafia.message(_GROUP__handlers_mafia, _is__handlers_mafia(_START__handlers_mafia))
async def start_game(message: Message, bot, db: Database) -> None:
    g = get_game(message.chat.id)
    if g is None or message.from_user is None:
        return
    if message.from_user.id != g.host and not await can_configure(bot, db, message.chat.id, message.from_user.id):
        await tell(message, "⚠️ Начать игру может ведущий набора или админ.")
        return
    err = request_start(g)
    if err:
        await tell(message, f"⚠️ {err}")


@router__handlers_mafia.message(_GROUP__handlers_mafia, _is__handlers_mafia(_STOP__handlers_mafia))
async def stop_game(message: Message, bot, db: Database) -> None:
    g = get_game(message.chat.id)
    if g is None or message.from_user is None:
        return
    if message.from_user.id != g.host and not await can_configure(bot, db, message.chat.id, message.from_user.id):
        await tell(message, "⚠️ Остановить игру может ведущий набора или админ.")
        return
    stop(g)


@router__handlers_mafia.message(F.chat.type == "private", _is__handlers_mafia(_DEEP))
async def deep_link(message: Message, bot) -> None:
    payload = _DEEP.match(message.text.strip()).group(1)
    if payload in ("role", "go"):
        await message.answer("Все ходы игры приходят сюда личными сообщениями с кнопками — смотри выше. Если ждёшь свою очередь, подожди пару секунд.")
        return
    g = get_game(int(payload))
    if g is None:
        await message.answer("Эта игра уже закончилась или не существует.")
        return
    me = await bot.me()
    err = await join(bot, g, message.from_user.id, _name__handlers_mafia(message.from_user), me.username)
    if err:
        await message.answer(f"⚠️ {err}")
        return
    await message.answer(f"Ты присоединился к игре в <b>{html.escape(g.title)}</b>. Когда начнётся игра, роль придёт сюда.")


@router__handlers_mafia.callback_query(F.data.startswith("mf:"))
async def action(cb: CallbackQuery, bot) -> None:
    try:
        _, kind, chat, arg = cb.data.split(":")
        g, arg = get_game(int(chat)), int(arg)
    except ValueError:
        await cb.answer()
        return
    if g is None or cb.from_user.id not in g.players:
        await cb.answer("Игра закончилась.", show_alert=True)
        return
    uid = cb.from_user.id
    if kind == "n":
        text, extra = night_action(g, uid, arg)
        if text.startswith("⚠️"):
            await cb.answer(text[3:], show_alert=True)
            return
        await _finish_pick(cb, text)
        for to, msg in extra:
            await _say(bot, to, msg)
        if g.players[uid].role in MAFIA and all(u in g.mafia_votes for u in g.alive_ids(MAFIA)):
            target = g.mafia_target()
            if target is not None:
                for m in g.alive_ids(MAFIA):
                    await _say(bot, m, f"Голосование мафии завершено\nМафия принесла в жертву {html.escape(g.players[target].name)}.")
    elif kind == "v":
        text, announce = vote_action(g, uid, arg)
        if announce is None:
            await cb.answer(text[3:], show_alert=True)
            return
        await _finish_pick(cb, text)
        await _say(bot, g.chat_id, announce)
    elif kind == "c":
        err = g.cast_confirm(uid, bool(arg))
        await cb.answer(err or "Голос принят", show_alert=bool(err))
    else:
        await cb.answer()


async def _finish_pick(cb: CallbackQuery, text: str) -> None:
    """Выбор сделан: убираем кнопки, оставляем «Ты выбрал …»."""
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=None)
    except Exception:
        pass


def _can_speak(message: Message) -> bool:
    if message.from_user is None or not message.text:
        return False
    g = game_of_user(message.from_user.id)
    p = g.players.get(message.from_user.id) if g else None
    return bool(p and not p.alive and p.can_speak and not message.text.startswith("/"))


@router__handlers_mafia.message(F.chat.type == "private", F.func(_can_speak))
async def final_words(message: Message, bot) -> None:
    g = game_of_user(message.from_user.id)
    text = last_words(g, message.from_user.id, message.text)
    if text is None:
        return
    await message.answer("Сообщение принято и будет отправлено в чат через бота.")
    await _say(bot, g.chat_id, text)



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/mog.py
# Мог-баттл: «мог @ник» (или «мог» ответом) — вызов конкретному человеку; «мог» / «могну» без цели — открытый вызов,
# принять может любой. После принятия ИИ оценивает аватарку, ник и @юзернейм, а Premium и возраст аккаунта считает бот,
# Нори присылает картинку с результатом: у проигравшего на аватарке «MOGGED» и крест. «мог топ» — рейтинг моггеров.
#
# Аватарки и профили уходят во внешний ИИ только после согласия обоих (вызвал сам + принял кнопкой) и только если ИИ
# включён в чате и у владельца бота. Без ИИ баттл всё равно идёт — «судит удача», и это написано на картинке.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__handlers_mog = Router(name="mog")
router__handlers_mog.message.filter(Enabled("mog_on"))   # группу команд можно выключить в настройках → «Команды»
CHALLENGE_TTL = 300
COOLDOWN__handlers_mog = 30               # вызывать — не чаще раза в 30 с на человека
DAILY__handlers_mog = 40                  # баттлов с ИИ в сутки на чат (защита ключа ИИ)
_RE__handlers_mog = re.compile(r"^(?:мог|mog|могну|могнуть)(?:\s+(@\w+|\d{5,}))?$", re.IGNORECASE)
_TOP = re.compile(r"^(?:мог топ|топ мог|моггеры)$", re.IGNORECASE)
_pending__handlers_mog: dict[str, dict] = {}
_cool__handlers_mog: dict[tuple[int, int], float] = {}
_locks__handlers_mog: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def _kb__handlers_mog(cid: str, open_: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="⚔️ Принять", callback_data=f"mog:{cid}:yes")] + ([] if open_ else [B(text="Отклонить", callback_data=f"mog:{cid}:no")]),
        [B(text="↩️ Отозвать", callback_data=f"mog:{cid}:x")]])


def _prune(now: float) -> None:
    for k in [k for k, v in _pending__handlers_mog.items() if v["expires"] < now]:
        _pending__handlers_mog.pop(k, None)
    if len(_cool__handlers_mog) > 5000:
        for k in [k for k, t in _cool__handlers_mog.items() if now - t > COOLDOWN__handlers_mog]:
            _cool__handlers_mog.pop(k, None)


def _player(user) -> dict:
    return {"uid": user.id, "name": user.full_name, "username": user.username, "premium": bool(getattr(user, "is_premium", False))}


@router__handlers_mog.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: bool(t) and _TOP.match(t.strip()) is not None))
async def mog_top(message: Message, db: Database) -> None:
    rows = await db.mog_top(message.chat.id)
    if not rows:
        await message.reply("🗿 Мог-баттлов ещё не было. Вызов: <code>мог @ник</code> или просто <code>мог</code>.")
        return
    lines = [f"{i}. {listed(u, (await db.user_name(u)) or f'id{u}', 28)} — {w} побед, {l} пор." for i, (u, w, l) in enumerate(rows, 1)]
    await message.reply("🗿 <b>Топ моггеров</b>\n" + "\n".join(lines))


@router__handlers_mog.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: bool(t) and _RE__handlers_mog.match(t.strip()) is not None))
async def mog_challenge(message: Message, bot, db: Database) -> None:
    u = message.from_user
    if u is None or u.is_bot:
        return
    chat, now = message.chat.id, time.time()
    _prune(now)
    token = _RE__handlers_mog.match(message.text.strip()).group(1)
    reply = real_reply(message)
    target = None
    if token:
        uid = await db.find_user(token) if token.startswith("@") else int(token)
        if uid is None:
            await tell(message, "❌ Не нашёл такого пользователя.")
            return
        await db.ensure_user(uid)
        target = {"uid": uid, "name": (await db.user_name(uid)) or f"id{uid}", "username": None, "premium": False}
    elif reply is not None and reply.from_user is not None:
        target = _player(reply.from_user)
        if reply.from_user.is_bot:
            await tell(message, "⚠️ С ботами не могаются 🗿")
            return
    if target is not None and target["uid"] in (u.id, (await bot.me()).id):
        await tell(message, "⚠️ Нужен живой соперник, не вы сами и не я.")
        return
    if now - _cool__handlers_mog.get((chat, u.id), 0) < COOLDOWN__handlers_mog:
        await tell(message, "⚠️ Остынь: вызывать можно раз в 30 секунд.")
        return
    if any(v["chat"] == chat and v["a"]["uid"] == u.id for v in _pending__handlers_mog.values()):
        await tell(message, "⚠️ У вас уже висит вызов — дождитесь ответа или отзовите его.")
        return
    _cool__handlers_mog[(chat, u.id)] = now
    cid = uuid.uuid4().hex[:10]
    _pending__handlers_mog[cid] = {"chat": chat, "a": _player(u), "b": target, "expires": now + CHALLENGE_TTL}
    who = mention__targets(u.id, u.full_name)
    if target is None:
        text = (f"🗿 {who} бросает открытый вызов на <b>мог-баттл</b>! Кто осмелится? Принять может любой.\n"
                "<i>ИИ оценит аватарки, ники и смысл юзернеймов, бот — их длину, подарки и NFT, Premium и возраст аккаунтов.</i>")
    else:
        text = (f"🗿 {who} вызывает {ping(target['uid'], target['name'])} на <b>мог-баттл</b>!\n"
                "<i>ИИ оценит аватарки, ники и смысл юзернеймов, бот — их длину, подарки и NFT, Premium и возраст аккаунтов. Принимаете?</i>")
    await message.answer(text, reply_markup=_kb__handlers_mog(cid, target is None))


@router__handlers_mog.callback_query(F.data.startswith("mog:"))
async def mog_cb(cb: CallbackQuery, bot, db: Database, ai=None, rt=None) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or cb.message is None:
        await cb.answer()
        return
    _, cid, op = parts
    v = _pending__handlers_mog.get(cid)
    if v is None or v["chat"] != cb.message.chat.id or v["expires"] < time.time():
        _pending__handlers_mog.pop(cid, None)
        await cb.answer("Вызов устарел.", show_alert=True)
        return
    uid = cb.from_user.id
    if op == "x":
        if uid != v["a"]["uid"]:
            await cb.answer("Отозвать может только тот, кто вызывал.", show_alert=True)
            return
        _pending__handlers_mog.pop(cid, None)
        await cb.message.edit_text("🗿 Вызов отозван.")
        await cb.answer()
        return
    if uid == v["a"]["uid"]:
        await cb.answer("Сам себя не могнёшь 🗿", show_alert=True)
        return
    if v["b"] is not None and uid != v["b"]["uid"]:
        await cb.answer("Это не ваш вызов.", show_alert=True)
        return
    if cb.from_user.is_bot:
        await cb.answer()
        return
    lock = _locks__handlers_mog.setdefault(cid, asyncio.Lock())
    if lock.locked():
        await cb.answer()
        return
    async with lock:
        if _pending__handlers_mog.pop(cid, None) is None:          # уже принял кто-то другой
            await cb.answer("Вызов уже принят.", show_alert=True)
            return
        if op == "no":
            await cb.message.edit_text(f"🗿 {mention__targets(uid, cb.from_user.full_name)} {await say(db, uid, '⟦отказался|отказалась⟧')} от мог-баттла. {await say(db, uid, '⟦Зассал|Зассала⟧')}?")
            await cb.answer()
            return
        b = _player(cb.from_user)                    # данные принявшего — из нажатия (имя, ник, Premium точные)
        await cb.answer("Баттл начинается!")
        try:
            await cb.message.edit_text(f"⚔️ {mention__targets(v['a']['uid'], v['a']['name'])} vs {mention__targets(b['uid'], b['name'])} — "
                                       "Нори оценивает профили… 🗿")
        except Exception:
            pass
        await run_battle(cb.message, bot, db, v["a"], b, ai, rt)


async def _gifts(bot, uid: int) -> tuple[int, int]:
    """(обычных, уникальных/NFT) подарков, которые человек показывает в профиле. Скрыл или сбой — (0, 0)."""
    regular = unique = 0
    try:
        offset = ""
        for _ in range(3):                                   # до 300 подарков — дальше счёт уже максимальный
            page = await bot.get_user_gifts(user_id=uid, limit=100, offset=offset or None)
            for g in page.gifts or []:
                if getattr(g, "type", "") == "unique":
                    unique += 1
                else:
                    regular += 1
            offset = getattr(page, "next_offset", None)
            if not offset:
                break
    except Exception:
        pass
    return regular, unique


async def _usernames(bot, uid: int, main: str | None) -> list[str]:
    """Все активные юзернеймы (основной первым): дополнительные бывают только коллекционными (NFT)."""
    try:
        info = await bot.get_chat(uid)
        names = list(getattr(info, "active_usernames", None) or [])
        if names:
            return names
    except Exception:
        pass
    return [main] if main else []


async def _rate(db: Database, ai, p: dict, use_ai: bool, now: int) -> tuple[dict, bool]:
    """(оценка профиля, оценивал ли ИИ). Запомненная оценка — сразу; иначе ИИ (температура 0) и запоминаем;
    без ИИ или при сбое — правила (одни и те же для всех, без случайностей)."""
    fp = fingerprint(p)
    cached = await db.mog_rating_get(fp, now)
    if cached is not None:
        return cached, True
    if use_ai:
        img = await asyncio.to_thread(normalized_jpeg, p["avatar"]) if p.get("avatar") else None
        rating = parse_rating(await ai.mog_rate(rate_prompt(p), img))
        if rating is not None:
            await db.mog_rating_put(fp, rating, now)
            return rating, True
    return rule_rating(p), False


async def run_battle(msg: Message, bot, db: Database, a: dict, b: dict, ai, rt) -> None:
    chat, now = msg.chat.id, int(time.time())
    players = [a, b]
    # всё про обоих игроков — параллельно, а не по очереди: аватарки, подарки, юзернеймы
    got = await asyncio.gather(*(avatar_info(bot, p["uid"]) for p in players),
                               *(_gifts(bot, p["uid"]) for p in players),
                               *(_usernames(bot, p["uid"], p.get("username")) for p in players))
    for i, p in enumerate(players):
        p["avatar"], p["avatar_id"] = got[i]
        p["has_photo"] = p["avatar"] is not None
        p["gifts_regular"], p["gifts_unique"] = got[2 + i]
        p["nft_usernames"] = collectible_usernames(got[4 + i])
        p["since"] = since_text(p["uid"], now)
    s = await db.get_settings(chat)
    use_ai = bool(ai is not None and getattr(ai, "has_river", False) and hasattr(ai, "mog_rate") and s["ai_on"]
                  and (rt is None or rt.flag("ai")))
    if use_ai and not await db.take_quota(chat, "mog", now, DAILY__handlers_mog):
        use_ai = False                                     # лимит ИИ на сегодня — оцениваем по правилам
    rated = await asyncio.gather(*(_rate(db, ai, p, use_ai, now) for p in players))   # каждого — отдельно
    by_ai = all(r[1] for r in rated)
    if use_ai and not any(r[1] for r in rated):
        await db.refund_quota(chat, "mog", now)             # ИИ не ответил толком — лимит не тратим
        use_ai = False
    sa, sb = scores_from(rated[0][0], a, now), scores_from(rated[1][0], b, now)
    win = winner__mog(sa, sb)
    verdict = ""
    if use_ai and hasattr(ai, "mog_verdict"):
        verdict = clean_verdict(await ai.mog_verdict(verdict_system(s.get("ai_chat_style", "casual")),
                                                         verdict_prompt(players, [sa, sb], win)))
    image = await asyncio.to_thread(mog_card, players, [sa, sb], CRITERIA, win, verdict, by_ai)
    w, l = players[win], players[1 - win]
    await db.mog_add(chat, w["uid"], l["uid"], now)
    caption = (f"🗿 {ping(w['uid'], w['name'])} <b>{await say(db, w['uid'], '⟦могнул|могнула⟧')}</b> {ping(l['uid'], l['name'])} — "
               f"{total(sa if win == 0 else sb)} : {total(sb if win == 0 else sa)}"
               + (f"\n<i>{html.escape(verdict)}</i>" if verdict else ""))
    try:
        await msg.answer_photo(BufferedInputFile(image, "mog.jpg"), caption=caption[:1000])
    finally:
        try:
            await msg.edit_text(f"⚔️ Мог-баттл {mention__targets(a['uid'], a['name'])} vs {mention__targets(b['uid'], b['name'])} завершён 👇")
        except Exception:
            pass



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/pair.py
# Пара: меню, действия, РП пары, история искр, расходы, список и топ, ссора, обида, расставание.
# Команды без слэша: «пара …» или «отн …» (например «пара действия», «пара завтрак», «пара обнять»). Запрос и брак — прежние
# команды «отношения @ник» / «брак @ник» (handlers/family.py): теперь они создают пару с общим кошельком.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__handlers_pair = Router(name="pair")
_RE__handlers_pair = re.compile(r"^(?:пара|отн)(?:\s+(.+))?$", re.IGNORECASE | re.DOTALL)
SUBS = {"меню": "menu", "я": "menu", "профиль": "menu", "действия": "actions", "действие": "actions", "история": "history",
        "лог": "history", "расходы": "costs", "расход": "costs", "содержание": "costs", "список": "list", "топ": "top",
        "расстаться": "end", "расторгнуть": "end", "обида": "offense", "обидеться": "offense", "простить": "offense",
        "помириться": "peace", "мир": "peace", "пополнить": "topup", "справка": "help", "помощь": "help",
        "запрос": "request", "задания": "quests", "задание": "quests", "квесты": "quests", "сезон": "season", "подарки": "gifts", "подарок": "gifts", "магазин": "gifts", "подарить": "give", "витрина": "showcase", "дом": "house", "близость": "intim", "малыш": "baby", "премиум": "premium", "vip": "premium", "питомцы": "pets", "питомец": "pets", "питомник": "pets", "дети": "kids", "ребёнок": "kids", "ребенок": "kids", "зал": "hall", "славы": "hall", "ожидание": "baby", "защита": "protect", "дома": "houses", "улица": "houses", "награда": "claim", "да": "yes", "нет": "no"}
TOP_KINDS = {"тепло": "тепло", "искры": "искры", "длительность": "длительность", "активность": "активность"}


def parse__handlers_pair(text: str | None):
    """(команда, остаток) или None, если это не команда пары («пара минут» в обычной речи не трогаем)."""
    m = _RE__handlers_pair.match((text or "").strip())
    if not m:
        return None
    rest = (m.group(1) or "").strip()
    if not rest:
        return "menu", ""
    word, _, arg = rest.partition(" ")
    key = norm__data(word)
    if key in SUBS:
        return SUBS[key], arg.strip()
    if find_action(rest):
        return "act", rest
    if find_rp(rest):
        return "rp", rest
    return None


def n(x: int) -> str:
    return f"{int(x):,}".replace(",", " ")


async def name(db: Database, uid: int) -> str:
    return (await db.user_name(uid)) or f"id{uid}"


async def m(db: Database, uid: int) -> str:
    return str(mention__targets(uid, await name(db, uid)))


def duration_since(ts: int, now: int) -> str:
    return fmt_duration(max(now - ts, 0))


# ---------- события (сообщения про ссору, распад, уровень) ----------
async def event_text(db: Database, p: dict, ev: tuple) -> str | None:
    kind, d = ev
    a, b = await m(db, p["u1"]), await m(db, p["u2"])
    if kind == "levelup":
        return f"🎖 {a} и {b}, у вас новый уровень: <b>{level_name(d['level'])}</b> ({d['level']}). Подарок: +{n(d['gift'])} 🔥"
    if kind == "quarrel":
        hours = max(round((d["until"] - int(time.time())) / 3600), 1)
        return f"💢 {a} и {b}, искры кончились, вы поссорились. Помиритесь за {hours} ч: <code>пара пополнить 100</code>."
    if kind == "dissolved":
        return f"💔 {a} и {b} больше не пара. Были вместе {duration_since(d['since'], int(time.time()))}."
    if kind == "warn":
        return f"🚨 {a} и {b}, искр на завтра не хватит: {n(d['sparks'])} из {n(d['need'])}. Загляните в <code>пара действия</code>."
    if kind == "quest":
        return f"✅ {a} и {b} справились с заданием: {d['text']} · +{n(d['sparks'])} 🔥 +{d['warmth']} ☀️"
    if kind == "bill_missed":
        return f"🧾 {a} и {b}, за дом не хватило денег. Долг {n(d['debt'])} 🔥, просрочек {d['missed']}. <code>пара дом оплатить</code>"
    if kind == "arrested":
        return f"🚔 Дом {a} и {b} арестован за долг {n(d['debt'])} 🔥. Оплатите: <code>пара дом оплатить</code>"
    if kind == "confiscated":
        return f"⚖️ Дом {a} и {b} забрали за долги. В кошелёк вернулось {n(d['back'])} 🔥."
    if kind == "pet_hatched":
        return f"🐣 У {a} и {b} вылупился питомец: {d['emoji']} <b>{d['species']}</b> ({d['rarity']})"
    if kind == "child_grown":
        return f"💼 {html.escape(d['name'])} вырос(ла) и съезжает от {a} и {b}. Профессия: <b>{d['job']}</b>. Оставил(а) вам {n(d['gift'])} 🔥"
    if kind == "baby_lost":
        return f"🤝 {a} и {b}, ожидание малыша не удалось сохранить. Это не ваша вина. Берегите друг друга."
    if kind == "baby_born":
        names = ", ".join(f"<b>{html.escape(x)}</b>" for x in d["names"])
        return f"👶 {a} и {b}, поздравляем! {'Родились' if len(d['names']) > 1 else 'Родился(ась)'} {names} · +{BIRTH_WARMTH} ☀️"
    if kind == "peace":
        return f"🤝 {a} и {b} помирились. Всё снова можно!"
    return None


async def event_lines(db: Database, p: dict, events: list, skip: tuple = ()) -> list[str]:
    out = []
    for ev in events:
        if ev[0] in skip:
            continue
        t = await event_text(db, p, ev)
        if t:
            out.append(t)
    return out


# ---------- экраны ----------
def menu_screen(p: dict, partner_name: str, now: int, kids: int, notes: list[str]) -> Screen:
    lvl = p["level"]
    base = threshold(lvl)
    step = level_step(lvl)
    upkeep = upkeep_amount(lvl, kids, p["sparks"])
    side = side_of__service(p, p["u1"])
    lines = [f"💞 <b>Половинка:</b> {partner_name}",
             f"🎖 Уровень {lvl} · <b>{level_name(lvl)}</b>",
             f"☀️ Тепло {n(p['warmth'] - base)} из {n(step)}",
             f"🔥 Искры {n(p['sparks'])}",
             f"📉 Расход {n(upkeep)} в сутки"
             + (f" · спишется через {fmt_duration(p['upkeep_at'] - now)}" if p["state"] == "ok" else ""),
             f"📅 Серия {effective_streak(p, now)} дн. · +{int(streak_bonus(effective_streak(p, now)) * 100)}% к теплу",
             (f"{BADGE} Премиум пары до {time.strftime('%d.%m.%Y', time.gmtime(p['premium_until']))}" if active(p, now) else "🕙 Премиум пары: <code>пара премиум</code>"),
             f"🕙 Вместе {duration_since(p['created'], now)}"
             + (" · 💍 в браке" if p["stage"] == "marriage" else "")]
    lines += notes
    lines.append(f"🆔 Пара № {p['id']}")
    pid = p["id"]
    rows = [[Btn("✨ Действия", cb=f"pr:a:{pid}"), Btn("📋 История", cb=f"pr:h:{pid}:all:0")],
            [Btn("📉 Расходы", cb=f"pr:e:{pid}"), Btn("👥 Пары беседы", cb=f"pr:l:{pid}")],
            [Btn("📋 Задания", cb=f"pr:q:{pid}"), Btn("🏆 Топ", cb=f"pr:t:{pid}:тепло")],
            [Btn("🎁 Подарки", cb=f"pr:gs:{pid}:0"), Btn("🖼 Витрина", cb=f"pr:sc:{pid}")],
            [Btn("🏠 Дом", cb=f"pr:ho:{pid}"), Btn("👶 Малыш", cb=f"pr:bb:{pid}")],
            [Btn("👦 Дети", cb=f"pr:ki:{pid}"), Btn("🐾 Питомцы", cb=f"pr:pt:{pid}")],
            [Btn("💎 Премиум", cb=f"pr:pm:{pid}"), Btn("⚙️ Ещё", cb=f"pr:more:{pid}")]]
    return Screen("💞 Ваша пара", lines, rows, quote=True)


def more_screen(p: dict, user: int) -> Screen:
    pid = p["id"]
    offended = p["offended_by"] == user
    return Screen("⚙️ Ещё", [
        "😢 Обида закрывает половинке действия и РП, пока ты не простишь.",
        "🤝 Помирить пару в ссоре может любое пополнение искр.",
        "💰 Пополнить кошелёк монетами: <code>пара пополнить 100</code> (1 монета = 1 искра)."],
        [[Btn("😊 Простить" if offended else "😢 Обидеться", cb=f"pr:ob:{pid}"), Btn("🤝 Помириться", cb=f"pr:peace:{pid}")],
         [Btn("💔 Расстаться", cb=f"pr:end:{pid}", style="danger")], [Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")]])


def actions_screen(p: dict, now: int, user: int, result_lines: list[str] | None = None) -> Screen:
    pid, lvl = p["id"], p["level"]
    side = side_of__service(p, user)
    wait = max(p[f"next{side}"] - now, 0)
    best = best_action(lvl)
    nxt = next_action(lvl)
    lines = list(result_lines or [])
    lines.append(f"✨ Лучшее: <b>{best.key}</b> · +{n(best.sparks)} 🔥 · откат {best.cd} мин.")
    if nxt:
        lines.append(f"🔒 Дальше: {nxt.key} — с {nxt.level} уровня")
    lines.append("✅ Действие доступно" if wait == 0 else f"⏳ Следующее действие через {fmt_duration(wait)}")
    lines.append("<i>Нажми на название или напиши «пара название».</i>")
    avail = unlocked(lvl)[-8:][::-1]
    btns = [Btn(f"{a.emoji} {a.key}", cb=f"pr:do:{pid}:{a.level}", style="primary" if a is best and wait == 0 else None) for a in avail]
    rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
    rows.append([Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("✨ Действия", lines, rows)


async def history_screen(svc: PairService, db: Database, p: dict, kind: str, page: int, now: int) -> Screen:
    pid = p["id"]
    rows_, total = await svc.history(pid, page, 10, kind, now)
    pages = max((total + 9) // 10, 1)
    page = min(max(page, 0), pages - 1)
    icons = {"action": "✨", "upkeep": "📉", "topup": "💰", "create": "💞", "quarrel": "💢", "level": "🎖"}
    lines = [f"🔥 Сейчас: {n(p['sparks'])}"]
    for r in rows_:
        t = time.strftime("%d.%m %H:%M", time.localtime(r["ts"] + 3 * 3600 - time.timezone))
        who = f" · {html.escape(await name(db, r['actor']))}" if r["actor"] else ""
        warm = f" · тепло +{r['warmth']}" if r["warmth"] else ""
        lines.append(f"{icons.get(r['kind'], '•')} {html.escape(r['detail'] or r['kind'])} · {t}{who} · стало {n(r['balance'])}{warm} · "
                     f"<b>{'+' if r['amount'] > 0 else ''}{n(r['amount'])}</b>")
    if not rows_:
        lines.append("Записей пока нет. История хранится 30 дней.")
    tabs = [Btn(("• " if kind == k else "") + label, cb=f"pr:h:{pid}:{k}:0") for label, k in (("Все", "all"), ("Приход", "in"), ("Траты", "out"))]
    nav = []
    if page > 0:
        nav.append(Btn("◀️", cb=f"pr:h:{pid}:{kind}:{page - 1}"))
    nav.append(Btn(f"{page + 1}/{pages}", cb="noop"))
    if page < pages - 1:
        nav.append(Btn("▶️", cb=f"pr:h:{pid}:{kind}:{page + 1}"))
    return Screen("📜 История искр", lines, [tabs, nav, [Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")]])


async def costs_screen(svc: PairService, p: dict, now: int) -> Screen:
    kids = await svc.kids(p)
    base = upkeep_base(p["level"])
    total = int(round(base * (1 + KID_UPKEEP * kids)))
    final = upkeep_amount(p["level"], kids, p["sparks"])
    lines = [f"🎖 Уровень {p['level']}: {n(base)}"]
    if kids:
        lines.append(f"👶 Дети: {kids}: +{n(total - base)} · +{int(kids * KID_UPKEEP * 100)}%")
    if final < total:
        lines.append(f"🏷 Потолок 3% кошелька: {n(final)}")
    lines.append(f"📉 Итого: <b>{n(final)}</b> в сутки")
    if p["state"] == "ok":
        lines.append(f"🕙 Спишется через {fmt_duration(p['upkeep_at'] - now)}")
        days = p["sparks"] // final if final else 0
        lines.append(f"🧮 Кошелька хватит примерно на {days} сут.")
    lines.append("<i>Каждый ребёнок прибавляет 10%, больше 3% кошелька за сутки не берём (но не меньше 15). В ссоре содержание не списывается.</i>")
    return Screen("📉 Расходы пары", lines, [[Btn("📜 Все траты", cb=f"pr:h:{p['id']}:out:0")],
                                              [Btn("◀️ Меню", cb=f"pr:m:{p['id']}", style="link")]])


async def list_screen(svc: PairService, db: Database, p: dict | None, chat: int, now: int) -> Screen:
    rows, sleeping = await svc.list_chat(chat, now)
    lines = []
    for i, r in enumerate(rows[:20], 1):
        mark = (" 💍" if r["stage"] == "marriage" else "") + (f" {BADGE}" if active(r, now) else "")
        lines.append(f"{i}. {html.escape(await name(db, r['u1']))} + {html.escape(await name(db, r['u2']))}{mark} · "
                     f"{duration_since(r['created'], now)} · ур. {r['level']}")
    if not lines:
        lines.append("В этой беседе пока нет пар.")
    lines.append(f"Всего: {len(rows)}" + (f" · спящих: {sleeping}" if sleeping else ""))
    back = [[Btn("◀️ Меню", cb=f"pr:m:{p['id']}", style="link")]] if p else []
    return Screen("👥 Пары беседы", lines, back)


async def top_screen(svc: PairService, db: Database, p: dict | None, chat: int, by: str, now: int) -> Screen:
    rows = await svc.top(chat, by, now)
    lines = []
    for i, r in enumerate(rows, 1):
        who = f"{html.escape(await name(db, r['u1']))} + {html.escape(await name(db, r['u2']))}"
        val = {"тепло": f"ур. {r['level']} · ☀️ {n(r['warmth'])}", "искры": f"🔥 {n(r['sparks'])}",
               "длительность": duration_since(r["created"], now), "активность": f"🫂 {n(r.get('activity', 0))}"}[by]
        lines.append(f"{i}. {who}{' ' + BADGE if active(r, now) else ''} · {val}")
    if not lines:
        lines.append("Пока нет пар.")
    pid = p["id"] if p else 0
    tabs = [Btn(("• " if k == by else "") + label, cb=f"pr:t:{pid}:{k}")
            for label, k in (("☀️ Тепло", "тепло"), ("🔥 Искры", "искры"), ("🕙 Время", "длительность"), ("🫂 Активность", "активность"))]
    rows_ = [tabs[:2], tabs[2:]]
    if p:
        rows_.append([Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("🏆 Топ пар беседы", lines, rows_)


def bar__handlers_pair(done: int, total: int, width: int = 8) -> str:
    k = round(width * min(done, total) / total) if total else width
    return "▰" * k + "▱" * (width - k)


async def quests_screen(svc: PairService, p: dict, now: int) -> Screen:
    pid = p["id"]
    rows = await svc.quests(p, now)
    lines = []
    for title, scope in (("Сегодня", "d"), ("На неделе", "w")):
        lines.append(f"<b>{title}</b>")
        for q in (r for r in rows if r["scope"] == scope):
            mark = "✅" if q["done"] else "🔘"
            lines.append(f"{mark} {text(q['kind'], q['goal'])}\n    {bar__handlers_pair(q['progress'], q['goal'])} {q['progress']}/{q['goal']}"
                         f" · +{n(q['reward'])} 🔥 · +{q['warmth']} ☀️")
    s = await svc.season(p, now)
    lines.append(f"🌟 Сезон: ступень {s['step']}/{s['max']} · очки {s['points']} (по {s['per']} на ступень)")
    btns = []
    if s["step"] > s["claimed"]:
        btns.append([Btn(f"🎁 Забрать награды сезона ({s['step'] - s['claimed']})", cb=f"pr:cl:{pid}", style="success")])
    btns.append([Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("📋 Задания пары", lines, btns)


def gifts_screen(p: dict, section: str) -> Screen:
    pid = p["id"]
    sec = section if section in SECTIONS else SECTIONS[0]
    items = [g for g in GIFTS if g.section == sec]
    lines = ["Подарок покупается за твои монеты и ложится в витрину пары. Подарить: <code>пара подарить роза</code> или кнопкой.",
             "Тепло получают первые 3 подарка в сутки."]
    lines += [f"{g.emoji} {g.key} · {n(g.price)} 🪙 · +{warmth__gifts(g.price)} ☀️" for g in items]
    tabs = [Btn(("• " if s == sec else "") + s, cb=f"pr:gs:{pid}:{i}") for i, s in enumerate(SECTIONS)]
    rows = [tabs[i:i + 3] for i in range(0, len(tabs), 3)]
    gi = SECTIONS.index(sec)
    buy = [Btn(f"{g.emoji} {g.key}", cb=f"pr:gb:{pid}:{GIFTS.index(g)}") for g in items]
    rows += [buy[i:i + 2] for i in range(0, len(buy), 2)]
    rows.append([Btn("🖼 Витрина", cb=f"pr:sc:{pid}"), Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("🎁 Подарки · " + sec, lines, rows)


async def showcase_screen(svc: PairService, p: dict) -> Screen:
    pid = p["id"]
    items = await svc.showcase(pid)
    lines = []
    for sec in SECTIONS:
        row = [f"{g.emoji} {g.key} ×{items[g.key]}" for g in GIFTS if g.section == sec and g.key in items]
        if row:
            lines.append(f"<b>{sec}:</b> " + " · ".join(row))
    if not lines:
        lines.append("Витрина пуста. Подарите что-нибудь половинке!")
    lines.append(f"✨ Престиж витрины: <b>{n(prestige__gifts(items))}</b>")
    return Screen("🖼 Витрина пары", lines, [[Btn("🎁 Подарки", cb=f"pr:gs:{pid}:0"), Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")]])


async def house_screen(svc: PairService, p: dict, now: int) -> Screen:
    pid = p["id"]
    h = await svc.house(pid)
    if h is None:
        lines = ["У пары пока нет дома. Дом даёт копилку, комнаты и престиж, но раз в неделю присылает счёт.",
                 f"🔥 В кошельке: {n(p['sparks'])}"]
        lines += [f"{x.emoji} {x.key} · {n(x.price)} 🔥 · комнат {x.slots} · копилка {n(x.hoard_cap)}" for x in HOUSES]
        btns = [Btn(f"{x.emoji} {x.key}", cb=f"pr:hb:{pid}:{i}") for i, x in enumerate(HOUSES)]
        rows = [btns[i:i + 3] for i in range(0, len(btns), 3)] + [[Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")]]
        return Screen("🏠 Дом", lines, rows)
    d = h["def"]
    title = html.escape(h["name"]) if h["name"] else d.key
    lines = [f"{d.emoji} <b>{title}</b> · {d.key}",
             f"🏅 {rank_name(h['prestige'])} · престиж {n(h['prestige'])}",
             f"💰 Копилка {n(h['hoard'])} из {n(d.hoard_cap)}",
             f"🧾 Счёт {n(h['bill'])} 🔥 через {fmt_duration(max(h['bill_at'] - now, 0))}"]
    if h["debt"]:
        lines.append(f"⚠️ Долг {n(h['debt'])} 🔥 · пропущено счетов {h['missed']}" + (" · 🚔 дом арестован" if h["arrested"] else ""))
    rooms = [f"{r.emoji} {r.key} {h['rooms'][r.key]}/{ROOM_MAX}" for r in ROOMS if r.key in h["rooms"]]
    lines.append(f"🚪 Комнаты {len(h['rooms'])}/{d.slots}: " + (" · ".join(rooms) if rooms else "пока нет"))
    nxt = [Btn(f"{r.emoji} {r.key} · {n(room_cost(r, h['rooms'].get(r.key, 0) + 1))}", cb=f"pr:hr:{pid}:{i}")
           for i, r in enumerate(ROOMS) if h["rooms"].get(r.key, 0) < ROOM_MAX
           and (r.key in h["rooms"] or len(h["rooms"]) < d.slots)]
    rows = [nxt[i:i + 2] for i in range(0, len(nxt), 2)]
    rows.append([Btn("💰 +100", cb=f"pr:hh:{pid}:100"), Btn("💰 +1000", cb=f"pr:hh:{pid}:1000"),
                 Btn("💰 −100", cb=f"pr:hh:{pid}:-100"), Btn("💰 −1000", cb=f"pr:hh:{pid}:-1000")])
    if h["debt"]:
        rows.append([Btn("💳 Оплатить долг", cb=f"pr:hp:{pid}", style="danger")])
    rows.append([Btn("🌃 Улица", cb=f"pr:hs:{pid}"), Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    lines.append("<i>Переезд в дом побольше: пара дом купить вилла (старый выкупают за 50%).</i>")
    return Screen("🏠 Дом", lines, rows)


async def street_screen(svc: PairService, db: Database, p: dict | None, chat: int) -> Screen:
    rows = await svc.top_houses(chat)
    lines = []
    for i, r in enumerate(rows, 1):
        h = find_house(r["tier"])
        nm = html.escape(r["name"]) if r["name"] else h.key
        lines.append(f"{i}. {h.emoji} {nm} · {html.escape(await name(db, r['u1']))} + {html.escape(await name(db, r['u2']))} · "
                     f"{rank_name(r['prestige'])} · {n(r['prestige'])}")
    if not lines:
        lines.append("На улице пока пусто. Арестованные дома в топ не попадают.")
    back = [[Btn("🏠 Мой дом", cb=f"pr:ho:{p['id']}"), Btn("◀️ Меню", cb=f"pr:m:{p['id']}", style="link")]] if p else []
    return Screen("🌃 Улица", lines, back)


async def baby_screen(svc: PairService, db: Database, p: dict, now: int) -> Screen:
    pid = p["id"]
    b = await svc.baby(pid, now)
    kids = await svc.children(pid)
    kid_line = "👶 Дети: " + (", ".join(html.escape(k["name"]) for k in kids) if kids else "пока нет")
    if b is None:
        return Screen("👶 Малыш", [kid_line, "Сейчас вы не ждёте малыша.",
                                  f"Защита: {'🛡 включена' if p['protect'] else '⚠️ выключена'} (<code>пара защита вкл|выкл</code>)"],
                      [[Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")]])
    w = b["week"]
    mother = await m(db, b["mother"]) if b["mother"] else "пока не выбрано"
    lines = [f"👶 Ожидание малыша · неделя {w}/{WEEKS} · триместр {trimester(w)}",
             f"👤 Носит: {mother}",
             f"❤️ Здоровье {bar__handlers_pair(b['health'], 100)} {b['health']}/100",
             f"🥄 Двойня: {'ждём двойню' if b['twins'] and w >= 12 else 'узнаем позже'}" if b["twins"] else "🥄 Один малыш",
             f"✏️ Имя: {html.escape(b['name']) if b['name'] else 'выберем при рождении (пара малыш имя Тима)'}",
             "Здоровье падает со временем: заботьтесь — врач, отдых, витамины.", kid_line]
    rows = []
    if not b["mother"]:
        rows.append([Btn("👶 Ношу я", cb=f"pr:bm:{pid}", style="primary")])
    care = [Btn(f"{e} {k}", cb=f"pr:bc:{pid}:{k}") for k, (e, _, _, _) in CARE__baby.items()]
    rows.append(care)
    if w < ABORT_UNTIL_WEEK:
        rows.append([Btn("🚫 Прервать", cb=f"pr:ba:{pid}", style="danger")])
    rows.append([Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("👶 Малыш", lines, rows)


async def kids_screen(svc: PairService, p: dict, now: int) -> Screen:
    pid = p["id"]
    rows_ = await svc.children(pid, now)
    lines, rows = [], []
    for c in rows_:
        if c["grown"]:
            lines.append(f"💼 {html.escape(c['name'])} · {c['job']} · взрослый(ая)")
            continue
        skills = " · ".join(f"{SKILL_NAMES[k]} {c[k]}" for k in SKILL_NAMES)
        lines.append(f"{'👶' if c['age'] < 3 else '👦'} <b>{html.escape(c['name'])}</b> · {c['age']} лет · {stage(c['age'])}\n"
                     f"    ❤️ {bar__handlers_pair(c['mood'], 100)} {c['mood']}/100 · {skills}")
        rows.append([Btn(f"{v[0]} {k}", cb=f"pr:kc:{pid}:{c['id']}:{k}") for k, v in CARE__kids.items() if c["age"] >= v[5]][:4])
    if not lines:
        lines.append("Детей пока нет. Пара может подождать малыша: <code>пара малыш</code>.")
    lines.append("<i>Год ребёнка — 5 суток. В 18 лет он выбирает профессию и съезжает.</i>")
    rows.append([Btn("👶 Малыш", cb=f"pr:bb:{pid}"), Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("👦 Дети", lines, rows)


async def pets_screen(svc: PairService, p: dict, now: int) -> Screen:
    pid = p["id"]
    pets = await svc.pets(pid, now)
    lines, rows = [], []
    for r in pets:
        if r["egg"]:
            lines.append(f"🥚 Яйцо · вылупится через {fmt_duration(max(r['hatch_at'] - now, 0))}")
            continue
        nm = html.escape(r["name"]) if r["name"] else r["species"]
        lines.append(f"{r['emoji']} <b>{nm}</b> · {r['species']} ({r['rarity']}) · ур. {r['level']}\n"
                     f"    ❤️ {bar__handlers_pair(r['mood'], 100)} {r['mood']}/100 · приносит {n(income(r['rarity'], r['xp']))} 🔥/сутки")
        rows.append([Btn(f"{v[0]} {k} {nm}", cb=f"pr:pc:{pid}:{r['id']}:{k}") for k, v in CARE__pets.items()])
    if not lines:
        lines.append("Питомцев пока нет. Яйцо стоит " + f"{EGG_PRICE} 🔥, вылупится за сутки; редкость случайная.")
    cap = PETS_MAX if active(p, now) else MAX_PETS
    lines.append(f"🔥 В кошельке {n(p['sparks'])} · места {len(pets)}/{cap}")
    act = []
    if len(pets) < cap:
        act.append(Btn(f"🥚 Яйцо · {EGG_PRICE}", cb=f"pr:pe:{pid}"))
    if any(not r["egg"] for r in pets):
        act.append(Btn("🎁 Забрать приработок", cb=f"pr:pg:{pid}", style="success"))
    if act:
        rows.append(act)
    rows.append([Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("🐾 Питомцы", lines, rows)


async def premium_screen(bot, p: dict, now: int) -> Screen:
    pid = p["id"]
    lines = [f"{BADGE} <b>Премиум пары</b> — {PRICE} ⭐ на 30 дней (платёж разовый, продлевается вручную).",
             f"☀️ +{WARMTH_PCT}% к теплу от всего, что вы делаете",
             f"🐾 {PETS_MAX} питомцев вместо {MAX_PETS}",
             f"🤝 {QUARREL_HOURS__pair_premium} часов на примирение вместо {QUARREL_HOURS__pair_economy}",
             f"{BADGE} значок в списках и топах"]
    if active(p, now):
        lines.append(f"✅ Активен до {time.strftime('%d.%m.%Y', time.gmtime(p['premium_until']))}. Можно продлить: +30 дней.")
    rows = []
    try:
        from aiogram.types import LabeledPrice
        link = await bot.create_invoice_link(
            title="Премиум пары", description="30 дней: +10% тепла, 5 питомцев, 48 часов на примирение, значок.",
            payload=payload(pid), currency="XTR", prices=[LabeledPrice(label="Премиум пары на 30 дней", amount=PRICE)])
        rows.append([Btn(f"⭐ Оплатить {PRICE}", url=link, style="success")])
    except Exception:
        logging.info("pair premium: не удалось создать счёт")
        lines.append("⚠️ Оплата сейчас недоступна, попробуйте позже.")
    rows.append([Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen(f"{BADGE} Премиум пары", lines, rows)


def help_text() -> str:
    return ("💞 <b>Пара</b>\n"
            "Искры 🔥 приносят действия, а раз в сутки часть уходит на жизнь. Кончились — ссора, потом расставание.\n"
            "☀️ Тепло растит уровень.\n"
            "<blockquote expandable>"
            "<code>отношения</code> реплеем или с @ником · завести пару\n<code>брак</code> · свадьба (с 3 уровня)\n"
            "<code>пара</code> · меню\n<code>пара действия</code> · <code>пара завтрак</code> · что-то сделать вместе\n"
            "<code>пара обнять</code> · РП: обнять, поцеловать, кусь, шлёп, погладить, щелбан и другие\n"
            "<code>пара задания</code> · <code>пара награда</code>\n"
            "<code>пара подарки</code> · <code>пара подарить роза</code> · <code>пара витрина</code>\n"
            "<code>пара дом</code> · <code>пара дома</code> · дом, комнаты, копилка, счёт\n"
            "<code>пара малыш</code> · <code>пара дети</code> · <code>пара питомцы</code>\n"
            "<code>пара близость</code> · <code>пара защита вкл|выкл</code> (если админ включил <code>+близость</code>)\n"
            "<code>пара история</code> · <code>расходы</code> · <code>список</code> · <code>топ</code>\n"
            "<code>пара пополнить 100</code> · монеты в искры\n"
            "<code>пара обида</code> · <code>пара расстаться</code> · <code>пара премиум</code>"
            "</blockquote>")


# ---------- команды ----------
async def _my_pair(message: Message, svc: PairService, now: int):
    """(пара, события) или (None, []) с подсказкой, если пары нет."""
    p = await svc.get(message.chat.id, message.from_user.id)
    if p is None:
        await tell(message, "💞 У вас нет пары в этой беседе. Завести: <code>отношения @ник</code> (или ответом на сообщение).")
        return None, []
    p, events = await svc.settle(p["id"], now)
    return p, events


async def _send_events(message: Message, db: Database, p: dict | None, events: list, pair_row: dict, skip: tuple = ()) -> None:
    for t in await event_lines(db, pair_row, events, skip):
        await message.answer(t)


@router__handlers_pair.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("+близость", "-близость")))
async def intim_toggle(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    if not await is_admin__mod_service(bot, message.chat.id, message.from_user.id):
        await tell(message, "⚠️ Включать близость пар могут только админы.")
        return
    on = message.text.strip().startswith("+")
    await db.set_setting(message.chat.id, "pair_intim", 1 if on else 0)
    await message.reply("🌙 Близость пар включена (только для взрослых беседы, по согласию обоих)." if on else "🌙 Близость пар выключена.")


@router__handlers_pair.message(F.text.func(lambda t: parse__handlers_pair(t) is not None))
async def pair_cmd(message: Message, bot, db: Database, http=None) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    if not (await db.get_settings(message.chat.id))["rp_on"]:
        return
    sub, arg = parse__handlers_pair(message.text)
    svc, fam, now = PairService(db), Family(db), int(time.time())
    chat, me = message.chat.id, message.from_user.id

    if sub == "help":
        await message.reply(help_text())
        return
    if sub == "request":                                           # «пара запрос @ник» = «отношения @ник»
        pass  # (импорт убран: всё в одном модуле)
        target = await resolve_user(db, arg or None, real_reply(message))
        if target is None:
            await tell(message, "⚠️ Ответьте командой на сообщение человека или укажите @ник.")
            return
        if target[0] == (await bot.me()).id:
            await message.reply("🤖 Я всего лишь бот, у меня нет пары.")
            return
        await _propose(message, bot, db, fam, "relation", target[0], now)
        return
    if sub in ("yes", "no"):
        pass  # (импорт убран: всё в одном модуле)
        req = await fam.pending_to(chat, me, now)
        if req is None:
            await tell(message, "ℹ️ Вам никто не предлагал: ответить можно на запрос «отношения @ник» или «брак @ник».")
            return
        if not await fam.delete_request(req["id"]):
            return
        text = await _apply(db, fam, req["kind"], chat, req["from_user"], req["to_user"], now) if sub == "yes" else "💔 Отказ."
        edited = False
        if req.get("message_id"):
            try:
                await bot.edit_message_text(text, chat_id=chat, message_id=req["message_id"])
                edited = True
            except Exception:
                pass
        if not edited:
            await message.answer(text)
        if sub == "yes" and "теперь" in text:
            await extra_gif(bot, http, chat, FAMILY_MAP.get(req["kind"]), await get(db, req["from_user"]),
                                 await get(db, req["to_user"]))
        return
    if sub in ("list", "top") and await svc.get(chat, me) is None:   # списки доступны и без своей пары
        if sub == "list":
            await message.answer(**_msg(await list_screen(svc, db, None, chat, now)))
        else:
            by = TOP_KINDS.get(norm__data(arg), "тепло")
            await message.answer(**_msg(await top_screen(svc, db, None, chat, by, now)))
        return

    if not await ensure(message, db):
        return
    p, events = await _my_pair(message, svc, now)
    if p is None:
        for r in events:
            pass
        return
    partner = partner_of(p, me)
    if sub == "menu":
        await _send_menu(message, db, svc, p, partner, now)
    elif sub == "actions":
        await send__rich_ui(bot, chat, actions_screen(p, now, me), thread_id=_thread(message))
    elif sub in ("act", "rp"):
        res = await (svc.act(p["id"], me, arg, now) if sub == "act" else svc.rp(p["id"], me, arg, now))
        if not res.ok:
            await tell(message, res.error or "⚠️ Не получилось.")
        else:
            text = await _result_text(db, p, me, partner, res, sub)
            sent = False
            if sub == "rp" and (await db.get_settings(chat)).get("rp_gifs", 1):
                sent = await reply_gif(bot, http, message, text, PAIR_MAP.get(res.info["rp"].key), await get(db, me),
                                            await get(db, partner), reply_to=message.message_id)
            if not sent:
                await message.reply(text)
        for t in await event_lines(db, p, res.events, skip=("levelup",) if sub == "act" and res.ok else ()):
            await message.answer(t)
    elif sub in ("quests", "season"):
        await send__rich_ui(bot, chat, await quests_screen(svc, p, now), thread_id=_thread(message))
    elif sub == "gifts":
        sec = next((s for s in SECTIONS if norm__data(s) == norm__data(arg)), SECTIONS[0])
        await send__rich_ui(bot, chat, gifts_screen(p, sec), thread_id=_thread(message))
    elif sub == "showcase":
        await send__rich_ui(bot, chat, await showcase_screen(svc, p), thread_id=_thread(message))
    elif sub == "give":
        res = await svc.give(p["id"], me, arg, now)
        if not res.ok:
            await tell(message, f"⚠️ {res.error}")
        else:
            g = res.info["gift"]
            extra = f" · +{res.info['warmth']} ☀️" if res.info["warmth"] else ""
            await message.reply(f"{g.emoji} {await m(db, me)} дарит {await m(db, partner)}: <b>{g.key}</b>{extra}")
        for t in await event_lines(db, p, res.events):
            await message.answer(t)
    elif sub == "houses":
        await send__rich_ui(bot, chat, await street_screen(svc, db, p, chat), thread_id=_thread(message))
    elif sub == "house":
        word, _, rest = arg.partition(" ")
        w = norm__data(word)
        res = None
        if w in ("купить", "переехать"):
            res = await svc.buy_house(p["id"], me, rest, now)
            ok = f"{res.info['house'].emoji} Куплен дом «{res.info['house'].key}» за {n(res.info['cost'])} 🔥" if res.ok else None
        elif w in ("комната", "построить", "улучшить"):
            res = await svc.build_room(p["id"], me, rest, now)
            ok = f"{res.info['room'].emoji} {res.info['room'].key}: уровень {res.info['level']} за {n(res.info['cost'])} 🔥" if res.ok else None
        elif w == "копилка":
            sign = -1 if rest.startswith(("-", "−")) else 1
            digits = "".join(ch for ch in rest if ch.isdigit())
            if not digits:
                await tell(message, "⚠️ Например: <code>пара дом копилка +500</code> или <code>-500</code>.")
                return
            res = await svc.hoard_move(p["id"], me, sign * int(digits), now)
            ok = f"💰 Копилка: {n(res.info['hoard'])} · кошелёк {n(res.info['sparks'])}" if res.ok else None
        elif w == "оплатить":
            res = await svc.pay_debt(p["id"], me, now)
            ok = (f"💳 Оплачено {n(res.info['paid'])} 🔥, долг {n(res.info['debt'])}" + (" · 🚔 арест снят" if res.info["free"] else "")) if res.ok else None
        elif w in ("имя", "название"):
            res = await svc.rename_house(p["id"], me, rest)
            ok = f"✏️ Название: {html.escape(res.info['name'])}" if res.ok else None
        if res is not None:
            await (message.reply(ok) if res.ok else tell(message, f"⚠️ {res.error}"))
            for t in await event_lines(db, p, res.events):
                await message.answer(t)
        else:
            await send__rich_ui(bot, chat, await house_screen(svc, p, now), thread_id=_thread(message))
    elif sub == "protect":
        on = norm__data(arg) in ("вкл", "включить", "да", "on", "+")
        if norm__data(arg) not in ("вкл", "включить", "да", "on", "+", "выкл", "выключить", "нет", "off", "-"):
            await tell(message, f"ℹ️ Защита сейчас {'включена' if p['protect'] else 'выключена'}: <code>пара защита вкл</code> или <code>выкл</code>.")
            return
        await svc.set_protect(p["id"], me, on)
        await message.reply("🛡 Защита включена." if on else "⚠️ Защита выключена: шанс малыша заметно выше.")
    elif sub == "intim":
        if not (await db.get_settings(chat))["pair_intim"]:
            await tell(message, "🔒 Близость пар выключена в этой беседе: админ включает «+близость».")
            return
        err = svc.intim_check(p, me, now)
        if err:
            await tell(message, f"⚠️ {err}")
            return
        pid = p["id"]
        exp = now + 300
        await message.answer(
            f"🌙 {await m(db, me)} предлагает {await m(db, partner)} провести вечер вместе. Защита: {'🛡 включена' if p['protect'] else '⚠️ выключена'}.",
            reply_markup=kb__rich_ui([[Btn("💞 " + gz("⟦Согласен|Согласна⟧", await get(db, partner)), cb=f"pr:iy:{pid}:{me}:{exp}", style="success"),
                                      Btn("✖️ Не сейчас", cb=f"pr:in:{pid}:{me}:{exp}")]]))
    elif sub == "baby":
        word, _, rest = arg.partition(" ")
        w = norm__data(word)
        if w in CARE__baby:
            res = await svc.care(p["id"], me, w, now)
            await (message.reply(f"{res.info['emoji']} {res.info['label'].capitalize()}: здоровье +{res.info['plus']} → {res.info['health']}/100")
                   if res.ok else tell(message, f"⚠️ {res.error}"))
        elif w in ("имя", "назвать"):
            res = await svc.name_baby(p["id"], me, rest)
            await (message.reply(f"✏️ Имя малыша: {html.escape(res.info['name'])}") if res.ok else tell(message, f"⚠️ {res.error}"))
        elif w in ("прервать",):
            await message.answer("🚫 Прервать ожидание? Решение необратимо.", reply_markup=kb__rich_ui(
                [[Btn("Да, прервать", cb=f"pr:bay:{p['id']}", style="danger"), Btn("Отмена", cb=f"pr:bn:{p['id']}")]]))
        else:
            await send__rich_ui(bot, chat, await baby_screen(svc, db, p, now), thread_id=_thread(message))
    elif sub == "kids":
        kws = arg.split()
        act = next((w for w in kws if norm__data(w) in CARE__kids), None)
        if act:
            nm = " ".join(w for w in kws if w is not act)
            kids_ = [c for c in await svc.children(p["id"], now) if not c["grown"]]
            c = next((c for c in kids_ if norm__data(c["name"]) == norm__data(nm)), kids_[0] if kids_ and not nm else None)
            if c is None:
                await tell(message, "⚠️ Не нашёл ребёнка: <code>пара дети покормить Тима</code>.")
            else:
                res = await svc.care_child(p["id"], me, c["id"], act, now)
                if res.ok:
                    i = res.info
                    extra = f" · {SKILL_NAMES[i['skill']]} +{i['gained']}" if i["gained"] else ""
                    await message.reply(f"{i['emoji']} Вы с {html.escape(i['name'])} {i['label']}: настроение {i['mood']}/100{extra}")
                else:
                    await tell(message, f"⚠️ {res.error}")
        else:
            await send__rich_ui(bot, chat, await kids_screen(svc, p, now), thread_id=_thread(message))
    elif sub == "pets":
        word, _, rest = arg.partition(" ")
        w = norm__data(word)
        pets = [r for r in await svc.pets(p["id"], now) if not r["egg"]]
        if w in ("яйцо", "купить"):
            res = await svc.buy_egg(p["id"], me, now)
            await (message.reply(f"🥚 Яйцо куплено за {EGG_PRICE} 🔥, вылупится через сутки.") if res.ok else tell(message, f"⚠️ {res.error}"))
        elif w in ("собрать", "забрать", "доход"):
            res = await svc.collect_pets(p["id"], me, now)
            await (message.reply(f"🎁 Питомцы принесли {n(res.info['sparks'])} 🔥") if res.ok else tell(message, f"⚠️ {res.error}"))
            for t in await event_lines(db, p, res.events):
                await message.answer(t)
        elif w in CARE__pets:
            nm = rest.strip()
            r = next((x for x in pets if norm__data(x["name"] or x["species"]) == norm__data(nm)), pets[0] if pets and not nm else None)
            if r is None:
                await tell(message, "⚠️ Не нашёл питомца: <code>пара питомцы покормить Пушок</code>.")
            else:
                res = await svc.care_pet(p["id"], me, r["id"], w, now)
                await (message.reply(f"{res.info['emoji']} {html.escape(r['name'] or r['species'])}: настроение {res.info['mood']}/100")
                       if res.ok else tell(message, f"⚠️ {res.error}"))
        elif w in ("имя", "назвать"):
            old, _, new = rest.partition(" ")
            r = next((x for x in pets if norm__data(x["name"] or x["species"]) == norm__data(old)), None)
            if r is None or not new:
                await tell(message, "⚠️ Так: <code>пара питомцы имя котёнок Пушок</code>.")
            else:
                res = await svc.name_pet(p["id"], me, r["id"], new)
                await (message.reply(f"✏️ Теперь его зовут {html.escape(res.info['name'])}") if res.ok else tell(message, f"⚠️ {res.error}"))
        else:
            await send__rich_ui(bot, chat, await pets_screen(svc, p, now), thread_id=_thread(message))
    elif sub == "premium":
        await send__rich_ui(bot, chat, await premium_screen(bot, p, now), thread_id=_thread(message))
    elif sub == "claim":
        res = await svc.claim_season(p["id"], me, now)
        await (message.reply(f"🎁 Награда сезона: +{n(res.info['sparks'])} 🔥 (ступень {res.info['step']})") if res.ok
               else tell(message, f"⚠️ {res.error}"))
    elif sub == "history":
        kind = {"приход": "in", "траты": "out", "доход": "in"}.get(norm__data(arg.split()[0]) if arg else "", "all")
        page = int(arg.split()[-1]) - 1 if arg and arg.split()[-1].isdigit() else 0
        await send__rich_ui(bot, chat, await history_screen(svc, db, p, kind, page, now), thread_id=_thread(message))
    elif sub == "costs":
        await send__rich_ui(bot, chat, await costs_screen(svc, p, now), thread_id=_thread(message))
    elif sub == "list":
        await send__rich_ui(bot, chat, await list_screen(svc, db, p, chat, now), thread_id=_thread(message))
    elif sub == "top":
        by = TOP_KINDS.get(norm__data(arg), "тепло")
        await send__rich_ui(bot, chat, await top_screen(svc, db, p, chat, by, now), thread_id=_thread(message))
    elif sub == "offense":
        res = await svc.toggle_offense(p["id"], me, now)
        if not res.ok:
            await tell(message, f"⚠️ {res.error}")
        elif res.info["offended"]:
            await message.answer(f"😢 {await m(db, partner)}, твоя половинка в обиде. Действия и РП для тебя закрыты, пока "
                                 f"{await m(db, me)} не простит: <code>пара обида</code>.")
        else:
            await message.answer(f"😊 {await m(db, partner)}, твоя половинка больше не обижается. Всё снова доступно!")
    elif sub == "peace":
        await message.reply(_peace_hint(p, now))
    elif sub == "topup":
        if not arg.isdigit():
            await tell(message, "⚠️ Сколько монет? Например: <code>пара пополнить 100</code>.")
            return
        res = await svc.topup(p["id"], me, int(arg), now)
        if not res.ok:
            await tell(message, f"⚠️ {res.error}")
            return
        await message.reply(f"💰 В кошелёк пары добавлено <b>{n(res.info['sparks'])}</b> 🔥.")
        for t in await event_lines(db, p, res.events):
            await message.answer(t)
    elif sub == "end":
        await send__rich_ui(bot, chat, await _end_screen(db, p, partner), thread_id=_thread(message))


def _thread(message: Message) -> int | None:
    return message.message_thread_id if getattr(message, "is_topic_message", False) else None


def _msg(screen: Screen) -> dict:
    text, kb = to_classic(screen)
    return {"text": text, "reply_markup": kb}


def _peace_hint(p: dict, now: int) -> str:
    if p["state"] != "quarrel":
        return "🤝 Вы не в ссоре. Всё хорошо!"
    return (f"💢 Вы в ссоре: искры кончились, действия закрыты. Помирят любые искры — пополните кошелёк: "
            f"<code>пара пополнить 100</code>. Осталось {fmt_duration(p['quarrel_until'] - now)}.")


async def _send_menu(message: Message, db: Database, svc: PairService, p: dict, partner: int, now: int) -> None:
    await send__rich_ui(message.bot, message.chat.id, await _menu(db, svc, p, message.from_user.id, now),
                       thread_id=_thread(message))


async def _menu(db: Database, svc: PairService, p: dict, user: int, now: int) -> Screen:
    partner = partner_of(p, user)
    kids = await svc.kids(p)
    notes = []
    if p["state"] == "quarrel":
        notes.append(f"💢 <b>Ссора</b>: помирят любые искры, осталось {fmt_duration(p['quarrel_until'] - now)}")
    elif p["sparks"] < upkeep_amount(p["level"], kids, p["sparks"]) * 2:
        notes.append("🚨 Искр мало: скоро не хватит на содержание")
    if p["offended_by"]:
        notes.append("😢 Обида: " + ("ты обижаешься на половинку" if p["offended_by"] == user else "половинка обижена на тебя"))
    side = side_of__service(p, user)
    wait = p[f"next{side}"] - now
    notes.append("✨ Действие доступно" if wait <= 0 else f"⏳ Действие через {fmt_duration(wait)}")
    if is_sleeping(p, now):
        notes.append("💤 Пара спит: давно ничего не делали")
    return menu_screen(p, await m(db, partner), now, kids, notes)


async def _end_screen(db: Database, p: dict, partner: int) -> Screen:
    pid = p["id"]
    word = "Развестись" if p["stage"] == "marriage" else "Расстаться"
    return Screen(f"💔 {word} с {html.escape(await name(db, partner))}?", [
        f"Пропадёт всё, что есть у пары: {n(p['sparks'])} 🔥, уровень {p['level']}. Согласие половинки не нужно."],
        [[Btn(f"💔 Да, {word.lower()}", cb=f"pr:endy:{pid}", style="danger"), Btn("✖️ Отмена", cb=f"pr:m:{pid}")]])


async def _result_text(db: Database, p: dict, me: int, partner: int, res, sub: str) -> str:
    a, b = await m(db, me), await m(db, partner)
    i = res.info
    if sub == "rp":
        rp = i["rp"]
        extra = f"\n☀️ +{i['warmth']} тепла" if i["warmth"] else ""
        return f"{rp.emoji} {rp.text.format(a=a, b=b)}{extra}"
    act = i["action"]
    lines = [f"{act.emoji} {act.text.format(a=a, b=b)}",
             f"🔥 +{n(i['sparks'])} · ☀️ +{i['warmth']} тепла · снова через {fmt_duration(i['cd'])}"]
    extras = []
    if i["tired"]:
        extras.append("😮‍💨 усталость: награда вдвое меньше")
    if i["unison"]:
        extras.append("в унисон +20%")
    if i["streak"] and not i["together"]:
        extras.append(f"серия {i['streak']} дн. +{int(streak_bonus(i['streak']) * 100)}%")
    if extras:
        lines.append("🔗 " + " · ".join(extras))
    if i["together"]:
        lines.append(f"💞 День вместе засчитан: серия {i['streak']} дн., +{DAY_TOGETHER_WARMTH} тепла")
    for ev in res.events:
        if ev[0] == "levelup":
            lines.append(f"🎖 Новый уровень: <b>{level_name(ev[1]['level'])}</b> ({ev[1]['level']})! 🎁 +{n(ev[1]['gift'])} 🔥")
    return "\n".join(lines)


# ---------- кнопки ----------
@router__handlers_pair.callback_query(F.data.startswith("pr:"))
async def pair_cb(cb: CallbackQuery, bot, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit() or cb.message is None:
        await cb.answer()
        return
    op, pid, args = parts[1], int(parts[2]), parts[3:]
    svc, now, user = PairService(db), int(time.time()), cb.from_user.id
    p0 = await svc.get_by_id(pid)
    if p0 is None or p0["ended_at"] is not None or p0["chat_id"] != cb.message.chat.id:
        await cb.answer("Эта пара уже не существует.", show_alert=True)
        return
    if user not in (p0["u1"], p0["u2"]):
        await cb.answer("Не твоя кнопка", show_alert=True)
        return
    p, events = await svc.settle(pid, now)
    if p is None:
        await cb.answer("💔 Пара распалась.", show_alert=True)
        for t in await event_lines(db, p0, events):
            await cb.message.answer(t)
        return
    partner = partner_of(p, user)
    popup = None
    if op == "m":
        screen = await _menu(db, svc, p, user, now)
    elif op == "more":
        screen = more_screen(p, user)
    elif op == "a":
        screen = actions_screen(p, now, user)
    elif op == "do":
        level = int(args[0]) if args and args[0].isdigit() else 0
        action = next((x for x in ACTIONS__data if x.level == level), None)
        res = await svc.act(pid, user, action.key, now) if action else None
        p = await svc.get_by_id(pid)
        if res is None or not res.ok:
            popup = res.error if res else "Нет такого действия."
            screen = actions_screen(p, now, user)
        else:
            text = await _result_text(db, p, user, partner, res, "act")
            popup = f"+{n(res.info['sparks'])} 🔥 · +{res.info['warmth']} ☀️"
            screen = actions_screen(p, now, user, text.split("\n"))
    elif op == "h":
        kind = args[0] if args else "all"
        page = int(args[1]) if len(args) > 1 and args[1].lstrip("-").isdigit() else 0
        screen = await history_screen(svc, db, p, kind if kind in ("all", "in", "out") else "all", page, now)
    elif op == "q":
        screen = await quests_screen(svc, p, now)
    elif op == "cl":
        res = await svc.claim_season(pid, user, now)
        popup = f"🎁 +{n(res.info['sparks'])} 🔥" if res.ok else res.error
        p = await svc.get_by_id(pid)
        screen = await quests_screen(svc, p, now)
    elif op == "gs":
        i = int(args[0]) if args and args[0].isdigit() else 0
        screen = gifts_screen(p, SECTIONS[i] if i < len(SECTIONS) else SECTIONS[0])
    elif op == "gb":
        i = int(args[0]) if args and args[0].isdigit() else -1
        g = GIFTS[i] if 0 <= i < len(GIFTS) else None
        res = await svc.give(pid, user, g.key, now) if g else None
        p = await svc.get_by_id(pid)
        if res is None or not res.ok:
            popup = res.error if res else "Нет такого подарка."
        else:
            popup = f"{g.emoji} Подарено: {g.key}"
            await cb.message.answer(f"{g.emoji} {await m(db, user)} дарит {await m(db, partner)}: <b>{g.key}</b>"
                                    + (f" · +{res.info['warmth']} ☀️" if res.info["warmth"] else ""))
            events = events + res.events
        screen = gifts_screen(p, g.section if g else SECTIONS[0])
    elif op == "sc":
        screen = await showcase_screen(svc, p)
    elif op == "ho":
        screen = await house_screen(svc, p, now)
    elif op == "hs":
        screen = await street_screen(svc, db, p, p["chat_id"])
    elif op in ("hb", "hr", "hh", "hp"):
        res = None
        if op == "hb":
            i = int(args[0]) if args and args[0].isdigit() else -1
            res = await svc.buy_house(pid, user, HOUSES[i].key, now) if 0 <= i < len(HOUSES) else None
            popup = "🏠 Дом куплен!" if res and res.ok else None
        elif op == "hr":
            i = int(args[0]) if args and args[0].isdigit() else -1
            res = await svc.build_room(pid, user, ROOMS[i].key, now) if 0 <= i < len(ROOMS) else None
            popup = "🚪 Комната улучшена" if res and res.ok else None
        elif op == "hh":
            res = await svc.hoard_move(pid, user, int(args[0]) if args else 0, now)
            popup = "💰 Готово" if res.ok else None
        else:
            res = await svc.pay_debt(pid, user, now)
            popup = "💳 Оплачено" if res.ok else None
        if res is not None and not res.ok:
            popup = res.error
        events = events + (res.events if res else [])
        p = await svc.get_by_id(pid)
        screen = await house_screen(svc, p, now)
    elif op == "ki":
        screen = await kids_screen(svc, p, now)
    elif op == "kc":
        res = await svc.care_child(pid, user, int(args[0]) if args and args[0].isdigit() else 0, args[1] if len(args) > 1 else "", now)
        popup = (f"{res.info['emoji']} {res.info['name']}: настроение {res.info['mood']}" if res.ok else res.error)
        screen = await kids_screen(svc, p, now)
    elif op == "pt":
        screen = await pets_screen(svc, p, now)
    elif op == "pe":
        res = await svc.buy_egg(pid, user, now)
        popup = "🥚 Яйцо куплено" if res.ok else res.error
        p = await svc.get_by_id(pid)
        screen = await pets_screen(svc, p, now)
    elif op == "pg":
        res = await svc.collect_pets(pid, user, now)
        popup = f"🎁 +{n(res.info['sparks'])} 🔥" if res.ok else res.error
        events = events + res.events
        p = await svc.get_by_id(pid)
        screen = await pets_screen(svc, p, now)
    elif op == "pc":
        res = await svc.care_pet(pid, user, int(args[0]) if args and args[0].isdigit() else 0, args[1] if len(args) > 1 else "", now)
        popup = f"{res.info['emoji']} настроение {res.info['mood']}" if res.ok else res.error
        screen = await pets_screen(svc, p, now)
    elif op == "pm":
        screen = await premium_screen(bot, p, now)
    elif op == "bb":
        screen = await baby_screen(svc, db, p, now)
    elif op == "bm":
        res = await svc.set_mother(pid, user)
        popup = None if res.ok else res.error
        screen = await baby_screen(svc, db, p, now)
    elif op == "bc":
        res = await svc.care(pid, user, args[0] if args else "", now)
        popup = f"{res.info['emoji']} +{res.info['plus']} здоровья" if res.ok else res.error
        screen = await baby_screen(svc, db, p, now)
    elif op == "ba":
        await cb.answer()
        await cb.message.answer("🚫 Прервать ожидание? Решение необратимо.", reply_markup=kb__rich_ui(
            [[Btn("Да, прервать", cb=f"pr:bay:{pid}", style="danger"), Btn("Отмена", cb=f"pr:bn:{pid}")]]))
        return
    elif op == "bay":
        res = await svc.abort(pid, user, now)
        await cb.answer(None if res.ok else res.error, show_alert=not res.ok)
        if res.ok:
            await cb.message.edit_text("🤝 Ожидание малыша прервано. Берегите себя.")
        return
    elif op == "bn":
        await cb.answer("Отменено")
        await cb.message.delete()
        return
    elif op in ("iy", "in"):
        init = int(args[0]) if args and args[0].isdigit() else 0
        exp = int(args[1]) if len(args) > 1 and args[1].isdigit() else 0
        if user == init:
            await cb.answer("Ответить должна половинка", show_alert=True)
            return
        if now > exp:
            await cb.answer("Предложение устарело", show_alert=True)
            return
        if op == "in":
            await cb.answer()
            await cb.message.edit_text("🌙 Половинка пока не готова. Всё в порядке.")
            return
        if not (await db.get_settings(p["chat_id"]))["pair_intim"]:
            await cb.answer("Близость выключена в беседе", show_alert=True)
            return
        res = await svc.intimacy(pid, init, now)
        if not res.ok:
            await cb.answer(res.error, show_alert=True)
            return
        await cb.answer("💞")
        a, b2 = await m(db, init), await m(db, user)
        text = f"🌙 {a} и {b2} провели ночь вместе · +{res.info['warmth']} ☀️"
        kb = None
        if res.info["pregnant"]:
            text += "\n👶 Тест положительный! Вы ждёте малыша. Кто носит?"
            kb = kb__rich_ui([[Btn("👶 Ношу я", cb=f"pr:bm2:{pid}", style="primary")]])
        await cb.message.edit_text(text, reply_markup=kb)
        for t in await event_lines(db, p, res.events):
            await cb.message.answer(t)
        return
    elif op == "bm2":
        res = await svc.set_mother(pid, user)
        if res.ok:
            await cb.answer("👶")
            await cb.message.edit_text(f"👶 Малыша носит {await m(db, user)}. Заботьтесь друг о друге: <code>пара малыш</code>.")
        else:
            await cb.answer(res.error, show_alert=True)
        return
    elif op == "e":
        screen = await costs_screen(svc, p, now)
    elif op == "l":
        screen = await list_screen(svc, db, p, p["chat_id"], now)
    elif op == "t":
        screen = await top_screen(svc, db, p, p["chat_id"], TOP_KINDS.get(args[0] if args else "", "тепло"), now)
    elif op == "ob":
        res = await svc.toggle_offense(pid, user, now)
        popup = (await say(db, user, "😢 Ты ⟦обиделся|обиделась⟧: действия половинки закрыты") if res.ok and res.info["offended"] else
                 "😊 Обида снята" if res.ok else res.error)
        p = await svc.get_by_id(pid)
        screen = more_screen(p, user)
    elif op == "peace":
        popup = _peace_hint(p, now).replace("<code>", "").replace("</code>", "")
        screen = more_screen(p, user)
    elif op == "end":
        screen = await _end_screen(db, p, partner)
    elif op == "endy":
        ended = await svc.end(pid, "breakup", now, user)
        await cb.answer("💔 Отношения завершены")
        if ended:
            try:
                await cb.message.edit_text(f"💔 {await m(db, user)} и {await m(db, partner)} больше не пара. "
                                           f"Вы были вместе {duration_since(p['created'], now)}.")
            except Exception:
                pass
        return
    else:
        await cb.answer()
        return
    await cb.answer(popup[:190] if popup else None, show_alert=bool(popup and len(popup) > 60))
    await show(cb, screen)
    for t in await event_lines(db, p, events):
        await cb.message.answer(t)


# ---------- фон: содержание, ссора, распад ----------
async def pair_watchdog(bot, db: Database) -> None:
    """Раз в 5 минут досчитывает пары, у которых что-то подошло к сроку, и объявляет ссору, распад и предупреждения."""
    svc = PairService(db)
    while True:
        await asyncio.sleep(300)
        try:
            now = int(time.time())
            for p in await svc.due(now):
                p2, events = await svc.settle(p["id"], now)
                for ev in events:
                    if ev[0] in ("quarrel", "dissolved", "warn", "bill_missed", "arrested", "confiscated", "baby_born", "baby_lost", "child_grown", "pet_hatched"):
                        t = await event_text(db, p, ev)
                        if t:
                            try:
                                await bot.send_message(p["chat_id"], t)
                            except Exception:
                                logging.info("pair: не отправилось в чат %s", p["chat_id"])
        except Exception:
            logging.exception("pair watchdog")



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/quotes.py
# Цитатник: «+цитата» ответом на сообщение — карточка-картинка с аватаркой; «цитата», «цитата 5», «цитата @ник»,
# «цитаты», «цитаты @ник», «-цитата 5». Выключается в настройках → «Команды».
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__quotes = Router(name="quotes")
router__quotes.message.filter(Enabled("quotes_on"))   # группу команд можно выключить в настройках → «Команды»
MAX_QUOTE = 700
SHOW_COOLDOWN = 5          # «цитата» в одном чате — не чаще раза в 5 с
_last__quotes: dict[int, float] = {}

_ADD__quotes = re.compile(r"^\+(?:цитата|цитатка|quote)$", re.IGNORECASE)
_SHOW__quotes = re.compile(r"^цитата(?:\s+(\d{1,7}|@\w+))?$", re.IGNORECASE)
_LIST__quotes = re.compile(r"^цитаты(?:\s+(@\w+))?$", re.IGNORECASE)
_DEL__quotes = re.compile(r"^-цитата\s+(\d{1,7})$", re.IGNORECASE)


def _parse__quotes(text: str | None):
    t = (text or "").strip()
    for kind, rx in (("add", _ADD__quotes), ("show", _SHOW__quotes), ("list", _LIST__quotes), ("del", _DEL__quotes)):
        m = rx.match(t)
        if m:
            return kind, (m.group(1) if m.groups() else None)
    return None


def _author(reply: Message) -> tuple[int, str]:
    """Кого цитируем: у пересланного — исходного автора, у сообщения от имени канала — канал."""
    origin = getattr(reply, "forward_origin", None)
    if origin is not None:
        u = getattr(origin, "sender_user", None)
        if u is not None:
            return u.id, u.full_name
        name = getattr(origin, "sender_user_name", None)
        if name:
            return 0, name
        ch = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
        if ch is not None:
            return ch.id, ch.title or "канал"
    if reply.sender_chat is not None and reply.sender_chat.id != reply.chat.id:
        return reply.sender_chat.id, reply.sender_chat.title or "канал"
    u = reply.from_user
    return (u.id, u.full_name) if u else (0, "аноним")


async def _send_card(message: Message, bot, db: Database, q: dict) -> None:
    caption = f"💬 Цитата №{q['id']}"
    if q.get("card"):                                   # уже рисовали — повторно отправляем тот же файл, без рендера
        try:
            await message.reply_photo(q["card"], caption=caption)
            return
        except Exception:
            await db.quote_set_card(q["id"], None)
    tz = tz_of((await db.get_settings(message.chat.id))["tz"])
    av = await avatar__media(bot, q["author_id"]) if q["author_id"] > 0 else None
    png = await asyncio.to_thread(
        quote_card, q["text"], q["author_name"], q["author_id"], av,
        datetime__i1.fromtimestamp(q["ts"], tz).strftime("%d.%m.%Y %H:%M"), message.chat.title or "", q["id"])
    sent = await message.reply_photo(BufferedInputFile(png, f"quote{q['id']}.jpg"), caption=caption)
    if sent and getattr(sent, "photo", None):
        await db.quote_set_card(q["id"], sent.photo[-1].file_id)


@router__quotes.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: _parse__quotes(t) is not None))
async def quotes_cmd(message: Message, bot, db: Database) -> None:
    if message.from_user is None:
        return
    kind, arg = _parse__quotes(message.text)
    chat, me, now = message.chat.id, message.from_user.id, int(time.time())

    if kind == "add":
        reply = real_reply(message)
        if reply is None:
            await tell(message, "⚠️ Ответьте <code>+цитата</code> на сообщение, которое нужно сохранить.")
            return
        text = (reply.text or reply.caption or "").strip()
        if not text:
            await tell(message, "⚠️ В этом сообщении нет текста — цитировать нечего.")
            return
        if len(text) > MAX_QUOTE:
            text = text[:MAX_QUOTE - 1].rstrip() + "…"
        aid, aname = _author(reply)
        qid = await db.quote_add(chat, aid, aname, text, int(reply.date.timestamp()), me, now, reply.message_id)
        if qid is None:
            old = await db.quote_by_message(chat, reply.message_id)
            await message.reply(f"Это уже в цитатнике: №{old['id']}." if old else "Это уже в цитатнике.")
            return
        await _send_card(message, bot, db, await db.quote_get(chat, qid))
        return

    if kind == "show":
        if time.time() - _last__quotes.get(chat, 0) < SHOW_COOLDOWN:
            return
        _last__quotes[chat] = time.time()
        if arg and arg.isdigit():
            q = await db.quote_get(chat, int(arg))
            if q is None:
                await tell(message, f"❌ Цитаты №{arg} нет.")
                return
        else:
            uid = await db.find_user(arg) if arg else None
            if arg and uid is None:
                await tell(message, "❌ Не нашёл такого пользователя.")
                return
            q = await db.quote_random(chat, uid)
            if q is None:
                await message.reply("ℹ️ Цитатник пуст. Ответьте <code>+цитата</code> на чьё-нибудь сообщение 😏")
                return
        await _send_card(message, bot, db, q)
        return

    if kind == "list":
        uid = await db.find_user(arg) if arg else None
        if arg and uid is None:
            await tell(message, "❌ Не знаю такого пользователя.")
            return
        if uid is None:
            total, top = await db.quote_stats(chat)
            if not total:
                await message.reply("ℹ️ Цитатник пуст. Ответьте <code>+цитата</code> на чьё-нибудь сообщение 😏")
                return
            lines = [f"{i}. {listed(a, (await db.user_name(a)) or n or f'id{a}') if a > 0 else html.escape(n or '?')} — {c}"
                     for i, (a, n, c) in enumerate(top, 1)]
            await message.reply(f"💬 <b>Цитатник</b> · {total}\nЧаще всех цитируют:\n" + "\n".join(lines)
                                + "\n<i>Случайная — <code>цитата</code>, по номеру — <code>цитата 5</code></i>")
            return
        rows = await db.quote_list(chat, uid)
        if not rows:
            await message.reply("ℹ️ У этого человека цитат пока нет.")
            return
        lines = [f"№{r['id']}: {html.escape(fit(' '.join(r['text'].split()), font(20), 520))}" for r in rows]
        await message.reply("💬 <b>Цитаты</b>\n" + "\n".join(lines))
        return

    # del: удалить может тот, кто добавил, автор цитаты или модератор
    q = await db.quote_get(chat, int(arg))
    if q is None:
        await tell(message, f"❌ Цитаты №{arg} нет.")
        return
    if me not in (q["added_by"], q["author_id"]) and await effective_rank(bot, db, chat, me) < 1:
        await tell(message, "⚠️ Удалить цитату может тот, кто её добавил, её автор или модератор.")
        return
    await db.quote_delete(chat, q["id"])
    await message.reply(f"🗑 Цитата №{q['id']} удалена.")



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/rp.py
# РП-команды: «обнять» ответом на сообщение или «обнять @ник».
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__rp = Router(name="rp")
COOLDOWN__rp = 2          # пауза между РП-действиями одного человека, сек
# Список самих действий и их текстов — bot/rp_data.py (там же как добавить новое действие)
_last__rp: dict[tuple[int, int], float] = {}


def _in_group(m: Message) -> bool:
    return m.chat.type in ("group", "supergroup")


@router__rp.message(F.text.func(lambda t: parse_rp(t) is not None))
# РП-ХЕНДЛЕР: «обнять @ник» / ответом. Порядок проверок: группа и настройка rp_on → цель → 18+ → пол → кулдаун → ответ с гифкой.
# Тексты и список действий НЕ здесь, а в rp_data.py.
async def rp_cmd(message: Message, bot, db: Database, http=None) -> None:
    if not _in_group(message) or not (await db.get_settings(message.chat.id))["rp_on"]:
        return
    action, token = parse_rp(message.text)
    reply = real_reply(message)
    target = await resolve_user(db, token, reply)
    if target is None:
        return  # нет цели — это не команда, а обычная фраза
    tid, tname = target
    if reply is not None and token is None and reply.from_user and reply.from_user.is_bot and \
            reply.from_user.id != (await bot.me()).id:
        return
    if is_adult(action) and not (await db.get_settings(message.chat.id)).get("rp_adult", 0):
        await tell(message, "🔞 Флирт и мат выключены в этой беседе. Включить могут админы: <code>+рп18</code>.")
        return
    if not await ensure(message, db):               # пол — один раз, дальше помним
        return
    key = (message.chat.id, message.from_user.id)
    if time.time() - _last__rp.get(key, 0) < COOLDOWN__rp:
        return
    _last__rp[key] = time.time()
    if tid == message.from_user.id:
        await message.reply("🙃 Сам себя? Выберите другого человека.")
        return
    if tid == (await bot.me()).id:
        await message.reply("🤖 Спасибо, но я всего лишь бот.")
        return
    ga = await get(db, message.from_user.id)
    text = f"{action.emoji} " + gz(action.text, ga).format(
        a=mention__targets(message.from_user.id, message.from_user.full_name), b=mention__targets(tid, tname))
    s = await db.get_settings(message.chat.id)
    reply_to = reply.message_id if (reply is not None and token is None) else None
    if await reply_gif(bot, http, message, text, RP_MAP.get(action.phrase), ga,
                            await get(db, tid), reply_to=reply_to, enabled=bool(s.get("rp_gifs", 1))):
        return
    if reply_to:
        await message.answer(text, reply_to_message_id=reply_to)
    else:
        await message.answer(text)


@router__rp.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("мой пол", "сменить пол", "выбрать пол")))
async def gender_change(message: Message, db: Database) -> None:
    u = message.from_user
    if u is None:
        return
    await message.reply("Кто ты? Выбор можно менять.", reply_markup=kb__gender(u.id))


@router__rp.callback_query(F.data.startswith("gd:"))
async def gender_pick(cb: CallbackQuery, db: Database) -> None:
    await on_pick(cb, db)


@router__rp.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("рп", "рп команды", "рп список", "рп помощь")))
async def rp_list(message: Message, db: Database) -> None:
    adult = bool((await db.get_settings(message.chat.id)).get("rp_adult", 0)) if message.chat.type != "private" else False
    await message.answer(catalog(adult))


@router__rp.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("+рп18", "-рп18")))
async def rp_adult_toggle(message: Message, bot, db: Database) -> None:
    if not _in_group(message):
        return
    if not await is_admin__mod_service(bot, message.chat.id, message.from_user.id):
        await tell(message, "⚠️ Включать флирт и мат в РП могут только админы.")
        return
    on = message.text.strip().startswith("+")
    await db.set_setting(message.chat.id, "rp_adult", 1 if on else 0)
    await message.reply("🔞 Флирт и мат в РП включены: только для взрослых участников беседы." if on else "🔞 Флирт и мат в РП выключены.")


@router__rp.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("+рп", "-рп")))
async def rp_toggle(message: Message, bot, db: Database) -> None:
    if not _in_group(message):
        return
    if not await is_admin__mod_service(bot, message.chat.id, message.from_user.id):
        await tell(message, "⚠️ Включать и выключать РП могут только админы.")
        return
    on = message.text.strip().startswith("+")
    await db.set_setting(message.chat.id, "rp_on", 1 if on else 0)
    await message.reply("🎭 РП-команды и семья включены." if on else "🎭 РП-команды и семья выключены.")



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/services.py
# Сервисы без префикса: «калк 2+2», «курс usd», «крипто btc», «вики Пушкин», «факт», «маршрут А — Б», «гороскоп лев».
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__handlers_services = Router(name="services")
router__handlers_services.message.filter(Enabled("svc_on"))

_PATTERNS__handlers_services = [
    ("calc", r"^(?:калк|реши|посчитай|calc)\s+(.+)$"),
    ("rate", r"^(?:курс|конв)\s+(.+)$"),
    ("crypto", r"^(?:крипто|крипта)\s+(.+)$"),
    ("wiki", r"^(?:вики|wiki)\s+(.+)$"),
    ("fact", r"^(?:факт|факт дня)$"),
    ("route", r"^(?:маршрут|расстояние|дистанция)\s+(.+)$"),
    ("horo", r"^гороскоп(?:\s+(.+))?$"),
]
_COMPILED__handlers_services = [(k, re.compile(p, re.IGNORECASE | re.DOTALL)) for k, p in _PATTERNS__handlers_services]
COOLDOWN__handlers_services = 3
_last__handlers_services: dict[int, float] = {}


def parse__handlers_services(text: str | None):
    t = (text or "").strip()
    if not t or len(t) > 200:
        return None
    for kind, rx in _COMPILED__handlers_services:
        m = rx.match(t)
        if m:
            return kind, (m.group(1) or "").strip() if m.groups() else ""
    return None


@router__handlers_services.message(F.text.func(lambda t: parse__handlers_services(t) is not None))
async def on_service(message: Message, http=None, ai=None) -> None:
    if message.from_user is None:
        return
    now = time.time()
    if now - _last__handlers_services.get(message.from_user.id, 0) < COOLDOWN__handlers_services:
        return
    if len(_last__handlers_services) > 5000:
        _last__handlers_services.clear()
    _last__handlers_services[message.from_user.id] = now
    kind, arg = parse__handlers_services(message.text)

    if kind == "calc":
        try:
            await message.reply(f"🧮 <code>{html.escape(arg)}</code> = <b>{html.escape(calc(arg))}</b>")
        except CalcError as e:
            await tell(message, f"⚠️ {html.escape(str(e))}. Пример: <code>калк (2+3)*4</code>")
        return
    if kind == "horo":
        sign = parse_sign(arg)
        if sign is None:
            await tell(message, "⚠️ Укажите знак или дату: <code>гороскоп лев</code> или <code>гороскоп 15.08</code>")
            return
        if ai is None or not getattr(ai, "has_river", False):
            await message.reply("🔮 Гороскоп сочиняет ИИ, а он у меня сейчас не подключён.")
            return
        try:
            text = await ai.ask(f"Сегодня {date.today():%d.%m.%Y}. Напиши короткий (3–4 предложения) весёлый гороскоп на сегодня "
                                f"для знака «{sign}». Без вступлений и без пометки, что это шутка.",
                                max_tokens=300)
        except Exception:
            text = ""
        await message.reply(f"🔮 <b>{sign}</b>\n{html.escape(text.strip())}" if text and text.strip()
                            else "🔮 Звёзды сейчас молчат — попробуйте позже.")
        return
    if http is None:
        await tell(message, "⚠️ Сервис сейчас недоступен.")
        return

    if kind == "rate":
        parsed = parse_money(arg)
        if parsed is None:
            await tell(message, "⚠️ Пример: <code>курс 100 usd eur</code>, <code>курс евро</code>")
            return
        amount, src, dst = parsed
        rates = await fetch_rates(http)
        res = convert(rates, amount, src, dst) if rates else None
        await message.reply(f"💱 {fmt_num(amount)} {src} = <b>{fmt_num(res)} {dst}</b>\n<i>курс ЦБ РФ</i>" if res is not None
                            else "💱 Не нашёл такую валюту или сервис курсов недоступен.")
    elif kind == "crypto":
        parsed = parse_crypto(arg)
        if parsed is None:
            await tell(message, "⚠️ Пример: <code>крипто btc</code>, <code>крипто 2 eth rub</code> "
                                   f"(монеты: {', '.join(k for k in COINS if k.isascii())})")
            return
        amount, coin, fiat = parsed
        price = await fetch_crypto(http, coin, fiat)
        await message.reply(f"🪙 {fmt_num(amount)} {coin.upper()} = <b>{fmt_num(price * amount)} {fiat.upper()}</b>" if price
                            else "🪙 Сервис курсов крипты сейчас недоступен.")
    elif kind == "wiki":
        got = await wiki(http, arg)
        if got is None:
            await message.reply("📚 Ничего не нашёл.")
        else:
            title, extract, url = got
            await message.reply(f"📚 <b>{html.escape(title)}</b>\n{html.escape(extract)}" + (f'\n<a href="{html.escape(url)}">Читать в Википедии</a>' if url else ""),
                                disable_web_page_preview=True)
    elif kind == "fact":
        fact = await fact_of_day(http)
        await message.reply(f"📅 <b>В этот день</b>\n{html.escape(fact)}" if fact else "📅 Факт дня сейчас недоступен.")
    elif kind == "route":
        pair = parse_route(arg)
        if pair is None:
            await tell(message, "⚠️ Пример: <code>маршрут Москва — Казань</code>")
            return
        r = await route(http, *pair)
        if r is None:
            await message.reply("🗺 Не нашёл такие города или сервис карт недоступен.")
            return
        lines = [f"🗺 <b>{html.escape(r['from'])} → {html.escape(r['to'])}</b>", f"По прямой: {fmt_num(r['air_km'])} км"]
        if r["road_km"] is not None:
            h = r["hours"]
            lines.append(f"По дороге: {fmt_num(r['road_km'])} км, ~{int(h)} ч {int(h % 1 * 60)} мин на машине")
        await message.reply("\n".join(lines))



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/handlers/votes.py
# Голосование за временный мут нарушителя: «гб @ник» / «гб» ответом.
# ════════════════════════════════════════════════════════════════════════════════════════════════════
router__votes = Router(name="votes")
VOTES_NEEDED = 5
VOTER_MIN_MESSAGES = 10
VOTE_TTL = 600
MUTE_SECONDS__votes = 86400
_RE__votes = re.compile(r"^гб(?:\s+(@\w+|\d{5,}|стоп))?$", re.IGNORECASE)
_votes: dict[str, dict] = {}


def _kb__votes(vid: str, n: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        B(text=f"🗳 За мут на сутки ({n}/{VOTES_NEEDED})", callback_data=f"vote:{vid}:y")]])


@router__votes.message(F.text.func(lambda t: bool(t) and _RE__votes.match(t.strip()) is not None))
async def start_vote(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup"):
        return
    chat, me = message.chat.id, message.from_user.id
    token = _RE__votes.match(message.text.strip()).group(1)
    now = time.time()
    for k in [k for k, v in _votes.items() if v["expires"] < now]:
        _votes.pop(k, None)
    if token == "стоп":
        if await effective_rank(bot, db, chat, me) >= 1:
            for k in [k for k, v in _votes.items() if v["chat"] == chat]:
                _votes.pop(k)
            await tell(message, "⚠️ Голосования в этом чате остановлены.")
        return
    target = await resolve_user(db, token, real_reply(message))
    if target is None:
        return  # «гб» без цели — просто буквы
    tid, tname = target
    if await db.user_total(chat, me, None) < VOTER_MIN_MESSAGES:
        await tell(message, f"⚠️ Начинать голосование можно после {VOTER_MIN_MESSAGES} сообщений в чате.")
        return
    if tid == me or tid == (await bot.me()).id:
        await tell(message, "⚠️ Нужен другой человек.")
        return
    try:
        tm = await get_member(bot, chat, tid)
    except Exception:
        await tell(message, "❌ Не нашёл такого участника в чате.")
        return
    if tm.status in ("left", "kicked") or (tm.status == "restricted" and not getattr(tm, "is_member", False)):
        await tell(message, "⚠️ Этот человек больше не участвует в чате.")
        return
    if tm.status in ("administrator", "creator"):
        await tell(message, "⚠️ Администраторов голосованием наказывать нельзя.")
        return
    if await db.get_rank(chat, tid):
        await tell(message, "⚠️ Модераторов голосованием наказывать нельзя.")
        return
    if any(v["chat"] == chat and v["target"] == tid for v in _votes.values()):
        await tell(message, "⚠️ Голосование против этого человека уже идёт.")
        return
    vid = uuid.uuid4().hex[:8]
    _votes[vid] = {"chat": chat, "target": tid, "tname": tname, "voters": {me}, "expires": now + VOTE_TTL}
    try:
        await message.answer(
            f"⚖️ Голосование: {mention__targets(tid, tname)} — мут на сутки?\nНужно {VOTES_NEEDED} голосов за 10 минут. "
            "Голосуют участники, написавшие в чате не меньше 10 сообщений.", reply_markup=_kb__votes(vid, 1))
    except BaseException:
        _votes.pop(vid, None)
        raise


@router__votes.callback_query(F.data.startswith("vote:"))
async def vote_cb(cb: CallbackQuery, bot, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or parts[2] != "y":
        await cb.answer()
        return
    _, vid, _op = parts
    v = _votes.get(vid)
    if v is None or cb.message is None or v["chat"] != cb.message.chat.id or v["expires"] < time.time():
        _votes.pop(vid, None)
        await cb.answer("Голосование закончено.", show_alert=True)
        return
    uid = cb.from_user.id
    if uid == v["target"]:
        await cb.answer("Против себя голосовать нельзя.", show_alert=True)
        return
    if uid in v["voters"]:
        await cb.answer("Вы уже проголосовали.", show_alert=True)
        return
    try:
        member = await bot.get_chat_member(v["chat"], uid)
        if member.status in ("left", "kicked") or (member.status == "restricted" and not getattr(member, "is_member", False)):
            await cb.answer("Голосовать могут только участники чата.", show_alert=True)
            return
    except Exception:
        await cb.answer("Не удалось проверить участие в чате. Попробуйте ещё раз.", show_alert=True)
        return
    if await db.user_total(v["chat"], uid, None) < VOTER_MIN_MESSAGES:
        await cb.answer(f"Голосовать могут те, у кого от {VOTER_MIN_MESSAGES} сообщений в чате.", show_alert=True)
        return
    v["voters"].add(uid)
    if len(v["voters"]) < VOTES_NEEDED:
        await cb.message.edit_reply_markup(reply_markup=_kb__votes(vid, len(v["voters"])))
        await cb.answer("Голос учтён.")
        return
    if _votes.pop(vid, None) is None:  # второе одновременное нажатие на пороге не должно мутить повторно
        await cb.answer()
        return
    now = int(time.time())
    try:
        target = await bot.get_chat_member(v["chat"], v["target"])
        if (target.status in ("administrator", "creator", "left", "kicked") or
                (target.status == "restricted" and not getattr(target, "is_member", False)) or
                await db.get_rank(v["chat"], v["target"])):
            await cb.message.edit_text("⚖️ Голосование закрыто: участник вышел из чата или получил полномочия.")
            await cb.answer()
            return
        await apply__mod_service(bot, db, ModCommand("мут", None, datetime__i2.timedelta(seconds=MUTE_SECONDS__votes),
                                           "решение голосования"), v["chat"], (await bot.me()).id, v["target"], now)
        await cb.message.edit_text(f"⚖️ Голосование завершено: {mention__targets(v['target'], v['tname'])} в муте на сутки.")
    except Exception as e:
        await cb.message.edit_text(f"⚖️ Голосов достаточно, но мут не получился: {html.escape(str(e))}")
    await cb.answer()
