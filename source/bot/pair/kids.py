"""Дети: рост (5 суток = 1 год), настроение, забота, навыки, профессия, взросление. Правила без БД."""
from __future__ import annotations

YEAR_SEC = 5 * 86400
ADULT_AGE = 18
MOOD_DECAY_SEC = 4 * 3600
SKILL_CAP = 100
GROWN_GIFT = 1000                      # искр в кошелёк пары, когда ребёнок съезжает
CARE = {                                # ключ: (эмодзи, подпись, кулдаун, +настроение, навык, мин. возраст)
    "покормить": ("🥄", "покормили", 6 * 3600, 25, None, 0),
    "поиграть": ("🧸", "поиграли", 3 * 3600, 15, "s_cre", 0),
    "учить": ("📖", "позанимались", 4 * 3600, 5, "s_int", 3),
    "спорт": ("⚽", "потренировались", 4 * 3600, 5, "s_spo", 3),
}
COL = {"покормить": "fed_at", "поиграть": "play_at", "учить": "study_at", "спорт": "sport_at"}
JOBS = {"s_int": ["учёный", "врач", "инженер"], "s_cre": ["художник", "музыкант", "писатель"], "s_spo": ["тренер", "спасатель", "гонщик"]}
SKILL_NAMES = {"s_int": "ум", "s_cre": "творчество", "s_spo": "спорт"}


def age(born: int, now: int) -> int:
    return max(0, (now - born) // YEAR_SEC)


def stage(a: int) -> str:
    return "малыш" if a < 3 else "дошкольник" if a < 7 else "школьник" if a < 14 else "подросток" if a < ADULT_AGE else "взрослый"


def mood_now(mood: int, mood_at: int, now: int) -> tuple[int, int]:
    steps = max(0, (now - mood_at) // MOOD_DECAY_SEC)
    return max(0, mood - steps), mood_at + steps * MOOD_DECAY_SEC


def job_for(c: dict) -> str:
    best = max(JOBS, key=lambda k: c[k])
    jobs = JOBS[best]
    return jobs[c["id"] % len(jobs)]
