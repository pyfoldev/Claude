"""Английский интерфейс. Язык задаётся настройкой чата «Язык» (в личке — по языку Telegram пользователя).

Как это работает: тексты бота написаны по-русски; на выходе (запрос к Telegram) они проходят через словарь фраз,
если у чата язык en. Переводятся меню, настройки, мастер настройки, статистика, опросы, память, основные статусы и
сообщения об ошибках. В английских чатах работают и английские команды: ban, mute, stats, balance… (см. ALIASES).
Тексты, которых нет в словаре, остаются русскими — словарь можно пополнять."""
from __future__ import annotations

import re

from aiogram import BaseMiddleware, Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

# ---------- команды ----------
# английская фраза -> русская команда. Длинные проверяются первыми.
# ДОБАВИТЬ АНГЛИЙСКУЮ КОМАНДУ: "english phrase": "русская команда" (бот всё равно понимает только русские хендлеры).
ALIASES = {
    "unban": "разбан", "ban": "бан", "kick": "кик", "unmute": "размут", "mute": "мут",
    "remove warn": "снять варн", "unwarn": "снять варн", "warns": "варны", "warn": "варн",
    "history": "история", "stats": "стата", "stat": "стата", "balance": "баланс", "bonus": "бонус", "top": "топ",
    "menu": "меню", "help": "помощь", "settings": "настройки", "poll": "опрос", "report": "жалоба",
    "delete": "удалить", "unpin": "открепить", "pin": "закреп", "purge": "чистка", "clean": "чистка",
    "rules": "правила", "reputation": "репутация", "rep": "репутация", "rating": "рейтинг", "who is inactive": "кто неактив",
    "inactive": "кто неактив", "web panel": "веб-панель", "panel": "веб-панель", "topics": "темы",
    "remember": "запомни", "what do you remember": "что ты помнишь", "forget": "забудь", "memory on": "память вкл",
    "memory off": "память выкл", "slots": "слоты", "roulette": "рулетка", "duel": "дуэль", "garden": "огород",
    "marry": "брак", "divorce": "развод", "my family": "моя семья", "who am i": "кто я", "my profile": "моя анкета",
    "ask,": "ии,", "ai,": "ии,", "diagnostics": "диагностика",
}
_ARG = {"week": "неделя", "month": "месяц", "all": "вся", "forever": "навсегда", "topics": "темы", "day": "сутки"}
_ARG_FORGET = {"all": "все", "everything": "всё"}
_ARG_BACK = {"неделя": "week", "месяц": "month", "вся": "all", "навсегда": "forever", "темы": "topics", "сутки": "day",
             "все": "all", "всё": "all"}
_DUR_BACK = re.compile(r"\b(\d+)([мчд])\b")
_DUR_BACK_MAP = {"м": "m", "ч": "h", "д": "d"}
_DUR = re.compile(r"^(\d+)([mhd])$")
_DUR_RU = {"m": "м", "h": "ч", "d": "д"}
_ALIAS_ORDER = sorted(ALIASES, key=len, reverse=True)
_REVERSE = {ru: en for en, ru in sorted(ALIASES.items(), key=lambda kv: -len(kv[0])) if ru not in ("ии,",)}
_REVERSE.update({"стата": "stats", "чистка": "purge", "репутация": "reputation", "кто неактив": "inactive",
                 "веб-панель": "web panel", "снять варн": "remove warn", "что ты помнишь": "what do you remember"})


def alias_to_ru(text: str) -> str | None:
    """«ban @vasya 1d spam» → «бан @vasya 1д spam»; не команда → None."""
    t = text.strip()
    low = t.lower()
    for en in _ALIAS_ORDER:
        if low == en or low.startswith(en + " ") or (en.endswith(",") and low.startswith(en)):
            rest = t[len(en):].strip()
            toks = []
            for w in rest.split(" "):
                lw = w.lower()
                m = _DUR.match(lw)
                if m:
                    toks.append(f"{m.group(1)}{_DUR_RU[m.group(2)]}")
                elif en == "forget":
                    toks.append(_ARG_FORGET.get(lw, w))
                elif en in ("stats", "stat", "ban", "mute", "topics"):
                    toks.append(_ARG.get(lw, w))
                else:
                    toks.append(w)
            return (ALIASES[en] + (" " + " ".join(toks) if toks else "")).strip()
    return None


# ---------- интерфейс ----------
# подстроки (достаточно длинные и специфичные, чтобы не портить чужой текст)
# ДОБАВИТЬ ПЕРЕВОД ТЕКСТА: "русский фрагмент": "English fragment". Большие списки — в bot/i18n_en.py (MESSAGES).
PHRASES = {
    "Меню Chat Helper": "Chat Helper menu", "Выберите раздел": "Choose a section",
    "Настройки чата": "Chat settings", "К разделам": "Back to sections", "В меню": "To menu", "Открыть как приложение": "Open as app",
    "Открыть веб-панель": "Open web panel", "Веб-панель": "Web panel", "Меню команд": "Command menu",
    "Добавить в чат": "Add to chat", "Первая настройка": "First setup",
    "Включите нужное (только админы). Остальное — в разделе «Все настройки».": "Turn on what you need (admins only). Everything else is in “All settings”.",
    "Все настройки": "All settings",
    "Ответом на сообщение или с @ником.": "Reply to a message or add an @username.",
    "Дайте боту права админа: удаление, ограничение участников, приглашения, закрепление.": "Give the bot admin rights: delete messages, restrict members, invite users, pin messages.",
    "Включается в": "Turn on in",
    "антиспам · антирейд · фильтр 18+ · стоп-слова · капча · ИИ-модерация · расшифровка голосовых": "anti-spam · anti-raid · 18+ filter · stop words · captcha · AI moderation · voice transcription",
    "Привет! Я Chat Helper — помощник для чатов.": "Hi! I'm Chat Helper — an assistant for chats.",
    "Модерация, защита от спама, статистика, игры и ИИ.": "Moderation, spam protection, stats, games and AI.",
    "Как начать": "Getting started",
    "Добавьте меня в чат — кнопка ниже сама выдаст нужные права.": "Add me to a chat — the button below requests the right permissions.",
    "В чате появится мастер первой настройки: включите капчу, антиспам и приветствие.": "A setup wizard will appear in the chat: enable captcha, anti-spam and the welcome message.",
    "Все команды — ": "All commands — ", "настройки — ": "settings — ",
    "Подсказки по командам в любом чате: напишите @имя_бота и слово — например, «бан».": "Command hints in any chat: type @botname and a word, e.g. “ban”.",
    "@ник": "@username", "Вопрос | да | нет": "Question | yes | no", "диагностика": "diagnostics", "владельцу": "owner only",
    "Модерация": "Moderation", "Игры и фан": "Games & fun", "РП и семья": "RP & family", "Ранги и профиль": "Ranks & profile",
    "Защита": "Protection", "Помощь": "Help",
    # статусы и ошибки
    "Готово.": "Done.", "Запомнил.": "Got it.", "Всё забыл.": "Forgot everything.", "Забыл.": "Forgotten.",
    "Нужен ранг": "Rank required:", "Нужен другой человек": "Another person is needed",
    "Не хватает монет": "Not enough coins", "Баланс": "Balance", "Ваш баланс": "Your balance",
    "Бонус уже получен сегодня. Приходите завтра!": "Daily bonus already claimed. Come back tomorrow!",
    "Ежедневный бонус": "Daily bonus", "Подождите": "Please wait", "С Premium — без ожидания.": "No waiting with Premium.",
    "Вы исчерпали лимит оценок на сегодня.": "You've used up today's rating limit.",
    "Вы уже оценивали этого человека за последний час.": "You already rated this person in the last hour.",
    "Нет доступа": "No access", "Только для админов": "Admins only", "Сохранено": "Saved",
    "Не нашёл": "Couldn't find", "Не получилось": "Failed",
    "Настройки доступны в группе.": "Settings are available in a group chat.",
    "Настройки только для админов и модераторов с нужным рангом.": "Settings are for admins and moderators with the required rank only.",
    "Только для админов и модераторов с нужным рангом": "Admins and moderators with the required rank only",
    # модерация
    "забанен": "banned", "разбанен": "unbanned", "в муте на": "muted for", "может писать снова": "can write again",
    "исключён": "removed", "предупреждение": "warning", "предупреждений": "warnings", "Лимит достигнут — мут на 1 дн.": "Limit reached — muted for 1 day.",
    "сообщение удалено": "message deleted", "Исключить": "Remove", "Отмена": "Cancel", "Отменено.": "Cancelled.",
    "Забанить": "Ban", "Это не он": "Not him", "Оставлен: модератор решил, что это не двойник.": "Kept: the moderator decided it's not a duplicate.",
    "похож на забаненного": "looks like banned user", "сходство": "similarity", "Решает модератор.": "A moderator decides.",
    "Неактивные": "Inactive", "Кик всех": "Kick all", "Неактивных": "Inactive", "дн.": "d",
    # статистика и таблицы
    "Статистика": "Statistics", "за 24 часа": "for 24 hours", "за неделю": "for a week", "за месяц": "for a month",
    "за всё время": "for all time", "Участник": "Member", "Сообщ.": "Msgs", "Пока нет сообщений.": "No messages yet.",
    "Предупреждения": "Warnings", "Рейдинг репутации": "Reputation ranking", "Рейтинг репутации": "Reputation ranking",
    "Репутация": "Reputation", "Богатейшие": "Richest", "Победы в дуэлях": "Duel wins", "Темы": "Topics", "Тема": "Topic", "Доля": "Share",
    "Досье": "File", "видно модераторам": "visible to moderators", "Сейчас": "Now", "без наказаний": "no penalties",
    "Наказаний за всё время": "Penalties in total", "Сообщений": "Messages", "Все записи": "All records",
    # опросы / память / темы
    "Формат:": "Format:", "Ключи в конце:": "Options at the end:", "Вопрос — от 1 до 300 символов.": "Question: 1 to 300 characters.",
    "Нужно от 2 до": "Need 2 to", "вариантов.": "options.", "Что я помню о вас": "What I remember about you",
    "Пока ничего не помню.": "I don't remember anything yet.", "Память выключена.": "Memory is off.",
    "Память включена.": "Memory is on.", "Удалить:": "Delete:", "для ответов ИИ": "for AI replies",
    "Тема тихая: бот не отвечает участникам.": "Quiet topic: the bot won't answer members here.",
    "Тема снова обычная.": "Topic is back to normal.", "Пока нет сообщений по темам.": "No topic messages yet.",
    "Напишите это внутри нужной темы.": "Send this inside the topic you want.",
    # капча
    "Проверка пройдена": "Verification passed", "Добро пожаловать": "Welcome",
}
from bot.i18n_en import MESSAGES as _MESSAGES   # noqa: E402 — большой словарь сообщений в отдельном файле

PHRASES.update(_MESSAGES)
# целиком совпадающие подписи кнопок (после снятия эмодзи/отметок)
# ПОДПИСИ КНОПОК (целиком): "Русская кнопка": "English button"
EXACT = {
    "Модерация": "Moderation", "Статистика": "Statistics", "Игры и фан": "Games & fun", "Защита": "Protection",
    "РП и семья": "RP & family", "Настройки": "Settings", "Ранги и профиль": "Ranks & profile", "Помощь": "Help",
    "Капча": "Captcha", "Капча для новичков": "Captcha for newcomers", "Время": "Time", "1 мин": "1 min", "3 мин": "3 min",
    "5 мин": "5 min", "10 мин": "10 min", "Повторно": "Repeat", "Нет": "No", "Без @ника": "No @username", "Всем": "Everyone",
    "Антиспам": "Anti-spam", "Флуд, сообщ.": "Flood, msgs", "за, сек": "per, sec", "Одинаковые сообщения": "Duplicate messages",
    "Ссылки": "Links", "Всем можно": "Allowed", "Новичкам нет": "Not for newcomers", "Всем нет": "Not allowed",
    "Упоминаний макс.": "Max mentions", "Пересылки от новичков": "Forwards from newcomers", "ИИ-проверка новичков": "AI check of newcomers",
    "Действие": "Action", "Удалить": "Delete", "Варн": "Warn", "Мут": "Mute", "Фишинг": "Phishing", "Фишинг-ссылки": "Phishing links",
    "Стоп-слова": "Stop words", "Антирейд": "Anti-raid", "Двойники забаненных": "Banned-user lookalikes", "Входов": "Joins",
    "Новичкам": "Newcomers", "Кик": "Kick", "Режим, мин": "Mode, min", "Фильтр 18+": "18+ filter", "Строгость": "Strictness",
    "Строго": "Strict", "Средне": "Medium", "Мягко": "Soft", "ИИ-проверка (картинка уходит во внешний ИИ)": "AI check (image goes to an external AI)",
    "Расшифровка": "Transcription", "Расшифровка голосовых": "Voice transcription", "Макс. длина": "Max length",
    "ИИ-модерация": "AI moderation", "Проверять": "Check", "Выкл": "Off", "Новичков": "Newcomers", "Подозрительное": "Suspicious",
    "Жалоба": "Report", "Уверенность": "Confidence", "ИИ": "AI", "Команда «ии …»": "“ai …” command", "Живое общение": "Live chat",
    "Отвечает": "Replies", "Болтает": "Chats", "Стиль": "Style", "По-свойски (с матом)": "Casual (with swearing)", "Вежливо": "Polite",
    "Приветствие": "Welcome", "Жалобы": "Reports", "Команда «жалоба»": "“report” command", "Команды": "Commands",
    "Общий сбор": "Rally", "Цитатник": "Quotes", "Мог-баттлы": "Mog battles", "Конкурсы": "Giveaways", "Предложка": "Suggestions",
    "Картинки «нарисуй»": "Image generation", "Скачивание «скачай»": "Downloads", "Скачивание по ссылке": "Auto download",
    "Игры": "Games", "«кто …»": "“who …”", "Репутация": "Reputation", "Варны": "Warns", "Лимит до автомута": "Warns until auto-mute",
    "Срок жизни варна": "Warn lifetime", "7 д": "7 d", "30 д": "30 d", "90 д": "90 d", "Бессрочно": "Forever",
    "База спамеров": "Spammer database", "Новички из базы спамеров": "Newcomers in spammer DB", "Уведомлять": "Notify", "Банить": "Ban",
    "Гостевые боты": "Guest bots", "Режим": "Mode", "Белый список": "Allowlist", "Запретить": "Block",
    "Заявки без капчи": "Requests without captcha", "Админам": "To admins", "Принять": "Approve",
    "Язык": "Language", "Язык / Language": "Language", "Русский": "Русский", "English": "English",
    "В меню": "To menu", "К разделам": "Back to sections", "Меню": "Menu", "Все настройки": "All settings",
    "Исключить": "Remove", "Отмена": "Cancel", "Да": "Yes", "Забанить": "Ban", "Это не он": "Not him",
    "Нори Premium": "Nori Premium", "Бан везде": "Ban everywhere",
}
USER_LANG: dict[int, str] = {}          # user_id -> language_code из Telegram (личные чаты)
_MARK = re.compile(r"^((?:[✅❌•⬅️➡️◀️▶️]\s*)*)(?:([^\w\s«»(]{1,4})\s+)?(.*)$", re.DOTALL)
_BOLD = re.compile(r"<b>([^<>]{1,60})</b>")
_CODE = re.compile(r"<code>(.*?)</code>", re.DOTALL)
_PH_ORDER = sorted(PHRASES, key=len, reverse=True)


def _code_en(m: re.Match) -> str:
    inner = m.group(1)
    low = inner.lower()
    for ru in sorted(_REVERSE, key=len, reverse=True):
        if low == ru or low.startswith(ru + " "):
            rest = _DUR_BACK.sub(lambda mm: mm.group(1) + _DUR_BACK_MAP[mm.group(2)], inner[len(ru):])
            rest = " ".join(_ARG_BACK.get(w, w) for w in rest.split(" "))
            return "<code>" + _REVERSE[ru] + rest + "</code>"
    return m.group(0)


def translate(text: str | None, lang: str) -> str | None:
    if not text or lang != "en":
        return text
    out = _CODE.sub(_code_en, text)
    out = _BOLD.sub(lambda m: "<b>" + translate_button(m.group(1), lang) + "</b>", out)     # заголовки: «🛡 Капча» → «🛡 Captcha»
    for ru in _PH_ORDER:
        if ru in out:
            out = out.replace(ru, PHRASES[ru])
    return out


def translate_button(label: str, lang: str) -> str:
    if lang != "en" or not label:
        return label
    m = _MARK.match(label)
    lead, emoji, rest = (m.group(1) or "", m.group(2) or "", m.group(3)) if m else ("", "", label)
    if rest in EXACT:
        return lead + (emoji + " " if emoji else "") + EXACT[rest]
    return translate(label, lang)


def translate_markup(markup, lang: str):
    if lang != "en" or markup is None:
        return markup
    if isinstance(markup, InlineKeyboardMarkup):
        rows = [[b.model_copy(update={"text": translate_button(b.text, lang)}) for b in row] for row in markup.inline_keyboard]
        return markup.model_copy(update={"inline_keyboard": rows})
    return markup


_EMOJI_TAG = r"(?:<tg-emoji[^>]*>[^<]*</tg-emoji>\s*)*"
_INNER = re.compile(r"(<(?:tg-button|h[1-6]|th)\b[^>]*>)(" + _EMOJI_TAG + r")([^<]*)(</(?:tg-button|h[1-6]|th)>)")


def translate_html(text: str, lang: str) -> str:
    """HTML rich-сообщения: подписи кнопок, заголовков и шапки таблиц переводятся целиком (с учётом иконки <tg-emoji>
    слева), остальное — по словарю фраз."""
    if lang != "en" or not text:
        return text
    text = _INNER.sub(lambda m: m.group(1) + m.group(2) + translate_button(m.group(3).strip(), lang) + m.group(4), text)
    return translate(text, lang)


def _tr_value(v, lang: str):
    if isinstance(v, str):
        core = v.strip()
        lead, trail = v[:len(v) - len(v.lstrip())], v[len(v.rstrip()):]
        out = translate_button(core, lang) if len(core) < 60 else translate(core, lang)
        return lead + out + trail
    if isinstance(v, list):
        return [_tr_value(x, lang) for x in v]
    if isinstance(v, dict):
        return {k: (_tr_value(x, lang) if k in ("text", "caption") else _walk(x, lang)) for k, x in v.items()}
    return v


def _walk(v, lang: str):
    if isinstance(v, dict):
        return {k: (_tr_value(x, lang) if k in ("text", "caption") else translate_html(x, lang) if k == "html" and isinstance(x, str)
                    else _walk(x, lang)) for k, x in v.items()}
    if isinstance(v, list):
        return [_walk(x, lang) for x in v]
    return v


def translate_rich(msg, lang: str):
    """Переводит тексты внутри rich-сообщения (таблицы статистики и топов): заголовок, шапка, подписи."""
    try:
        return type(msg).model_validate(_walk(msg.model_dump(exclude_none=True), lang))
    except Exception:
        return msg


def pick_lang(setting: str | None, user_code: str | None = None) -> str:
    """Язык чата из настройки; для личек (настройки нет) — по языку Telegram пользователя."""
    if setting in ("ru", "en"):
        return setting
    return "en" if (user_code or "").lower().startswith("en") else "ru"


class TranslateMiddleware(BaseRequestMiddleware):
    """Переводит исходящие тексты и кнопки, если у чата язык en. Ничего не знает про хендлеры — работает на уровне запросов."""

    def __init__(self, db):
        self.db = db

    async def _lang(self, chat_id) -> str:
        if not isinstance(chat_id, int):
            return "ru"
        if chat_id > 0:                                   # личка: язык пользователя из Telegram
            return pick_lang(None, USER_LANG.get(chat_id))
        return pick_lang((await self.db.get_settings(chat_id)).get("lang"))

    async def __call__(self, make_request, bot: Bot, method):
        chat_id = getattr(method, "chat_id", None)
        if chat_id is not None and any(hasattr(method, a) for a in ("text", "caption", "reply_markup", "question")):
            lang = await self._lang(chat_id)
            if lang == "en":
                upd = {}
                for attr in ("text", "caption"):
                    v = getattr(method, attr, None)
                    if isinstance(v, str) and not getattr(method, "entities", None):   # текст с entities (правила чата) — как есть
                        upd[attr] = translate(v, lang)
                rm = getattr(method, "reply_markup", None)
                if rm is not None:
                    upd["reply_markup"] = translate_markup(rm, lang)
                rich = getattr(method, "rich_message", None)
                if rich is not None:
                    upd["rich_message"] = translate_rich(rich, lang)
                if upd:
                    method = method.model_copy(update=upd)
        return await make_request(bot, method)


class CommandAliasMiddleware(BaseMiddleware):
    """В английских чатах понимает английские команды (ban, mute, stats …): переписывает их в русские до разбора."""

    def __init__(self, db):
        self.db = db

    async def __call__(self, handler, m, data):
        if m.text and m.from_user is not None and not m.text.startswith("/"):
            setting = (await self.db.get_settings(m.chat.id)).get("lang") if m.chat.type in ("group", "supergroup") else None
            if pick_lang(setting, m.from_user.language_code) == "en":
                ru = alias_to_ru(m.text)
                if ru:
                    m = m.model_copy(update={"text": ru, "entities": None})
        return await handler(m, data)
