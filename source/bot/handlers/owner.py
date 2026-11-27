"""Панель владельца: управление ботом из личных сообщений. Доступна только пользователям из OWNER_ID."""
from __future__ import annotations

import asyncio
import html
import os
import platform
import re
import tempfile
import time

import aiogram
from aiogram import F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import BaseFilter
from aiogram.types import (CallbackQuery, FSInputFile, InlineKeyboardButton as B, InlineKeyboardMarkup, Message)

from bot import mod_service as ms
from bot.diagnostics import CHECKLIST, diagnose_chat, diagnose_global
from bot.db import Database
from bot.fmt import kv_table
from bot.parsing import ModCommand
from bot.runtime import Runtime
from bot.targets import listed

router = Router(name="owner")
PER_PAGE = 8
BROADCAST_DELAY = 0.06   # ~16 сообщений в секунду, с запасом от лимита Telegram
FLAGS = {"ai": ("g_ai", "ИИ (команда «ии»)"), "stt": ("g_stt", "Расшифровка голосовых"),
         "nsfw": ("g_nsfw", "Фильтр 18+"),
         "aimod": ("g_aimod", "ИИ-модерация"),
         "maint": ("maintenance", "Режим обслуживания")}

# что владелец ввёл «следующим сообщением»: owner_id -> {"kind": ..., "ts": ...}; живёт 5 минут
_pending: dict[int, dict] = {}
PENDING_TTL = 300


def _set_pending(oid: int, data: dict) -> None:
    _pending[oid] = {**data, "ts": time.time()}


class OwnerFilter(BaseFilter):
    async def __call__(self, event, owner_ids=frozenset()) -> bool:
        u = getattr(event, "from_user", None)
        return bool(u and u.id in owner_ids)


router.message.filter(OwnerFilter(), F.chat.type == "private")
router.callback_query.filter(OwnerFilter())


# ---------- чистые помощники (тестируются отдельно) ----------

def fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    return (f"{d} д " if d else "") + (f"{h} ч " if d or h else "") + f"{m} мин"


def page_bounds(total: int, page: int, per: int = PER_PAGE) -> tuple[int, int]:
    """(нормализованная страница, всего страниц)."""
    pages = max((total + per - 1) // per, 1)
    return min(max(page, 0), pages - 1), pages


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """Кнопка — (текст, данные) или (текст, данные, цвет): цвет primary | success | danger (Bot API 9.4)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text=b[0], callback_data=b[1], style=b[2] if len(b) > 2 else None) for b in row] for row in rows])


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def short(text: str, n: int = 28) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


HOME_KB = kb([
    [("📊 Статус", "own:status"), ("💬 Чаты", "own:chats:0")],
    [("👥 Пользователи", "own:u"), ("🚫 Блок-лист", "own:bans")],
    [("📣 Рассылка", "own:bc"), ("⚙️ Функции", "own:flags")],
    [("💾 Бэкап БД", "own:backup"), ("📜 Журнал", "own:log")],
    [("⚙️ Диагностика", "own:diag")],
    [("🔁 Перезагрузка", "own:ask:restart:0"), ("⏻ Выключить", "own:ask:shutdown:0")],
])
BACK = [("⬅️ В панель", "own:home")]


async def _retry(call):
    """Один повтор после «слишком часто» (flood control) — иначе остаток рассылки терялся бы молча."""
    try:
        return await call()
    except TelegramRetryAfter as e:
        await asyncio.sleep(min(e.retry_after, 30))
        return await call()


async def _log(db: Database, owner_id: int, action: str, detail: str) -> None:
    await db.log_owner(owner_id, action, detail, int(time.time()))


async def _status_text(db: Database, rt: Runtime) -> str:
    size = await db.size_bytes()
    yn = lambda v: "вкл" if v else "выкл"  # noqa: E731
    rows = [("Работает", fmt_uptime(time.time() - rt.started_at)), ("Пользователей", await db.count_users()),
            ("Чатов", f"{await db.count_chats(active_only=True)} из {await db.count_chats()}"),
            ("Блок-лист", f"{len(rt.banned_users)} польз. / {len(rt.banned_chats)} чатов"),
            ("База", f"{db.backend}, {size / 1024:.0f} КБ"),
            ("ИИ / STT / 18+", f"{yn(rt.flag('ai'))} / {yn(rt.flag('stt'))} / {yn(rt.flag('nsfw'))}"),
            ("ИИ-модерация", yn(rt.flag("aimod"))), ("Обслуживание", yn(rt.maintenance)),
            ("Версии", f"py {platform.python_version()}, aiogram {aiogram.__version__}")]
    return "📊 <b>Статус</b>\n" + kv_table(rows, key_width=14, value_width=24)


# ---------- вход ----------

@router.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("/owner", "/panel", "панель", "/start owner")))
async def open_panel(message: Message, webapp_url: str = "") -> None:
    _pending.pop(message.from_user.id, None)
    markup = HOME_KB
    if webapp_url:   # веб-панель: то же самое и больше, без многоуровневых кнопок
        from bot.handlers.webpanel import panel_button
        markup = InlineKeyboardMarkup(inline_keyboard=[[panel_button(webapp_url)], *HOME_KB.inline_keyboard])
    await message.answer("🛠 <b>Панель владельца</b>", reply_markup=markup)


_EMOJI_TEST_RE = re.compile(r"^тест эмодзи$", re.IGNORECASE)


@router.message(F.text.func(lambda t: bool(t) and _EMOJI_TEST_RE.match(t.strip()) is not None))
async def emoji_test(message: Message, bot) -> None:
    """Проверка премиум-эмодзи: четыре способа показать одно и то же. Видно, какой из них у вас рисуется как премиум."""
    from aiogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup
    from bot import emoji_inject, rich_ui
    emap = emoji_inject.load_map()
    cid = emap.get("🛡")
    if not cid:
        await message.answer("В карте эмодзи нет 🛡 — проверять нечем.")
        return
    await message.answer(f'1) обычное сообщение, тег в тексте: <tg-emoji emoji-id="{cid}">🛡</tg-emoji> должно быть премиум-иконкой')
    await message.answer("2) обычное сообщение, иконка на кнопке:",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[B(text="Кнопка", icon_custom_emoji_id=cid, callback_data="noop")]]))
    s = rich_ui.Screen("🛡 3) rich-сообщение: заголовок", ["4) абзац 🛡 и кнопка ниже:"], [[rich_ui.Btn("🛡 Кнопка", cb="noop")]])
    try:
        await bot.send_rich_message(chat_id=message.chat.id, rich_message=rich_ui.to_rich(s))
    except Exception as e:
        await message.answer(f"rich-сообщение не отправилось: {esc(e)}")
        return
    await message.answer("Какие из 1–4 показывают обычный 🛡 вместо премиум-иконки? Напишите номера.")


_DIAG_RE = re.compile(r"^диагностика(?:\s+(-?\d{5,}))?$", re.IGNORECASE)


async def _diag_text(bot, db: Database, rt: Runtime, ai, webapp_url: str, chat_id: int | None) -> str:
    parts = [await diagnose_global(db, rt, ai, webapp_url)]
    if chat_id is not None:
        ids = [chat_id]
    else:
        ids = [c["chat_id"] for c in await db.list_chats(0, 5, active_only=True)]
    for cid in ids:
        parts.append(await diagnose_chat(bot, db, cid))
    return "\n\n".join(parts)


@router.message(F.text.func(lambda t: bool(t) and _DIAG_RE.match(t.strip()) is not None))
async def diag_cmd(message: Message, bot, db: Database, rt: Runtime, ai=None, webapp_url: str = "") -> None:
    m = _DIAG_RE.match(message.text.strip())
    await message.answer(await _diag_text(bot, db, rt, ai, webapp_url, int(m.group(1)) if m.group(1) else None))


@router.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("метрики", "/metrics")))
async def metrics_cmd(message: Message, bot, metrics=None, db_path: str = "", uq=None) -> None:
    if metrics is None:
        await message.answer("⚠️ Метрики не подключены.")
        return
    waits = getattr(bot.session, "flood_waits", None)
    extra = {"Упирались в лимит Telegram": waits} if waits is not None else {}
    if uq is not None:
        extra["Очередь обновлений"] = (f"{uq.depth()} ждут · воркеров {uq.workers} (пик занятых {uq.peak_busy}) · "
                                       f"обработано {uq.processed} · ошибок {uq.failed} · дублей {uq.duplicates} · повторено после сбоя {uq.replayed}")
    await message.answer(metrics.render(db_path, extra))


@router.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("чеклист", "чек-лист")))
async def checklist_cmd(message: Message) -> None:
    await message.answer(CHECKLIST)


async def _edit(cb: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:  # «message is not modified»
        pass


def _private(cb: CallbackQuery) -> bool:
    return cb.message is not None and cb.message.chat.type == "private"


# ---------- кнопки ----------

@router.callback_query(F.data.startswith("own:"))
async def on_button(cb: CallbackQuery, bot, db: Database, rt: Runtime, owner_ids: frozenset = frozenset(),
                    ai=None, webapp_url: str = "") -> None:
    if not _private(cb):
        await cb.answer("Панель работает только в личке с ботом.", show_alert=True)
        return
    oid = cb.from_user.id
    parts = cb.data.split(":")
    op = parts[1]
    arg = parts[2:]
    _pending.pop(oid, None)  # любое нажатие отменяет ожидание текста
    await cb.answer()

    if op == "home":
        await _edit(cb, "🛠 <b>Панель владельца</b>", HOME_KB)
    elif op == "diag":
        await _edit(cb, await _diag_text(bot, db, rt, ai, webapp_url, None), kb([BACK]))
    elif op == "status":
        await _edit(cb, await _status_text(db, rt), kb([BACK]))
    elif op == "chats":
        await _chats(cb, db, rt, int(arg[0]))
    elif op == "c":
        await _chat_card(cb, db, rt, int(arg[0]))
    elif op == "mem":                      # участники чата: имя, @ник, id
        await _members(cb, db, int(arg[0]), int(arg[1]))
    elif op == "cm":                       # действие в чате: просим цель/текст
        chat_id, action = int(arg[0]), arg[1]
        _set_pending(oid, {"kind": "say" if action == "say" else "modact", "chat_id": chat_id, "action": action})
        what = "сообщение (текст или фото/видео с подписью — отправлю как есть)" if action == "say" else "один или несколько id и @ников (через пробел, запятую или с новой строки)"
        await _edit(cb, f"Отправьте {what} следующим сообщением.", kb([[("Отмена", f"own:c:{chat_id}")]]))
    elif op == "u":                        # все известные боту пользователи, постранично
        _pending.pop(oid, None)
        await _users(cb, db, int(arg[0]) if arg else 0)
    elif op == "us":                       # поиск
        _set_pending(oid, {"kind": "find_user"})
        await _edit(cb, "Отправьте id, @ник или часть имени.", kb([[("⬅️ К списку", "own:u:0")]]))
    elif op == "uc":
        await _user_card(cb, db, rt, int(arg[0]))
    elif op == "ub":                       # переключить бан в боте
        await _toggle_user_ban(cb, db, rt, oid, int(arg[0]), owner_ids)
    elif op == "bans":
        await _bans(cb, db)
    elif op == "unb":
        kind, id_ = arg[0], int(arg[1])
        await db.bot_unban(kind, id_)
        (rt.banned_users if kind == "user" else rt.banned_chats).discard(id_)
        rt.left_chats.discard(id_)
        await _log(db, oid, "разбан в боте", f"{kind} {id_}")
        await _bans(cb, db)
    elif op == "bc":
        _set_pending(oid, {"kind": "broadcast"})
        await _edit(cb, "Отправьте сообщение для рассылки: текст или фото/видео/GIF/файл с подписью. Форматирование и "
                        "премиум-эмодзи сохранятся. Уйдёт во все активные чаты после подтверждения.", kb([BACK]))
    elif op == "flags":
        await _flags(cb, rt)
    elif op == "fl":
        await _set_flag(cb, db, rt, oid, arg[0], int(arg[1]))
    elif op == "backup":
        await _backup(cb, bot, db, oid)
    elif op == "log":
        rows = await db.recent_owner_log(15)
        text = "📜 <b>Журнал действий</b>\n" + ("\n".join(
            f"{time.strftime('%d.%m %H:%M', time.localtime(r['ts']))} · {esc(r['action'])} · {esc(r['detail'])}"
            for r in rows) or "пусто")
        await _edit(cb, text, kb([BACK]))
    elif op == "ask":                      # подтверждение опасных действий
        await _ask(cb, arg[0], arg[1])
    elif op == "ok":
        await _confirmed(cb, bot, db, rt, oid, arg[0], arg[1], owner_ids)


async def _ask(cb: CallbackQuery, action: str, arg: str) -> None:
    texts = {
        "restart": "Перезагрузить бота?",
        "shutdown": "Выключить бота? Включить его снова можно только на сервере.",
        "leave": f"Выйти из чата {arg}?",
        "cban": f"Заблокировать чат {arg}? Бот выйдет из него и будет игнорировать.",
        "banall": f"Забанить пользователя {arg} во всех чатах, где у бота есть права, и в самом боте?",
        "bc": "Отправить рассылку во все активные чаты?",
    }
    back = f"own:c:{arg}" if action in ("leave", "cban") else "own:home"
    await _edit(cb, "⚠️ " + texts.get(action, "Подтвердите действие") + (
        _draft_preview(cb.from_user.id) if action == "bc" else ""),
        kb([[("✅ Да", f"own:ok:{action}:{arg}", "danger"), ("Отмена", back)]]))


def _draft_preview(oid: int) -> str:
    d = _drafts.get(oid)
    return f"\n\n<i>{esc(d['summary'])}</i>" if d else "\n\n(сообщения нет)"


# Черновик рассылки — ссылка на сообщение владельца в личке (чат + номер), а не голый текст: copy_message отправляет
# его как есть — с фото/видео/файлом, подписью, форматированием и премиум-эмодзи.
_drafts: dict[int, dict] = {}
MEDIA_RU = (("photo", "фото"), ("video", "видео"), ("animation", "GIF"), ("document", "файл"), ("audio", "аудио"),
            ("voice", "голосовое"), ("video_note", "кружок"), ("sticker", "стикер"), ("poll", "опрос"))


def _summary(m: Message) -> str:
    kind = next((ru for attr, ru in MEDIA_RU if getattr(m, attr, None)), None)
    text = (m.text or m.caption or "").strip()
    return (f"[{kind}] " if kind else "") + (short(text, 400) if text else ("" if kind else "(пусто)"))


async def _confirmed(cb, bot, db: Database, rt: Runtime, oid: int, action: str, arg: str, owner_ids) -> None:
    if action in ("restart", "shutdown"):
        await _log(db, oid, action, "из панели")
        await _edit(cb, "🔁 Перезагружаюсь…" if action == "restart" else "⏻ Выключаюсь…")
        rt.request_stop(restart=(action == "restart"))
    elif action == "leave":
        chat_id = int(arg)
        try:
            await bot.leave_chat(chat_id)
            await db.set_chat_active(chat_id, False)
            result = "Вышел из чата."
        except Exception as e:
            result = f"Не получилось: {esc(e)}"
        await _log(db, oid, "выход из чата", str(chat_id))
        await _edit(cb, result, kb([BACK]))
    elif action == "cban":
        chat_id = int(arg)
        await db.bot_ban("chat", chat_id, "владелец", int(time.time()))
        rt.banned_chats.add(chat_id)
        rt.left_chats.discard(chat_id)
        try:
            await bot.leave_chat(chat_id)
            rt.left_chats.add(chat_id)
            await db.set_chat_active(chat_id, False)
        except Exception:
            pass
        await _log(db, oid, "бан чата", str(chat_id))
        await _edit(cb, "Чат заблокирован.", kb([BACK]))
    elif action == "banall":
        await _ban_everywhere(cb, bot, db, rt, oid, int(arg), owner_ids)
    elif action == "bc":
        await _broadcast(cb, bot, db, rt, oid)


# ---------- разделы ----------

async def _chats(cb, db: Database, rt: Runtime, page: int) -> None:
    total = await db.count_chats()
    page, pages = page_bounds(total, page)
    rows = await db.list_chats(page * PER_PAGE, PER_PAGE)
    buttons = []
    for r in rows:
        mark = "🚫 " if r["chat_id"] in rt.banned_chats else ("" if r["active"] else "💤 ")
        buttons.append([(mark + short(r["title"] or str(r["chat_id"])), f"own:c:{r['chat_id']}")])
    nav = []
    if page > 0:
        nav.append(("◀️", f"own:chats:{page - 1}"))
    if page < pages - 1:
        nav.append(("▶️", f"own:chats:{page + 1}"))
    buttons += ([nav] if nav else []) + [BACK]
    await _edit(cb, f"💬 <b>Чаты</b> ({total}), стр. {page + 1}/{pages}\n💤 — бот вышел, 🚫 — заблокирован",
                kb(buttons))


async def _chat_card(cb, db: Database, rt: Runtime, chat_id: int) -> None:
    c = await db.get_chat(chat_id)
    if not c:
        await _edit(cb, "Чат не найден.", kb([[("⬅️ К чатам", "own:chats:0")]]))
        return
    banned = chat_id in rt.banned_chats
    text = (f"💬 <b>{esc(c['title'])}</b>\nID: <code>{chat_id}</code> · {esc(c['type'])}"
            + (f" · @{esc(c['username'])}" if c["username"] else "")
            + f"\nУчастников известно: {await db.member_count(chat_id)}"
            + f"\nБот в чате: {'да' if c['active'] else 'нет'}" + (" · 🚫 заблокирован" if banned else ""))
    await _edit(cb, text, kb([
        [("✉️ Написать", f"own:cm:{chat_id}:say"), ("👥 Участники", f"own:mem:{chat_id}:0")],
        [("🔨 Бан", f"own:cm:{chat_id}:ban"), ("🔓 Разбан", f"own:cm:{chat_id}:unban")],
        [("🔇 Мут 1ч", f"own:cm:{chat_id}:mute"), ("👢 Кик", f"own:cm:{chat_id}:kick")],
        [("🚪 Покинуть", f"own:ask:leave:{chat_id}"),
         (("♻️ Разблокировать" if banned else "🚫 Заблокировать"),
          (f"own:unb:chat:{chat_id}" if banned else f"own:ask:cban:{chat_id}"))],
        [("⬅️ К чатам", "own:chats:0")]]))


MEMBERS_PAGE = 25


async def _members(cb, db: Database, chat_id: int, page: int) -> None:
    """Кто в чате (известен боту): кликабельное имя, @ник, id и когда был в последний раз — свежие сверху."""
    members = sorted(await db.members_info(chat_id), key=lambda m: m["last_seen"] or 0, reverse=True)
    pages = max((len(members) + MEMBERS_PAGE - 1) // MEMBERS_PAGE, 1)
    page = max(0, min(page, pages - 1))
    now = int(time.time())
    title = (await db.get_chat(chat_id) or {}).get("title") or str(chat_id)
    lines = []
    for i, m in enumerate(members[page * MEMBERS_PAGE:(page + 1) * MEMBERS_PAGE], page * MEMBERS_PAGE + 1):
        uid = m["user_id"]
        days = (now - m["last_seen"]) // 86400 if m["last_seen"] else None
        seen = "сегодня" if days == 0 else (f"{days} дн. назад" if days is not None else "—")
        lines.append(f"{i}. {listed(uid, (await db.user_name(uid)) or f'id{uid}', 32)} · <code>{uid}</code> · {seen}")
    nav = []
    if page > 0:
        nav.append(("◀️", f"own:mem:{chat_id}:{page - 1}"))
    if page < pages - 1:
        nav.append(("▶️", f"own:mem:{chat_id}:{page + 1}"))
    text = (f"👥 <b>Участники · {esc(title)}</b> — {len(members)}" + (f" · стр. {page + 1}/{pages}" if pages > 1 else "")
            + "\n" + ("\n".join(lines) if lines else "Бот пока никого здесь не знает."))
    await _edit(cb, text, kb(([nav] if nav else []) + [[("⬅️ К чату", f"own:c:{chat_id}")]]))


USERS_PAGE = 10


async def _users(cb, db: Database, page: int) -> None:
    total = await db.count_users()
    pages = max((total + USERS_PAGE - 1) // USERS_PAGE, 1)
    page = max(0, min(page, pages - 1))
    users = await db.search_users("", USERS_PAGE, page * USERS_PAGE)
    rows = [[(short(f"{u['name'] or 'id' + str(u['user_id'])}" + (f" @{u['username']}" if u["username"] else "")
                    + f" · {u['user_id']}", 48), f"own:uc:{u['user_id']}")] for u in users]
    nav = []
    if page > 0:
        nav.append(("◀️", f"own:u:{page - 1}"))
    nav.append((f"{page + 1}/{pages}", "noop"))
    if page < pages - 1:
        nav.append(("▶️", f"own:u:{page + 1}"))
    await _edit(cb, f"👥 <b>Пользователи</b> — {total}",
                kb(rows + [nav, [("🔎 Поиск", "own:us")], BACK]))


async def _user_card(cb, db: Database, rt: Runtime, uid: int) -> None:
    c = await db.user_card(uid)
    if not c:
        await _edit(cb, "Пользователь не найден.", kb([[("⬅️ К списку", "own:u:0")]]))
        return
    banned = uid in rt.banned_users
    text = (f"👤 <b>{esc(c['name'])}</b>" + (f" @{esc(c['username'])}" if c["username"] else "")
            + f"\nID: <code>{uid}</code>\nЧатов: {c['chats']} · Сообщений: {c['messages']}"
            + ("\n🚫 заблокирован в боте" if banned else ""))
    await _edit(cb, text, kb([
        [("✅ Разбан в боте" if banned else "🚫 Бан в боте", f"own:ub:{uid}")],
        [("🔨 Бан везде", f"own:ask:banall:{uid}", "danger")], BACK]))


async def _toggle_user_ban(cb, db: Database, rt: Runtime, oid: int, uid: int, owner_ids) -> None:
    if uid in owner_ids:
        await cb.message.answer("⚠️ Владельца заблокировать нельзя.")
        return
    if uid in rt.banned_users:
        await db.bot_unban("user", uid)
        rt.banned_users.discard(uid)
        await _log(db, oid, "разбан в боте", f"user {uid}")
    else:
        await db.bot_ban("user", uid, "владелец", int(time.time()))
        rt.banned_users.add(uid)
        await _log(db, oid, "бан в боте", f"user {uid}")
    await _user_card(cb, db, rt, uid)


async def _bans(cb, db: Database) -> None:
    users, chats = await db.list_bot_bans("user"), await db.list_bot_bans("chat")
    rows = []
    for b in users[:10]:                                  # не голый id, а имя и @ник — видно, кого разблокируешь
        c = await db.user_card(b["id"]) or {}
        label = (c.get("name") or "user") + (f" @{c['username']}" if c.get("username") else "") + f" ({b['id']})"
        rows.append([(f"♻️ {short(label, 40)}", f"own:unb:user:{b['id']}")])
    rows += [[(f"♻️ чат {b['id']}", f"own:unb:chat:{b['id']}")] for b in chats[:10]]
    await _edit(cb, f"🚫 <b>Блок-лист</b>\nПользователей: {len(users)} · Чатов: {len(chats)}\n"
                    "Нажмите, чтобы разблокировать.", kb(rows + [BACK]))


async def _flags(cb, rt: Runtime) -> None:
    state = {"ai": rt.flag("ai"), "stt": rt.flag("stt"), "nsfw": rt.flag("nsfw"), "aimod": rt.flag("aimod"),
             "maint": rt.maintenance}
    rows = [[(f"{'✅' if state[k] else '❌'} {label}: {'вкл' if state[k] else 'выкл'}", f"own:fl:{k}:{0 if state[k] else 1}")]
            for k, (_, label) in FLAGS.items()]
    await _edit(cb, "⚙️ <b>Глобальные функции</b>\nДействуют сразу во всех чатах.", kb(rows + [BACK]))


async def _set_flag(cb, db: Database, rt: Runtime, oid: int, key: str, value: int) -> None:
    if key not in FLAGS:
        return
    await db.set_global(FLAGS[key][0], value)
    rt.apply_globals(await db.get_global())
    await _log(db, oid, "глобальный флаг", f"{key}={value}")
    await _flags(cb, rt)


async def _backup(cb, bot, db: Database, oid: int) -> None:
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, f"bot-backup-{time.strftime('%Y%m%d-%H%M%S')}.db")
        await db.backup_to(path)
        await bot.send_document(cb.message.chat.id, FSInputFile(path), caption="💾 Резервная копия базы")
    await _log(db, oid, "бэкап", "отправлен владельцу")


async def _ban_everywhere(cb, bot, db: Database, rt: Runtime, oid: int, uid: int, owner_ids) -> None:
    if uid in owner_ids:
        await _edit(cb, "Владельца банить нельзя.", kb([BACK]))
        return
    await db.bot_ban("user", uid, "владелец (везде)", int(time.time()))
    rt.banned_users.add(uid)
    chats = await db.list_chats(0, 10_000, active_only=True)
    ok = 0
    for c in chats:
        try:
            await _retry(lambda c=c: bot.ban_chat_member(c["chat_id"], uid))
            ok += 1
        except Exception:
            pass
        await asyncio.sleep(0.03)
    await _log(db, oid, "бан везде", f"user {uid}: {ok}/{len(chats)} чатов")
    await _edit(cb, f"🔨 Пользователь {uid} заблокирован в боте и забанен в {ok} из {len(chats)} чатов.",
                kb([BACK]))


async def _broadcast(cb, bot, db: Database, rt: Runtime, oid: int) -> None:
    draft = _drafts.pop(oid, None)
    if not draft:
        await _edit(cb, "Сообщения для рассылки нет.", kb([BACK]))
        return
    chats = [c for c in await db.list_chats(0, 10_000, active_only=True) if c["chat_id"] not in rt.banned_chats]
    ok = bad = 0
    for c in chats:
        try:
            await _retry(lambda c=c: bot.copy_message(c["chat_id"], from_chat_id=draft["chat"], message_id=draft["mid"]))
            ok += 1
        except Exception:
            bad += 1
        await asyncio.sleep(BROADCAST_DELAY)
    await _log(db, oid, "рассылка", f"{ok} из {len(chats)} чатов")
    await _edit(cb, f"📣 Рассылка: доставлено {ok}, не удалось {bad}.", kb([BACK]))


# ---------- ввод текста после кнопки ----------

def _has_pending(m: Message) -> bool:
    p = _pending.get(m.from_user.id) if m.from_user else None
    if p is not None and time.time() - p["ts"] > PENDING_TTL:
        _pending.pop(m.from_user.id, None)  # ожидание устарело — следующий текст не уйдёт в чат по ошибке
        return False
    return p is not None


@router.message(F.func(_has_pending))
async def on_pending_text(message: Message, bot, db: Database, rt: Runtime, owner_ids: frozenset = frozenset()) -> None:
    oid = message.from_user.id
    p = _pending.pop(oid)
    kind = p["kind"]
    text = (message.text or "").strip()
    if kind in ("find_user", "modact") and not text:
        _set_pending(oid, p)                                  # ждём дальше: здесь нужен текст (id или @ник)
        await message.answer("⚠️ Пришлите текстом: id или @ник.")
        return
    if kind == "find_user":
        users = await db.search_users(text)
        if not users:
            await message.answer("Никого не нашёл.", reply_markup=kb([[("⬅️ К списку", "own:u:0")]]))
            return
        rows = [[(short(f"{u['name']}" + (f" @{u['username']}" if u["username"] else "") + f" ({u['user_id']})", 48),
                  f"own:uc:{u['user_id']}")] for u in users]
        await message.answer("Нашёл:", reply_markup=kb(rows + [[("⬅️ К списку", "own:u:0")]]))
    elif kind == "say":
        try:   # копия сообщения как есть: фото/видео, подпись, форматирование, премиум-эмодзи
            await bot.copy_message(p["chat_id"], from_chat_id=message.chat.id, message_id=message.message_id)
            await _log(db, oid, "сообщение в чат", f"{p['chat_id']}: {short(_summary(message), 60)}")
            await message.answer("✅ Отправлено.", reply_markup=kb([[("⬅️ К чату", f"own:c:{p['chat_id']}")]]))
        except Exception as e:
            await message.answer(f"❌ Не получилось: {esc(e)}")
    elif kind == "modact":
        await _remote_mod(message, bot, db, oid, p, text, owner_ids)
    elif kind == "broadcast":
        _drafts[oid] = {"chat": message.chat.id, "mid": message.message_id, "summary": _summary(message)}
        await message.answer("👇 Так рассылка будет выглядеть в чатах:")
        try:
            await bot.copy_message(message.chat.id, from_chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass
        await message.answer("Отправить во все активные чаты?",
                             reply_markup=kb([[("📣 Отправить во все чаты", "own:ask:bc:0")], BACK]))


async def _remote_mod(message: Message, bot, db: Database, oid: int, p: dict, text: str, owner_ids=frozenset()) -> None:
    """Бан/разбан/мут/кик одного или нескольких людей (id и @ники вперемешку). Неизвестный @ник при бане
    запоминается и исполняется, когда бот его увидит."""
    from bot import bulk
    chat_id, action = p["chat_id"], p["action"]
    try:
        targets, invalid = bulk.parse_targets(text)
    except bulk.BulkError as e:
        await message.answer(esc(e))
        return
    if not targets:
        await message.answer("❌ Не нашёл ни одного id или @ника. Пришлите числовые id и @ники, можно несколько.")
        return
    name = {"ban": "бан", "unban": "разбан", "mute": "мут", "kick": "кик"}[action]
    protected = frozenset(owner_ids) | {(await bot.me()).id}
    res = await bulk.bulk_action(bot, db, chat_id, oid, targets, name, "владелец", None, int(time.time()),
                                 owner=True, protected=protected)
    icon = {"ok": "✅", "pending": "🕐", "skipped": "⚠️", "failed": "❌"}
    lines = [f"{icon[o.status]} {esc(o.name or o.target)}: {esc(o.detail)}" for o in res]
    if invalid:
        lines.append("Не распознал: " + esc(", ".join(invalid)))
    done = sum(1 for o in res if o.status == "ok")
    await _log(db, oid, f"{name} в чате", f"{chat_id}: " + ", ".join(
        f"{o.user_id or o.target}={o.status}" for o in res)[:300])
    head = f"<b>{name.capitalize()}</b>: выполнено {done} из {len(res)}\n"
    await message.answer(head + "\n".join(lines)[:3800], reply_markup=kb([[("⬅️ К чату", f"own:c:{chat_id}")]]))
