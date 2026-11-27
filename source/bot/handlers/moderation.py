import re
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.toggles import Enabled
from bot import mod_service as ms
from bot.db import Database
from bot import ux
from bot.emoji import emoji
from bot.keyboards import undo_keyboard
from bot.parsing import ModCommand, parse_mod_command
from bot.targets import resolve_user
from bot import wipe as wipe_mod

router = Router(name="moderation")
router.message.filter(Enabled("mod_on"))   # группу команд можно выключить в настройках → «Команды»

PUNITIVE = {"бан", "мут", "кик", "варн"}
TARGETED = PUNITIVE | {"разбан", "размут", "снять варн", "вайп"}
UNDO_ACTION = {"бан": "ban", "мут": "mute", "варн": "warn"}
UNDO_PAIR = {"бан": "разбан", "мут": "размут", "варн": "снять варн"}
_ROLLBACK_RE = re.compile(r"^откат(?:\s+(@\w+|\d{5,}))?$", re.IGNORECASE)


def _is_cmd(text: str | None) -> bool:
    return bool(text) and parse_mod_command(text) is not None


@router.message(F.text.func(_is_cmd))
async def on_mod(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup"):
        await ux.tell(message, "⚠️ Модерация работает только в группах.")
        return
    if message.from_user and message.from_user.id == ms.ANON_ADMIN_ID and not ms.is_anonymous_admin(message):
        return  # id GroupAnonymousBot без sender_chat = чата — не анонимный админ, права не даём
    cmd = parse_mod_command(message.text)
    chat_id, actor = message.chat.id, message.from_user.id
    now = int(time.time())
    reply = ms.real_reply(message)

    if cmd.name == "варны":  # доступно всем
        reply_uid = reply.from_user.id if reply and reply.from_user else None
        tid, hint = await ms.resolve_target(bot, db, cmd, reply_uid)
        tid = tid or actor
        await message.answer(await ms.apply(bot, db, cmd, chat_id, actor, tid, now))
        return

    if cmd.name in ("удалить", "закреп", "открепить", "чистка"):
        await _message_ops(message, bot, db, cmd)
        return

    ok, why = await ms.can_act(bot, chat_id, actor, None, "restrict", db=db, command=cmd.name)
    if not ok:
        await ux.tell(message, why)
        return
    if cmd.name == "амнистия":
        await _amnesty(message, bot, db, chat_id, actor, now)
        return
    reply_uid = reply.from_user.id if reply and reply.from_user else None
    tid, hint = await ms.resolve_target(bot, db, cmd, reply_uid)
    if tid is None:
        if cmd.name == "бан" and cmd.target and cmd.target.startswith("@"):   # бан по неизвестному нику — запомнить и выполнить при появлении
            await db.add_pending_ban(chat_id, cmd.target.lstrip("@").lower(),
                                     int(cmd.duration.total_seconds()) if getattr(cmd, "duration", None) else None,
                                     getattr(cmd, "reason", "") or "", actor, now, forced=False)
            await message.answer(f"✅ {cmd.target} запомнен — забаню, как только появится.")
            return
        await ux.tell(message, hint)
        return
    if cmd.name in TARGETED:  # включая размут/разбан/снять варн: ранг цели проверяется всегда
        ok, why = await ms.can_act(bot, chat_id, actor, tid, "restrict", db=db, command=cmd.name)
        if not ok:
            await ux.tell(message, why)
            return
    if cmd.name == "вайп":
        n = await wipe_mod.wipe(bot, chat_id, tid, now)
        await db.log_action(chat_id, actor, tid, "вайп", f"удалено {n}", now)
        await message.answer(f"🧹 Сообщений удалено: {n} (за последние 48 ч, из тех, что бот видел)")
        return
    try:
        text = await ms.apply(bot, db, cmd, chat_id, actor, tid, now, gif=not cmd.silent)
    except Exception as e:  # нет прав у бота и т. п.
        await message.answer(f"{emoji('fail')} Не получилось: {e}")
        return
    if cmd.delete_msg and reply is not None:                  # «дбан/дмут…» — убрать и сообщение нарушителя
        try:
            await bot.delete_message(chat_id, reply.message_id)
        except Exception:
            pass
    if cmd.silent:                                            # «тбан/тмут…» — не оставлять следов в чате
        try:
            await bot.delete_message(chat_id, message.message_id)
        except Exception:
            pass
        return
    kb = undo_keyboard(UNDO_ACTION[cmd.name], tid) if cmd.name in UNDO_ACTION else None
    await message.answer(text, reply_markup=kb)


async def _amnesty(message: Message, bot, db: Database, chat_id: int, actor: int, now: int) -> None:
    """«амнистия» — снять баны (и муты) со всех, кто сейчас наказан ботом."""
    n = 0
    for kind in ("ban", "mute"):
        for r in await db.list_state(chat_id, kind, now):
            try:
                await ms.apply(bot, db, ModCommand("разбан" if kind == "ban" else "размут", None, None, ""),
                               chat_id, actor, r["user_id"], now, gif=False)
                n += 1
            except Exception:
                continue
    await message.answer(f"🕊 Амнистия: снято наказаний — {n}")


async def _message_ops(message: Message, bot, db: Database, cmd: ModCommand) -> None:
    chat_id, actor = message.chat.id, message.from_user.id
    right = "pin" if cmd.name in ("закреп", "открепить") else "delete"
    ok, why = await ms.can_act(bot, chat_id, actor, None, right, db=db, command=cmd.name)
    if not ok:
        await ux.tell(message, why)
        return
    reply = ms.real_reply(message)
    try:
        if cmd.name == "удалить":
            if not reply:
                await ux.tell(message, "⚠️ Ответьте командой на сообщение, которое нужно удалить.")
                return
            await bot.delete_messages(chat_id, [reply.message_id, message.message_id])
        elif cmd.name == "закреп":
            if not reply:
                await ux.tell(message, "⚠️ Ответьте командой на сообщение, которое нужно закрепить.")
                return
            await bot.pin_chat_message(chat_id, reply.message_id)
        elif cmd.name == "открепить":
            if reply:
                await bot.unpin_chat_message(chat_id, reply.message_id)
            else:
                await bot.unpin_chat_message(chat_id)
            await message.answer(f"{emoji('pin')} Откреплено")
        elif cmd.name == "чистка":
            if reply:
                first = reply.message_id
            else:
                n = int(cmd.reason) if cmd.reason.isdigit() else 0
                if n < 1:
                    await ux.tell(message, "⚠️ Укажите число: <code>чистка 20</code> (до 100).")
                    return
                first = message.message_id - min(n, 100)
            ids = list(range(max(first, 1), message.message_id + 1))[-100:]
            await bot.delete_messages(chat_id, ids)
    except Exception as e:
        await message.answer(f"{emoji('fail')} Не получилось: {e}")


@router.callback_query(F.data.startswith("undo:"))
async def undo_cb(cb: CallbackQuery, bot, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or parts[1] not in ("ban", "mute", "warn") or not parts[2].lstrip("-").isdigit() \
            or cb.message is None:
        await cb.answer()
        return
    action, tid = parts[1], int(parts[2])
    chat_id = cb.message.chat.id
    name = {"ban": "разбан", "mute": "размут", "warn": "снять варн"}[action]
    ok, why = await ms.can_act(bot, chat_id, cb.from_user.id, tid, "restrict", db=db, command=name)
    if not ok:
        await cb.answer(why or "Недостаточно прав", show_alert=True)
        return
    try:
        await cb.message.edit_reply_markup(reply_markup=None)  # защита от повторного нажатия
    except Exception:
        await cb.answer("Уже отменено", show_alert=True)       # кнопку нажали дважды: второе нажатие не повторяет действие
        return
    now = int(time.time())
    try:
        text = await ms.apply(bot, db, ModCommand(name, None, None, ""), chat_id, cb.from_user.id, tid, now)
    except Exception as e:                                       # у бота отобрали права и т. п.
        await cb.answer(f"Не получилось: {e}"[:180], show_alert=True)
        return
    await cb.message.answer(f"↩️ {text}")
    await cb.answer("Отменено")


@router.message(F.text.func(lambda t: bool(t) and _ROLLBACK_RE.match(t.strip()) is not None))
async def rollback_cmd(message: Message, bot, db: Database) -> None:
    """«откат» — отменить последнее наказание (бан/мут/варн) в чате; «откат @ник» или ответом — последнее у этого человека.
    Работает по журналу, поэтому годится и когда кнопка «Отменить» уже пропала или наказание выдал антиспам."""
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    token = _ROLLBACK_RE.match(message.text.strip()).group(1)
    chat_id, actor, now = message.chat.id, message.from_user.id, int(time.time())
    target = await resolve_user(db, token, ms.real_reply(message))
    names = tuple(UNDO_PAIR) + tuple(UNDO_PAIR.values())
    last = await db.last_mod_action(chat_id, names, target[0] if target else None)
    if last is None or last["action"] not in UNDO_PAIR or last["target_id"] is None:
        await ux.tell(message, "❌ Нечего откатывать: последнее действие уже отменено или наказаний не было.")
        return
    tid, undo_name = last["target_id"], UNDO_PAIR[last["action"]]
    ok, why = await ms.can_act(bot, chat_id, actor, tid, "restrict", db=db, command=undo_name)
    if not ok:
        await message.reply(why or "Недостаточно прав.")
        return
    try:
        text = await ms.apply(bot, db, ModCommand(undo_name, None, None, ""), chat_id, actor, tid, now)
    except Exception as e:
        await message.reply(f"{emoji('fail')} Не получилось: {e}")
        return
    await message.reply(f"↩️ Откат «{last['action']}»: {text}")
