"""Мафия: команды в группе, вход по ссылке в личку, кнопки ночи и голосования, предсмертные сообщения. Логика игры — bot/mafia.py."""
from __future__ import annotations

import html
import re

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot import mafia as mf, ux
from bot.db import Database
from bot.handlers.settings import can_configure

router = Router(name="mafia")

_GAME = re.compile(r"^(?:/game(?:@\w+)?|игра мафия|играть в мафию)$", re.IGNORECASE)
_START = re.compile(r"^(?:/startgame(?:@\w+)?|начать мафию|начать игру)$", re.IGNORECASE)
_STOP = re.compile(r"^(?:/stopgame(?:@\w+)?|стоп мафия|остановить мафию)$", re.IGNORECASE)
_DEEP = re.compile(r"^/start mafia_(-?\d{1,20}|role|go)$")
_GROUP = F.chat.type.in_({"group", "supergroup"})


def _is(rx):
    return F.text.func(lambda t: bool(t) and rx.match(t.strip()) is not None)


def _name(user) -> str:
    return (user.full_name or user.username or f"id{user.id}")[:40]


# Страж чата: на время партии удаляет сообщения тех, кто не играет или убит. Подключается в main.py ПЕРВЫМ роутером,
# чтобы такие сообщения не доходили ни до статистики, ни до ИИ. Команды управления игрой пропускает — ими пользуются ведущий и админы.
guard = Router(name="mafia_guard")


def _muted(message: Message) -> bool:
    if message.chat.type not in ("group", "supergroup"):
        return False
    t = (message.text or "").strip()
    if t and (_START.match(t) or _STOP.match(t)):
        return False
    return mf.must_delete(message.chat.id, message.from_user.id if message.from_user else None)


@guard.message(F.func(_muted))
async def delete_silenced(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass                                                # нет права удалять — бот предупредил об этом при старте игры


@router.message(_GROUP, _is(_GAME))
async def new_game(message: Message, bot, db: Database) -> None:
    if message.from_user is None:
        return
    if not (await db.get_settings(message.chat.id)).get("mafia_on", 1):
        return
    me = await bot.me()
    g, err = await mf.open_registration(bot, message.chat.id, message.chat.title or "чат", message.from_user.id,
                                        _name(message.from_user), me.username)
    if err:
        await ux.tell(message, f"⚠️ {err}")


@router.message(_GROUP, _is(_START))
async def start_game(message: Message, bot, db: Database) -> None:
    g = mf.get_game(message.chat.id)
    if g is None or message.from_user is None:
        return
    if message.from_user.id != g.host and not await can_configure(bot, db, message.chat.id, message.from_user.id):
        await ux.tell(message, "⚠️ Начать игру может ведущий набора или админ.")
        return
    err = mf.request_start(g)
    if err:
        await ux.tell(message, f"⚠️ {err}")


@router.message(_GROUP, _is(_STOP))
async def stop_game(message: Message, bot, db: Database) -> None:
    g = mf.get_game(message.chat.id)
    if g is None or message.from_user is None:
        return
    if message.from_user.id != g.host and not await can_configure(bot, db, message.chat.id, message.from_user.id):
        await ux.tell(message, "⚠️ Остановить игру может ведущий набора или админ.")
        return
    mf.stop(g)


@router.message(F.chat.type == "private", _is(_DEEP))
async def deep_link(message: Message, bot) -> None:
    payload = _DEEP.match(message.text.strip()).group(1)
    if payload in ("role", "go"):
        await message.answer("Все ходы игры приходят сюда личными сообщениями с кнопками — смотри выше. Если ждёшь свою очередь, подожди пару секунд.")
        return
    g = mf.get_game(int(payload))
    if g is None:
        await message.answer("Эта игра уже закончилась или не существует.")
        return
    me = await bot.me()
    err = await mf.join(bot, g, message.from_user.id, _name(message.from_user), me.username)
    if err:
        await message.answer(f"⚠️ {err}")
        return
    await message.answer(f"Ты присоединился к игре в <b>{html.escape(g.title)}</b>. Когда начнётся игра, роль придёт сюда.")


@router.callback_query(F.data.startswith("mf:"))
async def action(cb: CallbackQuery, bot) -> None:
    try:
        _, kind, chat, arg = cb.data.split(":")
        g, arg = mf.get_game(int(chat)), int(arg)
    except ValueError:
        await cb.answer()
        return
    if g is None or cb.from_user.id not in g.players:
        await cb.answer("Игра закончилась.", show_alert=True)
        return
    uid = cb.from_user.id
    if kind == "n":
        text, extra = mf.night_action(g, uid, arg)
        if text.startswith("⚠️"):
            await cb.answer(text[3:], show_alert=True)
            return
        await _finish_pick(cb, text)
        for to, msg in extra:
            await mf._say(bot, to, msg)
        if g.players[uid].role in mf.MAFIA and all(u in g.mafia_votes for u in g.alive_ids(mf.MAFIA)):
            target = g.mafia_target()
            if target is not None:
                for m in g.alive_ids(mf.MAFIA):
                    await mf._say(bot, m, f"Голосование мафии завершено\nМафия принесла в жертву {html.escape(g.players[target].name)}.")
    elif kind == "v":
        text, announce = mf.vote_action(g, uid, arg)
        if announce is None:
            await cb.answer(text[3:], show_alert=True)
            return
        await _finish_pick(cb, text)
        await mf._say(bot, g.chat_id, announce)
    elif kind == "c":
        err = g.cast_confirm(uid, bool(arg))
        await cb.answer(err or "Голос принят", show_alert=bool(err))
    else:
        await cb.answer()


async def _finish_pick(cb: CallbackQuery, text: str) -> None:
    """Выбор сделан: убираем кнопки, оставляем «Ты выбрал …»."""
    await cb.answer()
    try:
        await cb.message.edit_text(text, reply_markup=None)
    except Exception:
        pass


def _can_speak(message: Message) -> bool:
    if message.from_user is None or not message.text:
        return False
    g = mf.game_of_user(message.from_user.id)
    p = g.players.get(message.from_user.id) if g else None
    return bool(p and not p.alive and p.can_speak and not message.text.startswith("/"))


@router.message(F.chat.type == "private", F.func(_can_speak))
async def final_words(message: Message, bot) -> None:
    g = mf.game_of_user(message.from_user.id)
    text = mf.last_words(g, message.from_user.id, message.text)
    if text is None:
        return
    await message.answer("Сообщение принято и будет отправлено в чат через бота.")
    await mf._say(bot, g.chat_id, text)
