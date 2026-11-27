# Рецепты «хочу сделать X»

| Хочу | Что делать |
|---|---|
| Изменить текст ответа бота | найдите фразу: `grep -rn "кусок текста" bot/` и правьте строку; перевод — `i18n.py` |
| Изменить баланс игры (награды, кулдауны) | константы вверху `handlers/economy.py`, `db.py` (`START_BALANCE`, `BONUS_AMOUNT`), `games/*.py` |
| Добавить РП-действие | строка в `rp_data.py` (формат — в шапке файла) |
| Добавить команду в справку «меню» | `handlers/menu.py` → `SECTION_DATA` |
| Новая кнопка в главном меню | `menu.py` → `MAIN_ROWS` + запись в `SECTION_DATA` |
| Изменить приветствие в личке | `menu.py` → `onboarding_screen` |
| Поменять имя бота в обращении («нори») | `middlewares/prefix.py` → `_RE`; `main.py` → `BotCommand`; тексты `menu.py` |
| Новая настройка чата | `templates/setting_template.md` |
| Включатель группы команд | `templates/toggle_group_template.py` |
| Ограничить команду рангом | `ranks.DEFAULT_ACCESS` + `need_rank` (`templates/admin_command_template.py`) |
| Новая таблица / запрос | `templates/db_methods_template.py` |
| Новая фоновая задача | `templates/job_template.py` → `jobs` в `main.py` |
| Новая переменная `.env` | `config.py` (поле + `load_config`) и `.env.example` |
| Новый API-метод для панели | `templates/web_route_template.py` |
| Поменять лимиты антиспама по умолчанию | `db.py` → `DEFAULT_SETTINGS` (`spam_*`), логика — `spam.py` |
| Поменять лимит команд в секунду | `middlewares/ratelimit.py` (`PER_SEC`, `PER_MIN`) |
| Поменять промпт ИИ | `ai.py`, `chatmind.py`, `handlers/ai.py` |
| Поменять стиль/эмодзи сообщений | `style.py`, `emoji.py`, `emoji_map.json` |
| Скрыть/выключить функцию для всех | флаги владельца (`rt.flags`) или не подключайте роутер в `ROUTERS` |
| Добавить язык интерфейса | по образцу `i18n.py` + словарь `i18n_xx.py`, ветка в `TranslateMiddleware` |
| Поменять срок хранения статистики | `db.py` → `ROLLUP_DAYS` (+ `prune_old`) |
