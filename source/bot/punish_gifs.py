"""Гифки к бану, муту, варну, разбану и размуту: файл грузится один раз, дальше отправляем по file_id."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from aiogram.types import FSInputFile

ASSETS = Path(__file__).with_name("assets") / "punish"
FILES = {"бан": "ban.mp4", "разбан": "unban.mp4", "мут": "mute.mp4", "размут": "unmute.mp4", "варн": "warn.mp4"}
MIN_GAP = 20                     # не чаще раза в 20 секунд на чат и вид (рейд, массовые баны — без потока гифок)
PENDING_WAIT = 4                 # столько ждём, пока текст наказания дойдёт до отправки: тогда гифка уйдёт вместе с ним
CAPTION_MAX = 1000
_ids: dict[str, str] = {}
_pending: dict[tuple[int, str], str] = {}
_last: dict[tuple[int, str], float] = {}
_bg: set = set()


async def send(bot, chat_id: int, action: str, thread_id: int | None = None, delay: float = 0.6) -> None:
    name = FILES.get(action)
    if name is None:
        return
    now = time.time()
    if now - _last.get((chat_id, action), 0) < MIN_GAP:
        return
    _last[(chat_id, action)] = now
    await asyncio.sleep(delay)                       # сначала приходит текст, потом гифка
    path = ASSETS / name
    try:
        src = _ids.get(name) or FSInputFile(path)
        msg = await bot.send_animation(chat_id, src, message_thread_id=thread_id)
        if name not in _ids and getattr(msg, "animation", None):
            _ids[name] = msg.animation.file_id
    except Exception as e:
        _ids.pop(name, None)                         # id мог устареть — в следующий раз загрузим файл заново
        logging.info("гифка %s не отправилась: %s", action, e)


def spawn(bot, chat_id: int, action: str, thread_id: int | None = None) -> None:
    """В фоне: ответ на команду не ждёт загрузку гифки."""
    if action not in FILES:
        return
    try:
        t = asyncio.get_running_loop().create_task(send(bot, chat_id, action, thread_id))
    except RuntimeError:
        return
    _bg.add(t)
    t.add_done_callback(_bg.discard)


def source(action: str):
    """Что отправлять: file_id (если уже загружали) или сам файл."""
    name = FILES[action]
    return _ids.get(name) or FSInputFile(ASSETS / name)


def remember(action: str, msg) -> None:
    name = FILES.get(action)
    anim = getattr(msg, "animation", None)
    if name and anim is not None and name not in _ids:
        _ids[name] = anim.file_id


def arm(bot, chat_id: int, text: str, action: str) -> None:
    """Гифка должна уйти вместе с этим текстом (подписью): сессия бота подменит отправку текста на гифку с подписью.
    Если текст так и не отправили (или его изменили) — через PENDING_WAIT секунд шлём гифку отдельно."""
    if action not in FILES:
        return
    now = time.time()
    if now - _last.get((chat_id, action), 0) < MIN_GAP:
        return
    if len(text) > CAPTION_MAX:                      # в подпись не влезает — гифка отдельно, как раньше
        spawn(bot, chat_id, action)
        return
    _last[(chat_id, action)] = now
    key = (chat_id, text)
    _pending[key] = action

    async def fallback():
        await asyncio.sleep(PENDING_WAIT)
        if _pending.pop(key, None) is not None:
            _last.pop((chat_id, action), None)
            await send(bot, chat_id, action, delay=0)
    try:
        t = asyncio.get_running_loop().create_task(fallback())
    except RuntimeError:
        _pending.pop(key, None)
        return
    _bg.add(t)
    t.add_done_callback(_bg.discard)


def take(chat_id: int, text: str | None) -> str | None:
    """Если для этого текста ждёт гифка — забрать (и больше не отправлять отдельно)."""
    return _pending.pop((chat_id, text), None) if text else None
