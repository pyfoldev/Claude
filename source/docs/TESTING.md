# Тесты и проверки

## Быстрая проверка без зависимостей
```bash
python tools/check_project.py    # синтаксис, подключение роутеров, ключи настроек, ранги, .env.example
python tools/gen_docs.py         # перегенерировать справочники docs/*.md
```
Или `make check`.

## Автотесты (pytest)
Зависимости разработки: `pip install -r requirements.lock pytest pytest-asyncio`. Запуск: `make test` (= `pytest -q`).
Тесты лежат в `tests/`; шаблон — `templates/test_template.py`. `tests/test_smoke.py` проверяет, что проект не развалился
(без сети и Telegram).

Что стоит покрывать:
1. Парсеры команд (`parse`, `parse_rp`, `parsing.py`) — чистые функции, быстро.
2. Методы БД на временном файле SQLite.
3. Расчёты (кулдауны, формулы игр) — выносите их в чистые функции.

`pytest.ini`/настройки — в `pyproject.toml` (`asyncio_mode = "auto"`).

## Ручная проверка новой команды
1. Запустить `MODE=polling python -m bot.main` на тестовом боте.
2. Проверить: нужные права / без прав, личка / группа, пустой аргумент, длинный ввод, спецсимволы `<>&`.
3. `python tools/check_project.py`.
