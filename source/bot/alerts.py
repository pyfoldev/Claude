"""Оповещение владельцев о сбоях: необработанные ошибки, падение фоновых задач, старт после сбоя."""
import asyncio
import logging
import os
import time
from collections import deque
from typing import Awaitable, Callable

# последние ошибки (время, тип исключения) — для диагностики; текст исключения не храним
RECENT: deque = deque(maxlen=10)


class Alerter:
    def __init__(self, bot, owner_ids, min_interval: float = 300, clock: Callable[[], float] = time.time):
        self.bot = bot
        self.owner_ids = list(owner_ids)
        self.min_interval = min_interval
        self.clock = clock
        self._last: float | None = None
        self._suppressed = 0

    async def alert(self, text: str) -> None:
        now = self.clock()
        if self._last is not None and now - self._last < self.min_interval:
            self._suppressed += 1
            return
        if self._suppressed:
            text += f"\n(ещё {self._suppressed} подобных сообщений пропущено)"
            self._suppressed = 0
        self._last = now
        for oid in self.owner_ids:
            try:
                await self.bot.send_message(oid, text)
            except Exception:
                logging.warning("alert to %s failed", oid)


def make_error_handler(alerter: Alerter):
    async def on_error(event) -> bool:
        exc = event.exception
        logging.error("Unhandled error in update", exc_info=exc)
        RECENT.append((int(time.time()), type(exc).__name__))
        # тип без текста исключения: в нём могут оказаться токены/данные пользователей
        uid = getattr(event.update, "update_id", "?")
        await alerter.alert(f"⚠️ Ошибка в боте: {type(exc).__name__} (update {uid}). Подробности — в логах сервера.")
        return True

    return on_error


async def supervise(name: str, factory: Callable[[], Awaitable[None]], alerter: Alerter,
                    backoff: float = 5.0) -> None:
    """Запускает фоновую задачу заново после падения и сообщает владельцу."""
    while True:
        try:
            await factory()
            return
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception("background task %s crashed", name)
            RECENT.append((int(time.time()), f"{name}: {type(e).__name__}"))
            await alerter.alert(f"⚠️ Фоновая задача «{name}» упала ({type(e).__name__}) и перезапущена.")
            await asyncio.sleep(backoff)


def set_marker_and_check_crash(path: str) -> bool:
    """Ставит маркер «работаю». True, если он уже был — прошлый запуск не завершился штатно."""
    crashed = os.path.exists(path)
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w") as f:
            f.write(str(int(time.time())))
    except OSError:
        logging.warning("cannot write run marker %s", path)
    return crashed


def clear_marker(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
