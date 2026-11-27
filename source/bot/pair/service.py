"""Сервис пары: хранение и правила (искры, содержание, ссора и распад, действия, РП, серия). Без Telegram: возвращает данные
и «события» (ссора, распад, предупреждение, новый уровень), а сообщения в чат собирает обработчик.

Время считается лениво: при каждом обращении к паре settle() досчитывает содержание за прошедшие сутки; фоновый обход
(handlers/pair.py) нужен только чтобы вовремя объявить ссору и распад. Операции над одной парой идут под её замком."""
from __future__ import annotations

import asyncio
from weakref import WeakValueDictionary
import time
from dataclasses import dataclass, field

from bot.db import Database
import random

from bot.pair import premium as pp, baby as bb, kids as kd, pets as pt, data, economy as eco, gifts as gf, house as hs, quests as qs

_LOCKS: WeakValueDictionary[int, asyncio.Lock] = WeakValueDictionary()


def _lock(pid: int) -> asyncio.Lock:
    return _LOCKS.setdefault(pid, asyncio.Lock())


@dataclass
class Result:
    ok: bool
    error: str | None = None
    info: dict = field(default_factory=dict)
    events: list = field(default_factory=list)


def partner_of(p: dict, user: int) -> int:
    return p["u2"] if p["u1"] == user else p["u1"]


def side_of(p: dict, user: int) -> int:
    return 1 if p["u1"] == user else 2


def is_sleeping(p: dict, now: int) -> bool:
    return now - (p.get("last_active") or p["created"]) > eco.SLEEP_AFTER


def effective_streak(p: dict, now: int) -> int:
    """Серия, которая действует сейчас: если вчера день не засчитан и сегодня тоже — серия сгорела."""
    return p["streak"] if p["streak_day"] >= eco.day_index(now) - 1 else 0


class PairService:
    def __init__(self, db: Database):
        self.db = db

    # ---------- чтение ----------
    async def _one(self, sql: str, args: tuple = ()) -> dict | None:
        cur = await self.db.conn.execute(sql, args)
        r = await cur.fetchone()
        return dict(r) if r else None

    async def _all(self, sql: str, args: tuple = ()) -> list[dict]:
        cur = await self.db.conn.execute(sql, args)
        return [dict(r) for r in await cur.fetchall()]

    async def get(self, chat: int, user: int) -> dict | None:
        return await self._one("SELECT * FROM pairs WHERE chat_id=? AND (u1=? OR u2=?) AND ended_at IS NULL",
                               (chat, user, user))

    async def get_by_id(self, pid: int, *, for_update: bool = False) -> dict | None:
        suffix = " FOR UPDATE" if for_update and self.db.backend == "pg" else ""
        return await self._one("SELECT * FROM pairs WHERE id=?" + suffix, (pid,))

    async def kids(self, p: dict) -> int:
        r = await self._one("SELECT COUNT(DISTINCT child) AS n FROM parents WHERE chat_id=? AND (parent=? OR parent=?)",
                            (p["chat_id"], p["u1"], p["u2"]))
        c = await self._one("SELECT COUNT(*) AS n FROM pair_children WHERE pair_id=? AND grown=0", (p["id"],))
        return (int(r["n"]) if r else 0) + (int(c["n"]) if c else 0)

    async def counters(self, pid: int) -> dict[str, int]:
        return {r["kind"]: r["n"] for r in await self._all("SELECT kind, n FROM pair_counters WHERE pair_id=?", (pid,))}

    # ---------- запись ----------
    async def _save(self, pid: int, fields: dict) -> None:
        sets = ",".join(f"{k}=?" for k in fields)
        await self.db.conn.execute(f"UPDATE pairs SET {sets} WHERE id=?", (*fields.values(), pid))

    async def _log(self, pid: int, ts: int, kind: str, amount: int, balance: int, warmth: int, actor: int | None,
                   detail: str = "") -> None:
        await self.db.conn.execute(
            "INSERT INTO pair_log(pair_id,ts,kind,amount,balance,warmth,actor,detail) VALUES(?,?,?,?,?,?,?,?)",
            (pid, ts, kind, amount, balance, warmth, actor, detail))

    async def create(self, chat: int, a: int, b: int, now: int, stage: str = "relation", *, sparks: int = eco.START_SPARKS,
                     warmth: int = 0, created: int | None = None, legacy_key: str | None = None) -> dict:
        async with self.db.atomic():
            u1, u2 = (a, b) if a < b else (b, a)
            level = eco.level_for(warmth)
            cur = await self.db.conn.execute(
                "INSERT INTO pairs(chat_id,u1,u2,stage,created,sparks,warmth,level,upkeep_at,last_active,legacy_key) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (chat, u1, u2, stage, created or now, sparks, warmth, level, now + eco.DAY, now, legacy_key))
            pid = cur.lastrowid
            await self._log(pid, now, "create", sparks, sparks, warmth, a, "новая пара")
            await self.db.conn.commit()
            return await self.get_by_id(pid)

    async def set_stage(self, pid: int, stage: str) -> None:
        await self._save(pid, {"stage": stage})
        await self.db.conn.commit()

    async def end(self, pid: int, reason: str, now: int, actor: int | None = None) -> dict | None:
        """Закрыть пару (расставание, развод, ссора без примирения). Запись остаётся в архиве."""
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            if p is None or p["ended_at"] is not None:
                return None
            await self._save(pid, {"ended_at": now, "ended_reason": reason})
            await self._log(pid, now, "end", 0, p["sparks"], 0, actor, reason)
            await self.db.conn.commit()
            return {**p, "ended_at": now, "ended_reason": reason}

    # ---------- время: содержание, ссора, распад ----------
    async def settle(self, pid: int, now: int) -> tuple[dict | None, list]:
        """Досчитать содержание и ссору до now. Возвращает (пара | None если распалась, события)."""
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            if p is None or p["ended_at"] is not None:
                return None, []
            events: list = []
            upd: dict = {}
            kids = await self.kids(p)
            guard = 0
            while p["state"] == "ok" and p["upkeep_at"] and now >= p["upkeep_at"] and guard < 90:
                guard += 1
                amt = eco.upkeep_amount(p["level"], kids, p["sparks"])
                if p["sparks"] <= amt:                       # кошелёк пуст — ссора
                    paid, at = p["sparks"], p["upkeep_at"]
                    hours = pp.QUARREL_HOURS if pp.active(p, at) else eco.QUARREL_HOURS
                    p.update(sparks=0, state="quarrel", quarrel_until=at + hours * 3600)
                    if paid:
                        await self._log(pid, at, "upkeep", -paid, 0, 0, None, "содержание")
                    await self._log(pid, at, "quarrel", 0, 0, 0, None, "искры кончились")
                    events.append(("quarrel", {"until": p["quarrel_until"]}))
                    break
                p["sparks"] -= amt
                await self._log(pid, p["upkeep_at"], "upkeep", -amt, p["sparks"], 0, None, "содержание")
                p["upkeep_at"] += eco.DAY
            aux = await self._one(
                "SELECT (SELECT COUNT(*) FROM pair_baby WHERE pair_id=?) AS b, "
                "(SELECT COUNT(*) FROM pair_children WHERE pair_id=? AND grown=0) AS k, "
                "(SELECT COUNT(*) FROM pair_pets WHERE pair_id=? AND egg=1) AS e, "
                "(SELECT COUNT(*) FROM pair_houses WHERE pair_id=?) AS h", (pid, pid, pid, pid))
            if aux["b"]:                                       # лишние запросы только там, где есть что считать
                events += await self._baby_tick(p, now)
            if aux["k"]:
                events += await self._kids_tick(p, now)
            if aux["e"]:
                events += await self._pets_tick(p, now)
            if p["state"] == "ok" and aux["h"]:
                events += await self._house_tick(p, kids, now)
            if p["state"] == "quarrel" and now >= p["quarrel_until"]:
                await self._save(pid, {"sparks": 0, "state": "quarrel", "upkeep_at": p["upkeep_at"], "ended_at": now,
                                       "ended_reason": "sparks"})
                await self._log(pid, now, "end", 0, 0, 0, None, "не помирились")
                await self.db.conn.commit()
                events.append(("dissolved", {"since": p["created"]}))
                return None, events
            if p["state"] == "ok":                           # предупреждение за сутки до нехватки
                nxt = eco.upkeep_amount(p["level"], kids, p["sparks"])
                if p["sparks"] <= nxt and p["warned_day"] != eco.day_index(now) and p["upkeep_at"] - now <= eco.DAY:
                    p["warned_day"] = eco.day_index(now)
                    events.append(("warn", {"sparks": p["sparks"], "need": nxt}))
            await self._save(pid, {k: p[k] for k in ("sparks", "state", "quarrel_until", "upkeep_at", "warned_day", "warmth", "level")})
            await self.db.conn.commit()
            return p, events

    # ---------- искры ----------
    async def credit(self, pid: int, amount: int, kind: str, actor: int | None, now: int, detail: str = "") -> list:
        """Начислить искры. Любые искры помирят пару, если она в ссоре."""
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            if p is None or p["ended_at"] is not None or amount <= 0:
                return []
            return await self._credit(p, amount, kind, actor, now, detail)

    async def _credit(self, p: dict, amount: int, kind: str, actor: int | None, now: int, detail: str = "") -> list:
        """Credit while the caller holds the pair row and DB transaction."""
        pid = p["id"]
        events: list = []
        p["sparks"] += amount
        fields = {"sparks": p["sparks"], "last_active": now}
        if p["state"] == "quarrel":
            fields.update(state="ok", quarrel_until=0, upkeep_at=now + eco.DAY)
            events.append(("peace", {}))
        await self._save(pid, fields)
        await self._log(pid, now, kind, amount, p["sparks"], 0, actor, detail)
        await self.db.conn.commit()
        return events

    async def topup(self, pid: int, user: int, coins: int, now: int) -> Result:
        """Пополнить кошелёк пары своими монетами (1 монета = 1 искра, не больше TOPUP_DAILY за сутки на пару)."""
        if type(coins) is not int or coins < 1:
            return Result(False, "Сумма — от 1 монеты.")
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            if p is None or p["ended_at"] is not None:
                return Result(False, "Пары уже нет.")
            if user not in (p["u1"], p["u2"]):
                return Result(False, "Это не ваша пара.")
            day = eco.day_index(now)
            used = p["topup_sum"] if p["topup_day"] == day else 0
            if used + coins > TOPUP_DAILY:
                left = max(TOPUP_DAILY - used, 0)
                return Result(False, f"Пополнить можно не больше {TOPUP_DAILY} искр в сутки (осталось {left}).")
            if not await self.db.try_spend(p["chat_id"], user, coins):
                return Result(False, "Не хватает монет.")
            sparks = p["sparks"] + coins
            fields = {"topup_day": day, "topup_sum": used + coins, "sparks": sparks, "last_active": now}
            events = []
            if p["state"] == "quarrel":
                fields.update(state="ok", quarrel_until=0, upkeep_at=now + eco.DAY)
                events.append(("peace", {}))
            await self._save(pid, fields)
            await self._log(pid, now, "topup", coins, sparks, 0, user, "пополнение монетами")
            await self.db.conn.commit()
            return Result(True, info={"sparks": coins}, events=events)

    # ---------- действия ----------
    async def act(self, pid: int, user: int, key: str, now: int) -> Result:
        action = data.find_action(key)
        if action is None:
            return Result(False, "Нет такого действия.")
        p, events = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.", events=events)
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self._blocked(p, user)
            if err:
                return Result(False, err, events=events)
            side = side_of(p, user)
            nxt = p[f"next{side}"]
            if now < nxt:
                return Result(False, f"⏳ Рано: следующее действие через {eco.fmt_duration(nxt - now)}.", events=events)
            if action.level > p["level"]:
                return Result(False, f"🔒 «{action.key}» откроется на {action.level} уровне (сейчас {p['level']}).", events=events)
            day = eco.day_index(now)
            if p["day"] != day:
                p.update(day=day, mask=0, n1=0, n2=0, rp1=0, rp2=0)
            n = p[f"n{side}"]
            other_ts = p[f"act{3 - side}"]
            unison = bool(other_ts) and now - other_ts <= eco.UNISON_WINDOW
            streak = effective_streak(p, now)
            tired = n >= eco.DAILY_ACTIONS_BEFORE_TIRED
            sparks, warmth = eco.action_reward(action.sparks, action.cd, streak=streak, unison=unison, tired=tired)
            p[f"n{side}"] = n + 1
            p[f"act{side}"] = now
            p[f"next{side}"] = now + action.cd * 60
            p["mask"] |= side
            p["sparks"] += sparks
            together = False
            if p["mask"] == 3 and p["streak_day"] != day:        # оба сегодня делали действия — день вместе
                p["streak"] = p["streak"] + 1 if p["streak_day"] == day - 1 else 1
                p["streak_day"] = day
                warmth += eco.DAY_TOGETHER_WARMTH
                together = True
            events += await self._quest_progress(p, "act", 1, now)
            if together:
                events += await self._quest_progress(p, "together", 1, now)
            events += await self._grow(p, warmth, now)
            levelup = [e for e in events if e[0] == "levelup"]
            await self._save(pid, {k: p[k] for k in (
                "sparks", "warmth", "level", "streak", "streak_day", "day", "mask", "n1", "n2", "rp1", "rp2", "act1", "act2",
                "next1", "next2")} | {"last_active": now})
            await self._log(pid, now, "action", sparks, p["sparks"], warmth, user, action.key)
            await self.db.conn.commit()
            return Result(True, info={"action": action, "sparks": sparks, "warmth": warmth, "unison": unison, "tired": tired,
                                       "streak": p["streak"] if together else streak, "together": together,
                                       "cd": action.cd * 60, "level": p["level"], "levelup": bool(levelup)},
                          events=events)

    async def _grow(self, p: dict, warmth: int, now: int) -> list:
        """Прибавить тепло, пересчитать уровень; за каждый новый уровень — подарок искрами."""
        events: list = []
        warmth = pp.boost(warmth, p, now)
        p["warmth"] += warmth
        new = eco.level_for(p["warmth"])
        while p["level"] < new:
            p["level"] += 1
            gift = eco.level_gift(p["level"])
            p["sparks"] += gift
            events.append(("levelup", {"level": p["level"], "gift": gift}))
        return events

    # ---------- премиум пары ----------
    async def grant_premium(self, pid: int, now: int) -> int | None:
        """Продлить премиум пары на 30 дней; вернуть новую дату окончания."""
        async with self.db.atomic():
            cur = await self.db.conn.execute(
                "UPDATE pairs SET premium_until=CASE WHEN COALESCE(premium_until,0)>? "
                "THEN premium_until ELSE ? END + ? WHERE id=? AND ended_at IS NULL",
                (now, now, pp.PERIOD, pid))
            if cur.rowcount != 1:
                return None
            p = await self.get_by_id(pid)
            await self._log(pid, now, "premium", 0, p["sparks"], 0, None, "премиум пары")
            return p["premium_until"]

    async def revoke_premium(self, pid: int) -> bool:
        async with self.db.atomic():
            cur = await self.db.conn.execute("UPDATE pairs SET premium_until=0 WHERE id=?", (pid,))
            await self.db.conn.execute("UPDATE payment_effects SET until=-1 WHERE kind='pair' AND target_id=?", (pid,))
            return cur.rowcount == 1

    # ---------- питомцы ----------
    async def pets(self, pid: int, now: int) -> list[dict]:
        rows = await self._all("SELECT * FROM pair_pets WHERE pair_id=? ORDER BY id", (pid,))
        for r in rows:
            r["mood"], _ = pt.mood_now(r["mood"], r["mood_at"] or r["hatch_at"], now)
            r["level"] = pt.level(r["xp"])
            r["emoji"] = pt.emoji_of(r["species"])
        return rows

    async def _pets_tick(self, p: dict, now: int) -> list:
        events = []
        for r in await self._all("SELECT * FROM pair_pets WHERE pair_id=? AND egg=1 AND hatch_at<=?", (p["id"], now)):
            await self.db.conn.execute("UPDATE pair_pets SET egg=0, mood=70, mood_at=? WHERE id=?", (now, r["id"]))
            events.append(("pet_hatched", {"species": r["species"], "rarity": r["rarity"], "emoji": pt.emoji_of(r["species"])}))
        return events

    async def buy_egg(self, pid: int, user: int, now: int, rng=None) -> Result:
        rng = rng or random
        p, events = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.", events=events)
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self._blocked(p, user)
            if err:
                return Result(False, err)
            have = await self._one("SELECT COUNT(*) AS n FROM pair_pets WHERE pair_id=?", (pid,))
            cap = pp.PETS_MAX if pp.active(p, now) else pt.MAX_PETS
            if have["n"] >= cap:
                return Result(False, f"В питомнике максимум {cap} питомцев" + ("" if cap > pt.MAX_PETS else ": с премиумом пары их 5") + ".")
            if p["sparks"] < pt.EGG_PRICE:
                return Result(False, f"Яйцо стоит {pt.EGG_PRICE} 🔥, в кошельке {p['sparks']}.")
            sp, _, rarity = pt.roll(rng)
            p["sparks"] -= pt.EGG_PRICE
            await self._save(pid, {"sparks": p["sparks"], "last_active": now})
            await self.db.conn.execute("INSERT INTO pair_pets(pair_id,species,rarity,egg,hatch_at,mood_at) VALUES(?,?,?,1,?,?)",
                                       (pid, sp, rarity, now + pt.HATCH_SEC, now))
            await self._log(pid, now, "pet", -pt.EGG_PRICE, p["sparks"], 0, user, "яйцо питомца")
            await self.db.conn.commit()
            return Result(True, info={"hatch_in": pt.HATCH_SEC}, events=events)

    async def care_pet(self, pid: int, user: int, pet_id: int, act: str, now: int) -> Result:
        item = pt.CARE.get(data.norm(act))
        if item is None:
            return Result(False, "Покормить или поиграть.")
        p, events = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.", events=events)
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self._blocked(p, user)
            if err:
                return Result(False, err)
            r = await self._one("SELECT * FROM pair_pets WHERE id=? AND pair_id=? AND egg=0", (pet_id, pid))
            if r is None:
                return Result(False, "Такого питомца нет (или он ещё в яйце).")
            emoji, col, cd, plus, xp = item
            if now < r[col] + cd:
                return Result(False, f"⏳ Рано: ещё {eco.fmt_duration(r[col] + cd - now)}.")
            mood, _ = pt.mood_now(r["mood"], r["mood_at"] or r["hatch_at"], now)
            mood = min(100, mood + plus)
            await self.db.conn.execute(f"UPDATE pair_pets SET mood=?, mood_at=?, {col}=?, xp=xp+? WHERE id=?",
                                       (mood, now, now, xp, pet_id))
            await self.db.conn.commit()
            return Result(True, info={"emoji": emoji, "species": r["species"], "mood": mood}, events=events)

    async def collect_pets(self, pid: int, user: int, now: int) -> Result:
        """Раз в сутки питомцы с настроением от 50 приносят искры."""
        p, events = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.", events=events)
        day = eco.day_index(now)
        total = 0
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self._blocked(p, user)
            if err:
                return Result(False, err)
            for r in await self._all("SELECT * FROM pair_pets WHERE pair_id=? AND egg=0 AND claim_day<?", (pid, day)):
                mood, _ = pt.mood_now(r["mood"], r["mood_at"] or r["hatch_at"], now)
                if mood >= pt.MIN_MOOD_INCOME:
                    total += pt.income(r["rarity"], r["xp"])
                    await self.db.conn.execute("UPDATE pair_pets SET claim_day=? WHERE id=?", (day, r["id"]))
            if total == 0:
                return Result(False, "Сегодня питомцы ничего не принесли: покормите их и поиграйте (настроение от 50) или уже забрали.")
            events += await self._credit(p, total, "pet", user, now, "приработок питомцев")
        return Result(True, info={"sparks": total}, events=events)

    async def name_pet(self, pid: int, user: int, pet_id: int, name: str) -> Result:
        p = await self.get_by_id(pid)
        err = self._blocked(p, user)
        if err:
            return Result(False, err)
        name = " ".join(name.split())[:20]
        if len(name) < 2:
            return Result(False, "Имя — от 2 символов.")
        cur = await self.db.conn.execute("UPDATE pair_pets SET name=? WHERE id=? AND pair_id=?", (name, pet_id, pid))
        await self.db.conn.commit()
        return Result(cur.rowcount == 1, None if cur.rowcount == 1 else "Нет такого питомца.", info={"name": name})

    # ---------- малыш ----------
    async def baby(self, pid: int, now: int | None = None) -> dict | None:
        b = await self._one("SELECT * FROM pair_baby WHERE pair_id=?", (pid,))
        if b and now is not None:
            b["week"] = bb.week(b["started"], now)
            b["health"], _ = bb.decayed(b["health"], b["health_at"], now)
        return b

    async def _baby_tick(self, p: dict, now: int) -> list:
        """Спад здоровья, потеря при нуле, роды на 40-й неделе."""
        b = await self._one("SELECT * FROM pair_baby WHERE pair_id=?", (p["id"],))
        if b is None:
            return []
        pid = p["id"]
        health, at = bb.decayed(b["health"], b["health_at"], now)
        if health <= 0:
            await self.db.conn.execute("DELETE FROM pair_baby WHERE pair_id=?", (pid,))
            await self._log(pid, now, "baby", 0, p["sparks"], 0, None, "беременность прервалась")
            return [("baby_lost", {})]
        if bb.week(b["started"], now) >= bb.WEEKS:
            count = 2 if b["twins"] else 1
            names = [b["name"] or random.choice(bb.NAMES)]
            if count == 2:
                names.append(random.choice([x for x in bb.NAMES if x != names[0]]))
            for nm in names:
                await self.db.conn.execute("INSERT INTO pair_children(pair_id,name,born) VALUES(?,?,?)", (pid, nm, now))
            await self.db.conn.execute("DELETE FROM pair_baby WHERE pair_id=?", (pid,))
            evs = await self._grow(p, bb.BIRTH_WARMTH, now)
            await self._log(pid, now, "baby", 0, p["sparks"], bb.BIRTH_WARMTH, None, "рождение: " + ", ".join(names))
            return evs + [("baby_born", {"names": names})]
        if (health, at) != (b["health"], b["health_at"]):
            await self.db.conn.execute("UPDATE pair_baby SET health=?, health_at=? WHERE pair_id=?", (health, at, pid))
        return []

    async def children(self, pid: int, now: int | None = None) -> list[dict]:
        rows = await self._all("SELECT * FROM pair_children WHERE pair_id=? ORDER BY grown, born, id", (pid,))
        if now is not None:
            for c in rows:
                c["age"] = kd.age(c["born"], now)
                c["mood"], _ = kd.mood_now(c["mood"], c["mood_at"] or c["born"], now)
        return rows

    async def _kids_tick(self, p: dict, now: int) -> list:
        """Настроение падает без заботы; в 18 лет ребёнок выбирает профессию и съезжает, оставляя семье подарок."""
        events: list = []
        for c in await self._all("SELECT * FROM pair_children WHERE pair_id=? AND grown=0", (p["id"],)):
            if kd.age(c["born"], now) >= kd.ADULT_AGE:
                job = kd.job_for(c)
                await self.db.conn.execute("UPDATE pair_children SET grown=1, job=? WHERE id=?", (job, c["id"]))
                p["sparks"] += kd.GROWN_GIFT
                await self._log(p["id"], now, "kid", kd.GROWN_GIFT, p["sparks"], 0, None, f"{c['name']} взрослый: {job}")
                events.append(("child_grown", {"name": c["name"], "job": job, "gift": kd.GROWN_GIFT}))
                continue
            mood, at = kd.mood_now(c["mood"], c["mood_at"] or c["born"], now)
            if (mood, at) != (c["mood"], c["mood_at"]):
                await self.db.conn.execute("UPDATE pair_children SET mood=?, mood_at=? WHERE id=?", (mood, at, c["id"]))
        return events

    async def care_child(self, pid: int, user: int, child_id: int, act: str, now: int) -> Result:
        item = kd.CARE.get(data.norm(act))
        if item is None:
            return Result(False, "Нет такого ухода: покормить, поиграть, учить, спорт.")
        p, events = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.", events=events)
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self._blocked(p, user)
            if err:
                return Result(False, err)
            c = await self._one("SELECT * FROM pair_children WHERE id=? AND pair_id=? AND grown=0", (child_id, pid))
            if c is None:
                return Result(False, "Такого ребёнка нет.")
            key = data.norm(act)
            emoji, label, cd, plus, skill, min_age = item
            a = kd.age(c["born"], now)
            if a < min_age:
                return Result(False, f"{c['name']} пока мал(а): с {min_age} лет.")
            col = kd.COL[key]
            if now < c[col] + cd:
                return Result(False, f"⏳ {c['name']}: {key} через {eco.fmt_duration(c[col] + cd - now)}.")
            mood, _ = kd.mood_now(c["mood"], c["mood_at"] or c["born"], now)
            mood = min(100, mood + plus)
            fields = {"mood": mood, "mood_at": now, col: now}
            gained = 0
            if skill and mood >= 30:                         # совсем расстроенный ребёнок не учится
                gained = 2 if mood >= 70 else 1
                fields[skill] = min(kd.SKILL_CAP, c[skill] + gained)
            sets = ",".join(f"{k}=?" for k in fields)
            await self.db.conn.execute(f"UPDATE pair_children SET {sets} WHERE id=?", (*fields.values(), child_id))
            events += await self._grow(p, 3, now)
            await self._save(pid, {"warmth": p["warmth"], "level": p["level"], "last_active": now})
            await self.db.conn.commit()
            return Result(True, info={"emoji": emoji, "label": label, "name": c["name"], "mood": mood, "skill": skill, "gained": gained},
                          events=events)

    async def set_protect(self, pid: int, user: int, on: bool) -> Result:
        p = await self.get_by_id(pid)
        err = self._blocked(p, user)
        if err:
            return Result(False, err)
        await self._save(pid, {"protect": 1 if on else 0})
        await self.db.conn.commit()
        return Result(True, info={"protect": on})

    def intim_check(self, p: dict, user: int, now: int) -> str | None:
        err = self._blocked(p, user)
        if err:
            return err
        if p["level"] < bb.INTIM_MIN_LEVEL:
            return f"Нужен {bb.INTIM_MIN_LEVEL} уровень пары (сейчас {p['level']})."
        if now < p["intim_at"] + bb.INTIM_COOLDOWN:
            return f"⏳ Рано: ещё {eco.fmt_duration(p['intim_at'] + bb.INTIM_COOLDOWN - now)}."
        return None

    async def intimacy(self, pid: int, user: int, now: int, rng: random.Random | None = None) -> Result:
        """Ночь вместе (оба согласились). Тепло всегда; шанс малыша — по защите. Нельзя, пока малыш ожидается."""
        rng = rng or random
        p, events = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.", events=events)
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self.intim_check(p, user, now)
            if err:
                return Result(False, err, events=events)
            pregnant = False
            if await self._one("SELECT 1 AS x FROM pair_baby WHERE pair_id=?", (pid,)) is None:
                pregnant = rng.randrange(100) < bb.chance(bool(p["protect"]))
            events += await self._grow(p, bb.INTIM_WARMTH, now)
            await self._save(pid, {"warmth": p["warmth"], "level": p["level"], "sparks": p["sparks"], "intim_at": now,
                                   "last_active": now})
            if pregnant:
                twins = 1 if rng.randrange(100) < bb.TWINS_PCT else 0
                await self.db.conn.execute(
                    "INSERT INTO pair_baby(pair_id,mother,started,health,health_at,twins) VALUES(?,0,?,80,?,?)", (pid, now, now, twins))
            await self._log(pid, now, "intim", 0, p["sparks"], bb.INTIM_WARMTH, user, "ночь вместе")
            await self.db.conn.commit()
            return Result(True, info={"pregnant": pregnant, "warmth": bb.INTIM_WARMTH}, events=events)

    async def set_mother(self, pid: int, user: int) -> Result:
        b = await self.baby(pid)
        p = await self.get_by_id(pid)
        if b is None or p is None or user not in (p["u1"], p["u2"]):
            return Result(False, "Ожидания малыша нет.")
        if b["mother"]:
            return Result(False, "Уже выбрано.")
        await self.db.conn.execute("UPDATE pair_baby SET mother=? WHERE pair_id=?", (user, pid))
        await self.db.conn.commit()
        return Result(True)

    async def care(self, pid: int, user: int, key: str, now: int) -> Result:
        item = bb.CARE.get(data.norm(key))
        if item is None:
            return Result(False, "Нет такой заботы: врач, отдых, витамины.")
        p, events = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.", events=events)
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self._blocked(p, user)
            if err:
                return Result(False, err)
            b = await self.baby(pid, now)
            if b is None:
                return Result(False, "Сейчас малыша не ждёте.")
            col = {"врач": "doc_at", "отдых": "rest_at", "витамины": "vit_at"}[data.norm(key)]
            emoji, plus, cd, label = item
            if now < b[col] + cd:
                return Result(False, f"⏳ Рано: {label} через {eco.fmt_duration(b[col] + cd - now)}.")
            health = min(100, b["health"] + plus)
            await self.db.conn.execute(f"UPDATE pair_baby SET health=?, health_at=?, {col}=? WHERE pair_id=?", (health, now, now, pid))
            await self.db.conn.commit()
            return Result(True, info={"emoji": emoji, "label": label, "plus": plus, "health": health}, events=events)

    async def name_baby(self, pid: int, user: int, name: str) -> Result:
        p = await self.get_by_id(pid)
        err = self._blocked(p, user)
        if err:
            return Result(False, err)
        if await self.baby(pid) is None:
            return Result(False, "Сейчас малыша не ждёте.")
        name = " ".join(name.split())[:20]
        if len(name) < 2:
            return Result(False, "Имя — от 2 символов.")
        await self.db.conn.execute("UPDATE pair_baby SET name=? WHERE pair_id=?", (name, pid))
        await self.db.conn.commit()
        return Result(True, info={"name": name})

    async def abort(self, pid: int, user: int, now: int) -> Result:
        p, _ = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.")
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            b = await self.baby(pid, now)
            if b is None or user not in (p["u1"], p["u2"]):
                return Result(False, "Сейчас малыша не ждёте.")
            if b["mother"] and b["mother"] != user:
                return Result(False, "Решение принимает тот, кто носит малыша.")
            if b["week"] >= bb.ABORT_UNTIL_WEEK:
                return Result(False, f"После {bb.ABORT_UNTIL_WEEK}-й недели прервать нельзя.")
            await self.db.conn.execute("DELETE FROM pair_baby WHERE pair_id=?", (pid,))
            await self._log(pid, now, "baby", 0, p["sparks"], 0, user, "ожидание прервано")
            await self.db.conn.commit()
            return Result(True)

    # ---------- дом ----------
    async def house(self, pid: int) -> dict | None:
        h = await self._one("SELECT * FROM pair_houses WHERE pair_id=?", (pid,))
        if h is None:
            return None
        h["rooms"] = {r["room"]: r["level"] for r in await self._all("SELECT room, level FROM pair_rooms WHERE pair_id=?", (pid,))}
        h["def"] = hs.find_house(h["tier"])
        h["bill"] = hs.bill_amount(h["def"], h["rooms"])
        h["prestige"] = hs.prestige(h["def"], h["rooms"])
        return h

    async def _house_tick(self, p: dict, kids: int, now: int) -> list:
        """Еженедельный счёт: копилка, потом кошелёк (оставляя на сутки содержания), остаток — в долг с пеней."""
        h = await self.house(p["id"])
        events: list = []
        if h is None:
            return events
        pid, guard = p["id"], 0
        while now >= h["bill_at"] and guard < 20:
            guard += 1
            due = h["bill"]
            take = min(h["hoard"], due)
            h["hoard"] -= take
            due -= take
            keep = eco.upkeep_amount(p["level"], kids, p["sparks"])
            take2 = min(max(p["sparks"] - keep, 0), due)
            p["sparks"] -= take2
            due -= take2
            if take2:
                await self._log(pid, h["bill_at"], "bill", -take2, p["sparks"], 0, None, "счёт за дом")
            if due > 0:
                h["debt"] += due + due * hs.PENALTY_PCT // 100
                h["missed"] += 1
                events.append(("bill_missed", {"debt": h["debt"], "missed": h["missed"]}))
            elif h["debt"] == 0:
                h["missed"] = 0
            h["bill_at"] += hs.WEEK
            if h["missed"] >= hs.CONFISCATE_AFTER:
                back = h["def"].price * hs.SELL_BACK_PCT // 100 + h["hoard"]
                p["sparks"] += max(back - h["debt"], 0)
                await self.db.conn.execute("DELETE FROM pair_houses WHERE pair_id=?", (pid,))
                await self.db.conn.execute("DELETE FROM pair_rooms WHERE pair_id=?", (pid,))
                await self._log(pid, now, "house", max(back - h["debt"], 0), p["sparks"], 0, None, "дом конфискован за долги")
                events.append(("confiscated", {"back": max(back - h["debt"], 0)}))
                return events
            if h["missed"] >= hs.ARREST_AFTER and not h["arrested"]:
                h["arrested"] = 1
                events.append(("arrested", {"debt": h["debt"]}))
        await self.db.conn.execute("UPDATE pair_houses SET hoard=?, bill_at=?, debt=?, missed=?, arrested=? WHERE pair_id=?",
                                   (h["hoard"], h["bill_at"], h["debt"], h["missed"], h["arrested"], pid))
        return events

    async def buy_house(self, pid: int, user: int, word: str, now: int) -> Result:
        tier = hs.find_house(word)
        if tier is None:
            return Result(False, "Нет такого дома: список — «пара дом».")
        p, events = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.", events=events)
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self._blocked(p, user)
            if err:
                return Result(False, err)
            h = await self.house(pid)
            cost = tier.price
            if h:
                if h["arrested"]:
                    return Result(False, "🚔 Дом арестован: сначала оплатите долг.")
                if tier.price <= h["def"].price:
                    return Result(False, "Переезжать можно только в дом побольше.")
                cost = tier.price - h["def"].price * hs.SELL_BACK_PCT // 100      # старый дом выкупают за половину
            if p["sparks"] - cost < 0:
                return Result(False, f"Не хватает искр: нужно {cost}, в кошельке {p['sparks']}.")
            p["sparks"] -= cost
            await self._save(pid, {"sparks": p["sparks"], "last_active": now})
            if h:
                await self.db.conn.execute("UPDATE pair_houses SET tier=? WHERE pair_id=?", (tier.key, pid))
            else:
                await self.db.conn.execute(
                    "INSERT INTO pair_houses(pair_id,tier,name,hoard,bill_at,debt,missed,arrested,since) VALUES(?,?,?,0,?,0,0,0,?)",
                    (pid, tier.key, "", now + hs.WEEK, now))
            await self._log(pid, now, "house", -cost, p["sparks"], 0, user, f"дом: {tier.key}")
            await self.db.conn.commit()
            return Result(True, info={"house": tier, "cost": cost}, events=events)

    async def build_room(self, pid: int, user: int, word: str, now: int) -> Result:
        room = hs.find_room(word)
        if room is None:
            return Result(False, "Нет такой комнаты.")
        p, events = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.", events=events)
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self._blocked(p, user)
            if err:
                return Result(False, err)
            h = await self.house(pid)
            if h is None:
                return Result(False, "Сначала купите дом: «пара дом».")
            if h["arrested"]:
                return Result(False, "🚔 Дом арестован: сначала оплатите долг.")
            lvl = h["rooms"].get(room.key, 0)
            if lvl >= hs.ROOM_MAX:
                return Result(False, "Комната уже на максимальном уровне.")
            if lvl == 0 and len(h["rooms"]) >= h["def"].slots:
                return Result(False, f"В доме «{h['def'].key}» всего {h['def'].slots} комн. Переезжайте в дом побольше.")
            cost = hs.room_cost(room, lvl + 1)
            if p["sparks"] < cost:
                return Result(False, f"Не хватает искр: нужно {cost}, в кошельке {p['sparks']}.")
            p["sparks"] -= cost
            await self._save(pid, {"sparks": p["sparks"], "last_active": now})
            await self.db.conn.execute(
                "INSERT INTO pair_rooms(pair_id,room,level) VALUES(?,?,1) ON CONFLICT(pair_id,room) DO UPDATE SET level=pair_rooms.level+1",
                (pid, room.key))
            await self._log(pid, now, "house", -cost, p["sparks"], 0, user, f"комната: {room.key} {lvl + 1}")
            await self.db.conn.commit()
            return Result(True, info={"room": room, "level": lvl + 1, "cost": cost}, events=events)

    async def hoard_move(self, pid: int, user: int, amount: int, now: int) -> Result:
        """amount > 0 — в копилку, < 0 — из копилки."""
        p, events = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.", events=events)
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self._blocked(p, user)
            if err:
                return Result(False, err)
            h = await self.house(pid)
            if h is None:
                return Result(False, "Копилка живёт в доме: «пара дом».")
            if amount > 0:
                amount = min(amount, h["def"].hoard_cap - h["hoard"], p["sparks"])
                if amount <= 0:
                    return Result(False, "Копилка заполнена или в кошельке нет искр.")
            else:
                amount = -min(-amount, h["hoard"])
                if amount == 0:
                    return Result(False, "В копилке пусто.")
            p["sparks"] -= amount
            await self._save(pid, {"sparks": p["sparks"]})
            await self.db.conn.execute("UPDATE pair_houses SET hoard=hoard+? WHERE pair_id=?", (amount, pid))
            await self._log(pid, now, "hoard", -amount, p["sparks"], 0, user, "копилка")
            await self.db.conn.commit()
            return Result(True, info={"moved": amount, "hoard": h["hoard"] + amount, "sparks": p["sparks"]}, events=events)

    async def pay_debt(self, pid: int, user: int, now: int) -> Result:
        p, events = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.", events=events)
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self._blocked(p, user)
            if err:
                return Result(False, err)
            h = await self.house(pid)
            if h is None or h["debt"] <= 0:
                return Result(False, "Долгов нет.")
            pay = min(h["debt"], p["sparks"])
            if pay <= 0:
                return Result(False, "В кошельке нет искр.")
            p["sparks"] -= pay
            debt = h["debt"] - pay
            arrested = h["arrested"] if debt else 0
            missed = h["missed"] if debt else 0
            await self._save(pid, {"sparks": p["sparks"]})
            await self.db.conn.execute("UPDATE pair_houses SET debt=?, arrested=?, missed=? WHERE pair_id=?", (debt, arrested, missed, pid))
            await self._log(pid, now, "bill", -pay, p["sparks"], 0, user, "долг за дом")
            await self.db.conn.commit()
            return Result(True, info={"paid": pay, "debt": debt, "free": bool(h["arrested"] and not arrested)}, events=events)

    async def rename_house(self, pid: int, user: int, name: str) -> Result:
        p = await self.get_by_id(pid)
        err = self._blocked(p, user)
        if err:
            return Result(False, err)
        if await self.house(pid) is None:
            return Result(False, "Сначала купите дом.")
        name = " ".join(name.split())[:32]
        await self.db.conn.execute("UPDATE pair_houses SET name=? WHERE pair_id=?", (name, pid))
        await self.db.conn.commit()
        return Result(True, info={"name": name})

    async def top_houses(self, chat: int, limit: int = 10) -> list[dict]:
        out = []
        for r in await self._all("SELECT h.pair_id, h.tier, h.name, h.arrested, p.u1, p.u2 FROM pair_houses h "
                                 "JOIN pairs p ON p.id=h.pair_id WHERE p.chat_id=? AND p.ended_at IS NULL AND h.arrested=0", (chat,)):
            h = await self.house(r["pair_id"])
            out.append({**r, "prestige": h["prestige"], "rooms": len(h["rooms"])})
        out.sort(key=lambda x: -x["prestige"])
        return out[:limit]

    # ---------- подарки ----------
    async def showcase(self, pid: int) -> dict[str, int]:
        return {r["gift"]: r["n"] for r in await self._all("SELECT gift, n FROM pair_gifts WHERE pair_id=? AND n>0", (pid,))}

    async def give(self, pid: int, user: int, word: str, now: int) -> Result:
        """Подарить половинке подарок за свои монеты: он ложится в витрину, пара получает тепло (первые 3 в сутки)."""
        gift = gf.find(word)
        if gift is None:
            return Result(False, "Нет такого подарка: список — «пара подарки».")
        p, events = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.", events=events)
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self._blocked(p, user)
            if err:
                return Result(False, err, events=events)
            if not await self.db.try_spend(p["chat_id"], user, gift.price):
                return Result(False, f"Не хватает монет: подарок стоит {gift.price}.", events=events)
            day = eco.day_index(now)
            given = p["gift_n"] if p["gift_day"] == day else 0
            warmth = gf.warmth(gift.price) if given < gf.GIFT_WARMTH_CAP_DAY else 0
            events += await self._grow(p, warmth, now)
            await self.db.conn.execute(
                "INSERT INTO pair_gifts(pair_id,gift,n) VALUES(?,?,1) ON CONFLICT(pair_id,gift) DO UPDATE SET n=pair_gifts.n+1",
                (pid, gift.key))
            await self._save(pid, {"warmth": p["warmth"], "level": p["level"], "sparks": p["sparks"], "gift_day": day,
                                   "gift_n": given + 1, "last_active": now})
            await self._log(pid, now, "gift", 0, p["sparks"], warmth, user, f"подарок: {gift.key}")
            await self.db.conn.commit()
            return Result(True, info={"gift": gift, "warmth": warmth}, events=events)

    # ---------- задания и сезон ----------
    async def quests(self, p: dict, now: int) -> list[dict]:
        """Задания на сегодня и неделю (создаются при первом обращении)."""
        pid, out = p["id"], []
        for scope, count in (("d", 2), ("w", 1)):
            per = qs.period(scope, now)
            rows = await self._all("SELECT * FROM pair_quests WHERE pair_id=? AND scope=? AND period=? ORDER BY slot",
                                   (pid, scope, per))
            if not rows:
                kinds = qs.DAILY_POOL if scope == "d" else [qs.WEEKLY]
                for slot in range(count):
                    kind = kinds[(per + slot) % len(kinds)] if scope == "d" else kinds[0]
                    goal = qs.goal_for(kind, scope, p["level"])
                    sp, wm = qs.reward_for(kind, scope, p["level"])
                    await self.db.conn.execute(
                        "INSERT OR IGNORE INTO pair_quests(pair_id,scope,period,slot,kind,goal,progress,reward,warmth,done) "
                        "VALUES(?,?,?,?,?,?,0,?,?,0)", (pid, scope, per, slot, kind, goal, sp, wm))
                await self.db.conn.commit()
                rows = await self._all("SELECT * FROM pair_quests WHERE pair_id=? AND scope=? AND period=? ORDER BY slot",
                                       (pid, scope, per))
            out += rows
        return out

    async def season(self, p: dict, now: int) -> dict:
        key = f"season:{qs.month_key(now)}"
        counters = await self.counters(p["id"])
        pts = counters.get(key, 0)
        step = qs.season_step(pts)
        claimed = counters.get(f"claimed:{qs.month_key(now)}", 0)
        return {"points": pts, "step": step, "claimed": claimed, "max": qs.SEASON_STEPS, "per": qs.STEP_POINTS}

    async def _bump(self, pid: int, kind: str, n: int) -> None:
        await self.db.conn.execute(
            "INSERT INTO pair_counters(pair_id,kind,n) VALUES(?,?,?) ON CONFLICT(pair_id,kind) DO UPDATE SET n=pair_counters.n+?",
            (pid, kind, n, n))

    async def _quest_progress(self, p: dict, kind: str, n: int, now: int) -> list:
        """Засчитать прогресс заданий (под замком пары, без commit). Награда приходит сразу на кошелёк в p."""
        events: list = []
        await self.quests(p, now)
        for scope in ("d", "w"):
            per = qs.period(scope, now)
            rows = await self._all("SELECT * FROM pair_quests WHERE pair_id=? AND scope=? AND period=? AND kind=? AND done=0",
                                   (p["id"], scope, per, kind))
            for q in rows:
                prog = min(q["progress"] + n, q["goal"])
                done = prog >= q["goal"]
                await self.db.conn.execute(
                    "UPDATE pair_quests SET progress=?, done=? WHERE pair_id=? AND scope=? AND period=? AND slot=?",
                    (prog, 1 if done else 0, p["id"], scope, per, q["slot"]))
                if done:
                    p["sparks"] += q["reward"]
                    events += await self._grow(p, q["warmth"], now)
                    await self._log(p["id"], now, "quest", q["reward"], p["sparks"], q["warmth"], None, qs.text(q["kind"], q["goal"]))
                    await self._bump(p["id"], f"season:{qs.month_key(now)}", qs.POINTS[scope])
                    events.append(("quest", {"text": qs.text(q["kind"], q["goal"]), "sparks": q["reward"], "warmth": q["warmth"],
                                             "scope": scope}))
        return events

    async def claim_season(self, pid: int, user: int, now: int) -> Result:
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self._blocked(p, user)
            if err:
                return Result(False, err)
            s = await self.season(p, now)
            if s["claimed"] >= s["step"]:
                return Result(False, "Награды сезона пока все забраны: делайте задания.")
            total = 0
            for step in range(s["claimed"] + 1, s["step"] + 1):
                total += qs.season_reward(step, p["level"])
            await self._bump(pid, f"claimed:{qs.month_key(now)}", s["step"] - s["claimed"])
            events = await self._credit(p, total, "season", user, now, f"сезон: ступень {s['step']}")
        return Result(True, info={"sparks": total, "step": s["step"]}, events=events)

    def _blocked(self, p: dict | None, user: int) -> str | None:
        if p is None or p["ended_at"] is not None:
            return "Пары уже нет."
        if user not in (p["u1"], p["u2"]):
            return "Это не ваша пара."
        if p["state"] == "quarrel":
            return "💢 Вы в ссоре: искры кончились, действия закрыты. Помирят любые искры — «пара пополнить 100»."
        if p["offended_by"] and p["offended_by"] != user:
            return "😢 Твоя половинка обижена: действия и РП закрыты, пока она не простит («пара обида»)."
        return None

    async def rp(self, pid: int, user: int, word: str, now: int) -> Result:
        item = data.find_rp(word)
        if item is None:
            return Result(False, "Нет такого действия.")
        p, events = await self.settle(pid, now)
        if p is None:
            return Result(False, "Пары уже нет.", events=events)
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            err = self._blocked(p, user)
            if err:
                return Result(False, err, events=events)
            side = side_of(p, user)
            day = eco.day_index(now)
            if p["day"] != day:
                p.update(day=day, mask=0, n1=0, n2=0, rp1=0, rp2=0)
            counted = p[f"rp{side}"] < eco.RP_WARMTH_PER_DAY
            warmth = eco.RP_WARMTH if counted else 0
            if counted:
                p[f"rp{side}"] += 1
            events += await self._quest_progress(p, "rp", 1, now)
            events += await self._grow(p, warmth, now)
            await self._save(pid, {k: p[k] for k in ("sparks", "warmth", "level", "day", "mask", "n1", "n2", "rp1", "rp2")}
                             | {"last_active": now})
            await self.db.conn.execute(
                "INSERT INTO pair_counters(pair_id,kind,n) VALUES(?,?,1) ON CONFLICT(pair_id,kind) DO UPDATE SET n=pair_counters.n+1",
                (pid, item.counter))
            await self.db.conn.commit()
            return Result(True, info={"rp": item, "warmth": warmth}, events=events)

    async def toggle_offense(self, pid: int, user: int, now: int) -> Result:
        async with _lock(pid), self.db.atomic():
            p = await self.get_by_id(pid, for_update=True)
            if p is None or p["ended_at"] is not None or user not in (p["u1"], p["u2"]):
                return Result(False, "Пары уже нет.")
            offended = p["offended_by"] != user and not p["offended_by"]
            if p["offended_by"] and p["offended_by"] != user:
                return Result(False, "Обиделась ваша половинка, а не вы: простить может только она.")
            new = user if offended else 0
            await self._save(pid, {"offended_by": new, "last_active": now})
            await self.db.conn.commit()
            return Result(True, info={"offended": bool(new)})

    # ---------- списки ----------
    async def history(self, pid: int, page: int, per: int = 10, kind: str = "all", now: int | None = None):
        now = int(time.time()) if now is None else now
        since = now - 30 * eco.DAY
        cond = {"all": "", "in": " AND amount>0", "out": " AND amount<0"}[kind]
        total = (await self._one(f"SELECT COUNT(*) AS n FROM pair_log WHERE pair_id=? AND ts>=? AND amount<>0{cond}",
                                 (pid, since)))["n"]
        rows = await self._all(
            f"SELECT * FROM pair_log WHERE pair_id=? AND ts>=? AND amount<>0{cond} ORDER BY ts DESC, id DESC LIMIT ? OFFSET ?",
            (pid, since, per, max(page, 0) * per))
        return rows, total

    async def list_chat(self, chat: int, now: int) -> tuple[list[dict], int]:
        rows = await self._all("SELECT * FROM pairs WHERE chat_id=? AND ended_at IS NULL ORDER BY created ASC, id", (chat,))
        awake = [r for r in rows if not is_sleeping(r, now)]
        return awake, len(rows) - len(awake)

    async def top(self, chat: int, by: str, now: int, limit: int = 10) -> list[dict]:
        rows, _ = await self.list_chat(chat, now)
        if by == "искры":
            rows.sort(key=lambda r: -r["sparks"])
        elif by == "длительность":
            rows.sort(key=lambda r: r["created"])
        elif by == "активность":
            totals = {r["pair_id"]: r["n"] for r in await self._all(
                "SELECT pair_id, SUM(n) AS n FROM pair_counters GROUP BY pair_id")}
            rows.sort(key=lambda r: -totals.get(r["id"], 0))
            for r in rows:
                r["activity"] = totals.get(r["id"], 0)
        else:
            rows.sort(key=lambda r: (-r["level"], -r["warmth"]))
        return rows[:limit]

    async def due(self, now: int, limit: int = 500) -> list[dict]:
        """Пары, которым пора что-то досчитать: содержание, конец ссоры, предупреждение для бедных кошельков."""
        return await self._all(
            "SELECT * FROM pairs WHERE ended_at IS NULL AND ((state='ok' AND (upkeep_at<=? OR sparks<?)) OR "
            "(state='quarrel' AND quarrel_until<=?) OR "
            "(state='ok' AND id IN (SELECT pair_id FROM pair_houses WHERE bill_at<=?)) OR "
            "id IN (SELECT pair_id FROM pair_pets WHERE egg=1) OR id IN (SELECT pair_id FROM pair_baby) OR id IN (SELECT pair_id FROM pair_children WHERE grown=0)) LIMIT ?",
            (now, WARN_SPARKS, now, now, limit))

    # ---------- перенос старых браков и отношений ----------
    async def migrate_legacy(self, now: int | None = None) -> dict[str, int]:
        """Одноразово (идемпотентно): старые браки и отношения становятся парами. Тепло — по сроку вместе."""
        now = int(time.time()) if now is None else now
        done = {"marriage": 0, "relation": 0, "skipped": 0}
        for table, stage, sparks, per_day, cap in (("marriages", "marriage", 500, 20, 3000), ("relations", "relation", 200, 15, 2000)):
            try:
                rows = await self._all(f"SELECT * FROM {table}")
            except Exception:
                continue
            for r in rows:
                key = f"{stage[0]}:{r['chat_id']}:{r['u1']}:{r['u2']}"
                if await self._one("SELECT 1 AS x FROM pairs WHERE legacy_key=?", (key,)):
                    continue
                if await self.get(r["chat_id"], r["u1"]) or await self.get(r["chat_id"], r["u2"]):
                    done["skipped"] += 1
                    continue
                days = max((now - (r["since"] or now)) // eco.DAY, 0)
                await self.create(r["chat_id"], r["u1"], r["u2"], now, stage, sparks=sparks,
                                  warmth=min(days * per_day, cap), created=r["since"], legacy_key=key)
                done[stage] += 1
        return done


TOPUP_DAILY = 2000        # искр в сутки на пару можно докупить монетами
WARN_SPARKS = 400         # бедные кошельки проверяем чаще, чтобы вовремя предупредить
