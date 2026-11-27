"""Антирейд: если за короткое время зашло слишком много людей — включаем режим защиты."""
from __future__ import annotations

from collections import deque


class RaidGuard:
    def __init__(self) -> None:
        self._joins: dict[int, deque[float]] = {}
        self._until: dict[int, float] = {}

    def until(self, chat_id: int) -> float:
        return self._until.get(chat_id, 0)

    def register(self, chat_id: int, now: float, s: dict) -> tuple[bool, bool]:
        """Учесть вход. Возвращает (режим_активен, сработал_только_что)."""
        if self._until.get(chat_id, 0) > now:
            return True, False
        joins = self._joins.setdefault(chat_id, deque())
        joins.append(now)
        while joins and now - joins[0] >= s["raid_sec"]:
            joins.popleft()
        if len(joins) >= s["raid_n"]:
            joins.clear()
            self._until[chat_id] = now + s["raid_minutes"] * 60
            return True, True
        return False, False


raid_guard = RaidGuard()
