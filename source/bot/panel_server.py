"""Веб-панель (Mini App): страница /panel и JSON API /panel/api/*.

Безопасность: каждый запрос API несёт подписанный Telegram initData (заголовок X-Init-Data, проверка HMAC, свежесть ≤ 1 часа);
пользователь определяется только по подписанным данным. Права проверяются НА СЕРВЕРЕ при каждом запросе — по реальному статусу в
Telegram и рангам бота (то, что прислала страница, ничему не доверяем). Чат должен быть известен боту, а пользователь — иметь в нём
ранг; чужие и неизвестные чаты дают 403. Есть лимит частоты на пользователя, ответы не кэшируются и не содержат секретов."""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import aiogram
from aiohttp import web

from bot import bulk
from bot import mod_service as ms
from bot import i18n, purge, ux
from bot.captcha_server import WEBAPP_DIR, validate_init_data
from bot.db import DAY, HOUR, Database
from bot.filters import MAX_FILTERS, MAX_WORD_LEN, FilterError, normalize, validate_regex
from bot.handlers import owner as owner_mod
from bot.handlers.logchat import connect_log_chat
from bot.handlers.reports import apply_report_action
from bot.handlers.settings import PAGES, allowed_values
from bot.links import normalize_domain
from bot.parsing import parse_duration
from bot.ranks import DEFAULT_ACCESS, MAX_ASSIGNABLE, need_rank, tg_rank

UID = web.RequestKey("uid", int)
UINFO = web.RequestKey("uinfo", dict)
PAGE_SIZE = 10
TEXT_KEYS = ("rules", "welcome")
MAX_TEXT = 2000
CSP = ("default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; "
       "frame-ancestors https://web.telegram.org https://webk.telegram.org https://webz.telegram.org")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@dataclass
class PanelContext:
    bot: object
    db: Database
    bot_token: str
    owner_ids: frozenset
    rt: object
    ai: object = None
    webapp_url: str = ""
    rate_limit: int = 120          # запросов в минуту на пользователя
    max_age: int = 3600
    trusted_proxy_ips: frozenset[str] = frozenset()
    _hits: dict = field(default_factory=dict)
    _bad: dict = field(default_factory=dict)

    def is_owner(self, uid: int) -> bool:
        return uid in self.owner_ids


async def _json(request: web.Request) -> dict:
    try:
        body = await request.json()
    except web.HTTPRequestEntityTooLarge:
        raise
    except Exception:
        raise ApiError(400, "Ожидался JSON")
    if not isinstance(body, dict):
        raise ApiError(400, "Ожидался JSON-объект")
    return body


def _int(v, name: str, lo: int | None = None, hi: int | None = None) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not -(2**63) <= v < 2**63 or (lo is not None and v < lo) or (hi is not None and v > hi):
        raise ApiError(400, f"Некорректное значение: {name}")
    return v


async def _name(db: Database, uid: int | None) -> str:
    if not uid:
        return "—"
    return (await db.user_name(uid)) or f"id{uid}"


def add_panel_routes(app: web.Application, ctx: PanelContext) -> None:
    db, bot = ctx.db, ctx.bot

    # ---------- middleware: подпись, лимит, единый формат ошибок ----------
    @web.middleware
    async def guard(request: web.Request, handler):
        now = time.monotonic()
        ip = request.remote or "?"
        if ip in ctx.trusted_proxy_ips:
            ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or ip)[:64]
        data = validate_init_data(request.headers.get("X-Init-Data", ""), ctx.bot_token, max_age=ctx.max_age)
        uid = data["user"].get("id") if data else None
        if type(uid) is not int:
            # Ограничение неудачных входов не блокирует уже подписанные запросы через общий прокси.
            if ip not in ctx._bad and len(ctx._bad) >= 2000:
                for k in [k for k, q in ctx._bad.items() if not q or now - q[-1] > 60]:
                    ctx._bad.pop(k, None)
                if len(ctx._bad) >= 2000:
                    ctx._bad.pop(next(iter(ctx._bad)))
            bad = ctx._bad.setdefault(ip, deque())
            while bad and now - bad[0] > 60:
                bad.popleft()
            if len(bad) >= 30:
                return web.json_response({"error": "too many requests"}, status=429, headers={"Cache-Control": "no-store"})
            bad.append(now)
            return web.json_response({"error": "unauthorized"}, status=401, headers={"Cache-Control": "no-store"})
        hits = ctx._hits.setdefault(uid, deque())
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= ctx.rate_limit:
            return web.json_response({"error": "too many requests"}, status=429, headers={"Cache-Control": "no-store"})
        hits.append(now)
        if len(ctx._hits) > 2000:                               # не копим пустые очереди давно ушедших пользователей
            for k in [k for k, q in ctx._hits.items() if not q or now - q[-1] > 60]:
                ctx._hits.pop(k, None)
            ctx._hits.setdefault(uid, hits)
        request[UID], request[UINFO] = uid, data["user"]
        try:
            resp = await handler(request)
        except ApiError as e:
            resp = web.json_response({"error": e.message}, status=e.status)
        except web.HTTPException:
            raise
        except Exception:
            logging.exception("panel api error")
            resp = web.json_response({"error": "internal error"}, status=500)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    api = web.Application(middlewares=[guard])

    # ---------- права ----------
    async def rank_in(cid: int, uid: int) -> int:
        if ctx.is_owner(uid):
            return 5
        try:
            # В панели статус проверяется заново: старый кэш или выданный ранг
            # не дают доступ вышедшему/исключённому участнику. Сбой Telegram закрывает доступ.
            member = await bot.get_chat_member(cid, uid)
            if member.status in ("left", "kicked") or (member.status == "restricted" and not member.is_member):
                return 0
            return max(await db.get_rank(cid, uid),
                       tg_rank(member.status, getattr(member, "can_restrict_members", False)))
        except Exception:
            return 0

    async def chat_access(request: web.Request, key: str | None = None) -> tuple[int, int]:
        try:
            cid = int(request.match_info["cid"])
            if not -(2**63) <= cid < 2**63:
                raise ValueError
        except (KeyError, ValueError):
            raise ApiError(403, "forbidden")
        if await db.get_chat(cid) is None:
            raise ApiError(403, "forbidden")                    # неизвестный чат — как «нет доступа», без подсказок
        rank = await rank_in(cid, request[UID])
        need = 1 if key is None else max(need_rank(await db.get_access(cid), key), 1)
        if rank < need:
            raise ApiError(403, "forbidden")
        return cid, rank

    async def owner_only(request: web.Request) -> int:
        if not ctx.is_owner(request[UID]):
            raise ApiError(403, "forbidden")
        return request[UID]

    # ---------- /me ----------
    async def me(request: web.Request):
        uid = request[UID]
        chats = await db.list_chats(0, 500, active_only=True)
        sem = asyncio.Semaphore(8)

        async def one(c):
            async with sem:
                return c, await rank_in(c["chat_id"], uid)
        out = []
        for c, rank in await asyncio.gather(*(one(c) for c in chats)):
            if rank >= 1:
                out.append({"id": c["chat_id"], "title": c["title"] or str(c["chat_id"]), "rank": rank})
        return web.json_response({"user": {"id": uid, "name": request[UINFO].get("first_name", "")},
                                  "is_owner": ctx.is_owner(uid), "chats": out})

    # ---------- настройки ----------
    def want_en(request) -> bool:
        lang = (request.headers.get("X-Lang") or request[UINFO].get("language_code") or "ru").lower()
        return lang.startswith("en")

    def spec(en: bool = False) -> list[dict]:
        T = (lambda s: i18n.translate_button(s, "en")) if en else (lambda s: s)
        pages = []
        for pid, (title, rows) in PAGES.items():
            pr = []
            for row in rows:
                if row[0] == "toggle":
                    pr.append({"type": "toggle", "key": row[1], "label": T(row[2])})
                else:
                    pr.append({"type": "choice", "key": row[1], "label": T(row[2]), "values": [[T(t), v] for t, v in row[3]]})
            pages.append({"id": pid, "title": T(title), "rows": pr})
        return pages

    setting_keys = {row[1] for _, rows in PAGES.values() for row in rows}

    async def settings_get(request):
        cid, _ = await chat_access(request, "настройки чата")
        cfg = await db.get_settings(cid)
        return web.json_response({"pages": spec(want_en(request)), "values": {k: cfg[k] for k in setting_keys}})

    async def settings_set(request):
        cid, _ = await chat_access(request, "настройки чата")
        body = await _json(request)
        key, value = body.get("key"), body.get("value")
        if not isinstance(key, str) or key not in setting_keys or isinstance(value, bool) or not isinstance(value, (int, str)) \
                or str(value) not in allowed_values(key):
            raise ApiError(400, "Недопустимая настройка или значение")
        await db.set_setting(cid, key, value, actor=request[UID])
        return web.json_response({"ok": True})

    # ---------- фильтры ----------
    async def filters_get(request):
        cid, _ = await chat_access(request, "фильтры")
        return web.json_response({"filters": await db.list_filters(cid), "limit": MAX_FILTERS})

    async def filters_add(request):
        cid, _ = await chat_access(request, "фильтры")
        body = await _json(request)
        kind, pattern = body.get("kind"), body.get("pattern")
        if kind not in ("word", "regex") or not isinstance(pattern, str):
            raise ApiError(400, "Нужны kind (word|regex) и pattern")
        pattern = " ".join(pattern.split()) if kind == "word" else pattern.strip()
        if kind == "word":
            if not pattern or len(pattern) > MAX_WORD_LEN or not normalize(pattern):
                raise ApiError(400, f"Слово или фраза: от 1 до {MAX_WORD_LEN} символов")
        else:
            try:
                validate_regex(pattern)
            except FilterError as e:
                raise ApiError(400, str(e))
        existing = await db.list_filters(cid)
        if any(f["kind"] == kind and f["pattern"] == pattern for f in existing):
            raise ApiError(409, "Такой фильтр уже есть")
        fid = await db.add_filter(cid, kind, pattern, request[UID], int(time.time()), limit=MAX_FILTERS)
        if fid is None:
            raise ApiError(400, f"Достигнут лимит фильтров ({MAX_FILTERS})")
        return web.json_response({"id": fid})

    async def filters_del(request):
        cid, _ = await chat_access(request, "фильтры")
        try:
            fid = int(request.match_info["fid"])
        except ValueError:
            raise ApiError(400, "Некорректный номер")
        if not await db.delete_filter(cid, fid):
            raise ApiError(404, "Нет такого фильтра")
        return web.json_response({"ok": True})

    # ---------- белый список ссылок ----------
    async def links_get(request):
        cid, _ = await chat_access(request, "ссылки")
        return web.json_response({"links": sorted(await db.link_allow_set(cid)),
                                  "mode": (await db.get_settings(cid))["links_mode"]})

    async def links_add(request):
        cid, _ = await chat_access(request, "ссылки")
        dom = normalize_domain(str((await _json(request)).get("domain", "")))
        if dom is None:
            raise ApiError(400, "Не похоже на домен")
        await db.add_link(cid, dom, request[UID])
        return web.json_response({"domain": dom})

    async def links_remove(request):
        cid, _ = await chat_access(request, "ссылки")
        dom = normalize_domain(str((await _json(request)).get("domain", "")))
        if dom is None or not await db.remove_link(cid, dom):
            raise ApiError(404, "Такого домена нет в списке")
        return web.json_response({"ok": True})

    # ---------- журнал ----------
    async def log_get(request):
        cid, _ = await chat_access(request, "настройки чата")
        return web.json_response({"log_chat_id": (await db.get_settings(cid))["log_chat_id"]})

    async def log_set(request):
        cid, _ = await chat_access(request, "настройки чата")
        dest = (await _json(request)).get("chat_id")
        if isinstance(dest, bool) or not isinstance(dest, int):
            raise ApiError(400, "Нужен числовой chat_id (0 — отключить)")
        if dest == 0:
            await db.set_setting(cid, "log_chat_id", 0, actor=request[UID])
            return web.json_response({"ok": True})
        title = (await db.get_chat(cid) or {}).get("title") or str(cid)
        ok, info = await connect_log_chat(bot, db, cid, title, request[UID], dest)
        if not ok:
            raise ApiError(400, info)
        return web.json_response({"ok": True})

    # ---------- тексты ----------
    async def texts_get(request):
        cid, _ = await chat_access(request, "настройки чата")
        from bot import rules_text
        texts = {k: (await db.get_text(cid, k)) or "" for k in TEXT_KEYS}
        texts["rules"] = rules_text.to_plain(texts["rules"])      # оформление в панели не редактируется — показываем чистый текст
        return web.json_response({"texts": texts})

    async def texts_set(request):
        cid, _ = await chat_access(request, "настройки чата")
        body = await _json(request)
        key, text = body.get("key"), body.get("text")
        if key not in TEXT_KEYS or not isinstance(text, str) or len(text) > MAX_TEXT:
            raise ApiError(400, f"Нужны key ({'|'.join(TEXT_KEYS)}) и text до {MAX_TEXT} символов")
        await db.set_text(cid, key, text.strip() or None)
        return web.json_response({"ok": True})

    # ---------- ранги и доступ команд ----------
    async def ranks_get(request):
        cid, my = await chat_access(request)
        access = await db.get_access(cid)
        ranks = [{"user_id": r["user_id"], "name": await _name(db, r["user_id"]), "rank": r["rank"]}
                 for r in await db.list_ranks(cid)]
        return web.json_response({
            "my_rank": my, "ranks": ranks,
            "access": [{"command": c, "need": need_rank(access, c), "changed": c in access} for c in DEFAULT_ACCESS]})

    async def ranks_set(request):
        cid, actor = await chat_access(request, "модер")
        body = await _json(request)
        tid, new = _int(body.get("user_id"), "user_id"), _int(body.get("rank"), "rank", 0, 5)
        if tid == request[UID] or tid == bot.id:
            raise ApiError(400, "Себе или боту ранг менять нельзя")
        try:
            tg_status = (await ms.get_member(bot, cid, tid)).status
        except Exception:
            tg_status = "member"
        if tg_status in ("administrator", "creator"):
            raise ApiError(400, "Админы Telegram и создатель имеют ранг по статусу — менять его нельзя")
        old = await db.get_rank(cid, tid)
        if old >= actor:
            raise ApiError(400, "Ранг этого человека не ниже вашего")
        if new >= actor or new > MAX_ASSIGNABLE:
            raise ApiError(400, f"Выдать можно ранг не выше {min(actor - 1, MAX_ASSIGNABLE)}")
        now = int(time.time())
        await db.set_rank(cid, tid, new, request[UID], now)
        await ux.sync_tag(bot, cid, tid, new)
        await db.log_action(cid, request[UID], tid, "ранг", f"{old}→{new}", now)
        return web.json_response({"ok": True})

    async def access_set(request):
        cid, my = await chat_access(request, "настройки чата")
        body = await _json(request)
        cmd = body.get("command")
        if not isinstance(cmd, str) or cmd not in DEFAULT_ACCESS:
            raise ApiError(400, "Неизвестная команда")
        need = _int(body.get("rank"), "rank", 1, 5)          # 0 («всем») запрещён: небезопасно
        if need > my:
            raise ApiError(400, f"Нельзя требовать ранг выше вашего ({my})")
        await db.set_access(cid, cmd, need)
        return web.json_response({"ok": True})

    async def access_reset(request):
        cid, _ = await chat_access(request, "настройки чата")
        await db.reset_access(cid)
        return web.json_response({"ok": True})

    # ---------- жалобы ----------
    async def reports_get(request):
        cid, _ = await chat_access(request, "варн")
        items = []
        for r in await db.list_reports(cid, 50):
            items.append({"id": r["id"], "status": r["status"], "ts": r["ts"], "text": r["text"], "reason": r["reason"],
                          "message_id": r["message_id"],
                          "reporter": {"id": r["reporter"], "name": await _name(db, r["reporter"])},
                          "target": {"id": r["target"], "name": await _name(db, r["target"])},
                          "handled_by": r["handled_by"]})
        return web.json_response({"reports": items})

    async def reports_act(request):
        cid, _ = await chat_access(request, "варн")
        try:
            rid = int(request.match_info["rid"])
        except ValueError:
            raise ApiError(400, "Некорректный номер")
        rep = await db.get_report(rid)
        if rep is None or rep["chat_id"] != cid:
            raise ApiError(404, "Жалоба не найдена")
        act = (await _json(request)).get("action")
        if act not in ("del", "mute", "ban", "dismiss"):
            raise ApiError(400, "Действие: del | mute | ban | dismiss")
        ok, info = await apply_report_action(bot, db, rep, act, request[UID], int(time.time()))
        if not ok:
            raise ApiError(409 if info == "Уже обработано" else 502 if info.startswith("Не получилось")
                           else 400 if info.startswith("У этой жалобы") else 403, info)
        return web.json_response({"ok": True, "result": info})

    # ---------- история ----------
    async def history_get(request):
        cid, _ = await chat_access(request, "история")
        q = request.query.get("user", "").strip()
        if not q:
            raise ApiError(400, "Укажите user: @ник или id")
        uid = await db.find_user(q) if q.startswith("@") else (int(q) if q.lstrip("-").isdigit() else None)
        if uid is not None and not 0 < uid < 2**63:
            raise ApiError(400, "Некорректный id пользователя")
        if uid is None:
            raise ApiError(404, "Пользователь не найден")
        try:
            page = max(int(request.query.get("page", "0")), 0)
            if page > 1000000:
                raise ValueError
        except ValueError:
            raise ApiError(400, "Некорректная страница")
        now = int(time.time())
        total = await db.count_mod_history(cid, uid)
        items = [{"ts": r["ts"], "action": r["action"], "duration": r["duration"], "reason": r["reason"],
                  "actor": {"id": r["actor_id"], "name": await _name(db, r["actor_id"])}}
                 for r in await db.list_mod_history(cid, uid, PAGE_SIZE, page * PAGE_SIZE)]
        active = {}
        for kind in ("ban", "mute"):
            st = await db.get_state(cid, uid, kind, now)
            if st:
                active[kind] = st["until"]
        rt_total, rt_open = await db.count_reports_against(cid, uid)
        return web.json_response({"user": {"id": uid, "name": await _name(db, uid)}, "total": total, "page": page,
                                  "pages": max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1), "items": items,
                                  "warns": await db.get_warns(cid, uid, now), "active": active,
                                  "reports": {"total": rt_total, "open": rt_open}})

    # ---------- статистика ----------
    async def stats_get(request):
        cid, _ = await chat_access(request)
        try:
            hours = int(request.query.get("hours", "168"))
        except ValueError:
            raise ApiError(400, "hours должно быть числом")
        if not 1 <= hours <= 24 * 90:
            raise ApiError(400, "hours: от 1 до 2160")
        since = int(time.time()) - hours * HOUR
        bucket = HOUR if hours <= 72 else DAY
        series = await db.activity_series(cid, since, bucket)
        total, top = await db.count_by_user(cid, since, 15)
        return web.json_response({"bucket": "hour" if bucket == HOUR else "day", "series": series, "total": total,
                                  "top": [{"user_id": u, "name": await _name(db, u), "n": n} for u, n in top]})

    async def charts_get(request):
        cid, _ = await chat_access(request)
        s = await db.get_settings(cid)
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime
            off = int(datetime.now(ZoneInfo(s["tz"])).utcoffset().total_seconds())
        except Exception:
            off = 0
        data = await db.charts_data(cid, int(time.time()) - 30 * DAY, off)
        data["members"] = await db.member_count(cid)
        return web.json_response(data)

    # ---------- массовый бан ----------
    async def bulk_ban(request):
        cid, _ = await chat_access(request, "массовый бан")
        body = await _json(request)
        reason = body.get("reason") or ""
        if not isinstance(reason, str) or len(reason) > 200:
            raise ApiError(400, "Причина: до 200 символов")
        dur = body.get("duration") or None
        duration = None
        if dur is not None:
            duration = parse_duration(dur) if isinstance(dur, str) else None
            if duration is None:
                raise ApiError(400, "Срок: например 1д, 7д, 12ч; пусто — навсегда")
        try:
            targets, invalid = bulk.parse_targets(body.get("targets"))
        except bulk.BulkError as e:
            raise ApiError(400, str(e))
        if not targets:
            raise ApiError(400, "Не нашёл ни одного id или @ника")
        try:
            res = await bulk.bulk_ban(bot, db, cid, request[UID], targets, reason.strip(), duration, int(time.time()))
        except PermissionError as e:
            raise ApiError(403, str(e))
        out = [{"target": o.target, "status": o.status, "detail": o.detail, "user_id": o.user_id, "name": o.name}
               for o in res]
        count = {k: sum(1 for o in res if o.status == k) for k in ("ok", "pending", "skipped", "failed")}
        return web.json_response({"results": out, "invalid": invalid, "count": count})

    async def pending_get(request):
        cid, _ = await chat_access(request, "массовый бан")
        rows = await db.list_pending_bans(cid, int(time.time()))
        return web.json_response({"pending": [{"username": r["username"], "reason": r["reason"], "ts": r["ts"],
                                               "duration": r["duration"]} for r in rows]})

    async def pending_remove(request):
        cid, _ = await chat_access(request, "массовый бан")
        name = (await _json(request)).get("username")
        if not isinstance(name, str) or not await db.remove_pending_ban(cid, name):
            raise ApiError(404, "Такого отложенного бана нет")
        return web.json_response({"ok": True})

    # ---------- очистка чата ----------
    async def purge_access(request) -> int:
        cid, rank = await chat_access(request, "очистить чат")
        if rank < purge.MIN_RANK:
            raise ApiError(403, "forbidden")
        return cid

    async def purge_get(request):
        cid = await purge_access(request)
        job = purge.get_job(cid)
        return web.json_response(job.public() if job else {"state": "idle"})

    async def purge_start(request):
        cid = await purge_access(request)
        phrase = (await _json(request)).get("confirm")
        if not isinstance(phrase, str) or phrase.strip().upper() != purge.CONFIRM_PHRASE:
            raise ApiError(400, f"Для подтверждения введите: {purge.CONFIRM_PHRASE}")
        try:
            job = await purge.start_purge(bot, db, cid, request[UID])
        except purge.PurgeError as e:
            raise ApiError(409, str(e))
        await db.log_action(cid, request[UID], 0, "очистка чата", "запущена через веб-панель", int(time.time()))
        return web.json_response(job.public())

    async def purge_stop(request):
        cid = await purge_access(request)
        if not purge.stop_job(cid):
            raise ApiError(404, "Очистка сейчас не идёт")
        return web.json_response({"ok": True})

    # ---------- владелец бота ----------
    async def owner_status(request):
        await owner_only(request)
        rt = ctx.rt
        return web.json_response({
            "uptime": int(time.time() - rt.started_at), "users": await db.count_users(),
            "chats_active": await db.count_chats(active_only=True), "chats_total": await db.count_chats(),
            "banned_users": len(rt.banned_users), "banned_chats": len(rt.banned_chats),
            "db_bytes": await db.size_bytes(), "db_backend": db.backend,
            "flags": {k: rt.flag(k) for k in ("ai", "stt", "nsfw", "aimod")}, "maintenance": rt.maintenance,
            "ai_configured": bool(getattr(ctx.ai, "has_river", False)), "stt_configured": bool(getattr(ctx.ai, "has_stt", False)),
            "aiogram": aiogram.__version__})

    async def owner_chats(request):
        await owner_only(request)
        return web.json_response({"chats": [
            {"id": c["chat_id"], "title": c["title"] or str(c["chat_id"]), "type": c["type"], "active": bool(c["active"]),
             "members": await db.member_count(c["chat_id"]), "banned": c["chat_id"] in ctx.rt.banned_chats}
            for c in await db.list_chats(0, 500)]})

    async def owner_users(request):
        await owner_only(request)
        q = request.query.get("q", "")[:64]
        return web.json_response({"users": [
            {"id": u["user_id"], "username": u["username"], "name": u["name"], "banned": u["user_id"] in ctx.rt.banned_users}
            for u in await db.search_users(q, 50)]})

    async def owner_bans(request):
        await owner_only(request)
        return web.json_response({"users": [{"id": b["id"], "reason": b["reason"]} for b in await db.list_bot_bans("user")],
                                  "chats": [{"id": b["id"], "reason": b["reason"]} for b in await db.list_bot_bans("chat")]})

    async def owner_ban(request):
        oid = await owner_only(request)
        body = await _json(request)
        uid, ban = _int(body.get("user_id"), "user_id"), body.get("ban")
        if not isinstance(ban, bool):
            raise ApiError(400, "ban должен быть true/false")
        if uid in ctx.owner_ids:
            raise ApiError(400, "Владельца заблокировать нельзя")
        now = int(time.time())
        if ban:
            await db.bot_ban("user", uid, "владелец (веб-панель)", now)
            ctx.rt.banned_users.add(uid)
        else:
            await db.bot_unban("user", uid)
            ctx.rt.banned_users.discard(uid)
        await db.log_owner(oid, "бан в боте" if ban else "разбан в боте", f"user {uid} (веб-панель)", now)
        return web.json_response({"ok": True})

    async def owner_flags_get(request):
        await owner_only(request)
        state = {"ai": ctx.rt.flag("ai"), "stt": ctx.rt.flag("stt"), "nsfw": ctx.rt.flag("nsfw"),
                 "aimod": ctx.rt.flag("aimod"), "maint": ctx.rt.maintenance}
        return web.json_response({"flags": [{"key": k, "label": i18n.translate_button(lbl, "en") if want_en(request) else lbl, "value": state[k]}
                                            for k, (_, lbl) in owner_mod.FLAGS.items()]})

    async def owner_flags_set(request):
        oid = await owner_only(request)
        body = await _json(request)
        key, value = body.get("key"), _int(body.get("value"), "value", 0, 1)
        if not isinstance(key, str) or key not in owner_mod.FLAGS:
            raise ApiError(400, "Неизвестная функция")
        await db.set_global(owner_mod.FLAGS[key][0], value)
        ctx.rt.apply_globals(await db.get_global())
        await db.log_owner(oid, "функция", f"{key}={value} (веб-панель)", int(time.time()))
        return web.json_response({"ok": True})

    async def owner_backup(request):
        oid = await owner_only(request)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bot-backup.db" if db.backend == "sqlite" else "bot-backup.dump")
            await db.backup_to(path)
            data = await asyncio.to_thread(Path(path).read_bytes)   # база может весить сотни МБ — не блокируем цикл
        await db.log_owner(oid, "бэкап", "скачан через веб-панель", int(time.time()))
        return web.Response(body=data, content_type="application/octet-stream", headers={
            "Content-Disposition": f'attachment; filename="{os.path.basename(path)}"'})

    r = api.router
    r.add_get("/me", me)
    r.add_get("/chats/{cid}/settings", settings_get)
    r.add_post("/chats/{cid}/settings", settings_set)
    r.add_get("/chats/{cid}/filters", filters_get)
    r.add_post("/chats/{cid}/filters", filters_add)
    r.add_delete("/chats/{cid}/filters/{fid}", filters_del)
    r.add_get("/chats/{cid}/links", links_get)
    r.add_post("/chats/{cid}/links", links_add)
    r.add_post("/chats/{cid}/links/remove", links_remove)
    r.add_get("/chats/{cid}/log", log_get)
    r.add_post("/chats/{cid}/log", log_set)
    r.add_get("/chats/{cid}/texts", texts_get)
    r.add_post("/chats/{cid}/texts", texts_set)
    r.add_get("/chats/{cid}/ranks", ranks_get)
    r.add_post("/chats/{cid}/ranks", ranks_set)
    r.add_post("/chats/{cid}/access", access_set)
    r.add_post("/chats/{cid}/access/reset", access_reset)
    r.add_get("/chats/{cid}/reports", reports_get)
    r.add_post("/chats/{cid}/reports/{rid}", reports_act)
    r.add_get("/chats/{cid}/history", history_get)
    r.add_get("/chats/{cid}/stats", stats_get)
    r.add_get("/chats/{cid}/charts", charts_get)
    r.add_post("/chats/{cid}/bulk-ban", bulk_ban)
    r.add_get("/chats/{cid}/pending-bans", pending_get)
    r.add_post("/chats/{cid}/pending-bans/remove", pending_remove)
    r.add_get("/chats/{cid}/purge", purge_get)
    r.add_post("/chats/{cid}/purge", purge_start)
    r.add_post("/chats/{cid}/purge/stop", purge_stop)
    r.add_get("/owner/status", owner_status)
    r.add_get("/owner/chats", owner_chats)
    r.add_get("/owner/users", owner_users)
    r.add_get("/owner/bans", owner_bans)
    r.add_post("/owner/ban", owner_ban)
    r.add_get("/owner/flags", owner_flags_get)
    r.add_post("/owner/flags", owner_flags_set)
    r.add_get("/owner/backup", owner_backup)

    async def page(request: web.Request) -> web.StreamResponse:
        resp = web.FileResponse(WEBAPP_DIR / "panel.html")
        resp.headers["Content-Security-Policy"] = CSP
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    app.router.add_get("/panel", page)
    app.add_subapp("/panel/api", api)
