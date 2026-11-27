"""Опросы: «опрос Вопрос | вариант | вариант» — настоящий опрос Telegram (можно менять голос, варианты перемешиваются
по желанию, результаты скрыты до закрытия — по ключам). Создают модераторы (ранг 1+)."""
import html
import re

from aiogram import F, Router
from aiogram.types import InputPollOption, Message

from bot import mod_service as ms
from bot import style, ux
from bot.parsing import parse_period

# Каждый файл handlers/*.py = свой Router; он подключается в main.py (список ROUTERS)
router = Router(name="polls")
_RE = re.compile(r"^опрос\s+(.+)$", re.IGNORECASE | re.DOTALL)
MAX_OPTIONS = 10
_FLAGS = {"скрыть": "hide", "перемешать": "shuffle", "несколько": "multi", "открытый": "public"}
HELP = ("Формат: <code>опрос Вопрос | вариант 1 | вариант 2</code>\n"
        "Ключи в конце: <code>несколько</code>, <code>скрыть</code> (результаты после закрытия), "
        "<code>перемешать</code>, <code>открытый</code> (видно, кто как голосовал), <code>1д</code> — закрыть через срок.")


def parse_poll(text: str):
    """(вопрос, [варианты], флаги, секунды до закрытия | None) или строка с ошибкой."""
    m = _RE.match(text.strip())
    if not m:
        return "Не понял формат."
    parts = [p.strip() for p in m.group(1).split("|")]
    flags, period = set(), None
    while len(parts) > 2:                                       # ключи и срок могут идти в любом порядке в конце
        last = parts[-1].lower()
        if last in _FLAGS:
            flags.add(_FLAGS[last])
        elif period is None and (d := parse_period(parts[-1])) is not None:
            period = int(d.total_seconds())
        else:
            break
        parts.pop()
    question, options = parts[0], [p for p in parts[1:] if p]
    if not question or len(question) > 300:
        return "Вопрос — от 1 до 300 символов."
    if not 2 <= len(options) <= MAX_OPTIONS:
        return f"Нужно от 2 до {MAX_OPTIONS} вариантов."
    if any(len(o) > 100 for o in options):
        return "Вариант — не длиннее 100 символов."
    if period is not None and not 5 <= period <= 2628000:
        return "Срок — от 5 секунд до 30 дней."
    return question, options, flags, period


# ХЕНДЛЕР: декоратор = фильтр (когда срабатывать), параметры (bot, db…) подставляются из dp[...] в main.py.
# Структура типичной команды: 1) проверка чата/ранга → 2) разбор текста → 3) действие → 4) ответ через ux.tell / реакция.
@router.message(F.text.func(lambda t: bool(t) and _RE.match(t.strip()) is not None))
async def poll_cmd(message: Message, bot, db) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    if await ms.effective_rank(bot, db, message.chat.id, message.from_user.id) < 1:
        return                                                    # «опрос …» от обычного участника — просто слова
    res = parse_poll(message.text)
    if isinstance(res, str):
        await ux.tell(message, style.warn(html.escape(res)) + "\n" + HELP)
        return
    question, options, flags, period = res
    try:
        await bot.send_poll(
            message.chat.id, question, [InputPollOption(text=o) for o in options], is_anonymous="public" not in flags,
            allows_multiple_answers=("multi" in flags) or None, allows_revoting=True,
            shuffle_options=("shuffle" in flags) or None, hide_results_until_closes=("hide" in flags) or None,
            open_period=period, message_thread_id=message.message_thread_id if message.is_topic_message else None)
    except Exception as e:
        await ux.tell(message, style.fail(f"Не получилось создать опрос: {html.escape(str(e))[:150]}"))
        return
    await ux.react(bot, message.chat.id, message.message_id, "👌")
