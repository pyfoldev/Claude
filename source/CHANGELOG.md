# Журнал изменений

Формат: новые записи сверху. Что изменилось, в каком файле, нужно ли что-то делать при обновлении.

## [Не выпущено]
### Добавлено
- Комментарии-навигация в `main.py`, `config.py`, `db.py`, `middlewares/*`, `handlers/menu|settings|economy|rp|polls`, `i18n.py`, `ai.py`, `ranks.py`, `toggles.py`, `runtime.py`.
- `templates/` — шаблоны хендлеров, middleware, задач, БД, веб-маршрутов, тестов и др.
- `docs/` — гайды и автогенерируемые справочники; `tools/` — `new_handler.py`, `check_project.py`, `gen_docs.py`; `Makefile`, `tests/test_smoke.py`.
### Изменено
- В `main.py` список роутеров оформлен как `ROUTERS` (один на строку, по группам). Поведение прежнее.
