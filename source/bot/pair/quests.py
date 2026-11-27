"""Задания пары (2 суточных + 1 недельное) и сезон (10 ступеней в месяц). Прогресс идёт от действий, РП и «дней вместе»."""
from __future__ import annotations

import datetime

from bot.pair import economy as eco

# вид: (текст с {n}, множитель награды)
KINDS = {
    "act": ("Сделайте {n} действий пары (на двоих)", 1.0),
    "rp": ("Обнимите, поцелуйте и приласкайте друг друга {n} раз", 0.8),
    "together": ("Проведите {n} дн. вместе: оба хотя бы раз за день совершили действие", 1.6),
}
DAILY_POOL = ["act", "rp"]
WEEKLY = "together"
SEASON_STEPS = 10
STEP_POINTS = 6
POINTS = {"d": 1, "w": 3}


def period(scope: str, now: int) -> int:
    d = eco.day_index(now)
    return d if scope == "d" else (d + 3) // 7           # неделя с понедельника (эпоха — четверг)


def month_key(now: int) -> int:
    t = datetime.datetime.fromtimestamp(now + eco.MSK, datetime.UTC)
    return t.year * 100 + t.month


def goal_for(kind: str, scope: str, level: int) -> int:
    if kind == "act":
        return 4 + level // 4 + (6 if scope == "w" else 0)
    if kind == "rp":
        return 3 + level // 6
    return 4 if scope == "w" else 1


def reward_for(kind: str, scope: str, level: int) -> tuple[int, int]:
    mult = KINDS[kind][1] * (3.5 if scope == "w" else 1.0)
    sparks = max(20, int(eco.upkeep_base(level) * 0.6 * mult))
    return sparks, int(12 * mult)


def text(kind: str, goal: int) -> str:
    return KINDS[kind][0].format(n=goal)


def season_step(points: int) -> int:
    return min(points // STEP_POINTS, SEASON_STEPS)


def season_reward(step: int, level: int) -> int:
    return int(eco.upkeep_base(level) * (0.8 + 0.3 * step))
