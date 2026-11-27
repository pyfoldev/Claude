"""ШАБЛОН: меню на inline-кнопках со страницами.

Формат callback_data: "<модуль>:<действие>:<владелец>:<аргумент>" — до 64 байт!
Вшиваем id владельца (того, кто вызвал меню), чтобы чужие нажатия отсекать.
Подключение: роутер в main.py (ROUTERS).
"""
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

router = Router(name="pager")
PREFIX = "pg"                          # уникальный префикс модуля, чтобы колбэки не пересекались с чужими
PAGE_SIZE = 5
ITEMS = [f"Пункт {i}" for i in range(1, 23)]     # ← ваши данные (в жизни — из db)


def render(page: int, owner: int) -> tuple[str, InlineKeyboardMarkup]:
    pages = max(1, (len(ITEMS) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    chunk = ITEMS[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    text = f"<b>Список</b> ({page + 1}/{pages})\n" + "\n".join(f"• {x}" for x in chunk)
    nav = [B(text="◀️", callback_data=f"{PREFIX}:go:{owner}:{page - 1}"),
           B(text=f"{page + 1}/{pages}", callback_data=f"{PREFIX}:noop:{owner}:0"),
           B(text="▶️", callback_data=f"{PREFIX}:go:{owner}:{page + 1}")]
    return text, InlineKeyboardMarkup(inline_keyboard=[nav, [B(text="✖️ Закрыть", callback_data=f"{PREFIX}:close:{owner}:0")]])


@router.message(F.text.lower() == "список")
async def open_list(message: Message) -> None:
    text, kb = render(0, message.from_user.id)
    await message.reply(text, reply_markup=kb)


@router.callback_query(F.data.startswith(f"{PREFIX}:"))
async def on_press(cb: CallbackQuery) -> None:
    _, action, owner, arg = cb.data.split(":")
    if cb.from_user.id != int(owner):                          # чужую кнопку нажать нельзя
        await cb.answer("Это меню открыл другой человек", show_alert=False)
        return
    if action == "close":
        await cb.message.delete()
    elif action == "go":
        text, kb = render(int(arg), int(owner))
        await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()                                           # ВСЕГДА отвечаем на callback, иначе кнопка «крутится»
