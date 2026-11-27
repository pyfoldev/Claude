"""Семья в чате: брак, отношения, дети. Предложения подтверждаются кнопками."""
import asyncio
import html
import logging
import re
import time
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import gender, gifs, ux
from bot.db import DAY, Database
from bot.emoji import emoji
from bot.fmt import Html, kv_table, pre_table
from bot.family import REQUEST_TTL, Family
from bot.mod_service import real_reply
from bot.targets import mention, resolve_user, listed

router = Router(name="family")

_T = r"(?:\s+(@\w+|\d{5,}))?"
# (вид, regex, «молчать, если цели нет»): одиночные слова могут быть просто болтовнёй — тогда не отвечаем
_PATTERNS = [
    ("marry", r"^(?:брак)" + _T + "$", False),
    ("marry", r"^(?:предложить брак|пожениться|жениться|выйти замуж)" + _T + "$", False),
    ("my_marriage", r"^(?:мой брак)$", False),
    ("divorce", r"^(?:развод|развестись)$", True),
    ("relation", r"^(?:отношения)" + _T + "$", False),
    ("relation", r"^(?:предложить отношения|встречаться)" + _T + "$", False),
    ("my_relation", r"^(?:мои отношения)$", False),
    ("breakup", r"^расстаться$", True),
    ("adopt", r"^(?:усыновить|удочерить)" + _T + "$", False),
    ("disown", r"^отречься" + _T + "$", False),
    ("leave", r"^уйти из семьи$", True),
    ("my_family", r"^(?:моя семья)$", False),
    ("family", r"^семья" + _T + "$", True),
    ("marriages", r"^браки$", False),
    ("top", r"^топ браков$", False),
    ("bonus", r"^семейный бонус$", False),
]
_COMPILED = [(k, re.compile(p, re.IGNORECASE), quiet) for k, p, quiet in _PATTERNS]
_SINGLE_WORDS = {"пожениться", "жениться", "встречаться", "усыновить", "удочерить", "брак", "отношения"}


@dataclass
class FamCmd:
    kind: str
    target: str | None
    quiet: bool  # если цели нет — не отвечать


def parse_family(text: str | None) -> FamCmd | None:
    t = re.sub(r"\s+", " ", (text or "").strip())
    for kind, rx, quiet in _COMPILED:
        m = rx.match(t)
        if m:
            target = m.group(1) if m.groups() else None
            single = t.lower() in _SINGLE_WORDS
            return FamCmd(kind, target, quiet or single)
    return None


def _kb(rid: str, yes: str, no: str, cancel: bool = True) -> InlineKeyboardMarkup:
    row = [B(text=yes, callback_data=f"fam:{rid}:yes"), B(text=no, callback_data=f"fam:{rid}:no")]
    rows = [row]
    if cancel:
        rows.append([B(text="↩️ Отозвать", callback_data=f"fam:{rid}:x")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _age(since: int, now: int) -> str:
    days = max((now - since) // DAY, 0)
    return f"{time.strftime('%d.%m.%Y', time.localtime(since))} ({days} дн.)"


async def _m(db: Database, uid: int) -> str:
    return mention(uid, (await db.user_name(uid)) or f"id{uid}")


# ---------- команды ----------

@router.message(F.text.func(lambda t: parse_family(t) is not None))
async def family_cmd(message: Message, bot, db: Database, http=None) -> None:
    if message.chat.type not in ("group", "supergroup") or not (await db.get_settings(message.chat.id))["rp_on"]:
        return
    cmd = parse_family(message.text)
    chat, me = message.chat.id, message.from_user.id
    if cmd.kind not in ("family", "marriages", "top", "bonus", "my_family", "my_marriage", "my_relation") \
            and not (cmd.quiet and cmd.target is None and real_reply(message) is None) \
            and not await gender.ensure(message, db):
        return
    fam = Family(db)
    now = int(time.time())
    kind = cmd.kind

    if kind in ("marry", "relation", "adopt", "disown", "family"):
        target = await resolve_user(db, cmd.target, real_reply(message))
        if target is None:
            if kind == "family" and cmd.quiet:
                return
            if not cmd.quiet:
                await ux.tell(message, "⚠️ Ответьте командой на сообщение человека или укажите @ник.")
            return
        tid, tname = target
        if kind == "family":
            await message.reply(await _render_family(db, fam, chat, tid, now), disable_web_page_preview=True)
            return
        if tid == (await bot.me()).id:
            await message.reply("🤖 Я всего лишь бот, у меня нет семьи.")
            return
        if kind == "disown":
            ok = await fam.disown(chat, me, tid)
            await message.reply(f"💔 {await _m(db, tid)} больше не ваш ребёнок." if ok
                                else "Этот человек не ваш ребёнок.")
            return
        await _propose(message, bot, db, fam, kind, tid, now)
        return

    if kind == "divorce":
        sp = await fam.spouse(chat, me)
        if not sp:
            return  # «развод» без брака — просто слово в разговоре
        rid = await fam.create_request(chat, "divorce", me, me, 0, now + REQUEST_TTL)
        m = await message.reply(f"💔 {await _m(db, me)}, вы действительно хотите развестись с "
                                f"{await _m(db, sp['partner'])}?", reply_markup=_kb(rid, "Да, развестись", "Отмена", False))
        await fam.set_request_message(rid, m.message_id)
    elif kind == "breakup":
        other = await fam.end_relation(chat, me)
        if other:
            await message.reply(f"💔 {await _m(db, me)} и {await _m(db, other)} больше не пара.")
            await gifs.extra_gif(bot, http, chat, gifs.FAMILY_MAP["breakup"], await gender.get(db, me), await gender.get(db, other))
    elif kind == "leave":
        if await fam.leave_family(chat, me):
            await message.reply(f"🚪 {await _m(db, me)} {await gender.say(db, me, '⟦ушёл|ушла⟧')} из семьи.")
    elif kind == "my_marriage":
        sp = await fam.spouse(chat, me)
        await message.reply(f"💍 Вы в браке с {await _m(db, sp['partner'])} с {_age(sp['since'], now)}." if sp
                            else "Вы не состоите в браке.")
    elif kind == "my_relation":
        p = await fam.partner(chat, me)
        await message.reply(f"💞 Вы в отношениях с {await _m(db, p['partner'])} с {_age(p['since'], now)}." if p
                            else "У вас нет отношений.")
    elif kind == "my_family":
        await message.reply(await _render_family(db, fam, chat, me, now), disable_web_page_preview=True)
    elif kind in ("marriages", "top"):
        await message.reply(await _render_marriages(db, fam, chat, now, newest=(kind == "marriages")),
                            disable_web_page_preview=True)
    elif kind == "bonus":
        sp = await fam.spouse(chat, me)
        if not sp:
            await ux.tell(message, "⚠️ Семейный бонус только для супругов: сначала поженитесь.")
            return
        got = await fam.claim_bonus(chat, me, now)
        await message.reply(f"{emoji('coin')} Семейный бонус: <b>+{got}</b> монет. Чем больше детей, тем он больше!"
                            if got else "Свой бонус вы сегодня уже получили.")


async def _propose(message: Message, bot, db: Database, fam: Family, kind: str, tid: int, now: int) -> None:
    chat, me = message.chat.id, message.from_user.id
    checker = {"marry": fam.check_marry, "relation": fam.check_relation, "adopt": fam.check_adopt}[kind]
    a, b = await _m(db, me), await _m(db, tid)
    async with db.atomic():
        err = await checker(chat, me, tid)
        busy = not err and (await fam.has_pending(chat, me, now) or await fam.has_pending(chat, tid, now))
        rid = None if err or busy else await fam.create_request(chat, kind, me, tid, 0, now + REQUEST_TTL)
    if err:
        await message.reply(f"{emoji('fail')} {err}")
        return
    if busy:
        await ux.tell(message, "⚠️ У вас или у этого человека уже есть незавершённое предложение.")
        return
    text, yes, no = {
        "marry": (f"💍 {a} делает предложение {b}!\n{b}, вы согласны?", "💍 Да", "💔 Нет"),
        "relation": (f"💞 {a} предлагает {b} встречаться!\n{b}, что скажете?", "💞 Да", "💔 Нет"),
        "adopt": (f"👶 {a} хочет взять {b} в свою семью!\n{b}, вы согласны?", "👨‍👩‍👧 Да", "Нет"),
    }[kind]
    try:
        sent = await message.answer(text, reply_markup=_kb(rid, yes, no))
        await fam.set_request_message(rid, sent.message_id)
    except Exception:
        await fam.delete_request(rid)
        raise


# ---------- кнопки ----------

@router.callback_query(F.data.startswith("fam:"))
async def family_cb(cb: CallbackQuery, db: Database, http=None) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or parts[2] not in ("yes", "no", "x"):
        await cb.answer()
        return
    _, rid, op = parts
    fam = Family(db)
    req = await fam.get_request(rid)
    if (req is None or cb.message is None or req["chat_id"] != cb.message.chat.id
            or req["message_id"] != cb.message.message_id):
        await cb.answer("Это предложение уже недействительно.", show_alert=True)
        return
    uid, now = cb.from_user.id, int(time.time())
    if req["expires_at"] < now:
        await fam.delete_request(rid)
        await cb.answer("Время на ответ вышло.", show_alert=True)
        return
    a, b, chat, kind = req["from_user"], req["to_user"], req["chat_id"], req["kind"]
    decider = a if kind == "divorce" else b

    if op == "x":
        if uid != a:
            await cb.answer("Отозвать может только автор.", show_alert=True)
            return
        await fam.delete_request(rid)
        await cb.message.edit_text("↩️ Предложение отозвано.")
    elif op == "no":
        if uid != decider:
            await cb.answer("Это решение не за вами.", show_alert=True)
            return
        await fam.delete_request(rid)
        await cb.message.edit_text("💔 Отказ." if kind != "divorce" else "Развод отменён.")
    elif op == "yes":
        if uid != decider:
            await cb.answer("Это решение не за вами.", show_alert=True)
            return
        if kind == "divorce":
            # Завершение пары берёт собственную блокировку; не держим перед ней блокировку БД.
            deleted = await fam.delete_request(rid)
            text = await _apply(db, fam, kind, chat, a, b, now) if deleted else ""
        else:
            # При сбое предложение остаётся доступным для повторного подтверждения.
            async with db.atomic():
                deleted = await fam.delete_request(rid)
                text = await _apply(db, fam, kind, chat, a, b, now) if deleted else ""
        if not deleted:
            await cb.answer()
            return
        await cb.message.edit_text(text)
        if "теперь" in text or "больше не" in text:                      # получилось — к тексту добавляем гифку
            await gifs.extra_gif(cb.bot, http, chat, gifs.FAMILY_MAP.get(kind), await gender.get(db, a), await gender.get(db, b))
    await cb.answer()


async def _apply(db: Database, fam: Family, kind: str, chat: int, a: int, b: int, now: int) -> str:
    A, Bm = await _m(db, a), await _m(db, b)
    if kind == "divorce":
        other = await fam.divorce(chat, a)
        return f"💔 {A} и {await _m(db, other)} больше не в браке." if other else "Вы уже не в браке."
    async with db.atomic():
        check = {"marry": fam.check_marry, "relation": fam.check_relation, "adopt": fam.check_adopt}[kind]
        err = await check(chat, a, b)  # пока ждали ответа, всё могло измениться
        if err:
            return f"{emoji('fail')} Не получилось: {err}"
        if kind == "marry":
            await fam.marry(chat, a, b, now)
            return f"💒 {A} и {Bm} теперь в браке! Совет да любовь 💍\n🔥 Искры, уровень и тепло остаются с вами: <code>пара</code>"
        if kind == "relation":
            await fam.start_relation(chat, a, b, now)
            return (f"💞 {A} и {Bm} теперь пара!\n"
                    "🔥 У вас 100 искр на двоих, раз в сутки часть уходит на жизнь. Пополняйте их делами: <code>пара действия</code>.")
        await fam.adopt(chat, a, b, now)
        return f"👨‍👩‍👧 {Bm} теперь в семье {A}!"


# ---------- отображение ----------

async def _plain(db: Database, uid: int):
    return listed(uid, (await db.user_name(uid)) or f"id{uid}", 28)


async def _render_family(db: Database, fam: Family, chat: int, uid: int, now: int) -> str:
    v = await fam.view(chat, uid)

    async def names(ids):
        return Html(", ".join([await _plain(db, i) for i in ids]) or "—")
    rows = [("Супруг(а)", Html(f"{await _plain(db, v['spouse']['partner'])} · {html.escape(_age(v['spouse']['since'], now))}") if v["spouse"] else "—")]
    if v["partner"]:
        rows.append(("Пара", Html(f"{await _plain(db, v['partner']['partner'])} · {html.escape(_age(v['partner']['since'], now))}")))
    rows += [("Родители", await names(v["parents"])), ("Дети", await names(v["children"]))]
    if v["siblings"]:
        rows.append(("Братья/сёстры", await names(sorted(v["siblings"]))))
    return f"👨‍👩‍👧‍👦 <b>Семья · {await _plain(db, uid)}</b>\n" + kv_table(rows, key_width=13, value_width=34)


async def _render_marriages(db: Database, fam: Family, chat: int, now: int, newest: bool) -> str:
    total = await fam.count_marriages(chat)
    if not total:
        return "💍 В этом чате пока нет браков."
    rows = await fam.list_marriages(chat, 10, max(total - 10, 0) if newest else 0)
    if newest:
        rows = rows[::-1]
    title = "💍 <b>Новые браки</b>" if newest else "🏆 <b>Самые долгие браки</b>"
    table = pre_table([(str(i), Html(f"{await _plain(db, r['u1'])} + {await _plain(db, r['u2'])}"), f"{max((now - r['since']) // DAY, 0)} дн.")
                       for i, r in enumerate(rows, 1)], header=("#", "Пара", "Вместе"), align="llr", maxw=(3, 26, 8))
    return f"{title} · всего {total}\n{table}"


async def family_watchdog(bot, db: Database) -> None:
    """Просроченные предложения закрываются сами."""
    fam = Family(db)
    while True:
        await asyncio.sleep(30)
        try:
            for r in await fam.expired_requests(int(time.time())):
                if await fam.delete_request(r["id"]) and r["message_id"]:
                    try:
                        await bot.edit_message_text("⌛ Время вышло, предложение отменено.",
                                                    chat_id=r["chat_id"], message_id=r["message_id"])
                    except Exception:
                        pass
        except Exception:
            logging.exception("family watchdog")
