"""Пара: меню, действия, РП пары, история искр, расходы, список и топ, ссора, обида, расставание.
Команды без слэша: «пара …» или «отн …» (например «пара действия», «пара завтрак», «пара обнять»). Запрос и брак — прежние
команды «отношения @ник» / «брак @ник» (handlers/family.py): теперь они создают пару с общим кошельком."""
import asyncio
import html
import logging
import re
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot import gender, gifs, ux
from bot.db import Database
from bot.family import Family
from bot.mod_service import is_admin, real_reply
from bot.pair import premium as pp, pets as pt, baby as bb, kids as kd, data, economy as eco, gifts as gf, house as hs, quests as qs
from bot.pair.service import PairService, effective_streak, is_sleeping, partner_of, side_of
from bot.rich_ui import Btn, Screen
from bot import rich_ui
from bot.targets import mention, resolve_user

router = Router(name="pair")
_RE = re.compile(r"^(?:пара|отн)(?:\s+(.+))?$", re.IGNORECASE | re.DOTALL)
SUBS = {"меню": "menu", "я": "menu", "профиль": "menu", "действия": "actions", "действие": "actions", "история": "history",
        "лог": "history", "расходы": "costs", "расход": "costs", "содержание": "costs", "список": "list", "топ": "top",
        "расстаться": "end", "расторгнуть": "end", "обида": "offense", "обидеться": "offense", "простить": "offense",
        "помириться": "peace", "мир": "peace", "пополнить": "topup", "справка": "help", "помощь": "help",
        "запрос": "request", "задания": "quests", "задание": "quests", "квесты": "quests", "сезон": "season", "подарки": "gifts", "подарок": "gifts", "магазин": "gifts", "подарить": "give", "витрина": "showcase", "дом": "house", "близость": "intim", "малыш": "baby", "премиум": "premium", "vip": "premium", "питомцы": "pets", "питомец": "pets", "питомник": "pets", "дети": "kids", "ребёнок": "kids", "ребенок": "kids", "зал": "hall", "славы": "hall", "ожидание": "baby", "защита": "protect", "дома": "houses", "улица": "houses", "награда": "claim", "да": "yes", "нет": "no"}
TOP_KINDS = {"тепло": "тепло", "искры": "искры", "длительность": "длительность", "активность": "активность"}


def parse(text: str | None):
    """(команда, остаток) или None, если это не команда пары («пара минут» в обычной речи не трогаем)."""
    m = _RE.match((text or "").strip())
    if not m:
        return None
    rest = (m.group(1) or "").strip()
    if not rest:
        return "menu", ""
    word, _, arg = rest.partition(" ")
    key = data.norm(word)
    if key in SUBS:
        return SUBS[key], arg.strip()
    if data.find_action(rest):
        return "act", rest
    if data.find_rp(rest):
        return "rp", rest
    return None


def n(x: int) -> str:
    return f"{int(x):,}".replace(",", " ")


async def name(db: Database, uid: int) -> str:
    return (await db.user_name(uid)) or f"id{uid}"


async def m(db: Database, uid: int) -> str:
    return str(mention(uid, await name(db, uid)))


def duration_since(ts: int, now: int) -> str:
    return eco.fmt_duration(max(now - ts, 0))


# ---------- события (сообщения про ссору, распад, уровень) ----------
async def event_text(db: Database, p: dict, ev: tuple) -> str | None:
    kind, d = ev
    a, b = await m(db, p["u1"]), await m(db, p["u2"])
    if kind == "levelup":
        return f"🎖 {a} и {b}, у вас новый уровень: <b>{data.level_name(d['level'])}</b> ({d['level']}). Подарок: +{n(d['gift'])} 🔥"
    if kind == "quarrel":
        hours = max(round((d["until"] - int(time.time())) / 3600), 1)
        return f"💢 {a} и {b}, искры кончились, вы поссорились. Помиритесь за {hours} ч: <code>пара пополнить 100</code>."
    if kind == "dissolved":
        return f"💔 {a} и {b} больше не пара. Были вместе {duration_since(d['since'], int(time.time()))}."
    if kind == "warn":
        return f"🚨 {a} и {b}, искр на завтра не хватит: {n(d['sparks'])} из {n(d['need'])}. Загляните в <code>пара действия</code>."
    if kind == "quest":
        return f"✅ {a} и {b} справились с заданием: {d['text']} · +{n(d['sparks'])} 🔥 +{d['warmth']} ☀️"
    if kind == "bill_missed":
        return f"🧾 {a} и {b}, за дом не хватило денег. Долг {n(d['debt'])} 🔥, просрочек {d['missed']}. <code>пара дом оплатить</code>"
    if kind == "arrested":
        return f"🚔 Дом {a} и {b} арестован за долг {n(d['debt'])} 🔥. Оплатите: <code>пара дом оплатить</code>"
    if kind == "confiscated":
        return f"⚖️ Дом {a} и {b} забрали за долги. В кошелёк вернулось {n(d['back'])} 🔥."
    if kind == "pet_hatched":
        return f"🐣 У {a} и {b} вылупился питомец: {d['emoji']} <b>{d['species']}</b> ({d['rarity']})"
    if kind == "child_grown":
        return f"💼 {html.escape(d['name'])} вырос(ла) и съезжает от {a} и {b}. Профессия: <b>{d['job']}</b>. Оставил(а) вам {n(d['gift'])} 🔥"
    if kind == "baby_lost":
        return f"🤝 {a} и {b}, ожидание малыша не удалось сохранить. Это не ваша вина. Берегите друг друга."
    if kind == "baby_born":
        names = ", ".join(f"<b>{html.escape(x)}</b>" for x in d["names"])
        return f"👶 {a} и {b}, поздравляем! {'Родились' if len(d['names']) > 1 else 'Родился(ась)'} {names} · +{bb.BIRTH_WARMTH} ☀️"
    if kind == "peace":
        return f"🤝 {a} и {b} помирились. Всё снова можно!"
    return None


async def event_lines(db: Database, p: dict, events: list, skip: tuple = ()) -> list[str]:
    out = []
    for ev in events:
        if ev[0] in skip:
            continue
        t = await event_text(db, p, ev)
        if t:
            out.append(t)
    return out


# ---------- экраны ----------
def menu_screen(p: dict, partner_name: str, now: int, kids: int, notes: list[str]) -> Screen:
    lvl = p["level"]
    base = eco.threshold(lvl)
    step = eco.level_step(lvl)
    upkeep = eco.upkeep_amount(lvl, kids, p["sparks"])
    side = side_of(p, p["u1"])
    lines = [f"💞 <b>Половинка:</b> {partner_name}",
             f"🎖 Уровень {lvl} · <b>{data.level_name(lvl)}</b>",
             f"☀️ Тепло {n(p['warmth'] - base)} из {n(step)}",
             f"🔥 Искры {n(p['sparks'])}",
             f"📉 Расход {n(upkeep)} в сутки"
             + (f" · спишется через {eco.fmt_duration(p['upkeep_at'] - now)}" if p["state"] == "ok" else ""),
             f"📅 Серия {effective_streak(p, now)} дн. · +{int(eco.streak_bonus(effective_streak(p, now)) * 100)}% к теплу",
             (f"{pp.BADGE} Премиум пары до {time.strftime('%d.%m.%Y', time.gmtime(p['premium_until']))}" if pp.active(p, now) else "🕙 Премиум пары: <code>пара премиум</code>"),
             f"🕙 Вместе {duration_since(p['created'], now)}"
             + (" · 💍 в браке" if p["stage"] == "marriage" else "")]
    lines += notes
    lines.append(f"🆔 Пара № {p['id']}")
    pid = p["id"]
    rows = [[Btn("✨ Действия", cb=f"pr:a:{pid}"), Btn("📋 История", cb=f"pr:h:{pid}:all:0")],
            [Btn("📉 Расходы", cb=f"pr:e:{pid}"), Btn("👥 Пары беседы", cb=f"pr:l:{pid}")],
            [Btn("📋 Задания", cb=f"pr:q:{pid}"), Btn("🏆 Топ", cb=f"pr:t:{pid}:тепло")],
            [Btn("🎁 Подарки", cb=f"pr:gs:{pid}:0"), Btn("🖼 Витрина", cb=f"pr:sc:{pid}")],
            [Btn("🏠 Дом", cb=f"pr:ho:{pid}"), Btn("👶 Малыш", cb=f"pr:bb:{pid}")],
            [Btn("👦 Дети", cb=f"pr:ki:{pid}"), Btn("🐾 Питомцы", cb=f"pr:pt:{pid}")],
            [Btn("💎 Премиум", cb=f"pr:pm:{pid}"), Btn("⚙️ Ещё", cb=f"pr:more:{pid}")]]
    return Screen("💞 Ваша пара", lines, rows, quote=True)


def more_screen(p: dict, user: int) -> Screen:
    pid = p["id"]
    offended = p["offended_by"] == user
    return Screen("⚙️ Ещё", [
        "😢 Обида закрывает половинке действия и РП, пока ты не простишь.",
        "🤝 Помирить пару в ссоре может любое пополнение искр.",
        "💰 Пополнить кошелёк монетами: <code>пара пополнить 100</code> (1 монета = 1 искра)."],
        [[Btn("😊 Простить" if offended else "😢 Обидеться", cb=f"pr:ob:{pid}"), Btn("🤝 Помириться", cb=f"pr:peace:{pid}")],
         [Btn("💔 Расстаться", cb=f"pr:end:{pid}", style="danger")], [Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")]])


def actions_screen(p: dict, now: int, user: int, result_lines: list[str] | None = None) -> Screen:
    pid, lvl = p["id"], p["level"]
    side = side_of(p, user)
    wait = max(p[f"next{side}"] - now, 0)
    best = data.best_action(lvl)
    nxt = data.next_action(lvl)
    lines = list(result_lines or [])
    lines.append(f"✨ Лучшее: <b>{best.key}</b> · +{n(best.sparks)} 🔥 · откат {best.cd} мин.")
    if nxt:
        lines.append(f"🔒 Дальше: {nxt.key} — с {nxt.level} уровня")
    lines.append("✅ Действие доступно" if wait == 0 else f"⏳ Следующее действие через {eco.fmt_duration(wait)}")
    lines.append("<i>Нажми на название или напиши «пара название».</i>")
    avail = data.unlocked(lvl)[-8:][::-1]
    btns = [Btn(f"{a.emoji} {a.key}", cb=f"pr:do:{pid}:{a.level}", style="primary" if a is best and wait == 0 else None) for a in avail]
    rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
    rows.append([Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("✨ Действия", lines, rows)


async def history_screen(svc: PairService, db: Database, p: dict, kind: str, page: int, now: int) -> Screen:
    pid = p["id"]
    rows_, total = await svc.history(pid, page, 10, kind, now)
    pages = max((total + 9) // 10, 1)
    page = min(max(page, 0), pages - 1)
    icons = {"action": "✨", "upkeep": "📉", "topup": "💰", "create": "💞", "quarrel": "💢", "level": "🎖"}
    lines = [f"🔥 Сейчас: {n(p['sparks'])}"]
    for r in rows_:
        t = time.strftime("%d.%m %H:%M", time.localtime(r["ts"] + 3 * 3600 - time.timezone))
        who = f" · {html.escape(await name(db, r['actor']))}" if r["actor"] else ""
        warm = f" · тепло +{r['warmth']}" if r["warmth"] else ""
        lines.append(f"{icons.get(r['kind'], '•')} {html.escape(r['detail'] or r['kind'])} · {t}{who} · стало {n(r['balance'])}{warm} · "
                     f"<b>{'+' if r['amount'] > 0 else ''}{n(r['amount'])}</b>")
    if not rows_:
        lines.append("Записей пока нет. История хранится 30 дней.")
    tabs = [Btn(("• " if kind == k else "") + label, cb=f"pr:h:{pid}:{k}:0") for label, k in (("Все", "all"), ("Приход", "in"), ("Траты", "out"))]
    nav = []
    if page > 0:
        nav.append(Btn("◀️", cb=f"pr:h:{pid}:{kind}:{page - 1}"))
    nav.append(Btn(f"{page + 1}/{pages}", cb="noop"))
    if page < pages - 1:
        nav.append(Btn("▶️", cb=f"pr:h:{pid}:{kind}:{page + 1}"))
    return Screen("📜 История искр", lines, [tabs, nav, [Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")]])


async def costs_screen(svc: PairService, p: dict, now: int) -> Screen:
    kids = await svc.kids(p)
    base = eco.upkeep_base(p["level"])
    total = int(round(base * (1 + eco.KID_UPKEEP * kids)))
    final = eco.upkeep_amount(p["level"], kids, p["sparks"])
    lines = [f"🎖 Уровень {p['level']}: {n(base)}"]
    if kids:
        lines.append(f"👶 Дети: {kids}: +{n(total - base)} · +{int(kids * eco.KID_UPKEEP * 100)}%")
    if final < total:
        lines.append(f"🏷 Потолок 3% кошелька: {n(final)}")
    lines.append(f"📉 Итого: <b>{n(final)}</b> в сутки")
    if p["state"] == "ok":
        lines.append(f"🕙 Спишется через {eco.fmt_duration(p['upkeep_at'] - now)}")
        days = p["sparks"] // final if final else 0
        lines.append(f"🧮 Кошелька хватит примерно на {days} сут.")
    lines.append("<i>Каждый ребёнок прибавляет 10%, больше 3% кошелька за сутки не берём (но не меньше 15). В ссоре содержание не списывается.</i>")
    return Screen("📉 Расходы пары", lines, [[Btn("📜 Все траты", cb=f"pr:h:{p['id']}:out:0")],
                                              [Btn("◀️ Меню", cb=f"pr:m:{p['id']}", style="link")]])


async def list_screen(svc: PairService, db: Database, p: dict | None, chat: int, now: int) -> Screen:
    rows, sleeping = await svc.list_chat(chat, now)
    lines = []
    for i, r in enumerate(rows[:20], 1):
        mark = (" 💍" if r["stage"] == "marriage" else "") + (f" {pp.BADGE}" if pp.active(r, now) else "")
        lines.append(f"{i}. {html.escape(await name(db, r['u1']))} + {html.escape(await name(db, r['u2']))}{mark} · "
                     f"{duration_since(r['created'], now)} · ур. {r['level']}")
    if not lines:
        lines.append("В этой беседе пока нет пар.")
    lines.append(f"Всего: {len(rows)}" + (f" · спящих: {sleeping}" if sleeping else ""))
    back = [[Btn("◀️ Меню", cb=f"pr:m:{p['id']}", style="link")]] if p else []
    return Screen("👥 Пары беседы", lines, back)


async def top_screen(svc: PairService, db: Database, p: dict | None, chat: int, by: str, now: int) -> Screen:
    rows = await svc.top(chat, by, now)
    lines = []
    for i, r in enumerate(rows, 1):
        who = f"{html.escape(await name(db, r['u1']))} + {html.escape(await name(db, r['u2']))}"
        val = {"тепло": f"ур. {r['level']} · ☀️ {n(r['warmth'])}", "искры": f"🔥 {n(r['sparks'])}",
               "длительность": duration_since(r["created"], now), "активность": f"🫂 {n(r.get('activity', 0))}"}[by]
        lines.append(f"{i}. {who}{' ' + pp.BADGE if pp.active(r, now) else ''} · {val}")
    if not lines:
        lines.append("Пока нет пар.")
    pid = p["id"] if p else 0
    tabs = [Btn(("• " if k == by else "") + label, cb=f"pr:t:{pid}:{k}")
            for label, k in (("☀️ Тепло", "тепло"), ("🔥 Искры", "искры"), ("🕙 Время", "длительность"), ("🫂 Активность", "активность"))]
    rows_ = [tabs[:2], tabs[2:]]
    if p:
        rows_.append([Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("🏆 Топ пар беседы", lines, rows_)


def bar(done: int, total: int, width: int = 8) -> str:
    k = round(width * min(done, total) / total) if total else width
    return "▰" * k + "▱" * (width - k)


async def quests_screen(svc: PairService, p: dict, now: int) -> Screen:
    pid = p["id"]
    rows = await svc.quests(p, now)
    lines = []
    for title, scope in (("Сегодня", "d"), ("На неделе", "w")):
        lines.append(f"<b>{title}</b>")
        for q in (r for r in rows if r["scope"] == scope):
            mark = "✅" if q["done"] else "🔘"
            lines.append(f"{mark} {qs.text(q['kind'], q['goal'])}\n    {bar(q['progress'], q['goal'])} {q['progress']}/{q['goal']}"
                         f" · +{n(q['reward'])} 🔥 · +{q['warmth']} ☀️")
    s = await svc.season(p, now)
    lines.append(f"🌟 Сезон: ступень {s['step']}/{s['max']} · очки {s['points']} (по {s['per']} на ступень)")
    btns = []
    if s["step"] > s["claimed"]:
        btns.append([Btn(f"🎁 Забрать награды сезона ({s['step'] - s['claimed']})", cb=f"pr:cl:{pid}", style="success")])
    btns.append([Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("📋 Задания пары", lines, btns)


def gifts_screen(p: dict, section: str) -> Screen:
    pid = p["id"]
    sec = section if section in gf.SECTIONS else gf.SECTIONS[0]
    items = [g for g in gf.GIFTS if g.section == sec]
    lines = ["Подарок покупается за твои монеты и ложится в витрину пары. Подарить: <code>пара подарить роза</code> или кнопкой.",
             "Тепло получают первые 3 подарка в сутки."]
    lines += [f"{g.emoji} {g.key} · {n(g.price)} 🪙 · +{gf.warmth(g.price)} ☀️" for g in items]
    tabs = [Btn(("• " if s == sec else "") + s, cb=f"pr:gs:{pid}:{i}") for i, s in enumerate(gf.SECTIONS)]
    rows = [tabs[i:i + 3] for i in range(0, len(tabs), 3)]
    gi = gf.SECTIONS.index(sec)
    buy = [Btn(f"{g.emoji} {g.key}", cb=f"pr:gb:{pid}:{gf.GIFTS.index(g)}") for g in items]
    rows += [buy[i:i + 2] for i in range(0, len(buy), 2)]
    rows.append([Btn("🖼 Витрина", cb=f"pr:sc:{pid}"), Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("🎁 Подарки · " + sec, lines, rows)


async def showcase_screen(svc: PairService, p: dict) -> Screen:
    pid = p["id"]
    items = await svc.showcase(pid)
    lines = []
    for sec in gf.SECTIONS:
        row = [f"{g.emoji} {g.key} ×{items[g.key]}" for g in gf.GIFTS if g.section == sec and g.key in items]
        if row:
            lines.append(f"<b>{sec}:</b> " + " · ".join(row))
    if not lines:
        lines.append("Витрина пуста. Подарите что-нибудь половинке!")
    lines.append(f"✨ Престиж витрины: <b>{n(gf.prestige(items))}</b>")
    return Screen("🖼 Витрина пары", lines, [[Btn("🎁 Подарки", cb=f"pr:gs:{pid}:0"), Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")]])


async def house_screen(svc: PairService, p: dict, now: int) -> Screen:
    pid = p["id"]
    h = await svc.house(pid)
    if h is None:
        lines = ["У пары пока нет дома. Дом даёт копилку, комнаты и престиж, но раз в неделю присылает счёт.",
                 f"🔥 В кошельке: {n(p['sparks'])}"]
        lines += [f"{x.emoji} {x.key} · {n(x.price)} 🔥 · комнат {x.slots} · копилка {n(x.hoard_cap)}" for x in hs.HOUSES]
        btns = [Btn(f"{x.emoji} {x.key}", cb=f"pr:hb:{pid}:{i}") for i, x in enumerate(hs.HOUSES)]
        rows = [btns[i:i + 3] for i in range(0, len(btns), 3)] + [[Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")]]
        return Screen("🏠 Дом", lines, rows)
    d = h["def"]
    title = html.escape(h["name"]) if h["name"] else d.key
    lines = [f"{d.emoji} <b>{title}</b> · {d.key}",
             f"🏅 {hs.rank_name(h['prestige'])} · престиж {n(h['prestige'])}",
             f"💰 Копилка {n(h['hoard'])} из {n(d.hoard_cap)}",
             f"🧾 Счёт {n(h['bill'])} 🔥 через {eco.fmt_duration(max(h['bill_at'] - now, 0))}"]
    if h["debt"]:
        lines.append(f"⚠️ Долг {n(h['debt'])} 🔥 · пропущено счетов {h['missed']}" + (" · 🚔 дом арестован" if h["arrested"] else ""))
    rooms = [f"{r.emoji} {r.key} {h['rooms'][r.key]}/{hs.ROOM_MAX}" for r in hs.ROOMS if r.key in h["rooms"]]
    lines.append(f"🚪 Комнаты {len(h['rooms'])}/{d.slots}: " + (" · ".join(rooms) if rooms else "пока нет"))
    nxt = [Btn(f"{r.emoji} {r.key} · {n(hs.room_cost(r, h['rooms'].get(r.key, 0) + 1))}", cb=f"pr:hr:{pid}:{i}")
           for i, r in enumerate(hs.ROOMS) if h["rooms"].get(r.key, 0) < hs.ROOM_MAX
           and (r.key in h["rooms"] or len(h["rooms"]) < d.slots)]
    rows = [nxt[i:i + 2] for i in range(0, len(nxt), 2)]
    rows.append([Btn("💰 +100", cb=f"pr:hh:{pid}:100"), Btn("💰 +1000", cb=f"pr:hh:{pid}:1000"),
                 Btn("💰 −100", cb=f"pr:hh:{pid}:-100"), Btn("💰 −1000", cb=f"pr:hh:{pid}:-1000")])
    if h["debt"]:
        rows.append([Btn("💳 Оплатить долг", cb=f"pr:hp:{pid}", style="danger")])
    rows.append([Btn("🌃 Улица", cb=f"pr:hs:{pid}"), Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    lines.append("<i>Переезд в дом побольше: пара дом купить вилла (старый выкупают за 50%).</i>")
    return Screen("🏠 Дом", lines, rows)


async def street_screen(svc: PairService, db: Database, p: dict | None, chat: int) -> Screen:
    rows = await svc.top_houses(chat)
    lines = []
    for i, r in enumerate(rows, 1):
        h = hs.find_house(r["tier"])
        nm = html.escape(r["name"]) if r["name"] else h.key
        lines.append(f"{i}. {h.emoji} {nm} · {html.escape(await name(db, r['u1']))} + {html.escape(await name(db, r['u2']))} · "
                     f"{hs.rank_name(r['prestige'])} · {n(r['prestige'])}")
    if not lines:
        lines.append("На улице пока пусто. Арестованные дома в топ не попадают.")
    back = [[Btn("🏠 Мой дом", cb=f"pr:ho:{p['id']}"), Btn("◀️ Меню", cb=f"pr:m:{p['id']}", style="link")]] if p else []
    return Screen("🌃 Улица", lines, back)


async def baby_screen(svc: PairService, db: Database, p: dict, now: int) -> Screen:
    pid = p["id"]
    b = await svc.baby(pid, now)
    kids = await svc.children(pid)
    kid_line = "👶 Дети: " + (", ".join(html.escape(k["name"]) for k in kids) if kids else "пока нет")
    if b is None:
        return Screen("👶 Малыш", [kid_line, "Сейчас вы не ждёте малыша.",
                                  f"Защита: {'🛡 включена' if p['protect'] else '⚠️ выключена'} (<code>пара защита вкл|выкл</code>)"],
                      [[Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")]])
    w = b["week"]
    mother = await m(db, b["mother"]) if b["mother"] else "пока не выбрано"
    lines = [f"👶 Ожидание малыша · неделя {w}/{bb.WEEKS} · триместр {bb.trimester(w)}",
             f"👤 Носит: {mother}",
             f"❤️ Здоровье {bar(b['health'], 100)} {b['health']}/100",
             f"🥄 Двойня: {'ждём двойню' if b['twins'] and w >= 12 else 'узнаем позже'}" if b["twins"] else "🥄 Один малыш",
             f"✏️ Имя: {html.escape(b['name']) if b['name'] else 'выберем при рождении (пара малыш имя Тима)'}",
             "Здоровье падает со временем: заботьтесь — врач, отдых, витамины.", kid_line]
    rows = []
    if not b["mother"]:
        rows.append([Btn("👶 Ношу я", cb=f"pr:bm:{pid}", style="primary")])
    care = [Btn(f"{e} {k}", cb=f"pr:bc:{pid}:{k}") for k, (e, _, _, _) in bb.CARE.items()]
    rows.append(care)
    if w < bb.ABORT_UNTIL_WEEK:
        rows.append([Btn("🚫 Прервать", cb=f"pr:ba:{pid}", style="danger")])
    rows.append([Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("👶 Малыш", lines, rows)


async def kids_screen(svc: PairService, p: dict, now: int) -> Screen:
    pid = p["id"]
    rows_ = await svc.children(pid, now)
    lines, rows = [], []
    for c in rows_:
        if c["grown"]:
            lines.append(f"💼 {html.escape(c['name'])} · {c['job']} · взрослый(ая)")
            continue
        skills = " · ".join(f"{kd.SKILL_NAMES[k]} {c[k]}" for k in kd.SKILL_NAMES)
        lines.append(f"{'👶' if c['age'] < 3 else '👦'} <b>{html.escape(c['name'])}</b> · {c['age']} лет · {kd.stage(c['age'])}\n"
                     f"    ❤️ {bar(c['mood'], 100)} {c['mood']}/100 · {skills}")
        rows.append([Btn(f"{v[0]} {k}", cb=f"pr:kc:{pid}:{c['id']}:{k}") for k, v in kd.CARE.items() if c["age"] >= v[5]][:4])
    if not lines:
        lines.append("Детей пока нет. Пара может подождать малыша: <code>пара малыш</code>.")
    lines.append("<i>Год ребёнка — 5 суток. В 18 лет он выбирает профессию и съезжает.</i>")
    rows.append([Btn("👶 Малыш", cb=f"pr:bb:{pid}"), Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("👦 Дети", lines, rows)


async def pets_screen(svc: PairService, p: dict, now: int) -> Screen:
    pid = p["id"]
    pets = await svc.pets(pid, now)
    lines, rows = [], []
    for r in pets:
        if r["egg"]:
            lines.append(f"🥚 Яйцо · вылупится через {eco.fmt_duration(max(r['hatch_at'] - now, 0))}")
            continue
        nm = html.escape(r["name"]) if r["name"] else r["species"]
        lines.append(f"{r['emoji']} <b>{nm}</b> · {r['species']} ({r['rarity']}) · ур. {r['level']}\n"
                     f"    ❤️ {bar(r['mood'], 100)} {r['mood']}/100 · приносит {n(pt.income(r['rarity'], r['xp']))} 🔥/сутки")
        rows.append([Btn(f"{v[0]} {k} {nm}", cb=f"pr:pc:{pid}:{r['id']}:{k}") for k, v in pt.CARE.items()])
    if not lines:
        lines.append("Питомцев пока нет. Яйцо стоит " + f"{pt.EGG_PRICE} 🔥, вылупится за сутки; редкость случайная.")
    cap = pp.PETS_MAX if pp.active(p, now) else pt.MAX_PETS
    lines.append(f"🔥 В кошельке {n(p['sparks'])} · места {len(pets)}/{cap}")
    act = []
    if len(pets) < cap:
        act.append(Btn(f"🥚 Яйцо · {pt.EGG_PRICE}", cb=f"pr:pe:{pid}"))
    if any(not r["egg"] for r in pets):
        act.append(Btn("🎁 Забрать приработок", cb=f"pr:pg:{pid}", style="success"))
    if act:
        rows.append(act)
    rows.append([Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen("🐾 Питомцы", lines, rows)


async def premium_screen(bot, p: dict, now: int) -> Screen:
    pid = p["id"]
    lines = [f"{pp.BADGE} <b>Премиум пары</b> — {pp.PRICE} ⭐ на 30 дней (платёж разовый, продлевается вручную).",
             f"☀️ +{pp.WARMTH_PCT}% к теплу от всего, что вы делаете",
             f"🐾 {pp.PETS_MAX} питомцев вместо {pt.MAX_PETS}",
             f"🤝 {pp.QUARREL_HOURS} часов на примирение вместо {eco.QUARREL_HOURS}",
             f"{pp.BADGE} значок в списках и топах"]
    if pp.active(p, now):
        lines.append(f"✅ Активен до {time.strftime('%d.%m.%Y', time.gmtime(p['premium_until']))}. Можно продлить: +30 дней.")
    rows = []
    try:
        from aiogram.types import LabeledPrice
        link = await bot.create_invoice_link(
            title="Премиум пары", description="30 дней: +10% тепла, 5 питомцев, 48 часов на примирение, значок.",
            payload=pp.payload(pid), currency="XTR", prices=[LabeledPrice(label="Премиум пары на 30 дней", amount=pp.PRICE)])
        rows.append([Btn(f"⭐ Оплатить {pp.PRICE}", url=link, style="success")])
    except Exception:
        logging.info("pair premium: не удалось создать счёт")
        lines.append("⚠️ Оплата сейчас недоступна, попробуйте позже.")
    rows.append([Btn("◀️ Меню", cb=f"pr:m:{pid}", style="link")])
    return Screen(f"{pp.BADGE} Премиум пары", lines, rows)


def help_text() -> str:
    return ("💞 <b>Пара</b>\n"
            "Искры 🔥 приносят действия, а раз в сутки часть уходит на жизнь. Кончились — ссора, потом расставание.\n"
            "☀️ Тепло растит уровень.\n"
            "<blockquote expandable>"
            "<code>отношения</code> реплеем или с @ником · завести пару\n<code>брак</code> · свадьба (с 3 уровня)\n"
            "<code>пара</code> · меню\n<code>пара действия</code> · <code>пара завтрак</code> · что-то сделать вместе\n"
            "<code>пара обнять</code> · РП: обнять, поцеловать, кусь, шлёп, погладить, щелбан и другие\n"
            "<code>пара задания</code> · <code>пара награда</code>\n"
            "<code>пара подарки</code> · <code>пара подарить роза</code> · <code>пара витрина</code>\n"
            "<code>пара дом</code> · <code>пара дома</code> · дом, комнаты, копилка, счёт\n"
            "<code>пара малыш</code> · <code>пара дети</code> · <code>пара питомцы</code>\n"
            "<code>пара близость</code> · <code>пара защита вкл|выкл</code> (если админ включил <code>+близость</code>)\n"
            "<code>пара история</code> · <code>расходы</code> · <code>список</code> · <code>топ</code>\n"
            "<code>пара пополнить 100</code> · монеты в искры\n"
            "<code>пара обида</code> · <code>пара расстаться</code> · <code>пара премиум</code>"
            "</blockquote>")


# ---------- команды ----------
async def _my_pair(message: Message, svc: PairService, now: int):
    """(пара, события) или (None, []) с подсказкой, если пары нет."""
    p = await svc.get(message.chat.id, message.from_user.id)
    if p is None:
        await ux.tell(message, "💞 У вас нет пары в этой беседе. Завести: <code>отношения @ник</code> (или ответом на сообщение).")
        return None, []
    p, events = await svc.settle(p["id"], now)
    return p, events


async def _send_events(message: Message, db: Database, p: dict | None, events: list, pair_row: dict, skip: tuple = ()) -> None:
    for t in await event_lines(db, pair_row, events, skip):
        await message.answer(t)


@router.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("+близость", "-близость")))
async def intim_toggle(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await ux.tell(message, "⚠️ Включать близость пар могут только админы.")
        return
    on = message.text.strip().startswith("+")
    await db.set_setting(message.chat.id, "pair_intim", 1 if on else 0)
    await message.reply("🌙 Близость пар включена (только для взрослых беседы, по согласию обоих)." if on else "🌙 Близость пар выключена.")


@router.message(F.text.func(lambda t: parse(t) is not None))
async def pair_cmd(message: Message, bot, db: Database, http=None) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    if not (await db.get_settings(message.chat.id))["rp_on"]:
        return
    sub, arg = parse(message.text)
    svc, fam, now = PairService(db), Family(db), int(time.time())
    chat, me = message.chat.id, message.from_user.id

    if sub == "help":
        await message.reply(help_text())
        return
    if sub == "request":                                           # «пара запрос @ник» = «отношения @ник»
        from bot.handlers.family import _propose
        target = await resolve_user(db, arg or None, real_reply(message))
        if target is None:
            await ux.tell(message, "⚠️ Ответьте командой на сообщение человека или укажите @ник.")
            return
        if target[0] == (await bot.me()).id:
            await message.reply("🤖 Я всего лишь бот, у меня нет пары.")
            return
        await _propose(message, bot, db, fam, "relation", target[0], now)
        return
    if sub in ("yes", "no"):
        from bot.handlers.family import _apply
        req = await fam.pending_to(chat, me, now)
        if req is None:
            await ux.tell(message, "ℹ️ Вам никто не предлагал: ответить можно на запрос «отношения @ник» или «брак @ник».")
            return
        if not await fam.delete_request(req["id"]):
            return
        text = await _apply(db, fam, req["kind"], chat, req["from_user"], req["to_user"], now) if sub == "yes" else "💔 Отказ."
        edited = False
        if req.get("message_id"):
            try:
                await bot.edit_message_text(text, chat_id=chat, message_id=req["message_id"])
                edited = True
            except Exception:
                pass
        if not edited:
            await message.answer(text)
        if sub == "yes" and "теперь" in text:
            await gifs.extra_gif(bot, http, chat, gifs.FAMILY_MAP.get(req["kind"]), await gender.get(db, req["from_user"]),
                                 await gender.get(db, req["to_user"]))
        return
    if sub in ("list", "top") and await svc.get(chat, me) is None:   # списки доступны и без своей пары
        if sub == "list":
            await message.answer(**_msg(await list_screen(svc, db, None, chat, now)))
        else:
            by = TOP_KINDS.get(data.norm(arg), "тепло")
            await message.answer(**_msg(await top_screen(svc, db, None, chat, by, now)))
        return

    if not await gender.ensure(message, db):
        return
    p, events = await _my_pair(message, svc, now)
    if p is None:
        for r in events:
            pass
        return
    partner = partner_of(p, me)
    if sub == "menu":
        await _send_menu(message, db, svc, p, partner, now)
    elif sub == "actions":
        await rich_ui.send(bot, chat, actions_screen(p, now, me), thread_id=_thread(message))
    elif sub in ("act", "rp"):
        res = await (svc.act(p["id"], me, arg, now) if sub == "act" else svc.rp(p["id"], me, arg, now))
        if not res.ok:
            await ux.tell(message, res.error or "⚠️ Не получилось.")
        else:
            text = await _result_text(db, p, me, partner, res, sub)
            sent = False
            if sub == "rp" and (await db.get_settings(chat)).get("rp_gifs", 1):
                sent = await gifs.reply_gif(bot, http, message, text, gifs.PAIR_MAP.get(res.info["rp"].key), await gender.get(db, me),
                                            await gender.get(db, partner), reply_to=message.message_id)
            if not sent:
                await message.reply(text)
        for t in await event_lines(db, p, res.events, skip=("levelup",) if sub == "act" and res.ok else ()):
            await message.answer(t)
    elif sub in ("quests", "season"):
        await rich_ui.send(bot, chat, await quests_screen(svc, p, now), thread_id=_thread(message))
    elif sub == "gifts":
        sec = next((s for s in gf.SECTIONS if data.norm(s) == data.norm(arg)), gf.SECTIONS[0])
        await rich_ui.send(bot, chat, gifts_screen(p, sec), thread_id=_thread(message))
    elif sub == "showcase":
        await rich_ui.send(bot, chat, await showcase_screen(svc, p), thread_id=_thread(message))
    elif sub == "give":
        res = await svc.give(p["id"], me, arg, now)
        if not res.ok:
            await ux.tell(message, f"⚠️ {res.error}")
        else:
            g = res.info["gift"]
            extra = f" · +{res.info['warmth']} ☀️" if res.info["warmth"] else ""
            await message.reply(f"{g.emoji} {await m(db, me)} дарит {await m(db, partner)}: <b>{g.key}</b>{extra}")
        for t in await event_lines(db, p, res.events):
            await message.answer(t)
    elif sub == "houses":
        await rich_ui.send(bot, chat, await street_screen(svc, db, p, chat), thread_id=_thread(message))
    elif sub == "house":
        word, _, rest = arg.partition(" ")
        w = data.norm(word)
        res = None
        if w in ("купить", "переехать"):
            res = await svc.buy_house(p["id"], me, rest, now)
            ok = f"{res.info['house'].emoji} Куплен дом «{res.info['house'].key}» за {n(res.info['cost'])} 🔥" if res.ok else None
        elif w in ("комната", "построить", "улучшить"):
            res = await svc.build_room(p["id"], me, rest, now)
            ok = f"{res.info['room'].emoji} {res.info['room'].key}: уровень {res.info['level']} за {n(res.info['cost'])} 🔥" if res.ok else None
        elif w == "копилка":
            sign = -1 if rest.startswith(("-", "−")) else 1
            digits = "".join(ch for ch in rest if ch.isdigit())
            if not digits:
                await ux.tell(message, "⚠️ Например: <code>пара дом копилка +500</code> или <code>-500</code>.")
                return
            res = await svc.hoard_move(p["id"], me, sign * int(digits), now)
            ok = f"💰 Копилка: {n(res.info['hoard'])} · кошелёк {n(res.info['sparks'])}" if res.ok else None
        elif w == "оплатить":
            res = await svc.pay_debt(p["id"], me, now)
            ok = (f"💳 Оплачено {n(res.info['paid'])} 🔥, долг {n(res.info['debt'])}" + (" · 🚔 арест снят" if res.info["free"] else "")) if res.ok else None
        elif w in ("имя", "название"):
            res = await svc.rename_house(p["id"], me, rest)
            ok = f"✏️ Название: {html.escape(res.info['name'])}" if res.ok else None
        if res is not None:
            await (message.reply(ok) if res.ok else ux.tell(message, f"⚠️ {res.error}"))
            for t in await event_lines(db, p, res.events):
                await message.answer(t)
        else:
            await rich_ui.send(bot, chat, await house_screen(svc, p, now), thread_id=_thread(message))
    elif sub == "protect":
        on = data.norm(arg) in ("вкл", "включить", "да", "on", "+")
        if data.norm(arg) not in ("вкл", "включить", "да", "on", "+", "выкл", "выключить", "нет", "off", "-"):
            await ux.tell(message, f"ℹ️ Защита сейчас {'включена' if p['protect'] else 'выключена'}: <code>пара защита вкл</code> или <code>выкл</code>.")
            return
        await svc.set_protect(p["id"], me, on)
        await message.reply("🛡 Защита включена." if on else "⚠️ Защита выключена: шанс малыша заметно выше.")
    elif sub == "intim":
        if not (await db.get_settings(chat))["pair_intim"]:
            await ux.tell(message, "🔒 Близость пар выключена в этой беседе: админ включает «+близость».")
            return
        err = svc.intim_check(p, me, now)
        if err:
            await ux.tell(message, f"⚠️ {err}")
            return
        pid = p["id"]
        exp = now + 300
        await message.answer(
            f"🌙 {await m(db, me)} предлагает {await m(db, partner)} провести вечер вместе. Защита: {'🛡 включена' if p['protect'] else '⚠️ выключена'}.",
            reply_markup=rich_ui.kb([[Btn("💞 " + gender.gz("⟦Согласен|Согласна⟧", await gender.get(db, partner)), cb=f"pr:iy:{pid}:{me}:{exp}", style="success"),
                                      Btn("✖️ Не сейчас", cb=f"pr:in:{pid}:{me}:{exp}")]]))
    elif sub == "baby":
        word, _, rest = arg.partition(" ")
        w = data.norm(word)
        if w in bb.CARE:
            res = await svc.care(p["id"], me, w, now)
            await (message.reply(f"{res.info['emoji']} {res.info['label'].capitalize()}: здоровье +{res.info['plus']} → {res.info['health']}/100")
                   if res.ok else ux.tell(message, f"⚠️ {res.error}"))
        elif w in ("имя", "назвать"):
            res = await svc.name_baby(p["id"], me, rest)
            await (message.reply(f"✏️ Имя малыша: {html.escape(res.info['name'])}") if res.ok else ux.tell(message, f"⚠️ {res.error}"))
        elif w in ("прервать",):
            await message.answer("🚫 Прервать ожидание? Решение необратимо.", reply_markup=rich_ui.kb(
                [[Btn("Да, прервать", cb=f"pr:bay:{p['id']}", style="danger"), Btn("Отмена", cb=f"pr:bn:{p['id']}")]]))
        else:
            await rich_ui.send(bot, chat, await baby_screen(svc, db, p, now), thread_id=_thread(message))
    elif sub == "kids":
        kws = arg.split()
        act = next((w for w in kws if data.norm(w) in kd.CARE), None)
        if act:
            nm = " ".join(w for w in kws if w is not act)
            kids_ = [c for c in await svc.children(p["id"], now) if not c["grown"]]
            c = next((c for c in kids_ if data.norm(c["name"]) == data.norm(nm)), kids_[0] if kids_ and not nm else None)
            if c is None:
                await ux.tell(message, "⚠️ Не нашёл ребёнка: <code>пара дети покормить Тима</code>.")
            else:
                res = await svc.care_child(p["id"], me, c["id"], act, now)
                if res.ok:
                    i = res.info
                    extra = f" · {kd.SKILL_NAMES[i['skill']]} +{i['gained']}" if i["gained"] else ""
                    await message.reply(f"{i['emoji']} Вы с {html.escape(i['name'])} {i['label']}: настроение {i['mood']}/100{extra}")
                else:
                    await ux.tell(message, f"⚠️ {res.error}")
        else:
            await rich_ui.send(bot, chat, await kids_screen(svc, p, now), thread_id=_thread(message))
    elif sub == "pets":
        word, _, rest = arg.partition(" ")
        w = data.norm(word)
        pets = [r for r in await svc.pets(p["id"], now) if not r["egg"]]
        if w in ("яйцо", "купить"):
            res = await svc.buy_egg(p["id"], me, now)
            await (message.reply(f"🥚 Яйцо куплено за {pt.EGG_PRICE} 🔥, вылупится через сутки.") if res.ok else ux.tell(message, f"⚠️ {res.error}"))
        elif w in ("собрать", "забрать", "доход"):
            res = await svc.collect_pets(p["id"], me, now)
            await (message.reply(f"🎁 Питомцы принесли {n(res.info['sparks'])} 🔥") if res.ok else ux.tell(message, f"⚠️ {res.error}"))
            for t in await event_lines(db, p, res.events):
                await message.answer(t)
        elif w in pt.CARE:
            nm = rest.strip()
            r = next((x for x in pets if data.norm(x["name"] or x["species"]) == data.norm(nm)), pets[0] if pets and not nm else None)
            if r is None:
                await ux.tell(message, "⚠️ Не нашёл питомца: <code>пара питомцы покормить Пушок</code>.")
            else:
                res = await svc.care_pet(p["id"], me, r["id"], w, now)
                await (message.reply(f"{res.info['emoji']} {html.escape(r['name'] or r['species'])}: настроение {res.info['mood']}/100")
                       if res.ok else ux.tell(message, f"⚠️ {res.error}"))
        elif w in ("имя", "назвать"):
            old, _, new = rest.partition(" ")
            r = next((x for x in pets if data.norm(x["name"] or x["species"]) == data.norm(old)), None)
            if r is None or not new:
                await ux.tell(message, "⚠️ Так: <code>пара питомцы имя котёнок Пушок</code>.")
            else:
                res = await svc.name_pet(p["id"], me, r["id"], new)
                await (message.reply(f"✏️ Теперь его зовут {html.escape(res.info['name'])}") if res.ok else ux.tell(message, f"⚠️ {res.error}"))
        else:
            await rich_ui.send(bot, chat, await pets_screen(svc, p, now), thread_id=_thread(message))
    elif sub == "premium":
        await rich_ui.send(bot, chat, await premium_screen(bot, p, now), thread_id=_thread(message))
    elif sub == "claim":
        res = await svc.claim_season(p["id"], me, now)
        await (message.reply(f"🎁 Награда сезона: +{n(res.info['sparks'])} 🔥 (ступень {res.info['step']})") if res.ok
               else ux.tell(message, f"⚠️ {res.error}"))
    elif sub == "history":
        kind = {"приход": "in", "траты": "out", "доход": "in"}.get(data.norm(arg.split()[0]) if arg else "", "all")
        page = int(arg.split()[-1]) - 1 if arg and arg.split()[-1].isdigit() else 0
        await rich_ui.send(bot, chat, await history_screen(svc, db, p, kind, page, now), thread_id=_thread(message))
    elif sub == "costs":
        await rich_ui.send(bot, chat, await costs_screen(svc, p, now), thread_id=_thread(message))
    elif sub == "list":
        await rich_ui.send(bot, chat, await list_screen(svc, db, p, chat, now), thread_id=_thread(message))
    elif sub == "top":
        by = TOP_KINDS.get(data.norm(arg), "тепло")
        await rich_ui.send(bot, chat, await top_screen(svc, db, p, chat, by, now), thread_id=_thread(message))
    elif sub == "offense":
        res = await svc.toggle_offense(p["id"], me, now)
        if not res.ok:
            await ux.tell(message, f"⚠️ {res.error}")
        elif res.info["offended"]:
            await message.answer(f"😢 {await m(db, partner)}, твоя половинка в обиде. Действия и РП для тебя закрыты, пока "
                                 f"{await m(db, me)} не простит: <code>пара обида</code>.")
        else:
            await message.answer(f"😊 {await m(db, partner)}, твоя половинка больше не обижается. Всё снова доступно!")
    elif sub == "peace":
        await message.reply(_peace_hint(p, now))
    elif sub == "topup":
        if not arg.isdigit():
            await ux.tell(message, "⚠️ Сколько монет? Например: <code>пара пополнить 100</code>.")
            return
        res = await svc.topup(p["id"], me, int(arg), now)
        if not res.ok:
            await ux.tell(message, f"⚠️ {res.error}")
            return
        await message.reply(f"💰 В кошелёк пары добавлено <b>{n(res.info['sparks'])}</b> 🔥.")
        for t in await event_lines(db, p, res.events):
            await message.answer(t)
    elif sub == "end":
        await rich_ui.send(bot, chat, await _end_screen(db, p, partner), thread_id=_thread(message))


def _thread(message: Message) -> int | None:
    return message.message_thread_id if getattr(message, "is_topic_message", False) else None


def _msg(screen: Screen) -> dict:
    text, kb = rich_ui.to_classic(screen)
    return {"text": text, "reply_markup": kb}


def _peace_hint(p: dict, now: int) -> str:
    if p["state"] != "quarrel":
        return "🤝 Вы не в ссоре. Всё хорошо!"
    return (f"💢 Вы в ссоре: искры кончились, действия закрыты. Помирят любые искры — пополните кошелёк: "
            f"<code>пара пополнить 100</code>. Осталось {eco.fmt_duration(p['quarrel_until'] - now)}.")


async def _send_menu(message: Message, db: Database, svc: PairService, p: dict, partner: int, now: int) -> None:
    await rich_ui.send(message.bot, message.chat.id, await _menu(db, svc, p, message.from_user.id, now),
                       thread_id=_thread(message))


async def _menu(db: Database, svc: PairService, p: dict, user: int, now: int) -> Screen:
    partner = partner_of(p, user)
    kids = await svc.kids(p)
    notes = []
    if p["state"] == "quarrel":
        notes.append(f"💢 <b>Ссора</b>: помирят любые искры, осталось {eco.fmt_duration(p['quarrel_until'] - now)}")
    elif p["sparks"] < eco.upkeep_amount(p["level"], kids, p["sparks"]) * 2:
        notes.append("🚨 Искр мало: скоро не хватит на содержание")
    if p["offended_by"]:
        notes.append("😢 Обида: " + ("ты обижаешься на половинку" if p["offended_by"] == user else "половинка обижена на тебя"))
    side = side_of(p, user)
    wait = p[f"next{side}"] - now
    notes.append("✨ Действие доступно" if wait <= 0 else f"⏳ Действие через {eco.fmt_duration(wait)}")
    if is_sleeping(p, now):
        notes.append("💤 Пара спит: давно ничего не делали")
    return menu_screen(p, await m(db, partner), now, kids, notes)


async def _end_screen(db: Database, p: dict, partner: int) -> Screen:
    pid = p["id"]
    word = "Развестись" if p["stage"] == "marriage" else "Расстаться"
    return Screen(f"💔 {word} с {html.escape(await name(db, partner))}?", [
        f"Пропадёт всё, что есть у пары: {n(p['sparks'])} 🔥, уровень {p['level']}. Согласие половинки не нужно."],
        [[Btn(f"💔 Да, {word.lower()}", cb=f"pr:endy:{pid}", style="danger"), Btn("✖️ Отмена", cb=f"pr:m:{pid}")]])


async def _result_text(db: Database, p: dict, me: int, partner: int, res, sub: str) -> str:
    a, b = await m(db, me), await m(db, partner)
    i = res.info
    if sub == "rp":
        rp = i["rp"]
        extra = f"\n☀️ +{i['warmth']} тепла" if i["warmth"] else ""
        return f"{rp.emoji} {rp.text.format(a=a, b=b)}{extra}"
    act = i["action"]
    lines = [f"{act.emoji} {act.text.format(a=a, b=b)}",
             f"🔥 +{n(i['sparks'])} · ☀️ +{i['warmth']} тепла · снова через {eco.fmt_duration(i['cd'])}"]
    extras = []
    if i["tired"]:
        extras.append("😮‍💨 усталость: награда вдвое меньше")
    if i["unison"]:
        extras.append("в унисон +20%")
    if i["streak"] and not i["together"]:
        extras.append(f"серия {i['streak']} дн. +{int(eco.streak_bonus(i['streak']) * 100)}%")
    if extras:
        lines.append("🔗 " + " · ".join(extras))
    if i["together"]:
        lines.append(f"💞 День вместе засчитан: серия {i['streak']} дн., +{eco.DAY_TOGETHER_WARMTH} тепла")
    for ev in res.events:
        if ev[0] == "levelup":
            lines.append(f"🎖 Новый уровень: <b>{data.level_name(ev[1]['level'])}</b> ({ev[1]['level']})! 🎁 +{n(ev[1]['gift'])} 🔥")
    return "\n".join(lines)


# ---------- кнопки ----------
@router.callback_query(F.data.startswith("pr:"))
async def pair_cb(cb: CallbackQuery, bot, db: Database) -> None:
    parts = cb.data.split(":")
    if len(parts) < 3 or not parts[2].isdigit() or cb.message is None:
        await cb.answer()
        return
    op, pid, args = parts[1], int(parts[2]), parts[3:]
    svc, now, user = PairService(db), int(time.time()), cb.from_user.id
    p0 = await svc.get_by_id(pid)
    if p0 is None or p0["ended_at"] is not None or p0["chat_id"] != cb.message.chat.id:
        await cb.answer("Эта пара уже не существует.", show_alert=True)
        return
    if user not in (p0["u1"], p0["u2"]):
        await cb.answer("Не твоя кнопка", show_alert=True)
        return
    p, events = await svc.settle(pid, now)
    if p is None:
        await cb.answer("💔 Пара распалась.", show_alert=True)
        for t in await event_lines(db, p0, events):
            await cb.message.answer(t)
        return
    partner = partner_of(p, user)
    popup = None
    if op == "m":
        screen = await _menu(db, svc, p, user, now)
    elif op == "more":
        screen = more_screen(p, user)
    elif op == "a":
        screen = actions_screen(p, now, user)
    elif op == "do":
        level = int(args[0]) if args and args[0].isdigit() else 0
        action = next((x for x in data.ACTIONS if x.level == level), None)
        res = await svc.act(pid, user, action.key, now) if action else None
        p = await svc.get_by_id(pid)
        if res is None or not res.ok:
            popup = res.error if res else "Нет такого действия."
            screen = actions_screen(p, now, user)
        else:
            text = await _result_text(db, p, user, partner, res, "act")
            popup = f"+{n(res.info['sparks'])} 🔥 · +{res.info['warmth']} ☀️"
            screen = actions_screen(p, now, user, text.split("\n"))
    elif op == "h":
        kind = args[0] if args else "all"
        page = int(args[1]) if len(args) > 1 and args[1].lstrip("-").isdigit() else 0
        screen = await history_screen(svc, db, p, kind if kind in ("all", "in", "out") else "all", page, now)
    elif op == "q":
        screen = await quests_screen(svc, p, now)
    elif op == "cl":
        res = await svc.claim_season(pid, user, now)
        popup = f"🎁 +{n(res.info['sparks'])} 🔥" if res.ok else res.error
        p = await svc.get_by_id(pid)
        screen = await quests_screen(svc, p, now)
    elif op == "gs":
        i = int(args[0]) if args and args[0].isdigit() else 0
        screen = gifts_screen(p, gf.SECTIONS[i] if i < len(gf.SECTIONS) else gf.SECTIONS[0])
    elif op == "gb":
        i = int(args[0]) if args and args[0].isdigit() else -1
        g = gf.GIFTS[i] if 0 <= i < len(gf.GIFTS) else None
        res = await svc.give(pid, user, g.key, now) if g else None
        p = await svc.get_by_id(pid)
        if res is None or not res.ok:
            popup = res.error if res else "Нет такого подарка."
        else:
            popup = f"{g.emoji} Подарено: {g.key}"
            await cb.message.answer(f"{g.emoji} {await m(db, user)} дарит {await m(db, partner)}: <b>{g.key}</b>"
                                    + (f" · +{res.info['warmth']} ☀️" if res.info["warmth"] else ""))
            events = events + res.events
        screen = gifts_screen(p, g.section if g else gf.SECTIONS[0])
    elif op == "sc":
        screen = await showcase_screen(svc, p)
    elif op == "ho":
        screen = await house_screen(svc, p, now)
    elif op == "hs":
        screen = await street_screen(svc, db, p, p["chat_id"])
    elif op in ("hb", "hr", "hh", "hp"):
        res = None
        if op == "hb":
            i = int(args[0]) if args and args[0].isdigit() else -1
            res = await svc.buy_house(pid, user, hs.HOUSES[i].key, now) if 0 <= i < len(hs.HOUSES) else None
            popup = "🏠 Дом куплен!" if res and res.ok else None
        elif op == "hr":
            i = int(args[0]) if args and args[0].isdigit() else -1
            res = await svc.build_room(pid, user, hs.ROOMS[i].key, now) if 0 <= i < len(hs.ROOMS) else None
            popup = "🚪 Комната улучшена" if res and res.ok else None
        elif op == "hh":
            res = await svc.hoard_move(pid, user, int(args[0]) if args else 0, now)
            popup = "💰 Готово" if res.ok else None
        else:
            res = await svc.pay_debt(pid, user, now)
            popup = "💳 Оплачено" if res.ok else None
        if res is not None and not res.ok:
            popup = res.error
        events = events + (res.events if res else [])
        p = await svc.get_by_id(pid)
        screen = await house_screen(svc, p, now)
    elif op == "ki":
        screen = await kids_screen(svc, p, now)
    elif op == "kc":
        res = await svc.care_child(pid, user, int(args[0]) if args and args[0].isdigit() else 0, args[1] if len(args) > 1 else "", now)
        popup = (f"{res.info['emoji']} {res.info['name']}: настроение {res.info['mood']}" if res.ok else res.error)
        screen = await kids_screen(svc, p, now)
    elif op == "pt":
        screen = await pets_screen(svc, p, now)
    elif op == "pe":
        res = await svc.buy_egg(pid, user, now)
        popup = "🥚 Яйцо куплено" if res.ok else res.error
        p = await svc.get_by_id(pid)
        screen = await pets_screen(svc, p, now)
    elif op == "pg":
        res = await svc.collect_pets(pid, user, now)
        popup = f"🎁 +{n(res.info['sparks'])} 🔥" if res.ok else res.error
        events = events + res.events
        p = await svc.get_by_id(pid)
        screen = await pets_screen(svc, p, now)
    elif op == "pc":
        res = await svc.care_pet(pid, user, int(args[0]) if args and args[0].isdigit() else 0, args[1] if len(args) > 1 else "", now)
        popup = f"{res.info['emoji']} настроение {res.info['mood']}" if res.ok else res.error
        screen = await pets_screen(svc, p, now)
    elif op == "pm":
        screen = await premium_screen(bot, p, now)
    elif op == "bb":
        screen = await baby_screen(svc, db, p, now)
    elif op == "bm":
        res = await svc.set_mother(pid, user)
        popup = None if res.ok else res.error
        screen = await baby_screen(svc, db, p, now)
    elif op == "bc":
        res = await svc.care(pid, user, args[0] if args else "", now)
        popup = f"{res.info['emoji']} +{res.info['plus']} здоровья" if res.ok else res.error
        screen = await baby_screen(svc, db, p, now)
    elif op == "ba":
        await cb.answer()
        await cb.message.answer("🚫 Прервать ожидание? Решение необратимо.", reply_markup=rich_ui.kb(
            [[Btn("Да, прервать", cb=f"pr:bay:{pid}", style="danger"), Btn("Отмена", cb=f"pr:bn:{pid}")]]))
        return
    elif op == "bay":
        res = await svc.abort(pid, user, now)
        await cb.answer(None if res.ok else res.error, show_alert=not res.ok)
        if res.ok:
            await cb.message.edit_text("🤝 Ожидание малыша прервано. Берегите себя.")
        return
    elif op == "bn":
        await cb.answer("Отменено")
        await cb.message.delete()
        return
    elif op in ("iy", "in"):
        init = int(args[0]) if args and args[0].isdigit() else 0
        exp = int(args[1]) if len(args) > 1 and args[1].isdigit() else 0
        if user == init:
            await cb.answer("Ответить должна половинка", show_alert=True)
            return
        if now > exp:
            await cb.answer("Предложение устарело", show_alert=True)
            return
        if op == "in":
            await cb.answer()
            await cb.message.edit_text("🌙 Половинка пока не готова. Всё в порядке.")
            return
        if not (await db.get_settings(p["chat_id"]))["pair_intim"]:
            await cb.answer("Близость выключена в беседе", show_alert=True)
            return
        res = await svc.intimacy(pid, init, now)
        if not res.ok:
            await cb.answer(res.error, show_alert=True)
            return
        await cb.answer("💞")
        a, b2 = await m(db, init), await m(db, user)
        text = f"🌙 {a} и {b2} провели ночь вместе · +{res.info['warmth']} ☀️"
        kb = None
        if res.info["pregnant"]:
            text += "\n👶 Тест положительный! Вы ждёте малыша. Кто носит?"
            kb = rich_ui.kb([[Btn("👶 Ношу я", cb=f"pr:bm2:{pid}", style="primary")]])
        await cb.message.edit_text(text, reply_markup=kb)
        for t in await event_lines(db, p, res.events):
            await cb.message.answer(t)
        return
    elif op == "bm2":
        res = await svc.set_mother(pid, user)
        if res.ok:
            await cb.answer("👶")
            await cb.message.edit_text(f"👶 Малыша носит {await m(db, user)}. Заботьтесь друг о друге: <code>пара малыш</code>.")
        else:
            await cb.answer(res.error, show_alert=True)
        return
    elif op == "e":
        screen = await costs_screen(svc, p, now)
    elif op == "l":
        screen = await list_screen(svc, db, p, p["chat_id"], now)
    elif op == "t":
        screen = await top_screen(svc, db, p, p["chat_id"], TOP_KINDS.get(args[0] if args else "", "тепло"), now)
    elif op == "ob":
        res = await svc.toggle_offense(pid, user, now)
        popup = (await gender.say(db, user, "😢 Ты ⟦обиделся|обиделась⟧: действия половинки закрыты") if res.ok and res.info["offended"] else
                 "😊 Обида снята" if res.ok else res.error)
        p = await svc.get_by_id(pid)
        screen = more_screen(p, user)
    elif op == "peace":
        popup = _peace_hint(p, now).replace("<code>", "").replace("</code>", "")
        screen = more_screen(p, user)
    elif op == "end":
        screen = await _end_screen(db, p, partner)
    elif op == "endy":
        ended = await svc.end(pid, "breakup", now, user)
        await cb.answer("💔 Отношения завершены")
        if ended:
            try:
                await cb.message.edit_text(f"💔 {await m(db, user)} и {await m(db, partner)} больше не пара. "
                                           f"Вы были вместе {duration_since(p['created'], now)}.")
            except Exception:
                pass
        return
    else:
        await cb.answer()
        return
    await cb.answer(popup[:190] if popup else None, show_alert=bool(popup and len(popup) > 60))
    await rich_ui.show(cb, screen)
    for t in await event_lines(db, p, events):
        await cb.message.answer(t)


# ---------- фон: содержание, ссора, распад ----------
async def pair_watchdog(bot, db: Database) -> None:
    """Раз в 5 минут досчитывает пары, у которых что-то подошло к сроку, и объявляет ссору, распад и предупреждения."""
    svc = PairService(db)
    while True:
        await asyncio.sleep(300)
        try:
            now = int(time.time())
            for p in await svc.due(now):
                p2, events = await svc.settle(p["id"], now)
                for ev in events:
                    if ev[0] in ("quarrel", "dissolved", "warn", "bill_missed", "arrested", "confiscated", "baby_born", "baby_lost", "child_grown", "pet_hatched"):
                        t = await event_text(db, p, ev)
                        if t:
                            try:
                                await bot.send_message(p["chat_id"], t)
                            except Exception:
                                logging.info("pair: не отправилось в чат %s", p["chat_id"])
        except Exception:
            logging.exception("pair watchdog")
