# База данных

- Файл: `bot/db.py` (класс `Database`), PostgreSQL-адаптер — `bot/pg.py`, перенос SQLite → PG — `bot/migrate.py`.
- Выбор: `DATABASE_URL=postgresql://…` → PostgreSQL, иначе файл `DB_PATH` (SQLite).
- Список таблиц — строка `SCHEMA` в `db.py`.

## Правила

1. **SQL только в `db.py`.** Хендлеры вызывают методы `db.xxx(...)`.
2. **Параметры через `?`**: `execute("... WHERE chat_id=?", (chat_id,))`. Никаких f-строк со значениями.
3. **После записи — `await self.conn.commit()`**; после `SELECT` не нужно.
4. **Связанные записи — одной транзакцией**: `async with db.atomic(): ...` (деньги, обмены, ставки).
5. **Метод возвращает простые типы** (`int`, `dict`, `list[dict]`), а не курсоры.
6. **Строки как словари**: `dict(row)` или `row["колонка"]`.

## Добавить таблицу / колонку

Пошагово — `templates/db_methods_template.py`:
1. `CREATE TABLE IF NOT EXISTS …` в `SCHEMA` (безопасно выполняется при каждом старте).
2. Для **новой колонки существующей таблицы** — `ALTER TABLE … ADD COLUMN IF NOT EXISTS` в блоке миграций `connect()`.
3. Методы — в раздел `# ---------- <тема> ----------` класса `Database`.

## Настройки чата

`DEFAULT_SETTINGS` (значения по умолчанию) → `await db.get_settings(chat_id)` (кэш 10 с) → `await db.set_setting(chat_id, key, value, actor)`.
Неизвестный ключ → `KeyError`: сначала заведите в `DEFAULT_SETTINGS`.

## Кэши в БД-слое

`_settings_cache`, `_rank_cache`, `_access_cache`, `_user_cache`, `USERNAMES`… — ускоряют частые чтения. Если пишете метод,
который меняет эти данные в обход существующих методов, сбросьте соответствующий кэш (`.pop(chat_id, None)`).

## Статистика сообщений

Сообщения не хранятся — только счётчики: `msg_hourly` (почасовая), `msg_daily` (старше `ROLLUP_DAYS` сворачивается). Запись буферизуется
в памяти и сбрасывается раз в 5 с (`flush_loop`).

## Бэкапы

`backup.py` → цикл «бэкап» в `jobs`; папка `BACKUP_DIR` (по умолчанию `data/backups`), хранится `BACKUP_KEEP` копий (14).
