"""Nori Premium (подписка за звёзды Telegram), выбор модели ИИ и промокоды.

«премиум» / «/premium» — что даёт и статус, кнопка оплаты (счёт-подписка на 30 дней, продлевается автоматически);
оплата → successful_payment → Premium до даты окончания подписки. «модель» — выбор модели ИИ (Premium).
«промокод КОД» — Premium по промокоду; владелец: «+промокод [КОД] [дней] [активаций]», «-промокод КОД», «промокоды».
Владелец бота (в личке): «выдать премиум <id> <дней>», «возврат <id>» (возврат звёзд за последний платёж), «подписчики»."""
from __future__ import annotations

import html
import logging
import re
import time
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (CallbackQuery, InlineKeyboardButton as B, InlineKeyboardMarkup,
                           LabeledPrice, Message, PreCheckoutQuery)

from bot import ux
from bot import plans
from bot.db import Database

router = Router(name="premium")
PAYLOAD = "nori_premium_30d"
MODELS_TTL = 3600
MODELS_MAX = 12
_NOT_CHAT = ("embed", "whisper", "tts", "rerank", "guard", "clip", "bge", "e5-", "diffusion", "flux", "sdxl", "ocr")
_models: tuple[float, list[str]] = (0.0, [])

_PREMIUM = re.compile(r"^(?:премиум|premium|/premium(?:@\w+)?|/start premium|подписка ии)$", re.IGNORECASE)
_MODEL = re.compile(r"^(?:модель|модели|/model(?:@\w+)?)$", re.IGNORECASE)
_GRANT = re.compile(r"^выдать премиум\s+(\d{1,15})(?:\s+(\d{1,4}))?$", re.IGNORECASE)
_REVOKE = re.compile(r"^снять премиум(?:\s+(пары))?\s+(\d{1,15})$", re.IGNORECASE)
_REFUND = re.compile(r"^возврат\s+(\d{1,15})$", re.IGNORECASE)
_PROMO_USE = re.compile(r"^(?:промокод|/promo(?:@\w+)?)\s+[\"«»']?([A-Za-z0-9_-]{3,32})[\"«»']?$", re.IGNORECASE)
_PROMO_NEW = re.compile(r"^\+промокод(?:\s+([A-Za-z0-9_-]{3,32}))?(?:\s+(\d{1,4}))?(?:\s+(\d{1,6}))?$", re.IGNORECASE)
_PROMO_DEL = re.compile(r"^-промокод\s+([A-Za-z0-9_-]{3,32})$", re.IGNORECASE)
PROMO_TRIES = 5                    # попыток ввести промокод в час на человека (защита от перебора)
_promo_tries: dict[int, list[float]] = {}


from bot.pair import premium as pair_premium
from bot.pair.service import PairService


def _date(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%d.%m.%Y")


async def invoice_link(bot, price: int) -> str:
    return await bot.create_invoice_link(
        title="Nori Premium", description="ИИ без кулдауна, выбор модели, больше вопросов и картинок. 30 дней.",
        payload=PAYLOAD, currency="XTR", prices=[LabeledPrice(label="Premium на 30 дней", amount=price)],
        subscription_period=plans.PREMIUM_PERIOD)


async def _premium_card(bot, db: Database, uid: int, owner_ids: frozenset, price: int) -> tuple[str, InlineKeyboardMarkup | None]:
    until = await db.premium_until(uid)
    now = int(time.time())
    if uid in owner_ids:
        status = "\n\n✅ Вы владелец бота — Premium всегда включён."
    elif until and until > now:
        status = f"\n\n✅ У вас Premium до <b>{_date(until)}</b> (продлевается автоматически)."
    else:
        status = "\n\nСейчас у вас бесплатный тариф: " + (
            f"{plans.FREE.ai_daily} вопросов к ИИ в сутки, раз в {plans.FREE.ai_cooldown} с, {plans.FREE.img_daily} картинки.")
    kb = None
    if not (until and until > now) and uid not in owner_ids:
        try:
            kb = InlineKeyboardMarkup(inline_keyboard=[[B(text=f"⭐ Оформить за {price} звёзд", url=await invoice_link(bot, price))]])
        except Exception as e:
            logging.warning("premium: invoice link failed: %s", e)
    return plans.benefits_text(price) + status, kb


@router.message(F.text.func(lambda t: bool(t) and _PREMIUM.match(t.strip()) is not None))
async def premium_cmd(message: Message, bot, db: Database, owner_ids: frozenset = frozenset(),
                      premium_price: int = plans.PREMIUM_PRICE) -> None:
    text, kb = await _premium_card(bot, db, message.from_user.id, owner_ids, premium_price)
    await message.reply(text, reply_markup=kb)


@router.callback_query(F.data == "prem:info")
async def premium_info_cb(cb: CallbackQuery, bot, db: Database, owner_ids: frozenset = frozenset(),
                          premium_price: int = plans.PREMIUM_PRICE) -> None:
    text, kb = await _premium_card(bot, db, cb.from_user.id, owner_ids, premium_price)
    try:
        await bot.send_message(cb.from_user.id, text, reply_markup=kb)      # подробности и оплата — в личке
        await cb.answer()
    except Exception:
        if cb.message is not None:                        # бот не может написать в личку — карточку видит только нажавший
            await ux.tell_cb(cb, text, reply_markup=kb)
        else:
            await cb.answer()


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery, db: Database, premium_price: int = plans.PREMIUM_PRICE) -> None:
    pid = pair_premium.parse_payload(q.invoice_payload)
    if pid is not None:
        pair = await PairService(db).get_by_id(pid)
        ok = bool(pair) and pair["ended_at"] is None and q.from_user.id in (pair["u1"], pair["u2"]) \
            and q.currency == "XTR" and q.total_amount == pair_premium.PRICE
        await q.answer(ok=ok, error_message=None if ok else "Счёт устарел или пары уже нет.")
        return
    ok = q.invoice_payload == PAYLOAD and q.currency == "XTR" and q.total_amount == premium_price
    await q.answer(ok=ok, error_message=None if ok else "Счёт устарел — откройте «премиум» ещё раз.")


@router.message(F.successful_payment)
async def paid(message: Message, db: Database, owner_ids: frozenset = frozenset()) -> None:
    sp = message.successful_payment
    if sp.currency != "XTR" or type(sp.total_amount) is not int or sp.total_amount <= 0:
        logging.warning("premium: invalid payment currency or amount")
        return
    pid = pair_premium.parse_payload(sp.invoice_payload)
    if pid is not None:
        now = int(time.time())
        async with db.atomic():
            if not await db.payment_add(message.from_user.id, sp.telegram_payment_charge_id, sp.total_amount, now, False):
                return
            service = PairService(db)
            before = await service.get_by_id(pid, for_update=True)
            previous_until = (before["premium_until"] or 0) if before else 0
            until = await service.grant_premium(pid, now)
            await db.payment_effect(sp.telegram_payment_charge_id, "pair", pid, previous_until, until or 0)
            await db.log_owner(message.from_user.id, "pair_premium", f"оплата {sp.total_amount}⭐ пара {pid}", now)
        await message.answer(f"💎 Премиум пары активен до <b>{_date(until)}</b>!" if until else "⚠️ Платёж получен, но пары уже нет: напишите владельцу бота.")
        return
    if sp.invoice_payload != PAYLOAD:
        return
    uid, now = message.from_user.id, int(time.time())
    async with db.atomic():
        if not await db.payment_add(uid, sp.telegram_payment_charge_id, sp.total_amount, now, bool(sp.is_recurring)):
            return
        previous_until = await db.premium_lock_until(uid, now)
        until = sp.subscription_expiration_date or now + plans.PREMIUM_PERIOD
        await db.premium_grant(uid, int(until), now)
        await db.payment_effect(sp.telegram_payment_charge_id, "user", uid, previous_until, await db.premium_until(uid))
        await db.log_owner(uid, "premium", f"оплата {sp.total_amount}⭐ до {_date(int(until))}"
                           + (" (продление)" if sp.is_recurring else ""), now)
    await message.answer(f"⭐ Спасибо! Nori Premium активен до <b>{_date(int(until))}</b>.\n"
                         "Теперь: ИИ без кулдауна, больше вопросов и картинок, выбор модели — <code>модель</code>.")


# ---------- выбор модели ----------

async def _model_list(ai) -> list[str]:
    global _models
    if time.time() - _models[0] < MODELS_TTL and _models[1]:
        return _models[1]
    import os
    env = [m.strip() for m in os.environ.get("AI_MODELS", "").split(",") if m.strip()]
    found = env or [m for m in await ai.list_models() if not any(x in m.lower() for x in _NOT_CHAT)]
    default = getattr(ai, "river_model", None)
    out = ([default] if default else []) + [m for m in found if m != default]
    _models = (time.time(), out[:MODELS_MAX])
    return _models[1]


def _short(model: str) -> str:
    return model.rsplit("/", 1)[-1][:40]


@router.message(F.text.func(lambda t: bool(t) and _MODEL.match(t.strip()) is not None))
async def model_cmd(message: Message, db: Database, ai=None, owner_ids: frozenset = frozenset()) -> None:
    uid = message.from_user.id
    if (await plans.plan_for(db, uid, owner_ids)) is not plans.PREMIUM:
        await message.reply("🧠 Выбор модели ИИ — в Nori Premium.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            B(text="⭐ Nori Premium", callback_data="prem:info")]]))
        return
    if ai is None or not getattr(ai, "has_river", False):
        await ux.tell(message, "⚠️ ИИ не настроен.")
        return
    models = await _model_list(ai)
    current = (await db.get_ai_model(uid)) or (models[0] if models else "")
    rows = [[B(text=("✅ " if m == current else "") + _short(m), callback_data=f"mdl:{i}")] for i, m in enumerate(models)]
    await message.reply("🧠 <b>Модель ИИ</b> — для ваших вопросов «ии, …» (первая — по умолчанию):",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("mdl:"))
async def model_cb(cb: CallbackQuery, db: Database, ai=None, owner_ids: frozenset = frozenset()) -> None:
    uid = cb.from_user.id
    idx = cb.data.split(":", 1)[1]
    if (await plans.plan_for(db, uid, owner_ids)) is not plans.PREMIUM:
        await cb.answer("Выбор модели — в Premium.", show_alert=True)
        return
    models = await _model_list(ai) if ai is not None else []
    if not idx.isdigit() or int(idx) >= len(models):
        await cb.answer("Список моделей обновился — откройте «модель» ещё раз.", show_alert=True)
        return
    model = models[int(idx)]
    await db.set_ai_model(uid, None if int(idx) == 0 else model)
    await cb.answer(f"Модель: {_short(model)}")
    rows = [[B(text=("✅ " if m == model else "") + _short(m), callback_data=f"mdl:{i}")] for i, m in enumerate(models)]
    try:
        await cb.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    except Exception:
        pass


def _prem_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text="⭐ Nori Premium", callback_data="prem:info")]])


# ---------- владелец бота ----------

def _owner_cmd(t: str | None) -> bool:
    t = (t or "").strip()
    return bool(_GRANT.match(t) or _REVOKE.match(t) or _REFUND.match(t) or t.lower() == "подписчики")


async def _cancel_refunded_subscription(bot, db: Database, payment: dict) -> str:
    effect = await db.payment_get_effect(payment["charge_id"])
    if not effect or effect["kind"] != "user":
        return ""
    try:
        confirmed = await bot.edit_user_star_subscription(
            user_id=payment["user_id"], telegram_payment_charge_id=payment["charge_id"], is_canceled=True)
        if confirmed is True:
            return ""
    except Exception:
        pass
    return " Автопродление не удалось подтвердить: повторите эту команду или отмените подписку в Telegram."


@router.message(F.chat.type == "private", F.text.func(_owner_cmd))
async def owner_cmd(message: Message, bot, db: Database, owner_ids: frozenset = frozenset()) -> None:
    if message.from_user.id not in owner_ids:
        return
    t, now, oid = message.text.strip(), int(time.time()), message.from_user.id
    if t.lower() == "подписчики":
        active, stars = await db.premium_stats(now)
        await message.answer(f"⭐ Premium: активных {active}, получено {stars} звёзд (без возвратов).")
        return
    m = _REVOKE.match(t)
    if m:
        target = int(m.group(2))
        async with db.atomic():
            if m.group(1):
                changed = await PairService(db).revoke_premium(target)
            else:
                await db.premium_revoke(target)
                changed = True
            await db.log_owner(oid, "premium снят", f"{'pair' if m.group(1) else 'user'} {target}", now)
        await message.answer("✅ Premium снят." if changed else "Пара не найдена.")
        return
    m = _GRANT.match(t)
    if m:
        uid, days = int(m.group(1)), int(m.group(2) or plans.PREMIUM_DAYS)
        async with db.atomic():
            base = max(await db.premium_lock_until(uid, now), now)
            await db.premium_grant(uid, base + days * 86400, now)
            await db.log_owner(oid, "premium выдан", f"user {uid} на {days} дн.", now)
        await message.answer(f"✅ Пользователю {uid} выдан Premium до {_date(base + days * 86400)}.")
        return
    uid = int(_REFUND.match(t).group(1))
    pay = await db.payment_claim_refund(uid)
    if pay is None:
        await ux.tell(message, "❌ Платежей этого пользователя не найдено.")
        return
    if pay["refunded"] == 1:
        warning = await _cancel_refunded_subscription(bot, db, pay)
        await message.answer("↩️ Последний платёж уже возвращён." + warning)
        return
    try:
        confirmed = await bot.refund_star_payment(user_id=uid, telegram_payment_charge_id=pay["charge_id"])
        if confirmed is not True:
            raise RuntimeError("Telegram не подтвердил возврат")
    except Exception as e:
        if not (isinstance(e, TelegramBadRequest) and "CHARGE_ALREADY_REFUNDED" in e.message.upper()):
            await ux.tell(message, f"❌ Возврат не подтверждён: {html.escape(str(e)[:200])}. Повторите ту же команду для проверки этого платежа.")
            return
    async with db.atomic():
        changed, kind = await db.payment_finish_refund(pay["id"], now)
        if changed:
            await db.log_owner(oid, "premium возврат", f"user {uid}: {pay['amount']}⭐ ({kind})", now)
    warning = await _cancel_refunded_subscription(bot, db, pay)
    if not changed:
        await message.answer("↩️ Этот платёж уже возвращён." + warning)
        return
    result = "оплаченный период личного Premium отозван" if kind == "user" else "оплаченный период Premium пары отозван" if kind == "pair" else "подписка менялась после оплаты — оплаченный период нужно проверить вручную" if kind.endswith("_manual") else "тип старого платежа неизвестен — проверьте подписку вручную"
    await message.answer(f"↩️ Возвращено {pay['amount']} звёзд пользователю {uid}; {result}." + warning)



# ---------- промокоды ----------

def _promo_rate_ok(uid: int) -> bool:
    now = time.monotonic()
    if uid not in _promo_tries and len(_promo_tries) >= 20000:
        for key, history in list(_promo_tries.items()):
            if not history or now - history[-1] >= 3600:
                _promo_tries.pop(key, None)
        if len(_promo_tries) >= 20000:
            return False  # не обнуляем лимиты всех остальных пользователей
    tries = [t for t in _promo_tries.get(uid, []) if now - t < 3600]
    if len(tries) >= PROMO_TRIES:
        _promo_tries[uid] = tries
        return False
    tries.append(now)
    _promo_tries[uid] = tries
    return True


@router.message(F.text.func(lambda t: bool(t) and _PROMO_USE.match(t.strip()) is not None))
async def promo_use(message: Message, bot, db: Database, owner_ids: frozenset = frozenset()) -> None:
    """«промокод КОД» — активировать Premium по промокоду. В группе сообщение с кодом удаляем, чтобы его не увидели другие."""
    uid, now = message.from_user.id, int(time.time())
    code = _PROMO_USE.match(message.text.strip()).group(1).upper()
    if message.chat.type in ("group", "supergroup"):
        try:
            await bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass
    if not _promo_rate_ok(uid):
        await ux.tell(message, "❌ Слишком много попыток ввести промокод. Попробуйте через час.")
        return
    async with db.atomic():
        status, days = await db.promo_redeem(code, uid, now)
        if status == "ok":
            base = max(await db.premium_lock_until(uid, now), now)
            until = base + days * 86400
            await db.premium_grant(uid, until, now)
            await db.log_owner(uid, "premium промокод", f"{code}: {days} дн. до {_date(until)}", now)
    if status == "used":
        await ux.tell(message, "⚠️ Вы уже активировали этот промокод.")
        return
    if status != "ok":
        await ux.tell(message, "❌ Такого промокода нет или он закончился.")
        return
    who = message.from_user.full_name
    await message.answer(f"🎁 {html.escape(who)}, промокод активирован! Nori Premium на {days} дн. — до <b>{_date(until)}</b>.\n"
                         "ИИ без кулдауна, больше вопросов и картинок, выбор модели — <code>модель</code>.")


def _promo_admin_cmd(t: str | None) -> bool:
    t = (t or "").strip()
    return bool(_PROMO_NEW.match(t) or _PROMO_DEL.match(t) or t.lower() == "промокоды")


@router.message(F.chat.type == "private", F.text.func(_promo_admin_cmd))
async def promo_admin(message: Message, db: Database, owner_ids: frozenset = frozenset()) -> None:
    """Владелец: «+промокод [КОД] [дней] [активаций]» (по умолчанию — случайный код, 30 дней, 1 активация),
    «-промокод КОД», «промокоды»."""
    if message.from_user.id not in owner_ids:
        return
    t, now = message.text.strip(), int(time.time())
    if t.lower() == "промокоды":
        rows = await db.promo_list()
        if not rows:
            await message.answer("ℹ️ Промокодов нет. Создать: <code>+промокод</code> или <code>+промокод NORI2026 30 1</code>")
            return
        lines = [f"<code>{r['code']}</code> — {r['days']} дн., осталось активаций: {r['uses_left']}, активировали: {r['used']}"
                 for r in rows]
        await message.answer("🎁 <b>Промокоды</b>\n" + "\n".join(lines))
        return
    m = _PROMO_DEL.match(t)
    if m:
        ok = await db.promo_delete(m.group(1).upper())
        await message.answer("🗑 Промокод удалён." if ok else "Такого промокода нет.")
        return
    m = _PROMO_NEW.match(t)
    import secrets
    code = (m.group(1) or "NORI-" + "".join(secrets.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(8))).upper()
    days, uses = int(m.group(2) or plans.PREMIUM_DAYS), int(m.group(3) or 1)
    if not 1 <= days <= 3650 or uses < 1:
        await ux.tell(message, "⚠️ Дней — от 1 до 3650, активаций — от 1.")
        return
    if not await db.promo_create(code, days, uses, message.from_user.id, now):
        await ux.tell(message, "⚠️ Такой промокод уже есть.")
        return
    await message.answer(f"🎁 Промокод создан: <code>{code}</code>\nPremium на {days} дн., активаций: {uses}.\n"
                         f"Активировать: <code>промокод {code}</code> (лучше в личке с ботом).")
