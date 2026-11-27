"""ИИ-модерация: кнопка «Это ошибка» (возврат и пометка для настройки порога) и команда «ии модерация» со статистикой."""
import html
import re
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot import mod_service as ms
from bot.db import Database
from bot.fmt import kv_table, quote
from bot.parsing import ModCommand
from bot.ranks import need_rank

router = Router(name="aimod")
_STATS_RE = re.compile(r"^ии[\s\-]модерация$", re.IGNORECASE)
DAY = 86400


@router.callback_query(F.data.startswith("aimod:"))
async def error_button(cb: CallbackQuery, bot, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) != 2 or not parts[1].isdigit() or cb.message is None:
        await cb.answer()
        return
    ev = await db.get_aimod_event(int(parts[1]))
    if ev is None:
        await cb.answer("Запись устарела", show_alert=True)
        return
    chat, mod, uid = ev["chat_id"], cb.from_user.id, ev["user_id"]
    if await ms.effective_rank(bot, db, chat, mod) < need_rank(await db.get_access(chat), "варн"):
        await cb.answer("Только для модераторов", show_alert=True)
        return
    if not await db.mark_aimod_false(ev["id"], mod):
        await cb.answer("Уже обработано", show_alert=True)
        return
    now = int(time.time())

    async def manual_notice(text: str) -> None:
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await cb.answer(text, show_alert=True)

    try:
        marker = f"[ai-msg:{ev['message_id']}]" if ev.get("message_id") else ""
        bot_id = (await bot.me()).id
        if ev["action"] == "mute":
            state = await db.get_state(chat, uid, "mute", now)
            if not marker or not state or state["actor"] != bot_id or not (state.get("reason") or "").endswith(marker):
                await manual_notice("Ошибка отмечена. Текущий мут изменён или не связан с этим событием — проверьте его вручную.")
                return
            await ms.apply(bot, db, ModCommand("размут", None, None, ""), chat, mod, uid, now)
        elif ev["action"] == "warn":
            if not marker or not await db.remove_ai_warn(chat, uid, bot_id, marker, now):
                await manual_notice("Ошибка отмечена. Связанное предупреждение не найдено — проверьте вручную.")
                return
        else:  # delete: вернуть текст от имени бота
            who = await ms.mention(bot, db, chat, uid)
            await bot.send_message(chat, f"↩️ {who}: сообщение восстановлено модератором (ИИ ошибся):\n"
                                         f"«{html.escape(ev['text'])}»")
        await db.log_action(chat, mod, uid, "ошибка ИИ", f"{ev['category']} {ev['confidence']}%", now)
        answer = ("Отмечено как ошибка ИИ", False)
    except Exception as e:
        answer = (f"Пометил как ошибку, но возврат не удался: {e}"[:180], True)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.answer(answer[0], show_alert=answer[1])   # на callback отвечают ровно один раз


@router.message(F.text.func(lambda t: bool(t) and _STATS_RE.match(t.strip()) is not None))
async def stats_cmd(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    chat = message.chat.id
    if await ms.effective_rank(bot, db, chat, message.from_user.id) < need_rank(await db.get_access(chat), "настройки чата"):
        return
    cfg = await db.get_settings(chat)
    total, false = await db.aimod_stats(chat, int(time.time()) - 7 * DAY)
    mode = {"off": "выключена", "newbies": "новички", "all": "новички + подозрительное"}[cfg["ai_mod"]]
    tip = ""
    if total >= 5 and false / total > 0.2:
        tip = "\n⚠️ Много ложных срабатываний — поднимите порог (настройки → ИИ-модерация)."
    await message.reply("🤖 <b>ИИ-модерация</b>\n" + kv_table([
        ("Режим", mode), ("Действие", cfg["ai_mod_action"]), ("Порог", f"{cfg['ai_mod_conf']}%"),
        ("За 7 дней", f"{total} сработ., {false} ошибок")], key_width=10, value_width=26) + tip + "\n"
        + quote("Включить: настройки → ИИ-модерация. Проверяемый текст отправляется во внешний сервис ИИ.", expandable=False))
