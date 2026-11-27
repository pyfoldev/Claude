"""Фишинговые ссылки: локальная эвристика по домену (без внешних запросов) и необязательная сверка с Google Safe Browsing.

Локально ловим: домены в punycode (xn-- — подмена букв), голые IP-адреса, «двойников» известных сервисов
(telegram-premium.xyz, sberbank-login.top), дешёвые зоны вместе со словами-приманками (free, gift, airdrop, verify…).
Белый список чата проверяется до этого (links.host_allowed). Safe Browsing включается ключом SAFE_BROWSING_KEY в .env;
тогда адреса ссылок из сообщений уходят в Google — это указано в настройках раздела."""
from __future__ import annotations

import ipaddress
import logging
import os
import time
import unicodedata

# бренд -> официальные домены; всё остальное с таким словом в имени — подозрительно
BRANDS = {
    "telegram": {"telegram.org", "telegram.me", "t.me", "telegra.ph", "telesco.pe"},
    "whatsapp": {"whatsapp.com", "wa.me"},
    "instagram": {"instagram.com"}, "facebook": {"facebook.com", "fb.com"},
    "vkontakte": {"vk.com", "vk.ru"}, "gosuslugi": {"gosuslugi.ru"},
    "sberbank": {"sberbank.ru", "sber.ru"}, "tinkoff": {"tinkoff.ru", "tbank.ru"},
    "binance": {"binance.com"}, "paypal": {"paypal.com"}, "apple": {"apple.com", "icloud.com"},
    "google": {"google.com", "google.ru", "goo.gl"}, "steam": {"steampowered.com", "steamcommunity.com"},
    "discord": {"discord.com", "discord.gg"}, "avito": {"avito.ru"}, "wildberries": {"wildberries.ru"},
}
CHEAP_TLDS = {"tk", "ml", "ga", "cf", "gq", "zip", "mov", "click", "top", "xyz", "icu", "cfd", "sbs", "buzz", "monster"}
BAIT = ("free", "gift", "giveaway", "airdrop", "claim", "bonus", "prize", "verify", "login", "secure", "wallet",
        "support", "premium", "nft", "reward", "unlock", "bot-", "-bot", "tg-", "-tg")


def _registrable(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


_LOOKALIKE = set("асеорхуіјԁԛѕһӏ")      # кириллица, неотличимая от латиницы


def _homoglyph(labels: list[str]) -> str | None:
    """Метка с буквами двух алфавитов или целиком из «двойников» латиницы в домене с латинской зоной — подмена."""
    ascii_tld = not labels[-1].startswith("xn--")
    for lb in labels[:-1] if len(labels) > 1 else labels:
        if not lb.startswith("xn--"):
            continue
        try:
            u = lb.encode("ascii").decode("idna")
        except UnicodeError:
            return "домен с подменой символов (punycode)"
        letters = [c for c in u if c.isalpha()]
        scripts = {unicodedata.name(c, "").split(" ")[0] for c in letters}
        latin = "LATIN" in scripts
        other = bool(scripts & {"CYRILLIC", "GREEK", "ARMENIAN"})     # ü, é, ñ — это всё ещё латиница
        if latin and other:
            return "домен со смешанными алфавитами"
        if ascii_tld and letters and all(c in _LOOKALIKE for c in letters):
            return "домен из букв-двойников латиницы"
    return None


def assess(host: str) -> str | None:
    """Причина, если домен похож на фишинг; иначе None. host — уже в нижнем регистре и punycode (links.normalize_domain)."""
    host = host.lstrip("*.").lower()
    try:
        ipaddress.ip_address(host)
        return "ссылка на IP-адрес"
    except ValueError:
        pass
    labels = host.split(".")
    if any(lb.startswith("xn--") for lb in labels):
        reason = _homoglyph(labels)                   # честные .рф и кириллические домены не трогаем
        if reason:
            return reason
    reg = _registrable(host)
    name = host.replace(".", "-")
    for brand, official in BRANDS.items():
        if brand in name and reg not in official and not any(host.endswith("." + o) for o in official):
            return f"подделка под «{brand}»"
    tld = labels[-1]
    bait = [w for w in BAIT if w in host]
    if tld in CHEAP_TLDS and bait:
        return f"подозрительный домен ({bait[0]})"
    if len(bait) >= 2 and host.count("-") >= 2:
        return "подозрительный домен"
    return None


def assess_many(hosts) -> str | None:
    for h in sorted(hosts):
        r = assess(h)
        if r:
            return r
    return None


_cache: dict[str, tuple[float, bool]] = {}
CACHE_TTL = 3600


async def safe_browsing(session, urls: list[str], key: str | None = None) -> bool:
    """True — Google Safe Browsing считает хотя бы одну ссылку опасной. Ошибки и отсутствие ключа — False."""
    key = key or os.environ.get("SAFE_BROWSING_KEY", "")
    if not key or not urls:
        return False
    now = time.time()
    fresh = [u for u in urls if u not in _cache or now - _cache[u][0] > CACHE_TTL]
    for u in urls:
        if u in _cache and now - _cache[u][0] <= CACHE_TTL and _cache[u][1]:
            return True
    if not fresh:
        return False
    # Не помечаем непроверенные ссылки безопасными: API получает пачки по 20.
    fresh = list(dict.fromkeys(fresh))
    for start in range(0, len(fresh), 20):
        batch = fresh[start:start + 20]
        body = {"client": {"clientId": "chat-helper", "clientVersion": "1"},
                "threatInfo": {"threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
                               "platformTypes": ["ANY_PLATFORM"], "threatEntryTypes": ["URL"],
                               "threatEntries": [{"url": u} for u in batch]}}
        try:
            async with session.post("https://safebrowsing.googleapis.com/v4/threatMatches:find",
                                    params={"key": key}, json=body, timeout=5) as r:
                if r.status != 200:
                    return False
                data = await r.json()
            bad = {m["threat"]["url"] for m in data.get("matches", [])}
        except Exception as e:
            logging.info("safe browsing: %s", e)
            return False
        if len(_cache) + len(batch) > 5000:
            _cache.clear()
        for u in batch:
            _cache[u] = (now, u in bad)
        if bad:
            return True
    return False
