"""Журнал действий в отдельный чат/канал: очередь с ограничением скорости, повтор при flood control.
Сбой журнала никогда не ломает модерацию: ошибки только пишутся в лог."""
from __future__ import annotations

import asyncio
import html
import logging
import time
from collections import deque
from typing import Awaitable, Callable

from aiogram.exceptions import TelegramRetryAfter

ICONS = {"бан": "🔨", "разбан": "✅", "мут": "🔇", "размут": "🔊", "кик": "👢", "варн": "⚠️",
         "снять варн": "↩️", "удаление": "🗑", "ранг": "🎖", "массовый кик": "🧹", "жалоба": "📣",
         "настройка": "⚙️", "антирейд": "🚨"}
MAX_TEXT = 3500


def _dur(sec: int | None) -> str:
    if not sec:
        return ""
    if sec % 86400 == 0:
        return f" на {sec // 86400} дн."
    if sec % 3600 == 0:
        return f" на {sec // 3600} ч."
    return f" на {max(sec // 60, 1)} мин."


def _escape_clip(value: str, budget: int) -> str:
    escaped = html.escape(value)
    if len(escaped) <= budget:
        return escaped
    out, used = [], 0
    for ch in value:
        fragment = html.escape(ch)
        if used + len(fragment) > budget - 1:
            break
        out.append(fragment)
        used += len(fragment)
    return "".join(out) + "…"


def format_event(chat_title: str, actor: str, target: str | None, action: str, duration: int | None,
                 reason: str, ts: int) -> str:
    lines = [f"{ICONS.get(action, '📝')} <b>{_escape_clip(action, 160)}</b>{_dur(duration)}",
             f"Чат: {_escape_clip(chat_title, 768)}", f"Кто: {_escape_clip(actor, 768)}"]
    if target:
        lines.append(f"Кого: {_escape_clip(target, 768)}")
    timestamp = "🕒 " + time.strftime("%d.%m.%Y %H:%M:%S", time.gmtime(ts)) + " UTC"
    if reason:
        budget = MAX_TEXT - len("\n".join(lines)) - len(timestamp) - len("Причина: ") - 2
        lines.append("Причина: " + _escape_clip(reason, max(1, budget)))
    lines.append(timestamp)
    return "\n".join(lines)


class Auditor:
    def __init__(self, bot, db, interval: float = 1.1, max_queue: int = 500,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.bot, self.db, self.interval, self.max_queue, self._sleep = bot, db, interval, max_queue, sleep
        self._q: deque[tuple[int, str]] = deque()
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._pending: set[asyncio.Task] = set()

    # ---- приём событий ----
    def action_fire_and_forget(self, *args) -> None:
        """Вызывается из Database.log_action: ничего не ждём и ничего не бросаем."""
        try:
            t = asyncio.get_running_loop().create_task(self.record_action(*args))
        except RuntimeError:
            return
        self._pending.add(t)
        t.add_done_callback(self._pending.discard)

    async def _name(self, uid: int | None) -> str:
        if not uid:
            return "—"
        name = await self.db.user_name(uid)
        return f"{name} ({uid})" if name else f"id{uid}"

    async def record_action(self, chat_id: int, actor_id: int, target_id: int | None, action: str,
                            reason: str, ts: int, duration: int | None) -> None:
        try:
            dest = (await self.db.get_settings(chat_id)).get("log_chat_id", 0)
            if not dest:
                return
            chat = await self.db.get_chat(chat_id)
            text = format_event((chat or {}).get("title") or str(chat_id), await self._name(actor_id),
                                await self._name(target_id) if target_id else None, action, duration, reason or "", ts)
            await self.push(dest, text)
        except Exception:
            logging.exception("audit: не смог подготовить запись")

    async def push(self, dest: int, text: str) -> None:
        if len(self._q) >= self.max_queue:
            self._q.popleft()   # переполнение: теряем самое старое
        self._q.append((dest, text))
        self._wake.set()

    # ---- отправка ----
    async def _send_one(self, dest: int, text: str) -> None:
        for _ in range(3):
            try:
                await self.bot.send_message(dest, text, disable_web_page_preview=True)
                return
            except TelegramRetryAfter as e:
                await self._sleep(min(e.retry_after, 60))
            except Exception as e:
                logging.warning("audit: отправка в %s не удалась: %s", dest, type(e).__name__)
                return

    async def drain(self) -> None:
        """Отправить всё из очереди (используется воркером и тестами)."""
        if self._pending:
            await asyncio.shield(asyncio.gather(*list(self._pending), return_exceptions=True))
        first = True
        while self._q:
            dest, text = self._q.popleft()
            try:
                if not first:
                    await self._sleep(self.interval)
                first = False
                await self._send_one(dest, text)
            except asyncio.CancelledError:
                self._q.appendleft((dest, text))
                raise

    async def _worker(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            try:
                await self.drain()
            except Exception:
                logging.exception("audit worker")
            await self._sleep(self.interval)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._worker())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None


    async def aclose(self, timeout: float = 5.0) -> None:
        worker = self._task
        self.stop()
        if worker is not None:
            await asyncio.gather(worker, return_exceptions=True)
        try:
            await asyncio.wait_for(self.drain(), timeout)
        except asyncio.TimeoutError:
            logging.warning("audit: shutdown deadline reached; %s events left", len(self._q))
        finally:
            pending = list(self._pending)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            self._pending.difference_update(pending)
            self._q.clear()
