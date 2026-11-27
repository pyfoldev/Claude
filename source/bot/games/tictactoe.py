LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def new_board() -> list[str]:
    return [" "] * 9


def move(board: list[str], idx: int, mark: str) -> bool:
    if not 0 <= idx < 9 or board[idx] != " ":
        return False
    board[idx] = mark
    return True


def winner(board: list[str]) -> str | None:
    for a, b, c in LINES:
        if board[a] != " " and board[a] == board[b] == board[c]:
            return board[a]
    return "draw" if " " not in board else None
