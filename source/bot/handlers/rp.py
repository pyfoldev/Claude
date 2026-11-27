"""РП-команды: «обнять» ответом на сообщение или «обнять @ник»."""
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot import gender, gifs, ux
from bot.db import Database
from bot.mod_service import is_admin, real_reply
from bot.rp_data import catalog, is_adult, parse_rp
from bot.targets import mention, resolve_user

router = Router(name="rp")
COOLDOWN = 2
_last: dict[tuple[int, int], float] = {}


def _in_group(m: Message) -> bool:
    return m.chat.type in ("group", "supergroup")


@router.message(F.text.func(lambda t: parse_rp(t) is not None))
async def rp_cmd(message: Message, bot, db: Database, http=None) -> None:
    if not _in_group(message) or not (await db.get_settings(message.chat.id))["rp_on"]:
        return
    action, token = parse_rp(message.text)
    reply = real_reply(message)
    target = await resolve_user(db, token, reply)
    if target is None:
        return  # нет цели — это не команда, а обычная фраза
    tid, tname = target
    if reply is not None and token is None and reply.from_user and reply.from_user.is_bot and \
            reply.from_user.id != (await bot.me()).id:
        return
    if is_adult(action) and not (await db.get_settings(message.chat.id)).get("rp_adult", 0):
        await ux.tell(message, "🔞 Флирт и мат выключены в этой беседе. Включить могут админы: <code>+рп18</code>.")
        return
    if not await gender.ensure(message, db):               # пол — один раз, дальше помним
        return
    key = (message.chat.id, message.from_user.id)
    if time.time() - _last.get(key, 0) < COOLDOWN:
        return
    _last[key] = time.time()
    if tid == message.from_user.id:
        await message.reply("🙃 Сам себя? Выберите другого человека.")
        return
    if tid == (await bot.me()).id:
        await message.reply("🤖 Спасибо, но я всего лишь бот.")
        return
    ga = await gender.get(db, message.from_user.id)
    text = f"{action.emoji} " + gender.gz(action.text, ga).format(
        a=mention(message.from_user.id, message.from_user.full_name), b=mention(tid, tname))
    s = await db.get_settings(message.chat.id)
    reply_to = reply.message_id if (reply is not None and token is None) else None
    if await gifs.reply_gif(bot, http, message, text, gifs.RP_MAP.get(action.phrase), ga,
                            await gender.get(db, tid), reply_to=reply_to, enabled=bool(s.get("rp_gifs", 1))):
        return
    if reply_to:
        await message.answer(text, reply_to_message_id=reply_to)
    else:
        await message.answer(text)


@router.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("мой пол", "сменить пол", "выбрать пол")))
async def gender_change(message: Message, db: Database) -> None:
    u = message.from_user
    if u is None:
        return
    await message.reply("Кто ты? Выбор можно менять.", reply_markup=gender.kb(u.id))


@router.callback_query(F.data.startswith("gd:"))
async def gender_pick(cb: CallbackQuery, db: Database) -> None:
    await gender.on_pick(cb, db)


@router.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("рп", "рп команды", "рп список", "рп помощь")))
async def rp_list(message: Message, db: Database) -> None:
    adult = bool((await db.get_settings(message.chat.id)).get("rp_adult", 0)) if message.chat.type != "private" else False
    await message.answer(catalog(adult))


@router.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("+рп18", "-рп18")))
async def rp_adult_toggle(message: Message, bot, db: Database) -> None:
    if not _in_group(message):
        return
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await ux.tell(message, "⚠️ Включать флирт и мат в РП могут только админы.")
        return
    on = message.text.strip().startswith("+")
    await db.set_setting(message.chat.id, "rp_adult", 1 if on else 0)
    await message.reply("🔞 Флирт и мат в РП включены: только для взрослых участников беседы." if on else "🔞 Флирт и мат в РП выключены.")


@router.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("+рп", "-рп")))
async def rp_toggle(message: Message, bot, db: Database) -> None:
    if not _in_group(message):
        return
    if not await is_admin(bot, message.chat.id, message.from_user.id):
        await ux.tell(message, "⚠️ Включать и выключать РП могут только админы.")
        return
    on = message.text.strip().startswith("+")
    await db.set_setting(message.chat.id, "rp_on", 1 if on else 0)
    await message.reply("🎭 РП-команды и семья включены." if on else "🎭 РП-команды и семья выключены.")
