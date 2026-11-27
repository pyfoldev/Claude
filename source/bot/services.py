"""Сервисы: калькулятор, курсы валют, крипта, википедия, факт дня, расстояние между городами, гороскоп.

Разбор и вычисления — чистые функции; запросы к внешним API — отдельные функции, которым передают aiohttp-сессию.
Любой сбой сети даёт None: бот в этом случае отвечает «сервис недоступен», а не падает."""
from __future__ import annotations

import ast
import math
import operator
import random
import re
from datetime import date
from urllib.parse import quote

import aiohttp

TIMEOUT = aiohttp.ClientTimeout(total=8)
UA = {"User-Agent": "chat-helper-bot/1.0"}


# ---------- калькулятор ----------
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_UN = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round, "sin": math.sin, "cos": math.cos, "tan": math.tan,
          "log": math.log, "ln": math.log, "log10": math.log10, "exp": math.exp, "floor": math.floor, "ceil": math.ceil}
_CONST = {"pi": math.pi, "e": math.e, "пи": math.pi}


class CalcError(ValueError):
    pass


def _eval(node, depth=0):
    if depth > 30:
        raise CalcError("слишком сложно")
    if isinstance(node, ast.Expression):
        return _eval(node.body, depth + 1)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONST:
        return _CONST[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UN:
        return _UN[type(node.op)](_eval(node.operand, depth + 1))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        a, b = _eval(node.left, depth + 1), _eval(node.right, depth + 1)
        if isinstance(node.op, ast.Pow) and (abs(b) > 1000 or (abs(a) > 1e6 and abs(b) > 50)):
            raise CalcError("слишком большая степень")
        return _BIN[type(node.op)](a, b)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS \
            and not node.keywords and 1 <= len(node.args) <= 2:
        return _FUNCS[node.func.id](*[_eval(a, depth + 1) for a in node.args])
    raise CalcError("не понял выражение")


def calc(expr: str) -> str:
    """«2+2*2», «sqrt(16)+10%3», «2^10», «15% от 200» -> строка результата. CalcError — не получилось."""
    e = (expr or "").strip().lower().replace(",", ".").replace("×", "*").replace("÷", "/").replace("^", "**")
    e = e.replace(":", "/")
    m = re.match(r"^([\d.]+)\s*%\s*от\s*([\d.]+)$", e)
    if m:
        e = f"{m.group(1)}*{m.group(2)}/100"
    if not e or len(e) > 120 or not re.fullmatch(r"[\d\s.+\-*/%()a-zа-я0-9_]+", e):
        raise CalcError("не понял выражение")
    try:
        val = _eval(ast.parse(e, mode="eval"))
    except CalcError:
        raise
    except ZeroDivisionError:
        raise CalcError("на ноль делить нельзя")
    except (SyntaxError, ValueError, OverflowError, TypeError, RecursionError):
        raise CalcError("не понял выражение")
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            raise CalcError("результат не число")
        val = round(val, 10)
        return f"{val:.10g}" if abs(val) < 1e15 else f"{val:.6e}"
    return str(val) if abs(val) < 10 ** 30 else f"{float(val):.6e}"


# ---------- курсы валют ----------
CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
_CUR_ALIAS = {"доллар": "USD", "доллары": "USD", "долларов": "USD", "доллара": "USD", "бакс": "USD", "евро": "EUR",
              "рубль": "RUB", "рублей": "RUB", "рубли": "RUB", "рубля": "RUB", "руб": "RUB", "юань": "CNY", "юаней": "CNY", "тенге": "KZT", "гривна": "UAH", "гривен": "UAH",
              "фунт": "GBP", "иена": "JPY", "иен": "JPY", "лира": "TRY", "лир": "TRY", "злотый": "PLN",
              "франк": "CHF", "бел": "BYN"}


def parse_money(arg: str, default_to: str = "RUB") -> tuple[float, str, str] | None:
    """«100 usd eur», «usd», «евро», «2.5 доллара в рубли» -> (сумма, из, в)."""
    toks = [t for t in re.split(r"\s+", (arg or "").strip().lower().replace(",", ".")) if t and t not in ("в", "в→", "to", "->")]
    amount = 1.0
    if toks and re.fullmatch(r"\d+(?:\.\d+)?", toks[0]):
        amount = float(toks.pop(0))
    codes = []
    for t in toks[:2]:
        t = _CUR_ALIAS.get(t, t.upper())
        if not re.fullmatch(r"[A-Z]{3}", t):
            return None
        codes.append(t)
    if not codes or amount <= 0 or amount > 1e12:
        return None
    return amount, codes[0], codes[1] if len(codes) > 1 else default_to


def convert(rates: dict, amount: float, src: str, dst: str) -> float | None:
    """rates: {код: рублей за 1 единицу}. RUB = 1."""
    def rub(code):
        return 1.0 if code == "RUB" else rates.get(code)
    a, b = rub(src), rub(dst)
    if a is None or b is None or b == 0:
        return None
    return amount * a / b


async def fetch_rates(session: aiohttp.ClientSession) -> dict | None:
    try:
        async with session.get(CBR_URL, timeout=TIMEOUT, headers=UA) as r:
            if r.status != 200:
                return None
            data = await r.json(content_type=None)
        return {code: v["Value"] / v["Nominal"] for code, v in data["Valute"].items()}
    except (aiohttp.ClientError, TimeoutError, KeyError, ValueError, TypeError):
        return None


# ---------- крипта ----------
COINS = {"btc": "bitcoin", "биткоин": "bitcoin", "eth": "ethereum", "эфир": "ethereum", "ton": "the-open-network",
         "тон": "the-open-network", "sol": "solana", "usdt": "tether", "bnb": "binancecoin", "doge": "dogecoin",
         "xrp": "ripple", "ltc": "litecoin", "trx": "tron", "ada": "cardano", "not": "notcoin"}
FIATS = {"usd", "rub", "eur", "uah", "kzt", "try", "cny"}


def parse_crypto(arg: str) -> tuple[float, str, str] | None:
    toks = (arg or "").strip().lower().replace(",", ".").split()
    amount = 1.0
    if toks and re.fullmatch(r"\d+(?:\.\d+)?", toks[0]):
        amount = float(toks.pop(0))
    if not toks or toks[0] not in COINS or amount <= 0 or amount > 1e12:
        return None
    fiat = toks[1] if len(toks) > 1 else "usd"
    fiat = {"доллар": "usd", "рубль": "rub", "руб": "rub", "евро": "eur"}.get(fiat, fiat)
    return (amount, toks[0], fiat) if fiat in FIATS else None


async def fetch_crypto(session: aiohttp.ClientSession, coin: str, fiat: str) -> float | None:
    try:
        async with session.get("https://api.coingecko.com/api/v3/simple/price", timeout=TIMEOUT, headers=UA,
                               params={"ids": COINS[coin], "vs_currencies": fiat}) as r:
            if r.status != 200:
                return None
            data = await r.json(content_type=None)
        return float(data[COINS[coin]][fiat])
    except (aiohttp.ClientError, TimeoutError, KeyError, ValueError, TypeError):
        return None


def fmt_num(x: float) -> str:
    if x >= 1000:
        return f"{x:,.0f}".replace(",", " ")
    if x >= 1:
        return f"{x:,.2f}".replace(",", " ")
    return f"{x:.6g}"


# ---------- википедия, факт дня ----------
async def wiki(session: aiohttp.ClientSession, query: str) -> tuple[str, str, str] | None:
    """(заголовок, краткое описание, ссылка) или None."""
    q = (query or "").strip()
    if not 2 <= len(q) <= 80:
        return None
    try:
        async with session.get("https://ru.wikipedia.org/w/api.php", timeout=TIMEOUT, headers=UA,
                               params={"action": "opensearch", "search": q, "limit": 1, "format": "json"}) as r:
            found = await r.json(content_type=None)
        title = found[1][0]
        async with session.get(f"https://ru.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}",
                               timeout=TIMEOUT, headers=UA) as r:
            if r.status != 200:
                return None
            d = await r.json(content_type=None)
        extract = (d.get("extract") or "").strip()
        if not extract:
            return None
        return d.get("title", title), extract[:700], d.get("content_urls", {}).get("desktop", {}).get("page", "")
    except (aiohttp.ClientError, TimeoutError, IndexError, KeyError, ValueError, TypeError):
        return None


async def fact_of_day(session: aiohttp.ClientSession, today: date | None = None) -> str | None:
    """Историческое событие «в этот день» из Википедии."""
    d = today or date.today()
    try:
        async with session.get(f"https://ru.wikipedia.org/api/rest_v1/feed/onthisday/events/{d.month:02d}/{d.day:02d}",
                               timeout=TIMEOUT, headers=UA) as r:
            if r.status != 200:
                return None
            data = await r.json(content_type=None)
        events = [e for e in data.get("events", []) if e.get("text") and e.get("year")]
        if not events:
            return None
        e = random.choice(events)
        return f"{e['year']} год: {e['text']}"
    except (aiohttp.ClientError, TimeoutError, KeyError, ValueError, TypeError):
        return None


# ---------- расстояние между городами ----------
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def parse_route(arg: str) -> tuple[str, str] | None:
    arg = re.sub(r"^из\s+", "", (arg or "").strip(), flags=re.IGNORECASE)
    parts = re.split(r"\s*(?:—|–|→|->|=>)\s*|\s+-\s+|\s+(?:до|в)\s+", arg, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2 or not all(2 <= len(p.strip()) <= 40 for p in parts):
        return None
    return parts[0].strip(), parts[1].strip()


async def _geocode(session: aiohttp.ClientSession, place: str) -> tuple[float, float, str] | None:
    async with session.get("https://nominatim.openstreetmap.org/search", timeout=TIMEOUT, headers=UA,
                           params={"q": place, "format": "json", "limit": 1, "accept-language": "ru"}) as r:
        data = await r.json(content_type=None)
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", place).split(",")[0]


async def route(session: aiohttp.ClientSession, a: str, b: str) -> dict | None:
    """{'from','to','air_km','road_km','hours'} (дорога — если OSRM ответил)."""
    try:
        pa, pb = await _geocode(session, a), await _geocode(session, b)
    except (aiohttp.ClientError, TimeoutError, KeyError, ValueError, TypeError):
        return None
    if not pa or not pb:
        return None
    out = {"from": pa[2], "to": pb[2], "air_km": haversine_km(pa[0], pa[1], pb[0], pb[1]), "road_km": None, "hours": None}
    try:
        async with session.get(f"https://router.project-osrm.org/route/v1/driving/{pa[1]},{pa[0]};{pb[1]},{pb[0]}",
                               timeout=TIMEOUT, headers=UA, params={"overview": "false"}) as r:
            d = await r.json(content_type=None)
        leg = d["routes"][0]
        out["road_km"], out["hours"] = leg["distance"] / 1000, leg["duration"] / 3600
    except (aiohttp.ClientError, TimeoutError, KeyError, IndexError, ValueError, TypeError):
        pass
    return out


# ---------- гороскоп ----------
SIGNS = {"овен": "Овен", "телец": "Телец", "близнецы": "Близнецы", "рак": "Рак", "лев": "Лев", "дева": "Дева",
         "весы": "Весы", "скорпион": "Скорпион", "стрелец": "Стрелец", "козерог": "Козерог", "водолей": "Водолей",
         "рыбы": "Рыбы"}
_SIGN_DATES = [((1, 20), "Водолей"), ((2, 19), "Рыбы"), ((3, 21), "Овен"), ((4, 20), "Телец"), ((5, 21), "Близнецы"),
               ((6, 21), "Рак"), ((7, 23), "Лев"), ((8, 23), "Дева"), ((9, 23), "Весы"), ((10, 23), "Скорпион"),
               ((11, 22), "Стрелец"), ((12, 22), "Козерог")]


def sign_for(day: int, month: int) -> str:
    sign = "Козерог"
    for (m, d), name in _SIGN_DATES:
        if (month, day) >= (m, d):
            sign = name
    return sign


def parse_sign(arg: str) -> str | None:
    a = (arg or "").strip().lower()
    if a in SIGNS:
        return SIGNS[a]
    m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})", a)
    if m and 1 <= int(m.group(1)) <= 31 and 1 <= int(m.group(2)) <= 12:
        return sign_for(int(m.group(1)), int(m.group(2)))
    return None
