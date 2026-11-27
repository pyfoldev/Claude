"""Удаление ВСЕХ сообщений чата.

В Bot API нет «удалить всё»: бот может лишь удалять сообщения по номерам, до 100 за вызов. Номера в чате идут подряд,
поэтому бот узнаёт номер самого свежего сообщения (отправляет своё статусное) и идёт вниз до 1, удаляя пачками.
Несуществующие и неудаляемые номера Telegram пропускает молча. Админ-бот с правом «удалять сообщения» может удалять
любые сообщения без ограничения в 48 часов. Работа идёт в фоне, есть прогресс и остановка.
Это необратимо, поэтому минимальный ранг — 4, и его нельзя снизить в «доступе команд»."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from weakref import WeakValueDictionary

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from bot.db import Database

MIN_RANK = 4
CONFIRM_PHRASE = "УДАЛИТЬ ВСЁ"
BATCH = 100
PAUSE = 0.05              # пауза между вызовами; при лимитах Telegram ждём сколько он скажет
PROGRESS_EVERY = 5.0
MAX_BAD_BATCHES = 5       # столько подряд отказов Telegram — и работа прекращается


class PurgeError(Exception):
    pass


@dataclass
class PurgeJob:
    chat_id: int
    actor: int
    top: int
    started: float = field(default_factory=time.time)
    processed: int = 0                 # сколько номеров уже пройдено (от top вниз)
    state: str = "running"             # running | done | stopped | failed
    error: str = ""
    stop: bool = False
    task: asyncio.Task | None = None
    status_msg: int | None = None

    def public(self) -> dict:
        return {"state": self.state, "processed": min(self.processed, self.top), "total": self.top,
                "error": self.error, "started": int(self.started)}


JOBS: dict[int, PurgeJob] = {}
_start_locks: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()


def get_job(chat_id: int) -> PurgeJob | None:
    return JOBS.get(chat_id)


def stop_job(chat_id: int) -> bool:
    job = JOBS.get(chat_id)
    if job is None or job.state != "running":
        return False
    job.stop = True
    return True


async def _check_bot_rights(bot, chat_id: int) -> None:
    try:
        me = await bot.me()
        m = await bot.get_chat_member(chat_id, me.id)
    except Exception as e:
        raise PurgeError(f"Не удалось проверить права бота: {e}"[:200])
    if m.status == "creator":
        return
    if m.status != "administrator" or not getattr(m, "can_delete_messages", False):
        raise PurgeError("Сделайте бота админом с правом «Удаление сообщений».")


async def start_purge(bot, db: Database, chat_id: int, actor: int) -> PurgeJob:
    async with _start_locks.setdefault(chat_id, asyncio.Lock()):
        cur = JOBS.get(chat_id)
        if cur is not None and cur.state == "running":
            raise PurgeError("Очистка этого чата уже идёт.")
        await _check_bot_rights(bot, chat_id)
        try:
            st = await bot.send_message(chat_id, "🧹 Очищаю чат… Это может занять время.")
        except Exception as e:
            raise PurgeError(f"Не могу писать в чат: {e}"[:200])
        job = PurgeJob(chat_id, actor, top=st.message_id - 1, status_msg=st.message_id)
        JOBS[chat_id] = job
        job.task = asyncio.create_task(_run(bot, db, job))
        return job


def _bar(job: PurgeJob) -> str:
    pct = 100 if job.top <= 0 else int(min(job.processed, job.top) * 100 / job.top)
    return f"{pct}%"


async def _edit(bot, job: PurgeJob, text: str) -> None:
    try:
        await bot.edit_message_text(text, chat_id=job.chat_id, message_id=job.status_msg)
    except Exception:
        pass


async def _run(bot, db: Database, job: PurgeJob) -> None:
    cur, last_edit, bad = job.top, time.monotonic(), 0
    try:
        while cur > 0 and not job.stop:
            lo = max(cur - BATCH + 1, 1)
            try:
                await bot.delete_messages(job.chat_id, list(range(lo, cur + 1)))
                bad = 0
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                continue                                   # ту же пачку — заново
            except TelegramForbiddenError:
                raise
            except TelegramBadRequest as e:
                text = str(e).lower()
                if "not enough rights" in text or "chat not found" in text or "not a member" in text:
                    raise
                bad += 1
                if bad >= MAX_BAD_BATCHES:
                    raise
            cur = lo - 1
            job.processed = job.top - cur
            if time.monotonic() - last_edit >= PROGRESS_EVERY:
                last_edit = time.monotonic()
                await _edit(bot, job, f"🧹 Очищаю чат… {_bar(job)}")
            await asyncio.sleep(PAUSE)
        job.state = "stopped" if job.stop else "done"
    except asyncio.CancelledError:
        job.state = "stopped"
        raise
    except Exception as e:
        logging.exception("purge %s failed", job.chat_id)
        job.state, job.error = "failed", str(e)[:200]
    finally:
        try:
            await db.log_action(job.chat_id, job.actor, 0, "очистка чата",
                                f"{job.state}: номера 1–{job.top}, пройдено {min(job.processed, job.top)}",
                                int(time.time()))
        except Exception:
            logging.exception("purge log failed")
        final = {"done": "✅ Чат очищен.", "stopped": f"⏹ Очистка остановлена на {_bar(job)}.",
                 "failed": f"⚠️ Очистка прервана: {job.error}"}[job.state]
        await _edit(bot, job, final)
