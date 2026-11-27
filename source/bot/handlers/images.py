"""«нарисуй <описание>» — картинка через Cloudflare Workers AI (FLUX.1 [schnell]).

Описание переводится ИИ в английский промпт (если есть ключ River); готовая картинка проверяется фильтром 18+.
Лимиты по тарифу (bot/plans.py: бесплатно / Premium) и IMG_GLOBAL_DAILY на весь бот (бережём бесплатный суточный лимит
Cloudflare). В чате выключается: настройки → «Команды»."""
from __future__ import annotations

import html
import logging
import re
import time

from aiogram import F, Router
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import plans
from bot import perf
from bot.db import Database
from bot.imagegen import ImageError
from bot.toggles import Enabled

router = Router(name="images")
router.message.filter(Enabled("img_on"))   # группу команд можно выключить в настройках → «Команды»
IMG_GLOBAL_DAILY = 300
IMG_NSFW_BLOCK = 60          # оценка фильтра 18+, с которой сгенерированное не отправляем
_last: dict[int, float] = {}
_DRAW = re.compile(r"^(?:нарисуй|сгенерируй|/img(?:@\w+)?)\s+(.{2,800})$", re.IGNORECASE | re.DOTALL)


@router.message(F.text.func(lambda t: bool(t) and _DRAW.match(t.strip()) is not None))
async def draw_cmd(message: Message, bot, db: Database, ai=None, imagegen=None, detector=None, rt=None,
                   owner_ids: frozenset = frozenset()) -> None:
    if imagegen is None or not imagegen.configured:
        await message.reply("🎨 Генерация картинок не настроена (нужны CF_ACCOUNT_ID и CF_API_TOKEN).")
        return
    if rt is not None and not rt.flag("ai"):
        await message.reply("🎨 ИИ временно отключён владельцем бота.")
        return
    uid, now = message.from_user.id, int(time.time())
    plan = await plans.plan_for(db, uid, owner_ids)
    prem = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⭐ Nori Premium", callback_data="prem:info")]])
    wait = plan.img_cooldown - (time.time() - _last.get(uid, 0))
    if wait > 0:
        await message.reply(f"⚠️ Подождите {int(wait) + 1} с перед следующей картинкой. С Premium — без ожидания.",
                            reply_markup=prem)
        return
    reserved = time.time()
    _last[uid] = reserved
    if not await db.take_quota(uid, "uimg", now, plan.img_daily):
        if _last.get(uid) == reserved:
            _last.pop(uid, None)
        await message.reply(f"⚠️ Лимит картинок на сегодня ({plan.img_daily}) исчерпан."
                            + ("" if plan is plans.PREMIUM else f" С Premium — {plans.PREMIUM.img_daily} в сутки."),
                            reply_markup=None if plan is plans.PREMIUM else prem)
        return
    if not await db.take_quota(0, "img_all", now, IMG_GLOBAL_DAILY):
        await db.refund_quota(uid, "uimg", now)
        if _last.get(uid) == reserved:
            _last.pop(uid, None)
        await message.reply("🎨 Общий лимит генерации на сегодня исчерпан, попробуйте завтра.")
        return
    if len(_last) > 20000:
        cutoff = time.time() - plans.FREE.img_cooldown
        for key, value in list(_last.items()):
            if value < cutoff:
                _last.pop(key, None)
    request = _DRAW.match(message.text.strip()).group(1).strip()
    perf.chat_action(bot, message.chat.id, "upload_photo")
    prompt = await ai.image_prompt(request) if ai is not None and getattr(ai, "has_river", False) else request
    try:
        image = await imagegen.generate(prompt)
    except ImageError as e:
        await db.refund_quota(uid, "uimg", now)                # сбой не съедает лимиты
        await db.refund_quota(0, "img_all", now)
        await message.reply(f"🎨 Не получилось: {html.escape(str(e))}")
        return
    try:
        if detector is None:
            raise RuntimeError("фильтр недоступен")
        if await detector.score_images([image]) >= IMG_NSFW_BLOCK:
            await message.reply("🎨 Получилось 18+ — такое не отправляю. Попробуйте другое описание.")
            return
    except Exception:
        logging.exception("nsfw check of generated image failed")
        await db.refund_quota(uid, "uimg", now)
        await message.reply("🎨 Не удалось проверить картинку, поэтому она не отправлена. Попробуйте позже.")
        return
    await message.reply_photo(BufferedInputFile(image, "nori.jpg"), caption=f"🎨 {html.escape(request[:150])}")
