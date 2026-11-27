# Инструменты (`tools/`) и `Makefile`

| Команда | Что делает |
|---|---|
| `python tools/new_handler.py имя --kind text\|target\|economy\|ai\|menu\|confirm\|admin\|toggle` | создаёт `handlers/имя.py` из шаблона и подключает роутер в `main.py`; `--dry-run` — показать без записи |
| `python tools/check_project.py` | проверки целостности проекта (код выхода 1 при ошибках) |
| `python tools/gen_docs.py` | генерирует `docs/COMMANDS.md`, `SETTINGS.md`, `ROUTERS.md`, `DB_TABLES.md`, `ENV.md` |
| `make check` / `make docs` / `make test` / `make run` / `make pyz` / `make new NAME=pets KIND=economy` | то же короче |

Генератор ставит роутер в конец списка, но **выше блока ИИ** (якорь `>>> СЮДА добавляйте свой роутер` в `main.py` — не удаляйте его).
Для `--kind toggle` дополнительно заведите ключ в `toggles.GROUPS` и `DEFAULT_SETTINGS` (см. комментарий в шаблоне).
