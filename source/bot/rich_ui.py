"""Экраны в стиле rich-сообщений Telegram: заголовок, текст, таблица команд и кнопки-«таблетки» по центру внутри самого
сообщения (с премиум-эмодзи в кнопках), а не отдельной клавиатурой под ним.

Один экран (Screen) умеет показываться двумя способами:
  • rich — настоящее rich-сообщение (Bot API 10.1+): блоки heading / paragraph / table / buttons;
  • classic — обычное сообщение с HTML-текстом и inline-клавиатурой (если Telegram или клиент rich не принял).
Выбор автоматический: сначала пробуем rich, при отказе помним об этом 10 минут и отвечаем обычным сообщением.

При нажатии кнопки `show` всегда правит сообщение на месте (rich, а если нельзя — обычным текстом)."""
from __future__ import annotations

import html
import logging
import os
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup, InputRichBlockButtons, InputRichBlockDivider,
                           InputRichBlockFooter, InputRichBlockParagraph, InputRichBlockSectionHeading,
                           InputRichBlockTable, InputRichMessage, ReplyParameters, RichBlockTableCell,
                           RichMessageButton, RichTextBold, RichTextCode, RichTextCustomEmoji, RichTextItalic,
                           RichTextUnderline, RichTextUrl, WebAppInfo)

from bot import emoji_inject

# RICH_UI в .env: hybrid (по умолчанию) — rich-текст и таблицы + обычные inline-кнопки под ними (премиум-иконки на кнопках,
# правка на месте); 1 — кнопки-таблетки внутри rich-сообщения; 0 — только обычные сообщения без rich.
MODE = os.environ.get("RICH_UI", "hybrid").lower()
ENABLED = MODE != "0"
PILLS = MODE == "1"
# В группах Telegram вырезает премиум-эмодзи при ЛЮБОЙ правке rich-сообщения (в личке — нет; проверено пробой), поэтому в группах
# экраны показываются обычными сообщениями (премиум-эмодзи остаются, правка на месте работает). RICH_IN_GROUPS=1 вернёт rich и туда.
RICH_IN_GROUPS = os.environ.get("RICH_IN_GROUPS", "0") == "1"
_off_until = 0.0                         # rich недоступен — до этого момента не пробуем (секунды, time.time)
OFF_FOR = 600
MAX_ROW = 8                              # в одном блоке buttons — до 8 кнопок
_emap: dict | None = None
_use_html = os.environ.get("RICH_FORM", "html") != "blocks"      # html | blocks — в какой форме слать rich


def _has_custom_emoji(obj) -> bool:
    """Есть ли в rich-сообщении (модель или словарь) узлы custom_emoji."""
    try:
        data = obj.model_dump(exclude_none=True) if hasattr(obj, "model_dump") else obj
    except Exception:
        return True
    stack = [data]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            if x.get("type") == "custom_emoji":
                return True
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
    return False


def _map() -> dict:
    global _emap
    if _emap is None:
        _emap = emoji_inject.load_map()
    return _emap


@dataclass
class Btn:
    """Кнопка экрана. Ровно одно из cb / url / web_app. style: primary | success | danger | link."""
    text: str
    cb: str | None = None
    url: str | None = None
    web_app: str | None = None
    style: str | None = None


@dataclass
class Screen:
    """title — заголовок; body — элементы: строка (абзац, мини-HTML: <b> <i> <code> <a>), ("table", [строки]) где строка —
    (команда, описание) или текст, ("rows", header, rows) — таблица из колонок, "---" — разделитель;
    rows — ряды кнопок; footer — мелкая подпись внизу; classic — готовый HTML для обычного сообщения (если нужен
    свой вид вместо автоматического)."""
    title: str | None = None
    body: list = field(default_factory=list)
    rows: list[list[Btn]] = field(default_factory=list)
    footer: str | None = None
    classic: str | None = None
    classic_rows: list | None = None         # другой набор кнопок для обычного сообщения (если нужен иной порядок)
    quote: bool = False                      # весь текст экрана одной цитатой; длинные абзацы и так сворачиваются в цитату


# ---------- мини-HTML → rich text ----------
class _P(HTMLParser):
    def __init__(self, convert_emoji: bool):
        super().__init__(convert_charrefs=True)
        self.root: list = []
        self.stack: list[tuple[str, list, dict]] = []
        self.cur = self.root
        self.convert_emoji = convert_emoji
        self._skip_emoji_text = 0

    def handle_starttag(self, tag, attrs):
        tag = {"strong": "b", "em": "i"}.get(tag, tag)
        if tag in ("b", "strong", "i", "em", "code", "u", "a", "tg-emoji"):
            self.stack.append((tag, self.cur, dict(attrs)))
            self.cur = []

    def handle_endtag(self, tag):
        if tag == "strong":
            tag = "b"
        if tag == "em":
            tag = "i"
        if not self.stack or self.stack[-1][0] != tag:
            return
        t, parent, attrs = self.stack.pop()
        inner = _simplify(self.cur)
        self.cur = parent
        if t == "b":
            node = RichTextBold(text=inner)
        elif t == "i":
            node = RichTextItalic(text=inner)
        elif t == "code":
            node = RichTextCode(text=inner)
        elif t == "u":
            node = RichTextUnderline(text=inner)
        elif t == "a":
            href = attrs.get("href") or ""
            node = RichTextUrl(text=inner, url=href) if href else inner
        else:                                   # tg-emoji: <tg-emoji emoji-id="..">🛡</tg-emoji>
            cid = attrs.get("emoji-id")
            alt = inner if isinstance(inner, str) else "•"
            node = RichTextCustomEmoji(custom_emoji_id=cid, alternative_text=alt) if cid else inner
        self.cur.append(node)

    def handle_data(self, data):
        if not data:
            return
        inside_code = any(s[0] == "code" for s in self.stack)
        if self.convert_emoji and not inside_code and not any(s[0] == "tg-emoji" for s in self.stack):
            self.cur.extend(_split_emoji(data))
        else:
            self.cur.append(data)


def _split_emoji(text: str) -> list:
    """Известные эмодзи → премиум-эмодзи (как в обычных сообщениях через emoji_inject), остальное — текст."""
    emap = _map()
    if not emap:
        return [text]
    out, buf, i, budget = [], [], 0, 12
    while i < len(text):
        hit = emoji_inject._emoji_at(text, i, emap) if budget > 0 else None
        if hit:
            frag, cid, n = hit
            if buf:
                out.append("".join(buf))
                buf = []
            out.append(RichTextCustomEmoji(custom_emoji_id=cid, alternative_text=frag))
            budget -= 1
            i += n
        else:
            buf.append(text[i])
            i += 1
    if buf:
        out.append("".join(buf))
    return out


def _simplify(parts: list):
    parts = [p for p in parts if p != ""]
    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else parts


def rich_text(html_text: str, convert_emoji: bool = True):
    """'<b>Привет</b> 🛡 мир' → RichText (строка, узлы или список узлов)."""
    p = _P(convert_emoji)
    p.feed(html_text or "")
    p.close()
    while p.stack:                              # незакрытые теги закрываем, чтобы не потерять текст
        p.handle_endtag(p.stack[-1][0])
    return _simplify(p.root)


# ---------- кнопки ----------
def _btn_text(text: str):
    """Ведущий эмодзи кнопки → премиум-эмодзи (как иконка слева на скриншотах)."""
    text = html.unescape(text)
    emap = _map()
    hit = emoji_inject._emoji_at(text, 0, emap) if emap and text else None
    if hit:
        frag, cid, n = hit
        rest = text[n:].lstrip()
        return [RichTextCustomEmoji(custom_emoji_id=cid, alternative_text=frag), " " + rest] if rest else \
            RichTextCustomEmoji(custom_emoji_id=cid, alternative_text=frag)
    return text


def _rich_button(b: Btn) -> RichMessageButton:
    kw = {"text": _btn_text(b.text), "style": b.style}
    if b.url:
        kw["url"] = b.url
    elif b.web_app:
        kw["web_app"] = WebAppInfo(url=b.web_app)
    else:
        kw["callback_data"] = b.cb or "noop"
    return RichMessageButton(**kw)


def _classic_button(b: Btn) -> InlineKeyboardButton:
    kw = {"text": b.text, "style": b.style if b.style in ("primary", "success", "danger") else None}
    if b.url:
        kw["url"] = b.url
    elif b.web_app:
        kw["web_app"] = WebAppInfo(url=b.web_app)
    else:
        kw["callback_data"] = b.cb or "noop"
    return InlineKeyboardButton(**kw)


# ---------- рендеры ----------
def _cell(text, header: bool = False):
    return RichBlockTableCell(align="left", valign="middle", text=text, is_header=True if header else None)


def to_rich(s: Screen) -> InputRichMessage:
    blocks: list = []
    if s.title:
        blocks.append(InputRichBlockSectionHeading(text=rich_text(s.title), size=3))
    for item in s.body:
        if item == "---":
            blocks.append(InputRichBlockDivider())
        elif isinstance(item, str):
            blocks.append(InputRichBlockParagraph(text=rich_text(item)))
        elif item[0] == "table":                 # строки «команда — описание»: одна колонка, команда кодом, описание курсивом
            cells = []
            for row in item[1]:
                if isinstance(row, (tuple, list)):
                    cmd, desc = row
                    cells.append([_cell([RichTextCode(text=cmd), " — ", RichTextItalic(text=rich_text(desc))])])
                else:
                    cells.append([_cell(rich_text(row))])
            blocks.append(InputRichBlockTable(cells=cells, is_bordered=True, is_compact=True))
        elif item[0] == "rows":                  # настоящая таблица из колонок
            _, header, rows = item
            cells = [[_cell(RichTextBold(text=h), True) for h in header]] + [[_cell(rich_text(str(c))) for c in r] for r in rows]
            blocks.append(InputRichBlockTable(cells=cells, is_bordered=True, is_striped=True))
    for row in s.rows:
        for i in range(0, len(row), MAX_ROW):
            blocks.append(InputRichBlockButtons(buttons=[_rich_button(b) for b in row[i:i + MAX_ROW]], align="center"))
    if s.footer:
        blocks.append(InputRichBlockFooter(text=rich_text(s.footer)))
    return InputRichMessage(blocks=blocks)


def _h(text: str) -> str:
    """Мини-HTML экрана → HTML rich-сообщения: известные эмодзи заменяются на <tg-emoji> (как в обычных сообщениях)."""
    return emoji_inject.inject_html(text, _map()) if _map() else text


def _attr(v: str) -> str:
    return html.escape(v, quote=True)


def _button_html(b: Btn) -> str:
    label = html.escape(html.unescape(b.text))
    hit = emoji_inject._emoji_at(b.text, 0, _map()) if _map() and b.text else None
    if hit:
        frag, cid, n = hit
        rest = html.escape(html.unescape(b.text[n:].strip()))
        label = f'<tg-emoji emoji-id="{cid}">{html.escape(frag)}</tg-emoji>' + (f" {rest}" if rest else "")
    style = f' style="{b.style}"' if b.style else ""
    if b.url:
        return f'<tg-button type="url"{style} url="{_attr(b.url)}">{label}</tg-button>'
    if b.web_app:
        return f'<tg-button type="web_app"{style} url="{_attr(b.web_app)}">{label}</tg-button>'
    return f'<tg-button type="callback_data"{style} data="{_attr(b.cb or "noop")}">{label}</tg-button>'


LONG_PARA = 250          # абзац длиннее (без разметки) сворачивается в раскрывающуюся цитату


def _plain_len(text: str) -> int:
    return len(re.sub(r"<[^>]+>", "", text))


def _br(text: str) -> str:
    return text.replace("\n", "<br>")


def to_rich_html(s: Screen) -> InputRichMessage:
    """Тот же экран в HTML-форме rich-сообщения (<h3>, <p>, <blockquote>, <table>, <tg-button-row>). Эта форма идёт тем же путём,
    что и обычные сообщения с <tg-emoji>, поэтому премиум-эмодзи сохраняются и при правке на месте."""
    out: list[str] = []
    quoted: list[str] = []

    def flush() -> None:
        if quoted:
            out.append("<blockquote>" + "<br>".join(quoted) + "</blockquote>")
            quoted.clear()

    if s.title:
        out.append(f"<h3>{_h(s.title)}</h3>")
    for item in s.body:
        if item == "---":
            flush()
            out.append("<hr>")
        elif isinstance(item, str):
            if s.quote:
                quoted.append(_br(_h(item)))
            elif _plain_len(item) > LONG_PARA:
                out.append(f"<blockquote expandable>{_br(_h(item))}</blockquote>")
            else:
                out.append(f"<p>{_h(item)}</p>")
        elif item[0] == "table":
            flush()
            rows = []
            for row in item[1]:
                cell = f"<code>{html.escape(row[0])}</code> — <i>{_h(row[1])}</i>" if isinstance(row, (tuple, list)) else _h(row)
                rows.append(f"<tr><td>{cell}</td></tr>")
            out.append(f"<table bordered compact>{''.join(rows)}</table>")
        elif item[0] == "rows":
            flush()
            _, header, rows = item
            head = "".join(f"<th>{html.escape(h)}</th>" for h in header)
            body = "".join("<tr>" + "".join(f"<td>{_h(str(c))}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f"<table bordered striped><tr>{head}</tr>{body}</table>")
    flush()
    for row in s.rows:
        for i in range(0, len(row), MAX_ROW):
            out.append('<tg-button-row align="center">' + "".join(_button_html(b) for b in row[i:i + MAX_ROW]) + "</tg-button-row>")
    if s.footer:
        out.append(f"<footer>{_h(s.footer)}</footer>")
    return InputRichMessage(html="\n".join(out))


def _body_only(s: Screen) -> Screen:
    return Screen(s.title, s.body, [], s.footer)


def to_payload(s: Screen, html_form: bool | None = None) -> InputRichMessage:
    """Какую форму rich отправлять сейчас: HTML (по умолчанию) или блоки (если Telegram не принял HTML-разметку кнопок).
    В hybrid-режиме кнопок внутри нет — они идут обычной inline-клавиатурой (to_markup)."""
    if not PILLS:
        s = _body_only(s)
    return to_rich_html(s) if (_use_html if html_form is None else html_form) else to_rich(s)


def _rich_allowed(chat_id: int) -> bool:
    """rich — в личке всегда; в группах (id < 0) только если RICH_IN_GROUPS=1."""
    return ENABLED and (chat_id > 0 or RICH_IN_GROUPS)


def _emoji_lost(rich: InputRichMessage, res) -> bool:
    """Мы отправили премиум-эмодзи, а в ответе Telegram на правку их нет. Ответ без rich_message (True) — не знаем, не считаем потерей."""
    if res is None or isinstance(res, bool) or getattr(res, "rich_message", None) is None:
        return False
    sent = "<tg-emoji" in (rich.html or "") or _has_custom_emoji(rich)
    return sent and not _has_custom_emoji(res.rich_message)


def _forms() -> tuple:
    """Формы rich для попыток: HTML (сохраняет премиум-эмодзи), а при отказе — блоки только для ЭТОГО запроса.
    Глобально на блоки не переключаемся: одна ошибка (сеть, лишнее поле) раньше навсегда убивала премиум-эмодзи."""
    return (True, False) if _use_html else (False, True)


def to_markup(s: Screen):
    """Inline-клавиатура экрана в hybrid-режиме (в режиме таблеток — None: кнопки уже внутри сообщения)."""
    return None if PILLS else to_classic(s)[1]


def to_classic(s: Screen) -> tuple[str, InlineKeyboardMarkup | None]:
    """Тот же экран обычным сообщением: HTML-текст + inline-клавиатура."""
    brows = s.classic_rows if s.classic_rows is not None else s.rows
    if s.classic is not None:
        kb = InlineKeyboardMarkup(inline_keyboard=[[_classic_button(b) for b in row] for row in brows]) if brows else None
        return s.classic, kb
    lines: list[str] = []
    if s.title:
        lines.append(f"<b>{s.title}</b>")
    quoted: list[str] = []

    def flush() -> None:
        if quoted:
            lines.append("<blockquote>" + "\n".join(quoted) + "</blockquote>")
            quoted.clear()

    for item in s.body:
        if item == "---":
            flush()
            lines.append("")
        elif isinstance(item, str):
            if s.quote:
                quoted.append(item)
            elif _plain_len(item) > LONG_PARA:
                lines.append(f"<blockquote expandable>{item}</blockquote>")
            else:
                lines.append(item)
        elif item[0] == "table":
            flush()
            for row in item[1]:
                lines.append(f"<code>{html.escape(row[0])}</code> — <i>{row[1]}</i>" if isinstance(row, (tuple, list)) else row)
        elif item[0] == "rows":
            flush()
            _, header, rows = item
            lines.extend(" · ".join(str(c) for c in r) for r in rows)
    flush()
    if s.footer:
        lines.append(f"<i>{s.footer}</i>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[_classic_button(b) for b in row] for row in brows]) if brows else None
    return "\n".join(lines), kb


# ---------- отправка ----------
async def send(bot, chat_id: int, s: Screen, *, thread_id: int | None = None, reply_to: int | None = None):
    """Показывает экран: rich, а если не вышло — обычным сообщением. Возвращает отправленное сообщение."""
    global _off_until
    reply = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
    if _rich_allowed(chat_id) and time.time() >= _off_until:
        forms = _forms()
        for form in forms:
            try:
                return await bot.send_rich_message(chat_id=chat_id, rich_message=to_payload(s, form), reply_markup=to_markup(s),
                                                   message_thread_id=thread_id, reply_parameters=reply)
            except Exception as e:
                if form is not forms[-1]:                 # HTML-форма не принята — этот экран пробуем блоками
                    logging.warning("rich в HTML-форме не принят (%s) — пробую блоки", e)
                    continue
                logging.info("rich-экран не отправлен, шлю обычным сообщением: %s", e)
                _off_until = time.time() + OFF_FOR
                break
    text, kb = to_classic(s)
    return await bot.send_message(chat_id, text, reply_markup=kb, message_thread_id=thread_id, reply_parameters=reply,
                                  disable_web_page_preview=True)


async def show(cb, s: Screen) -> None:
    """Переход по кнопке — ВСЕГДА правим сообщение на месте, не удаляя и не присылая новое.
    1) rich-правка (editMessageText + rich_message); 2) обычная правка текста с inline-клавиатурой.
    Новое сообщение + удаление старого — только в крайнем случае: старое rich-сообщение, которое Telegram
    отказывается превращать в обычное, а rich-правка не проходит."""
    msg = cb.message
    if msg is None:
        return
    bot = cb.bot
    is_rich = getattr(msg, "rich_message", None) is not None
    if _rich_allowed(msg.chat.id) and (is_rich or time.time() >= _off_until):
        forms = _forms()
        for form in forms:
            try:
                rich = to_payload(s, form)
                # parse_mode / превью явно None: иначе aiogram подставляет их из DefaultBotProperties, а вместе
                # с rich_message Telegram такую правку отклоняет — и бот уходил в «новое сообщение + удаление старого»
                res = await bot.edit_message_text(chat_id=msg.chat.id, message_id=msg.message_id, rich_message=rich,
                                                  reply_markup=to_markup(s), parse_mode=None, link_preview_options=None,
                                                  disable_web_page_preview=None)
                if _emoji_lost(rich, res):                  # Telegram принял правку, но убрал премиум-эмодзи — повторов не делаем
                    logging.warning("правка rich потеряла премиум-эмодзи (чат %s); ответ Telegram: %s", msg.chat.id,
                                    str(getattr(res, "rich_message", res))[:200])
                return
            except TelegramBadRequest as e:
                if "not modified" in str(e).lower():
                    return
                if form is not forms[-1]:                   # HTML-форма не принята — этот экран пробуем блоками
                    logging.warning("rich-правка в HTML-форме не удалась (%s) — пробую блоки", e)
                    continue
                logging.warning("rich-правка не удалась (%s) — правлю обычным текстом", e)
                break
            except Exception as e:
                logging.warning("rich-правка не удалась (%s) — правлю обычным текстом", e)
                break
    text, kb = to_classic(s)
    try:
        await msg.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        return
    except Exception as e:
        if "not modified" in str(e).lower():
            return
        logging.warning("правка обычным текстом не удалась (%s) — шлю новый экран вместо старого", e)
    # крайний случай: старое сообщение нельзя ни так, ни так отредактировать
    try:
        thread = msg.message_thread_id if getattr(msg, "is_topic_message", False) else None
        sent = await send(bot, msg.chat.id, s, thread_id=thread)
        if sent is not None:
            await msg.delete()
    except Exception:
        pass


def kb(rows: list[list[Btn]]) -> InlineKeyboardMarkup:
    """Обычная inline-клавиатура из рядов Btn (для коротких сообщений-вопросов)."""
    return InlineKeyboardMarkup(inline_keyboard=[[_classic_button(b) for b in row] for row in rows])
