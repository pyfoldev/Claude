"""Точка входа: сборка диспетчера, подключение роутеров и middleware, фоновые задачи, запуск.

Файл собран из нескольких исходных модулей; каждый начинается с шапки «МОДУЛЬ: bot/<путь>.py».
Ищите по слову «МОДУЛЬ:» (Ctrl+F). Пути вида handlers/xxx.py в комментариях — это такие разделы.

КАРТА ФАЙЛОВ (где искать разделы):
  data.py: audit, backup, db, pg
  core.py: perf, __init__, alerts, cleanup, config, emoji_inject, emoji, fmt, gender, i18n_en, i18n, keyboards, links, members, metrics, parsing, plans, punish_gifs, ranks, rich, rich_ui, runtime, style, targets, toggles, ttl, updatequeue, ux, weather, webhook, wipe
  services.py: ai, aimod, cards, chatmind, collectibles, downloader, pair.economy, pair.baby, pair.data, pair.gifts, pair.house, pair.kids, pair.pets, pair.premium, pair.quests, pair.service, family, gifs, giveaway, imagegen, media, mog, nsfw, rp_data, services
  moderation.py: activity, mod_service, bulk, captcha_server, cas, diagnostics, dupes, filters, guestbots, handlers.settings, handlers.activity, handlers.ai, handlers.aimod, rules_text, handlers.chatinfo, raid, handlers.captcha, handlers.chatfilters, handlers.cleanup, handlers.download, handlers.history, handlers.images, handlers.inline, handlers.logchat, handlers.memory, handlers.menu, handlers.moderation, handlers.owner, handlers.polls, handlers.premium, purge, handlers.purge, handlers.ranks, handlers.social, handlers.reports, middlewares.tracker, phishing, spam, middlewares.guard, rules, middlewares.rules, handlers.rulecmds, handlers.scan, handlers.setup, handlers.stats, handlers.suggest, handlers.topics, handlers.webpanel, middlewares.blocklist, middlewares.counter, middlewares.memory, middlewares.prefix, middlewares.quiet, middlewares.ratelimit, profile_card, scheduler
  community.py: games.checkers, games.chessgame, games.seabattle, boardgames, games.garden, games.rps, games.slots, games.tictactoe, handlers.economy, handlers.boardgames, handlers.collect, handlers.duels, handlers.entertainment, handlers.family, handlers.fun, handlers.games, handlers.garden, handlers.giveaway, mafia, handlers.mafia, handlers.mog, handlers.pair, handlers.quotes, handlers.rp, handlers.services, handlers.votes
  web.py: giveaway_server, panel_server
"""

import aiohttp
import asyncio
import logging
import math
import os
import signal
import sys
import time
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiohttp import web
from contextlib import AsyncExitStack

# имена из более ранних файлов
from bot.data import Auditor, Database, backup_loop
from bot.core import (
    Alerter,
    CommandAliasMiddleware,
    EmojiSession,
    Metrics,
    MetricsMiddleware,
    Runtime,
    TranslateMiddleware,
    UpdateQueue,
    clear_marker,
    load_config,
    make_error_handler,
    prune_stale,
    register_webhook,
    set_marker_and_check_crash,
    supervise,
    sweep_loop,
    webhook_target,
    webhook_watch,
)
from bot.services import AiClient, ImageGen, NsfwDetector, PairService
from bot.moderation import (
    BlockMiddleware,
    ChatMemoryMiddleware,
    CounterMiddleware,
    GuardMiddleware,
    MembershipMiddleware,
    NoriPrefixMiddleware,
    QuietTopicMiddleware,
    RateLimitMiddleware,
    RulesMiddleware,
    UserTrackerMiddleware,
    _last__chatinfo,
    _last_ask,
    _passed,
    activity_loop,
    build_app,
    captcha_watchdog,
    make_on_pass,
    router__captcha,
    router__cas,
    router__chatfilters,
    router__chatinfo,
    router__download,
    router__dupes,
    router__guestbots,
    router__handlers_activity,
    router__handlers_ai,
    router__handlers_aimod,
    router__handlers_cleanup,
    router__handlers_memory,
    router__handlers_premium,
    router__handlers_purge,
    router__handlers_ranks,
    router__history,
    router__images,
    router__inline,
    router__logchat,
    router__menu,
    router__moderation,
    router__owner,
    router__polls,
    router__reports,
    router__rulecmds,
    router__scan,
    router__settings,
    router__setup,
    router__social,
    router__stats,
    router__suggest,
    router__topics,
    router__webpanel,
    scheduler_loop,
    timer_watchdog,
)
from bot.community import (
    _cool__handlers_economy,
    _last__entertainment,
    _last__fun,
    _last__rp,
    bgame_watchdog,
    duel_watchdog,
    family_watchdog,
    giveaway_watchdog,
    guard__handlers_mafia,
    pair_watchdog,
    router__collect,
    router__duels,
    router__entertainment,
    router__fun,
    router__handlers_boardgames,
    router__handlers_economy,
    router__handlers_family,
    router__handlers_games,
    router__handlers_garden,
    router__handlers_giveaway,
    router__handlers_mafia,
    router__handlers_mog,
    router__handlers_pair,
    router__handlers_services,
    router__quotes,
    router__rp,
    router__votes,
)
from bot.web import PanelContext, add_giveaway_routes, add_panel_routes



# ════════════════════════════════════════════════════════════════════════════════════════════════════
# МОДУЛЬ: bot/main.py
# ТОЧКА ВХОДА БОТА (python -m bot.main).
#
# КАК ЭТОТ ФАЙЛ УСТРОЕН — где что менять (шаги внутри main() идут по порядку):
#   2.1 конфиг и БД                      — раздел «МОДУЛЬ: bot/config.py» (core.py), «bot/db.py» (data.py)
#   2.2 объекты в dp[...]                — всё, что хендлер может запросить параметром (db, ai, rt, http…).
#                                          Новый общий объект: dp["name"] = obj → в хендлере `async def f(m, name)`.
#   2.3 MIDDLEWARE                       — порядок важен! см. комментарии у каждой строки.
#   2.4 РОУТЕРЫ (ROUTERS)                — порядок = приоритет: первый подошедший хендлер «съедает» сообщение.
#   2.5 веб-сервер (капча, панель, конкурсы)
#   2.6 ФОНОВЫЕ ЗАДАЧИ (jobs)            — сюда добавлять циклы «раз в N минут».
#   2.7 запуск: webhook или polling
#
# Как добавить команду: напишите хендлеры с новым `Router(...)` в конец community.py (или moderation.py),
# импортируйте его здесь из bot.community и добавьте в список ROUTERS (строго выше блока ИИ).
# ════════════════════════════════════════════════════════════════════════════════════════════════════
# ======================= ХЕНДЛЕРЫ (команды) =======================
# Все модули команд (bot/handlers/*.py) теперь — разделы «МОДУЛЬ: …» внутри moderation.py и community.py.
# Новый роутер надо добавить в список ROUTERS ниже (иначе команды не заработают).
# ======================= прочие сервисы =======================
# ======================= MIDDLEWARE (прослойки до хендлеров) =======================
# Новая прослойка: класс в moderation.py (раздел «МОДУЛЬ: bot/middlewares/…»), подключение — в разделе 2.3 внутри main().


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
            for d, age in ((_last__fun, 3600), (_last__chatinfo, 3600), (_last_ask, 3600),
                           (_cool__handlers_economy, 86400), (_last__rp, 3600),
                           (_last__entertainment, 3600), (_passed, 3600)):
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
        bot.session.middleware(TranslateMiddleware(db))           # английский интерфейс для чатов с языком en
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
        dp.message.outer_middleware(CommandAliasMiddleware(db))   # после префикса: «nori, ban @x» тоже понятно  # последним: счётчик и защита видят исходный текст
        dp.edited_message.outer_middleware(guard)  # правкой нельзя обойти проверку
        # --- 2.4 РОУТЕРЫ (ROUTERS) ---
        # ПОРЯДОК ВАЖЕН: Telegram-событие идёт по списку сверху вниз, первый подошедший хендлер выигрывает.
        #   • узкие/специальные команды — выше, «ловушки» вроде ai_handlers (отвечает на любой текст) — в самом конце;
        #   • новый роутер: добавьте `xxx_handlers.router` в нужное место списка ROUTERS.
        # Группы: служебные и онбординг → модерация → статистика → игры → РП/семья → фан → ИИ (последним).
        # captcha первым: «/start cap_…» не должен попасть в общее меню
        ROUTERS = [
            # --- служебное: защита мафии, владелец, капча, веб-панель ---
            guard__handlers_mafia,
            router__owner,
            router__captcha,
            router__webpanel,
            # --- розыгрыши, предложения, Premium, медиа ---
            router__handlers_mafia,
            router__handlers_giveaway,
            router__suggest,
            router__handlers_premium,
            router__images,
            router__download,
            # --- меню, инлайн, память, опросы, темы, защита от дублей/гостевых ботов/CAS ---
            router__menu,
            router__inline,
            router__handlers_memory,
            router__polls,
            router__topics,
            router__dupes,
            router__guestbots,
            router__cas,
            # --- пары, настройки, правила, мастер настройки, ранги, активность, чистка ---
            router__handlers_pair,
            router__settings,
            router__rulecmds,
            router__setup,
            router__handlers_ranks,
            router__handlers_activity,
            router__handlers_cleanup,
            router__handlers_purge,
            router__chatinfo,
            router__scan,
            # --- модерация и логи ---
            router__social,
            router__moderation,
            router__history,
            router__logchat,
            router__reports,
            router__chatfilters,
            router__handlers_aimod,
            # --- статистика, цитаты ---
            router__stats,
            router__quotes,
            router__handlers_mog,
            # --- игры и экономика ---
            router__handlers_games,
            router__duels,
            router__handlers_boardgames,
            router__collect,
            router__handlers_economy,
            router__votes,
            # --- РП, семья, огород, развлечения, сервисы ---
            router__rp,
            router__handlers_family,
            router__handlers_garden,
            router__entertainment,
            router__handlers_services,
            router__fun,
            # >>> СЮДА добавляйте свой роутер: xxx_handlers.router, (строго выше блока ИИ!) <<<
            # --- ИИ — ПОСЛЕДНИМ (ловит «ии, …» и обращения по имени) ---
            router__handlers_ai,
        ]
        for r in ROUTERS:
            dp.include_router(r)

        # --- 2.5 ВЕБ-СЕРВЕР: капча, мини-приложение конкурсов, веб-панель. Новые HTTP-маршруты: app.router.add_get/post(...) ---
        app = build_app(db, cfg.bot_token, make_on_pass(bot, db, cfg.webapp_url))
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
        backup_dir = os.environ.get("BACKUP_DIR") or os.path.join(data_dir, "backups")
        jobs = {"капча": lambda: captcha_watchdog(bot, db),
                "дуэли": lambda: duel_watchdog(bot, db),
                "настольные игры": lambda: bgame_watchdog(bot, db),
                "семья": lambda: family_watchdog(bot, db),
                "пары": lambda: pair_watchdog(bot, db),
                "таймеры": lambda: timer_watchdog(bot, db),
                "статистика": lambda: rollup_loop(db),
                "сброс счётчиков": lambda: flush_loop(db, guard),
                "участники": lambda: sweep_loop(bot, db),
                "активность": lambda: activity_loop(bot, db, ai if ai.has_river else None),
                "конкурсы": lambda: giveaway_watchdog(bot, db),
                "правила чата": lambda: scheduler_loop(bot, db),
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


def _run__main(coro):
    """uvloop — быстрый цикл событий (сеть, aiohttp, aiosqlite); нет uvloop (Windows, локальная разработка) — обычный."""
    try:
        import uvloop
    except ImportError:
        return asyncio.run(coro)
    return uvloop.run(coro)


if __name__ == "__main__":
    if _run__main(main()):
        os.execv(sys.executable, [sys.executable, "-m", "bot.main"])  # перезагрузка по команде владельца
