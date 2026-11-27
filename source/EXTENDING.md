# Как расширять и редактировать бота

> Подробные гайды — в [docs/](docs/README.md); шаблоны — в [templates/](templates/README.md); генератор модулей — `python tools/new_handler.py`.

Карта проекта (`source/bot/`):

| Что | Где |
|---|---|
| Запуск, порядок middleware и роутеров, фоновые задачи | `main.py` (размечен секциями 2.1–2.7) |
| Настройки из `.env` | `config.py` + `../.env.example` |
| Команды (хендлеры) | `handlers/*.py` — один файл = один `Router` |
| Прослойки до хендлеров (защита, счётчики, префикс «нори») | `middlewares/*.py` |
| Запросы к БД, настройки чата по умолчанию | `db.py` (`DEFAULT_SETTINGS`) |
| Экран настроек чата | `handlers/settings.py` (`PAGES`) |
| Главное меню и справка по командам | `handlers/menu.py` (`MAIN_ROWS`, `SECTION_DATA`) |
| Английский интерфейс и английские команды | `i18n.py` (`ALIASES`, `PHRASES`, `EXACT`), `i18n_en.py` |
| Оформление сообщений, ответы, реакции | `style.py`, `ux.py` |
| Права и ранги | `mod_service.py` (`effective_rank`), `ranks.py` |
| Веб-панель / капча / конкурсы | `panel_server.py`, `captcha_server.py`, `giveaway_server.py`, `../webapp/` |

## Рецепты (шаблоны в `source/templates/`)

- **Новая команда** → `templates/handler_template.py`: копия в `handlers/<имя>.py`, импорт и `router` в `main.py` (список `ROUTERS`, выше `ai_handlers`).
- **Новая прослойка** → `templates/middleware_template.py`, подключение в `main.py` п. 2.3.
- **Фоновая задача** → `templates/job_template.py`, строка в `jobs` (`main.py` п. 2.6).
- **Новая настройка чата** → `templates/setting_template.md` (3 шага).
- **Общий объект для хендлеров** → `dp["name"] = obj` в `main.py` п. 2.2; в хендлере параметр `name`.
- **Новая переменная окружения** → `config.py` (поле, чтение в `load_config`, проверка) + `.env.example`.
- **Команда в меню «/»** → `bot.set_my_commands(...)` в `main.py`.
- **Строка в справке «меню»** → `SECTION_DATA` в `handlers/menu.py`.
- **Английский перевод** → `PHRASES` / `EXACT` / `ALIASES` в `i18n.py`.
- **Новая таблица БД** → `CREATE TABLE IF NOT EXISTS` в `db.py`; для новых колонок — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` в блоке миграций.

## Важно знать

- Порядок роутеров = приоритет: первый подошедший хендлер обрабатывает сообщение.
- Порядок middleware важен (блок-лист → трекер → счётчик → защита → лимиты → правила → префикс «нори»).
- Тексты ответов — по-русски в коде; в чатах с языком en они переводятся словарём из `i18n.py`.
- Проверка синтаксиса после правок: `python3 -m compileall -q source/bot`.
