"""Сервисы без префикса: «калк 2+2», «курс usd», «крипто btc», «вики Пушкин», «факт», «маршрут А — Б», «гороскоп лев»."""
from __future__ import annotations

import html
import re
import time
from datetime import date

from aiogram import F, Router
from aiogram.types import Message

from bot import services as svc
from bot import ux
from bot.toggles import Enabled

router = Router(name="services")
router.message.filter(Enabled("svc_on"))

_PATTERNS = [
    ("calc", r"^(?:калк|реши|посчитай|calc)\s+(.+)$"),
    ("rate", r"^(?:курс|конв)\s+(.+)$"),
    ("crypto", r"^(?:крипто|крипта)\s+(.+)$"),
    ("wiki", r"^(?:вики|wiki)\s+(.+)$"),
    ("fact", r"^(?:факт|факт дня)$"),
    ("route", r"^(?:маршрут|расстояние|дистанция)\s+(.+)$"),
    ("horo", r"^гороскоп(?:\s+(.+))?$"),
]
_COMPILED = [(k, re.compile(p, re.IGNORECASE | re.DOTALL)) for k, p in _PATTERNS]
COOLDOWN = 3
_last: dict[int, float] = {}


def parse(text: str | None):
    t = (text or "").strip()
    if not t or len(t) > 200:
        return None
    for kind, rx in _COMPILED:
        m = rx.match(t)
        if m:
            return kind, (m.group(1) or "").strip() if m.groups() else ""
    return None


@router.message(F.text.func(lambda t: parse(t) is not None))
async def on_service(message: Message, http=None, ai=None) -> None:
    if message.from_user is None:
        return
    now = time.time()
    if now - _last.get(message.from_user.id, 0) < COOLDOWN:
        return
    if len(_last) > 5000:
        _last.clear()
    _last[message.from_user.id] = now
    kind, arg = parse(message.text)

    if kind == "calc":
        try:
            await message.reply(f"🧮 <code>{html.escape(arg)}</code> = <b>{html.escape(svc.calc(arg))}</b>")
        except svc.CalcError as e:
            await ux.tell(message, f"⚠️ {html.escape(str(e))}. Пример: <code>калк (2+3)*4</code>")
        return
    if kind == "horo":
        sign = svc.parse_sign(arg)
        if sign is None:
            await ux.tell(message, "⚠️ Укажите знак или дату: <code>гороскоп лев</code> или <code>гороскоп 15.08</code>")
            return
        if ai is None or not getattr(ai, "has_river", False):
            await message.reply("🔮 Гороскоп сочиняет ИИ, а он у меня сейчас не подключён.")
            return
        try:
            text = await ai.ask(f"Сегодня {date.today():%d.%m.%Y}. Напиши короткий (3–4 предложения) весёлый гороскоп на сегодня "
                                f"для знака «{sign}». Без вступлений и без пометки, что это шутка.",
                                max_tokens=300)
        except Exception:
            text = ""
        await message.reply(f"🔮 <b>{sign}</b>\n{html.escape(text.strip())}" if text and text.strip()
                            else "🔮 Звёзды сейчас молчат — попробуйте позже.")
        return
    if http is None:
        await ux.tell(message, "⚠️ Сервис сейчас недоступен.")
        return

    if kind == "rate":
        parsed = svc.parse_money(arg)
        if parsed is None:
            await ux.tell(message, "⚠️ Пример: <code>курс 100 usd eur</code>, <code>курс евро</code>")
            return
        amount, src, dst = parsed
        rates = await svc.fetch_rates(http)
        res = svc.convert(rates, amount, src, dst) if rates else None
        await message.reply(f"💱 {svc.fmt_num(amount)} {src} = <b>{svc.fmt_num(res)} {dst}</b>\n<i>курс ЦБ РФ</i>" if res is not None
                            else "💱 Не нашёл такую валюту или сервис курсов недоступен.")
    elif kind == "crypto":
        parsed = svc.parse_crypto(arg)
        if parsed is None:
            await ux.tell(message, "⚠️ Пример: <code>крипто btc</code>, <code>крипто 2 eth rub</code> "
                                   f"(монеты: {', '.join(k for k in svc.COINS if k.isascii())})")
            return
        amount, coin, fiat = parsed
        price = await svc.fetch_crypto(http, coin, fiat)
        await message.reply(f"🪙 {svc.fmt_num(amount)} {coin.upper()} = <b>{svc.fmt_num(price * amount)} {fiat.upper()}</b>" if price
                            else "🪙 Сервис курсов крипты сейчас недоступен.")
    elif kind == "wiki":
        got = await svc.wiki(http, arg)
        if got is None:
            await message.reply("📚 Ничего не нашёл.")
        else:
            title, extract, url = got
            await message.reply(f"📚 <b>{html.escape(title)}</b>\n{html.escape(extract)}" + (f'\n<a href="{html.escape(url)}">Читать в Википедии</a>' if url else ""),
                                disable_web_page_preview=True)
    elif kind == "fact":
        fact = await svc.fact_of_day(http)
        await message.reply(f"📅 <b>В этот день</b>\n{html.escape(fact)}" if fact else "📅 Факт дня сейчас недоступен.")
    elif kind == "route":
        pair = svc.parse_route(arg)
        if pair is None:
            await ux.tell(message, "⚠️ Пример: <code>маршрут Москва — Казань</code>")
            return
        r = await svc.route(http, *pair)
        if r is None:
            await message.reply("🗺 Не нашёл такие города или сервис карт недоступен.")
            return
        lines = [f"🗺 <b>{html.escape(r['from'])} → {html.escape(r['to'])}</b>", f"По прямой: {svc.fmt_num(r['air_km'])} км"]
        if r["road_km"] is not None:
            h = r["hours"]
            lines.append(f"По дороге: {svc.fmt_num(r['road_km'])} км, ~{int(h)} ч {int(h % 1 * 60)} мин на машине")
        await message.reply("\n".join(lines))
