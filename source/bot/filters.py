"""Стоп-слова и фильтры по регулярным выражениям.

Слова: целое слово без учёта регистра, с «ё/е», латиницей вместо кириллицы, повторами букв и невидимыми символами.
Регулярные выражения: короткие, без вложенных квантификаторов и просмотров, плюс жёсткий таймаут на сопоставление
(библиотека `regex`), чтобы «катастрофический откат» не мог повесить бота."""
from __future__ import annotations

import logging
import re
import time
import unicodedata

import regex

MAX_REGEX_LEN = 200
MAX_WORD_LEN = 64
MAX_FILTERS = 50
MATCH_TIMEOUT = 0.05
MAX_SCAN = 4000

_LOOKALIKE = str.maketrans("aekmhopctxyb", "аекмнорстхув")
_CLEAN = re.compile(r"[\W_]+", re.UNICODE)
_RUNS = re.compile(r"(.)\1+")


class FilterError(ValueError):
    pass


def normalize(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if unicodedata.category(c) not in ("Mn", "Cf"))
    s = s.lower().translate(_LOOKALIKE)
    s = _CLEAN.sub(" ", s)
    s = _RUNS.sub(r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def _strip_classes_and_escapes(p: str) -> str:
    """Убирает [..] и экранированные символы, чтобы проверка скобок/квантификаторов их не путала."""
    out, i, in_class = [], 0, False
    while i < len(p):
        c = p[i]
        if c == "\\":
            i += 2
            out.append("E")
            continue
        if in_class:
            if c == "]":
                in_class = False
            i += 1
            continue
        if c == "[":
            in_class = True
            out.append("C")
        else:
            out.append(c)
        i += 1
    return "".join(out)


def validate_regex(pattern: str) -> None:
    if not pattern or len(pattern) > MAX_REGEX_LEN:
        raise FilterError(f"Выражение должно быть от 1 до {MAX_REGEX_LEN} символов.")
    if re.search(r"\(\?(?:=|!|<=|<!|\(|P=|>)|\\[1-9]", pattern):
        raise FilterError("Просмотры вперёд/назад, условия и обратные ссылки не поддерживаются.")
    try:
        regex.compile(pattern, regex.IGNORECASE)
    except regex.error as e:
        raise FilterError(f"Некорректное выражение: {e}") from e
    flat = _strip_classes_and_escapes(pattern)
    stack: list[int] = []
    for i, c in enumerate(flat):
        if c == "(":
            stack.append(i)
        elif c == ")" and stack:
            start = stack.pop()
            nxt = flat[i + 1] if i + 1 < len(flat) else ""
            if nxt in ("*", "+", "{") and re.search(r"[*+{|]", flat[start + 1:i]):
                raise FilterError("Вложенные повторы и повтор группы с «|» запрещены (риск зависания).")


class FilterSet:
    """Набор фильтров чата: first_match(text) → id сработавшего фильтра или None."""

    def __init__(self, rows: list[dict]):
        self._words: list[tuple[int, str]] = []
        self._regexes: list[tuple[int, regex.Pattern]] = []
        for r in rows:
            if r["kind"] == "word":
                w = normalize(r["pattern"])
                if w:
                    self._words.append((r["id"], f" {w} "))
            else:
                try:
                    self._regexes.append((r["id"], regex.compile(r["pattern"], regex.IGNORECASE)))
                except regex.error:
                    logging.warning("filter %s: сохранённое выражение не компилируется, пропущено", r["id"])

        self._regexes.sort(key=lambda item: item[0])

    def __bool__(self) -> bool:
        return bool(self._words or self._regexes)

    def first_match(self, text: str) -> int | None:
        text = (text or "")[:MAX_SCAN]
        if not text:
            return None
        hits: list[int] = []
        padded = f" {normalize(text)} " if self._words else ""
        for fid, w in self._words:
            if w in padded:
                hits.append(fid)
        best = min(hits) if hits else None
        deadline = time.monotonic() + MATCH_TIMEOUT
        for fid, rx in self._regexes:
            if best is not None and fid >= best:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                if rx.search(text, timeout=remaining):
                    return fid
            except TimeoutError:
                logging.warning("filter %s: таймаут сопоставления", fid)
        return best
