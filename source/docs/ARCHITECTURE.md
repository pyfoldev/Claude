# Архитектура

## Общая схема

```
Telegram ──(webhook | polling)──► aiogram Dispatcher (main.py)
                                    │
        ┌───────────────────────────┴─── outer-middleware (по порядку) ───────────────────────────┐
        │ Metrics → Block(блок-лист) → UserTracker → Counter → Guard(антиспам/18+) → RateLimit →  │
        │ Rules(правила чата) → QuietTopic → ChatMemory → NoriPrefix(«нори …») → CommandAlias(en) │
        └──────────────────────────────────────────┬──────────────────────────────────────────────┘
                                                   ▼
                        ROUTERS (handlers/*.py) — первый подошедший хендлер отвечает
                                                   │
              ┌────────────────────┬───────────────┴───────────┬──────────────────┐
              ▼                    ▼                           ▼                  ▼
        Database (db.py)     AiClient (ai.py)         ux / style (ответы)   Telegram Bot API
        SQLite | PostgreSQL  River / Mistral / GigaAM

Параллельно: aiohttp-сервер (капча, веб-панель, конкурсы, /webhook) и фоновые задачи (jobs в main.py).
```

## Жизненный цикл запуска (main.py → main())

1. `load_config()` — читает `.env`, проверяет значения (`config.py`).
2. `Database.connect()` — SQLite-файл или PostgreSQL (`DATABASE_URL`); создаёт таблицы из `SCHEMA`, миграции.
3. Создаются `Bot`, `AiClient`, `Runtime`, `Dispatcher`; общие объекты кладутся в `dp[...]` (→ параметры хендлеров).
4. Подключаются middleware, затем роутеры (`ROUTERS`).
5. Поднимается веб-сервер; стартуют фоновые задачи (`jobs`, под присмотром `supervise`).
6. Режим `webhook` (очередь `UpdateQueue` → воркеры) или `polling`.
7. Остановка по сигналу/команде владельца: корректно закрывает БД, сессии, задачи; `restart=True` → перезапуск процесса.

## Карта файлов `bot/`

| Группа | Файлы |
|---|---|
| Запуск и конфиг | `main.py`, `config.py`, `runtime.py`, `alerts.py`, `metrics.py`, `updatequeue.py`, `webhook.py` |
| Хендлеры (команды) | `handlers/*.py` (один файл — один `Router`) |
| Прослойки | `middlewares/*.py` |
| Данные | `db.py`, `pg.py`, `migrate.py`, `backup.py`, `pair/*` (пары, семья, дети, питомцы) |
| Права | `mod_service.py`, `ranks.py`, `toggles.py`, `members.py` |
| Защита | `spam.py`, `raid.py`, `nsfw.py`, `phishing.py`, `cas.py`, `dupes.py`, `guestbots.py`, `filters.py`, `rules.py` |
| ИИ | `ai.py`, `chatmind.py`, `aimod.py`, `imagegen.py` |
| Интерфейс | `ux.py`, `style.py`, `rich_ui.py`, `keyboards.py`, `emoji.py`, `i18n.py`, `i18n_en.py` |
| Игры и развлечения | `games/*`, `mafia.py`, `boardgames.py`, `cards.py`, `rp_data.py`, `gifs.py` |
| Веб | `panel_server.py`, `captcha_server.py`, `giveaway_server.py`, `../webapp/*` |
| Разбор текста | `parsing.py`, `targets.py` |

## Принципы (чтобы код оставался понятным)

- **Команды по-русски, без «/»**: «бан @ник 1д». Разбор — регулярками в самом модуле или в `parsing.py`.
- **Хендлер тонкий**: проверки → вызов сервиса/БД → ответ. SQL — только в `db.py`. Тяжёлая логика — в отдельных модулях (`mod_service.py`, `bot/pair/service.py`).
- **Тишина вместо ошибок**: если текст не похож на команду или нет прав — молча `return`, чтобы бот не мешал болтовне.
- **Кэши — словари с чисткой**: `_last`, `_cool` и т. п. чистятся в `main.rollup_loop` через `prune_stale`.
- **Безопасность**: пользовательский текст в HTML всегда `html.escape`; SQL только через `?`; ответ ИИ — тоже экранируется.
