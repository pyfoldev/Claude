"""Лёгкие метрики работы бота: сколько обновлений, как быстро обрабатываются, сколько ошибок, размер БД.
Живут в памяти (сбрасываются при перезапуске); владельцу доступны командой «метрики» в личке."""
from __future__ import annotations

import os
import time
from collections import deque

from aiogram import BaseMiddleware

SLOW_MS = 500.0


class Metrics:
    def __init__(self, window: int = 2000):
        self.started = time.time()
        self.total = 0
        self.errors = 0
        self.slow = 0
        self._lat: deque[float] = deque(maxlen=window)      # миллисекунды
        self._stamps: deque[float] = deque(maxlen=20000)    # когда пришли последние обновления

    def record(self, ms: float, ok: bool = True) -> None:
        self.total += 1
        self._lat.append(ms)
        self._stamps.append(time.time())
        if not ok:
            self.errors += 1
        if ms >= SLOW_MS:
            self.slow += 1

    def rate(self, seconds: float = 60.0, now: float | None = None) -> float:
        """Обновлений в секунду за последние seconds секунд."""
        now = time.time() if now is None else now
        n = sum(1 for t in reversed(self._stamps) if now - t <= seconds)
        return n / seconds

    def percentile(self, p: float) -> float:
        if not self._lat:
            return 0.0
        data = sorted(self._lat)
        return data[min(int(len(data) * p), len(data) - 1)]

    def render(self, db_path: str = "", extra: dict | None = None) -> str:
        up = int(time.time() - self.started)
        lines = [
            "📈 <b>Метрики</b>",
            f"Работает: {up // 86400} д {up % 86400 // 3600} ч {up % 3600 // 60} мин",
            f"Обновлений: {self.total} · сейчас {self.rate():.2f}/с (за минуту)",
            f"Время обработки: p50 {self.percentile(.5):.1f} мс · p95 {self.percentile(.95):.1f} мс · p99 {self.percentile(.99):.1f} мс",
            f"Ошибок: {self.errors} · медленных (>{int(SLOW_MS)} мс): {self.slow}",
        ]
        if db_path and os.path.exists(db_path):
            lines.append(f"База: {os.path.getsize(db_path) / 1048576:.1f} МБ")
        for k, v in (extra or {}).items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)


class MetricsMiddleware(BaseMiddleware):
    """Внешний слой на update: замеряет полное время обработки и считает ошибки."""

    def __init__(self, metrics: Metrics):
        self.metrics = metrics

    async def __call__(self, handler, event, data):
        t = time.perf_counter()
        ok = True
        try:
            return await handler(event, data)
        except Exception:
            ok = False
            raise
        finally:
            self.metrics.record((time.perf_counter() - t) * 1000, ok)
