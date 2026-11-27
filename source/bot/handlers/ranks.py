"""Ранги модераторов, «доступ команд» (ДК) и списки наказаний — по мотивам Ирис."""
import asyncio
import html
import logging
import re
import time
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.types import Message

from bot import style, ux
from bot.toggles import Enabled
from bot import mod_service as ms
from bot.db import Database
from bot.fmt import pre_table
from bot.ranks import DEFAULT_ACCESS, MAX_ASSIGNABLE, need_rank
from bot.targets import mention, resolve_user, listed

router = Router(name="ranks")
router.message.filter(Enabled("mod_on"))   # группу команд можно выключить в настройках → «Команды»

_T = r"(@\w+|\d{5,})"
_PATTERNS = [
    ("grant", r"^\+модер(?:\s+([1-5]))?(?:\s+" + _T + ")?$"),
    ("promote", r"^повысить(?:\s+" + _T + ")?$"),
    ("demote", r"^понизить(?:\s+" + _T + ")?$"),
    ("revoke", r"^снять(?:\s+" + _T + ")?$"),
    ("resign", r"^!?снимаю полномочия$"),
    ("list", r"^(?:кто админ|модеры)$"),
    ("acl_show", r"^дк$"),
    ("acl_set", r"^\+дк\s+(.+?)\s+([0-5])$"),
    ("acl_reset", r"^сброс дк$"),
    ("mutes", r"^муты$"),
    ("bans", r"^(?:банлист|баны)$"),
    ("warnlist", r"^варнлист$"),
    ("why", r"^причина(?:\s+" + _T + ")?$"),
    ("my_warns", r"^мои варны$"),
    ("warn_limit", r"^варны лимит\s+(\d{1,2})$"),
]
_COMPILED = [(k, re.compile(p, re.IGNORECASE)) for k, p in _PATTERNS]


@dataclass
class RankCmd:
    kind: str
    args: tuple


def parse_rank_cmd(text: str | None) -> RankCmd | None:
    t = re.sub(r"\s+", " ", (text or "").strip())
    for kind, rx in _COMPILED:
        m = rx.match(t)
        if m:
            return RankCmd(kind, m.groups())
    return None


async def _name(db: Database, uid: int) -> str:
    return mention(uid, (await db.user_name(uid)) or f"id{uid}")


def _left(until: int | None, now: int) -> str:
    if until is None:
        return "навсегда"
    mins = max((until - now) // 60, 1)
    return f"ещё {mins // 1440} д" if mins >= 1440 else (f"ещё {mins // 60} ч" if mins >= 60 else f"ещё {mins} мин")


@router.message(F.text.func(lambda t: parse_rank_cmd(t) is not None))
async def rank_cmd(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup"):
        return
    t0 = time.monotonic()
    cmd = parse_rank_cmd(message.text)
    chat, me = message.chat.id, message.from_user.id
    now = int(time.time())
    k = cmd.kind

    if k == "my_warns":
        n = await db.get_warns(chat, me)
        limit = (await db.get_settings(chat))["warn_limit"]
        await ux.tell(message, f"⚠️ У вас предупреждений: {n}/{limit}")
        return

    actor, access = await asyncio.gather(ms.effective_rank(bot, db, chat, me), db.get_access(chat))

    if k in ("mutes", "bans", "warnlist", "why", "list", "acl_show"):
        if actor < 1 and k != "list":
            return  # списки наказаний — для тех, у кого есть ранг
        await _lists(message, db, k, cmd, chat, now)
        return

    if k == "resign":
        if await db.get_rank(chat, me):
            await db.set_rank(chat, me, 0, me, now)
            await message.reply("🫡 Вы сложили полномочия.")
        return

    if k in ("acl_set", "acl_reset", "warn_limit"):
        if actor < need_rank(access, "настройки чата"):
            await message.reply("⚠️ Нужен ранг %d или выше." % need_rank(access, "настройки чата"))
            return
        if k == "acl_reset":
            await db.reset_access(chat)
            await message.reply("♻️ Доступ команд сброшен к значениям по умолчанию.")
        elif k == "warn_limit":
            n = int(cmd.args[0])
            if not 1 <= n <= 20:
                await ux.tell(message, "⚠️ Лимит варнов — от 1 до 20.")
                return
            await db.set_setting(chat, "warn_limit", n)
            await ux.tell(message, f"⚠️ Лимит предупреждений до автомута: {n}.")
        else:
            name, n = cmd.args[0].lower(), int(cmd.args[1])
            if n < 1:
                await ux.tell(message, "⚠️ Минимальный ранг — 1: открыть команду всем нельзя, это небезопасно.")
                return
            if name not in DEFAULT_ACCESS:
                await ux.tell(message, "❌ Не знаю такой команды. Список — <code>дк</code>.")
                return
            if n > actor:   # иначе модератор мог бы отнять команду у тех, кто выше его, или запереть настройки
                await ux.tell(message, f"❌ Нельзя требовать ранг выше вашего ({actor}).")
                return
            await db.set_access(chat, name, n)
            await db.log_action(chat, me, None, "дк", f"{name} → ранг {n}", now)       # журнал доступа: «лог дк»
            await message.reply(f"🔧 Команда «{html.escape(name)}»: нужен ранг {n}.")
        return

    # grant / promote / demote / revoke
    if actor < need_rank(access, "модер"):
        if k == "grant":
            await message.reply("⚠️ Нужен ранг %d или выше." % need_rank(access, "модер"))
        return
    token = cmd.args[1] if k == "grant" else cmd.args[0]
    target = await resolve_user(db, token, ms.real_reply(message))
    if target is None:
        if k == "grant":
            await ux.tell(message, "⚠️ Ответьте командой на сообщение человека или укажите @ник.")
        return
    tid, _ = target
    bot_id = (await bot.me()).id if tid != me else 0
    if tid == me or tid == bot_id:
        await ux.tell(message, "⚠️ Себе или боту ранг менять нельзя.")
        return
    old, eff = await asyncio.gather(db.get_rank(chat, tid), ms.effective_rank(bot, db, chat, tid))
    if max(old, eff) >= actor:
        await ux.tell(message, "⚠️ Ранг этого человека не ниже вашего: менять его нельзя.")
        return
    if k == "grant":
        new = int(cmd.args[0]) if cmd.args[0] else 1
    elif k == "promote":
        new = old + 1
    elif k == "demote":
        new = old - 1
    else:
        new = 0
        if not old:
            return
    if new >= actor or new > MAX_ASSIGNABLE:
        await ux.tell(message, f"⚠️ Выдать можно ранг не выше {min(actor - 1, MAX_ASSIGNABLE)}.")
        return
    if k == "demote" and old == 0:
        return
    await db.set_rank(chat, tid, new, me, now)
    await db.log_action(chat, me, tid, "ранг", f"{old}→{new}", now)
    who = await _name(db, tid)
    await message.reply(f"🎖 {who}: ранг {new}" if new else f"🎖 {who} больше не модератор.")
    logging.info("ранг %s→%s выдан за %.0f мс (до ответа в чат)", old, new, (time.monotonic() - t0) * 1000)
    ux._spawn(ux.sync_tag(bot, chat, tid, new))                  # тег рядом с ником (Bot API 9.5) — в фоне, ответ не ждёт Telegram


async def _plain(db: Database, uid: int):
    return listed(uid, (await db.user_name(uid)) or f"id{uid}", 28)


async def _lists(message: Message, db: Database, k: str, cmd: RankCmd, chat: int, now: int) -> None:
    if k == "list":
        rows = await db.list_ranks(chat)
        table = pre_table([(str(r["rank"]), await _plain(db, r["user_id"])) for r in rows],
                          header=("Ранг", "Модератор"), maxw=(4, 24)) if rows else "Пока никого."
        await message.reply(f"🎖 <b>Модераторы</b>\n{table}\n<i>Админы Telegram — ранг 3, создатель — 5.</i>")
    elif k == "acl_show":
        access = await db.get_access(chat)
        table = pre_table([(name + (" *" if name in access else ""), str(need_rank(access, name))) for name in DEFAULT_ACCESS],
                          header=("Команда", "Ранг"), align="lr", maxw=(18, 4))
        await message.reply(f"🔧 <b>Доступ команд</b>\n{table}\n<i>* — изменено. Изменить: </i><code>+дк бан 4</code><i>, сбросить: </i><code>сброс дк</code>")
    elif k in ("mutes", "bans"):
        kind = "mute" if k == "mutes" else "ban"
        rows = await db.list_state(chat, kind, now)
        if not rows:
            await message.reply("ℹ️ Список пуст.")
            return
        table = pre_table([(await _plain(db, r["user_id"]), _left(r["until"], now), r["reason"] or "") for r in rows[:25]],
                          header=("Участник", "Срок", "Причина"), maxw=(16, 9, 14))
        await message.reply(("🔇 <b>Муты</b>" if kind == "mute" else "🔨 <b>Баны</b>") + f" · {len(rows)}\n{table}")
    elif k == "warnlist":
        rows = await db.list_warns(chat)
        limit = (await db.get_settings(chat))["warn_limit"]
        if not rows:
            await ux.tell(message, "⚠️ Предупреждений ни у кого нет.")
            return
        table = pre_table([(await _plain(db, u), f"{n}/{limit}") for u, n in rows[:25]],
                          header=("Участник", "Варны"), align="lr", maxw=(22, 6))
        from bot.db import USERNAMES
        trows = [[((await db.user_name(u)) or f"id{u}", f"https://t.me/{USERNAMES[u]}" if USERNAMES.get(u) else f"tg://user?id={u}"),
                  f"{n}/{limit} {style.bar(n, limit)}"] for u, n in rows[:25]]
        await ux.table_or_text(message, "Предупреждения", ["Участник", "Варны"], trows,
                               f"⚠️ <b>Предупреждения</b>\n{table}", aligns=["left", "right"])
    elif k == "why":
        target = await resolve_user(db, cmd.args[0], ms.real_reply(message))
        if target is None:
            return
        tid = target[0]
        for kind, label in (("ban", "забанен"), ("mute", "в муте")):
            st = await db.get_state(chat, tid, kind, now)
            if st:
                by = await _name(db, st["actor"])
                await message.reply(f"ℹ️ {await _name(db, tid)} {label} ({_left(st['until'], now)}). "
                                    f"Причина: {html.escape(st['reason'] or 'не указана')}. Выдал: {by}.",
                                    disable_web_page_preview=True)
                return
        await message.reply("ℹ️ Активных наказаний нет.")
