"""Диагностика для владельца: права бота в чате, настройки, ключи, сертификат, ошибки + чек-лист живой проверки."""
from __future__ import annotations

import asyncio
import html
import os
import ssl
import time
from urllib.parse import urlparse

from bot import alerts
from bot.db import Database
from bot.fmt import kv_table, pre_table, quote

_RIGHTS = [("can_delete_messages", "удалять сообщения"), ("can_restrict_members", "ограничивать участников"),
           ("can_invite_users", "приглашать/одобрять заявки"), ("can_pin_messages", "закреплять сообщения")]
_FEATURES = [("captcha_on", "капча"), ("spam_on", "антиспам"), ("raid_on", "антирейд"), ("nsfw_on", "фильтр 18+"),
             ("transcribe_on", "расшифровка голосовых"), ("ai_on", "ИИ"), ("games_on", "игры"),
             ("rp_on", "РП и семья"), ("rep_on", "репутация")]


def _ok(v) -> str:
    return "да" if v else "НЕТ"


async def diagnose_chat(bot, db: Database, chat_id: int) -> str:
    chat = await db.get_chat(chat_id)
    title = html.escape((chat or {}).get("title") or str(chat_id))
    head = f"💬 <b>{title}</b> · <code>{chat_id}</code>"
    try:
        me = await bot.me()
        member = await bot.get_chat_member(chat_id, me.id)
    except Exception as e:
        return head + f"\nНе удалось получить права бота: {html.escape(type(e).__name__)}. Бот в чате? Он админ?"
    parts = [head]
    if member.status not in ("administrator", "creator"):
        parts.append("❌ Бот не администратор — модерация, капча и защита не заработают.")
    else:
        rights = [(label, _ok(getattr(member, attr, False) or member.status == "creator")) for attr, label in _RIGHTS]
        parts.append("<b>Права бота</b>\n" + pre_table(rights, align="ll", maxw=(26, 3)))
    if getattr(me, "can_read_all_group_messages", False):
        parts.append("✅ Режим приватности выключен: бот видит все сообщения.")
    else:
        parts.append("❌ Включён режим приватности: бот не видит обычные сообщения (команды без слэша, антиспам).\n"
                     + quote("BotFather → /setprivacy → Disable, затем заново добавьте бота в чат.", expandable=False))
    cfg = await db.get_settings(chat_id)
    if cfg.get("captcha_on"):
        from bot.captcha_server import turnstile_keys
        parts.append("✅ Капча: Cloudflare Turnstile." if turnstile_keys() else
                     "ℹ️ Капча: запасная (код с картинки). Для Cloudflare Turnstile задайте TURNSTILE_SITEKEY и TURNSTILE_SECRET в .env.")
    try:                                                        # страж заявок: назначается в настройках чата в Telegram
        guard = getattr((await bot.get_chat(chat_id)), "guard_bot", None)
        if guard is not None and guard.id == me.id:
            parts.append("✅ Бот — страж заявок на вступление: капча открывается прямо в заявке.")
        elif guard is not None:
            parts.append(f"ℹ️ Стражем заявок назначен другой бот (@{html.escape(guard.username or str(guard.id))}).")
        else:
            parts.append("ℹ️ Страж заявок не назначен: чтобы капча открывалась прямо в заявке, назначьте этого бота "
                         "в настройках чата Telegram (заявки на вступление).")
    except Exception:
        pass
    if cfg.get("cas_mode", "off") != "off":
        from bot import cas
        parts.append("🚀 База спамеров: lols.bot" + (" + CAS" if cas.has_key() else
                     " (CAS подключится, если задать CAS_API_KEY — ключ на combot.org)"))
    parts.append("<b>Функции</b>\n" + pre_table([(label, "вкл" if cfg.get(k) else "—") for k, label in _FEATURES],
                                                  align="lr", maxw=(24, 3)))
    return "\n".join(parts)


async def cert_days_left(host: str, port: int = 443, timeout: float = 5.0, via: str | None = None) -> int | None:
    """Сколько дней осталось у сертификата HTTPS; None — недоступно/ошибка.
    via — подключиться к другому хосту (имя сервиса в docker-сети), сохранив SNI: из контейнера публичный IP
    сервера обычно недостижим (hairpin NAT)."""
    try:
        ctx = ssl.create_default_context()
        _, writer = await asyncio.wait_for(asyncio.open_connection(via or host, port, ssl=ctx, server_hostname=host), timeout)
        try:
            cert = writer.get_extra_info("ssl_object").getpeercert()
        finally:
            writer.close()
        end = ssl.cert_time_to_seconds(cert["notAfter"])
        return int((end - time.time()) // 86400)
    except Exception:
        return None


async def diagnose_global(db: Database, rt, ai, webapp_url: str = "") -> str:
    size = await db.size_bytes()
    rows = [("ИИ (River)", "ключ есть" if getattr(ai, "has_river", False) else "НЕТ"),
            ("Расшифровка", "ключ есть" if getattr(ai, "has_stt", False) else "НЕТ"),
            ("База", f"{db.backend}, {size / 1024:.0f} КБ"),
            ("Обслуживание", "ВКЛ" if rt.maintenance else "выкл")]
    host = urlparse(webapp_url).hostname if webapp_url else None
    if host:
        port = urlparse(webapp_url).port or 443
        days = await cert_days_left(host, port, timeout=4)
        if days is None:   # из контейнера бота публичный адрес недоступен — проверяем через сервис caddy
            days = await cert_days_left(host, port, timeout=4, via=os.environ.get("CERT_VIA", "caddy"))
        rows.append(("Сертификат", "не проверить" if days is None else f"{days} дн." + ("" if days > 14 else " (скоро конец!)")))
    else:
        rows.append(("WEBAPP_URL", "не задан (капча выкл)"))
    out = ["⚙️ <b>Диагностика бота</b>", kv_table(rows, key_width=14, value_width=22)]
    if alerts.RECENT:
        errs = [(time.strftime("%d.%m %H:%M", time.gmtime(ts)), name) for ts, name in list(alerts.RECENT)[-5:]]
        out.append("<b>Последние ошибки</b> (UTC)\n" + pre_table(errs, maxw=(11, 24)))
    else:
        out.append("✅ Ошибок с момента запуска нет")
    return "\n".join(out)


CHECKLIST = """📋 <b>Чек-лист живой проверки</b> (на тестовой группе)
1. Капча без заявок: зайти новым аккаунтом → бот ограничил, кнопка ведёт в личку, код с картинки снимает ограничение.
2. Капча с заявками: подать заявку → в личку пришла кнопка → верный код одобряет, таймаут отклоняет.
3. Антирейд: включить, войти N аккаунтами за минуту → режим включился, новички проходят усиленную капчу.
4. Фильтр 18+: включить, отправить допустимое тестовое медиа и команду «скан» ответом → оценка выводится; подобрать порог.
5. Голосование за мут («гб»): 5 голосов → мут; повторный голос не засчитывается.
6. Массовая чистка: «кик неактив 30д» → превью и подтверждение кнопкой, отмена работает.
7. Панель владельца: статус, чаты, бэкап БД файлом, рассылка с предпросмотром, режим обслуживания.
8. Семья и РП: предложение брака с кнопками, лимиты, отказ.
9. Антиспам: флуд, повторы, ссылки новичка → сработало заданное действие.
10. Расшифровка: голосовое и кружок → текст; слишком длинное отклоняется.
Результат каждого пункта (ок / не ок + что увидели) пришлите — дефекты пойдут в тесты и исправления."""
