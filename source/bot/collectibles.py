"""Коллекционные карточки: каталог, шансы выпадения и правила обмена (без Telegram и БД)."""
from __future__ import annotations

import random

COOLDOWN = 12 * 3600
RARITY = [("обычная", "⚪", 60), ("редкая", "🔵", 28), ("эпическая", "🟣", 10), ("легендарная", "🟡", 2)]
RARITY_NAME = [r[0] for r in RARITY]

# серия -> [(эмодзи, название)] ×10; порядок задаёт редкость: 0–4 обычные, 5–7 редкие, 8 эпическая, 9 легендарная
SERIES: dict[str, list[tuple[str, str]]] = {
    "🐾 Животные": [("🦊", "Лиса"), ("🐺", "Волк"), ("🐻", "Медведь"), ("🦉", "Сова"), ("🐬", "Дельфин"),
                    ("🐯", "Тигр"), ("🐼", "Панда"), ("🐘", "Слон"), ("🦅", "Орёл"), ("🦄", "Единорог")],
    "🚀 Космос": [("🌙", "Луна"), ("🪐", "Сатурн"), ("☄️", "Комета"), ("🛰", "Спутник"), ("🔴", "Марс"),
                  ("☀️", "Солнце"), ("🌌", "Туманность"), ("🌠", "Метеорит"), ("🚀", "Ракета"), ("🕳", "Чёрная дыра")],
    "🍔 Еда": [("🍕", "Пицца"), ("🍣", "Суши"), ("🥟", "Пельмени"), ("🍲", "Борщ"), ("🥞", "Блины"),
               ("🍦", "Мороженое"), ("🍰", "Тортик"), ("🍔", "Бургер"), ("🍖", "Шашлык"), ("☕", "Кофе")],
    "🧙 Фэнтези": [("🧝", "Эльф"), ("🧚", "Фея"), ("⚔️", "Рыцарь"), ("🧌", "Тролль"), ("🏰", "Замок"),
                   ("🧙", "Маг"), ("🐉", "Дракон"), ("🦅", "Грифон"), ("🔥", "Феникс"), ("💎", "Кристалл")],
    "🌍 Чудеса света": [("🗼", "Эйфелева башня"), ("🏛", "Колизей"), ("🗽", "Статуя Свободы"), ("🗻", "Фудзи"),
                        ("🌊", "Ниагара"), ("🕌", "Тадж-Махал"), ("🏔", "Эверест"), ("🐪", "Сфинкс"),
                        ("🌋", "Везувий"), ("🌅", "Байкал")],
    "🎮 Игры": [("🎲", "Кубики"), ("🃏", "Джокер"), ("♟", "Шахматы"), ("🎯", "Дартс"), ("🧩", "Пазл"),
                ("🎰", "Слоты"), ("🕹", "Аркада"), ("🎳", "Боулинг"), ("👾", "Инопланетянин"), ("🏆", "Кубок")],
}


def _rarity_of(i: int) -> int:
    return 0 if i < 5 else 1 if i < 8 else 2 if i == 8 else 3


CARDS: dict[int, dict] = {}
for _s, (_title, _items) in enumerate(SERIES.items()):
    for _i, (_emoji, _name) in enumerate(_items):
        _id = _s * 10 + _i + 1
        CARDS[_id] = {"id": _id, "series": _title, "emoji": _emoji, "name": _name, "rarity": _rarity_of(_i)}
TOTAL = len(CARDS)


def label(card_id: int) -> str:
    c = CARDS[card_id]
    return f"{RARITY[c['rarity']][1]} {c['emoji']} {c['name']} #{card_id}"


def draw(rng: random.Random | None = None) -> int:
    """Выпавшая карточка: сначала редкость по шансам, потом случайная карта этой редкости."""
    rng = rng or random.Random()
    roll = rng.uniform(0, sum(w for *_, w in RARITY))
    acc, rarity = 0.0, 0
    for i, (*_, w) in enumerate(RARITY):
        acc += w
        if roll <= acc:
            rarity = i
            break
    return rng.choice([i for i, c in CARDS.items() if c["rarity"] == rarity])


def find(arg: str) -> int | None:
    """Номер или часть названия -> id карточки."""
    a = (arg or "").strip().lower().lstrip("#")
    if a.isdigit():
        return int(a) if int(a) in CARDS else None
    hits = [i for i, c in CARDS.items() if a and a in c["name"].lower()]
    return hits[0] if len(hits) == 1 else None


def series_progress(owned: dict[int, int]) -> list[tuple[str, int, int]]:
    out = []
    for s, (title, items) in enumerate(SERIES.items()):
        have = sum(1 for i in range(len(items)) if owned.get(s * 10 + i + 1, 0) > 0)
        out.append((title, have, len(items)))
    return out


def can_trade(give_owner: dict[int, int], give: int, get_owner: dict[int, int], get: int) -> str | None:
    """None — обмен возможен; иначе причина отказа. Меняются только запасные копии (больше одной)."""
    if give not in CARDS or get not in CARDS:
        return "такой карточки нет"
    if give == get:
        return "обмен одинаковых карточек не нужен"
    if give_owner.get(give, 0) < 2:
        return "у вас нет запасной копии этой карточки"
    if get_owner.get(get, 0) < 2:
        return "у соперника нет запасной копии той карточки"
    return None
