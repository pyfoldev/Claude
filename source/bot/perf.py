"""Ускорение aiogram: синхронные фильтры — сразу в цикле событий, без отдельного потока.

aiogram вызывает любой не-async фильтр (в том числе все `F.text.func(...)`) через asyncio.to_thread. У бота ~65 таких
фильтров, и обычное сообщение «привет» проходит почти все: это ~65 прыжков в пул потоков на сообщение — основная
часть времени обработки. Наши фильтры — короткие проверки (регулярки, сравнения), ничего не ждут, поэтому вызываем их
напрямую. Обработчики (handlers) не трогаем: у бота они все async, а синхронные aiogram по-прежнему увезёт в поток."""
from __future__ import annotations

from functools import partial

from aiogram.dispatcher.event.handler import FilterObject

_applied = False


async def _call_inline(self: FilterObject, *args, **kwargs):
    wrapped = partial(self.callback, *args, **self._prepare_kwargs(kwargs))
    if self.awaitable:
        return await wrapped()
    return wrapped()


def apply() -> None:
    global _applied
    if not _applied:
        FilterObject.call = _call_inline
        _applied = True


apply()


# ---------- фоновые «печатает…» ----------
import asyncio  # noqa: E402

_bg: set = set()


def chat_action(bot, chat_id: int, action: str) -> None:
    """«печатает…» / «отправляет фото…» — в фоне: ответ не ждёт лишний сетевой круг до Telegram."""
    async def _send():
        try:
            await bot.send_chat_action(chat_id, action)
        except Exception:
            pass
    try:
        t = asyncio.get_running_loop().create_task(_send())
    except RuntimeError:
        return
    _bg.add(t)
    t.add_done_callback(_bg.discard)
