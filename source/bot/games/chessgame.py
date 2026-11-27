"""Шахматы: полные правила (рокировка, взятие на проходе, превращение пешки, мат, пат, ничьи).

Позиция хранится строкой из 64 символов (ряд 0 — восьмая горизонталь), так её легко класть в JSON.
Превращение пешки — всегда в ферзя (кнопка выбора фигуры сильно усложнила бы доску в чате)."""
from __future__ import annotations

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


def legal_moves(s: State) -> list[tuple[int, int, str]]:
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
    if not legal_moves(s):
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
    return sum(perft(make_move(s, m), depth - 1) for m in legal_moves(s))
