"""«скан» ответом на медиа: показывает, что видит фильтр 18+ (для модераторов, удобно подбирать строгость)."""
import html

from aiogram import F, Router
from aiogram.types import Message

from bot import ux
from bot import mod_service as ms
from bot import nsfw as nsfw_mod
from bot.db import Database

router = Router(name="scan")


@router.message(F.text.func(lambda t: bool(t) and t.strip().lower() in ("скан", "скан 18+", "скан 18")))
async def scan_cmd(message: Message, bot, db: Database, detector=None) -> None:
    if message.chat.type not in ("group", "supergroup"):
        return
    r = ms.real_reply(message)
    if r is None or not nsfw_mod.has_checkable_media(r):
        return  # «скан» без медиа — просто слово
    if await ms.effective_rank(bot, db, message.chat.id, message.from_user.id) < 1:
        return
    if detector is None:
        await ux.tell(message, "❌ Фильтр 18+ не загружен на этом сервере.")
        return
    images = await nsfw_mod.images_from_message(bot, r)
    if not images:
        await ux.tell(message, "❌ Не смог получить картинку для проверки (файл слишком большой или формат не поддерживается).")
        return
    try:
        score, labels = await detector.explain_images(images)
    except Exception:
        await ux.tell(message, "❌ Не удалось проверить медиа. Попробуйте позже или проверьте работу модели на сервере.")
        return
    s = await db.get_settings(message.chat.id)
    found = "\n".join(f"• {html.escape(c)}: {v * 100:.0f}%" for c, v in labels if v >= 0.2) or "ничего заметного"
    verdict = "🚫 было бы удалено" if score >= s["nsfw_threshold"] else "✅ прошло бы"
    on = "включён" if s["nsfw_on"] else "ВЫКЛЮЧЕН (включите в «настройки» → «Фильтр 18+»)"
    await message.reply(f"🔎 <b>Скан 18+</b>: оценка <b>{score:.0f}%</b> при пороге {s['nsfw_threshold']}% — {verdict}\n"
                        f"Кадров проверено: {len(images)}\nНайдено моделью:\n{found}\n\nФильтр в чате: {on}. "
                        "Админы и модераторы фильтром не проверяются, поэтому свои тесты делайте со второго аккаунта.")
