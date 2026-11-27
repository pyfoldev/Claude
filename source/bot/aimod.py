"""ИИ-модерация: разбор структурированного ответа модели, предфильтр (экономия денег) и кэш вердиктов.

Текст сообщения для модели — данные, а не инструкции: ответ жёстко валидируется (JSON, известная категория,
уверенность 0..1, короткое пояснение без управляющих символов), всё лишнее отбрасывается, а действие выбирает
только код бота."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import OrderedDict
from dataclasses import dataclass

from bot.links import extract_hosts

CATEGORIES = {"ok", "spam", "scam", "insult", "threat", "ads", "adult"}
CATEGORY_RU = {"spam": "спам", "scam": "мошенничество", "insult": "оскорбления", "threat": "угрозы",
               "ads": "реклама", "adult": "18+ текст"}
MIN_LEN, MAX_LEN = 15, 1500
_SUSPICIOUS = re.compile(
    r"заработ|инвест|крипт|казино|ставк|бонус|бесплатн|розыгрыш|подпиши|переходи|в\s*лс|в\s*личку|"
    r"раздач|схема|быстр\w*\s+деньг|прибыл|удалённ\w*\s+работ|набор|вакансия|18\+|интим|проститут|"
    r"наркот|закладк|кредит|займ|выигр|акци[яи]\b", re.IGNORECASE)
_JSON = re.compile(r"\{.*?\}", re.DOTALL)


@dataclass(frozen=True)
class ModResult:
    category: str
    confidence: float
    explain: str


def parse_moderation(raw: str | None) -> ModResult | None:
    if not raw:
        return None
    for m in _JSON.finditer(raw):
        try:
            data = json.loads(m.group(0))
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        cat = data.get("category")
        conf = data.get("confidence")
        if not isinstance(cat, str) or cat not in CATEGORIES or isinstance(conf, bool) or not isinstance(conf, (int, float)):
            continue
        conf = float(conf)
        if not math.isfinite(conf) or not 0 <= conf <= 100:
            continue
        if conf > 1:
            conf /= 100
        explain = data.get("explain", "")
        explain = re.sub(r"[\x00-\x1f\x7f]+", " ", explain if isinstance(explain, str) else "").strip()[:100]
        return ModResult(cat, round(conf, 2), explain)
    return None


def prefilter(text: str, newbie: bool, mode: str) -> bool:
    """Стоит ли тратить запрос к ИИ. newbies — все сообщения новичков; all — ещё и подозрительные от остальных."""
    if mode not in ("newbies", "all") or not (MIN_LEN <= len(text) <= MAX_LEN):
        return False
    if newbie:
        return True
    if mode != "all":
        return False
    if _SUSPICIOUS.search(text) or extract_hosts(text, []):
        return True
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 20 and sum(c.isupper() for c in letters) / len(letters) > 0.7   # КРИК


class Cache:
    """Вердикты для одинакового текста и одинакового контекста модели."""

    def __init__(self, max_size: int = 2000):
        self.max_size = max_size
        self._d: OrderedDict[str, ModResult] = OrderedDict()

    @staticmethod
    def key(text: str, context: str | None = None) -> str:
        payload = json.dumps([text, context], ensure_ascii=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, text: str, context: str | None = None) -> ModResult | None:
        k = self.key(text, context)
        if k in self._d:
            self._d.move_to_end(k)
            return self._d[k]
        return None

    def put(self, text: str, res: ModResult, context: str | None = None) -> None:
        k = self.key(text, context)
        self._d[k] = res
        self._d.move_to_end(k)
        while len(self._d) > self.max_size:
            self._d.popitem(last=False)

    def __len__(self) -> int:
        return len(self._d)
