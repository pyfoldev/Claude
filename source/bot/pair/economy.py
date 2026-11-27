"""Чистая экономика пары (без БД и Telegram): содержание, уровни, награды, тепло. Всё проверяется тестами по таблицам.

Две валюты: «искры» 🔥 — общий кошелёк (тратятся на содержание, приходят от действий), «тепло» ☀️ — только копится и даёт уровень.
Числа — стартовые ориентиры для баланса; менять их можно здесь и в data.py, не трогая логику."""
from __future__ import annotations

MSK = 3 * 3600                      # сутки считаются по Москве
DAY = 86400

START_SPARKS = 100                  # искр у новой пары
UNISON_WINDOW = 15 * 60             # «в унисон»: половинка действовала не раньше 15 минут назад
UNISON_BONUS = 0.20
STREAK_STEP, STREAK_CAP = 0.02, 0.30
DAILY_ACTIONS_BEFORE_TIRED = 12     # после этого награда вдвое меньше до полуночи
DAY_TOGETHER_WARMTH = 60
RP_WARMTH, RP_WARMTH_PER_DAY = 5, 10
QUARREL_HOURS = 24
SLEEP_AFTER = 7 * DAY               # неделя без дел — пара «спит» (не в списках и топах)
KID_UPKEEP = 0.10
UPKEEP_CAP_SHARE = 0.03             # за сутки берём не больше 3% кошелька…
UPKEEP_MIN = 15                     # …но не меньше 15 искр
LEVEL_GIFT_DAYS = 2                 # за новый уровень — два суточных содержания нового уровня
MARRIAGE_MIN_LEVEL = 3

# содержание в сутки по уровням 1–30 (дальше — как на 30-м)
UPKEEP = [15, 30, 45, 60, 80, 120, 170, 230, 300, 380, 480, 600, 740, 900, 1100, 1350, 1650, 2000, 2400, 2900,
          3500, 4200, 5000, 6000, 7200, 8600, 10200, 12000, 14500, 18000]


def day_index(now: int) -> int:
    """Номер суток по Москве."""
    return (int(now) + MSK) // DAY


def upkeep_base(level: int) -> int:
    return UPKEEP[min(max(level, 1), len(UPKEEP)) - 1]


def upkeep_amount(level: int, kids: int, sparks: int) -> int:
    """Сколько спишется за сутки: база уровня + 10% за ребёнка, но не больше 3% кошелька и не меньше 15 искр."""
    total = int(round(upkeep_base(level) * (1 + KID_UPKEEP * max(kids, 0))))
    return max(UPKEEP_MIN, min(total, int(max(sparks, 0) * UPKEEP_CAP_SHARE)))


def level_step(n: int) -> int:
    """Тепла с уровня n на уровень n+1: 100·n^1,5 с округлением до десятков (280, 520, 800, 1120…)."""
    return int(round(100 * n ** 1.5 / 10.0)) * 10


def threshold(level: int) -> int:
    """Сколько тепла нужно, чтобы быть на уровне level (1 уровень — 0)."""
    return sum(level_step(n) for n in range(1, max(level, 1)))


def level_for(warmth: int) -> int:
    lvl, need = 1, level_step(1)
    left = max(warmth, 0)
    while left >= need:
        left -= need
        lvl += 1
        need = level_step(lvl)
    return lvl


def streak_bonus(streak: int) -> float:
    return min(max(streak, 0) * STREAK_STEP, STREAK_CAP)


def action_reward(base_sparks: int, cd_minutes: int, *, streak: int, unison: bool, tired: bool) -> tuple[int, int]:
    """(искры, тепло) за действие. Тепло — минуты отката действия + бонусы серии и унисона; усталость делит обе награды пополам.
    Искры серия и унисон не меняют: они растят только тепло, то есть уровень."""
    sparks = base_sparks // 2 if tired else base_sparks
    warmth = cd_minutes // 2 if tired else cd_minutes
    bonus = streak_bonus(streak) + (UNISON_BONUS if unison else 0.0)
    return max(sparks, 1), max(int(round(warmth * (1 + bonus))), 1)


def level_gift(new_level: int) -> int:
    return LEVEL_GIFT_DAYS * upkeep_base(new_level)


def fmt_duration(seconds: int) -> str:
    seconds = max(int(seconds), 0)
    d, rem = divmod(seconds, DAY)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} д. {h} ч." if h else f"{d} д."
    if h:
        return f"{h} ч. {m} мин." if m else f"{h} ч."
    return f"{max(m, 1)} мин." if seconds >= 60 else f"{seconds} сек."
