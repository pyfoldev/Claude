"""Огород: чистая логика (без Telegram и БД). Состояние игрока — обычный dict, его хранит Database."""
from __future__ import annotations

from dataclasses import dataclass

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


def render(g: dict, now: int) -> str:
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
