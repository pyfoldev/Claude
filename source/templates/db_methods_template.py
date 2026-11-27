"""ШАБЛОН: новая таблица и методы БД. Это НЕ отдельный файл проекта — код вставляется в bot/db.py.

ШАГ 1. Таблица — в строку SCHEMA (bot/db.py, ~строка 81), в конец:

    CREATE TABLE IF NOT EXISTS notes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,      -- для PostgreSQL это приводится автоматически (bot/pg.py)
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        ts INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_notes_chat ON notes(chat_id, ts);

ШАГ 2 (если таблица УЖЕ есть и нужна новая колонка) — в блок миграций connect(), рядом с другими ALTER:
    await conn.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS pinned INTEGER DEFAULT 0")
(для SQLite смотрите, как сделано рядом с CHILD_COLS: колонку добавляют, только если её нет.)

ШАГ 3. Методы — в класс Database, под своим разделом «# ---------- заметки ----------».
"""

# --- вставьте МЕТОДЫ (всё, что внутри class ниже) в class Database; обёртка нужна только чтобы файл был валидным Python ---
class Database:

    # ---------- заметки ----------
    async def note_add(self, chat_id: int, user_id: int, text: str, ts: int) -> int:
        """Добавить заметку, вернуть её номер."""
        cur = await self.conn.execute(
            "INSERT INTO notes(chat_id,user_id,text,ts) VALUES(?,?,?,?)", (chat_id, user_id, text, ts))
        await self.conn.commit()                    # commit после ЗАПИСИ обязателен; после SELECT — нет
        return cur.lastrowid

    async def note_list(self, chat_id: int, limit: int = 10) -> list[dict]:
        cur = await self.conn.execute(
            "SELECT id,user_id,text,ts FROM notes WHERE chat_id=? ORDER BY ts DESC LIMIT ?", (chat_id, limit))
        return [dict(r) for r in await cur.fetchall()]     # строки доступны по имени колонки: r["text"]

    async def note_delete(self, chat_id: int, note_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM notes WHERE chat_id=? AND id=?", (chat_id, note_id))
        await self.conn.commit()
        return cur.rowcount == 1                    # True — удалили ровно одну

# ПРАВИЛА: SQL только с `?` и кортежем параметров (никаких f-строк со значениями — SQL-инъекции!);
# в хендлерах SQL не пишем; несколько связанных записей — `async with self.atomic():`.
