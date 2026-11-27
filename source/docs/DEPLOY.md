# Развёртывание

## Что нужно
Docker + Docker Compose, домен с HTTPS (для Mini App и webhook), токен бота (@BotFather).

## Быстрый старт
```bash
cp .env.example .env          # заполните BOT_TOKEN, OWNER_ID, WEBAPP_URL, WEBHOOK_SECRET (для webhook)
docker compose up -d --build  # bot + caddy
docker compose logs -f bot
```
Сборка образа: `Dockerfile` копирует `bot.pyz` — одиночный архив приложения (в архиве есть `__main__.py`, который распаковывает себя в кэш). Собрать его можно командой `make pyz` (`python -m zipapp`); если у вас своя сборка — используйте её. Папки `docs/`, `tests/`, `templates/`, `tools/` для работы бота не нужны.

## Режимы
| MODE | Когда | Что нужно |
|---|---|---|
| `polling` | локально, без домена | только токен; капча-веб на `PORT` |
| `webhook` | прод | `WEBAPP_URL`/`WEBHOOK_URL` (HTTPS, порт 443/80/88/8443), `WEBHOOK_SECRET` 16–256 символов `A-Za-z0-9_-`; `UPDATE_WORKERS` |

## PostgreSQL
`docker compose --profile pg up -d`, в `.env`: `POSTGRES_PASSWORD=…`, `DATABASE_URL=postgresql://chat:ПАРОЛЬ@postgres:5432/chat`.
Перенос данных SQLite → PG: `bot/migrate.py`.

## Данные и бэкапы
Всё лежит в `./data` (в контейнере `/data`): `bot.db`, `backups/`, `gifs/`. Бэкапы — автоматически (`BACKUP_KEEP`, `BACKUP_DIR`).
Восстановление: остановить бота, подложить файл бэкапа вместо `bot.db`, запустить.

## Обновление
`git pull && docker compose up -d --build`. Схема БД обновляется сама при старте (`CREATE … IF NOT EXISTS` + миграции).

## Безопасность контейнера
`no-new-privileges`, `cap_drop: ALL`, порт бота слушает только `127.0.0.1` — наружу выходит Caddy.

## Caddy
`Caddyfile`: замените домен на свой. Telegram принимает webhook только на портах 443, 80, 88, 8443.
