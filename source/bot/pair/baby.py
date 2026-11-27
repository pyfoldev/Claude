"""Ожидание малыша: правила (без БД). Всё мягко и без откровенного: «ночь вместе», «тест», «малыш»."""
from __future__ import annotations

WEEK_SEC = 12 * 3600              # одна «неделя» ожидания = 12 часов, всего 40 недель (20 суток)
WEEKS = 40
ABORT_UNTIL_WEEK = 20
CHANCE_OPEN = 25                  # % при выключенной защите
CHANCE_PROTECTED = 2              # % при включённой защите
TWINS_PCT = 3
INTIM_COOLDOWN = 12 * 3600
INTIM_MIN_LEVEL = 2
INTIM_WARMTH = 20
HEALTH_DECAY_SEC = 6 * 3600       # −1 здоровье за каждые 6 часов без заботы
BIRTH_WARMTH = 150
CARE = {                           # ключ: (эмодзи, +здоровье, кулдаун сек, подпись)
    "врач": ("🧴", 25, 8 * 3600, "визит к врачу"),
    "отдых": ("🛌", 10, 3 * 3600, "отдых"),
    "витамины": ("💊", 10, 3 * 3600, "витамины"),
}
NAMES = ["Тима", "Мирон", "Ясен", "Лада", "Веся", "Ника", "Арти", "Зоя", "Лёва", "Рада", "Тоша", "Мила", "Фима", "Дара", "Гоша",
         "Эля", "Саша", "Женя", "Валя", "Шура"]


def week(started: int, now: int) -> int:
    return max(0, (now - started) // WEEK_SEC)


def trimester(w: int) -> int:
    return 1 if w < 14 else 2 if w < 28 else 3


def decayed(health: int, health_at: int, now: int) -> tuple[int, int]:
    """(здоровье, новая отметка времени) после лениво посчитанного спада."""
    steps = max(0, (now - health_at) // HEALTH_DECAY_SEC)
    return max(0, health - steps), health_at + steps * HEALTH_DECAY_SEC


def chance(protected: bool) -> int:
    return CHANCE_PROTECTED if protected else CHANCE_OPEN
