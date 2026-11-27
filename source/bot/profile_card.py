"""Карточка участника по команде «репутация [@ник]»: репутация, активность и «досье» — варны, действующие наказания,
число наказаний и жалоб. Досье видят модераторы (право «история»); остальным показывается только репутация и варны."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from bot import style
from bot import mod_service as ms
from bot.ranks import need_rank
from bot.targets import mention


def _tz(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


async def build(bot, db, chat: int, uid: int, name: str, viewer: int, now: int | None = None) -> str:
    now = int(time.time()) if now is None else now
    cfg = await db.get_settings(chat)
    tz = _tz(cfg["tz"])
    is_mod = await ms.effective_rank(bot, db, chat, viewer) >= need_rank(await db.get_access(chat), "история")
    rep = await db.get_rep(chat, uid)
    warns = await db.get_warns(chat, uid, now)
    limit = cfg["warn_limit"]
    lines = [style.head("⭐", f"Репутация {mention(uid, name)}", None), "",
             style.kv("Репутация", rep),
             f"Предупреждения: <b>{warns}/{limit}</b> {style.bar(warns, limit)}"]
    msgs = await db.user_total(chat, uid, None)
    if msgs:
        lines.append(style.kv("Сообщений", msgs))
    if not is_mod:
        return "\n".join(lines)
    now_states = []
    for kind, label in (("ban", "бан"), ("mute", "мут")):
        st = await db.get_state(chat, uid, kind, now)
        if st:
            left = "бессрочно" if st["until"] is None else "до " + datetime.fromtimestamp(st["until"], tz).strftime("%d.%m %H:%M")
            now_states.append(f"{label} {left}")
    total = await db.count_mod_history(chat, uid)
    reports_total, reports_open = await db.count_reports_against(chat, uid)
    lines += ["", style.head("🗂", "Досье", "видно модераторам"),
              "⚡️ Сейчас: " + ("; ".join(now_states) if now_states else "без наказаний"),
              style.kv("Наказаний за всё время", total)]
    if reports_total:
        lines.append(f"📣 Жалоб: <b>{reports_total}</b> (открытых {reports_open})")
    last = await db.list_mod_history(chat, uid, 3, 0) if total else []
    for r in last:
        what = r["action"] + (f" · {r['reason']}" if r["reason"] else "")
        lines.append(f"• {datetime.fromtimestamp(r['ts'], tz).strftime('%d.%m %H:%M')} — {what}")
    if total:
        lines.append(f"<i>Все записи: <code>история {uid}</code></i>")
    return "\n".join(lines)
