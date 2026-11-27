"""Семья: браки, отношения, дети (усыновление). Правила и хранение; без Telegram."""
from __future__ import annotations

import time
import uuid

from bot.db import DAY, Database
from bot.pair import economy as eco
from bot.pair.service import PairService, partner_of

MAX_CHILDREN = 5
MAX_PARENTS = 2
BONUS_BASE = 300
BONUS_PER_CHILD = 100
REQUEST_TTL = 600


def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


class Family:
    def __init__(self, db: Database):
        self.db = db
        self.pairs = PairService(db)

    async def _all(self, sql: str, args: tuple) -> list:
        cur = await self.db.conn.execute(sql, args)
        return await cur.fetchall()

    # ---------- чтение ----------
    async def spouse(self, chat: int, u: int) -> dict | None:
        p = await self.pairs.get(chat, u)
        if p and p["stage"] == "marriage":
            return {"partner": partner_of(p, u), "since": p["created"]}
        return None

    async def partner(self, chat: int, u: int) -> dict | None:
        p = await self.pairs.get(chat, u)
        if p and p["stage"] == "relation":
            return {"partner": partner_of(p, u), "since": p["created"]}
        return None

    async def parents_of(self, chat: int, child: int) -> list[int]:
        rows = await self._all("SELECT parent FROM parents WHERE chat_id=? AND child=? ORDER BY since, parent",
                               (chat, child))
        return [r["parent"] for r in rows]

    async def children_of(self, chat: int, parent: int) -> list[int]:
        rows = await self._all("SELECT child FROM parents WHERE chat_id=? AND parent=? ORDER BY since, child",
                               (chat, parent))
        return [r["child"] for r in rows]

    async def siblings_of(self, chat: int, u: int) -> set[int]:
        out: set[int] = set()
        for p in await self.parents_of(chat, u):
            out |= set(await self.children_of(chat, p))
        out.discard(u)
        return out

    async def ancestors(self, chat: int, u: int, depth: int = 8) -> set[int]:
        seen: set[int] = set()
        frontier = {u}
        for _ in range(depth):
            nxt: set[int] = set()
            for x in frontier:
                nxt |= set(await self.parents_of(chat, x))
            nxt -= seen
            if not nxt:
                break
            seen |= nxt
            frontier = nxt
        return seen

    async def _kin(self, chat: int, a: int, b: int) -> bool:
        return (b in await self.ancestors(chat, a) or a in await self.ancestors(chat, b)
                or b in await self.siblings_of(chat, a))

    async def view(self, chat: int, u: int) -> dict:
        return {
            "spouse": await self.spouse(chat, u), "partner": await self.partner(chat, u),
            "parents": await self.parents_of(chat, u), "children": await self.children_of(chat, u),
            "siblings": await self.siblings_of(chat, u),
        }

    # ---------- проверки (None — можно, иначе текст отказа) ----------
    async def check_marry(self, chat: int, a: int, b: int) -> str | None:
        """Брак — следующий этап пары: сначала отношения, и паре нужен 3 уровень (его набирают действиями)."""
        if a == b:
            return "Сам с собой? Выберите другого человека."
        if await self._kin(chat, a, b):
            return "Нельзя заключить брак с родственником."
        pa = await self.pairs.get(chat, a)
        if pa is None:
            return "Сначала начните отношения: «отношения @ник». Брак — следующий этап пары."
        if partner_of(pa, a) != b:
            return "Сначала завершите свои отношения (расстаться)." if pa["stage"] == "relation" else "Вы уже в браке."
        if pa["stage"] == "marriage":
            return "Вы уже в браке."
        if pa["level"] < eco.MARRIAGE_MIN_LEVEL:
            return (f"Для брака паре нужен {eco.MARRIAGE_MIN_LEVEL} уровень (сейчас {pa['level']}): "
                    "растите тепло — «пара действия».")
        return None

    async def check_relation(self, chat: int, a: int, b: int) -> str | None:
        if a == b:
            return "Сам с собой? Выберите другого человека."
        pa, pb = await self.pairs.get(chat, a), await self.pairs.get(chat, b)
        if pa:
            return "Вы состоите в браке." if pa["stage"] == "marriage" else "У вас уже есть пара (расстаться — чтобы завершить)."
        if pb:
            return "Этот человек состоит в браке." if pb["stage"] == "marriage" else "У этого человека уже есть пара."
        if await self._kin(chat, a, b):
            return "Нельзя встречаться с родственником."
        return None

    async def check_adopt(self, chat: int, parent: int, child: int) -> str | None:
        if parent == child:
            return "Себя усыновить нельзя."
        if child in await self.children_of(chat, parent):
            return "Это уже ваш ребёнок."
        if await self.spouse(chat, child):
            return "Нельзя усыновить человека, состоящего в браке."
        for rel in (await self.spouse(chat, parent), await self.partner(chat, parent)):
            if rel and rel["partner"] == child:
                return "Нельзя усыновить своего супруга или партнёра."
        if child in await self.ancestors(chat, parent):
            return "Нельзя усыновить своего родителя или предка."
        if child in await self.siblings_of(chat, parent):
            return "Нельзя усыновить брата или сестру."
        if len(await self.parents_of(chat, child)) >= MAX_PARENTS:
            return "У этого человека уже есть два родителя."
        if len(await self.children_of(chat, parent)) >= MAX_CHILDREN:
            return f"Больше {MAX_CHILDREN} детей быть не может."
        return None

    # ---------- изменения ----------
    async def marry(self, chat: int, a: int, b: int, now: int) -> None:
        """Свадьба: отношения пары становятся браком (пара сохраняет искры, тепло и уровень)."""
        p = await self.pairs.get(chat, a)
        if p and partner_of(p, a) == b:
            await self.pairs.set_stage(p["id"], "marriage")
        else:
            await self.pairs.create(chat, a, b, now, "marriage")

    async def divorce(self, chat: int, u: int) -> int | None:
        sp = await self.spouse(chat, u)
        if not sp:
            return None
        p = await self.pairs.get(chat, u)
        await self.pairs.end(p["id"], "divorce", int(time.time()), u)
        return sp["partner"]

    async def start_relation(self, chat: int, a: int, b: int, now: int) -> None:
        await self.pairs.create(chat, a, b, now, "relation")

    async def end_relation(self, chat: int, u: int) -> int | None:
        p = await self.partner(chat, u)
        if not p:
            return None
        pair = await self.pairs.get(chat, u)
        await self.pairs.end(pair["id"], "breakup", int(time.time()), u)
        return p["partner"]

    async def adopt(self, chat: int, parent: int, child: int, now: int) -> None:
        """Родителем становится и супруг(а) усыновителя, если у ребёнка есть место, а у супруга — лимит."""
        await self.db.conn.execute(
            "INSERT OR IGNORE INTO parents(chat_id,child,parent,since) VALUES(?,?,?,?)", (chat, child, parent, now))
        sp = await self.spouse(chat, parent)
        if sp and (sp["partner"] == child or child in await self.ancestors(chat, sp["partner"])):
            sp = None  # родителем-супругом не делаем того, кто сам потомок или предок ребёнка (иначе петля)
        if (sp and len(await self.parents_of(chat, child)) < MAX_PARENTS
                and len(await self.children_of(chat, sp["partner"])) < MAX_CHILDREN):
            await self.db.conn.execute(
                "INSERT OR IGNORE INTO parents(chat_id,child,parent,since) VALUES(?,?,?,?)",
                (chat, child, sp["partner"], now))
        await self.db.conn.commit()

    async def disown(self, chat: int, parent: int, child: int) -> bool:
        cur = await self.db.conn.execute(
            "DELETE FROM parents WHERE chat_id=? AND child=? AND parent=?", (chat, child, parent))
        await self.db.conn.commit()
        return cur.rowcount == 1

    async def leave_family(self, chat: int, child: int) -> int:
        cur = await self.db.conn.execute("DELETE FROM parents WHERE chat_id=? AND child=?", (chat, child))
        await self.db.conn.commit()
        return cur.rowcount

    async def claim_bonus(self, chat: int, u: int, now: int) -> int | None:
        async with self.db.atomic():
            sp = await self.spouse(chat, u)
            if not sp:
                return None
            day = now // DAY
            # отдельная таблица: развод и повторный брак в тот же день бонус не сбрасывают
            cur = await self.db.conn.execute(
                "INSERT INTO family_bonus VALUES(?,?,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET day=excluded.day "
                "WHERE family_bonus.day<excluded.day", (chat, u, day))
            await self.db.conn.commit()
            if cur.rowcount != 1:
                return None
            kids = set(await self.children_of(chat, u)) | set(await self.children_of(chat, sp["partner"]))
            amount = BONUS_BASE + BONUS_PER_CHILD * min(len(kids), MAX_CHILDREN)
            await self.db.change_balance(chat, u, amount)
            return amount

    # ---------- запросы с кнопками ----------
    async def create_request(self, chat: int, kind: str, from_user: int, to_user: int,
                             message_id: int, expires_at: int) -> str:
        rid = uuid.uuid4().hex[:8]
        await self.db.conn.execute(
            "INSERT INTO family_requests VALUES(?,?,?,?,?,?,?)",
            (rid, chat, kind, from_user, to_user, message_id, expires_at))
        await self.db.conn.commit()
        return rid

    async def set_request_message(self, rid: str, message_id: int) -> None:
        await self.db.conn.execute("UPDATE family_requests SET message_id=? WHERE id=?", (message_id, rid))
        await self.db.conn.commit()

    async def get_request(self, rid: str) -> dict | None:
        rows = await self._all("SELECT * FROM family_requests WHERE id=?", (rid,))
        return dict(rows[0]) if rows else None

    async def delete_request(self, rid: str) -> bool:
        cur = await self.db.conn.execute("DELETE FROM family_requests WHERE id=?", (rid,))
        await self.db.conn.commit()
        return cur.rowcount == 1

    async def expired_requests(self, now: int) -> list[dict]:
        return [dict(r) for r in await self._all("SELECT * FROM family_requests WHERE expires_at<?", (now,))]

    async def has_pending(self, chat: int, u: int, now: int | None = None) -> bool:
        sql = "SELECT 1 FROM family_requests WHERE chat_id=? AND (from_user=? OR to_user=?)"
        args: tuple = (chat, u, u)
        if now is not None:
            sql += " AND expires_at>=?"
            args += (now,)
        return bool(await self._all(sql + " LIMIT 1", args))

    # ---------- списки ----------
    async def list_marriages(self, chat: int, limit: int, offset: int) -> list[dict]:
        rows = await self._all(
            "SELECT * FROM pairs WHERE chat_id=? AND stage='marriage' AND ended_at IS NULL ORDER BY created ASC, id LIMIT ? OFFSET ?",
            (chat, limit, offset))
        return [{"chat_id": r["chat_id"], "u1": r["u1"], "u2": r["u2"], "since": r["created"]} for r in rows]

    async def count_marriages(self, chat: int) -> int:
        return (await self._all("SELECT COUNT(*) AS n FROM pairs WHERE chat_id=? AND stage='marriage' AND ended_at IS NULL",
                                (chat,)))[0]["n"]

    async def pending_to(self, chat: int, user: int, now: int) -> dict | None:
        rows = await self._all("SELECT * FROM family_requests WHERE chat_id=? AND to_user=? AND expires_at>=? "
                               "ORDER BY expires_at DESC LIMIT 1", (chat, user, now))
        return dict(rows[0]) if rows else None
