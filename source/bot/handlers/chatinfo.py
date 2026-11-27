"""Оформление чата: правила, приветствие, открыть/закрыть чат, сводка и списки участников."""
import asyncio
import html
import json
import logging
import re
import time

from aiogram import F, Router
from aiogram.types import ChatPermissions, Message

from bot import rules_text, ux
from bot import mod_service as ms
from bot.db import Database
from bot.family import Family
from bot.fmt import kv_table, pre_table, quote
from bot.ranks import need_rank
from bot import members as members_mod
from bot.targets import mention, ping, listed

router = Router(name="chatinfo")
MAX_TEXT = 700      # приветствие: после экранирования HTML текст может вырасти до 5 раз — в лимит 4096 влезет
MAX_RULES = 1500    # правила: дополнительно проверяется длина после экранирования
DEFAULT_WELCOME = "👋 {name}, добро пожаловать в «{chat}»!\n\n{rules}"
LIST_COOLDOWN = 20
RALLY_COOLDOWN = 300     # «общий сбор» не чаще раза в 5 минут на чат: иначе это спам уведомлениями
RALLY_MAX = 50           # сколько человек зовём за раз (самые недавно активные)
SYNC_COOLDOWN = 600      # «проверить участников» — не чаще раза в 10 минут на чат
RALLY_CHUNK = 5          # упоминаний в одном сообщении: аккуратно, небольшими порциями
RALLY_PAUSE = 0.6        # пауза между сообщениями, секунд: 50 человек ≈ 6 секунд; при лимите Telegram сессия подождёт сама
RALLY_DAILY = 5          # сколько общих сборов в сутки на чат
RALLY_TEXT = 300
_last: dict[tuple, float] = {}

_PATTERNS = [
    ("set_rules", r"^\+правила(?:\s+(.+))?$"), ("del_rules", r"^-правила$"), ("rules", r"^правила$"),
    ("set_welcome", r"^\+приветствие\s+(.+)$"), ("del_welcome", r"^-приветствие$"), ("welcome", r"^приветствие$"),
    ("open", r"^\+чат$"), ("close", r"^-чат$"), ("info", r"^чат инфо$"),
    ("rally", r"^(?:общий сбор|калл|call)(?:\s+(.+))?$"),
    ("olds", r"^олды$"), ("newbies", r"^новички$"), ("online", r"^кто онлайн$"),
    ("sync", r"^(?:проверить|обновить) участников$"),
]
_COMPILED = [(k, re.compile(p, re.IGNORECASE | re.DOTALL)) for k, p in _PATTERNS]


def parse(text: str | None):
    t = (text or "").strip()
    for kind, rx in _COMPILED:
        m = rx.match(t)
        if m:
            return kind, (m.group(1).strip() if m.groups() and m.group(1) else None)
    return None


def render_rules(rules: str | None) -> str:
    """Правила для приветствия: заголовок и сами правила в сворачиваемой цитате (длинный список не растягивает сообщение,
    открывается по нажатию). Хранимые с оформлением (JSON) — как HTML со всеми стилями и премиум-эмодзи, старые — как текст;
    пусто — пустая строка."""
    if not rules:
        return ""
    got = rules_text.load(rules)
    if got and got[1] is not None:
        body = rules_text.to_html(rules)
        if "<blockquote" in body:                                # вложенные цитаты Telegram не принимает — оставляем как есть
            return f"📜 <b>Правила</b>\n{body}"
        return f"📜 <b>Правила</b>\n{quote(body, expandable=True)}"
    return f"📜 <b>Правила</b>\n{quote(html.escape(got[0] if got else rules), expandable=True)}"


def render_welcome(template: str, user_id: int, name: str, chat_title: str, rules: str | None = None) -> str:
    """Текст пользователя экранируется целиком, {name}, {chat} и {rules} подставляются после — безопасно для HTML."""
    out = html.escape(template)
    out = out.replace("{name}", mention(user_id, name)).replace("{chat}", html.escape(chat_title or "чат"))
    out = out.replace("{rules}", render_rules(rules))
    out = re.sub(r"\n{3,}", "\n\n", out)                       # лишние пустые строки
    out = re.sub(r"(?<!\n)\n(📜 <b>Правила</b>)", r"\n\n\1", out)   # между приветствием и правилами — одна пустая строка
    if len(out) > 3900:                                         # слишком длинно для одного сообщения — отправляем отсылку
        out = html.escape(template).replace("{name}", mention(user_id, name)).replace(
            "{chat}", html.escape(chat_title or "чат")).replace("{rules}", "📜 Правила — команда <code>правила</code>")
    return out.strip()


async def send_welcome(bot, db: Database, chat_id: int, user_id: int, name: str | None = None) -> None:
    if not (await db.get_settings(chat_id))["welcome_on"]:
        return
    tpl = await db.get_text(chat_id, "welcome") or DEFAULT_WELCOME
    name = name or (await db.user_name(user_id)) or f"id{user_id}"
    chat = await db.get_chat(chat_id)
    rules = await db.get_text(chat_id, "rules")
    try:
        await bot.send_message(chat_id, render_welcome(tpl, user_id, name, (chat or {}).get("title") or "чат", rules),
                               disable_web_page_preview=True)
    except Exception:
        pass


@router.message(F.text.func(lambda t: parse(t) is not None))
async def chatinfo_cmd(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup"):
        return
    kind, arg = parse(message.text)
    chat, me = message.chat.id, message.from_user.id
    now = int(time.time())

    if kind == "rules":
        stored = await db.get_text(chat, "rules")
        got = rules_text.load(stored)
        if got is None:
            await message.reply("📜 Правила пока не заданы.\nАдмины: <code>+правила текст</code> "
                                "(или ответьте <code>+правила</code> на готовое сообщение)")
        elif got[1] is None:                                     # старые правила без оформления
            await message.reply(render_rules(stored))
        else:                                                    # точная копия: текст и entities как написал админ
            try:
                await message.answer(got[0], entities=got[1], parse_mode=None, disable_web_page_preview=True)
            except Exception as e:                               # Telegram не принял entities — шлём то же через HTML
                logging.warning("правила: отправка с entities не удалась (%s) — шлю через HTML", e)
                await message.answer(rules_text.to_html(stored), disable_web_page_preview=True)
        return
    if kind == "welcome":
        tpl = await db.get_text(chat, "welcome")
        await message.reply("👋 <b>Приветствие</b>\n" + quote(html.escape(tpl)) if tpl else
                            "👋 Используется стандартное приветствие.\nСвоё: <code>+приветствие Привет, {name}!</code>")
        return
    if kind == "rally":
        if arg and len(arg) >= 2 and arg[0] + arg[-1] in ('""', "«»", "“”", "„“"):
            arg = arg[1:-1].strip() or None                      # калл "причина" — кавычки не нужны в тексте
        await _rally(message, bot, db, arg, now)
        return
    if kind == "sync":
        need = need_rank(await db.get_access(chat), "неактивные")
        if await ms.effective_rank(bot, db, chat, me) < need:
            return
        if time.time() - _last.get((chat, "sync"), 0) < SYNC_COOLDOWN:
            await ux.tell(message, "⚠️ Список участников недавно проверяли — попробуйте позже.")
            return
        _last[(chat, "sync")] = time.time()
        await message.reply("🔄 Сверяю список участников с Telegram…")
        checked, removed = await members_mod.sync_chat(bot, db, chat)
        await message.reply(f"✅ Проверено {checked}. Убрано вышедших: {removed}. "
                            f"Сейчас в списке: {await db.member_count(chat)}.")
        return
    if kind in ("olds", "newbies", "online", "info"):
        key = (chat, kind)
        if time.time() - _last.get(key, 0) < LIST_COOLDOWN:
            return  # списки с упоминаниями не чаще раза в 20 секунд на чат
        _last[key] = time.time()
    if kind == "olds":
        rows = await db.oldest_members(chat)
        table = pre_table([(str(i), listed(r["user_id"], (await db.user_name(r["user_id"])) or f"id{r['user_id']}", 28),
                            time.strftime("%d.%m.%Y", time.localtime(r["first_seen"]))) for i, r in enumerate(rows, 1)],
                          header=("#", "Старожил", "С"), align="llr", maxw=(3, 20, 10)) if rows else "Пока никого."
        await message.reply(f"🕰 <b>Старожилы</b>\n{table}")
        return
    if kind == "newbies":
        rows = await db.newest_members(chat)
        table = pre_table([(str(i), listed(r["user_id"], (await db.user_name(r["user_id"])) or f"id{r['user_id']}", 28),
                            time.strftime("%d.%m %H:%M", time.localtime(r["t"]))) for i, r in enumerate(rows, 1)],
                          header=("#", "Новичок", "Пришёл"), align="llr", maxw=(3, 18, 11)) if rows else "Пока никого."
        await message.reply(f"🌱 <b>Новички</b>\n{table}")
        return
    if kind == "online":
        ids = await db.online_members(chat, now)
        body = ", ".join([listed(u, (await db.user_name(u)) or "") for u in ids[:40]]) or "никого не видно"
        await message.reply(f"🟢 <b>Были активны за 10 минут</b> · {len(ids)}\n{quote(body, expandable=len(ids) > 8)}",
                            disable_web_page_preview=True)
        return
    if kind == "info":
        total, _ = await db.count_by_user(chat, None)
        day, _ = await db.count_by_user(chat, now - 86400)
        mutes, bans = len(await db.list_state(chat, "mute", now)), len(await db.list_state(chat, "ban", now))
        await message.reply("ℹ️ <b>О чате</b>\n" + kv_table([
            ("Участников", await db.member_count(chat)), ("Сообщений", f"{total} (за сутки {day})"),
            ("Браков", await Family(db).count_marriages(chat)), ("Мутов / банов", f"{mutes} / {bans}"),
            ("Модераторов", len(await db.list_ranks(chat)))], key_width=14, value_width=22))
        return

    # дальше — настройка чата: нужен ранг
    need = need_rank(await db.get_access(chat), "настройки чата")
    if await ms.effective_rank(bot, db, chat, me) < need:
        await ux.tell(message, f"⚠️ Это доступно с ранга {need}.")
        return
    if kind == "set_rules":
        src = rules_text.extract(message, ms.real_reply(message))
        if src is None:
            await ux.tell(message, "⚠️ Напишите правила после команды (можно с оформлением и эмодзи) "
                                   "или ответьте <code>+правила</code> на готовое сообщение.")
            return
        text, entities = src
        if rules_text.too_long(text):
            await ux.tell(message, f"❌ Слишком длинно: максимум {rules_text.MAX_LEN} символов.")
            return
        await db.set_text(chat, "rules", rules_text.dump(text, entities))
        premium, styles = rules_text.summary(entities)
        await message.reply(f"✅ Правила сохранены: {len(text)} симв. · премиум-эмодзи: {premium} · стилей: {styles}\n"
                            "<i>Покажу их в таком же виде.</i>")
        return
    if kind in ("set_rules", "set_welcome"):
        limit = MAX_RULES if kind == "set_rules" else MAX_TEXT
        if len(arg) > limit or len(html.escape(arg)) > 3300:
            await ux.tell(message, f"❌ Слишком длинно: максимум {limit} символов.")
            return
        await db.set_text(chat, "rules" if kind == "set_rules" else "welcome", arg)
        await message.reply("✅ Правила сохранены." if kind == "set_rules" else
                            "✅ Приветствие сохранено\n" + quote("Подстановки: {name} — имя, {chat} — чат, {rules} — правила"))
    elif kind in ("del_rules", "del_welcome"):
        await db.set_text(chat, "rules" if kind == "del_rules" else "welcome", None)
        await message.reply("🗑 Правила удалены." if kind == "del_rules" else "🗑 Приветствие удалено — будет стандартное.")
    elif kind in ("open", "close"):
        try:
            if kind == "close":
                if await db.get_text(chat, "perms_backup") is None:  # запоминаем настроенные админами права
                    try:
                        cur = (await bot.get_chat(chat)).permissions
                        if cur is not None:
                            await db.set_text(chat, "perms_backup", json.dumps(cur.model_dump(exclude_none=True)))
                    except Exception:
                        pass
                perms = ChatPermissions(can_send_messages=False)
            else:
                saved = await db.get_text(chat, "perms_backup")
                perms = ChatPermissions(**json.loads(saved)) if saved else ms._FULL
                if saved and not perms.can_send_messages:
                    perms = ChatPermissions(**{**json.loads(saved), "can_send_messages": True})
            await bot.set_chat_permissions(chat, permissions=perms)
            if kind == "open":
                await db.set_text(chat, "perms_backup", None)
        except Exception as e:
            await ux.tell(message, f"❌ Не получилось: {html.escape(str(e))}")
            return
        await message.reply("🔓 Чат открыт для всех." if kind == "open" else "🔒 Чат закрыт: пишут только админы.")


def rally_chunks(mentions: list[str], size: int = RALLY_CHUNK) -> list[str]:
    return [" ".join(mentions[i:i + size]) for i in range(0, len(mentions), size)]


async def _rally(message: Message, bot, db: Database, text: str | None, now: int) -> None:
    """«общий сбор [текст]» — позвать всех известных боту участников чата. Только с нужным рангом (по умолчанию 2),
    не чаще раза в 5 минут; без прав бот молчит (иначе обычная фраза «общий сбор» в разговоре вызывала бы ответы)."""
    chat, me = message.chat.id, message.from_user.id
    if not (await db.get_settings(chat))["rally_on"]:
        return                                               # выключено в настройках → «Команды»
    need = need_rank(await db.get_access(chat), "общий сбор")
    if await ms.effective_rank(bot, db, chat, me) < need:
        return
    wait = RALLY_COOLDOWN - (time.time() - _last.get((chat, "rally"), 0))
    if wait > 0:
        await message.reply(f"📣 Общий сбор уже объявляли. Следующий — через {int(wait) // 60 + 1} мин.")
        return
    members = sorted((m for m in await db.members_info(chat) if m["user_id"] != me),
                     key=lambda m: m["last_seen"] or 0, reverse=True)
    if not members:
        await ux.tell(message, "⚠️ Я пока никого здесь не знаю: звать некого 🤷")
        return
    if not await db.take_quota(chat, "rally", now, RALLY_DAILY):
        await message.reply(f"📣 Лимит общих сборов на сегодня исчерпан ({RALLY_DAILY} в сутки на чат).")
        return
    _last[(chat, "rally")] = time.time()
    present = []                                             # зовём только тех, кто ещё в чате: вышедших убираем из списка
    for m in members:
        if len(present) >= RALLY_MAX:
            break
        if await members_mod.check(bot, db, chat, m["user_id"]) is not False:
            present.append(m)
    total = sum(1 for m in await db.members_info(chat) if m["user_id"] != me)   # уже без вышедших
    members = present
    if not members:
        await ux.tell(message, "⚠️ Все, кого я знал, уже вышли из чата: звать некого 🤷")
        return
    mentions = [ping(m["user_id"], (await db.user_name(m["user_id"])) or "участник") for m in members]   # @ник будит всегда
    head = f"📣 <b>Общий сбор!</b> {mention(me, message.from_user.full_name)}"
    head += f": {html.escape(text[:RALLY_TEXT])}" if text else " зовёт всех"
    await message.answer(head, disable_web_page_preview=True)
    for part in rally_chunks(mentions):                      # небольшими порциями, с паузой — а не всех одним сообщением
        await asyncio.sleep(RALLY_PAUSE)
        await message.answer("👥 " + part, disable_web_page_preview=True)
    if total > RALLY_MAX:
        await asyncio.sleep(RALLY_PAUSE)
        await message.answer(f"<i>Позвал {RALLY_MAX} самых активных из {total}: за один сбор больше не зову.</i>")
