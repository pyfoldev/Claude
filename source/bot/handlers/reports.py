"""Жалобы: «жалоба» ответом на сообщение (или «жалоба @ник») → карточка модераторам с кнопками действий."""
import datetime
import html
import re
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import ux
from bot import mod_service as ms
from bot.db import Database
from bot.fmt import quote
from bot.handlers.social import chat_link
from bot.parsing import ModCommand
from bot.targets import mention, resolve_user, listed

router = Router(name="reports")
DAILY_LIMIT = 5
MUTE_SECONDS = 3600
_T = r"(@\w+|\d{5,})"
_RU = re.compile(r"^жалоба(?:\s+" + _T + r")?(?:\s+причина[:\s]\s*(.+))?$", re.IGNORECASE | re.DOTALL)
_SLASH = re.compile(r"^/report(?:@\w+)?(?:\s+(.+))?$", re.IGNORECASE | re.DOTALL)
STATUS_TEXT = {"deleted": "сообщение удалено", "muted": "мут на 1 ч", "banned": "бан", "dismissed": "жалоба отклонена"}
ACTION_STATUS = {"del": "deleted", "mute": "muted", "ban": "banned", "dismiss": "dismissed"}


def _parse(text: str | None):
    t = (text or "").strip()
    m = _RU.match(t)
    if m:
        return m.group(1), (m.group(2) or "").strip()
    m = _SLASH.match(t)
    if m:
        return None, (m.group(1) or "").strip()
    return False


def _keyboard(rid: int, with_delete: bool) -> InlineKeyboardMarkup:
    row1 = ([B(text="🗑 Удалить сообщение", callback_data=f"rep:{rid}:del")] if with_delete else []) + \
           [B(text="🔇 Мут 1 ч", callback_data=f"rep:{rid}:mute")]
    row2 = [B(text="🔨 Бан", callback_data=f"rep:{rid}:ban"), B(text="❌ Отклонить", callback_data=f"rep:{rid}:dismiss")]
    return InlineKeyboardMarkup(inline_keyboard=[row1, row2])


async def post_report_card(bot, db: Database, chat: int, reporter_id: int, reporter_html: str, tid: int, tname: str,
                           message_id: int | None, text: str, reason: str, now: int) -> bool:
    """Сохраняет жалобу и шлёт карточку модераторам (в чат или в журнал). Общая для людей и ИИ-модерации."""
    rid = await db.add_report(chat, reporter_id, tid, message_id, text, reason, now)
    await db.log_action(chat, reporter_id, tid, "жалоба", reason or f"#{rid}", now)
    cfg = await db.get_settings(chat)
    dest = cfg["log_chat_id"] or chat
    rejected = await db.count_rejected_reports(chat, reporter_id)
    link = chat_link(chat, message_id) if message_id else None
    lines = [f"📣 <b>Жалоба #{rid}</b>" + (f" · чат <code>{chat}</code>" if dest != chat else ""),
             f"{reporter_html} → {listed(tid, tname)}" + (f" <i>(отклонённых у автора: {rejected})</i>" if rejected else "")]
    if reason:
        lines.append(f"Причина: {html.escape(reason)}")
    if text:
        lines.append(quote(html.escape(text), expandable=len(text) > 120)
                     + (f'\n<a href="{link}">Перейти к сообщению</a>' if link else ""))
    if dest == chat:
        try:
            admins = [a.user for a in await bot.get_chat_administrators(chat) if not a.user.is_bot][:5]
            lines.append("Модераторам: " + " ".join(mention(u.id, u.first_name) for u in admins))
        except Exception:
            pass
    try:
        await bot.send_message(dest, "\n".join(lines), reply_markup=_keyboard(rid, message_id is not None),
                               disable_web_page_preview=True)
    except Exception:
        return False
    return True


@router.message(F.text.func(lambda t: _parse(t) is not False))
async def report_cmd(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    chat, me, now = message.chat.id, message.from_user.id, int(time.time())
    if not (await db.get_settings(chat))["report_on"]:
        return
    token, reason = _parse(message.text)
    reply = ms.real_reply(message)
    target = await resolve_user(db, token, reply)
    if target is None:
        return  # «жалоба» без цели — просто слово
    tid, tname = target
    message_id = reply.message_id if reply is not None and not token else None
    if tid == me or tid == (await bot.me()).id or (reply is not None and reply.from_user and reply.from_user.is_bot):
        await ux.tell(message, "⚠️ На себя и на бота жаловаться нельзя.")
        return
    try:
        protected = (await ms.get_member(bot, chat, tid)).status in ("administrator", "creator") \
            or await ms.effective_rank(bot, db, chat, tid) > 0
    except Exception:
        protected = False
    if protected:
        await ux.tell(message, "⚠️ На админов и модераторов жаловаться нельзя.")
        return
    if await db.report_exists(chat, message_id):
        await ux.tell(message, "⚠️ На это сообщение уже пожаловались — модераторы в курсе.")
        return
    if not await db.take_quota(chat, f"report{me}", now, DAILY_LIMIT):
        await ux.tell(message, f"⚠️ Лимит жалоб на сегодня исчерпан ({DAILY_LIMIT}).")
        return
    text = ""
    if reply is not None and not token:
        text = (reply.text or reply.caption or "[медиа без текста]")[:300]
    if not await post_report_card(bot, db, chat, me, listed(me, message.from_user.full_name), tid, tname,
                                  message_id, text, reason, now):
        await db.refund_quota(chat, f"report{me}", now)   # карточка не ушла — суточный лимит жалоб не тратим
        await ux.tell(message, "❌ Не удалось отправить жалобу модераторам. Попробуйте позже.")
        return
    await message.reply("📣 Жалоба отправлена модераторам.")


async def apply_report_action(bot, db: Database, rep: dict, act: str, mod: int, now: int) -> tuple[bool, str]:
    """Обработать жалобу действием del|mute|ban|dismiss от имени модератора mod. Права проверяются здесь —
    по чату жалобы и при каждом вызове (общая логика кнопок в Telegram и веб-панели)."""
    if act not in ACTION_STATUS:
        return False, "Неизвестное действие"
    if rep["status"] != "open":
        return False, "Уже обработано"
    chat, tid = rep["chat_id"], rep["target"]
    if act == "del" and not rep.get("message_id"):
        return False, "У этой жалобы нет сообщения для удаления"
    if act == "del":
        ok, why = await ms.can_act(bot, chat, mod, None, "delete", db=db, command="удалить")
    elif act == "dismiss":
        ok, why = await ms.can_act(bot, chat, mod, None, "restrict", db=db, command="варн")
    else:
        ok, why = await ms.can_act(bot, chat, mod, tid, "restrict", db=db, command="мут" if act == "mute" else "бан")
    if not ok:
        return False, why or "Недостаточно прав"
    if not await db.claim_report(rep["id"], ACTION_STATUS[act], mod):
        return False, "Уже обработано"
    try:
        if act == "del":
            await bot.delete_message(chat, rep["message_id"])
            await db.log_action(chat, mod, tid, "удаление", f"жалоба #{rep['id']}", now)
        elif act == "mute":
            await ms.apply(bot, db, ModCommand("мут", None, datetime.timedelta(seconds=MUTE_SECONDS),
                                                f"жалоба #{rep['id']}"), chat, mod, tid, now)
        elif act == "ban":
            await ms.apply(bot, db, ModCommand("бан", None, None, f"жалоба #{rep['id']}"), chat, mod, tid, now)
    except Exception as e:
        await db.reopen_report(rep["id"])
        return False, f"Не получилось: {e}"[:180]
    return True, STATUS_TEXT[ACTION_STATUS[act]]


@router.callback_query(F.data.startswith("rep:"))
async def report_action(cb: CallbackQuery, bot, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or not parts[1].isdigit() or parts[2] not in ACTION_STATUS or cb.message is None:
        await cb.answer()
        return
    rep = await db.get_report(int(parts[1]))
    if rep is None:
        await cb.answer("Жалоба не найдена", show_alert=True)
        return
    ok, info = await apply_report_action(bot, db, rep, parts[2], cb.from_user.id, int(time.time()))
    if not ok:
        await cb.answer(info, show_alert=True)
        return
    by = mention(cb.from_user.id, (await db.user_name(cb.from_user.id)) or cb.from_user.full_name)
    try:
        await cb.message.edit_text((cb.message.html_text or "") + f"\n\n✅ {info} — {by}",
                                   reply_markup=None, disable_web_page_preview=True)
    except Exception:
        pass
    await cb.answer("Готово")
