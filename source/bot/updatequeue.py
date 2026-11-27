"""Надёжная очередь входящих обновлений (режим webhook).

Проблема: раньше webhook отвечал Telegram «200» сразу и обрабатывал обновление в фоне. Если бот падал или перезапускался
в этот момент, обновление терялось безвозвратно (Telegram считал его доставленным).

Решение: обновление сначала записывается в БД (группой — один commit на пачку одновременно пришедших), только потом
Telegram получает «200». Обрабатывают очередь N параллельных воркеров (UPDATE_WORKERS, по умолчанию 64): бот работает
одинаково при любой нагрузке, а число одновременных обработчиков ограничено и настраивается. После сбоя необработанные
свежие обновления выполняются заново; «ядовитое» обновление, на котором бот падает, пропускается после нескольких попыток.
Повторная доставка того же update_id (Telegram ретраит при таймауте) отбрасывается."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict

from aiogram.types import Update

MAX_ATTEMPTS = 3        # сколько раз пробуем обновление, на котором бот падал
REPLAY_MAX_AGE = 300    # старше 5 минут после сбоя не повторяем: поздний бан/выдача монет хуже пропуска
DONE_FLUSH = 0.2        # как часто стираем обработанные из таблицы (окно возможного повтора при падении)
SEEN_LIMIT = 5000       # сколько последних update_id помним для защиты от дублей


class QueueFull(Exception):
    pass


class UpdateQueue:
    def __init__(self, db, dp, bot, workers: int = 64, maxsize: int = 10000):
        self.db, self.dp, self.bot = db, dp, bot
        self.workers = max(1, workers)
        self._q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._tasks: list[asyncio.Task] = []
        self._done: list[int] = []
        self._done_ids: set[int] = set()
        self._seen: OrderedDict[int, None] = OrderedDict()
        self._pending: dict[int, asyncio.Task] = {}
        self._inflight: set[int] = set()
        self._stopping = False
        self._seq = 0            # номер последней вставки
        self._covered = 0        # до какого номера вставки дошёл commit
        self._committing: asyncio.Future | None = None
        self._committing_seq = 0
        self.processed = 0
        self.failed = 0
        self.duplicates = 0
        self.replayed = 0
        self.busy = 0            # сколько воркеров заняты прямо сейчас
        self.peak_busy = 0

    # ---------- приём ----------
    def _remember(self, uid: int) -> bool:
        """False — этот update_id мы уже видели."""
        if uid in self._seen:
            return False
        self._seen[uid] = None
        if len(self._seen) > SEEN_LIMIT:
            self._seen.popitem(last=False)
        return True

    async def put(self, update: Update, raw: str) -> bool:
        """Записать и поставить в очередь. После возврата обновление гарантированно лежит в БД.
        False — дубль (уже принято раньше)."""
        if self._stopping:
            raise QueueFull
        uid = update.update_id
        if uid in self._pending:
            await asyncio.shield(self._pending[uid])
            self.duplicates += 1
            return False
        if uid in self._seen or uid in self._inflight or uid in self._done_ids:
            self.duplicates += 1
            return False
        # Резервируем место до первого await: параллельные запросы не переполнят очередь.
        if self._q.maxsize > 0 and self._q.qsize() + len(self._pending) >= self._q.maxsize:
            raise QueueFull
        task = asyncio.create_task(self._accept(update, raw))
        self._pending[uid] = task
        # При обрыве HTTP приём продолжается до commit и постановки в очередь.
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        return await asyncio.shield(task)

    async def _accept(self, update: Update, raw: str) -> bool:
        try:
            await self.db.conn.execute(
                "INSERT OR IGNORE INTO update_queue(update_id, ts, attempts, payload) VALUES(?,?,?,?)",
                (update.update_id, int(time.time()), 0, raw))
            self._seq += 1
            await self._sync(self._seq)
            self._remember(update.update_id)
            self._inflight.add(update.update_id)
            self._q.put_nowait(update)
            return True
        finally:
            self._pending.pop(update.update_id, None)

    async def _sync(self, seq: int) -> None:
        """Дождаться commit, начатого после нашей вставки (групповой commit: одна запись на пачку обновлений)."""
        while self._covered < seq:
            if self._committing is None:
                self._committing = asyncio.create_task(self._commit(self._seq))
            await asyncio.shield(self._committing)

    async def _commit(self, target: int) -> None:
        try:
            await self.db.conn.commit()
            self._covered = max(self._covered, target)
        finally:
            self._committing = None

    # ---------- обработка ----------
    async def _worker(self) -> None:
        while True:
            update = await self._q.get()
            self.busy += 1
            self.peak_busy = max(self.peak_busy, self.busy)
            try:
                await self.dp.feed_update(self.bot, update)
                self.processed += 1
            except Exception:
                self.failed += 1
                self._done.append(update.update_id)
                self._done_ids.add(update.update_id)
                self._inflight.discard(update.update_id)
                logging.exception("update %s failed", getattr(update, "update_id", "?"))
            else:
                self._done.append(update.update_id)
                self._done_ids.add(update.update_id)
                self._inflight.discard(update.update_id)
            finally:
                self.busy -= 1
                self._q.task_done()

    async def _cleaner(self) -> None:
        while True:
            await asyncio.sleep(DONE_FLUSH)
            await self.flush_done()

    async def flush_done(self) -> None:
        if not self._done:
            return
        ids, self._done = self._done, []
        try:
            # Один запрос на пачку сокращает число обращений к БД и переключений задач.
            for start in range(0, len(ids), 500):
                batch = ids[start:start + 500]
                placeholders = ",".join("?" for _ in batch)
                await self.db.conn.execute(f"DELETE FROM update_queue WHERE update_id IN ({placeholders})", tuple(batch))
            await self.db.conn.commit()
            self._done_ids.difference_update(ids)
        except asyncio.CancelledError:
            self._done = ids + self._done
            raise
        except Exception:
            self._done = ids + self._done
            logging.exception("update queue cleanup failed")

    async def start(self) -> None:
        if self._stopping:
            raise RuntimeError("update queue already stopped")
        if self._tasks:
            raise RuntimeError("update queue already started")
        self._tasks = [asyncio.create_task(self._worker()) for _ in range(self.workers)]
        try:
            await self._recover()
        except BaseException:
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()
            raise
        self._tasks.append(asyncio.create_task(self._cleaner()))

    async def _recover(self) -> None:
        """После сбоя: свежие необработанные обновления выполняем снова, «ядовитые» и старые выбрасываем."""
        now = int(time.time())
        cur = await self.db.conn.execute("SELECT update_id, ts, attempts, payload FROM update_queue ORDER BY update_id")
        rows = [dict(r) for r in await cur.fetchall()]
        for r in rows:
            if r["update_id"] in self._seen:
                continue                      # уже стоит в очереди этого запуска
            if r["attempts"] >= MAX_ATTEMPTS or now - r["ts"] > REPLAY_MAX_AGE:
                await self.db.conn.execute("DELETE FROM update_queue WHERE update_id=?", (r["update_id"],))
                logging.warning("update %s пропущен после сбоя (попыток %s, возраст %s с)",
                                r["update_id"], r["attempts"], now - r["ts"])
                continue
            await self.db.conn.execute("UPDATE update_queue SET attempts=attempts+1 WHERE update_id=?", (r["update_id"],))
            try:
                upd = Update.model_validate_json(r["payload"], context={"bot": self.bot})
            except Exception:
                await self.db.conn.execute("DELETE FROM update_queue WHERE update_id=?", (r["update_id"],))
                continue
            self._remember(upd.update_id)
            self._inflight.add(upd.update_id)
            await self.db.conn.commit()
            await self._q.put(upd)
            self.replayed += 1
        await self.db.conn.commit()
        if self.replayed:
            logging.info("очередь обновлений: повторяю %s необработанных после сбоя", self.replayed)

    async def stop(self, timeout: float = 15.0) -> None:
        """Штатная остановка: дорабатываем то, что принято, и стираем из таблицы."""
        self._stopping = True
        if self._pending:
            await asyncio.gather(*list(self._pending.values()), return_exceptions=True)
        try:
            await asyncio.wait_for(self._q.join(), timeout)
        except asyncio.TimeoutError:
            logging.warning("очередь обновлений: не успели обработать %s шт. за %s с — повторим при старте", self._q.qsize(), timeout)
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self.flush_done()
        self._tasks.clear()

    def depth(self) -> int:
        return self._q.qsize()
