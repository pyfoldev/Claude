"""Ссылки в сообщениях: извлечение доменов и проверка по белому списку чата."""
from __future__ import annotations

import re
from urllib.parse import urlparse

_TLDS = r"(?:com|ru|org|net|io|me|su|xyz|top|site)"
_RE = re.compile(
    r"https?://(?P<h1>[^\s/?#]+)"
    r"|(?P<h2>www\.[^\s/?#]+)"
    r"|(?<![@\w.\-])(?P<h3>(?:[\w\-]+\.)+" + _TLDS + r")\b",
    re.IGNORECASE)


def normalize_domain(raw: str) -> str | None:
    """«https://www.Example.com/a» → «example.com»; «*.x.org» сохраняется; мусор → None."""
    s = (raw or "").strip().lower()
    if not s or " " in s:
        return None
    wildcard = s.startswith("*.")
    if wildcard:
        s = s[2:]
    if "://" in s:
        try:
            s = urlparse(s).netloc
        except ValueError:
            return None
    s = s.split("/")[0].split("?")[0].split("#")[0]
    s = s.rsplit("@", 1)[-1].split(":")[0].strip(".,;:!?)(\"'«»")
    if s.startswith("www."):
        s = s[4:]
    if "." not in s or s.startswith(".") or ".." in s:
        return None
    try:
        s = s.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    if len(s) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in s.split(".")):
        return None
    return ("*." if wildcard else "") + s


def extract_hosts(text: str, entities) -> set[str]:
    hosts: set[str] = set()
    for e in entities or []:
        if e.type == "text_link" and e.url:
            d = normalize_domain(e.url)
        elif e.type == "url":
            d = normalize_domain(e.extract_from(text))
        else:
            continue
        if d:
            hosts.add(d)
    for m in _RE.finditer(text or ""):
        d = normalize_domain(m.group("h1") or m.group("h2") or m.group("h3"))
        if d:
            hosts.add(d)
    return hosts


def host_allowed(host: str, allow: set[str]) -> bool:
    """Точное совпадение; поддомены — только если в списке явно «*.домен» (он же разрешает и сам домен)."""
    if host in allow:
        return True
    parts = host.split(".")
    return any("*." + ".".join(parts[i:]) in allow for i in range(len(parts) - 1))
