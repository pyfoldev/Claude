"""Мастер первой настройки: при добавлении бота в группу — проверка прав/приватности и кнопки основных функций."""
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardButton as B, InlineKeyboardMarkup

from bot import rich_ui
from bot.rich_ui import Btn, Screen
from bot.db import Database
from bot.diagnostics import diagnose_chat
from bot.mod_service import is_admin

router = Router(name="setup")

# (ключ настройки, подпись) — только эти ключи можно менять из мастера
WIZARD = [("captcha_on", "Капча"), ("spam_on", "Антиспам"), ("phish_on", "Фишинг-ссылки"), ("raid_on", "Антирейд"), ("nsfw_on", "Фильтр 18+"),
          ("transcribe_on", "Расшифровка голосовых"), ("ai_on", "ИИ"), ("spam_ai", "ИИ-проверка новичков")]
_KEYS = {k for k, _ in WIZARD}
RESEND_AFTER = 3600
_sent: dict[int, float] = {}   # чат -> когда последний раз присылали мастер


def render(cfg: dict, report: str, webapp_url: str = "", panel_url: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    text = "👋 <b>Первая настройка</b>\n\n" + report
    if cfg.get("captcha_on") and not webapp_url:
        text += "\n\n⚠️ Капча включена, но у бота не задан WEBAPP_URL — она работать не будет."
    text += "\n\nВключите нужное (только админы). Остальное — в разделе «Все настройки»."
    rows = [[B(text=f"{'✅' if cfg[key] else '❌'} {label}", callback_data=f"wiz:{key}:{0 if cfg[key] else 1}",
               style="success" if cfg[key] else None)] for key, label in WIZARD]
    rows.append([B(text="⚙️ Все настройки", callback_data="cfg:home"), B(text="📖 Меню", callback_data="menu:home")])
    if panel_url:
        rows.append([B(text="🌐 Открыть как приложение", url=panel_url, style="primary")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def screen(cfg: dict, report: str, webapp_url: str = "", panel_url: str | None = None) -> Screen:
    """Мастер первой настройки как rich-экран: отчёт о правах и переключатели-таблетки."""
    body = [report]
    if cfg.get("captcha_on") and not webapp_url:
        body.append("⚠️ Капча включена, но у бота не задан WEBAPP_URL — она работать не будет.")
    body.append("<i>Включите нужное (только админы). Остальное — в разделе «Все настройки».</i>")
    rows = [[Btn(f"{'✅' if cfg[key] else '❌'} {label}", cb=f"wiz:{key}:{0 if cfg[key] else 1}",
                 style="success" if cfg[key] else None)] for key, label in WIZARD]
    rows.append([Btn("⚙️ Все настройки", cb="cfg:home"), Btn("📖 Меню", cb="menu:home")])
    if panel_url:
        rows.append([Btn("🌐 Открыть как приложение", url=panel_url, style="primary")])
    text, kb = render(cfg, report, webapp_url, panel_url)
    return Screen("👋 Первая настройка", body, rows, classic=text)


@router.my_chat_member(F.chat.type.in_({"group", "supergroup"}))
async def on_bot_added(ev: ChatMemberUpdated, bot, db: Database, webapp_url: str = "") -> None:
    was_in = ev.old_chat_member.status in ("member", "administrator", "restricted", "creator")
    now_in = ev.new_chat_member.status in ("member", "administrator", "creator")
    if was_in or not now_in:
        return
    now = time.time()
    if now - _sent.get(ev.chat.id, 0) < RESEND_AFTER:
        return
    _sent[ev.chat.id] = now
    report = await diagnose_chat(bot, db, ev.chat.id)
    from bot.handlers.settings import panel_url
    try:
        await rich_ui.send(bot, ev.chat.id, screen(await db.get_settings(ev.chat.id), report, webapp_url,
                                                   await panel_url(bot, ev.chat.id, webapp_url)))
    except Exception:
        _sent.pop(ev.chat.id, None)


@router.callback_query(F.data.startswith("wiz:"))
async def wizard_toggle(cb: CallbackQuery, bot, db: Database, webapp_url: str = "") -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or parts[1] not in _KEYS or parts[2] not in ("0", "1") or cb.message is None:
        await cb.answer()
        return
    if not await is_admin(bot, cb.message.chat.id, cb.from_user.id):
        await cb.answer("Только для админов", show_alert=True)
        return
    await db.set_setting(cb.message.chat.id, parts[1], parts[2], actor=cb.from_user.id)
    cfg = await db.get_settings(cb.message.chat.id)
    report = await diagnose_chat(bot, db, cb.message.chat.id)
    from bot.handlers.settings import panel_url
    await cb.answer("Сохранено")
    await rich_ui.show(cb, screen(cfg, report, webapp_url, await panel_url(bot, cb.message.chat.id, webapp_url)))
