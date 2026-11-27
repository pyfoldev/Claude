"""Автобэкап БД: копия через sqlite backup API, проверка целостности, ротация, оповещение при ошибке."""
import asyncio
import logging
import os
import sqlite3
import time
import secrets
import re
import tempfile
from pathlib import Path
from typing import Awaitable, Callable

PREFIX = "bot-backup-"


class BackupError(Exception):
    pass


async def _check_pg_dump(path: str) -> None:
    proc = await asyncio.create_subprocess_exec("pg_restore", "--list", path,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        _, error = await asyncio.wait_for(proc.communicate(), 60)
    except BaseException:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
        raise
    if proc.returncode != 0:
        raise BackupError("дамп PostgreSQL не читается: " + error.decode(errors="replace")[:150])


def _check_integrity(path: str) -> None:
    try:
        conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
        try:
            res = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as e:
        raise BackupError(f"копия не открывается: {e}") from e
    if not res or res[0] != "ok":
        raise BackupError(f"проверка целостности: {res[0] if res else 'нет ответа'}")


async def make_backup(db, directory: str, now: int | None = None) -> str:
    os.makedirs(directory, mode=0o700, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now if now is not None else time.time()))
    pg = getattr(db, "backend", "sqlite") == "pg"
    path = os.path.join(directory, f"{PREFIX}{ts}-{time.time_ns():020d}-{secrets.token_hex(4)}.{'dump' if pg else 'db'}")
    descriptor, partial = tempfile.mkstemp(prefix=".backup-", suffix=".partial", dir=directory)
    os.close(descriptor)
    try:
        await db.backup_to(partial)
        if pg:
            await _check_pg_dump(partial)
        else:
            await asyncio.to_thread(_check_integrity, partial)
        os.replace(partial, path)  # only validated backups become visible to rotation
    except BaseException:
        if os.path.exists(partial):
            os.remove(partial)
        raise
    return path


def rotate(directory: str, keep: int) -> int:
    pattern = re.compile(r"bot-backup-([0-9]{8}-[0-9]{6})(?:-([0-9]+)-[0-9a-f]+)?\.(?:db|dump)")
    files = []
    with os.scandir(directory) as entries:
        for entry in entries:
            match = pattern.fullmatch(entry.name)
            if match and entry.is_file(follow_symlinks=False):
                files.append(((match[1], int(match[2] or 0)), entry.name))
    files.sort()
    old = files[:-keep] if keep > 0 else files
    for _, name in old:
        os.remove(os.path.join(directory, name))
    return len(old)


async def backup_once(db, directory: str, keep: int, notify: Callable[[str], Awaitable[None]],
                      now: int | None = None) -> bool:
    try:
        await make_backup(db, directory, now=now)
        rotate(directory, keep)
        return True
    except Exception as e:
        logging.exception("backup failed")
        try:
            await notify(f"⚠️ Автоматический бэкап базы не удался: {type(e).__name__}: {e}")
        except Exception:
            logging.exception("backup notify failed")
        return False


async def backup_loop(db, directory: str, keep: int, notify: Callable[[str], Awaitable[None]],
                      interval: int = 86400, first_delay: int = 300) -> None:
    await asyncio.sleep(first_delay)
    while True:
        await backup_once(db, directory, keep, notify)
        await asyncio.sleep(interval)
