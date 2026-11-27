"""ШАБЛОН: автотест (pytest). Кладите в source/tests/test_<имя>.py. Запуск: `make test` или `pytest -q`.

Что тестировать в первую очередь: ЧИСТЫЕ функции разбора (parse, парсеры команд) — они быстрые и без Telegram.
Для БД используйте временный файл SQLite:  db = await Database.connect(str(tmp_path / "t.db")).
"""
import pytest

from bot.handlers.economy import parse        # ← ваша функция


def test_parse_farm():
    assert parse("ферма") == ("farm", ())


def test_parse_not_a_command():
    assert parse("привет всем") is None          # обычная болтовня не должна считаться командой


@pytest.mark.asyncio
async def test_db_example(tmp_path):
    from bot.db import Database
    db = await Database.connect(str(tmp_path / "t.db"))
    try:
        assert await db.get_balance(1, 1) >= 0
    finally:
        await db.close()
