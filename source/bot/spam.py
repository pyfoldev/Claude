"""Чистая логика антиспама (без Telegram): окна флуда, повторы, ссылки, упоминания, пересылки."""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass

DUP_LIMIT = 3      # столько одинаковых подряд — спам
DUP_WINDOW = 60    # секунд между одинаковыми
DUP_MIN_LEN = 15   # короткие тексты («слоты 10», «бонус») повторами не считаем


@dataclass
class MsgInfo:
    text: str
    links: int
    mentions: int
    forwarded: bool
    group_id: str | None = None  # media_group_id: альбом считаем одним сообщением


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


class SpamGuard:
    def __init__(self) -> None:
        self._times: dict[tuple[int, int], deque[float]] = {}
        self._last: dict[tuple[int, int], tuple[str, int, float]] = {}
        self._album: dict[tuple[int, int], str] = {}

    def prune(self, now: float, max_age: float = 3600) -> None:
        """Забыть тех, кто давно молчит: словари иначе растут по числу участников за всё время работы."""
        for k in [k for k, v in self._times.items() if not v or now - v[-1] > max_age]:
            self._times.pop(k, None)
        for k in [k for k, v in self._last.items() if now - v[2] > max_age]:
            self._last.pop(k, None)
        if len(self._album) > 5000:
            self._album.clear()

    def check(self, chat_id: int, user_id: int, info: MsgInfo, now: float, s: dict,
              newbie: bool) -> str | None:
        key = (chat_id, user_id)
        if info.mentions > s["spam_mentions"]:
            return "массовые упоминания"
        if info.links > 0:
            mode = s["links_mode"]   # off | newbies | all; info.links уже без доменов из белого списка
            if mode == "all":
                return "ссылка не из белого списка"
            if mode == "newbies" and newbie:
                return "ссылка от новичка"
        if newbie and s["spam_forward"] and info.forwarded:
            return "пересылка от новичка"

        if info.group_id and self._album.get(key) == info.group_id:
            return None  # остальные фото того же альбома
        if info.group_id:
            self._album[key] = info.group_id
        if info.forwarded:
            return None  # пачка пересланных сообщений — не флуд (новичков ловит отдельное правило)

        times = self._times.setdefault(key, deque())
        times.append(now)
        while times and now - times[0] >= s["spam_flood_sec"]:
            times.popleft()
        if len(times) >= s["spam_flood_n"]:
            times.clear()
            return "флуд"

        text = _norm(info.text)
        if s["spam_dup"] and len(text) >= DUP_MIN_LEN:
            prev = self._last.get(key)
            if prev and prev[0] == text and now - prev[2] <= DUP_WINDOW:
                count = prev[1] + 1
            else:
                count = 1
            self._last[key] = (text, count, now)
            if count >= DUP_LIMIT:
                self._last.pop(key, None)
                return "повторы"
        return None
