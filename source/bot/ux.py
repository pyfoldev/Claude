"""Новые возможности Telegram Bot API одним местом: ephemeral-сообщения, реакции, теги участников, таблицы.
Всё — «по возможности»: если Telegram или клиент чего-то не поддерживает, функции молча откатываются на обычное поведение."""
from __future__ import annotations

import asyncio
import html
import logging
import os
import re
import time

from aiogram.types import EphemeralMessageParameters, ReactionTypeEmoji, ReplyParameters

# Ephemeral-сообщения (Bot API 10.2) ВЫКЛЮЧЕНЫ: замечания и ответы идут обычным сообщением. Само оно не удаляется (NOTICE_TTL = 0).
# EPHEMERAL=1 в .env включает их обратно (в группе — видит только адресат).
EPHEMERAL = os.environ.get("EPHEMERAL", "0") == "1"
_eph_off_until = 0.0          # ephemeral недоступен (старый сервер/нет прав) — до этого момента не пробуем
_react_off_until = 0.0
NOTICE_TTL = 0                # сколько живёт обычный (не ephemeral) ответ-замечание, сек
_bg: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    t = asyncio.create_task(coro)
    _bg.add(t)
    t.add_done_callback(_bg.discard)


async def _delete_later(bot, chat_id: int, message_id: int, delay: float) -> None:
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


# ВЫБОР СПОСОБА ОТВЕТА:
#   ux.tell(message, text)  — ответ-замечание автору команды (ошибки, кулдауны, «нет прав»);
#   ux.tell_cb(cb, text)    — то же на нажатие inline-кнопки;
#   ux.react(bot, chat, msg_id, "👌") — молча поставить реакцию вместо текста;
#   message.answer / message.reply  — обычное публичное сообщение (результат, который видят все).
async def tell(message, text: str, *, reply_markup=None, ttl: int = NOTICE_TTL):
    """Ответ, который нужен только автору команды (кулдауны, «нет прав», баланс). В группе — ephemeral-сообщение
    (видит один человек, Bot API 10.2); если не вышло — обычный ответ, который удалится сам через ttl секунд."""
    global _eph_off_until
    user = message.from_user
    if EPHEMERAL and message.chat.type in ("group", "supergroup") and user is not None and time.time() >= _eph_off_until:
        try:
            await message.bot.send_message(
                message.chat.id, text, reply_markup=reply_markup, message_thread_id=message.message_thread_id
                if getattr(message, "is_topic_message", False) else None,
                ephemeral_message_parameters=EphemeralMessageParameters(receiver_user_id=user.id))
            return None
        except Exception as e:
            logging.info("ephemeral недоступен: %s", e)
            _eph_off_until = time.time() + 600
    sent = await message.reply(text, reply_markup=reply_markup)
    if message.chat.type in ("group", "supergroup") and ttl:
        _spawn(_delete_later(message.bot, sent.chat.id, sent.message_id, ttl))
    return sent


async def tell_cb(cb, text: str, *, reply_markup=None) -> None:
    """Ответ на нажатие кнопки, который нужен только нажавшему: ephemeral-сообщение (Bot API 10.2, связано с callback_query_id).
    Не вышло — всплывающее окно с тем же текстом без разметки (до 200 символов)."""
    global _eph_off_until
    msg = getattr(cb, "message", None)
    if EPHEMERAL and msg is not None and msg.chat.type in ("group", "supergroup") and time.time() >= _eph_off_until:
        try:
            await cb.bot.send_message(
                msg.chat.id, text, reply_markup=reply_markup,
                ephemeral_message_parameters=EphemeralMessageParameters(callback_query_id=cb.id))
            return
        except Exception as e:
            logging.info("ephemeral (callback) недоступен: %s", e)
            _eph_off_until = time.time() + 600
    plain = re.sub(r"<[^>]+>", "", text)
    try:
        await cb.answer(html.unescape(plain)[:200], show_alert=True)
    except Exception:
        pass


async def react(bot, chat_id: int, message_id: int, emoji: str = "👍") -> bool:
    """Поставить реакцию вместо лишнего текстового ответа (Bot API 7.0+; в чате реакции должны быть разрешены)."""
    global _react_off_until
    if time.time() < _react_off_until:
        return False
    try:
        await bot.set_message_reaction(chat_id, message_id, reaction=[ReactionTypeEmoji(emoji=emoji)])
        return True
    except Exception as e:
        text = str(e).lower()
        if "reaction" in text and ("invalid" in text or "not allowed" in text or "can't" in text):
            return False                                  # в этом чате такой эмодзи запрещён — не повод отключать всё
        _react_off_until = time.time() + 300
        return False


def rank_tag(rank: int) -> str | None:
    """Тег участника для ранга бота (до 16 символов); ранга нет — убрать тег."""
    return {1: "модератор", 2: "мл. админ", 3: "админ", 4: "ст. админ"}.get(rank) if rank > 0 else None


async def sync_tag(bot, chat_id: int, user_id: int, rank: int) -> bool:
    """Показывать ранг бота тегом рядом с ником (Bot API 9.5, нужно право can_manage_tags). Ошибки не критичны."""
    try:
        await bot.set_chat_member_tag(chat_id, user_id, tag=rank_tag(rank))
        return True
    except Exception as e:
        logging.info("тег участника не выставлен: %s", e)
        return False


async def table_or_text(message, title: str, header: list[str], rows: list[list], fallback_html: str, *,
                        aligns: list[str] | None = None, reply_markup=None, reply: bool = True) -> None:
    """Список в виде настоящей таблицы; если Telegram её не принял — тот же список обычным текстом."""
    from bot.rich import send_table
    if rows:
        sent = await send_table(
            message.bot, message.chat.id, title, header, rows, aligns=aligns, reply_markup=reply_markup,
            reply_to=message.message_id if reply else None,
            thread_id=message.message_thread_id if getattr(message, "is_topic_message", False) else None)
        if sent is not None:
            return
    await message.reply(fallback_html, reply_markup=reply_markup, disable_web_page_preview=True)
