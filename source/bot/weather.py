"""Погода через wttr.in (без ключа)."""
from __future__ import annotations

import re
from urllib.parse import quote

import aiohttp

_CITY_RE = re.compile(r"^[\w .,'-]{2,40}$", re.UNICODE)
FORMAT = "%l: %c %t (ощущается %f), ветер %w, влажность %h"


def valid_city(city: str) -> bool:
    return bool(_CITY_RE.match(city.strip()))


async def fetch_weather(session: aiohttp.ClientSession, city: str, base: str = "https://wttr.in") -> str | None:
    city = city.strip()
    if not valid_city(city):
        return None
    try:
        async with session.get(f"{base}/{quote(city)}", params={"format": FORMAT, "lang": "ru"},
                               timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status != 200:
                return None
            text = (await r.text()).strip()
    except (aiohttp.ClientError, TimeoutError):
        return None
    if not text or "Unknown location" in text or len(text) > 300:
        return None
    return text
