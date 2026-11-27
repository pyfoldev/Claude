"""Кого предлагать к массовому исключению (чистая логика)."""
from __future__ import annotations

MAX_KICK = 200


def activity(m: dict, last_msg: dict[int, int] | None) -> tuple[int | None, bool]:
    """(когда человек был активен, писал ли он вообще). Активность — его собственные сообщения; нет сообщений — отсчёт
    идёт от входа в чат (или от первой встречи ботом). Упоминания и ответы ему активностью не считаются."""
    if last_msg is not None and m["user_id"] in last_msg:
        return last_msg[m["user_id"]], True
    return (m.get("joined_at") or m.get("first_seen")), False


def pick_candidates(kind: str, members: list[dict], writers: set[int], now: int, period: int,
                    exclude: set[int], last_msg: dict[int, int] | None = None) -> list[int]:
    """kind: 'неактив' — не появлялись дольше period; 'новичков' — вошли за последние period (рейд);
    'молчунов' — давно в чате, но не написали ни одного сообщения."""
    out = []
    for m in members:
        uid = m["user_id"]
        if uid in exclude:
            continue
        if kind == "неактив":
            if last_msg is not None:                       # по сообщениям: молчун тоже неактивен, считая от входа
                ts, _ = activity(m, last_msg)
                ok = ts is not None and now - ts > period
            else:
                ok = m["last_seen"] is not None and now - m["last_seen"] > period
        elif kind == "новичков":
            ok = m["joined_at"] is not None and now - m["joined_at"] < period
        else:  # молчунов
            since = m["joined_at"] or m["first_seen"]
            ok = uid not in writers and since is not None and now - since > period
        if ok:
            out.append(uid)
    return out[:MAX_KICK]
