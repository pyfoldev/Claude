"""Проверка новичков по внешним базам спамеров.

Источники (оба публичные, id пользователя — единственное, что уходит наружу):
  • lols.bot (api.lols.bot) — работает без ключа, включён всегда;
  • CAS — Combot Anti-Spam (api.cas.chat) — теперь требует ключ API: он общий с Combot (combot.org → вход через Telegram →
    Settings → API key), задаётся в `.env` как CAS_API_KEY; без ключа CAS пропускается. Ключ уходит в заголовке Authorization.
Достаточно, чтобы любой источник назвал человека спамером. Режим в настройках («База спамеров»): off — выключено; warn —
уведомить модераторов; ban — сразу забанить. Ошибки и таймауты сети НЕ блокируют вход (нет ответа — считаем, что в базе нет).
Результаты кэшируются: 6 часов — найден, 1 час — нет."""
from __future__ import annotations

import asyncio
import html
import logging
import os
import re
import time

import aiohttp
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup

from bot import mod_service as ms
from bot import style
from bot.db import Database
from bot.ranks import need_rank
from bot.parsing import ModCommand
from bot.targets import mention

router = Router(name="cas")
URL = "https://api.cas.chat/check"
LOLS_URL = "https://api.lols.bot/account"
TIMEOUT = aiohttp.ClientTimeout(total=3)
TTL_FOUND, TTL_CLEAN = 6 * 3600, 3600
_cache: dict[int, tuple[float, bool]] = {}


_warned_auth = False


def has_key() -> bool:
    return bool(os.environ.get("CAS_API_KEY", "").strip())


async def _fetch_lols(user_id: int) -> bool | None:
    """lols.bot: {"ok": true, "user_id": N, "banned": false|true}. Ключ не нужен."""
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as s, s.get(LOLS_URL, params={"id": user_id}) as r:
            if r.status != 200:
                return None
            data = await r.json(content_type=None)
    except Exception as e:
        logging.info("lols: %s", e)
        return None
    if data.get("ok") is True and isinstance(data.get("banned"), bool):
        return data["banned"]
    return None


async def _fetch(user_id: int) -> bool | None:
    """Общий ответ источников: True — хотя бы один назвал спамером, False — все ответили «нет», None — узнать не удалось."""
    import asyncio
    res = await asyncio.gather(_fetch_lols(user_id), _fetch_cas(user_id))
    if any(r is True for r in res):
        return True
    return False if any(r is False for r in res) else None


async def _fetch_cas(user_id: int) -> bool | None:
    """CAS: True — в базе, False — нет, None — не удалось узнать (нет ключа, неверный ключ, сбой сети)."""
    global _warned_auth
    key = os.environ.get("CAS_API_KEY", "").strip()
    if not key:
        return None
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT, headers={"Authorization": f"Bearer {key}"}) as s, \
                s.get(URL, params={"user_id": user_id}) as r:
            if r.status == 401:
                if not _warned_auth:
                    _warned_auth = True
                    logging.warning("cas: ключ CAS_API_KEY отклонён (401) — проверка по базе спамеров не работает")
                return None
            if r.status != 200:
                return None
            data = await r.json(content_type=None)
    except Exception as e:
        logging.info("cas: %s", e)
        return None
    if data.get("ok") is True:
        return True
    return False if "not found" in str(data.get("description", "")).lower() else None


async def is_spammer(user_id: int, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    hit = _cache.get(user_id)
    if hit is not None and now < hit[0]:
        return hit[1]
    res = await _fetch(user_id)
    if res is None:
        return False                                            # не знаем — не мешаем входу
    if len(_cache) > 20000:
        _cache.clear()
    _cache[user_id] = (now + (TTL_FOUND if res else TTL_CLEAN), res)
    return res


async def handle(bot, db: Database, chat_id: int, user, mode: str | None = None) -> str | None:
    """Проверка при входе (в заявке или после вступления). Возвращает сработавший режим ('warn' | 'ban') или None.
    Бан/уведомление выполняется здесь; вызывающий код при 'ban' дальше капчу не выдаёт."""
    mode = mode or (await db.get_settings(chat_id)).get("cas_mode", "off")
    if mode == "off" or user.is_bot:
        return None
    if await db.cas_allowed(chat_id, user.id) or not await is_spammer(user.id):
        return None
    try:
        if mode == "ban":
            await bot.ban_chat_member(chat_id, user.id)
            await db.log_action(chat_id, (await bot.me()).id, user.id, "бан", "в базе спамеров", int(time.time()))
            kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="↩️ Это ошибка", callback_data=f"cas:ok:{user.id}")]])
            await bot.send_message(chat_id, style.warn(f"{mention(user.id, user.full_name)} в базе спамеров — забанен."),
                                   reply_markup=kb)
        else:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                B(text="🔨 Забанить", callback_data=f"cas:ban:{user.id}", style="danger"),
                B(text="✅ Это не спамер", callback_data=f"cas:ok:{user.id}")]])
            await bot.send_message(chat_id, style.warn(f"{mention(user.id, user.full_name)} есть в базе спамеров.")
                                   + "\n<i>Решает модератор.</i>", reply_markup=kb)
    except Exception:
        logging.exception("cas: действие не выполнилось")
    return mode


_CHECK_RE = re.compile(r"^(?:база спамеров|спам-база)(?:\s+(@\w+|\d{5,}))?$", re.IGNORECASE)


def _verdict(v: bool | None, no_key: bool = False) -> str:
    if no_key:
        return "пропущен (нет CAS_API_KEY)"
    return {True: "❗ в базе", False: "✅ нет в базе", None: "не ответил"}[v]


async def check_report(user_id: int) -> str:
    """Ответ по одному человеку: что говорит каждый источник (без кэша — проверка «вживую»)."""
    lols, cas_res = await asyncio.gather(_fetch_lols(user_id), _fetch_cas(user_id))
    return "\n".join([f"🚀 <b>База спамеров</b> · <code>{user_id}</code>",
                      f"lols.bot: {_verdict(lols)}", f"CAS: {_verdict(cas_res, no_key=not has_key())}"])


@router.message(F.chat.type.in_({"group", "supergroup", "private"}), F.text.func(lambda t: bool(t) and _CHECK_RE.match(t.strip()) is not None))
async def check_cmd(message, bot, db: Database) -> None:
    """«база спамеров @ник» (или ответом на сообщение): проверить человека по базам прямо сейчас. Модераторам и в личке владельцу."""
    from bot.targets import resolve_user
    if message.from_user is None:
        return
    if message.chat.type != "private" and await ms.effective_rank(bot, db, message.chat.id, message.from_user.id) < 1:
        return
    token = _CHECK_RE.match(message.text.strip()).group(1)
    target = await resolve_user(db, token, ms.real_reply(message)) if message.chat.type != "private" or token else None
    if target is None:
        await message.reply("Укажите @ник или id, либо ответьте на сообщение человека: <code>база спамеров @ник</code>")
        return
    await message.reply(await check_report(target[0]))


@router.callback_query(F.data.startswith("cas:"))
async def on_button(cb: CallbackQuery, bot, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or parts[1] not in ("ban", "ok") or not parts[2].isdigit() or cb.message is None:
        await cb.answer()
        return
    chat, uid = cb.message.chat.id, int(parts[2])
    if await ms.effective_rank(bot, db, chat, cb.from_user.id) < need_rank(await db.get_access(chat), "бан"):
        await cb.answer("Нужен ранг модератора", show_alert=True)
        return
    if parts[1] == "ban":
        allowed, why = await ms.can_act(bot, chat, cb.from_user.id, uid, "restrict", db=db, command="бан", allow_unknown=True)
        if not allowed:
            await cb.answer(why or "Недостаточно прав", show_alert=True)
            return
        try:
            await ms.apply(bot, db, ModCommand("бан", None, None, "в базе спамеров"),
                           chat, cb.from_user.id, uid, int(time.time()), gif=False)
            text = style.ok("Забанен.")
        except Exception as e:
            text = style.fail(f"Не получилось: {html.escape(str(e))}")
    else:                                                       # «это не спамер»: исключение для этого чата, бан снимается
        await db.cas_allow(chat, uid)
        try:
            await bot.unban_chat_member(chat, uid, only_if_banned=True)
        except Exception:
            pass
        text = style.ok("Оставлен: модератор решил, что это не спамер.")
    try:
        await cb.message.edit_text(text, reply_markup=None)
    except Exception:
        pass
    await cb.answer()
