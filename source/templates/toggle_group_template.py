"""ШАБЛОН: группа команд, которую админ чата включает/выключает в «настройки → Команды».

Шаги:
  1) bot/toggles.py → GROUPS:        "pets_on": "Питомцы (…команды…)"
  2) bot/db.py → DEFAULT_SETTINGS:   "pets_on": 1      (1 — включено по умолчанию)
  3) в этом файле — фильтр на весь роутер (одна строка!).
Если группа выключена, ВСЕ команды роутера молча игнорируются.
"""
from aiogram import F, Router
from aiogram.types import Message

from bot.toggles import Enabled

router = Router(name="pets")
router.message.filter(Enabled("pets_on"))      # ← вся магия здесь; Enabled("ключ") должен быть в toggles.GROUPS


@router.message(F.text.lower() == "питомец")
async def pet(message: Message) -> None:
    await message.reply("🐾 Мяу!")
