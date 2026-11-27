"""Оформление сообщений: цитаты для длинного и моноширинные таблицы (в Telegram нет настоящих таблиц)."""
from __future__ import annotations

import html

_ELLIPSIS = "…"
MAX_PRE = 3500   # запас до лимита 4096 с учётом остального текста сообщения


class Html(str):
    """Уже готовый HTML (например, ссылка-упоминание): pre_table и kv_table вставляют его как есть, не экранируя и не обрезая."""


def esc(value) -> str:
    if isinstance(value, Html):
        return str(value)
    return html.escape(str(value if value is not None else ""))


def escaped_clip(text: str, max_html: int, max_utf16: int | None = None) -> str:
    """Экранировать и ограничить текст, не обрывая HTML-сущности или символы."""
    parts, html_len, utf16_len = [], 0, 0
    for char in str(text):
        piece = html.escape(char)
        units = 2 if ord(char) > 0xFFFF else 1
        if html_len + len(piece) > max_html or (max_utf16 is not None and utf16_len + units > max_utf16):
            break
        parts.append(piece)
        html_len += len(piece)
        utf16_len += units
    return "".join(parts)


def quote(body_html: str, expandable: bool | None = None) -> str:
    """Цитата вокруг УЖЕ экранированного HTML. Длинное (>300 символов или от 5 строк) сворачивается."""
    if expandable is None:
        expandable = len(body_html) > 300 or body_html.count("\n") >= 4
    open_tag = "<blockquote expandable>" if expandable else "<blockquote>"
    return f"{open_tag}{body_html}</blockquote>"      # закрывающий тег без атрибута — иначе Telegram: «Unclosed end tag»


def _cut(text, width: int) -> str:
    if isinstance(text, Html):
        return text
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: max(width - 1, 1)] + _ELLIPSIS


def _lines_block(lines: list[str], quoted: bool = True) -> str:
    """Строки внутри цитаты (quoted=False — обычным текстом); сворачиваем только действительно длинное."""
    body = "\n".join(lines)
    while len(body) > MAX_PRE and len(lines) > 1:   # слишком длинный список: режем хвост
        lines = lines[:-1]
        body = "\n".join(lines)
    return quote(body, expandable=len(lines) > 14 or len(body) > 1200) if quoted else body


def pre_table(rows: list[tuple], header: tuple | None = None, align: str = "", maxw: int | tuple = 22,
              gap: int = 2, quoted: bool = True) -> str:
    """«Таблица» цитатой: на телефонах моноширинные блоки ломают выравнивание (кириллица, эмодзи), поэтому
    строки выводятся читаемым списком: «1. Имя — значение · значение». Колонка «#»/«№» превращается в нумерацию,
    при 4+ колонках сверху идёт строка-подсказка. Значения экранируются здесь; align и gap оставлены для совместимости."""
    if not rows:
        return ""
    ncols = len(rows[0])
    caps = list(maxw) if isinstance(maxw, (tuple, list)) else [maxw] * ncols
    caps = [c * 2 for c in caps]                      # в цитате текст переносится — режем мягче
    numbered = bool(header) and header[0] in ("#", "№")
    lines = []
    if header and len([h for h in header if h not in ("#", "№")]) >= 4:
        names = [h for h in header if h not in ("#", "№")]
        lines.append(f"<i>{esc(names[0])} — " + esc(" · ".join(n.lower() for n in names[1:])) + "</i>")
    for r in rows:
        cells = [esc(_cut(c, caps[i])) for i, c in enumerate(r)]
        if numbered:
            head, rest = f"{cells[0]}. {cells[1]}", cells[2:]
        else:
            head, rest = cells[0], cells[1:]
        lines.append(head + (" — " + " · ".join(c for c in rest if c) if any(rest) else ""))
    return _lines_block(lines, quoted)


def kv_table(pairs: list[tuple[str, object]], key_width: int = 14, value_width: int = 24) -> str:
    """Пары «параметр: значение» цитатой."""
    return _lines_block([f"<b>{esc(_cut(k, key_width * 2))}:</b> {esc(_cut(v, value_width * 2))}" for k, v in pairs])
