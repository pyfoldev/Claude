"""Премиум пары за Telegram Stars: 30 дней, один платёж на пару. Бонусы: +10% тепла, 5 питомцев, 48 ч на примирение, значок 💎."""
PRICE = 150
PERIOD = 30 * 86400
PAYLOAD_PREFIX = "pairprem:"
WARMTH_PCT = 10
PETS_MAX = 5
QUARREL_HOURS = 48
BADGE = "💎"


def payload(pid: int) -> str:
    return f"{PAYLOAD_PREFIX}{pid}"


def parse_payload(text: str) -> int | None:
    if not isinstance(text, str) or not text.startswith(PAYLOAD_PREFIX):
        return None
    raw = text[len(PAYLOAD_PREFIX):]
    if not raw or not raw.isascii() or not raw.isdigit() or len(raw) > 19:
        return None
    value = int(raw)
    return value if 0 < value < 2**63 else None


def active(p: dict, now: int) -> bool:
    return bool(p) and (p.get("premium_until") or 0) > now


def boost(warmth: int, p: dict, now: int) -> int:
    return warmth + warmth * WARMTH_PCT // 100 if active(p, now) else warmth
