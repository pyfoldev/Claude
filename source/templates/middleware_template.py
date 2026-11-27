"""ШАБЛОН MIDDLEWARE — скопируйте в bot/middlewares/<имя>.py.

ПОДКЛЮЧЕНИЕ в bot/main.py (раздел 2.3, ПОРЯДОК ВАЖЕН — выполняются сверху вниз):
    from bot.middlewares.example import ExampleMiddleware
    dp.message.outer_middleware(ExampleMiddleware(db))
Типы: dp.update (всё), dp.message, dp.edited_message, dp.callback_query, dp.chat_member.
"""
from aiogram import BaseMiddleware
from aiogram.types import Message


class ExampleMiddleware(BaseMiddleware):
    def __init__(self, db):                 # зависимости передаются при подключении
        self.db = db

    async def __call__(self, handler, event: Message, data: dict):
        # data — словарь, из которого хендлеры берут параметры: data["bot"], data["db"]...
        if event.from_user is None:
            return await handler(event, data)           # пропустить дальше
        if False:                                       # <-- ваше условие «заблокировать»
            return None                                 # None = сообщение не дойдёт до хендлеров
        data["example_flag"] = True                     # добавить параметр для хендлеров
        return await handler(event, data)
