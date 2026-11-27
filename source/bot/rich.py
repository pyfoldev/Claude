"""Богатые сообщения Telegram (Bot API 10.1+): настоящие таблицы вместо моноширинного текста.
Если Telegram или клиент не принял такое сообщение, вызывающий код получает None и отправляет обычный текст."""
from __future__ import annotations

import logging

from aiogram.types import (InputRichBlockSectionHeading, InputRichBlockTable, InputRichMessage,
                           ReplyParameters, RichBlockTableCell, RichTextBold, RichTextUrl)


def _cell(text, *, header: bool = False, align: str = "left"):
    return RichBlockTableCell(align=align, valign="middle", text=text, is_header=True if header else None)


async def send_table(bot, chat_id: int, title: str, header: list[str], rows: list[list], *, aligns: list[str] | None = None,
                     reply_markup=None, reply_to: int | None = None, thread_id: int | None = None):
    """rows — списки ячеек; ячейка — строка или (текст, ссылка). Возвращает отправленное сообщение или None."""
    aligns = aligns or ["left"] * len(header)

    def conv(v):
        if isinstance(v, tuple):
            return RichTextUrl(text=v[0], url=v[1]) if v[1] else v[0]
        return v

    cells = [[_cell(RichTextBold(text=h), header=True, align=a) for h, a in zip(header, aligns)]]
    cells += [[_cell(conv(v), align=a) for v, a in zip(r, aligns)] for r in rows]
    msg = InputRichMessage(blocks=[
        InputRichBlockSectionHeading(text=title, size=3),
        InputRichBlockTable(cells=cells, is_bordered=True, is_striped=True)])
    try:
        return await bot.send_rich_message(
            chat_id=chat_id, rich_message=msg, reply_markup=reply_markup, message_thread_id=thread_id,
            reply_parameters=ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None)
    except Exception as e:                       # старый сервер/клиент, лимиты — не страшно, будет текстовая таблица
        logging.info("rich table не отправлена: %s", e)
        return None
