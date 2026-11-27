"""Тарифы: бесплатный и Premium (подписка за звёзды Telegram). Здесь только цифры и «какой тариф у человека»."""
from __future__ import annotations

import time
from dataclasses import dataclass

PREMIUM_PRICE = 70                 # звёзд за 30 дней (PREMIUM_PRICE в .env)
PREMIUM_DAYS = 30
PREMIUM_PERIOD = PREMIUM_DAYS * 86400   # Telegram принимает для подписок за звёзды только 30 дней


@dataclass(frozen=True)
class Plan:
    name: str
    ai_daily: int          # вопросов к ИИ в сутки (лично)
    ai_cooldown: int       # секунд между вопросами
    ai_max_tokens: int     # длина ответа
    ai_reply_chars: int
    img_daily: int         # картинок в сутки
    img_cooldown: int
    choose_model: bool     # выбор модели ИИ
    ai_private: bool       # ИИ в личке с ботом


FREE = Plan("Бесплатный", ai_daily=25, ai_cooldown=20, ai_max_tokens=800, ai_reply_chars=2000,
            img_daily=5, img_cooldown=45, choose_model=False, ai_private=False)
PREMIUM = Plan("Premium", ai_daily=150, ai_cooldown=0, ai_max_tokens=1600, ai_reply_chars=3500,
               img_daily=30, img_cooldown=0, choose_model=True, ai_private=True)


async def plan_for(db, user_id: int, owner_ids: frozenset = frozenset(), now: int | None = None) -> Plan:
    """Владельцы бота — всегда Premium; остальные — по оплаченной подписке."""
    if user_id in owner_ids:
        return PREMIUM
    until = await db.premium_until(user_id)
    return PREMIUM if until and until > (int(time.time()) if now is None else now) else FREE


def benefits_text(price: int = PREMIUM_PRICE) -> str:
    return (f"⭐ <b>Nori Premium</b> — {price} звёзд в месяц\n"
            f"• ИИ без кулдауна (бесплатно — раз в {FREE.ai_cooldown} с)\n"
            f"• {PREMIUM.ai_daily} вопросов к ИИ в сутки вместо {FREE.ai_daily}, ответы длиннее и подробнее\n"
            "• выбор модели ИИ: <code>модель</code>\n"
            "• ИИ в личке с ботом\n"
            f"• {PREMIUM.img_daily} картинок в сутки вместо {FREE.img_daily}, без ожидания: <code>нарисуй …</code>\n"
            "Подписка продлевается автоматически, отменить можно в любой момент в Telegram.")
