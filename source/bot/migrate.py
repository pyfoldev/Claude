"""Перенос данных из файла SQLite в PostgreSQL с проверкой числа строк по каждой таблице."""
from __future__ import annotations

import re
import sqlite3

from bot.db import Database
from bot.pg import AUTOINC_TABLES


class MigrationError(Exception):
    pass


async def migrate(sqlite_path: str, pg_url: str, schema: str | None = None, keep_schema: bool = False) -> dict:
    """Возвращает {таблица: (строк в SQLite, строк в PostgreSQL)}. Цель должна быть пустой.
    keep_schema — только для тестов: не удалять схему при закрытии."""
    src = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    try:
        dst = await Database.connect(pg_url, schema=schema)
    except BaseException:
        src.close()
        raise
    if keep_schema:
        dst.conn.schema_keep = True
    try:
        tables = [r[0] for r in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        pg_tables = {r["tablename"] for r in await (await dst.conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname=current_schema()")).fetchall()}
        tables = [t for t in tables if t in pg_tables and t != "schema_migrations"]
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", t) for t in tables):
            raise MigrationError("недопустимое имя таблицы")
        for t in tables:
            n = (await (await dst.conn.execute(f"SELECT COUNT(*) AS n FROM {t}")).fetchone())["n"]
            if n:
                raise MigrationError(f"таблица {t} в PostgreSQL не пуста ({n} строк): перенос только в пустую базу")
        report: dict[str, tuple[int, int]] = {}
        raw = dst.conn._c
        async with dst.conn._lock:
            await raw.execute("BEGIN")
            try:
                for t in tables:
                    cols = [r[1] for r in src.execute(f"PRAGMA table_info({t})")]
                    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", c) for c in cols):
                        raise MigrationError(f"недопустимое имя столбца в {t}")
                    cursor = src.execute(f"SELECT {','.join(cols)} FROM {t}")
                    count = 0
                    while rows := cursor.fetchmany(1000):
                        batch = [tuple(r) for r in rows]
                        await raw.copy_records_to_table(t, records=batch, columns=cols)
                        count += len(batch)
                    if t in AUTOINC_TABLES:
                        await raw.execute(
                            f"SELECT setval(pg_get_serial_sequence('{t}','id'), COALESCE((SELECT MAX(id) FROM {t}), 0)+1, false)")
                    got = await raw.fetchval(f"SELECT COUNT(*) FROM {t}")
                    report[t] = (count, got)
                if any(a != b for a, b in report.values()):
                    raise MigrationError(f"число строк не совпало: { {t: v for t, v in report.items() if v[0] != v[1]} }")
                await raw.execute(
                    "INSERT INTO payment_receipts(charge_id,ts) "
                    "SELECT charge_id,MIN(ts) FROM payments WHERE charge_id IS NOT NULL GROUP BY charge_id "
                    "ON CONFLICT DO NOTHING")
                await raw.execute("COMMIT")
            except BaseException:
                await raw.execute("ROLLBACK")
                raise
        return report
    finally:
        src.close()
        if keep_schema:
            await dst.conn._c.close()
        else:
            await dst.close()
