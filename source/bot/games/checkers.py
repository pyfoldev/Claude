"""Русские шашки: обязательное взятие, взятие назад, дамки ходят и бьют через всю диагональ, серия взятий одной шашкой.

Доска — список из 64 клеток (индекс = ряд*8 + столбец, ряд 0 — сверху). Чёрные стоят сверху и ходят вниз,
белые снизу и ходят вверх. Фигуры: w, W (дамка), b, B (дамка), пробел — пусто.
Упрощение: взятая шашка снимается сразу, а не в конце хода — на практике разница видна лишь в редких позициях."""
from __future__ import annotations

DIRS = ((-1, -1), (-1, 1), (1, -1), (1, 1))
NO_PROGRESS_LIMIT = 60          # полуходов без взятия и без хода простой шашкой — ничья


def new_board() -> list[str]:
    b = [" "] * 64
    for r in range(8):
        for c in range(8):
            if (r + c) % 2 == 1:
                if r < 3:
                    b[r * 8 + c] = "b"
                elif r > 4:
                    b[r * 8 + c] = "w"
    return b


def side_of(p: str) -> str | None:
    return None if p == " " else p.lower()


def _inside(r: int, c: int) -> bool:
    return 0 <= r < 8 and 0 <= c < 8


def captures_from(board: list[str], pos: int) -> list[tuple[int, int]]:
    """Все взятия фигуры с клетки pos: [(куда встать, номер клетки со взятой фигурой)]."""
    p = board[pos]
    if p == " ":
        return []
    me, king = side_of(p), p.isupper()
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
        if victim == " " or side_of(victim) == me:
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
    me, king = side_of(p), p.isupper()
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


def legal_moves(board: list[str], side: str, lock: int | None = None) -> dict[int, list[tuple[int, int | None]]]:
    """{откуда: [(куда, взятая клетка или None)]}. Есть взятие — разрешены только взятия; lock — серия одной шашкой."""
    caps: dict[int, list] = {}
    for pos, p in enumerate(board):
        if side_of(p) == side and (lock is None or lock == pos):
            c = captures_from(board, pos)
            if c:
                caps[pos] = c
    if caps or lock is not None:
        return caps
    quiet = {}
    for pos, p in enumerate(board):
        if side_of(p) == side:
            m = _simple_moves(board, pos)
            if m:
                quiet[pos] = [(to, None) for to in m]
    return quiet


class IllegalMove(ValueError):
    pass


def apply_move(board: list[str], side: str, src: int, dst: int, lock: int | None = None) -> dict:
    """Ход одной шашки. Меняет board. Возвращает {'captured': bool, 'lock': int|None (серия продолжается),
    'promoted': bool, 'quiet_man': bool}. Исключение IllegalMove — ход запрещён."""
    options = legal_moves(board, side, lock).get(src, [])
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
    return sum(1 for p in board if side_of(p) == side)


def result(board: list[str], to_move: str, lock: int | None, quiet_plies: int) -> str | None:
    """'w' / 'b' — победитель, 'draw' — ничья, None — игра идёт."""
    if not legal_moves(board, to_move, lock):
        return "b" if to_move == "w" else "w"
    if quiet_plies >= NO_PROGRESS_LIMIT:
        return "draw"
    return None
