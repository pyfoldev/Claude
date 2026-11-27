"""ШАБЛОН ФОНОВОЙ ЗАДАЧИ — функция живёт в вашем модуле (например handlers/example.py).

ПОДКЛЮЧЕНИЕ в bot/main.py, словарь jobs (раздел 2.6), одна строка:
    "моя задача": lambda: example_handlers.example_watchdog(bot, db),
Если цикл упадёт — supervise() перезапустит его и сообщит владельцам.
"""
import asyncio
import logging
import time

INTERVAL_SEC = 300      # как часто просыпаться


async def example_watchdog(bot, db) -> None:
    while True:
        await asyncio.sleep(INTERVAL_SEC)
        try:
            now = int(time.time())
            # ... найти что пора сделать и сделать (bot.send_message, db.… ) ...
        except Exception:
            logging.exception("example watchdog failed")   # одна ошибка не должна убивать цикл
