"""Вход в веб-панель (Mini App): кнопки web_app работают только в личке, из группы ведёт кнопка-ссылка в личку бота."""
import re

from aiogram import F, Router
from aiogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup, Message, WebAppInfo

from bot import ux
from bot import mod_service as ms
from bot.db import Database

router = Router(name="webpanel")
_CMD = re.compile(r"^(?:веб[-\s]?панель|/webpanel(?:@\w+)?)$", re.IGNORECASE)
_START = re.compile(r"^/start panel_(-?\d{1,20})$")


def panel_button(webapp_url: str, chat_id: int | None = None) -> B:
    url = f"{webapp_url}/panel" + (f"?chat={chat_id}" if chat_id is not None else "")
    return B(text="🌐 Открыть веб-панель", web_app=WebAppInfo(url=url))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: bool(t) and _CMD.match(t.strip()) is not None))
async def group_cmd(message: Message, bot, db: Database, webapp_url: str = "") -> None:
    if message.from_user is None or not webapp_url:
        return
    if await ms.effective_rank(bot, db, message.chat.id, message.from_user.id) < 1:
        return    # панель — для модераторов; остальным команда — просто слова
    username = (await bot.me()).username
    kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="🌐 Веб-панель чата", url=f"https://t.me/{username}?start=panel_{message.chat.id}")]])
    await message.reply("Откройте панель в личке с ботом (права проверяются при каждом действии):", reply_markup=kb)


@router.message(F.chat.type == "private", F.text.func(lambda t: bool(t) and _START.match(t.strip()) is not None))
async def start_panel(message: Message, webapp_url: str = "") -> None:
    if not webapp_url:
        await ux.tell(message, "⚠️ WEBAPP_URL не настроен — веб-панель недоступна.")
        return
    chat_id = int(_START.match(message.text.strip()).group(1))
    await message.answer("Панель чата. Видны только те разделы, на которые у вас есть права:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[panel_button(webapp_url, chat_id)]]))


@router.message(F.chat.type == "private", F.text.func(lambda t: bool(t) and _CMD.match(t.strip()) is not None))
async def private_cmd(message: Message, webapp_url: str = "") -> None:
    if not webapp_url:
        await ux.tell(message, "⚠️ WEBAPP_URL не настроен — веб-панель недоступна.")
        return
    await message.answer("Веб-панель: настройки чатов (для админов и модераторов) и управление ботом (для владельца).",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[panel_button(webapp_url)]]))
