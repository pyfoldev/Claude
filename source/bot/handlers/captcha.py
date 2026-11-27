"""Капча для новичков.

Telegram не разрешает web_app-кнопки в группах, поэтому в группе показывается URL-кнопка
на личный чат с ботом (/start cap_<token>), а там уже кнопка Mini App.
"""
import asyncio
import html
import logging
import re
import secrets
import time
from collections import defaultdict, deque

from aiogram import F, Router
from aiogram.filters import JOIN_TRANSITION, ChatMemberUpdatedFilter
from aiogram.types import (CallbackQuery, ChatJoinRequest, ChatMemberUpdated, ChatPermissions, InlineKeyboardButton as B,
                           InlineKeyboardMarkup, Message, WebAppInfo)

from bot import ux
from bot.captcha_server import level_params, new_code
from bot.db import Database
from bot.emoji import emoji
from bot.mod_service import _FULL
from bot.handlers.chatinfo import send_welcome
from bot.raid import raid_guard
from bot.targets import ping

router = Router(name="captcha")
_passed: dict[tuple[int, int], float] = {}   # кто только что прошёл капчу по заявке: повторной капчи после одобрения не нужно
PASSED_TTL = 600
FAIL_WINDOW = 900                       # окно, в котором считаем «непрошедших» в чате
WAVE_FAILS, HEAVY_FAILS = 3, 6          # столько провалов за окно — повышенная / усиленная капча
_fails: dict[int, deque] = defaultdict(deque)   # чат -> когда участники не прошли капчу вовремя


def record_failure(chat_id: int, now: float | None = None) -> None:
    now = time.time() if now is None else now
    q = _fails[chat_id]
    q.append(now)
    while q and now - q[0] > FAIL_WINDOW:
        q.popleft()


def recent_failures(chat_id: int, now: float | None = None) -> int:
    now = time.time() if now is None else now
    q = _fails.get(chat_id)
    if not q:
        return 0
    while q and now - q[0] > FAIL_WINDOW:
        q.popleft()
    return len(q)


def pick_level(chat_id: int, raid_active: bool, user, now: float | None = None) -> int:
    """Сложность капчи по обстановке. Рейд — максимум; волна непрошедших в чате — выше; без ника — на ступень выше, если в чате уже были непрошедшие;
    Premium-аккаунт (платный, боты-спамеры почти не бывают Premium) — обычная, если нет рейда."""
    if raid_active:
        return 2
    fails = recent_failures(chat_id, now)
    score = (2 if fails >= HEAVY_FAILS else 1 if fails >= WAVE_FAILS else 0)
    if fails and not getattr(user, "username", None):
        score += 1          # без ника — подозрительнее, но только когда в чате уже были непрошедшие (многие живые люди без ника)
    if getattr(user, "is_premium", False):
        score = min(score, 1) if fails >= HEAVY_FAILS else 0
    return min(score, 2)
_no_rights_warned: dict[int, float] = {}   # чат -> когда последний раз предупреждали, что у бота нет права ограничивать


_GROUPS = {"group", "supergroup"}   # капча, антирейд и приветствие — только для групп. В каналах (например, канал
                                    # обязательной подписки, где бот — админ) Telegram тоже присылает «вступил», но там
                                    # ограничивать некого и писать в канал нельзя.


_handled: dict[tuple[int, int], tuple[float, str]] = {}   # (чат, человек) -> (когда, каким путём) обработали вход
HANDLED_TTL = 20
BTN_EMOJI = ["🐱", "🐶", "🦄", "🐹", "🐸", "🤡", "🐥", "🐦", "🐰", "🐻"]
BTN_TRIES = 3


def _recent(chat_id: int, user_id: int, source: str) -> bool:
    """True, если этот же вход уже обработал ДРУГОЙ путь (chat_member и служебное сообщение приходят оба).
    Повторный вход тем же путём — это новый вход, его обрабатываем."""
    now = time.time()
    for k in [k for k, (t, _s) in _handled.items() if now - t > HANDLED_TTL]:
        _handled.pop(k, None)
    prev = _handled.get((chat_id, user_id))
    if prev and prev[1] != source:
        _handled.pop((chat_id, user_id), None)
        return True
    _handled[(chat_id, user_id)] = (now, source)
    return False


@router.chat_member(F.chat.type.in_(_GROUPS), ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_join(event: ChatMemberUpdated, bot, db: Database, webapp_url: str = "") -> None:
    user = event.new_chat_member.user
    old = event.old_chat_member
    # заявку одобрил человек (админ), а не сам бот после капчи: проверять такого участника не нужно
    approved = bool(event.via_join_request) and event.from_user.id not in (user.id, (await bot.me()).id)
    await handle_join(bot, db, event.chat.id, user, webapp_url,
                      old_muted=old.status == "restricted" and not getattr(old, "can_send_messages", False), source="member",
                      approved=approved)


@router.message(F.chat.type.in_(_GROUPS), F.new_chat_members)
async def on_join_service(message: Message, bot, db: Database, webapp_url: str = "") -> None:
    """Запасной путь: если Telegram не прислал chat_member (бот не админ или нет права), вход виден по служебному сообщению."""
    for user in message.new_chat_members or []:
        pending = await db.get_captcha_for_user(message.chat.id, user.id)         # висит капча по заявке — её одобрил админ
        approved = bool(pending and pending.get("kind") in ("join_request", "guard"))
        await handle_join(bot, db, message.chat.id, user, webapp_url, old_muted=False, source="service", approved=approved)


def human_time(seconds: int) -> str:
    """90 → «1 мин. 30 сек.», 1800 → «30 мин.», 7200 → «2 ч.»."""
    seconds = int(seconds)
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{seconds // 3600} ч."
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds // 60} мин."
    if seconds > 60:
        return f"{seconds // 60} мин. {seconds % 60} сек."
    return f"{seconds} сек."


_TIME_RE = re.compile(r"^(\d{1,5})\s*(с|сек|секунд[ы]?|м|мин|минут[ы]?|ч|час|часа|часов)?$", re.IGNORECASE)
MIN_CAPTCHA, MAX_CAPTCHA = 30, 24 * 3600


def parse_captcha_time(text: str) -> int | None:
    """«30м», «45 мин», «90с», «2ч», «15» (минуты) → секунды; вне диапазона 30 с … 24 ч — None."""
    m = _TIME_RE.match((text or "").strip())
    if not m:
        return None
    n, unit = int(m.group(1)), (m.group(2) or "м").lower()
    secs = n * (1 if unit.startswith("с") else 3600 if unit.startswith("ч") else 60)
    return secs if MIN_CAPTCHA <= secs <= MAX_CAPTCHA else None


_CMD_RE = re.compile(r"^капча\s+время(?:\s+(.+))?$", re.IGNORECASE)


@router.message(F.chat.type.in_(_GROUPS), F.text.func(lambda t: bool(t) and _CMD_RE.match(t.strip()) is not None))
async def captcha_time_cmd(message: Message, bot, db: Database) -> None:
    """«капча время 30м» — сколько у новичка времени на капчу (от 30 секунд до 24 часов); «капча время» — показать."""
    from bot import mod_service as ms
    from bot.ranks import need_rank
    if message.from_user is None:
        return
    chat = message.chat.id
    arg = _CMD_RE.match(message.text.strip()).group(1)
    cur = (await db.get_settings(chat))["captcha_timeout"]
    if arg is None:
        await message.reply(f"🛡 Время на капчу: <b>{human_time(cur)}</b>\n<i>Изменить: <code>капча время 30м</code> "
                            "(от 30 сек. до 24 ч.)</i>")
        return
    need = need_rank(await db.get_access(chat), "настройки чата")
    if await ms.effective_rank(bot, db, chat, message.from_user.id) < need:
        await ux.tell(message, f"⚠️ Это доступно с ранга {need}.")
        return
    secs = parse_captcha_time(arg)
    if secs is None:
        await ux.tell(message, "❌ Не понял время. Примеры: <code>капча время 30м</code>, <code>90с</code>, <code>2ч</code> "
                               "(от 30 секунд до 24 часов).")
        return
    await db.set_setting(chat, "captcha_timeout", secs, actor=message.from_user.id)
    note = "\n<i>Для заявок через личку Telegram даёт боту не больше 5 минут — там время ограничено.</i>" if secs > 280 else ""
    await message.reply(f"✅ Время на капчу: <b>{human_time(secs)}</b>{note}")


_rechecked: dict[tuple[int, int], float] = {}   # (чат, человек) -> когда выдали повторную капчу
RECHECK_TTL = 900


async def _approved_by_admin(bot, db: Database, chat_id: int, user) -> None:
    """Заявку принял админ (не бот): капчу не выдаём и ничего не ограничиваем; висящую капчу по заявке закрываем,
    иначе она позже истекла бы и отклонила/исключила уже принятого человека."""
    cap = await db.get_captcha_for_user(chat_id, user.id)
    if cap and cap.get("kind") in ("join_request", "guard"):
        await db.consume_captcha(cap["token"])
        if cap["kind"] == "guard":
            await db.guard_query_pop(chat_id, user.id)
        else:
            try:
                await bot.edit_message_text("✅ Заявку одобрил администратор — проверка не нужна.",
                                            chat_id=cap["user_id"], message_id=cap["message_id"], reply_markup=None)
            except Exception:
                pass
    await send_welcome(bot, db, chat_id, user.id, user.full_name)


async def handle_join(bot, db: Database, chat_id: int, user, webapp_url: str = "", old_muted: bool = False,
                      source: str = "member", min_level: int = 0, approved: bool = False) -> None:
    if user.is_bot or _recent(chat_id, user.id, source):
        return
    if approved:
        await _approved_by_admin(bot, db, chat_id, user)
        return
    old_cap = await db.get_captcha_for_user(chat_id, user.id)
    if old_muted and not old_cap:
        return  # человек в муте у модератора: капча не должна его снять.
        # (restricted с правом писать — просто остаток после «размут»: такому капча нужна, как и всем)
    if old_muted and await db.get_state(chat_id, user.id, "mute", int(time.time())):
        return
    settings = await db.get_settings(chat_id)
    if settings.get("cas_mode", "off") != "off" and source != "recheck":
        from bot import cas
        if await cas.handle(bot, db, chat_id, user, settings["cas_mode"]) == "ban":
            return                                              # забанен по базе спамеров — капча не нужна
    if settings.get("dupe_on") and source != "recheck":
        from bot import dupes
        await dupes.check_join(bot, db, chat_id, user)       # «похож на забаненного» — уведомление модераторам
    raid_active = False
    if time.time() - _passed.get((chat_id, user.id), 0) < PASSED_TTL:
        await send_welcome(bot, db, chat_id, user.id, user.full_name)  # заявка одобрена после капчи в личке
        return
    if settings["raid_on"]:
        raid_active, fresh = raid_guard.register(chat_id, time.time(), settings)
        if fresh:
            await _raid_announce(bot, chat_id, settings)
            await db.log_action(chat_id, 0, None, "антирейд", f"{settings['raid_n']} входов за {settings['raid_sec']} с", int(time.time()))
        if raid_active and settings["raid_action"] == "kick":
            try:
                await bot.ban_chat_member(chat_id, user.id)
                await bot.unban_chat_member(chat_id, user.id)
            except Exception:
                pass
            return
    # во время рейда капча обязательна, даже если в чате она выключена
    if not (settings["captcha_on"] or raid_active):
        if not old_cap:
            await send_welcome(bot, db, chat_id, user.id, user.full_name)
        return
    if old_cap:
        # человек вышел и вернулся, пока капча ещё висела: старое сообщение/код больше не нужны — выдаём новую капчу,
        # а не оставляем его молча в муте
        if await db.consume_captcha(old_cap["token"]) and old_cap.get("kind") != "join_request":
            try:
                await bot.delete_message(chat_id, old_cap["message_id"])
            except Exception:
                pass
    try:
        await bot.restrict_chat_member(chat_id, user.id, permissions=ChatPermissions(can_send_messages=False))
    except Exception:
        # нет прав — защитить не можем; раз в час говорим об этом чату, а не молчим
        if time.time() - _no_rights_warned.get(chat_id, 0) > 3600:
            _no_rights_warned[chat_id] = time.time()
            try:
                await bot.send_message(chat_id, "⚠️ Капча не работает: у бота нет права «ограничивать участников». "
                                                "Сделайте его админом с этим правом (проверка — <code>диагностика</code>).")
            except Exception:
                pass
        return
    token = secrets.token_urlsafe(12)
    level = max(pick_level(chat_id, raid_active, user), min_level)
    minutes = human_time(settings["captcha_timeout"])
    expires = int(time.time()) + settings["captcha_timeout"]
    if not webapp_url:
        # без домена Mini App не открыть (нужен https) — вместо «капчи нет» даём простую проверку кнопкой прямо в чате
        right = secrets.randbelow(len(BTN_EMOJI))
        pool = [i for i in range(len(BTN_EMOJI)) if i != right]
        secrets.SystemRandom().shuffle(pool)
        opts = pool[:5] + [right]
        secrets.SystemRandom().shuffle(opts)
        kb = InlineKeyboardMarkup(inline_keyboard=[[B(text=BTN_EMOJI[i], callback_data=f"capb:{token}:{i}") for i in opts[:3]],
                                                   [B(text=BTN_EMOJI[i], callback_data=f"capb:{token}:{i}") for i in opts[3:]]])
        text = (f'{emoji("shield")} {ping(user.id, user.full_name)}, это проверка на человека: нажмите {BTN_EMOJI[right]}, '
                f"чтобы писать в чат. Время — {minutes}, иначе вас исключат.")
        answer = {"btn": right}
    else:
        username = (await bot.me()).username
        kb = InlineKeyboardMarkup(inline_keyboard=[[B(
            text="✅ Пройти проверку", url=f"https://t.me/{username}?start=cap_{token}")]])
        text = (f'{emoji("shield")} {ping(user.id, user.full_name)}, пройдите капчу, '
                f"чтобы писать в чат: нажмите кнопку ниже, в чате с ботом нажмите «Запустить» и пройдите проверку. "
                f"Время — {minutes}, иначе вас исключат.")
        answer = new_code(level_params(level)[0])
    try:
        m = await bot.send_message(chat_id, text, reply_markup=kb)
    except Exception:
        await make_on_pass(bot)(chat_id, user.id, 0)  # сообщение не ушло — не оставляем человека в муте
        return
    try:
        await db.create_captcha(token, chat_id, user.id, answer, expires, m.message_id, level=level)
    except Exception:
        logging.exception("captcha: не удалось сохранить проверку; снимаем временное ограничение")
        try:
            await make_on_pass(bot)(chat_id, user.id, m.message_id)
        except Exception:
            logging.exception("captcha: не удалось снять временное ограничение после ошибки БД")


@router.callback_query(F.data.startswith("capb:"))
async def button_captcha(cb: CallbackQuery, bot, db: Database) -> None:
    try:
        _, token, idx = cb.data.split(":")
        idx = int(idx)
    except ValueError:
        await cb.answer()
        return
    cap = await db.get_captcha(token)
    if not cap or cap["expires_at"] <= time.time():
        await cb.answer("Проверка уже закончилась.", show_alert=True)
        return
    if cap["user_id"] != cb.from_user.id:
        await cb.answer("Эта проверка не для вас.", show_alert=True)
        return
    if not isinstance(cap["answer"], dict) or idx != cap["answer"].get("btn"):
        if await db.take_captcha_attempt(token, BTN_TRIES - 1):
            await cb.answer("Не тот. Попробуйте ещё раз.", show_alert=True)
        else:
            if await db.consume_captcha(token):
                await cb.answer("Попытки закончились.", show_alert=True)
                await expire_captcha(bot, cap, db)
        return
    if await db.consume_captcha(token):
        try:
            result = await make_on_pass(bot, db)(cap["chat_id"], cap["user_id"], cap["message_id"])
        except Exception:
            logging.exception("captcha: Telegram не применил результат проверки")
            await cb.answer("Проверка пройдена, но доступ не обновлён. Обратитесь к администратору.", show_alert=True)
            return
        text = "Проверка пройдена. Ограничение модератора сохранено." if result == "restricted" else "Проверка пройдена."
        await cb.answer(text, show_alert=(result == "restricted"))
    else:
        await cb.answer()


async def _raid_announce(bot, chat_id: int, settings: dict) -> None:
    what = "исключаются" if settings["raid_action"] == "kick" else "проходят усиленную капчу"
    try:
        await bot.send_message(
            chat_id, f"{emoji('shield')} <b>Антирейд!</b> Слишком много входов "
                     f"({settings['raid_n']} за {settings['raid_sec']} сек.). "
                     f"Новые участники {what} ещё {settings['raid_minutes']} мин.")
    except Exception:
        pass


async def _guard_request(event: ChatJoinRequest, bot, db: Database, webapp_url: str) -> None:
    """Бот назначен стражем заявок чата (Bot API 10.2): заявка приходит с query_id, и за 10 секунд нужно либо показать
    человеку Mini App (sendChatJoinRequestWebApp), либо решить сразу (answerChatJoinRequestQuery). Капча открывается
    прямо в заявке, без писем в личку и без сообщений-ловушек в чате; результат капчи решает судьбу заявки."""
    user, chat_id, qid = event.from_user, event.chat.id, event.query_id
    now = int(time.time())

    async def answer(result: str) -> None:
        try:
            await bot.answer_chat_join_request_query(qid, result)
        except Exception as e:
            logging.warning("answerChatJoinRequestQuery(%s) не удался: %s", result, e)

    settings = await db.get_settings(chat_id)
    if user.is_bot or await db.get_state(chat_id, user.id, "ban", now):
        await answer("decline")
        return
    if settings.get("cas_mode", "off") != "off":                 # в базе спамеров: ban — отклонить, warn — модераторам
        from bot import cas
        hit = await cas.handle(bot, db, chat_id, user, "warn" if settings["cas_mode"] == "warn" else "ban")
        if hit == "ban":
            await answer("decline")
            return
        if hit == "warn":
            await answer("queue")
            return
    if settings.get("dupe_on"):                                  # похож на забаненного — решают модераторы
        from bot import dupes
        if await dupes.find_match(db, chat_id, user, bot=bot) is not None:
            await dupes.check_join(bot, db, chat_id, user)
            await answer("queue")
            return
    if settings["captcha_on"] and webapp_url:
        token = secrets.token_urlsafe(12)
        level = pick_level(chat_id, False, user)
        expires = now + settings["captcha_timeout"]
        await db.create_captcha(token, chat_id, user.id, new_code(level_params(level)[0]), expires, 0,
                                kind="guard", level=level)
        await db.guard_query_set(chat_id, user.id, qid, now)
        try:
            await bot.send_chat_join_request_web_app(qid, f"{webapp_url}/captcha?token={token}")
            return
        except Exception as e:
            logging.warning("sendChatJoinRequestWebApp не удался: %s", e)
            await db.consume_captcha(token)
            await db.guard_query_pop(chat_id, user.id)
            await answer("queue")                                # не смогли показать капчу — решат админы
            return
    await answer("approve" if settings.get("guard_default") == "approve" else "queue")


@router.chat_join_request(F.chat.type.in_(_GROUPS))
async def on_join_request(event: ChatJoinRequest, bot, db: Database, webapp_url: str = "") -> None:
    """Заявка на вступление: бот пишет человеку в личку с кнопкой капчи и одобряет заявку, когда проверка пройдена.
    Если бот — страж заявок (в заявке есть query_id), капча открывается прямо в ней."""
    if event.query_id:
        await _guard_request(event, bot, db, webapp_url)
        return
    user, chat_id = event.from_user, event.chat.id
    settings = await db.get_settings(chat_id)
    if settings.get("cas_mode", "off") != "off" and not user.is_bot:
        from bot import cas
        hit = await cas.handle(bot, db, chat_id, user, settings["cas_mode"])
        if hit == "ban":
            try:
                await bot.decline_chat_join_request(chat_id, user.id)
            except Exception:
                pass
            return
        if hit == "warn":
            return                                              # заявку решают модераторы
    if user.is_bot or not webapp_url or not settings["captcha_on"]:
        return  # капча выключена — заявку решают админы
    if await db.get_captcha_for_user(chat_id, user.id):
        return
    token = secrets.token_urlsafe(12)
    timeout = min(settings["captcha_timeout"], 280)  # Telegram разрешает писать по заявке только 5 минут
    kb = InlineKeyboardMarkup(inline_keyboard=[[B(
        text="✅ Открыть проверку", web_app=WebAppInfo(url=f"{webapp_url}/captcha?token={token}"))]])
    try:
        m = await bot.send_message(
            event.user_chat_id,
            f"{emoji('shield')} Вы подали заявку в «{html.escape(event.chat.title or 'чат')}».\n"
            f"Чтобы её одобрили, пройдите проверку: нажмите кнопку и подтвердите, что вы не бот. "
            f"Время — {human_time(timeout)}.", reply_markup=kb)
    except Exception:
        return  # написать человеку нельзя — заявка остаётся на ручное решение админов
    level = pick_level(chat_id, False, user)
    await db.create_captcha(token, chat_id, user.id, new_code(level_params(level)[0]), int(time.time()) + timeout,
                            m.message_id, kind="join_request", level=level)


@router.message(F.chat.type == "private", F.text.startswith("/start cap_"))
async def start_captcha(message: Message, db: Database, webapp_url: str) -> None:
    token = message.text.split("cap_", 1)[1].strip()
    cap = await db.get_captcha(token)
    if not cap or cap["user_id"] != message.from_user.id or cap["expires_at"] <= time.time():
        await ux.tell(message, "⚠️ Проверка не найдена, уже пройдена или время вышло.")
        return
    if not webapp_url:
        await ux.tell(message, "⚠️ WEBAPP_URL не настроен — обратитесь к администратору бота.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[B(
        text="✅ Открыть проверку", web_app=WebAppInfo(url=f"{webapp_url}/captcha?token={token}"))]])
    await message.answer("Нажмите кнопку и пройдите проверку:", reply_markup=kb)


async def _recheck(bot, db: Database, chat_id: int, user_id: int, webapp_url: str) -> bool:
    """Повторная капча (настройка «Повторная проверка»): после первой — вторая, повышенной сложности, для подозрительных
    аккаунтов (без @ника) или для всех. Один раз за вход. True — повторная капча выдана."""
    mode = (await db.get_settings(chat_id)).get("captcha_recheck", "off")
    now = time.time()
    if mode == "off" or now - _rechecked.get((chat_id, user_id), 0) < RECHECK_TTL:
        return False
    try:
        user = (await bot.get_chat_member(chat_id, user_id)).user
    except Exception:
        return False
    if mode == "susp" and user.username:
        return False
    if len(_rechecked) > 5000:
        _rechecked.clear()
    _rechecked[(chat_id, user_id)] = now
    _handled.pop((chat_id, user_id), None)                # иначе защита от «двойной обработки входа» проглотит вызов
    await handle_join(bot, db, chat_id, user, webapp_url, source="recheck", min_level=1)
    cap = await db.get_captcha_for_user(chat_id, user_id)
    if not cap or cap["expires_at"] <= time.time():
        _rechecked.pop((chat_id, user_id), None)
        return False
    return True


def make_on_pass(bot, db=None, webapp_url: str = ""):
    async def on_pass(chat_id: int, user_id: int, message_id: int, kind: str = "member") -> str:
        if kind == "guard":
            qid = await db.guard_query_pop(chat_id, user_id) if db is not None else None
            try:
                if qid:
                    await bot.answer_chat_join_request_query(qid, "approve")
                else:
                    await bot.approve_chat_join_request(chat_id, user_id)
            except Exception:
                try:
                    await bot.approve_chat_join_request(chat_id, user_id)
                except Exception:
                    if qid and db is not None:
                        await db.guard_query_set(chat_id, user_id, qid, int(time.time()))
                    raise
            _passed[(chat_id, user_id)] = time.time()
            return "done"
        if kind == "join_request":
            try:
                await bot.approve_chat_join_request(chat_id, user_id)
                _passed[(chat_id, user_id)] = time.time()
                result = "done"
                text = "✅ Проверка пройдена, заявка одобрена. Добро пожаловать!"
            except Exception:
                result = "pending"
                text = "✅ Проверка пройдена. Не удалось одобрить заявку автоматически — её проверит администратор."
            try:
                await bot.edit_message_text(text, chat_id=user_id, message_id=message_id, reply_markup=None)
            except Exception:
                pass
            return result
        if db is not None:
            muted = await db.get_state(chat_id, user_id, "mute", int(time.time()))
            if muted:
                await bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False),
                                               until_date=muted["until"])
                try:
                    await bot.delete_message(chat_id, message_id)
                except Exception:
                    pass
                return "restricted"
        if db is not None and message_id and kind == "member" and await _recheck(bot, db, chat_id, user_id, webapp_url):
            return "recheck"
        # Сохраняем даже запрещающие разрешения чата; при сетевом сбое не выдаём полные права.
        chat = await bot.get_chat(chat_id)
        perms = chat.permissions if chat.permissions is not None else _FULL
        await bot.restrict_chat_member(chat_id, user_id, permissions=perms)
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            pass
        if db is not None and message_id:
            try:
                await send_welcome(bot, db, chat_id, user_id)
            except Exception:
                logging.exception("captcha: не удалось отправить приветствие")
        return "done"
    return on_pass


async def expire_captcha(bot, cap: dict, db: Database | None = None) -> None:
    """Время вышло: участника исключаем (вернуться можно), заявку отклоняем."""
    record_failure(cap["chat_id"])   # волна непройденных капч поднимает сложность для следующих новичков
    if cap.get("kind") == "guard":
        qid = await db.guard_query_pop(cap["chat_id"], cap["user_id"]) if db is not None else None
        try:
            if qid:
                await bot.answer_chat_join_request_query(qid, "decline")
            else:
                await bot.decline_chat_join_request(cap["chat_id"], cap["user_id"])
        except Exception:
            try:
                await bot.decline_chat_join_request(cap["chat_id"], cap["user_id"])
            except Exception:
                pass
        return
    if cap.get("kind") == "join_request":
        try:
            await bot.decline_chat_join_request(cap["chat_id"], cap["user_id"])
        except Exception:
            pass
        try:
            await bot.edit_message_text("⌛ Время на проверку вышло, заявка отклонена. Подайте её снова.",
                                        chat_id=cap["user_id"], message_id=cap["message_id"], reply_markup=None)
        except Exception:
            pass
        return
    try:
        await bot.ban_chat_member(cap["chat_id"], cap["user_id"])
        await bot.unban_chat_member(cap["chat_id"], cap["user_id"])
    except Exception:
        pass
    try:
        await bot.delete_message(cap["chat_id"], cap["message_id"])
    except Exception:
        pass


async def captcha_watchdog(bot, db: Database) -> None:
    """Раз в 15 секунд закрывает просроченные капчи."""
    while True:
        await asyncio.sleep(15)
        try:
            for cap in await db.expired_captchas(int(time.time())):
                if await db.consume_captcha(cap["token"]):
                    await expire_captcha(bot, cap, db)
        except Exception:
            logging.exception("captcha watchdog")
