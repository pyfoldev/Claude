"""Единый стиль текстов бота: заголовки, статусы, подписи. Все новые и переработанные сообщения собираются отсюда,
чтобы бот выглядел одинаково: «эмодзи + жирный заголовок», пояснение курсивом, статусы ✅ / ⚠️ / ❌."""
from __future__ import annotations

import html


# ВСЕ тексты бота лучше собирать этими функциями — единый вид. Пример:
#     style.head("🎲", "Игра", "подсказка") + "\n" + style.kv("Ставка", 50) + "\n" + style.ok("Готово")
def head(icon: str, title: str, hint: str | None = None) -> str:
    """🛡 <b>Заголовок</b> + (необязательно) короткая строка пояснения курсивом."""
    return f"{icon} <b>{title}</b>" + (f"\n<i>{hint}</i>" if hint else "")


def ok(text: str) -> str:
    return f"✅ {text}"


def warn(text: str) -> str:
    return f"⚠️ {text}"


def fail(text: str) -> str:
    return f"❌ {text}"


def kv(label: str, value) -> str:
    """Строка «подпись: значение» — подпись приглушена, значение жирным."""
    return f"{label}: <b>{html.escape(str(value))}</b>"


def bar(n: int, limit: int) -> str:
    """Шкала ▰▰▱ — прогресс/лимит."""
    limit = max(limit, 1)
    n = max(0, min(n, limit))
    return "▰" * n + "▱" * (limit - n)


def dur(seconds: int | None) -> str:
    """Срок по-русски: «2 дн.», «3 ч.», «15 мин.»."""
    if not seconds:
        return "навсегда"
    if seconds % 86400 == 0:
        return f"{seconds // 86400} дн."
    if seconds % 3600 == 0:
        return f"{seconds // 3600} ч."
    return f"{max(seconds // 60, 1)} мин."
