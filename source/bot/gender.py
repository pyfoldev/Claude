"""Пол пользователя для РП, семьи и пары: правильные окончания и местоимения. Пол выбирает сам человек (кнопки), хранится один раз.

В текстах: ⟦ушёл|ушла⟧ — мужской|женский вариант (gz). Пол неизвестен — «ушёл(ла)»-подобная запись «ушёл/ушла»."""
from __future__ import annotations

import re

from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot.db import Database

_TOKEN = re.compile(r"⟦([^|⟧]*)\|([^⟧]*)⟧")
LABEL = {"m": "👨 Мужской", "f": "👩 Женский"}
_cache: dict[int, str | None] = {}


def gz(text: str, gender: str | None) -> str:
    """Подставить род: m → первый вариант, f → второй, неизвестно → «первый/второй»."""
    def pick(m: re.Match) -> str:
        a, b = m.group(1), m.group(2)
        return a if gender == "m" else b if gender == "f" else f"{a}/{b}"
    return _TOKEN.sub(pick, text)


async def get(db: Database, uid: int) -> str | None:
    if uid in _cache:
        return _cache[uid]
    cur = await db.conn.execute("SELECT gender FROM user_gender WHERE user_id=?", (uid,))
    r = await cur.fetchone()
    g = r["gender"] if r else None
    _cache[uid] = g
    return g


async def put(db: Database, uid: int, gender: str) -> None:
    if gender not in ("m", "f"):
        return
    await db.conn.execute("INSERT INTO user_gender(user_id, gender) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET gender=excluded.gender",
                          (uid, gender))
    await db.conn.commit()
    _cache[uid] = gender


async def say(db: Database, uid: int, text: str) -> str:
    """Текст с ⟦м|ж⟧ по полу этого человека."""
    return gz(text, await get(db, uid))


def kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text=LABEL["m"], callback_data=f"gd:{uid}:m"),
                                                  B(text=LABEL["f"], callback_data=f"gd:{uid}:f")]])


async def ensure(message: Message, db: Database) -> bool:
    """True — пол известен, команду можно выполнять. Иначе просим выбрать кнопкой (нажать может только автор команды)."""
    u = message.from_user
    if u is None or await get(db, u.id):
        return True
    await message.reply("Сначала скажи, ты парень или девушка: так я не буду путать окончания и местоимения. "
                        "Потом повтори команду.", reply_markup=kb(u.id))
    return False


async def on_pick(cb: CallbackQuery, db: Database) -> None:
    parts = (cb.data or "").split(":")
    if len(parts) != 3 or not parts[1].isdigit() or parts[2] not in ("m", "f"):
        await cb.answer()
        return
    if cb.from_user.id != int(parts[1]):
        await cb.answer("Это не твой выбор", show_alert=True)
        return
    await put(db, cb.from_user.id, parts[2])
    await cb.answer("Запомнила ✅")
    if cb.message:
        word = "парень" if parts[2] == "m" else "девушка"
        try:
            await cb.message.edit_text(f"✅ Запомнила: {word}. Повтори команду. Поменять можно: <code>мой пол</code>.")
        except Exception:
            pass
