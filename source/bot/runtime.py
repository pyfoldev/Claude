"""Состояние работающего бота: блок-лист, глобальные флаги, запрос на остановку/перезапуск."""
from __future__ import annotations

import asyncio
import time

from bot.db import GLOBAL_DEFAULTS, Database

__all__ = ["Runtime", "GLOBAL_DEFAULTS"]


class Runtime:
    def __init__(self) -> None:
        self.started_at = time.time()
        self.restart = False
        self.stop_requested = False
        self._event = asyncio.Event()
        self.banned_users: set[int] = set()
        self.banned_chats: set[int] = set()
        self.left_chats: set[int] = set()   # из каких забаненных чатов уже вышли
        self.flags = {"ai": True, "stt": True, "nsfw": True, "aimod": True}
        self.maintenance = False

    def flag(self, name: str) -> bool:
        return self.flags.get(name, True)

    def apply_globals(self, g: dict) -> None:
        self.flags = {"ai": bool(g["g_ai"]), "stt": bool(g["g_stt"]), "nsfw": bool(g["g_nsfw"]),
                      "aimod": bool(g.get("g_aimod", 1))}
        self.maintenance = bool(g["maintenance"])

    async def load(self, db: Database) -> None:
        self.banned_users, self.banned_chats = await db.load_bans()
        self.apply_globals(await db.get_global())

    def request_stop(self, restart: bool = False) -> None:
        self.restart = restart
        self.stop_requested = True
        self._event.set()

    async def wait_stop(self) -> None:
        await self._event.wait()
