"""Мог-баттл: «мог @ник» (или «мог» ответом) — вызов конкретному человеку; «мог» / «могну» без цели — открытый вызов,
принять может любой. После принятия ИИ оценивает аватарку, ник и @юзернейм, а Premium и возраст аккаунта считает бот,
Нори присылает картинку с результатом: у проигравшего на аватарке «MOGGED» и крест. «мог топ» — рейтинг моггеров.

Аватарки и профили уходят во внешний ИИ только после согласия обоих (вызвал сам + принял кнопкой) и только если ИИ
включён в чате и у владельца бота. Без ИИ баттл всё равно идёт — «судит удача», и это написано на картинке."""
from __future__ import annotations

import asyncio
from weakref import WeakValueDictionary
import html
import re
import time
import uuid

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import gender, ux
from bot.toggles import Enabled
from bot import cards, media
from bot import mod_service as ms
from bot import mog
from bot.db import Database
from bot.targets import mention, ping, listed

router = Router(name="mog")
router.message.filter(Enabled("mog_on"))   # группу команд можно выключить в настройках → «Команды»
CHALLENGE_TTL = 300
COOLDOWN = 30               # вызывать — не чаще раза в 30 с на человека
DAILY = 40                  # баттлов с ИИ в сутки на чат (защита ключа ИИ)
_RE = re.compile(r"^(?:мог|mog|могну|могнуть)(?:\s+(@\w+|\d{5,}))?$", re.IGNORECASE)
_TOP = re.compile(r"^(?:мог топ|топ мог|моггеры)$", re.IGNORECASE)
_pending: dict[str, dict] = {}
_cool: dict[tuple[int, int], float] = {}
_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def _kb(cid: str, open_: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text="⚔️ Принять", callback_data=f"mog:{cid}:yes")] + ([] if open_ else [B(text="Отклонить", callback_data=f"mog:{cid}:no")]),
        [B(text="↩️ Отозвать", callback_data=f"mog:{cid}:x")]])


def _prune(now: float) -> None:
    for k in [k for k, v in _pending.items() if v["expires"] < now]:
        _pending.pop(k, None)
    if len(_cool) > 5000:
        for k in [k for k, t in _cool.items() if now - t > COOLDOWN]:
            _cool.pop(k, None)


def _player(user) -> dict:
    return {"uid": user.id, "name": user.full_name, "username": user.username, "premium": bool(getattr(user, "is_premium", False))}


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: bool(t) and _TOP.match(t.strip()) is not None))
async def mog_top(message: Message, db: Database) -> None:
    rows = await db.mog_top(message.chat.id)
    if not rows:
        await message.reply("🗿 Мог-баттлов ещё не было. Вызов: <code>мог @ник</code> или просто <code>мог</code>.")
        return
    lines = [f"{i}. {listed(u, (await db.user_name(u)) or f'id{u}', 28)} — {w} побед, {l} пор." for i, (u, w, l) in enumerate(rows, 1)]
    await message.reply("🗿 <b>Топ моггеров</b>\n" + "\n".join(lines))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.func(lambda t: bool(t) and _RE.match(t.strip()) is not None))
async def mog_challenge(message: Message, bot, db: Database) -> None:
    u = message.from_user
    if u is None or u.is_bot:
        return
    chat, now = message.chat.id, time.time()
    _prune(now)
    token = _RE.match(message.text.strip()).group(1)
    reply = ms.real_reply(message)
    target = None
    if token:
        uid = await db.find_user(token) if token.startswith("@") else int(token)
        if uid is None:
            await ux.tell(message, "❌ Не нашёл такого пользователя.")
            return
        await db.ensure_user(uid)
        target = {"uid": uid, "name": (await db.user_name(uid)) or f"id{uid}", "username": None, "premium": False}
    elif reply is not None and reply.from_user is not None:
        target = _player(reply.from_user)
        if reply.from_user.is_bot:
            await ux.tell(message, "⚠️ С ботами не могаются 🗿")
            return
    if target is not None and target["uid"] in (u.id, (await bot.me()).id):
        await ux.tell(message, "⚠️ Нужен живой соперник, не вы сами и не я.")
        return
    if now - _cool.get((chat, u.id), 0) < COOLDOWN:
        await ux.tell(message, "⚠️ Остынь: вызывать можно раз в 30 секунд.")
        return
    if any(v["chat"] == chat and v["a"]["uid"] == u.id for v in _pending.values()):
        await ux.tell(message, "⚠️ У вас уже висит вызов — дождитесь ответа или отзовите его.")
        return
    _cool[(chat, u.id)] = now
    cid = uuid.uuid4().hex[:10]
    _pending[cid] = {"chat": chat, "a": _player(u), "b": target, "expires": now + CHALLENGE_TTL}
    who = mention(u.id, u.full_name)
    if target is None:
        text = (f"🗿 {who} бросает открытый вызов на <b>мог-баттл</b>! Кто осмелится? Принять может любой.\n"
                "<i>ИИ оценит аватарки, ники и смысл юзернеймов, бот — их длину, подарки и NFT, Premium и возраст аккаунтов.</i>")
    else:
        text = (f"🗿 {who} вызывает {ping(target['uid'], target['name'])} на <b>мог-баттл</b>!\n"
                "<i>ИИ оценит аватарки, ники и смысл юзернеймов, бот — их длину, подарки и NFT, Premium и возраст аккаунтов. Принимаете?</i>")
    await message.answer(text, reply_markup=_kb(cid, target is None))


@router.callback_query(F.data.startswith("mog:"))
async def mog_cb(cb: CallbackQuery, bot, db: Database, ai=None, rt=None) -> None:
    parts = cb.data.split(":")
    if len(parts) != 3 or cb.message is None:
        await cb.answer()
        return
    _, cid, op = parts
    v = _pending.get(cid)
    if v is None or v["chat"] != cb.message.chat.id or v["expires"] < time.time():
        _pending.pop(cid, None)
        await cb.answer("Вызов устарел.", show_alert=True)
        return
    uid = cb.from_user.id
    if op == "x":
        if uid != v["a"]["uid"]:
            await cb.answer("Отозвать может только тот, кто вызывал.", show_alert=True)
            return
        _pending.pop(cid, None)
        await cb.message.edit_text("🗿 Вызов отозван.")
        await cb.answer()
        return
    if uid == v["a"]["uid"]:
        await cb.answer("Сам себя не могнёшь 🗿", show_alert=True)
        return
    if v["b"] is not None and uid != v["b"]["uid"]:
        await cb.answer("Это не ваш вызов.", show_alert=True)
        return
    if cb.from_user.is_bot:
        await cb.answer()
        return
    lock = _locks.setdefault(cid, asyncio.Lock())
    if lock.locked():
        await cb.answer()
        return
    async with lock:
        if _pending.pop(cid, None) is None:          # уже принял кто-то другой
            await cb.answer("Вызов уже принят.", show_alert=True)
            return
        if op == "no":
            await cb.message.edit_text(f"🗿 {mention(uid, cb.from_user.full_name)} {await gender.say(db, uid, '⟦отказался|отказалась⟧')} от мог-баттла. {await gender.say(db, uid, '⟦Зассал|Зассала⟧')}?")
            await cb.answer()
            return
        b = _player(cb.from_user)                    # данные принявшего — из нажатия (имя, ник, Premium точные)
        await cb.answer("Баттл начинается!")
        try:
            await cb.message.edit_text(f"⚔️ {mention(v['a']['uid'], v['a']['name'])} vs {mention(b['uid'], b['name'])} — "
                                       "Нори оценивает профили… 🗿")
        except Exception:
            pass
        await run_battle(cb.message, bot, db, v["a"], b, ai, rt)


async def _gifts(bot, uid: int) -> tuple[int, int]:
    """(обычных, уникальных/NFT) подарков, которые человек показывает в профиле. Скрыл или сбой — (0, 0)."""
    regular = unique = 0
    try:
        offset = ""
        for _ in range(3):                                   # до 300 подарков — дальше счёт уже максимальный
            page = await bot.get_user_gifts(user_id=uid, limit=100, offset=offset or None)
            for g in page.gifts or []:
                if getattr(g, "type", "") == "unique":
                    unique += 1
                else:
                    regular += 1
            offset = getattr(page, "next_offset", None)
            if not offset:
                break
    except Exception:
        pass
    return regular, unique


async def _usernames(bot, uid: int, main: str | None) -> list[str]:
    """Все активные юзернеймы (основной первым): дополнительные бывают только коллекционными (NFT)."""
    try:
        info = await bot.get_chat(uid)
        names = list(getattr(info, "active_usernames", None) or [])
        if names:
            return names
    except Exception:
        pass
    return [main] if main else []


async def _rate(db: Database, ai, p: dict, use_ai: bool, now: int) -> tuple[dict, bool]:
    """(оценка профиля, оценивал ли ИИ). Запомненная оценка — сразу; иначе ИИ (температура 0) и запоминаем;
    без ИИ или при сбое — правила (одни и те же для всех, без случайностей)."""
    fp = mog.fingerprint(p)
    cached = await db.mog_rating_get(fp, now)
    if cached is not None:
        return cached, True
    if use_ai:
        img = await asyncio.to_thread(cards.normalized_jpeg, p["avatar"]) if p.get("avatar") else None
        rating = mog.parse_rating(await ai.mog_rate(mog.rate_prompt(p), img))
        if rating is not None:
            await db.mog_rating_put(fp, rating, now)
            return rating, True
    return mog.rule_rating(p), False


async def run_battle(msg: Message, bot, db: Database, a: dict, b: dict, ai, rt) -> None:
    chat, now = msg.chat.id, int(time.time())
    players = [a, b]
    # всё про обоих игроков — параллельно, а не по очереди: аватарки, подарки, юзернеймы
    got = await asyncio.gather(*(media.avatar_info(bot, p["uid"]) for p in players),
                               *(_gifts(bot, p["uid"]) for p in players),
                               *(_usernames(bot, p["uid"], p.get("username")) for p in players))
    for i, p in enumerate(players):
        p["avatar"], p["avatar_id"] = got[i]
        p["has_photo"] = p["avatar"] is not None
        p["gifts_regular"], p["gifts_unique"] = got[2 + i]
        p["nft_usernames"] = mog.collectible_usernames(got[4 + i])
        p["since"] = mog.since_text(p["uid"], now)
    s = await db.get_settings(chat)
    use_ai = bool(ai is not None and getattr(ai, "has_river", False) and hasattr(ai, "mog_rate") and s["ai_on"]
                  and (rt is None or rt.flag("ai")))
    if use_ai and not await db.take_quota(chat, "mog", now, DAILY):
        use_ai = False                                     # лимит ИИ на сегодня — оцениваем по правилам
    rated = await asyncio.gather(*(_rate(db, ai, p, use_ai, now) for p in players))   # каждого — отдельно
    by_ai = all(r[1] for r in rated)
    if use_ai and not any(r[1] for r in rated):
        await db.refund_quota(chat, "mog", now)             # ИИ не ответил толком — лимит не тратим
        use_ai = False
    sa, sb = mog.scores_from(rated[0][0], a, now), mog.scores_from(rated[1][0], b, now)
    win = mog.winner(sa, sb)
    verdict = ""
    if use_ai and hasattr(ai, "mog_verdict"):
        verdict = mog.clean_verdict(await ai.mog_verdict(mog.verdict_system(s.get("ai_chat_style", "casual")),
                                                         mog.verdict_prompt(players, [sa, sb], win)))
    image = await asyncio.to_thread(cards.mog_card, players, [sa, sb], mog.CRITERIA, win, verdict, by_ai)
    w, l = players[win], players[1 - win]
    await db.mog_add(chat, w["uid"], l["uid"], now)
    caption = (f"🗿 {ping(w['uid'], w['name'])} <b>{await gender.say(db, w['uid'], '⟦могнул|могнула⟧')}</b> {ping(l['uid'], l['name'])} — "
               f"{mog.total(sa if win == 0 else sb)} : {mog.total(sb if win == 0 else sa)}"
               + (f"\n<i>{html.escape(verdict)}</i>" if verdict else ""))
    try:
        await msg.answer_photo(BufferedInputFile(image, "mog.jpg"), caption=caption[:1000])
    finally:
        try:
            await msg.edit_text(f"⚔️ Мог-баттл {mention(a['uid'], a['name'])} vs {mention(b['uid'], b['name'])} завершён 👇")
        except Exception:
            pass
