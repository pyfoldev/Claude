"""ТОЧКА ВХОДА БОТА (python -m bot.main).

КАК ЭТОТ ФАЙЛ УСТРОЕН — где что менять:
  [1] ИМПОРТЫ ХЕНДЛЕРОВ      — добавили новый файл handlers/xxx.py → импортируйте его здесь (блок «ХЕНДЛЕРЫ»).
  [2] main()  шаги по порядку:
        2.1 конфиг и БД                      (config.py, db.py)
        2.2 объекты в dp[...]                — всё, что хендлер может запросить параметром (db, ai, rt, http…).
                                               Новый общий объект: dp["name"] = obj → в хендлере `async def f(m, name)`.
        2.3 MIDDLEWARE                       — порядок важен! см. комментарии у каждой строки.
        2.4 РОУТЕРЫ (ROUTERS)                — порядок = приоритет: первый подошедший хендлер «съедает» сообщение.
        2.5 веб-сервер (капча, панель, конкурсы)
        2.6 ФОНОВЫЕ ЗАДАЧИ (jobs)            — сюда добавлять циклы «раз в N минут».
        2.7 запуск: webhook или polling
Шаблоны для нового хендлера/middleware/задачи — в папке templates/, подробно — EXTENDING.md.
"""
import asyncio
from contextlib import AsyncExitStack
import signal
import logging
import math
import os
import sys
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiohttp import web

import aiohttp

from bot.ai import AiClient
from bot.alerts import Alerter, clear_marker, make_error_handler, set_marker_and_check_crash, supervise
from bot.audit import Auditor
from bot.backup import backup_loop
from bot import members
from bot.webhook import register_webhook, webhook_target, webhook_watch
from bot.captcha_server import build_app
from bot.panel_server import PanelContext, add_panel_routes
from bot.config import load_config
from bot.emoji_inject import EmojiSession
from bot.db import Database
# ======================= [1] ХЕНДЛЕРЫ (импорт модулей с командами) =======================
# Новый модуль handlers/xxx.py: добавьте сюда `from bot.handlers import xxx as xxx_handlers`
# и затем — в список ROUTERS ниже (иначе команды не заработают).
from bot.handlers import ai as ai_handlers
from bot.handlers import owner as owner_handlers
from bot.handlers import captcha, duels, fun, games, menu, moderation, settings, stats
from bot.handlers import chatinfo as chatinfo_handlers
from bot.handlers import economy as economy_handlers
from bot.handlers import entertainment as fun_handlers
from bot.handlers import inline as inline_handlers, memory as memory_handlers, polls as polls_handlers
from bot import dupes as dupes_module
from bot import guestbots as guestbots_module
from bot import cas as cas_module
from bot.handlers import pair as pair_handlers
from bot.pair.service import PairService
from bot.handlers import votes as vote_handlers
from bot.handlers import cleanup as cleanup_handlers
from bot.handlers import rulecmds as rulecmds_handlers
from bot.handlers import services as services_handlers
from bot.handlers import boardgames as boardgames_handlers
from bot.handlers import collect as collect_handlers
from bot import scheduler as scheduler_module
from bot.middlewares.rules import MembershipMiddleware, RulesMiddleware
from bot.middlewares.ratelimit import RateLimitMiddleware
from bot.handlers import mafia as mafia_handlers
from bot.handlers import activity as activity_handlers
from bot import activity as activity_module
from bot.handlers import purge as purge_handlers
from bot.handlers import family as family_handlers
from bot.handlers import ranks as rank_handlers
from bot.handlers import rp as rp_handlers
from bot.handlers import scan as scan_handlers
from bot.handlers import social as social_handlers
from bot.handlers import garden as garden_handlers
from bot.handlers import setup as setup_handlers
from bot.handlers import history as history_handlers
from bot.handlers import logchat as logchat_handlers
from bot.handlers import reports as reports_handlers
from bot.handlers import chatfilters as chatfilters_handlers
from bot.handlers import aimod as aimod_handlers
from bot.handlers import webpanel as webpanel_handlers
from bot.handlers import giveaway as giveaway_handlers
from bot.handlers import suggest as suggest_handlers
from bot.handlers import images as images_handlers
from bot.handlers import download as download_handlers
from bot.handlers import premium as premium_handlers
# ======================= прочие сервисы =======================
from bot.imagegen import ImageGen
from bot.handlers import quotes as quotes_handlers
from bot.handlers import mog as mog_handlers
from bot.giveaway_server import add_giveaway_routes
from bot.metrics import Metrics, MetricsMiddleware
from bot.updatequeue import UpdateQueue
# ======================= MIDDLEWARE (прослойки до хендлеров) =======================
# Новая прослойка: файл middlewares/xxx.py (шаблон — templates/middleware_template.py), импорт здесь,
# подключение — в разделе 2.3 внутри main().
from bot.middlewares.blocklist import BlockMiddleware
from bot.middlewares.counter import CounterMiddleware
from bot.middlewares.guard import GuardMiddleware
from bot.middlewares.memory import ChatMemoryMiddleware
from bot.middlewares.prefix import NoriPrefixMiddleware
from bot.ttl import prune_stale
from bot.nsfw import NsfwDetector
from bot.runtime import Runtime
from bot.middlewares.tracker import UserTrackerMiddleware
from bot import i18n
from bot.middlewares.quiet import QuietTopicMiddleware
from bot.handlers import topics as topics_handlers


# ======================= ФОНОВЫЕ ЦИКЛЫ =======================
# Каждый цикл — бесконечный `while True` с await asyncio.sleep(...). Подключаются в словаре jobs (раздел 2.6).
# supervise() сам перезапустит цикл при падении и уведомит владельцев.
async def rollup_loop(db: Database) -> None:
    """Раз в сутки: сворачивает старую статистику, чистит БД и протухшие кэши (prune_stale).
    Новый кэш-словарь вида {ключ: время}, который должен чиститься — добавьте в кортеж ниже: (словарь, возраст_в_секундах)."""
    while True:
        try:
            await db.rollup_old(int(time.time()))
            await db.prune_old(int(time.time()))
            await db.optimize()                       # статистика для планировщика запросов — раз в сутки
            for d, age in ((fun._last, 3600), (chatinfo_handlers._last, 3600), (ai_handlers._last_ask, 3600),
                           (economy_handlers._cool, 86400), (rp_handlers._last, 3600),
                           (fun_handlers._last, 3600), (captcha._passed, 3600)):
                prune_stale(d, age, time.time())
        except Exception:
            logging.exception("rollup failed")
        await asyncio.sleep(86400)


async def flush_loop(db: Database, guard=None, every: float = 5.0) -> None:
    """Раз в несколько секунд пишет накопленный счётчик сообщений одной транзакцией; раз в час чистит кэши защиты."""
    if not math.isfinite(every) or every <= 0:
        raise ValueError("flush interval must be finite and positive")
    ticks = 0
    while True:
        await asyncio.sleep(every)
        await db.flush_messages()                    # заодно пишет очередь пользователей и участников
        ticks += 1
        if guard is not None and ticks % max(1, int(3600 / every)) == 0:
            guard.prune()


async def _cancel_tasks(tasks) -> None:
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _stop_polling(dp, task) -> None:
    if not task.done():
        await asyncio.sleep(0)  # let start_polling initialize its stop event
        if not task.done():
            try:
                await asyncio.wait_for(dp.stop_polling(), timeout=20)
            except (RuntimeError, asyncio.TimeoutError):
                task.cancel()
    await asyncio.gather(task, return_exceptions=True)


def _install_signals(rt, ready):
    loop = asyncio.get_running_loop()
    previous = {}
    task = asyncio.current_task()
    def stop():
        rt.request_stop()
        if not ready.is_set():
            task.cancel()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            handler = signal.getsignal(sig)
            loop.add_signal_handler(sig, stop)
            previous[sig] = handler
        except (NotImplementedError, RuntimeError, ValueError):
            pass
    def restore():
        for sig, handler in previous.items():
            loop.remove_signal_handler(sig)
            signal.signal(sig, handler)
    return restore


async def main() -> bool:
    """Работает до остановки. Возвращает True, если владелец попросил перезагрузку."""
    logging.basicConfig(level=logging.INFO)
    # --- 2.1 КОНФИГ: все настройки берутся из .env (см. config.py и .env.example) ---
    cfg = load_config()
    cfg.validate()
    try:
        backup_keep = int(os.environ.get("BACKUP_KEEP", "14") or 14)
        if backup_keep < 1:
            raise ValueError
    except ValueError:
        raise SystemExit("BACKUP_KEEP должен быть положительным целым числом")
    stack = AsyncExitStack()
    marker_active = False
    marker = ""
    orderly = False
    try:
        rt = Runtime()
        ready = asyncio.Event()
        stack.callback(_install_signals(rt, ready))
        # --- БД: SQLite (DB_PATH) или PostgreSQL (DATABASE_URL). Все запросы — методы класса Database в db.py ---
        db = await Database.connect(cfg.database_url or cfg.db_path)  # DATABASE_URL=postgresql://… или файл SQLite
        stack.push_async_callback(db.close)
        bot_session = EmojiSession()
        stack.push_async_callback(bot_session.close)
        bot = Bot(cfg.bot_token, session=bot_session, default=DefaultBotProperties(parse_mode=ParseMode.HTML,
                                                                                      link_preview_is_disabled=True))   # ссылки-имена (t.me/ник) не должны разворачиваться в превью
        bot.session.middleware(i18n.TranslateMiddleware(db))           # английский интерфейс для чатов с языком en
        migrated = await PairService(db).migrate_legacy()                # старые браки и отношения → пары (одноразово)
        if migrated["marriage"] or migrated["relation"]:
            logging.info("пары: перенесено браков %s, отношений %s", migrated["marriage"], migrated["relation"])
        db.bot = bot                                                  # запасной поиск @ника через Telegram (db.find_user)

        http = aiohttp.ClientSession()
        stack.push_async_callback(http.close)
        ai = AiClient(http, river_key=cfg.river_api_key, river_base=cfg.river_base_url, river_model=cfg.river_model,
                      mistral_key=cfg.mistral_api_key, mistral_base=cfg.mistral_base_url,
                      stt_model=cfg.mistral_stt_model, vision_model=cfg.river_vision_model,
                      chat_vision_model=cfg.river_chat_vision_model)
        if not ai.has_river:
            logging.info("RIVER_API_KEY не задан: команда «ии» и ИИ-проверка спама выключены")
        if not ai.has_stt:
            logging.info("GIGAAM_URL не задан: расшифровка выключена")

        # --- 2.2 DISPATCHER и общие объекты ---
        # Всё, что кладём в dp["имя"], хендлеры получают параметром с тем же именем: async def cmd(message, db, ai, rt)
        dp = Dispatcher()
        data_dir = os.path.dirname(cfg.db_path) or "."
        marker = os.path.join(data_dir, "running.marker")
        alerter = Alerter(bot, cfg.owner_ids)
        auditor = Auditor(bot, db)
        db.auditor = auditor
        stack.push_async_callback(auditor.aclose)
        auditor.start()
        dp.errors.register(make_error_handler(alerter))
        crashed = set_marker_and_check_crash(marker)
        marker_active = True
        if crashed:
            await alerter.alert("⚠️ Бот запущен после сбоя: прошлый запуск завершился не штатно. Проверьте логи.")
        dp["db"] = db
        dp["ai"] = ai
        dp["http"] = http
        dp["owner_ids"] = cfg.owner_ids
        await rt.load(db)
        dp["rt"] = rt
        if not cfg.owner_ids:
            logging.warning("OWNER_ID не задан: панель владельца недоступна")
        dp["webapp_url"] = cfg.webapp_url
        dp["premium_price"] = cfg.premium_price
        # Свой объект: dp["my_service"] = MyService(...)  → в хендлере: async def cmd(message, my_service)
        dp["ytdlp_cookies"] = os.environ.get("YTDLP_COOKIES") or None   # cookies.txt для Instagram/YouTube (по желанию)
        dp["imagegen"] = ImageGen(http, cfg.cf_account_id, cfg.cf_api_token, cfg.cf_image_model)
        if not dp["imagegen"].configured:
            logging.info("CF_ACCOUNT_ID/CF_API_TOKEN не заданы: «нарисуй» выключено")
        detector = NsfwDetector()
        dp["detector"] = detector
        # --- 2.3 MIDDLEWARE ---
        # outer_middleware выполняются СВЕРХУ ВНИЗ в порядке регистрации, ДО выбора хендлера.
        # dp.update   — любое обновление;  dp.message — новые сообщения;  dp.edited_message — правки;
        # dp.chat_member — вход/выход участников;  dp.callback_query — нажатия inline-кнопок.
        # Прослойка может: пропустить (return await handler(event, data)), остановить (return None), дописать data["x"].
        guard = GuardMiddleware(db, detector=detector, ai=ai if ai.has_river else None, rt=rt)
        metrics = Metrics()
        dp["metrics"] = metrics
        dp["db_path"] = cfg.db_path
        dp.update.outer_middleware(MetricsMiddleware(metrics))   # самый внешний: видит полное время, включая блок-лист
        dp.update.outer_middleware(BlockMiddleware(rt, cfg.owner_ids, guard))  # блок-лист и обслуживание — первыми
        dp.update.outer_middleware(UserTrackerMiddleware(db))
        dp.message.outer_middleware(CounterMiddleware(db))
        dp.message.outer_middleware(guard)
        dp.message.outer_middleware(RateLimitMiddleware(cfg.owner_ids))   # залп команд от одного человека
        dp.message.outer_middleware(RulesMiddleware(db))         # удаление по типу, триггеры, FAQ, блок стикеров
        dp.chat_member.outer_middleware(MembershipMiddleware(db))  # фейс-контроль и быстрый выход
        dp.message.outer_middleware(QuietTopicMiddleware(db))
        dp.message.outer_middleware(ChatMemoryMiddleware(db))    # после защиты: удалённый спам в память не попадает
        dp.message.outer_middleware(NoriPrefixMiddleware())
        dp.message.outer_middleware(i18n.CommandAliasMiddleware(db))   # после префикса: «nori, ban @x» тоже понятно  # последним: счётчик и защита видят исходный текст
        dp.edited_message.outer_middleware(guard)  # правкой нельзя обойти проверку
        # --- 2.4 РОУТЕРЫ (ROUTERS) ---
        # ПОРЯДОК ВАЖЕН: Telegram-событие идёт по списку сверху вниз, первый подошедший хендлер выигрывает.
        #   • узкие/специальные команды — выше, «ловушки» вроде ai_handlers (отвечает на любой текст) — в самом конце;
        #   • новый роутер: добавьте `xxx_handlers.router` в нужное место списка ROUTERS.
        # Группы: служебные и онбординг → модерация → статистика → игры → РП/семья → фан → ИИ (последним).
        # captcha первым: «/start cap_…» не должен попасть в общее меню
        ROUTERS = [
            # --- служебное: защита мафии, владелец, капча, веб-панель ---
            mafia_handlers.guard,
            owner_handlers.router,
            captcha.router,
            webpanel_handlers.router,
            # --- розыгрыши, предложения, Premium, медиа ---
            mafia_handlers.router,
            giveaway_handlers.router,
            suggest_handlers.router,
            premium_handlers.router,
            images_handlers.router,
            download_handlers.router,
            # --- меню, инлайн, память, опросы, темы, защита от дублей/гостевых ботов/CAS ---
            menu.router,
            inline_handlers.router,
            memory_handlers.router,
            polls_handlers.router,
            topics_handlers.router,
            dupes_module.router,
            guestbots_module.router,
            cas_module.router,
            # --- пары, настройки, правила, мастер настройки, ранги, активность, чистка ---
            pair_handlers.router,
            settings.router,
            rulecmds_handlers.router,
            setup_handlers.router,
            rank_handlers.router,
            activity_handlers.router,
            cleanup_handlers.router,
            purge_handlers.router,
            chatinfo_handlers.router,
            scan_handlers.router,
            # --- модерация и логи ---
            social_handlers.router,
            moderation.router,
            history_handlers.router,
            logchat_handlers.router,
            reports_handlers.router,
            chatfilters_handlers.router,
            aimod_handlers.router,
            # --- статистика, цитаты ---
            stats.router,
            quotes_handlers.router,
            mog_handlers.router,
            # --- игры и экономика ---
            games.router,
            duels.router,
            boardgames_handlers.router,
            collect_handlers.router,
            economy_handlers.router,
            vote_handlers.router,
            # --- РП, семья, огород, развлечения, сервисы ---
            rp_handlers.router,
            family_handlers.router,
            garden_handlers.router,
            fun_handlers.router,
            services_handlers.router,
            fun.router,
            # --- ИИ — ПОСЛЕДНИМ (ловит «ии, …» и обращения по имени) ---
            ai_handlers.router,
            # >>> СЮДА добавляйте свой роутер: xxx_handlers.router, (выше ai_handlers!) <<<
        ]
        for r in ROUTERS:
            dp.include_router(r)

        # --- 2.5 ВЕБ-СЕРВЕР: капча, мини-приложение конкурсов, веб-панель. Новые HTTP-маршруты: app.router.add_get/post(...) ---
        app = build_app(db, cfg.bot_token, captcha.make_on_pass(bot, db, cfg.webapp_url))
        add_giveaway_routes(app, db, bot, cfg.bot_token)
        add_panel_routes(app, PanelContext(bot=bot, db=db, bot_token=cfg.bot_token, owner_ids=cfg.owner_ids, rt=rt, ai=ai,
                                           webapp_url=cfg.webapp_url,
                                           trusted_proxy_ips=frozenset(ip.strip() for ip in os.environ.get("TRUSTED_PROXY_IPS", "").split(",") if ip.strip())))
        # my_chat_member (бота убрали из чата) и edited_message (защита от правок) нужны middleware, а не хендлерам
        allowed = sorted(set(dp.resolve_used_update_types()) | {"my_chat_member", "edited_message", "chat_member", "chat_join_request"})
        # Список команд в меню «/» у Telegram. Добавить команду: ещё один BotCommand(command="имя", description="текст")
        await bot.set_my_commands([BotCommand(command="menu", description="Меню бота"),
                                   BotCommand(command="help", description="Список команд")])

        # --- 2.6 ФОНОВЫЕ ЗАДАЧИ ---
        # Формат: "название для логов": lambda: функция_цикла(аргументы). Добавить свою — одна строка в словарь jobs ниже.
        # (шаблон цикла — templates/job_template.py)
        backup_dir = os.environ.get("BACKUP_DIR") or os.path.join(data_dir, "backups")
        jobs = {"капча": lambda: captcha.captcha_watchdog(bot, db),
                "дуэли": lambda: duels.duel_watchdog(bot, db),
                "настольные игры": lambda: boardgames_handlers.bgame_watchdog(bot, db),
                "семья": lambda: family_handlers.family_watchdog(bot, db),
                "пары": lambda: pair_handlers.pair_watchdog(bot, db),
                "таймеры": lambda: social_handlers.timer_watchdog(bot, db),
                "статистика": lambda: rollup_loop(db),
                "сброс счётчиков": lambda: flush_loop(db, guard),
                "участники": lambda: members.sweep_loop(bot, db),
                "активность": lambda: activity_module.activity_loop(bot, db, ai if ai.has_river else None),
                "конкурсы": lambda: giveaway_handlers.giveaway_watchdog(bot, db),
                "правила чата": lambda: scheduler_module.scheduler_loop(bot, db),
                "бэкап": lambda: backup_loop(db, backup_dir, backup_keep, alerter.alert)}
        tasks = []
        stack.push_async_callback(_cancel_tasks, tasks)
        for name, factory in jobs.items():
            tasks.append(asyncio.create_task(supervise(name, factory, alerter)))

        # --- 2.7 ЗАПУСК: MODE=webhook (прод, за reverse proxy) или MODE=polling (локальная разработка) ---
        if cfg.mode == "webhook":
            target = webhook_target(cfg.webhook_url, cfg.webapp_url)
            uq = UpdateQueue(db, dp, bot, workers=cfg.update_workers)
            dp["uq"] = uq
            stack.push_async_callback(uq.stop)
            await uq.start()                                  # сначала довыполняем то, что не успели до сбоя
            register_webhook(app, dp, bot, cfg.webhook_secret, queue=uq)
            runner = web.AppRunner(app, shutdown_timeout=10)
            stack.push_async_callback(runner.cleanup)
            await runner.setup()
            await web.TCPSite(runner, "0.0.0.0", cfg.port).start()    # сначала слушаем, потом сообщаем Telegram адрес
            await bot.set_webhook(target, secret_token=cfg.webhook_secret, allowed_updates=allowed)
            tasks.append(asyncio.create_task(webhook_watch(bot, alerter, target)))
            logging.info("webhook mode on :%s -> %s", cfg.port, target.split("/webhook")[0])
            ready.set()
            await rt.wait_stop()
        else:
            await bot.delete_webhook()
            runner = web.AppRunner(app, shutdown_timeout=10)
            stack.push_async_callback(runner.cleanup)
            await runner.setup()
            await web.TCPSite(runner, "0.0.0.0", cfg.port).start()
            logging.info("polling mode, captcha web on :%s", cfg.port)
            stop_task = asyncio.create_task(rt.wait_stop())
            stack.push_async_callback(_cancel_tasks, [stop_task])
            poll_task = asyncio.create_task(dp.start_polling(
                bot, allowed_updates=allowed, handle_signals=False, close_bot_session=False,
                tasks_concurrency_limit=cfg.update_workers, tasks_shutdown_timeout=15))
            stack.push_async_callback(_stop_polling, dp, poll_task)
            ready.set()
            done, _ = await asyncio.wait({stop_task, poll_task}, return_when=asyncio.FIRST_COMPLETED)
            if stop_task in done:
                await _stop_polling(dp, poll_task)
            await poll_task  # polling errors must reach the supervisor, not become a clean stop
            if not rt.stop_requested:
                raise RuntimeError("polling stopped without a shutdown request")
        orderly = True
        return rt.restart
    except asyncio.CancelledError:
        orderly = True
        raise
    finally:
        # Repeated shutdown signals must not interrupt closing DB/session resources.
        cleanup = asyncio.create_task(stack.aclose())
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                continue
        cleanup.result()
        if orderly and marker_active:
            clear_marker(marker)


def _run(coro):
    """uvloop — быстрый цикл событий (сеть, aiohttp, aiosqlite); нет uvloop (Windows, локальная разработка) — обычный."""
    try:
        import uvloop
    except ImportError:
        return asyncio.run(coro)
    return uvloop.run(coro)


if __name__ == "__main__":
    if _run(main()):
        os.execv(sys.executable, [sys.executable, "-m", "bot.main"])  # перезагрузка по команде владельца
