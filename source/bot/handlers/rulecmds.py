"""Команды правил чата: триггеры, доверенные (белый список), блок стикеров, FAQ, повторяющиеся сообщения,
ночной режим, фейс-контроль, сроки по умолчанию, сетка чатов и глобальный бан.

Каждая команда проверяет ранг по «доступу команд» (ключи — в bot.ranks.DEFAULT_ACCESS)."""
from __future__ import annotations

import html
import re
import time

from aiogram import F, Router
from aiogram.types import Message

from bot import mod_service as ms
from bot import rules, ux
from bot.db import Database
from bot.middlewares.rules import invalidate
from bot.parsing import _parse_span
from bot.ranks import need_rank
from bot.targets import listed, resolve_user
from bot.toggles import Enabled

router = Router(name="rulecmds")
router.message.filter(Enabled("mod_on"))

_T = r"(@\w+|\d{5,})"
_PATTERNS = [
    ("trig_add", r"^\+триггер\s+(.+)$", "триггеры"),
    ("trig_del", r"^-триггер\s+(\S+)$", "триггеры"),
    ("trig_list", r"^(?:триггеры|триги)$", "триггеры"),
    ("trust_add", r"^\+(?:доверять|вайтлист|wl)(?:\s+" + _T + ")?$", "белый список"),
    ("trust_del", r"^-(?:доверять|вайтлист|wl)(?:\s+" + _T + ")?$", "белый список"),
    ("trust_list", r"^(?:доверенные|белый список)$", "белый список"),
    ("stk_add", r"^\+блок стикер(?:\s+(один))?$", "блок стикеров"),
    ("stk_del", r"^-блок стикер(?:\s+(один))?$", "блок стикеров"),
    ("stk_list", r"^блок стикеры$", "блок стикеров"),
    ("faq_add", r"^\+faq\s+(.+)$", "faq"),
    ("faq_del", r"^-faq\s+(\d{1,6})$", "faq"),
    ("faq_list", r"^faq$", "faq"),
    ("per_add", r"^\+повтор\s+(.+)$", "повторы"),
    ("per_del", r"^-повтор\s+(\d{1,6})$", "повторы"),
    ("per_list", r"^повторы$", "повторы"),
    ("night", r"^ночной режим(?:\s+(.+))?$", "настройки чата"),
    ("fc", r"^фейс-?контроль(?:\s+(.+))?$", "фейс-контроль"),
    ("def_mute", r"^мут период(?:\s+(.+))?$", "настройки чата"),
    ("def_ban", r"^бан период(?:\s+(.+))?$", "настройки чата"),
    ("warn_ban", r"^варны чс(?:\s+(.+))?$", "настройки чата"),
    ("warn_ttl", r"^варны период(?:\s+(.+))?$", "настройки чата"),
    ("rank_log", r"^(?:модер лог|лог дк|лог рангов)$", "история"),
    ("grid_add", r"^сетка\s*\+$", "сетка"),
    ("grid_del", r"^сетка\s*-$", "сетка"),
    ("grid_list", r"^сетка$", "сетка"),
    ("gban", r"^глобан(?:\s+" + _T + ")?$", "сетка"),
    ("gunban", r"^глоразбан(?:\s+" + _T + ")?$", "сетка"),
]
_COMPILED = [(k, re.compile(p, re.IGNORECASE | re.DOTALL), need) for k, p, need in _PATTERNS]


def parse(text: str | None):
    t = (text or "").strip()
    for kind, rx, need in _COMPILED:
        m = rx.match(t)
        if m:
            return kind, (m.group(1) if m.groups() else None), need
    return None


def _span(arg: str | None):
    """«2ч», «на неделю», «навсегда» -> ('span', timedelta) | ('forever', None) | None."""
    if not arg:
        return None
    toks = arg.lower().split()
    res = _parse_span(toks)
    return res if res and res[0] in ("span", "forever") else None


def _dur(secs: int) -> str:
    if not secs:
        return "навсегда"
    return f"{secs // 86400} дн." if secs % 86400 == 0 else f"{secs // 3600} ч." if secs % 3600 == 0 else f"{max(secs // 60, 1)} мин."


@router.message(F.text.func(lambda t: parse(t) is not None))
async def on_rulecmd(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    kind, arg, key = parse(message.text)
    chat, me, now = message.chat.id, message.from_user.id, int(time.time())
    reply = ms.real_reply(message)
    rank = await ms.effective_rank(bot, db, chat, me)
    need = need_rank(await db.get_access(chat), key)
    if kind in ("night", "fc") and not arg:
        need = 0                                          # посмотреть состояние может любой
    if rank < need:
        await ux.tell(message, f"⚠️ Это доступно с ранга {need}.")
        return

    # ---- триггеры ----
    if kind == "trig_add":
        try:
            event, action, secs, reason = rules.parse_trigger(arg)
        except rules.TriggerError as e:
            await ux.tell(message, f"⚠️ {html.escape(str(e))}")
            return
        items = await db.list_triggers(chat)
        if len(items) >= rules.MAX_TRIGGERS or sum(1 for t in items if t["event"] == event) >= rules.MAX_TRIGGERS_PER_EVENT:
            await ux.tell(message, "⚠️ Слишком много триггеров (до 3 на событие, до 40 в чате).")
            return
        tid = await db.add_trigger(chat, event, action, secs, reason, me, now)
        invalidate(chat)
        await message.reply("✅ Триггер " + html.escape(rules.describe_trigger(
            {"id": tid, "event": event, "action": action, "secs": secs, "reason": reason})))
    elif kind == "trig_del":
        key_ = arg.lower()
        ev = rules.normalize_event(key_)
        n = await db.del_trigger(chat, key_ if key_.isdigit() else (ev or key_))
        invalidate(chat)
        await message.reply("🗑 Удалено триггеров: %d" % n if n else "❌ Такого триггера нет.")
    elif kind == "trig_list":
        items = await db.list_triggers(chat)
        body = "\n".join(html.escape(rules.describe_trigger(t)) for t in items) or "Пока нет."
        await message.reply("🎯 <b>Триггеры</b>\n" + body + "\n\n<i>Добавить: </i><code>+триггер капс варн</code> · "
                            "<code>+триггер ссылка мут 1ч \"реклама\"</code>\n<i>События: " + ", ".join(rules.EVENTS)
                            + "</i>\n<i>Удалить: </i><code>-триггер 3</code> или <code>-триггер капс</code>")

    # ---- доверенные ----
    elif kind in ("trust_add", "trust_del"):
        target = await resolve_user(db, arg, reply)
        if target is None:
            await ux.tell(message, "⚠️ Ответьте командой на сообщение или укажите @ник / id.")
            return
        uid, name = target
        if kind == "trust_add":
            ok = await db.add_trusted(chat, uid, me, now)
            await message.reply(f"🤝 {listed(uid, name)} теперь доверенный: антиспам и правила его не трогают." if ok
                                else "ℹ️ Он уже в белом списке.")
        else:
            ok = await db.remove_trusted(chat, uid)
            await message.reply("✅ Убран из белого списка." if ok else "ℹ️ Его там не было.")
        invalidate(chat)
    elif kind == "trust_list":
        ids = await db.list_trusted(chat)
        body = ", ".join(str(listed(u, (await db.user_name(u)) or f"id{u}")) for u in ids[:60]) or "никого"
        await message.reply(f"🤝 <b>Белый список</b> · {len(ids)}\n{body}", disable_web_page_preview=True)

    # ---- стикеры ----
    elif kind in ("stk_add", "stk_del"):
        st = reply.sticker if reply is not None else None
        if st is None:
            await ux.tell(message, "⚠️ Ответьте командой на стикер. Блокируется весь набор, "
                                   "или один стикер: <code>+блок стикер один</code>.")
            return
        one = arg == "один" or not st.set_name
        k, v = ("sticker", st.file_unique_id) if one else ("set", st.set_name)
        if kind == "stk_add":
            await db.block_sticker(chat, k, v)
            await message.reply("🚫 Стикер заблокирован." if one else f"🚫 Набор «{html.escape(st.set_name)}» заблокирован.")
        else:
            ok = await db.unblock_sticker(chat, k, v)
            await message.reply("✅ Разблокировано." if ok else "ℹ️ Он не был заблокирован.")
        invalidate(chat)
    elif kind == "stk_list":
        items = await db.blocked_stickers(chat)
        sets = sorted(v for k, v in items if k == "set")
        await message.reply(f"🚫 <b>Заблокировано стикеров</b>: {sum(1 for k, _ in items if k == 'sticker')}, наборов: {len(sets)}"
                            + ("\n" + ", ".join(html.escape(s) for s in sets[:30]) if sets else ""))

    # ---- FAQ ----
    elif kind == "faq_add":
        try:
            kw, ans = rules.parse_faq(arg)
        except rules.TriggerError as e:
            await ux.tell(message, f"⚠️ {html.escape(str(e))}")
            return
        if len(ans) > 1500 or len(await db.list_faq(chat)) >= 60:
            await ux.tell(message, "⚠️ Ответ слишком длинный (до 1500 символов) или FAQ переполнен (до 60).")
            return
        fid = await db.add_faq(chat, kw, ans, me, now)
        invalidate(chat)
        await message.reply(f"✅ FAQ #{fid}: на «{html.escape(kw)}» отвечу сам. Кнопка — строкой "
                            "<code>кнопка: Текст | https://…</code>")
    elif kind == "faq_del":
        ok = await db.del_faq(chat, int(arg))
        invalidate(chat)
        await message.reply("🗑 Удалено." if ok else "❌ Такого номера нет.")
    elif kind == "faq_list":
        items = await db.list_faq(chat)
        body = "\n".join(f"#{i['id']} «{html.escape(i['keyword'])}» → {html.escape(i['answer'][:50])}" for i in items) or "Пока пусто."
        await message.reply("💬 <b>FAQ</b>\n" + body + "\n<i>Добавить: </i><code>+faq где правила = смотри /правила</code>")

    # ---- повторы ----
    elif kind == "per_add":
        try:
            secs, text = rules.parse_periodic(arg)
        except rules.TriggerError as e:
            await ux.tell(message, f"⚠️ {html.escape(str(e))}")
            return
        if len(await db.list_periodic(chat)) >= rules.MAX_PERIODIC or len(text) > 1500:
            await ux.tell(message, "⚠️ Слишком много повторов (до 20) или текст длиннее 1500 символов.")
            return
        pid = await db.add_periodic(chat, secs, text, me, now)
        await message.reply(f"🔁 Повтор #{pid}: каждые {_dur(secs)}.")
    elif kind == "per_del":
        ok = await db.del_periodic(chat, int(arg))
        await message.reply("🗑 Удалено." if ok else "❌ Такого номера нет.")
    elif kind == "per_list":
        items = await db.list_periodic(chat)
        body = "\n".join(f"#{i['id']} каждые {_dur(i['every'])}: {html.escape(i['text'][:50])}" for i in items) or "Пока пусто."
        await message.reply("🔁 <b>Повторяющиеся сообщения</b>\n" + body + "\n<i>Добавить: </i><code>+повтор 6ч текст</code>")

    # ---- ночной режим ----
    elif kind == "night":
        s = await db.get_settings(chat)
        a = (arg or "").strip().lower()
        if not a:
            state = f"включён: {s['night_from']}:00–{s['night_to']}:00" if s["night_on"] else "выключен"
            await message.reply(f"🌙 Ночной режим {state}.\n<i>Включить: </i><code>ночной режим 23-7</code> · "
                                "<i>выключить: </i><code>ночной режим выкл</code>\n"
                                f"<i>Часовой пояс чата: {html.escape(s['tz'])}</i>")
        elif a in ("выкл", "выключить", "off", "нет"):
            await db.set_setting(chat, "night_on", 0, me)
            await message.reply("🌙 Ночной режим выключен. Если чат сейчас закрыт — откроется в течение минуты.")
        else:
            win = rules.parse_night(a)
            if win is None:
                await ux.tell(message, "⚠️ Формат: <code>ночной режим 23-7</code> (часы, 0–23).")
                return
            await db.set_setting(chat, "night_from", win[0], me)
            await db.set_setting(chat, "night_to", win[1], me)
            await db.set_setting(chat, "night_on", 1, me)
            await message.reply(f"🌙 Ночной режим: с {win[0]}:00 до {win[1]}:00 писать могут только админы.")

    # ---- фейс-контроль ----
    elif kind == "fc":
        a = (arg or "").strip().lower()
        s = await db.get_settings(chat)
        if a in ("вкл", "выкл"):
            await db.set_setting(chat, "fc_on", 1 if a == "вкл" else 0, me)
            await message.reply("🕵 Фейс-контроль " + ("включён" if a == "вкл" else "выключен") +
                                ". Критерии — в «Настройки → Фейс-контроль».")
        else:
            crit = [n for k, n in (("fc_photo", "нужно фото"), ("fc_username", "нужен @username"),
                                   ("fc_premium", "нужен Premium")) if s[k]]
            if s["fc_age"]:
                crit.append(f"возраст аккаунта от ~{s['fc_age']} дн.")
            await message.reply(f"🕵 Фейс-контроль: {'включён' if s['fc_on'] else 'выключен'}\n"
                                f"Критерии: {', '.join(crit) or 'не заданы'}\nПровал → {s['fc_action']}\n"
                                "<i>Включить: </i><code>фейсконтроль вкл</code><i>, критерии — в настройках.</i>")

    # ---- сроки по умолчанию ----
    elif kind in ("def_mute", "def_ban", "warn_ban", "warn_ttl"):
        await _defaults(message, db, kind, arg, chat, me)

    elif kind == "rank_log":
        rows = await db.list_log_actions(chat, ("ранг", "дк"), 20)
        if not rows:
            await message.reply("📜 Журнал рангов и доступа пуст.")
            return
        lines = []
        for r in rows:
            who = (await db.user_name(r["actor_id"])) or f"id{r['actor_id']}"
            tgt = (await db.user_name(r["target_id"])) or f"id{r['target_id']}" if r["target_id"] else ""
            when = time.strftime("%d.%m %H:%M", time.localtime(r["ts"]))
            what = f"ранг {html.escape(tgt)}: {html.escape(r['reason'])}" if r["action"] == "ранг" else f"доступ: {html.escape(r['reason'])}"
            lines.append(f"{when} · {html.escape(who)} · {what}")
        await message.reply("📜 <b>Журнал рангов и доступа</b>\n" + "\n".join(lines))

    # ---- сетка ----
    elif kind in ("grid_add", "grid_del", "grid_list", "gban", "gunban"):
        await _grid(message, bot, db, kind, arg, chat, me, now, reply)


async def _defaults(message: Message, db: Database, kind: str, arg: str | None, chat: int, me: int) -> None:
    s = await db.get_settings(chat)
    if kind == "warn_ban" and arg and arg.strip().lower() in ("кик", "мут"):
        await db.set_setting(chat, "warn_action", "kick" if arg.strip().lower() == "кик" else "mute", me)
        await message.reply("✅ При лимите варнов: " + ("исключение." if arg.strip().lower() == "кик" else "мут."))
        return
    if not arg:
        cur = {"def_mute": f"Мут по умолчанию: {_dur(s['mute_secs'] or ms.DEFAULT_MUTE)}",
               "def_ban": f"Бан по умолчанию: {_dur(s['ban_secs'])}",
               "warn_ban": f"При лимите варнов: {s['warn_action']} на {_dur(s['warn_secs'])}",
               "warn_ttl": f"Варн живёт: {s['warn_ttl_days']} дн. (0 — бессрочно)"}[kind]
        await message.reply(f"ℹ️ {cur}\n<i>Изменить: </i><code>мут период 2ч</code>, <code>бан период 7д</code>, "
                            "<code>варны чс 7д</code> (бан), <code>варны чс кик</code>, <code>варны период 30д</code>")
        return
    span = _span(arg)
    if span is None:
        await ux.tell(message, "⚠️ Срок: <code>30м</code>, <code>2ч</code>, <code>7д</code> или <code>навсегда</code>.")
        return
    forever = span[0] == "forever"
    secs = 0 if forever else int(span[1].total_seconds())
    if kind == "def_mute":
        if forever:
            await ux.tell(message, "⚠️ Мут не может быть вечным: максимум 366 дн.")
            return
        await db.set_setting(chat, "mute_secs", secs, me)
        await message.reply(f"✅ Мут по умолчанию: {_dur(secs)}.")
    elif kind == "def_ban":
        await db.set_setting(chat, "ban_secs", secs, me)
        await message.reply(f"✅ Бан по умолчанию: {_dur(secs)}.")
    elif kind == "warn_ban":
        await db.set_setting(chat, "warn_action", "ban", me)
        await db.set_setting(chat, "warn_secs", secs, me)
        await message.reply(f"✅ При лимите варнов: бан {'навсегда' if forever else 'на ' + _dur(secs)}.")
    else:
        await db.set_setting(chat, "warn_ttl_days", 0 if forever else max(1, secs // 86400), me)
        await message.reply("✅ Варны бессрочные." if forever else f"✅ Варн живёт {max(1, secs // 86400)} дн.")


async def _grid(message: Message, bot, db: Database, kind: str, arg: str | None, chat: int, me: int,
                now: int, reply) -> None:
    if kind == "grid_add":
        if await ms.effective_rank(bot, db, chat, me) < 5:
            await ux.tell(message, "⚠️ Добавить чат в сетку может только его создатель.")
            return
        await db.grid_add(chat, me, now)
        await message.reply("🕸 Чат добавлен в вашу сетку. Добавьте остальные чаты командой <code>сетка +</code>, "
                            "тогда <code>глобан @ник</code> будет банить сразу во всех.")
        return
    owner = await db.grid_owner(chat)
    if kind == "grid_del":
        if owner is None:
            await ux.tell(message, "ℹ️ Этот чат не в сетке.")
        elif owner != me:
            await ux.tell(message, "⚠️ Убрать чат может тот, кто его добавил.")
        else:
            await db.grid_remove(chat)
            await message.reply("✅ Чат убран из сетки.")
        return
    if owner is None:
        await ux.tell(message, "ℹ️ Чат не в сетке. Создатель добавляет его командой <code>сетка +</code>.")
        return
    chats = await db.grid_chats(owner)
    if kind == "grid_list":
        await message.reply(f"🕸 <b>Сетка</b>: чатов {len(chats)}\nВладелец: {listed(owner, (await db.user_name(owner)) or str(owner))}",
                            disable_web_page_preview=True)
        return
    if me != owner:
        await ux.tell(message, "⚠️ Глобальный бан доступен владельцу сетки.")
        return
    target = await resolve_user(db, arg, reply)
    if target is None:
        await ux.tell(message, "⚠️ Ответьте командой на сообщение или укажите @ник / id.")
        return
    uid, name = target
    ok = failed = 0
    for cid in chats:
        try:
            if kind == "gban":
                try:
                    member = await ms.get_member(bot, cid, uid)
                except Exception:
                    member = None
                if member is not None and member.status in ("administrator", "creator"):
                    failed += 1
                    continue
                await bot.ban_chat_member(cid, uid)
                await db.set_state(cid, uid, "ban", None, "глобальный бан сетки", me, now)
                await db.log_action(cid, me, uid, "бан", "глобальный бан сетки", now, None)
            else:
                await bot.unban_chat_member(cid, uid, only_if_banned=True)
                await db.clear_state(cid, uid, "ban")
                await db.log_action(cid, me, uid, "разбан", "глобальный разбан сетки", now, None)
            ok += 1
        except Exception:
            failed += 1
    verb = "забанен" if kind == "gban" else "разбанен"
    await message.reply(f"🕸 {listed(uid, name)} {verb} в чатах сетки: {ok}" + (f" (не вышло: {failed})" if failed else ""),
                        disable_web_page_preview=True)
