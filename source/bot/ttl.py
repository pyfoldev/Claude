"""Очистка словарей-кулдаунов в памяти, чтобы они не росли бесконечно."""


def prune_stale(d: dict, max_age: float, now: float) -> int:
    """Удаляет записи, где значение — время (float/int) старше max_age. Остальные значения не трогает."""
    stale = [k for k, v in d.items() if isinstance(v, (int, float)) and not isinstance(v, bool) and now - v > max_age]
    for k in stale:
        d.pop(k, None)
    return len(stale)
