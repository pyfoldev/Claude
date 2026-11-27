"""Питомцы пары: яйцо → вылупление → забота → ежедневный приработок. Правила без БД."""
from __future__ import annotations

EGG_PRICE = 250
HATCH_SEC = 24 * 3600
MAX_PETS = 3
MOOD_DECAY_SEC = 4 * 3600
MIN_MOOD_INCOME = 50
XP_PER_LEVEL = 10
MAX_LEVEL = 10
RARITIES = [("обычный", 70, 20), ("редкий", 22, 50), ("эпический", 7, 120), ("легендарный", 1, 300)]   # название, шанс %, доход
SPECIES = {
    "обычный": [("котёнок", "🐱"), ("щенок", "🐶"), ("хомяк", "🐹"), ("кролик", "🐰"), ("утёнок", "🐥")],
    "редкий": [("лисёнок", "😼"), ("енот", "🐻"), ("панда", "🐸"), ("сова", "🐦")],
    "эпический": [("единорог", "🦄"), ("дракончик", "💥"), ("феникс", "🐦‍🔥")],
    "легендарный": [("небесный кит", "🐋"), ("звёздный лис", "🌟")],
}
CARE = {"покормить": ("🍲", "fed_at", 6 * 3600, 25, 1), "поиграть": ("🎮", "play_at", 3 * 3600, 15, 1)}


def roll(rng) -> tuple[str, str, str]:
    """(вид, эмодзи, редкость)."""
    x = rng.randrange(100)
    acc = 0
    for name, chance, _ in RARITIES:
        acc += chance
        if x < acc:
            break
    sp, emoji = rng.choice(SPECIES[name])
    return sp, emoji, name


def emoji_of(species: str) -> str:
    for items in SPECIES.values():
        for s, e in items:
            if s == species:
                return e
    return "🐾"


def level(xp: int) -> int:
    return min(MAX_LEVEL, 1 + xp // XP_PER_LEVEL)


def income(rarity: str, xp: int) -> int:
    base = next(i for n, _, i in RARITIES if n == rarity)
    return int(base * (1 + 0.1 * (level(xp) - 1)))


def mood_now(mood: int, mood_at: int, now: int) -> tuple[int, int]:
    steps = max(0, (now - mood_at) // MOOD_DECAY_SEC)
    return max(0, mood - steps), mood_at + steps * MOOD_DECAY_SEC
