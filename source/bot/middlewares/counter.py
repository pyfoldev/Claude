import time

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.db import Database


# ┌─ MIDDLEWARE: счётчик сообщений ───────────────────────────────────────────────────────────────┐
# │ Где подключён: main.py, dp.message.outer_middleware(CounterMiddleware(db)) — РАНЬШЕ защиты, поэтому    │
# │ считаются и те сообщения, которые защита потом удалит.                                                  │
# │ Что делает: пишет +1 в статистику (db.record_message), для форумов — ещё и по темам (topic_*).         │
# │ Редактировать: чтобы НЕ считать какие-то сообщения — добавьте условие в `if` ниже.                    │
# └───────────────────────────────────────────────────────────────────────────────────────────────────────┘
class CounterMiddleware(BaseMiddleware):
    """Считает каждое сообщение в группе (текст не сохраняется) и запоминает @username."""

    def __init__(self, db: Database):
        self.db = db

    async def __call__(self, handler, event: Message, data):
        # u — автор; считаем только людей в группах (боты и личка не считаются)
        u = event.from_user
        if event.chat.type in ("group", "supergroup") and u and not u.is_bot:
            now = int(time.time())
            await self.db.record_message(event.chat.id, u.id, now)
            # --- форум: отдельная статистика по темам; thread=0 — «общая» тема ---
            if getattr(event.chat, "is_forum", False) or event.is_topic_message:       # статистика по темам форума
                thread = event.message_thread_id if event.is_topic_message else 0
                self.db.record_topic_message(event.chat.id, thread, now)
                created = getattr(event, "forum_topic_created", None)
                edited = getattr(event, "forum_topic_edited", None)
                r = event.reply_to_message
                name = (created.name if created else None) or (edited.name if edited and edited.name else None) \
                    or (r.forum_topic_created.name if r is not None and getattr(r, "forum_topic_created", None) else None)
                if thread and name:
                    await self.db.topic_seen(event.chat.id, thread, name)
        return await handler(event, data)       # ВСЕГДА пропускаем дальше: счётчик ничего не блокирует
