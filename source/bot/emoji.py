"""Премиум-эмодзи.

Чтобы подключить свои: впишите custom_emoji_id в PREMIUM_IDS вместо None.
Пока id не заданы, используются обычные эмодзи из FALLBACK.
"""
from __future__ import annotations

from bot.emoji_inject import load_map, norm

FALLBACK = {
    "ban": "🔨", "mute": "🔇", "kick": "👢", "warn": "⚠️", "stats": "📊",
    "game": "🎮", "slots": "🎰", "shield": "🛡", "ok": "✅", "fail": "❌",
    "menu": "📋", "settings": "⚙️", "coin": "🪙", "trophy": "🏆", "duel": "⚔️",
    "unmute": "🔊", "pin": "📌",
}

# Единый источник правды — bot/emoji_map.json (строится из tools/emoji_choices.py): так «именованные» эмодзи
# и автозамена в тексте всегда показывают одну и ту же картинку.
_MAP = load_map()
PREMIUM_IDS: dict[str, str | None] = {name: _MAP.get(norm(ch)) for name, ch in FALLBACK.items()}


def emoji(name: str) -> str:
    base = FALLBACK.get(name)
    if base is None:
        return ""
    pid = PREMIUM_IDS.get(name)
    if pid:
        return f'<tg-emoji emoji-id="{pid}">{base}</tg-emoji>'
    return base
