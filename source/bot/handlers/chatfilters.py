"""Команды управления стоп-словами/регулярками (ключ ДК «фильтры») и белым списком ссылок (ключ «ссылки»)."""
import html
import re
import time

from aiogram import F, Router
from aiogram.types import Message

from bot import ux
from bot import mod_service as ms
from bot.db import Database
from bot.fmt import pre_table, quote
from bot.filters import MAX_FILTERS, MAX_WORD_LEN, FilterError, normalize, validate_regex
from bot.links import normalize_domain
from bot.ranks import need_rank

router = Router(name="chatfilters")
_PATTERNS = [
    ("f_word", r"^\+фильтр\s+(.+)$"), ("f_regex", r"^\+регэксп\s+(.+)$"), ("f_del", r"^-фильтр\s+(\d{1,6})$"),
    ("f_list", r"^фильтры$"),
    ("l_add", r"^\+ссылка\s+(\S+)$"), ("l_del", r"^-ссылка\s+(\S+)$"), ("l_list", r"^ссылки$"),
]
_COMPILED = [(k, re.compile(p, re.IGNORECASE | re.DOTALL)) for k, p in _PATTERNS]
_LISTS = {"f_list", "l_list"}


def parse(text: str | None):
    t = (text or "").strip()
    for kind, rx in _COMPILED:
        m = rx.match(t)
        if m:
            return kind, m.groups()
    return None


@router.message(F.text.func(lambda t: parse(t) is not None))
async def cmd(message: Message, bot, db: Database) -> None:
    if message.chat.type not in ("group", "supergroup") or message.from_user is None:
        return
    kind, g = parse(message.text)
    chat, me, now = message.chat.id, message.from_user.id, int(time.time())
    key = "фильтры" if kind.startswith("f_") else "ссылки"
    need = need_rank(await db.get_access(chat), key)
    if await ms.effective_rank(bot, db, chat, me) < need:
        if kind not in _LISTS:               # слова «фильтры»/«ссылки» без прав — просто болтовня
            await ux.tell(message, f"⚠️ Эта команда доступна с ранга {need}.")
        return

    if kind == "f_list":
        rows = await db.list_filters(chat)
        if not rows:
            await message.reply("ℹ️ Фильтров нет. Добавить: <code>+фильтр слово</code> или <code>+регэксп выражение</code>.")
            return
        table = pre_table([(str(r["id"]), "слово" if r["kind"] == "word" else "regexp", r["pattern"]) for r in rows],
                          header=("№", "Тип", "Шаблон"), maxw=(4, 6, 22))
        await message.reply(f"📝 <b>Стоп-слова</b> · {len(rows)} из {MAX_FILTERS}\n{table}\nУдалить: <code>-фильтр номер</code>")
    elif kind == "f_word":
        word = " ".join(g[0].split())
        if len(word) > MAX_WORD_LEN or not normalize(word):
            await ux.tell(message, f"⚠️ Слово или фраза: от 1 до {MAX_WORD_LEN} символов, с буквами или цифрами.")
            return
        await _add(message, db, chat, me, now, "word", word)
    elif kind == "f_regex":
        try:
            validate_regex(g[0].strip())
        except FilterError as e:
            await ux.tell(message, f"❌ {html.escape(str(e))}")
            return
        await _add(message, db, chat, me, now, "regex", g[0].strip())
    elif kind == "f_del":
        ok = await db.delete_filter(chat, int(g[0]))
        await message.reply("🗑 Фильтр удалён." if ok else "Нет фильтра с таким номером.")

    elif kind == "l_list":
        links = sorted(await db.link_allow_set(chat))
        mode = (await db.get_settings(chat))["links_mode"]
        mode_ru = {"off": "ссылки разрешены всем", "newbies": "ссылки запрещены новичкам", "all": "ссылки запрещены всем"}[mode]
        body = quote("\n".join(html.escape(d) for d in links)) if links else "список пуст"
        await message.reply(f"🔗 <b>Белый список ссылок</b>\n{body}\n<i>Режим: {mode_ru}. Настройка — «Антиспам» (при включённом антиспаме).</i>\n"
                            "Добавить: <code>+ссылка домен</code> (<code>*.домен</code> — с поддоменами), убрать: <code>-ссылка домен</code>")
    elif kind in ("l_add", "l_del"):
        dom = normalize_domain(g[0])
        if dom is None:
            await ux.tell(message, "❌ Не похоже на домен. Пример: <code>+ссылка example.com</code>")
            return
        if kind == "l_add":
            ok = await db.add_link(chat, dom, me)
            await message.reply(f"✅ <code>{html.escape(dom)}</code> разрешён." if ok else "Этот домен уже в списке.")
        else:
            ok = await db.remove_link(chat, dom)
            await message.reply(f"🗑 <code>{html.escape(dom)}</code> убран." if ok else "Такого домена нет в списке.")


async def _add(message: Message, db: Database, chat: int, me: int, now: int, kind: str, pattern: str) -> None:
    fid = await db.add_filter(chat, kind, pattern, me, now, limit=MAX_FILTERS)
    if fid is None:
        await ux.tell(message, f"❌ Не добавлено: такой фильтр уже есть или достигнут лимит ({MAX_FILTERS}).")
    else:
        await message.reply(f"✅ Фильтр №{fid} добавлен. Действие при срабатывании — в настройках → «Стоп-слова».")
