"""Конкурсы (розыгрыши).

Группа: «+конкурс» (по умолчанию — владелец чата, ДК «конкурсы») → кнопка в личку; «конкурсы» — список;
«-конкурс N» — отменить; «реролл N» — выбрать другого победителя.
Личка: пошаговый мастер — текст (можно с фото) → когда опубликовать → когда закончить → сколько победителей → предпросмотр.
В назначенное время Нори публикует объявление с кнопкой «Участвовать»: она ведёт в личку бота, оттуда открывается Mini App
с капчей (кнопки Mini App в группах Telegram не разрешает). В конце Нори случайно выбирает победителей среди тех, кто
всё ещё в чате, и объявляет итоги ответом на объявление."""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message, WebAppInfo

from bot import ux
from bot.toggles import Enabled
from bot import giveaway as gw
from bot import members
from bot import mod_service as ms
from bot.db import Database
from bot.ranks import need_rank
from bot.targets import ping

router = Router(name="giveaway")
router.message.filter(Enabled("giveaway_on"))   # группу команд можно выключить в настройках → «Команды»
ACCESS_KEY = "конкурсы"
WATCH_EVERY = 10            # как часто сторож публикует / подводит итоги
COUNT_EDIT_EVERY = 20       # счётчик участников на кнопке обновляем не чаще, чем раз в 20 с
_count_edited: dict[int, float] = {}

_GROUP = re.compile(r"^(?:\+конкурс|\+розыгрыш)$|^(конкурсы|розыгрыши)$|^-(?:конкурс|розыгрыш)\s+(\d{1,9})$"
                    r"|^(?:реролл|перевыбрать)\s+(\d{1,9})$", re.IGNORECASE)
_START_NEW = re.compile(r"^/start gw_(-?\d{1,20})$")
_START_JOIN = re.compile(r"^/start gwj_(\d{1,9})$")
STATUS_RU = {"scheduled": "ждёт публикации", "active": "идёт", "finished": "завершён", "cancelled": "отменён",
             "failed": "не опубликован"}


def _parse_group(text: str | None):
    m = _GROUP.match((text or "").strip())
    if not m:
        return None
    if m.group(1):
        return "list", None
    if m.group(2):
        return "cancel", int(m.group(2))
    if m.group(3):
        return "reroll", int(m.group(3))
    return "new", None


async def _can_manage(bot, db: Database, chat_id: int, user_id: int) -> bool:
    return await ms.effective_rank(bot, db, chat_id, user_id) >= need_rank(await db.get_access(chat_id), ACCESS_KEY)


async def _tz(db: Database, chat_id: int):
    return gw.tz_of((await db.get_settings(chat_id))["tz"])


# ---------- объявление и итоги ----------

def _join_kb(username: str, gid: int, count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text=f"🎟 Участвовать ({count})",
                                                    url=f"https://t.me/{username}?start=gwj_{gid}")]])


def announcement(g: dict, tz) -> str:
    n = g["winners"]
    return (f"{g['text']}\n\n🎁 <b>Конкурс №{g['id']}</b> · победител{'ь' if n == 1 else 'ей'}: <b>{n}</b>\n"
            f"⏰ Итоги: <b>{gw.fmt_time(g['ends_at'], tz)}</b>\n"
            "<i>Нажмите «Участвовать» и пройдите проверку от ботов.</i>")


async def publish(bot, db: Database, g: dict) -> bool:
    """Отправить объявление в чат. Только один раз (статус scheduled → active)."""
    if not await db.gw_claim(g["id"], "scheduled", "publishing"):
        return False
    tz = await _tz(db, g["chat_id"])
    kb = _join_kb((await bot.me()).username, g["id"], 0)
    try:
        if g["photo"]:
            m = await bot.send_photo(g["chat_id"], g["photo"], caption=announcement(g, tz), reply_markup=kb)
        else:
            m = await bot.send_message(g["chat_id"], announcement(g, tz), reply_markup=kb)
    except Exception as e:
        logging.warning("giveaway %s: publish failed: %s", g["id"], e)
        await db.gw_update(g["id"], status="failed")
        await _notify(bot, g["creator"], f"⚠️ Конкурс №{g['id']} не удалось опубликовать: {html.escape(str(e))[:200]}\n"
                                         "Проверьте, что бот есть в чате и может писать.")
        return False
    await db.gw_update(g["id"], status="active", message_id=m.message_id, shown_count=0)
    return True


async def _pick(bot, db: Database, chat_id: int, candidates: list[int], n: int, exclude: set[int]) -> list[int]:
    """Первые n из случайного порядка, кто ещё в чате (вышедших пропускаем и убираем из списка участников чата)."""
    out = []
    for uid in gw.shuffled(candidates):
        if uid in exclude:
            continue
        if await members.check(bot, db, chat_id, uid) is False:
            continue
        out.append(uid)
        if len(out) >= n:
            break
    return out


async def _names(db: Database, ids: list[int]) -> str:
    return ", ".join([str(ping(u, (await db.user_name(u)) or f"id{u}")) for u in ids])


async def finish(bot, db: Database, g: dict) -> bool:
    if not await db.gw_claim(g["id"], "active", "finishing"):
        return False
    entries = await db.gw_entries(g["id"])
    winners = await _pick(bot, db, g["chat_id"], entries, g["winners"], set())
    await db.gw_update(g["id"], status="finished", result=json.dumps(winners))
    if winners:
        text = (f"🎉 <b>Итоги конкурса №{g['id']}</b>\nУчастников: {len(entries)}\n"
                f"{'Победитель' if len(winners) == 1 else 'Победители'}: {await _names(db, winners)}\nПоздравляем! 🥳")
    else:
        text = f"🎁 Конкурс №{g['id']} завершён: участников не было — победителя нет."
    try:
        await bot.edit_message_reply_markup(chat_id=g["chat_id"], message_id=g["message_id"], reply_markup=None)
    except Exception:
        pass
    try:
        await bot.send_message(g["chat_id"], text, reply_to_message_id=g["message_id"], allow_sending_without_reply=True)
    except Exception as e:
        logging.warning("giveaway %s: results not sent: %s", g["id"], e)
    await _notify(bot, g["creator"], text)
    await db.log_action(g["chat_id"], (await bot.me()).id, winners[0] if winners else None, "конкурс",
                        f"№{g['id']}: участников {len(entries)}, победителей {len(winners)}", int(time.time()))
    return True


async def _notify(bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text)
    except Exception:
        pass


async def _refresh_count(bot, db: Database, g: dict, username: str) -> None:
    n = await db.gw_count(g["id"])
    if n == g["shown_count"] or time.time() - _count_edited.get(g["id"], 0) < COUNT_EDIT_EVERY:
        return
    _count_edited[g["id"]] = time.time()
    try:
        await bot.edit_message_reply_markup(chat_id=g["chat_id"], message_id=g["message_id"],
                                            reply_markup=_join_kb(username, g["id"], n))
        await db.gw_update(g["id"], shown_count=n)
    except Exception:
        pass


async def tick(bot, db: Database, now: int | None = None) -> None:
    now = int(time.time()) if now is None else now
    for g in await db.gw_due("scheduled", "publish_at", now):
        await publish(bot, db, g)
    for g in await db.gw_due("active", "ends_at", now):
        await finish(bot, db, g)
    active = await db.gw_list(None, ("active",))
    if active:
        username = (await bot.me()).username
        for g in active:
            await _refresh_count(bot, db, g, username)


async def giveaway_watchdog(bot, db: Database) -> None:
    while True:
        await asyncio.sleep(WATCH_EVERY)
        try:
            await tick(bot, db)
        except Exception:
            logging.exception("giveaway watchdog")


# ---------- группа ----------

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: _parse_group(t) is not None))
async def group_cmd(message: Message, bot, db: Database, webapp_url: str = "") -> None:
    if message.from_user is None:
        return
    kind, gid = _parse_group(message.text)
    chat, me = message.chat.id, message.from_user.id
    tz = await _tz(db, chat)
    if kind == "list":
        rows = await db.gw_list(chat, ("scheduled", "active"))
        if not rows:
            await message.reply("🎁 Сейчас конкурсов нет.")
            return
        lines = []
        for g in rows:
            when = (f"публикация {gw.fmt_time(g['publish_at'], tz)}" if g["status"] == "scheduled"
                    else f"участников {await db.gw_count(g['id'])}")
            lines.append(f"№{g['id']} — {STATUS_RU[g['status']]}, {when}, итоги {gw.fmt_time(g['ends_at'], tz)}")
        await message.reply("🎁 <b>Конкурсы</b>\n" + "\n".join(lines))
        return
    if not await _can_manage(bot, db, chat, me):
        if kind == "new":
            await ux.tell(message, f"⚠️ Создавать конкурсы может владелец чата (ранг {need_rank(await db.get_access(chat), ACCESS_KEY)}+).")
        return
    if kind == "new":
        if not webapp_url:
            await ux.tell(message, "⚠️ Для конкурсов нужен WEBAPP_URL (проверка от ботов идёт в Mini App).")
            return
        username = (await bot.me()).username
        await message.reply("🎁 Создадим конкурс в личке с ботом — там можно добавить фото и выбрать время.",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                                B(text="✍️ Создать конкурс", url=f"https://t.me/{username}?start=gw_{chat}")]]))
        return
    g = await db.gw_get(gid)
    if g is None or g["chat_id"] != chat:
        await ux.tell(message, "❌ Нет такого конкурса в этом чате.")
        return
    if kind == "cancel":
        if g["status"] not in ("scheduled", "active") or not await db.gw_claim(g["id"], g["status"], "cancelled"):
            await ux.tell(message, "⚠️ Этот конкурс уже не идёт.")
            return
        if g["message_id"]:
            try:
                await bot.edit_message_reply_markup(chat_id=chat, message_id=g["message_id"], reply_markup=None)
            except Exception:
                pass
        await db.log_action(chat, me, None, "конкурс", f"№{gid} отменён", int(time.time()))
        await message.reply(f"🚫 Конкурс №{gid} отменён.")
        return
    # reroll
    if g["status"] != "finished":
        await ux.tell(message, "⚠️ Перевыбрать можно только после итогов.")
        return
    old = json.loads(g["result"] or "[]")
    new = await _pick(bot, db, chat, await db.gw_entries(gid), 1, set(old))
    if not new:
        await ux.tell(message, "❌ Больше выбрать некого: все участники уже побеждали или вышли из чата.")
        return
    await db.gw_update(gid, result=json.dumps(old + new))
    await db.log_action(chat, me, new[0], "конкурс", f"№{gid}: перевыбор", int(time.time()))
    await message.reply(f"🔁 Конкурс №{gid}, новый победитель: {await _names(db, new)} 🎉")


# ---------- участие (личка → Mini App) ----------

@router.message(F.chat.type == "private", F.text.func(lambda t: bool(t) and _START_JOIN.match(t.strip()) is not None))
async def start_join(message: Message, db: Database, webapp_url: str = "") -> None:
    gid = int(_START_JOIN.match(message.text.strip()).group(1))
    g = await db.gw_get(gid)
    if g is None or g["status"] != "active" or g["ends_at"] <= time.time():
        await ux.tell(message, "⚠️ Этот конкурс уже завершён или не найден.")
        return
    if await db.gw_joined(gid, message.from_user.id):
        await message.answer(f"✅ Вы уже участвуете в конкурсе №{gid}. Удачи!")
        return
    if not webapp_url:
        await ux.tell(message, "⚠️ Mini App не настроен — обратитесь к администратору бота.")
        return
    await message.answer(f"🎁 Конкурс №{gid}. Чтобы участвовать, пройдите короткую проверку от ботов:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                             B(text="🎟 Участвовать", web_app=WebAppInfo(url=f"{webapp_url}/giveaway?id={gid}"))]]))


# ---------- мастер создания (личка) ----------

def _kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text=t, callback_data=d) for t, d in row] for row in rows])


CANCEL_ROW = [("✖️ Отмена", "gw:cancel")]
PUBLISH_KB = _kb([[("Сейчас", "gw:p:0"), ("Через 1 ч", "gw:p:3600")], CANCEL_ROW])
END_KB = _kb([[("1 час", "gw:e:3600"), ("1 день", "gw:e:86400")], [("3 дня", "gw:e:259200"), ("7 дней", "gw:e:604800")],
              CANCEL_ROW])
WINNERS_KB = _kb([[(str(n), f"gw:w:{n}") for n in (1, 2, 3, 5)], CANCEL_ROW])
CONFIRM_KB = _kb([[("✅ Опубликовать", "gw:ok")], CANCEL_ROW])
ASK_TEXT = ("✍️ Пришлите текст конкурса: что разыгрывается и условия. Можно фото с подписью — фото по желанию.\n"
            "Отменить — «отмена».")


def _ask_publish(tz) -> str:
    return ("⏰ Когда опубликовать в чате? Нажмите кнопку или напишите: <code>20:00</code>, <code>завтра 18:30</code>, "
            f"<code>25.12 12:00</code>, <code>через 2 часа</code>. Время чата — {tz}.")


def _ask_end(g: dict, tz) -> str:
    return (f"🏁 Когда подвести итоги? Публикация: {gw.fmt_time(g['publish_at'], tz)}.\nКнопки и «через …» — от момента "
            "публикации; можно точное время: <code>завтра 21:00</code>, <code>31.12 23:00</code>.")


async def _draft_filter(message: Message, db: Database) -> bool:
    if message.chat.type != "private" or message.from_user is None:
        return False
    if (message.text or "").startswith("/start"):
        return False
    return await db.gw_draft(message.from_user.id) is not None


@router.message(F.chat.type == "private", F.text.func(lambda t: bool(t) and _START_NEW.match(t.strip()) is not None))
async def start_new(message: Message, bot, db: Database, webapp_url: str = "") -> None:
    chat_id = int(_START_NEW.match(message.text.strip()).group(1))
    if await db.get_chat(chat_id) is None or not await _can_manage(bot, db, chat_id, message.from_user.id):
        await ux.tell(message, "⚠️ Создавать конкурсы в этом чате вы не можете.")
        return
    if not webapp_url:
        await ux.tell(message, "⚠️ Для конкурсов нужен WEBAPP_URL.")
        return
    await db.gw_new_draft(chat_id, message.from_user.id, int(time.time()))
    title = (await db.get_chat(chat_id)).get("title") or str(chat_id)
    await message.answer(f"🎁 Новый конкурс для «{html.escape(title)}».\n\n" + ASK_TEXT, reply_markup=_kb([CANCEL_ROW]))


async def _preview(message: Message, db: Database, g: dict) -> None:
    tz = await _tz(db, g["chat_id"])
    text = announcement(g, tz)
    if g["photo"]:
        await message.answer_photo(g["photo"], caption=text)
    else:
        await message.answer(text)
    await message.answer(f"👆 Так будет выглядеть объявление. Публикация: <b>{gw.fmt_time(g['publish_at'], tz)}</b>, "
                         f"итоги: <b>{gw.fmt_time(g['ends_at'], tz)}</b>.", reply_markup=CONFIRM_KB)


@router.message(_draft_filter)
async def wizard_message(message: Message, bot, db: Database) -> None:
    uid = message.from_user.id
    g = await db.gw_draft(uid)
    if (message.text or "").strip().lower() in ("отмена", "/cancel"):
        await db.gw_delete_draft(uid)
        await ux.tell(message, "⚠️ Создание конкурса отменено.")
        return
    tz = await _tz(db, g["chat_id"])
    now = int(time.time())
    step = g["step"]
    if step == "text":
        photo = message.photo[-1].file_id if message.photo else None
        body = (message.html_text or "").strip()
        if not body:
            await ux.tell(message, "⚠️ Нужен текст: что разыгрывается и условия (фото — по желанию, с подписью).")
            return
        limit = gw.CAPTION_MAX if photo else gw.TEXT_MAX
        if len(body) > limit:
            await ux.tell(message, f"❌ Слишком длинно: до {limit} символов{' с фото' if photo else ''}.")
            return
        await db.gw_update(g["id"], text=body, photo=photo, step="publish")
        await message.answer(_ask_publish(tz), reply_markup=PUBLISH_KB)
    elif step in ("publish", "end"):
        if not message.text:
            await ux.tell(message, "⚠️ Напишите время текстом или нажмите кнопку.")
            return
        base = g["publish_at"] if step == "end" else None
        ts = gw.parse_when(message.text, now, tz, base=base)
        if ts is None:
            await message.answer("❌ Не понял время. Примеры: <code>20:00</code>, <code>завтра 18:30</code>, "
                                 "<code>25.12 12:00</code>, <code>через 2 часа</code>.")
            return
        await _set_time(message, db, g, step, ts, now, tz)
    else:
        await ux.tell(message, "⚠️ Выберите вариант кнопкой выше или напишите «отмена».")


async def _set_time(message: Message, db: Database, g: dict, step: str, ts: int, now: int, tz) -> None:
    if step == "publish":
        err = gw.check_publish(ts, now)
        if err:
            await message.answer(err)
            return
        ts = max(ts, now)
        await db.gw_update(g["id"], publish_at=ts, step="end")
        g["publish_at"] = ts
        await message.answer(_ask_end(g, tz), reply_markup=END_KB)
    else:
        err = gw.check_end(ts, g["publish_at"])
        if err:
            await message.answer(err)
            return
        await db.gw_update(g["id"], ends_at=ts, step="winners")
        await message.answer("🏆 Сколько победителей?", reply_markup=WINNERS_KB)


@router.callback_query(F.data.startswith("gw:"))
async def wizard_cb(cb: CallbackQuery, bot, db: Database) -> None:
    parts = cb.data.split(":")
    g = await db.gw_draft(cb.from_user.id)
    if g is None or cb.message is None:
        await cb.answer("Черновик не найден — начните заново: «+конкурс» в чате.", show_alert=True)
        return
    now = int(time.time())
    tz = await _tz(db, g["chat_id"])
    op = parts[1]
    if op == "cancel":
        await db.gw_delete_draft(cb.from_user.id)
        await cb.message.answer("⚠️ Создание конкурса отменено.")
    elif op in ("p", "e") and len(parts) == 3 and parts[2].isdigit():
        want = "publish" if op == "p" else "end"
        if g["step"] != want:
            await cb.answer("Этот шаг уже пройден.")
            return
        base = now if op == "p" else g["publish_at"]
        await _set_time(cb.message, db, g, want, base + int(parts[2]), now, tz)
    elif op == "w" and len(parts) == 3 and parts[2].isdigit() and g["step"] == "winners":
        n = min(max(int(parts[2]), 1), gw.MAX_WINNERS)
        await db.gw_update(g["id"], winners=n, step="confirm")
        g.update(winners=n)
        await _preview(cb.message, db, g)
    elif op == "ok" and g["step"] == "confirm":
        if not await _can_manage(bot, db, g["chat_id"], cb.from_user.id):     # права могли отобрать, пока шёл мастер
            await cb.answer("У вас больше нет прав на конкурсы в этом чате.", show_alert=True)
            return
        if not await db.gw_claim(g["id"], "draft", "scheduled"):
            await cb.answer()
            return
        g["status"] = "scheduled"
        if g["publish_at"] <= now:
            ok = await publish(bot, db, g)
            await cb.message.answer(f"✅ Конкурс №{g['id']} опубликован!" if ok else "⚠️ Опубликовать не получилось.")
        else:
            await cb.message.answer(f"✅ Конкурс №{g['id']} запланирован на {gw.fmt_time(g['publish_at'], tz)}. "
                                    f"Отменить: <code>-конкурс {g['id']}</code> в чате.")
        await db.log_action(g["chat_id"], cb.from_user.id, None, "конкурс", f"№{g['id']} создан", now)
    else:
        await cb.answer("Этот шаг уже пройден.")
        return
    await cb.answer()
