"""Двойники забаненных: при входе сравниваем имя и @ник новичка с теми, кого в этом чате уже банили (последние 180 дней).
Совпадение — не приговор, а повод для модератора: бот пишет уведомление с кнопками «Забанить» и «Это не он»."""
from __future__ import annotations

import difflib
import html
import logging
import re
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup

from bot import mod_service as ms
from bot import style
from bot.db import Database
from bot.ranks import need_rank
from bot.parsing import ModCommand
from bot.targets import mention

router = Router(name="dupes")
THRESHOLD = 0.85
MIN_LEN = 4
WINDOW = 180 * 86400
_LOOK = str.maketrans({"а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y", "і": "i", "ё": "e",
                       "0": "o", "1": "l", "3": "e", "5": "s", "@": "a", "$": "s"})


def norm(s: str | None) -> str:
    """Имя без регистра, пробелов, знаков и с заменой букв-двойников: «Аdmin_01» и «admin01» совпадут."""
    s = (s or "").casefold().translate(_LOOK)
    return re.sub(r"[\W_]+", "", s)


def similarity(a: str | None, b: str | None) -> float:
    x, y = norm(a), norm(b)
    if len(x) < MIN_LEN or len(y) < MIN_LEN:
        return 0.0
    return difflib.SequenceMatcher(None, x, y).ratio()


AVATAR_MAX_DIST = 6        # из 64 бит: чем меньше, тем строже (0 — одинаковая картинка)


def dhash(img) -> int:
    """Перцептивный хеш dHash 8×8: устойчив к сжатию, масштабу и лёгкой обрезке."""
    g = img.convert("L").resize((9, 8))
    px = list(g.get_flattened_data()) if hasattr(g, "get_flattened_data") else list(g.getdata())
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | (1 if px[row * 9 + col] > px[row * 9 + col + 1] else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


async def avatar_hash(bot, user_id: int) -> int | None:
    """dHash текущей аватарки пользователя (None — аватарки нет или Telegram её не отдал)."""
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if not photos.total_count or not photos.photos:
            return None
        size = sorted(photos.photos[0], key=lambda s: s.width * s.height)[0]     # самая маленькая версия: хватает для хеша
        from bot import media
        data = await media.download(bot, size.file_id, getattr(size, "file_size", None), 2 * 1024 * 1024)
        if not data:
            return None
        import io
        from PIL import Image
        with Image.open(io.BytesIO(data)) as img:
            return dhash(img)
    except Exception as e:
        logging.info("avatar hash: %s", e)
        return None


async def remember_avatar(bot, db: Database, user_id: int) -> None:
    """Сохраняем хеш аватарки (например, при бане), чтобы потом узнать двойника по картинке."""
    h = await avatar_hash(bot, user_id)
    if h is not None:
        await db.avatar_hash_set(user_id, h, int(time.time()))


async def find_match(db: Database, chat_id: int, user, now: int | None = None, bot=None):
    """(id, имя, сходство 0..1, причина) самого похожего из забаненных в чате или None. Сходство — по имени/@нику
    и, если задан bot, по аватарке (картинка совпала — это сильный признак, сходство не ниже 0.95)."""
    now = int(time.time()) if now is None else now
    ids = [uid for uid in await db.banned_ids(chat_id, now - WINDOW) if uid != user.id]
    new_hash = await avatar_hash(bot, user.id) if bot is not None and ids else None
    hashes = await db.avatar_hashes(ids) if new_hash is not None else {}
    best = None
    users = await db.users_by_ids(ids)
    for uid in ids:
        old_name = users.get(uid, {}).get("name")
        old_nick = users.get(uid, {}).get("username")
        score = max(similarity(user.full_name, old_name), similarity(user.username, old_nick),
                    similarity(user.full_name, old_nick), similarity(user.username, old_name))
        reason = "имя" if score >= THRESHOLD else ""
        if uid in hashes and hamming(new_hash, hashes[uid]) <= AVATAR_MAX_DIST:
            score, reason = max(score, 0.95), ("имя и аватарка" if reason else "аватарка")
        if score >= THRESHOLD and (best is None or score > best[2]):
            best = (uid, old_name or f"id{uid}", score, reason)
    return best


async def check_join(bot, db: Database, chat_id: int, user) -> None:
    """Вызывается при входе. Ошибки не должны ломать капчу."""
    try:
        m = await find_match(db, chat_id, user, bot=bot)
        if m is None:
            return
        uid, old_name, score, reason = m
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            B(text="🔨 Забанить", callback_data=f"dup:ban:{user.id}", style="danger"),
            B(text="✅ Это не он", callback_data=f"dup:ok:{user.id}")]])
        await bot.send_message(
            chat_id, style.warn(f"{mention(user.id, user.full_name)} похож на забаненного "
                                f"<b>{html.escape(old_name)}</b> (сходство {int(score * 100)}%, совпало: {reason}).") + "\n<i>Решает модератор.</i>",
            reply_markup=kb)
    except Exception:
        logging.exception("dupes: проверка входа не удалась")


@router.callback_query(F.data.startswith("dup:"))
async def on_button(cb: CallbackQuery, bot, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or parts[1] not in ("ban", "ok") or not parts[2].isdigit() or cb.message is None:
        await cb.answer()
        return
    chat, uid = cb.message.chat.id, int(parts[2])
    rank = await ms.effective_rank(bot, db, chat, cb.from_user.id)
    if rank < need_rank(await db.get_access(chat), "бан"):
        await cb.answer("Нужен ранг модератора", show_alert=True)
        return
    if parts[1] == "ban":
        allowed, why = await ms.can_act(bot, chat, cb.from_user.id, uid, "restrict", db=db, command="бан", allow_unknown=True)
        if not allowed:
            await cb.answer(why or "Недостаточно прав", show_alert=True)
            return
        try:
            await ms.apply(bot, db, ModCommand("бан", None, None, "двойник забаненного"),
                           chat, cb.from_user.id, uid, int(time.time()), gif=False)
            text = style.ok("Забанен.")
        except Exception as e:
            text = style.fail(f"Не получилось: {html.escape(str(e))}")
    else:
        text = style.ok("Оставлен: модератор решил, что это не двойник.")
    try:
        await cb.message.edit_text(text, reply_markup=None)
    except Exception:
        pass
    await cb.answer()
