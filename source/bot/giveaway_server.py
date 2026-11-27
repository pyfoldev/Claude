"""Mini App конкурса: страница /giveaway, сведения, картинка-капча и запись в участники.

Каждый запрос несёт подписанный Telegram initData (заголовок X-Init-Data): личность берётся только из него. Сервер сам
проверяет, что конкурс идёт, человек — участник чата, и капча решена (попытки — в БД, занимаются до сравнения)."""
from __future__ import annotations

import asyncio
import time

from aiohttp import web

from bot import giveaway as gw
from bot import members
from bot.captcha_server import PAGE_HEADERS, WEBAPP_DIR, answer_matches, new_code, render_image, validate_init_data
from bot.db import Database

CODE_LEN = 5
MAX_ATTEMPTS = 5
CHECK_TTL = 600            # новая картинка — не раньше чем через 10 минут после исчерпания попыток
INIT_MAX_AGE = 3600


def add_giveaway_routes(app: web.Application, db: Database, bot, bot_token: str) -> None:
    image_slots = asyncio.Semaphore(4)
    def err(status: int, code: str, text: str) -> web.Response:
        return web.json_response({"ok": False, "error": code, "message": text}, status=status,
                                 headers={"Cache-Control": "no-store"})

    async def context(request: web.Request, gid_raw) -> tuple[int, dict] | web.Response:
        data = validate_init_data(request.headers.get("X-Init-Data", ""), bot_token, max_age=INIT_MAX_AGE)
        uid = data["user"].get("id") if data and isinstance(data.get("user"), dict) else None
        if not isinstance(uid, int):
            return err(401, "auth", "Откройте конкурс из Telegram.")
        try:
            if isinstance(gid_raw, bool) or not isinstance(gid_raw, (int, str)):
                raise ValueError
            gid = int(gid_raw)
            if not 0 < gid < 2**63:
                raise ValueError
        except (TypeError, ValueError):
            return err(400, "bad", "Нет такого конкурса.")
        g = await db.gw_get(gid)
        if g is None or g["status"] != "active" or g["ends_at"] <= time.time():
            return err(410, "closed", "Конкурс уже завершён или не найден.")
        return uid, g

    async def page(request: web.Request) -> web.StreamResponse:
        resp = web.FileResponse(WEBAPP_DIR / "giveaway.html")
        resp.headers.update(PAGE_HEADERS)
        return resp

    async def info(request: web.Request) -> web.Response:
        ctx = await context(request, request.query.get("id"))
        if isinstance(ctx, web.Response):
            return ctx
        uid, g = ctx
        tz = gw.tz_of((await db.get_settings(g["chat_id"]))["tz"])
        chat = await db.get_chat(g["chat_id"]) or {}
        return web.json_response({"ok": True, "id": g["id"], "chat": chat.get("title") or "", "winners": g["winners"],
                                  "ends": gw.fmt_time(g["ends_at"], tz), "count": await db.gw_count(g["id"]),
                                  "joined": await db.gw_joined(g["id"], uid)}, headers={"Cache-Control": "no-store"})

    async def image(request: web.Request) -> web.Response:
        ctx = await context(request, request.query.get("id"))
        if isinstance(ctx, web.Response):
            return ctx
        uid, g = ctx
        now = int(time.time())
        chk = await db.gw_check_get(g["id"], uid)
        if chk is not None and chk["attempts"] >= MAX_ATTEMPTS and chk["expires_at"] > now:
            return err(429, "attempts", "Слишком много неверных попыток. Попробуйте через 10 минут.")
        if chk is None or chk["expires_at"] <= now or chk["attempts"] >= MAX_ATTEMPTS:
            await db.gw_check_new(g["id"], uid, new_code(CODE_LEN), now + CHECK_TTL, now)
            chk = await db.gw_check_get(g["id"], uid)
        seed = f"gw:{g['id']}:{uid}:{chk['expires_at']}:{chk['answer']}"   # одна и та же картинка: перезагрузкой не набрать вариантов
        async with image_slots:
            png = await asyncio.to_thread(render_image, chk["answer"], seed, 1)
        return web.Response(body=png, content_type="image/png",
                            headers={"Cache-Control": "no-store", "X-Code-Length": str(len(chk["answer"]))})

    async def join(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise TypeError
            answer = body["answer"]
            if not isinstance(answer, str):
                raise TypeError
        except (KeyError, ValueError, TypeError):
            return err(400, "bad", "Некорректный запрос.")
        ctx = await context(request, body.get("id"))
        if isinstance(ctx, web.Response):
            return ctx
        uid, g = ctx
        if await db.gw_joined(g["id"], uid):
            return web.json_response({"ok": True, "already": True, "count": await db.gw_count(g["id"])})
        if await members.check(bot, db, g["chat_id"], uid) is not True:
            return err(403, "member", "Участвовать могут только участники чата. Вступите в чат и попробуйте снова.")
        chk = await db.gw_check_get(g["id"], uid)
        if chk is None or chk["expires_at"] <= time.time():
            return err(409, "expired", "Картинка устарела — обновите её.")
        if not await db.gw_check_attempt(g["id"], uid, MAX_ATTEMPTS, chk["answer"], int(time.time())):
            return err(429, "attempts", "Слишком много неверных попыток. Попробуйте через 10 минут.")
        if not answer_matches(answer, str(chk["answer"])):
            left = MAX_ATTEMPTS - chk["attempts"] - 1
            return err(400, "wrong", f"Неверный код. Осталось попыток: {left}." if left > 0 else
                       "Неверный код. Попытки кончились — попробуйте через 10 минут.")
        if not await db.gw_join(g["id"], uid, int(time.time())):
            if await db.gw_joined(g["id"], uid):
                return web.json_response({"ok": True, "already": True, "count": await db.gw_count(g["id"])}, headers={"Cache-Control": "no-store"})
            return err(410, "closed", "Конкурс уже завершён.")
        await db.gw_check_done(g["id"], uid)
        return web.json_response({"ok": True, "count": await db.gw_count(g["id"])}, headers={"Cache-Control": "no-store"})

    app.router.add_get("/giveaway", page)
    app.router.add_get("/giveaway/api/info", info)
    app.router.add_get("/giveaway/api/image", image)
    app.router.add_post("/giveaway/api/join", join)
