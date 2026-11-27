"""Тихие темы форума: в теме, помеченной «+тихая тема», бот не отвечает на сообщения обычных участников.
Стоит ПОСЛЕ защиты, поэтому антиспам, фильтры и капча работают как обычно; модераторы командуют и там."""
from aiogram import BaseMiddleware
from aiogram.types import Message

from bot import mod_service as ms


# ПРИМЕР MIDDLEWARE: __call__ вызывается на каждое сообщение. return None = остановить, return await handler(m, data) = пропустить.
class QuietTopicMiddleware(BaseMiddleware):
    def __init__(self, db):
        self.db = db

    async def __call__(self, handler, m: Message, data):
        if m.chat.type == "supergroup" and m.is_topic_message and m.from_user is not None \
                and await self.db.topic_quiet(m.chat.id, m.message_thread_id):
            if await ms.effective_rank(data["bot"], self.db, m.chat.id, m.from_user.id) < 1:
                return None
        return await handler(m, data)
