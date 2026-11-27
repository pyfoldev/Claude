"""Логика модерации без привязки к хендлерам (легко тестировать)."""
from __future__ import annotations

import html
import time
from datetime import timedelta

from aiogram.types import ChatPermissions

from bot.db import Database
from bot.emoji import emoji
from bot.fmt import quote
from bot import punish_gifs
from bot.parsing import ModCommand

DEFAULT_MUTE = 3600
WARN_MUTE = 86400
NEED_HINT = "Напишите команду ответом на сообщение нарушителя или укажите @username / id."

_FULL = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True,
    can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
    can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
    can_add_web_page_previews=True, can_invite_users=True,
)
_MUTED = ChatPermissions(can_send_messages=False)

_RIGHT_ATTR = {
    "restrict": "can_restrict_members",
    "delete": "can_delete_messages",
    "pin": "can_pin_messages",
}


ANON_ADMIN_ID = 1087968824  # GroupAnonymousBot: так Telegram подписывает сообщения анонимных админов


def is_anonymous_admin(message) -> bool:
    """Сообщение от анонимного админа группы: автор — GroupAnonymousBot, а отправитель — сам чат.
    Без проверки sender_chat id бота нельзя считать правом админа."""
    sc = getattr(message, "sender_chat", None)
    return bool(message.from_user and message.from_user.id == ANON_ADMIN_ID
                and sc is not None and sc.id == message.chat.id)


MEMBER_TTL = 30          # статус участника (права админа и т. п.) помним 30 с
_members: dict[tuple[int, int], tuple[float, object]] = {}


async def get_member(bot, chat_id: int, user_id: int):
    """getChatMember с коротким кэшем. Одна команда модерации раньше спрашивала Telegram 2–3 раза подряд (права автора
    дважды + цель) — это сотни миллисекунд сети. Кэш сбрасывается, когда Telegram сообщает о смене статуса
    (bot.middlewares.tracker) и после наших же наказаний (apply), так что устаревшие права не живут."""
    key, now = (chat_id, user_id), time.monotonic()
    hit = _members.get(key)
    if hit is not None and now - hit[0] < MEMBER_TTL:
        return hit[1]
    m = await bot.get_chat_member(chat_id, user_id)
    if len(_members) > 50000:
        _members.clear()
    _members[key] = (now, m)
    return m


def forget_member(chat_id: int, user_id: int) -> None:
    _members.pop((chat_id, user_id), None)


async def is_admin(bot, chat_id: int, user_id: int) -> bool:
    m = await get_member(bot, chat_id, user_id)
    return m.status in ("administrator", "creator")


async def can_act(bot, chat_id: int, actor_id: int, target_id: int | None, right: str,
                  db: Database | None = None, command: str | None = None,
                  allow_unknown: bool = False) -> tuple[bool, str]:
    """Проверка прав автора и допустимости цели. target_id=None — цели нет (удаление/закреп).

    Если переданы db и command, действует система рангов: нужен эффективный ранг не ниже, чем указано
    в «доступе команд» (по умолчанию — bot.ranks.DEFAULT_ACCESS). Telegram-админ с нужным правом = ранг 3,
    создатель = 5. Без db работает старая проверка по правам Telegram.
    allow_unknown: цель, которую Telegram не отдаёт как участника (вышла из чата, не писала), не отклоняется —
    её всё равно можно забанить по id. Админов и ранги это не обходит.
    """
    anon = actor_id == ANON_ADMIN_ID  # анонимный админ: личность неизвестна, права — как у админа с рангом 3
    if anon:
        tg_ok, status = True, "administrator"
    else:
        actor = await get_member(bot, chat_id, actor_id)
        status = actor.status
        if status in ("left", "kicked") or (status == "restricted" and not getattr(actor, "is_member", False)):
            return False, "Команда доступна только участникам чата."
        tg_ok = status == "creator" or (
            status == "administrator" and getattr(actor, _RIGHT_ATTR[right], False))
    effective = None
    if db is not None and command is not None:
        from bot.ranks import need_rank, tg_rank
        explicit = 0 if anon else await db.get_rank(chat_id, actor_id)
        effective = max(explicit, tg_rank(status, tg_ok))
        need = need_rank(await db.get_access(chat_id), command)
        if need > 0 and effective < need:
            return False, ("Для этой команды нужен ранг не ниже %d." % need) if effective else \
                "Эта команда только для модераторов."
    elif not tg_ok:
        return False, "Эта команда только для админов с нужным правом."
    if target_id is not None:
        if target_id == actor_id:
            return False, "Себя трогать нельзя."
        if target_id == (await bot.me()).id:
            return False, "Меня трогать нельзя 🙂"
        try:
            t = await get_member(bot, chat_id, target_id)
        except Exception:
            if not allow_unknown:
                return False, "Не нашёл такого пользователя в этом чате."
            t = None
        if t is not None and t.status in ("administrator", "creator"):
            return False, "Администраторов трогать нельзя."
        if db is not None and effective is not None:
            target_rank = await db.get_rank(chat_id, target_id)
            if target_rank > 0 and target_rank >= effective:
                return False, "Ранг цели не ниже вашего."
    return True, ""


async def effective_rank(bot, db: Database, chat_id: int, user_id: int) -> int:
    """Выше из: выданный ранг и ранг по статусу в Telegram (создатель 5, админ с правом ограничивать 3)."""
    from bot.ranks import tg_rank
    explicit = await db.get_rank(chat_id, user_id)
    try:
        m = await get_member(bot, chat_id, user_id)
    except Exception:   # При сбое проверки членства не выдаём доступ к административным функциям.
        return 0
    if m.status in ("left", "kicked") or (m.status == "restricted" and not getattr(m, "is_member", False)):
        return 0
    can = getattr(m, "can_restrict_members", False) if m.status == "administrator" else False
    return max(explicit, tg_rank(m.status, can))


def real_reply(message):
    """Сообщение, на которое ответили. Сервисное сообщение темы форума — не ответ."""
    r = message.reply_to_message
    if r is None or getattr(r, "forum_topic_created", None) is not None:
        return None
    return r


async def resolve_target(bot, db: Database, cmd: ModCommand, reply_user_id: int | None) -> tuple[int | None, str]:
    """Явно указанная цель (@username/id) важнее ответа; иначе берём автора сообщения, на которое ответили."""
    if cmd.target:
        if not cmd.target.startswith("@"):
            await db.ensure_user(int(cmd.target))      # id запоминаем сразу, без «не знаю такого»
            return int(cmd.target), ""
        uid = await db.find_user(cmd.target)           # база, затем Telegram
        if uid is None:
            return None, f"Не нашёл {html.escape(cmd.target)} — ответьте командой на его сообщение или укажите id."
        return uid, ""
    if reply_user_id:
        await db.ensure_user(reply_user_id)
        return reply_user_id, ""
    return None, NEED_HINT


async def mention(bot, db: Database, chat_id: int, user_id: int) -> str:
    name = await db.user_name(user_id)
    if not name:
        try:
            name = (await bot.get_chat_member(chat_id, user_id)).user.first_name
        except Exception:
            name = f"id{user_id}"
    from bot.targets import mention as _mention
    return str(_mention(user_id, name))


def _fmt_dur(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400} дн."
    if seconds % 3600 == 0:
        return f"{seconds // 3600} ч."
    return f"{max(seconds // 60, 1)} мин."


async def _mute(bot, chat_id: int, target_id: int, until: int) -> None:
    await bot.restrict_chat_member(chat_id, target_id, permissions=_MUTED, until_date=until)


def _reason_line(reason: str) -> str:
    """Короткая причина — строкой, длинная — цитатой."""
    if not reason:
        return ""
    return f"\nПричина: {html.escape(reason)}" if len(reason) <= 60 else "\nПричина:\n" + quote(html.escape(reason), expandable=False)


def _bar(n: int, limit: int) -> str:
    """Шкала предупреждений: ▰▰▱ — сразу видно, сколько осталось до мута."""
    limit = max(limit, 1)
    n = max(0, min(n, limit))
    return "▰" * n + "▱" * (limit - n)


_avatar_tasks: set = set()


def _remember_avatar_later(bot, db: Database, user_id: int) -> None:
    """Хеш аватарки забаненного — в фоне, чтобы бан не ждал Telegram (нужен для поиска двойников)."""
    import asyncio
    from bot import dupes
    t = asyncio.create_task(dupes.remember_avatar(bot, db, user_id))
    _avatar_tasks.add(t)
    t.add_done_callback(_avatar_tasks.discard)


async def apply(bot, db: Database, cmd: ModCommand, chat_id: int, actor_id: int,
                target_id: int, now: int, gif: bool = True) -> str:
    who = await mention(bot, db, chat_id, target_id)
    reason = _reason_line(cmd.reason)
    name = cmd.name
    logged: int | None = None  # срок наказания в секундах для истории (None — без срока / не применимо)
    logged_already = False
    cfg0 = await db.get_settings(chat_id) if name in ("бан", "мут", "варн") else {}
    if name == "бан" and cmd.duration is None and cfg0.get("ban_secs"):
        cmd = ModCommand(cmd.name, cmd.target, timedelta(seconds=cfg0["ban_secs"]), cmd.reason, cmd.silent, cmd.delete_msg)
    if name == "бан":
        until = now + int(cmd.duration.total_seconds()) if cmd.duration else None
        logged = int(cmd.duration.total_seconds()) if cmd.duration else None
        await bot.ban_chat_member(chat_id, target_id, until_date=until)
        await db.set_state(chat_id, target_id, "ban", until, cmd.reason, actor_id, now)
        _remember_avatar_later(bot, db, target_id)
        text = f"{emoji('ban')} {who} забанен" + (
            f" на {_fmt_dur(int(cmd.duration.total_seconds()))}" if cmd.duration else "") + reason
    elif name == "разбан":
        await bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
        await db.clear_state(chat_id, target_id, "ban")
        text = f"{emoji('ok')} {who} разбанен"
    elif name == "мут":
        secs = int(cmd.duration.total_seconds()) if cmd.duration else (cfg0.get("mute_secs") or DEFAULT_MUTE)
        logged = secs
        await _mute(bot, chat_id, target_id, now + secs)
        await db.set_state(chat_id, target_id, "mute", now + secs, cmd.reason, actor_id, now)
        text = f"{emoji('mute')} {who} в муте на {_fmt_dur(secs)}" + reason
    elif name == "размут":
        await bot.restrict_chat_member(chat_id, target_id, permissions=_FULL)
        await db.clear_state(chat_id, target_id, "mute")
        text = f"{emoji('unmute')} {who} может писать снова"
    elif name == "кик":
        await bot.ban_chat_member(chat_id, target_id)
        await bot.unban_chat_member(chat_id, target_id)
        text = f"{emoji('kick')} {who} исключён" + reason
    elif name == "варн":
        cfg = await db.get_settings(chat_id)
        limit = cfg["warn_limit"]
        if cmd.duration:
            ttl = int(cmd.duration.total_seconds())
        else:
            ttl = cfg["warn_ttl_days"] * 86400 or None   # 0 дней = бессрочно
        logged = ttl
        n = await db.add_warn(chat_id, target_id, now=now, ttl=ttl, reason=cmd.reason, actor=actor_id)
        text = f"{emoji('warn')} {who}: предупреждение {n}/{limit} {_bar(n, limit)}" + (
            f" (действует {_fmt_dur(ttl)})" if ttl else "") + reason
        if n >= limit:
            # варн пишем в журнал раньше авто-мута: тогда «откат» снимает именно мут, а не уже сброшенный варн
            await db.log_action(chat_id, actor_id, target_id, name, cmd.reason, now, logged)
            logged_already = True
            act = cfg.get("warn_action", "mute")
            wsecs = cfg.get("warn_secs") or WARN_MUTE
            if act == "ban":
                until = now + wsecs if cfg.get("warn_secs") else None
                await bot.ban_chat_member(chat_id, target_id, until_date=until)
                await db.set_state(chat_id, target_id, "ban", until, "лимит предупреждений", actor_id, now)
                await db.log_action(chat_id, actor_id, target_id, "бан", "лимит предупреждений", now, wsecs if until else None)
                text += f"\n{emoji('ban')} Лимит достигнут — бан" + (f" на {_fmt_dur(wsecs)}." if until else ".")
            elif act == "kick":
                await bot.ban_chat_member(chat_id, target_id)
                await bot.unban_chat_member(chat_id, target_id)
                await db.log_action(chat_id, actor_id, target_id, "кик", "лимит предупреждений", now)
                text += f"\n{emoji('kick')} Лимит достигнут — исключён."
            else:
                await _mute(bot, chat_id, target_id, now + wsecs)
                await db.set_state(chat_id, target_id, "mute", now + wsecs, "лимит предупреждений", actor_id, now)
                await db.log_action(chat_id, actor_id, target_id, "мут", "лимит предупреждений", now, wsecs)
                text += f"\n{emoji('mute')} Лимит достигнут — мут на {_fmt_dur(wsecs)}."
            await db.reset_warns(chat_id, target_id, now=now)
    elif name == "снять варн":
        n = await db.remove_warn(chat_id, target_id, now=now)
        text = f"{emoji('ok')} {who}: предупреждений {n}"
    elif name == "варны":
        n = await db.get_warns(chat_id, target_id, now)
        limit = (await db.get_settings(chat_id))["warn_limit"]
        return f"{emoji('warn')} {who}: предупреждений {n}/{limit} {_bar(n, limit)}"
    else:
        raise ValueError(name)
    if not logged_already:
        await db.log_action(chat_id, actor_id, target_id, name, cmd.reason, now, logged)
    forget_member(chat_id, target_id)          # статус цели поменялся — следующая проверка спросит Telegram заново
    if gif and name in punish_gifs.FILES and (await db.get_settings(chat_id)).get("mod_gif", 1):
        punish_gifs.arm(bot, chat_id, text, name)
    return text


async def punish(bot, db: Database, chat_id: int, user_id: int, action: str, reason: str, now: int) -> str:
    """Наказание от имени бота (антиспам/18+): delete — только уведомление, warn — варн, mute — мут на 1 час."""
    if action in ("warn", "mute"):
        cmd = ModCommand("варн" if action == "warn" else "мут", None, None, reason)
        return await apply(bot, db, cmd, chat_id, (await bot.me()).id, user_id, now)
    who = await mention(bot, db, chat_id, user_id)
    await db.log_action(chat_id, (await bot.me()).id, user_id, "удаление", reason, now)
    if len(reason) <= 40:
        return f"{emoji('fail')} {who}: сообщение удалено ({html.escape(reason)})"
    return f"{emoji('fail')} {who}: сообщение удалено\n" + quote(html.escape(reason), expandable=False)
