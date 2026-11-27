"""Диагностика премиум-эмодзи при правке rich-сообщений.

    python bot.pyz probe <chat_id>            (или: python -m bot.probe_emoji <chat_id>)

BOT_TOKEN берётся из .env / окружения. Бот пришлёт в чат несколько тестовых сообщений, поправит каждое разными способами
и напечатает, что именно ответил Telegram: остались ли премиум-эмодзи в тексте и на кнопках. Каждое сообщение подписано
вариантом — посмотрите глазами, где эмодзи настоящие (анимированные), а где обычные, и пришлите вывод целиком.
Ничего не меняет в базе и настройках, работает отдельно от основного бота (остановите его на время теста, если он запущен
в polling — иначе будет конфликт только у него, тест на polling не влияет)."""
from __future__ import annotations

import asyncio
import json
import os
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InputRichMessage

from bot import emoji_inject, rich_ui
from bot.rich_ui import Btn, Screen


def has_emoji(obj) -> bool:
    """Есть ли в ответе Telegram узлы custom_emoji (в rich-теле, сущностях текста или иконках кнопок)."""
    if obj is None or isinstance(obj, bool):
        return False
    data = obj.model_dump(exclude_none=True) if hasattr(obj, "model_dump") else obj
    stack, found = [data], False
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if x.get("type") == "custom_emoji" or x.get("custom_emoji_id") or x.get("icon_custom_emoji_id"):
                found = True
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
    return found


def report(name: str, sent: bool, res) -> None:
    """Печатает итог варианта: что отправили и что вернул Telegram."""
    body = getattr(res, "rich_message", None)
    entities = getattr(res, "entities", None) or []
    markup = getattr(res, "reply_markup", None)
    print(f"\n=== {name}")
    print(f"  отправляли эмодзи:            {'да' if sent else 'нет'}")
    if isinstance(res, bool) or res is None:
        print(f"  ответ Telegram:               {res!r} (без тела — по ответу проверить нельзя, смотрите в чате)")
        return
    print(f"  эмодзи в rich-теле ответа:     {'да' if has_emoji(body) else 'НЕТ'}  (rich_message {'есть' if body is not None else 'нет'})")
    print(f"  эмодзи в сущностях текста:    {'да' if any(e.type == 'custom_emoji' for e in entities) else 'нет'}")
    print(f"  иконки эмодзи на кнопках:     {'да' if has_emoji(markup) else 'нет'}")
    if body is not None:
        print("  тело ответа:", json.dumps(body.model_dump(exclude_none=True), ensure_ascii=False)[:400])


async def attempt(name: str, sent: bool, coro) -> object:
    try:
        res = await coro
        report(name, sent, res)
        return res
    except Exception as e:
        print(f"\n=== {name}\n  ОШИБКА: {type(e).__name__}: {str(e)[:300]}")
        return None


def screen(label: str, with_buttons: bool = True) -> Screen:
    rows = [[Btn("🛡 Модерация", cb="probe:a"), Btn("📊 Статистика", cb="probe:b")]] if with_buttons else []
    return Screen(f"🛡 {label}", ["<i>Тест премиум-эмодзи: 🎮 🎭 ⚙️</i>", ("table", [("бан", "🚫 забанить"), ("мут", "🔇 заглушить")])], rows)


async def main(chat_id: int) -> None:
    from bot.config import load_config
    token = os.environ.get("BOT_TOKEN") or load_config().bot_token
    session = emoji_inject.EmojiSession()
    bot = Bot(token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True))
    me = await bot.me()
    print(f"Бот @{me.username}, чат {chat_id}, премиум-эмодзи в карте: {len(emoji_inject.load_map())}, RICH_UI={rich_ui.MODE}")
    rich_ui._off_until = 0.0
    try:
        # ---- 1. обычное сообщение: эталон (премиум-эмодзи в обычном тексте и правка обычного текста)
        m = await attempt("1. ОБЫЧНОЕ сообщение с <tg-emoji>", True, bot.send_message(
            chat_id, "1. обычное сообщение: 🛡 🎮 🎭", reply_markup=rich_ui.kb([[Btn("🛡 Кнопка", cb="probe:x")]])))
        if m:
            await attempt("1б. правка ОБЫЧНОГО текста", True, bot.edit_message_text(
                "1б. обычное после правки: 🛡 🎮 🎭", chat_id=chat_id, message_id=m.message_id,
                reply_markup=rich_ui.kb([[Btn("🛡 Кнопка", cb="probe:x")]])))

        # ---- 2. rich в HTML-форме: отправка и правки разными способами
        s = screen("2. rich HTML")
        m = await attempt("2. ОТПРАВКА rich (HTML-форма, как делает бот)", True, bot.send_rich_message(
            chat_id=chat_id, rich_message=rich_ui.to_payload(s, True), reply_markup=rich_ui.to_markup(s)))
        if m:
            s2 = screen("2а. правка как в боте (parse_mode=None)")
            await attempt("2а. ПРАВКА rich HTML, parse_mode=None (текущий способ)", True, bot.edit_message_text(
                chat_id=chat_id, message_id=m.message_id, rich_message=rich_ui.to_payload(s2, True),
                reply_markup=rich_ui.to_markup(s2), parse_mode=None, link_preview_options=None, disable_web_page_preview=None))
            s3 = screen("2б. правка со значениями по умолчанию")
            await attempt("2б. ПРАВКА rich HTML, parse_mode по умолчанию (как было раньше)", True, bot.edit_message_text(
                chat_id=chat_id, message_id=m.message_id, rich_message=rich_ui.to_payload(s3, True),
                reply_markup=rich_ui.to_markup(s3)))
            s4 = screen("2в. правка блоками")
            await attempt("2в. ПРАВКА rich БЛОКАМИ", True, bot.edit_message_text(
                chat_id=chat_id, message_id=m.message_id, rich_message=rich_ui.to_payload(s4, False),
                reply_markup=rich_ui.to_markup(s4), parse_mode=None, link_preview_options=None, disable_web_page_preview=None))
            s5 = screen("2г. правка без кнопок")
            await attempt("2г. ПРАВКА rich HTML, без клавиатуры", True, bot.edit_message_text(
                chat_id=chat_id, message_id=m.message_id, rich_message=rich_ui.to_payload(s5, True),
                parse_mode=None, link_preview_options=None, disable_web_page_preview=None))

        # ---- 3. rich блоками: отправка и правка блоками
        s = screen("3. rich блоки")
        m = await attempt("3. ОТПРАВКА rich БЛОКАМИ", True, bot.send_rich_message(
            chat_id=chat_id, rich_message=rich_ui.to_payload(s, False), reply_markup=rich_ui.to_markup(s)))
        if m:
            s2 = screen("3а. блоки → правка блоками")
            await attempt("3а. ПРАВКА блоками сообщения, отправленного блоками", True, bot.edit_message_text(
                chat_id=chat_id, message_id=m.message_id, rich_message=rich_ui.to_payload(s2, False),
                reply_markup=rich_ui.to_markup(s2), parse_mode=None, link_preview_options=None, disable_web_page_preview=None))

        # ---- 4. то же без нашей подмены эмодзи на кнопках (только тело)
        s = screen("4. rich без кнопок", with_buttons=False)
        m = await attempt("4. ОТПРАВКА rich без клавиатуры", True, bot.send_rich_message(
            chat_id=chat_id, rich_message=rich_ui.to_payload(s, True)))
        if m:
            s2 = screen("4а. правка без клавиатуры", with_buttons=False)
            await attempt("4а. ПРАВКА rich без клавиатуры", True, bot.edit_message_text(
                chat_id=chat_id, message_id=m.message_id, rich_message=rich_ui.to_payload(s2, True),
                parse_mode=None, link_preview_options=None, disable_web_page_preview=None))
    finally:
        await bot.session.close()
    print("\nГотово. Пришлите этот вывод целиком и скажите, в каких сообщениях в чате эмодзи настоящие (анимированные), "
          "а в каких обычные.")


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].lstrip("-").isdigit():
        sys.exit("Использование: python bot.pyz probe <chat_id>   (id чата — свой личный или группы, куда бот добавлен)")
    asyncio.run(main(int(sys.argv[1])))
