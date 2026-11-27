"""Режим webhook: приём обновлений от Telegram по HTTPS и наблюдение за тем, что доставка не сломалась."""
from __future__ import annotations

import asyncio
import hmac
import logging
import time

from aiogram.types import Update
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.updatequeue import QueueFull

ERROR_WINDOW = 600   # ошибки доставки старше 10 минут не считаем


def webhook_target(webhook_url: str, webapp_url: str) -> str:
    """Куда Telegram шлёт обновления: WEBHOOK_URL (порт 88/443/8443 — другие Telegram не принимает), иначе WEBAPP_URL."""
    base = (webhook_url or webapp_url or "").rstrip("/")
    return f"{base}/webhook" if base else ""


def register_webhook(app, dp, bot, secret: str, handle_in_background: bool = True, queue=None) -> None:
    """Маршрут POST /webhook с проверкой секретного заголовка X-Telegram-Bot-Api-Secret-Token.
    С queue (UpdateQueue) обновление сначала сохраняется в БД и только потом подтверждается Telegram."""
    if not secret:
        raise ValueError("webhook secret must not be empty")
    if queue is not None:
        async def handler(request: web.Request) -> web.Response:
            got = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not hmac.compare_digest(got.encode(), secret.encode()):
                return web.Response(status=401, text="Unauthorized")
            try:
                raw = await request.text()
                update = Update.model_validate_json(raw, context={"bot": bot})
            except Exception:
                return web.Response(status=400, text="Bad update")
            try:
                await queue.put(update, raw)
            except QueueFull:
                return web.Response(status=503, text="Busy")     # Telegram повторит позже
            except Exception:
                logging.exception("не удалось сохранить обновление")
                return web.Response(status=503, text="Retry")
            return web.json_response({})

        app.router.add_post("/webhook", handler)
        setup_application(app, dp, bot=bot)
        return
    SimpleRequestHandler(dp, bot, secret_token=secret, handle_in_background=handle_in_background).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)


async def check_webhook_once(bot, alerter, expected_url: str, now: int | None = None) -> bool:
    """True — всё в порядке. Иначе сообщает владельцу: вебхук слетел или Telegram недавно не смог доставить обновления."""
    now = int(time.time()) if now is None else now
    try:
        wi = await bot.get_webhook_info()
    except Exception:
        logging.warning("webhook watch: getWebhookInfo не удался")
        return True   # проблема связи с Telegram — не повод тревожить владельца
    if wi.url != expected_url:
        await alerter.alert(f"⚠️ Webhook не установлен или адрес изменён (ожидался {expected_url}): бот сейчас не получает сообщения.")
        return False
    recent_error = wi.last_error_date and now - int(wi.last_error_date) < ERROR_WINDOW
    if recent_error and wi.pending_update_count > 0:
        await alerter.alert(f"⚠️ Telegram не может доставить обновления на webhook: {wi.last_error_message} "
                            f"(в очереди {wi.pending_update_count}). Проверьте Caddy и сертификат.")
        return False
    return True


async def webhook_watch(bot, alerter, expected_url: str, interval: int = 300, first_delay: int = 60) -> None:
    await asyncio.sleep(first_delay)
    while True:
        await check_webhook_once(bot, alerter, expected_url)
        await asyncio.sleep(interval)
