"""Защита самого бота от залпа команд: команда с префиксом («/…», «!…», «.…») — не чаще 4 в секунду и 70 в минуту
от одного человека. Нарушитель на час игнорируется; повторы удлиняют паузу (2, 3 … до 50 часов).
Обычные разговорные сообщения не считаются. Владельцы бота не ограничиваются."""
from __future__ import annotations

import time
from collections import deque

from aiogram import BaseMiddleware
from aiogram.types import Message

PER_SEC = 4
PER_MIN = 70
BLOCK = 3600
MAX_HOURS = 50
FORGET = 24 * 3600


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, owner_ids=(), clock=time.time):
        self.owners = set(owner_ids)
        self.clock = clock
        self._hits: dict[int, deque] = {}
        self._until: dict[int, float] = {}
        self._strikes: dict[int, tuple[int, float]] = {}

    def check(self, user_id: int) -> str:
        """'ok' | 'blocked' (уже в паузе) | 'new' (пауза только что началась)."""
        now = self.clock()
        if self._until.get(user_id, 0) > now:
            return "blocked"
        q = self._hits.setdefault(user_id, deque())
        q.append(now)
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) > PER_MIN or sum(1 for t in q if now - t <= 1) > PER_SEC:
            n, at = self._strikes.get(user_id, (0, 0))
            n = n + 1 if now - at < FORGET else 1
            self._strikes[user_id] = (n, now)
            self._until[user_id] = now + BLOCK * min(n, MAX_HOURS)
            q.clear()
            if len(self._until) > 5000:
                for k in [k for k, t in self._until.items() if t < now]:
                    self._until.pop(k, None)
            return "new"
        return "ok"

    def hours(self, user_id: int) -> int:
        return max(1, int((self._until.get(user_id, 0) - self.clock() + 3599) // 3600))

    async def __call__(self, handler, m: Message, data):
        u = m.from_user
        text = m.text or ""
        if u is None or u.is_bot or u.id in self.owners or not text[:1] in ("/", "!", "."):
            return await handler(m, data)
        state = self.check(u.id)
        if state == "ok":
            return await handler(m, data)
        if state == "new":
            try:
                await m.reply(f"⏳ Слишком много команд подряд. Пауза для вас — {self.hours(u.id)} ч.")
            except Exception:
                pass
        return None
