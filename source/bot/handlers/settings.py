"""Панель настроек чата (`настройки`): разделы с переключателями и порогами. Только для админов."""
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import rich_ui
from bot.rich_ui import Btn, Screen
from bot import ux
from bot import mod_service as ms
from bot.db import Database
from bot.ranks import need_rank
from bot.toggles import GROUPS

router = Router(name="settings")

# Пояснения под страницей настроек: ключ страницы -> текст
NOTES = {"face": "Строгие критерии могут задеть обычных людей: без фото или @username сидят и настоящие участники. Возраст по id — оценка с точностью до нескольких месяцев. Доверенные (+доверять) проверку не проходят.",
         "leave": "Помогает против «зашёл — написал — вышел». Бан короткий: человек сможет вернуться.",
         "night": "Нужен часовой пояс чата (настройка tz). Права возвращаются утром сами.",
         "cas": "Id входящего уходит на api.lols.bot (и на api.cas.chat, если задан CAS_API_KEY); текст и имя не передаются.", "guest": "Гостевые боты отвечают в чате, не будучи его участниками. «Проверять» — стоп-слова, фишинг и флуд к их сообщениям.", "captcha": "Любое время на капчу — командой «капча время 45м». Если бот назначен стражем заявок (настройки чата в Telegram), капча открывается прямо в заявке.", "phish": "Проверка домена по признакам подделки. С ключом SAFE_BROWSING_KEY адреса ссылок сверяются с Google.", "aimod": "Текст уходит во внешний ИИ.", "ai": "В живом общении последние сообщения уходят во внешний ИИ.", "activity": "Неделя — с понедельника. Норма считается со следующей полной недели после включения; админы, модераторы и новички недели не кикаются. Любая другая норма — командой «норма 300». Реплики ИИ пишет Нори (нужен ключ ИИ)."}
# Готовый набор вариантов «действие при нарушении» для строк типа choice
ACTIONS = [("Удалить", "delete"), ("Варн", "warn"), ("Мут", "mute")]

SHORT = {"mod_on": "Модерация", "svc_on": "Сервисы (курс, вики…)", "cards_on": "Карточки", "stats_on": "Статистика", "rally_on": "Общий сбор", "quotes_on": "Цитатник",
         "mog_on": "Мог-баттлы", "giveaway_on": "Конкурсы", "suggest_on": "Предложка", "img_on": "Картинки «нарисуй»",
         "dl_on": "Скачивание «скачай»", "dl_auto": "Скачивание по ссылке"}

# СТРАНИЦЫ НАСТРОЕК. Добавить переключатель/выбор: допишите строку в нужную страницу, а ключ key заведите
# в DEFAULT_SETTINGS (db.py) со значением по умолчанию — иначе set_setting выдаст KeyError.
# Прочитать в коде: (await db.get_settings(chat_id))["key"]
# page -> (заголовок, строки). Строка: ("toggle", key, подпись) | ("choice", key, подпись, [(текст, значение)])
PAGES: dict[str, tuple[str, list[tuple]]] = {
    "captcha": ("🛡 Капча", [
        ("toggle", "captcha_on", "Капча для новичков"),
        ("choice", "captcha_timeout", "Время", [("1 мин", 60), ("3 мин", 180), ("5 мин", 300), ("10 мин", 600), ("30 мин", 1800)]),
        ("choice", "captcha_recheck", "Повторно", [("Нет", "off"), ("Без @ника", "susp"), ("Всем", "all")]),
        ("choice", "guard_default", "Заявки без капчи", [("Админам", "queue"), ("Принять", "approve")]),
    ]),
    "spam": ("🚫 Антиспам", [
        ("toggle", "spam_on", "Антиспам"),
        ("choice", "spam_flood_n", "Флуд, сообщ.", [("3", 3), ("5", 5), ("8", 8)]),
        ("choice", "spam_flood_sec", "за, сек", [("5", 5), ("10", 10), ("20", 20)]),
        ("toggle", "spam_dup", "Одинаковые сообщения"),
        ("choice", "links_mode", "Ссылки", [("Всем можно", "off"), ("Новичкам нет", "newbies"), ("Всем нет", "all")]),
        ("choice", "spam_mentions", "Упоминаний макс.", [("3", 3), ("5", 5), ("10", 10)]),
        ("toggle", "spam_forward", "Пересылки от новичков"),
        ("toggle", "spam_ai", "ИИ-проверка новичков"),
        ("choice", "spam_action", "Действие", ACTIONS),
    ]),
    "phish": ("🕵 Фишинг", [
        ("toggle", "phish_on", "Фишинг-ссылки"),
        ("choice", "phish_action", "Действие", ACTIONS),
    ]),
    "guest": ("🤖 Гостевые боты", [
        ("choice", "guest_mode", "Режим", [("Выкл", "off"), ("Проверять", "check"), ("Белый список", "allowlist"), ("Запретить", "block")]),
    ]),
    "cas": ("🚀 База спамеров", [
        ("choice", "cas_mode", "Новички из базы спамеров", [("Выкл", "off"), ("Уведомлять", "warn"), ("Банить", "ban")]),
    ]),
    "filters": ("📝 Стоп-слова", [
        ("choice", "filter_action", "Действие", ACTIONS),
    ]),
    "raid": ("🚨 Антирейд", [
        ("toggle", "raid_on", "Антирейд"),
        ("toggle", "dupe_on", "Двойники забаненных"),
        ("choice", "raid_n", "Входов", [("3", 3), ("5", 5), ("10", 10)]),
        ("choice", "raid_sec", "за, сек", [("30", 30), ("60", 60), ("120", 120)]),
        ("choice", "raid_action", "Новичкам", [("Капча", "captcha"), ("Кик", "kick")]),
        ("choice", "raid_minutes", "Режим, мин", [("5", 5), ("10", 10), ("30", 30)]),
    ]),
    "nsfw": ("🔞 Фильтр 18+", [
        ("toggle", "nsfw_on", "Фильтр 18+"),
        ("choice", "nsfw_threshold", "Строгость", [("Строго", 35), ("Средне", 55), ("Мягко", 75)]),
        ("choice", "nsfw_action", "Действие", ACTIONS),
        ("toggle", "nsfw_ai", "ИИ-проверка (картинка уходит во внешний ИИ)"),
    ]),
    "modgif": ("🎞 Гифки наказаний", [("toggle", "mod_gif", "Гифки к бану, муту, варну")]),
    "voice": ("🎙 Расшифровка", [
        ("toggle", "transcribe_on", "Расшифровка голосовых"),
        ("choice", "transcribe_max", "Макс. длина", [("1 мин", 60), ("3 мин", 180), ("10 мин", 600)]),
    ]),
    "aimod": ("🤖 ИИ-модерация", [
        ("choice", "ai_mod", "Проверять", [("Выкл", "off"), ("Новичков", "newbies"), ("Подозрительное", "all")]),
        ("choice", "ai_mod_action", "Действие", ACTIONS + [("Жалоба", "report")]),
        ("choice", "ai_mod_conf", "Уверенность", [("60%", 60), ("75%", 75), ("90%", 90)]),
    ]),
    "ai": ("🤖 ИИ", [
        ("toggle", "ai_on", "Команда «ии …»"),
        ("choice", "ai_chat", "Живое общение", [("Выкл", "off"), ("Отвечает", "reply"), ("Болтает", "live")]),
        ("choice", "ai_chat_style", "Стиль", [("По-свойски (с матом)", "casual"), ("Вежливо", "polite")]),
    ]),
    "activity": ("📅 Активность", [
        ("toggle", "quota_on", "Норма сообщений в неделю (автокик)"),
        ("choice", "quota_min", "Норма, сообщений", [("100", 100), ("150", 150), ("250", 250), ("400", 400), ("600", 600), ("1000", 1000)]),
        ("toggle", "quota_warn", "Предупреждать, кто не набирает"),
        ("toggle", "wake_on", "Подъём молчунов (Нори тегает)"),
        ("toggle", "idle_on", "Нори сама пишет, если чат затих"),
        ("choice", "idle_hours", "Затих, часов", [("3", 3), ("6", 6), ("12", 12), ("24", 24)]),
    ]),
    "lang": ("🌐 Язык / Language", [
        ("choice", "lang", "Язык", [("Русский", "ru"), ("English", "en")]),
    ]),
    "welcome": ("👋 Приветствие", [("toggle", "welcome_on", "Приветствие")]),
    "report": ("📣 Жалобы", [("toggle", "report_on", "Команда «жалоба»")]),
    "commands": ("🧩 Команды", [("toggle", key, SHORT.get(key, label)) for key, label in GROUPS.items()]),
    "games": ("🎮 Игры и фан", [
        ("toggle", "games_on", "Игры"),
        ("toggle", "mafia_on", "Мафия (/game)"),
        ("toggle", "fun_on", "«кто …»"),
        ("toggle", "rp_on", "РП и семья"),
        ("toggle", "rp_gifs", "Гифки в РП и семье"),
        ("toggle", "rp_adult", "РП 18+: флирт и мат"),
        ("toggle", "pair_intim", "Близость пар (18+)"),
        ("toggle", "rep_on", "Репутация"),
    ]),
    "warns": ("⚠️ Варны", [
        ("choice", "warn_limit", "Лимит до наказания", [("2", 2), ("3", 3), ("5", 5)]),
        ("choice", "warn_ttl_days", "Срок жизни варна", [("7 д", 7), ("30 д", 30), ("90 д", 90), ("Бессрочно", 0)]),
        ("choice", "warn_action", "При лимите", [("Мут", "mute"), ("Кик", "kick"), ("Бан", "ban")]),
        ("choice", "warn_secs", "Срок мута/бана", [("1 ч", 3600), ("1 д", 86400), ("7 д", 604800), ("30 д", 2592000)]),
        ("choice", "mute_secs", "Мут без срока", [("1 ч", 3600), ("1 д", 86400), ("7 д", 604800)]),
        ("choice", "ban_secs", "Бан без срока", [("Навсегда", 0), ("1 д", 86400), ("7 д", 604800), ("30 д", 2592000)]),
    ]),
    "delete": ("🗑 Удалять сообщения", [
        ("toggle", "del_caps", "КАПС"), ("toggle", "del_sticker", "Стикеры"), ("toggle", "del_gif", "Гифки"),
        ("toggle", "del_voice", "Голосовые"), ("toggle", "del_note", "Кружки"),
        ("toggle", "del_forward", "Пересланные"), ("toggle", "del_mention", "@упоминания"),
        ("toggle", "del_emoji", "Кастомные эмодзи"), ("toggle", "del_story", "Сторис"),
        ("toggle", "del_dice", "Игровые эмодзи (кубик, дартс)"), ("toggle", "del_format", "С форматированием"),
        ("toggle", "del_via", "Через inline-ботов"), ("toggle", "del_poll", "Опросы"),
        ("toggle", "del_service", "Служебные (вход, выход, закреп)"), ("toggle", "del_cmds", "Все /команды"),
        ("toggle", "unpin_channel", "Откреплять посты канала"),
        ("toggle", "leave_wipe", "Удалять сообщения ушедшего (48 ч)"),
    ]),
    "face": ("🕵 Фейс-контроль", [
        ("toggle", "fc_on", "Проверять новичков"),
        ("toggle", "fc_photo", "Нужно фото профиля"),
        ("toggle", "fc_username", "Нужен @username"),
        ("toggle", "fc_premium", "Нужен Telegram Premium"),
        ("choice", "fc_age", "Возраст аккаунта (по id, примерно)", [("Любой", 0), ("30 д", 30), ("90 д", 90), ("180 д", 180)]),
        ("choice", "fc_action", "Не прошёл", [("Кик", "kick"), ("Мут", "mute"), ("Бан", "ban")]),
    ]),
    "leave": ("🚪 Быстрый выход", [
        ("toggle", "leave_on", "Банить за быстрый выход"),
        ("choice", "leave_sec", "Вышел раньше, чем через", [("30 с", 30), ("2 мин", 120), ("10 мин", 600)]),
        ("choice", "leave_hours", "Бан на", [("1 ч", 1), ("24 ч", 24), ("7 д", 168)]),
    ]),
    "night": ("🌙 Ночной режим", [
        ("toggle", "night_on", "Закрывать чат ночью"),
        ("choice", "night_from", "С", [("22", 22), ("23", 23), ("0", 0), ("1", 1)]),
        ("choice", "night_to", "До", [("6", 6), ("7", 7), ("8", 8), ("9", 9)]),
    ]),
}


def settings_screen(page: str, s: dict, panel_url: str | None = None) -> Screen:
    """Экран настроек: главная — сетка таблеток по 2; раздел — переключатели и ряды вариантов внутри сообщения."""
    if page == "home" or page not in PAGES:
        btns = [Btn(title, cb=f"cfg:{p}") for p, (title, _) in PAGES.items()]
        rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]
        if panel_url:
            rows.append([Btn("🌐 Открыть как приложение", url=panel_url, style="primary")])
        rows.append([Btn("⬅️ Меню", cb="menu:home", style="link")])
        return Screen("⚙️ Настройки чата", [], rows)
    title, spec = PAGES[page]
    body: list = [f"<i>{NOTES[page]}</i>"] if page in NOTES else []
    rows = []
    for row in spec:
        if row[0] == "toggle":
            _, key, label = row
            on = bool(s[key])
            rows.append([Btn(f"{'✅' if on else '❌'} {label}", cb=f"set:{page}:{key}:{0 if on else 1}",
                             style="success" if on else None)])
        else:
            _, key, label, values = row
            rows.append([Btn(label, cb="noop", style="link")])          # подпись ряда
            rows.append([Btn(t, cb=f"set:{page}:{key}:{v}", style="primary" if str(s[key]) == str(v) else None)
                         for t, v in values])
    rows.append([Btn("⬅️ К разделам", cb="cfg:home", style="link")])
    classic_rows = []                                       # обычное сообщение: подпись и варианты в одном ряду, как раньше
    for row in spec:
        if row[0] == "toggle":
            _, key, label = row
            on = bool(s[key])
            classic_rows.append([Btn(f"{'✅' if on else '❌'} {label}", cb=f"set:{page}:{key}:{0 if on else 1}",
                                     style="success" if on else None)])
        else:
            _, key, label, values = row
            classic_rows.append([Btn(label, cb="noop")] + [
                Btn(("• " if str(s[key]) == str(v) else "") + t, cb=f"set:{page}:{key}:{v}") for t, v in values])
    classic_rows.append([Btn("⬅️ К разделам", cb="cfg:home")])
    return Screen(title, body, rows, classic_rows=classic_rows)


def allowed_values(key: str) -> set[str]:
    out: set[str] = set()
    for _, rows in PAGES.values():
        for row in rows:
            if row[1] != key:
                continue
            out |= {"0", "1"} if row[0] == "toggle" else {str(v) for _, v in row[3]}
    return out


def render_page(page: str, s: dict, panel_url: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    if page == "home" or page not in PAGES:
        btns = [B(text=title, callback_data=f"cfg:{p}") for p, (title, _) in PAGES.items()]
        rows = [btns[i:i + 2] for i in range(0, len(btns), 2)]          # сетка по 2 кнопки, как главное меню
        if panel_url:                                                   # те же настройки одним окном — мини-приложением
            rows.append([B(text="🌐 Открыть как приложение", url=panel_url, style="primary")])
        rows.append([B(text="⬅️ В меню", callback_data="menu:home")])
        return "⚙️ <b>Настройки чата</b>", InlineKeyboardMarkup(inline_keyboard=rows)
    title, spec = PAGES[page]
    kb: list[list[B]] = []
    for row in spec:
        if row[0] == "toggle":
            _, key, label = row
            on = bool(s[key])
            kb.append([B(text=f"{'✅' if on else '❌'} {label}", callback_data=f"set:{page}:{key}:{0 if on else 1}",
                         style="success" if on else None)])            # включённое подсвечено зелёным (Bot API 9.4)
        else:
            _, key, label, values = row
            kb.append([B(text=label, callback_data="noop")] + [
                B(text=("• " if str(s[key]) == str(v) else "") + t, callback_data=f"set:{page}:{key}:{v}",
                  style="primary" if str(s[key]) == str(v) else None)
                for t, v in values])
    kb.append([B(text="⬅️ К разделам", callback_data="cfg:home")])
    note = NOTES.get(page)
    return f"<b>{title}</b>" + (f"\n<i>{note}</i>" if note else ""), InlineKeyboardMarkup(inline_keyboard=kb)


async def panel_url(bot, chat_id: int, webapp_url: str) -> str | None:
    """Ссылка в личку бота, откуда открывается веб-панель этого чата (кнопка web_app в группах не работает)."""
    if not webapp_url:
        return None
    try:
        return f"https://t.me/{(await bot.me()).username}?start=panel_{chat_id}"
    except Exception:
        return None


async def can_configure(bot, db: Database, chat_id: int, user_id: int) -> bool:
    """Админ Telegram или модератор бота с рангом из ДК «настройки чата» — то же правило, что и в веб-панели."""
    try:
        m = await ms.get_member(bot, chat_id, user_id)
    except Exception:
        return False
    if m.status in ("administrator", "creator"):
        return True
    return await db.get_rank(chat_id, user_id) >= need_rank(await db.get_access(chat_id), "настройки чата")


async def _denied(cb: CallbackQuery) -> None:
    await cb.answer("Только для админов и модераторов с нужным рангом", show_alert=True)


async def open_settings(cb: CallbackQuery, bot, db: Database, webapp_url: str = "") -> None:
    if cb.message.chat.type == "private":
        await cb.answer("Настройки доступны в группе.", show_alert=True)
        return
    if not await can_configure(bot, db, cb.message.chat.id, cb.from_user.id):
        await _denied(cb)
        return
    await cb.answer()
    await rich_ui.show(cb, settings_screen("home", await db.get_settings(cb.message.chat.id),
                                           await panel_url(bot, cb.message.chat.id, webapp_url)))


@router.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("настройки", "настройка")))
async def settings_cmd(message: Message, bot, db: Database, webapp_url: str = "") -> None:
    if message.chat.type == "private":
        await ux.tell(message, "⚠️ Настройки доступны в группе.")
        return
    if not await can_configure(bot, db, message.chat.id, message.from_user.id):
        await ux.tell(message, "⚠️ Настройки только для админов и модераторов с нужным рангом.")
        return
    await rich_ui.send(bot, message.chat.id, settings_screen("home", await db.get_settings(message.chat.id),
                                                             await panel_url(bot, message.chat.id, webapp_url)),
                       thread_id=message.message_thread_id if message.is_topic_message else None)


async def _show(cb: CallbackQuery, db: Database, page: str, purl: str | None = None) -> None:
    await rich_ui.show(cb, settings_screen(page, await db.get_settings(cb.message.chat.id), purl))


@router.callback_query(F.data == "noop")
async def noop_cb(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data.startswith("cfg:"))
async def cfg_cb(cb: CallbackQuery, bot, db: Database, webapp_url: str = "") -> None:
    if not await can_configure(bot, db, cb.message.chat.id, cb.from_user.id):
        await _denied(cb)
        return
    await cb.answer()
    await _show(cb, db, cb.data.split(":", 1)[1], await panel_url(bot, cb.message.chat.id, webapp_url))


@router.callback_query(F.data.startswith("set:"))
async def set_cb(cb: CallbackQuery, bot, db: Database, webapp_url: str = "") -> None:
    parts = cb.data.split(":")
    if len(parts) != 4:
        await cb.answer()
        return
    _, page, key, value = parts
    if page not in PAGES or value not in allowed_values(key):
        await cb.answer()
        return
    if not await can_configure(bot, db, cb.message.chat.id, cb.from_user.id):
        await _denied(cb)
        return
    await db.set_setting(cb.message.chat.id, key, value, actor=cb.from_user.id)
    await cb.answer("Сохранено")
    await _show(cb, db, page, await panel_url(bot, cb.message.chat.id, webapp_url))
