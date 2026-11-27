"""ШАБЛОН: свой фильтр aiogram — условие срабатывания хендлера вынесено в класс.

Использование:   @router.message(IsModerator(min_rank=2), F.text == "команда")
Параметры фильтра (bot, db…) подставляются так же, как в хендлере.
Образец в проекте: bot/toggles.py → Enabled.
"""
from aiogram.filters import Filter
from aiogram.types import Message

from bot import mod_service as ms


class IsModerator(Filter):
    def __init__(self, min_rank: int = 1):
        self.min_rank = min_rank

    async def __call__(self, message: Message, bot, db) -> bool:
        if message.from_user is None or message.chat.type not in ("group", "supergroup"):
            return False
        return await ms.effective_rank(bot, db, message.chat.id, message.from_user.id) >= self.min_rank
