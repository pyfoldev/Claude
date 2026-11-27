"""Дом пары: каталог, комнаты, копилка, еженедельный счёт, долг, арест, конфискация. Чистые правила без БД."""
from __future__ import annotations

from dataclasses import dataclass

from bot.pair.data import norm

WEEK = 7 * 86400
BILL_PCT = 3               # счёт в неделю — 3% вложенного в дом
PENALTY_PCT = 10           # пеня на недоплату
ARREST_AFTER = 2           # пропущенных счетов до ареста
CONFISCATE_AFTER = 4       # …до конфискации
SELL_BACK_PCT = 50         # конфискация возвращает половину стоимости
ROOM_MAX = 5


@dataclass(frozen=True)
class House:
    key: str
    emoji: str
    price: int
    slots: int
    hoard_cap: int


@dataclass(frozen=True)
class Room:
    key: str
    emoji: str
    base: int


HOUSES = [House(*r) for r in [
    ("шалаш", "🏚", 300, 1, 2_000), ("домик", "🏠", 1_500, 2, 8_000), ("коттедж", "🏡", 5_000, 3, 25_000),
    ("дача", "🌱", 12_000, 4, 60_000), ("таунхаус", "🏢", 30_000, 5, 150_000), ("усадьба", "🏰", 70_000, 6, 350_000),
    ("особняк", "💎", 150_000, 8, 800_000), ("вилла", "🏖", 400_000, 10, 2_000_000), ("замок", "👑", 1_000_000, 12, 6_000_000),
]]
ROOMS = [Room(*r) for r in [
    ("спальня", "🛌", 200), ("кухня", "🍵", 250), ("гостиная", "🛋", 300), ("сад", "🌷", 350), ("библиотека", "📚", 400),
    ("камин", "🔥", 450), ("мастерская", "🛠", 500), ("терраса", "☀", 600), ("оранжерея", "🪴", 700), ("кинозал", "🎥", 900),
    ("бассейн", "🏖", 1200), ("обсерватория", "🔮", 1500),
]]
RANKS = [(0, "Новосёлы"), (500, "Хозяева"), (3_000, "Домовитые"), (10_000, "Уютная гавань"), (30_000, "Хлебосольные"),
         (80_000, "Гордость улицы"), (200_000, "Семейная усадьба"), (600_000, "Знатный род"), (1_500_000, "Летописный дом"),
         (4_000_000, "Легенда округи")]
_H = {norm(h.key): h for h in HOUSES}
_R = {norm(r.key): r for r in ROOMS}


def find_house(word: str) -> House | None:
    return _H.get(norm(word))


def find_room(word: str) -> Room | None:
    return _R.get(norm(word))


def room_cost(room: Room, level: int) -> int:
    """Цена перехода на уровень level (1..5)."""
    return room.base * level * level


def invested(house: House, rooms: dict[str, int]) -> int:
    total = house.price
    for k, lvl in rooms.items():
        r = find_room(k)
        if r:
            total += sum(room_cost(r, i) for i in range(1, lvl + 1))
    return total


def prestige(house: House, rooms: dict[str, int]) -> int:
    return invested(house, rooms)


def rank_name(points: int) -> str:
    name = RANKS[0][1]
    for need, title in RANKS:
        if points >= need:
            name = title
    return name


def bill_amount(house: House, rooms: dict[str, int]) -> int:
    return max(5, invested(house, rooms) * BILL_PCT // 100)
