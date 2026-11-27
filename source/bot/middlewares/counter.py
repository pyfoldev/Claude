import time

from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.db import Database


class CounterMiddleware(BaseMiddleware):
    """Считает каждое сообщение в группе (текст не сохраняется) и запоминает @username."""

    def __init__(self, db: Database):
        self.db = db

    async def __call__(self, handler, event: Message, data):
        u = event.from_user
        if event.chat.type in ("group", "supergroup") and u and not u.is_bot:
            now = int(time.time())
            await self.db.record_message(event.chat.id, u.id, now)
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
        return await handler(event, data)
