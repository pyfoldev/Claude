"""Запоминает каждого пользователя, которого бот хоть раз увидел (для команд по @username)."""
import logging
import time

from aiogram import BaseMiddleware
from aiogram.types import Message, Update, User

from bot import i18n
from bot import mod_service as ms
from bot.bulk import fulfil_pending
from bot.db import Database


def _from_message(m: Message | None, out: list[User]) -> None:
    if m is None:
        return
    if m.from_user:
        out.append(m.from_user)
    if m.left_chat_member:
        out.append(m.left_chat_member)
    out.extend(m.new_chat_members or [])
    for ent in (m.entities or []) + (m.caption_entities or []):
        if ent.type == "text_mention" and ent.user:
            out.append(ent.user)
    for src in (getattr(m, "forward_origin", None), getattr(getattr(m, "external_reply", None), "origin", None)):
        if src is not None and getattr(src, "sender_user", None):
            out.append(src.sender_user)
    caller = getattr(m, "guest_bot_caller_user", None)       # кто позвал гостевого бота
    if caller is not None:
        out.append(caller)
    for attr in ("forward_from", "via_bot"):
        u = getattr(m, attr, None)
        if u is not None:
            out.append(u)
    shared = getattr(m, "users_shared", None)
    for su in (getattr(shared, "users", None) or []):      # «поделиться контактом/пользователем»
        if getattr(su, "user_id", None):
            out.append(User(id=su.user_id, is_bot=False, first_name=getattr(su, "first_name", None) or f"id{su.user_id}",
                            last_name=getattr(su, "last_name", None), username=getattr(su, "username", None)))
    contact = getattr(m, "contact", None)
    if contact is not None and getattr(contact, "user_id", None):
        out.append(User(id=contact.user_id, is_bot=False, first_name=contact.first_name or f"id{contact.user_id}",
                        last_name=contact.last_name))
    if m.reply_to_message:
        _from_message(m.reply_to_message, out)
    pinned = getattr(m, "pinned_message", None)
    if pinned is not None and hasattr(pinned, "from_user"):
        _from_message(pinned, out)


def extract_users(update: Update) -> list[User]:
    out: list[User] = []
    for m in (update.message, update.edited_message, getattr(update, "business_message", None)):
        _from_message(m, out)
    if update.callback_query:
        out.append(update.callback_query.from_user)
        _from_message(update.callback_query.message, out)
    for name in ("inline_query", "chosen_inline_result", "shipping_query", "pre_checkout_query",
                 "message_reaction", "poll_answer", "chat_boost", "removed_chat_boost"):
        ev = getattr(update, name, None)
        if ev is None:
            continue
        for attr in ("from_user", "user"):
            u = getattr(ev, attr, None)
            if isinstance(u, User):
                out.append(u)
        src = getattr(getattr(ev, "boost", None), "source", None)
        if getattr(src, "user", None):
            out.append(src.user)
    for ev in (update.chat_member, update.my_chat_member):
        if ev:
            out += [ev.from_user, ev.old_chat_member.user, ev.new_chat_member.user]
    if update.chat_join_request:
        out.append(update.chat_join_request.from_user)
    return list({u.id: u for u in out}.values())


_GROUPS = ("group", "supergroup")
SERVICE_IDS = {777000, 136817688, 1087968824}  # Telegram, Channel_Bot, GroupAnonymousBot


from bot.members import is_present as _member_present  # noqa: E402 — одно правило «в чате ли» на весь бот


def _msg_memberships(m: Message | None, out: list) -> None:
    if m is None or m.chat.type not in _GROUPS:
        return
    cid = m.chat.id
    if m.from_user:
        out.append((cid, m.from_user, "seen"))
    for u in m.new_chat_members or []:
        out.append((cid, u, "joined"))
    if m.left_chat_member:
        out.append((cid, m.left_chat_member, "left"))
    # Автор сообщения, на которое ответили, и упомянутые НЕ считаются присутствующими: ответ на старое сообщение
    # вышедшего человека раньше возвращал его в список участников (и сбрасывал ему неактивность).
    # Их имена и ники бот всё равно запоминает (extract_users) — «бан @ник» продолжает работать.


def extract_memberships(update: Update) -> list[tuple[int, User, str]]:
    """(chat_id, user, kind): kind — seen | joined | left. Только группы."""
    out: list = []
    for m in (update.message, update.edited_message):
        _msg_memberships(m, out)
    if update.callback_query and update.callback_query.message \
            and update.callback_query.message.chat.type in _GROUPS:
        out.append((update.callback_query.message.chat.id, update.callback_query.from_user, "seen"))
    for ev in (update.chat_member, update.my_chat_member):
        if ev and ev.chat.type in _GROUPS:
            old, new = ev.old_chat_member, ev.new_chat_member
            if _member_present(new):
                kind = "seen" if _member_present(old) else "joined"
            else:
                kind = "left"
            out.append((ev.chat.id, new.user, kind))
    return out


def extract_chats(update: Update) -> list[tuple]:
    """(чат, активен_ли_бот_в_нём). Только группы и супергруппы."""
    out: list[tuple] = []
    for m in (update.message, update.edited_message):
        if m and m.chat.type in _GROUPS:
            out.append((m.chat, True))
    cb = update.callback_query
    if cb and cb.message and cb.message.chat.type in _GROUPS:
        out.append((cb.message.chat, True))
    if update.my_chat_member and update.my_chat_member.chat.type in _GROUPS:
        ev = update.my_chat_member
        out.append((ev.chat, ev.new_chat_member.status not in ("left", "kicked")))
    if update.chat_member and update.chat_member.chat.type in _GROUPS:
        out.append((update.chat_member.chat, True))
    return out


class UserTrackerMiddleware(BaseMiddleware):
    MEMBER_WRITE_EVERY = 60
    def __init__(self, db: Database):
        self.db = db
        self._chat_seen: dict[int, tuple[float, str | None]] = {}  # чтобы не писать чат в БД на каждое сообщение
        self._member_seen: dict[tuple[int, int], int] = {}          # (чат, юзер) -> когда последний раз писали «был в чате»

    async def __call__(self, handler, event: Update, data):
        try:
            for u in extract_users(event):
                if not u.is_bot and u.id not in SERVICE_IDS:
                    if u.language_code:
                        if len(i18n.USER_LANG) > 100000:
                            i18n.USER_LANG.clear()
                        i18n.USER_LANG[u.id] = u.language_code
                    await self.db.remember_user(u.id, u.username, u.full_name or f"id{u.id}")
                    bot = data.get("bot")
                    if bot is not None and self.db.has_pending(u.username):   # на этот ник стоит отложенный бан
                        await fulfil_pending(bot, self.db, u.id, u.username, int(time.time()))
            now = int(time.time())
            for chat, active in extract_chats(event):
                prev = self._chat_seen.get(chat.id)
                if not active:
                    await self.db.set_chat_active(chat.id, False)
                    self._chat_seen.pop(chat.id, None)
                elif prev is None or now - prev[0] > 300 or prev[1] != chat.title:
                    await self.db.upsert_chat(chat.id, chat.title, chat.type, chat.username, now)
                    self._chat_seen[chat.id] = (now, chat.title)
            for ev in (event.chat_member, event.my_chat_member):
                if ev is not None:                       # Telegram сообщил о смене статуса — сбрасываем кэш прав
                    ms.forget_member(ev.chat.id, ev.new_chat_member.user.id)
            for chat_id, u, kind in extract_memberships(event):
                if u.is_bot or u.id in SERVICE_IDS:
                    continue
                key = (chat_id, u.id)
                if kind == "left":
                    self._member_seen.pop(key, None)
                    await self.db.set_member_active(chat_id, u.id, False)
                elif kind == "seen" and now - self._member_seen.get(key, 0) < self.MEMBER_WRITE_EVERY:
                    continue                  # «был в чате» достаточно обновлять раз в минуту, а не на каждое сообщение
                else:
                    await self.db.touch_member(chat_id, u.id, now, joined=(kind == "joined"))
                    if len(self._member_seen) > 100000:
                        self._member_seen.clear()
                    self._member_seen[key] = now
        except Exception:  # учёт не должен ронять обработку
            logging.exception("tracker failed")
        return await handler(event, data)
