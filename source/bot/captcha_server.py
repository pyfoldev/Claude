"""Веб-часть капчи: проверка initData Mini App и приём ответа.

Основная капча — Cloudflare Turnstile (нужны ключи TURNSTILE_SITEKEY и TURNSTILE_SECRET в .env; домен из WEBAPP_URL добавьте
в список хостов виджета в панели Cloudflare). Виджет показывается в Mini App, а полученный токен сервер проверяет у Cloudflare
(siteverify), сверяя cdata с токеном капчи, чтобы чужой ответ нельзя было подсунуть. Без ключей остаётся прежняя капча
с картинкой и кодом — бот не остаётся без защиты."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import logging
import os
import random
import secrets
import time
from pathlib import Path
from functools import lru_cache
from urllib.parse import parse_qsl

import aiohttp
from aiohttp import web
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from bot.db import Database

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # без 0/O, 1/I/L — их путают
CODE_LEN = 5
MAX_ATTEMPTS = 5
# сложность: (длина кода, макс. попыток). 0 — обычная, 1 — повышенная (волна неудач в чате), 2 — усиленная (рейд)
LEVELS = {0: (5, 5), 1: (6, 4), 2: (6, 3)}


# как у веб-панели: только свои скрипты и скрипт Telegram, картинка капчи приходит как blob:
CAPTCHA_CSP = ("default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; img-src 'self' blob: data:; "
               "connect-src 'self'; base-uri 'none'; form-action 'none'; "
               "frame-ancestors https://web.telegram.org https://webk.telegram.org https://webz.telegram.org")
PAGE_HEADERS = {"Content-Security-Policy": CAPTCHA_CSP, "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}


# страница капчи с Turnstile: разрешаем скрипт и iframe Cloudflare (inline-стили нужны самому виджету)
CAPTCHA_CSP_TS = ("default-src 'self'; script-src 'self' https://telegram.org https://challenges.cloudflare.com; "
                  "style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
                  "connect-src 'self' https://challenges.cloudflare.com; frame-src https://challenges.cloudflare.com; "
                  "base-uri 'none'; form-action 'none'; "
                  "frame-ancestors https://web.telegram.org https://webk.telegram.org https://webz.telegram.org")
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_ATTEMPTS = 5
# Попытки Turnstile считаем ОТДЕЛЬНО от попыток капчи-картинки (в памяти): раньше они делили один счётчик в БД, и человек, у которого
# Turnstile не прошёл (Cloudflare тормозит или заблокирован), сжигал попытки и не мог пройти запасную капчу с кодом.
_ts_attempts: dict[str, tuple[int, float]] = {}
_TS_TRACK_TTL = 24 * 3600
_TS_TRACKED_MAX = 5000
REPORT_MAX_BYTES = 1024
REPORT_PER_MINUTE = 30                      # репортов клиента в минуту с одного адреса (эндпоинт без авторизации)
_report_hits: dict[str, list[float]] = {}


def take_turnstile_attempt(token: str) -> bool:
    now = time.monotonic()
    n, expires = _ts_attempts.get(token, (0, now + _TS_TRACK_TTL))
    if expires <= now:
        n, expires = 0, now + _TS_TRACK_TTL
    if n >= TURNSTILE_ATTEMPTS:
        return False
    if token not in _ts_attempts and len(_ts_attempts) >= _TS_TRACKED_MAX:
        for key, (_, until) in list(_ts_attempts.items()):
            if until <= now:
                _ts_attempts.pop(key, None)
        if len(_ts_attempts) >= _TS_TRACKED_MAX:
            return False  # не сбрасывать лимиты уже действующих капч
    _ts_attempts[token] = (n + 1, expires)
    return True


def refund_turnstile_attempt(token: str) -> None:
    item = _ts_attempts.get(token)
    if item and item[0] > 0:
        _ts_attempts[token] = (item[0] - 1, item[1])


def report_allowed(ip: str, now: float | None = None) -> bool:
    """Не больше REPORT_PER_MINUTE репортов в минуту с адреса."""
    now = time.monotonic() if now is None else now
    if ip not in _report_hits and len(_report_hits) >= 2000:
        for key, history in list(_report_hits.items()):
            if not history or now - history[-1] >= 60:
                _report_hits.pop(key, None)
        if len(_report_hits) >= 2000:
            return False
    hits = [t for t in _report_hits.get(ip, []) if now - t < 60]
    if len(hits) >= REPORT_PER_MINUTE:
        _report_hits[ip] = hits
        return False
    hits.append(now)
    _report_hits[ip] = hits
    return True


def turnstile_keys() -> tuple[str, str] | None:
    """(sitekey, secret) из окружения; None — Turnstile не настроен, работает капча с картинкой."""
    site, secret = os.environ.get("TURNSTILE_SITEKEY", "").strip(), os.environ.get("TURNSTILE_SECRET", "").strip()
    return (site, secret) if site and secret else None


async def verify_turnstile(secret: str, response: str, remote_ip: str | None = None) -> dict | None:
    """Ответ siteverify Cloudflare ({"success": true, "cdata": …, "hostname": …}); None — сеть недоступна."""
    data = {"secret": secret, "response": response}
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s, \
                s.post(TURNSTILE_VERIFY_URL, data=data) as r:
            return await r.json(content_type=None)
    except Exception as e:
        logging.warning("turnstile siteverify: %s", e)
        return None


def level_params(level: int) -> tuple[int, int]:
    return LEVELS.get(level, LEVELS[0])


def validate_init_data(init_data: str, bot_token: str, max_age: int = 300,
                       now: int | None = None) -> dict | None:
    """Проверка подписи Telegram WebApp initData. None — если подпись/свежесть неверны."""
    if not isinstance(init_data, str) or not init_data or len(init_data) > 16384:
        return None
    try:
        items = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True, max_num_fields=32)
        pairs = dict(items)
        if len(pairs) != len(items):
            return None
    except ValueError:
        return None
    got = pairs.pop("hash", None)
    if not got or len(got) != 64 or any(c not in "0123456789abcdef" for c in got):
        return None
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, got):
        return None
    try:
        auth_date = int(pairs["auth_date"])
        user = json.loads(pairs["user"])
    except (KeyError, ValueError):
        return None
    age = (now if now is not None else int(time.time())) - auth_date
    if age < 0 or age > max_age:
        return None
    if not isinstance(user, dict) or type(user.get("id")) is not int or user["id"] <= 0:
        return None
    pairs["user"] = user
    return pairs


def answer_matches(answer: str, expected: str) -> bool:
    """Безопасно сравнить код, включая некорректный Unicode из JSON."""
    if not isinstance(answer, str) or not isinstance(expected, str):
        return False
    if not answer.isascii() or not expected.isascii():
        return False
    normalized = answer.strip().upper()
    if len(normalized) > 16:
        return False
    return hmac.compare_digest(normalized, expected)


def new_code(length: int = CODE_LEN) -> str:
    """Случайный код для новой капчи. Не выводится из токена: токен лежит в ссылке-кнопке в чате,
    и бот-спамер иначе мог бы вычислить ответ без распознавания картинки."""
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def make_code(seed: str) -> str:
    """Код капчи; для одного seed (токена) всегда один и тот же."""
    rng = random.Random("code:" + seed)
    return "".join(rng.choice(ALPHABET) for _ in range(CODE_LEN))


def _wave(img: Image.Image, rng: random.Random, amp: float) -> Image.Image:
    """Волнообразный сдвиг столбцов по вертикали: ломает распознавание «буква за буквой»."""
    import math
    w, h = img.size
    phase, period = rng.uniform(0, 6.28), rng.uniform(28, 46)
    out = Image.new("RGB", (w, h), (12, 12, 12))
    for x in range(w):
        dy = int(amp * math.sin(x / period * 6.28 + phase))
        out.paste(img.crop((x, 0, x + 1, h)), (x, dy))
    return out


@lru_cache(maxsize=128)
def render_image(code: str, seed: str, level: int = 0) -> bytes:
    """PNG с искажённым кодом: у каждой буквы свой поворот и сдвиг, плюс помехи. Чем выше level, тем сильнее искажение."""
    rng = random.Random("img:" + seed)
    w, h = 260, 100
    img = Image.new("RGB", (w, h), (12, 12, 12))
    d = ImageDraw.Draw(img)
    for _ in range(900 + 350 * level):  # шум
        x, y = rng.randrange(w), rng.randrange(h)
        g = rng.randrange(40, 120)
        d.point((x, y), fill=(g, g, g))
    font = ImageFont.load_default(size=54)
    step = w // (len(code) + 1)
    for i, ch in enumerate(code):
        tile = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
        shade = rng.randrange(200, 256)
        ImageDraw.Draw(tile).text((40, 40), ch, font=font, anchor="mm", fill=(shade, shade, shade, 255))
        spin = 28 + 5 * level
        tile = tile.rotate(rng.uniform(-spin, spin), resample=Image.BICUBIC)
        img.paste(tile, (step * (i + 1) - 40 + rng.randint(-5, 5), 10 + rng.randint(-8, 8)), tile)
    d = ImageDraw.Draw(img)
    for _ in range(5 + 2 * level):  # линии поверх букв
        g = rng.randrange(90, 190)
        d.line([(rng.randrange(w), rng.randrange(h)), (rng.randrange(w), rng.randrange(h))],
               fill=(g, g, g), width=rng.randint(1, 2))
    if level >= 2:
        img = _wave(img, rng, 2.5)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def build_app(db: Database, bot_token: str, on_pass) -> web.Application:
    app = web.Application()
    image_slots = asyncio.Semaphore(4)

    async def page(request: web.Request) -> web.StreamResponse:
        # к скрипту добавляем версию (по времени файла): клиенты Telegram держат старый captcha.js в кэше и после обновления бота
        # открывали капчу со старой, уже неверной логикой
        html = (WEBAPP_DIR / "index.html").read_text(encoding="utf-8")
        ver = str(int(max((WEBAPP_DIR / f).stat().st_mtime for f in ("captcha.js", "style.css", "index.html"))))
        html = html.replace('/webapp/captcha.js"', f'/webapp/captcha.js?v={ver}"').replace('/webapp/style.css"', f'/webapp/style.css?v={ver}"')
        resp = web.Response(text=html, content_type="text/html", charset="utf-8")
        resp.headers.update(PAGE_HEADERS)
        if turnstile_keys():
            resp.headers["Content-Security-Policy"] = CAPTCHA_CSP_TS
        return resp

    async def report(request: web.Request) -> web.Response:
        """Сообщение клиента о сбое проверки (Turnstile не загрузился, ошибка JS): попадает в журнал, чтобы было видно, почему у человека
        вместо Cloudflare открылась запасная капча. Эндпоинт без авторизации — размер и частота ограничены, пишем только известные поля."""
        ip = request.remote or "?"
        if not report_allowed(ip) or (request.content_length or 0) > REPORT_MAX_BYTES:
            return web.json_response({"ok": False}, status=429)
        try:
            try:
                raw = await request.content.readexactly(REPORT_MAX_BYTES + 1)
            except asyncio.IncompleteReadError as exc:
                raw = exc.partial
            if len(raw) > REPORT_MAX_BYTES:
                return web.json_response({"ok": False}, status=413)
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            body = {}
        if isinstance(body, dict):
            fields = {k: str(body.get(k, ""))[:80] for k in ("reason", "code", "msg", "src", "line", "ua")}
            tok = str(body.get("token", ""))[:6]
            logging.warning("captcha[%s] клиент: %s", tok, {k: v for k, v in fields.items() if v})
        return web.json_response({"ok": True})

    async def info(request: web.Request) -> web.Response:
        """Какая капча у этого токена: Turnstile (sitekey публичный, cdata привязывает ответ к токену) или картинка."""
        token = request.query.get("token", "")
        cap, status = await load(token, request.headers.get("X-Init-Data", ""))
        if cap is None:
            return web.json_response({"error": "forbidden"}, status=status)
        keys = turnstile_keys()
        body = {"mode": "turnstile", "sitekey": keys[0], "cdata": token} if keys else {"mode": "image"}
        return web.json_response(body, headers={"Cache-Control": "no-store"})

    async def load(token: str, init_data: str) -> tuple[dict | None, int]:
        """Возвращает (captcha, http-статус). Проверяет подпись, владельца и срок."""
        data = validate_init_data(init_data, bot_token, max_age=3600)   # время на капчу может быть до 24 ч — 5 минут мало
        if data is None:
            return None, 403
        cap = await db.get_captcha(token)
        if cap is None or cap["expires_at"] <= time.time():
            return None, 404
        if data["user"].get("id") != cap["user_id"]:
            return None, 403
        return cap, 200

    async def image(request: web.Request) -> web.Response:
        token = request.query.get("token", "")
        cap, status = await load(token, request.headers.get("X-Init-Data", ""))
        if cap is None:
            return web.json_response({"error": "forbidden"}, status=status)
        level = int(cap.get("level") or 0)
        async with image_slots:
            png = await asyncio.to_thread(render_image, cap["answer"], token, level)
        return web.Response(body=png, content_type="image/png",
                            headers={"Cache-Control": "no-store", "X-Code-Length": str(len(cap["answer"]))})

    async def finish(cap: dict) -> str | None:
        """Применить результат проверки; None означает, что Telegram не подтвердил действие."""
        for attempt in (1, 2):
            try:
                return await on_pass(cap["chat_id"], cap["user_id"], cap["message_id"], kind=cap.get("kind") or "member") or "done"
            except Exception:
                logging.exception("captcha: on_pass не удался (попытка %s) chat=%s user=%s", attempt, cap["chat_id"], cap["user_id"])
                if attempt == 1:
                    await asyncio.sleep(1)
        return None

    async def completed(cap: dict) -> web.Response:
        result = await finish(cap)
        if result is None:
            return web.json_response({"ok": False, "error": "release_failed"})
        return web.json_response({"ok": True, "result": result})

    async def verify(request: web.Request) -> web.Response:
        keys = turnstile_keys()
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise TypeError
            token, init_data = body["token"], body["initData"]
            if not isinstance(token, str) or not isinstance(init_data, str):
                raise TypeError
            answer = body.get("answer", "")
            ts_response = body.get("turnstile", "")
            if not isinstance(answer, str) or not isinstance(ts_response, str):
                raise TypeError
            if keys and ts_response and not (0 < len(ts_response) <= 4096):
                raise ValueError
        except (KeyError, ValueError, TypeError):
            return web.json_response({"ok": False})
        cap, _ = await load(token, init_data)
        if cap is None:
            return web.json_response({"ok": False})
        if keys and ts_response:                   # Cloudflare Turnstile
            if not take_turnstile_attempt(token):
                return web.json_response({"ok": False, "error": "attempts"})
            # За обратным прокси адрес клиента нельзя брать из недоверенного заголовка.
            res = await verify_turnstile(keys[1], ts_response)
            if res is None:                        # Cloudflare недоступен с сервера — это не ошибка человека, попытку возвращаем
                refund_turnstile_attempt(token)
                logging.warning("captcha[%s] turnstile: siteverify недоступен", token[:6])
                return web.json_response({"ok": False, "error": "network"})
            if not isinstance(res, dict) or res.get("success") is not True:
                logging.warning("captcha[%s] turnstile отклонён: %s", token[:6],
                                res.get("error-codes") if isinstance(res, dict) else type(res).__name__)
                return web.json_response({"ok": False})
            # Ответ должен быть привязан к конкретной капче, включая отсутствие cdata.
            if res.get("cdata") != token:
                logging.warning("captcha[%s] turnstile: cdata отсутствует или не совпал", token[:6])
                return web.json_response({"ok": False})
            if not await db.consume_captcha(token):  # одноразовость
                return web.json_response({"ok": False})
            _ts_attempts.pop(token, None)
            return await completed(cap)
        # попытку занимаем ДО сравнения и в БД: ни перезапуск бота, ни пачка параллельных запросов не дают лишних попыток
        if not await db.take_captcha_attempt(token, level_params(int(cap.get("level") or 0))[1]):
            return web.json_response({"ok": False, "error": "attempts"})
        if not answer_matches(answer, str(cap["answer"])):
            return web.json_response({"ok": False})
        if not await db.consume_captcha(token):  # одноразовость
            return web.json_response({"ok": False})
        return await completed(cap)

    app.router.add_get("/captcha", page)
    app.router.add_post("/captcha/report", report)
    app.router.add_get("/captcha/info", info)
    app.router.add_get("/captcha/image", image)
    app.router.add_post("/captcha/verify", verify)
    app.router.add_static("/webapp/", WEBAPP_DIR)
    return app
