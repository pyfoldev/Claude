"""Морской бой 8×8 с автоматической расстановкой: корабли не касаются друг друга даже углами.

Флот: 4, 3, 2, 2, 1, 1, 1 клеток. Игрок стреляет по полю соперника; попал — стреляет снова."""
from __future__ import annotations

import random

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
