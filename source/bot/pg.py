"""PostgreSQL-адаптер: даёт asyncpg тот же интерфейс, что aiosqlite (execute/commit/курсор), и переводит
SQLite-диалект запросов Database в PostgreSQL. Публичные методы Database при этом не меняются."""
from __future__ import annotations

import asyncio
import re
import os
from urllib.parse import unquote, urlsplit
from functools import lru_cache
from typing import Any

import asyncpg

AUTOINC_TABLES = {"mod_log", "owner_log", "awards", "notes", "timers", "warn_events", "reports", "filters", "aimod_events", "giveaways", "quotes", "suggestions", "payments", "pairs", "pair_log", "pair_children", "pair_pets", "triggers", "faq", "periodic"}
# для INSERT OR REPLACE: первичный ключ таблицы
REPLACE_KEYS = {"marriages": ("chat_id", "u1", "u2"), "relations": ("chat_id", "u1", "u2")}


def _number_placeholders(sql: str) -> str:
    out, n, quote = [], 0, False
    for ch in sql:
        if ch == "'":
            quote = not quote
        if ch == "?" and not quote:
            n += 1
            out.append(f"${n}")
        else:
            out.append(ch)
    return "".join(out)


@lru_cache(maxsize=1024)
def translate(sql: str) -> tuple[str, bool]:
    """(SQL для PostgreSQL, нужно ли вернуть id вставленной строки)."""
    s = sql.strip().rstrip(";")
    returning = False
    m = re.match(r"INSERT OR IGNORE INTO", s, re.I)
    if m:
        s = "INSERT INTO" + s[m.end():] + " ON CONFLICT DO NOTHING"
    m = re.match(r"INSERT OR REPLACE INTO\s+(\w+)\s*\(([^)]*)\)", s, re.I)
    if m:
        table, cols = m.group(1), [c.strip() for c in m.group(2).split(",")]
        key = REPLACE_KEYS[table]
        upd = ",".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in key)
        s = "INSERT INTO" + s[len("INSERT OR REPLACE INTO"):] + f" ON CONFLICT ({','.join(key)}) DO UPDATE SET {upd}"
    s = re.sub(r"\bRANDOM\(\)", "random()", s, flags=re.I)
    s = s.replace("lower_py(", "lower(")
    m = re.match(r"INSERT INTO\s+(\w+)", s, re.I)
    if m and m.group(1).lower() in AUTOINC_TABLES and "ON CONFLICT" not in s.upper():
        s += " RETURNING id"
        returning = True
    return _number_placeholders(s), returning


def translate_ddl(ddl: str) -> str:
    ddl = ddl.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    return re.sub(r"\bINTEGER\b", "BIGINT", ddl)


class PgRow:
    """Строка, ведущая себя как sqlite3.Row: row["col"], row[0], dict(row), распаковка."""
    __slots__ = ("_keys", "_vals")

    def __init__(self, record: asyncpg.Record):
        self._keys = list(record.keys())
        self._vals = [_norm(v) for v in record.values()]

    def keys(self):
        return self._keys

    def __getitem__(self, k):
        return self._vals[k if isinstance(k, int) else self._keys.index(k)]

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)


def _norm(v: Any) -> Any:
    from decimal import Decimal
    return int(v) if isinstance(v, Decimal) and v == v.to_integral_value() else v


class PgCursor:
    def __init__(self, rows: list[PgRow], rowcount: int, lastrowid: int | None):
        self._rows, self.rowcount, self.lastrowid = rows, rowcount, lastrowid

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return list(self._rows)


class PgConn:
    """Одно соединение, как у SQLite: запросы идут по очереди, транзакция открывается на первой записи
    и закрывается commit(). SELECT вне транзакции не держит её открытой."""

    def __init__(self, conn: asyncpg.Connection, schema: str | None = None):
        self._c = conn
        self._lock = asyncio.Lock()
        self._in_tx = False
        self.schema = schema

    async def execute(self, sql: str, args=()) -> PgCursor:
        pg_sql, returning = translate(sql)
        is_read = bool(re.match(r"\s*(SELECT|WITH)\b", pg_sql, re.I))
        async with self._lock:
            try:
                if not is_read and not self._in_tx:
                    await self._c.execute("BEGIN")
                    self._in_tx = True
                if is_read or returning:
                    recs = await self._c.fetch(pg_sql, *args)
                    rows = [PgRow(r) for r in recs]
                    last = rows[0]["id"] if returning and rows else None
                    return PgCursor(rows, len(rows) if not is_read else -1, last)
                status = await self._c.execute(pg_sql, *args)
                return PgCursor([], int(status.split()[-1]) if status.split()[-1].isdigit() else 0, None)
            except Exception:
                if self._in_tx:  # в PG упавший запрос ломает всю транзакцию — откатываем, как «чистый лист»
                    await self._c.execute("ROLLBACK")
                    self._in_tx = False
                raise

    async def executemany(self, sql: str, args) -> None:
        """Batch writes under the same transaction and lock as execute()."""
        pg_sql, returning = translate(sql)
        if returning:
            raise ValueError("executemany does not support generated IDs")
        async with self._lock:
            try:
                if not self._in_tx:
                    await self._c.execute("BEGIN")
                    self._in_tx = True
                await self._c.executemany(pg_sql, args)
            except BaseException:
                if self._in_tx:
                    await self._c.execute("ROLLBACK")
                    self._in_tx = False
                raise

    async def begin(self) -> None:
        async with self._lock:
            if not self._in_tx:
                self._in_tx = True
                await self._c.execute("BEGIN")

    async def rollback(self) -> None:
        async with self._lock:
            if self._in_tx:
                await self._c.execute("ROLLBACK")
                self._in_tx = False

    async def commit(self) -> None:
        async with self._lock:
            if self._in_tx:
                await self._c.execute("COMMIT")
                self._in_tx = False

    async def executescript(self, script: str) -> None:
        async with self._lock:
            for stmt in (x.strip() for x in translate_ddl(script).split(";")):
                if stmt:
                    await self._c.execute(stmt)

    async def close(self) -> None:
        async with self._lock:
            if self._in_tx:
                await self._c.execute("ROLLBACK")
            if self.schema and not getattr(self, 'schema_keep', False):
                await self._c.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
            await self._c.close()


async def connect(url: str, schema: str | None = None) -> PgConn:
    if schema:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", schema):
            raise ValueError("invalid PostgreSQL schema name")
        boot = await asyncpg.connect(url)
        try:
            await boot.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        finally:
            await boot.close()
        conn = await asyncpg.connect(url, server_settings={"search_path": schema})
    else:
        conn = await asyncpg.connect(url)
    return PgConn(conn, schema)


def _dump_connection(url: str) -> tuple[str, dict]:
    """Keep libpq passwords out of process arguments; other URI options stay literal."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("postgresql", "postgres") or parsed.fragment:
        raise ValueError("PostgreSQL backup requires a valid database URI")
    environment = dict(os.environ)
    netloc = parsed.netloc
    if parsed.password is not None:
        userinfo, host = netloc.rsplit("@", 1)
        netloc = userinfo.split(":", 1)[0] + "@" + host
        environment["PGPASSWORD"] = unquote(parsed.password)
    query = []
    for item in parsed.query.split("&") if parsed.query else []:
        key, _, value = item.partition("=")
        if unquote(key).lower() == "password":
            environment["PGPASSWORD"] = unquote(value)
        else:
            query.append(item)
    clean = f"{parsed.scheme}://{netloc}{parsed.path}"
    if query:
        clean += "?" + "&".join(query)
    return clean, environment


async def pg_dump(url: str, path: str, timeout: float = 300) -> None:
    """Custom-format dump; reap pg_dump on cancellation or timeout."""
    clean_url, environment = _dump_connection(url)
    proc = await asyncio.create_subprocess_exec(
        "pg_dump", "--format=custom", "--file", path, "--dbname", clean_url, env=environment,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        _, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except BaseException:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
        raise
    if proc.returncode != 0:
        raise RuntimeError("pg_dump: " + err.decode(errors="replace")[:200])
