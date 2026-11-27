"""Запоминает последние сообщения чата для «живого» общения ИИ — только там, где оно включено."""
from aiogram import BaseMiddleware
from aiogram.types import Message

from bot.chatmind import BOT_UID, MEMORY, media_tag
from bot.db import Database


def reply_uid(event: Message, bot_id: int | None) -> int | None:
    """Кому отвечает сообщение: id автора исходного сообщения (BOT_UID — самой Нори), иначе None."""
    r = event.reply_to_message
    if r is None or r.from_user is None or getattr(r, "forum_topic_created", None) is not None:
        return None
    return BOT_UID if bot_id is not None and r.from_user.id == bot_id else r.from_user.id


class ChatMemoryMiddleware(BaseMiddleware):
    def __init__(self, db: Database):
        self.db = db

    async def __call__(self, handler, event: Message, data):
        u = event.from_user
        text = event.text or event.caption
        tag = media_tag(event)
        if tag:
            text = f"{tag} {text}".strip() if text else tag
        if (text and u and not u.is_bot and event.chat.type in ("group", "supergroup")
                and not text.startswith("/") and (await self.db.get_settings(event.chat.id))["ai_chat"] != "off"):
            bot = data.get("bot")
            MEMORY.add(event.chat.id, u.id, u.first_name or u.full_name, text, username=u.username,
                       msg_id=event.message_id, reply_uid=reply_uid(event, getattr(bot, "id", None)))
        return await handler(event, data)
