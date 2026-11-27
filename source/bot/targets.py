"""Кто цель команды: явный @ник/id важнее ответа на сообщение (иначе «бан @спамер» в ответ на жалобу забанит жалобщика)."""
from __future__ import annotations

import html

import re

from bot.db import USERNAMES, Database
from bot.fmt import Html

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{4,32}$")


def _username(user_id: int) -> str | None:
    u = USERNAMES.get(user_id)
    return u if u and _USERNAME_RE.match(u) else None


def mention(user_id: int, name: str, maxlen: int | None = None) -> Html:
    """Кликабельное имя (для списков, статистики, карточек). Ссылка по id (tg://user?id) у людей со скрытым аккаунтом
    в настройках приватности Telegram превращается в простой текст — поэтому, если известен @ник, ссылаемся по нику:
    такая ссылка открывает профиль всегда. maxlen обрезает длинное имя."""
    name = name or f"id{user_id}"
    if maxlen and len(name) > maxlen:
        name = name[: maxlen - 1] + "…"
    u = _username(user_id)
    href = f"https://t.me/{u}" if u else f"tg://user?id={user_id}"
    return Html(f'<a href="{href}">{html.escape(name)}</a>')


def listed(user_id: int, name: str, maxlen: int | None = None) -> Html:
    """Для списков: кликабельное имя и рядом @ник, чтобы было видно, кто именно (одинаковые и эмодзи-имена
    не путаются): «Саша (@sasha_k)». Ника нет — только имя."""
    u = _username(user_id)
    return Html(str(mention(user_id, name, maxlen)) + (f" (@{u})" if u else ""))


def ping(user_id: int, name: str) -> Html:
    """Позвать человека (общий сбор, капча): @ник присылает уведомление всегда; без ника — ссылка по id."""
    u = _username(user_id)
    if u:
        return Html(f"@{u}")
    return Html(f'<a href="tg://user?id={user_id}">{html.escape(name or f"id{user_id}")}</a>')


async def resolve_user(db: Database, token: str | None, reply_message) -> tuple[int, str] | None:
    """(id, имя) или None, если цель определить не удалось. reply_message — уже очищенный от сервисных ответов."""
    if token:
        if token.startswith("@"):
            uid = await db.find_user(token)
        else:
            uid = int(token)
            await db.ensure_user(uid)                  # неизвестный id — запоминаем и работаем дальше
        if uid is None:
            return None
        return uid, (await db.user_name(uid)) or f"id{uid}"
    if reply_message is not None and reply_message.from_user is not None:
        u = reply_message.from_user
        await db.ensure_user(u.id, u.username, u.full_name)
        return u.id, u.full_name
    return None
