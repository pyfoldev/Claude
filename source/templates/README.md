# Шаблоны (templates/)

Копируйте файл, переименовывайте `example` → своё имя, подключайте по инструкции в шапке файла.
Файлы `*.py` корректны синтаксически (проверяет `python tools/check_project.py`), но НЕ импортируются ботом.
Быстрее всего — сгенерировать заготовку: `python tools/new_handler.py имя` (см. docs/TOOLS.md).

| Шаблон | Что делает |
|---|---|
| `handler_template.py` | Текстовая команда + слэш-команда + кнопка |
| `command_with_target_template.py` | Команда «действие @ник / ответом» с проверкой цели и кулдауном |
| `economy_command_template.py` | Команда с монетами: ставка, списание, награда, атомарная транзакция |
| `ai_command_template.py` | Команда «ии …» / вызов нейросети с проверкой ключа и ошибок |
| `inline_menu_template.py` | Меню на inline-кнопках: страницы, «назад», проверка «кнопку нажал тот, кто вызвал» |
| `confirm_dialog_template.py` | Подтверждение «Да/Нет» перед опасным действием |
| `admin_command_template.py` | Команда только для модераторов с рангом и ДК + запись в журнал |
| `toggle_group_template.py` | Группа команд, которую админ чата включает/выключает |
| `custom_filter_template.py` | Свой фильтр aiogram (условие срабатывания хендлера) |
| `db_methods_template.py` | Таблица + методы БД (SQL, миграция колонки) |
| `job_template.py` | Фоновая задача «раз в N минут» |
| `middleware_template.py` | Прослойка до хендлеров |
| `web_route_template.py` | HTTP-маршрут в веб-сервере (aiohttp) |
| `rp_action_template.py` | Как добавить РП-действие |
| `i18n_template.py` | Как добавить английский перевод и английскую команду |
| `test_template.py` | Автотест (pytest) для вашей функции |
| `setting_template.md` | Новая настройка чата (3 шага) |
| `env_variable_template.md` | Новая переменная окружения (5 шагов) |
| `new_feature_checklist.md` | Чек-лист «ничего не забыл» |
