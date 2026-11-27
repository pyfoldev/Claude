"""ШАБЛОН ХЕНДЛЕРА — скопируйте в bot/handlers/<имя>.py, замените `example` и подключите в bot/main.py.

ПОДКЛЮЧЕНИЕ (2 строки в main.py):
    from bot.handlers import example as example_handlers          # в блок [1] импортов
    example_handlers.router,                                       # в список ROUTERS (выше ai_handlers!)
"""
import html
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup, Message

from bot import mod_service as ms     # ms.effective_rank(bot, db, chat_id, user_id) — ранг 0..5
from bot import style, ux             # style.ok/warn/fail/kv — оформление; ux.tell/react — ответ и реакция

router = Router(name="example")       # уникальное имя роутера

# ---------- КОНСТАНТЫ (удобно править в одном месте) ----------
MIN_RANK = 1                          # кто может пользоваться: 0 все, 1 модератор, 3 админ, 5 создатель
COOLDOWN_SEC = 30                     # пауза между вызовами одним человеком
TEXT_OK = "Готово!"                   # тексты ответов — меняйте здесь
HELP = "Формат: <code>пример текст</code>"

_RE = re.compile(r"^пример\s+(.+)$", re.IGNORECASE | re.DOTALL)   # русская команда без «/»
_last: dict[tuple[int, int], float] = {}   # кэш кулдауна; чтобы он чистился — добавьте в rollup_loop (main.py)


# ---------- 1. ТЕКСТОВАЯ КОМАНДА: «пример что-то» ----------
@router.message(F.text.func(lambda t: bool(t) and _RE.match(t.strip()) is not None))
async def example_cmd(message: Message, bot, db) -> None:
    # bot, db, ai, rt, http, owner_ids... — подставляются из dp[...] (см. main.py, шаг 2.2)
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return                                                      # только группы
    if await ms.effective_rank(bot, db, message.chat.id, message.from_user.id) < MIN_RANK:
        return                                                      # нет прав — молча игнорируем
    arg = _RE.match(message.text.strip()).group(1)
    settings = await db.get_settings(message.chat.id)               # настройки чата (db.py → DEFAULT_SETTINGS)
    # ... ваша логика ...
    kb = InlineKeyboardMarkup(inline_keyboard=[[B(text="Нажми", callback_data="example:press:1")]])
    await ux.tell(message, style.ok(html.escape(arg)), reply_markup=kb)   # сообщение, удалится само через TTL


# ---------- 2. СЛЭШ-КОМАНДА: /example ----------
@router.message(Command("example"))
async def example_slash(message: Message) -> None:
    await ux.tell(message, HELP)


# ---------- 3. КНОПКА (callback_data = "example:<действие>:<значение>") ----------
@router.callback_query(F.data.startswith("example:press:"))
async def example_press(cb: CallbackQuery, db) -> None:
    value = cb.data.split(":")[2]
    await ux.tell_cb(cb, f"Нажато: {html.escape(value)}")
