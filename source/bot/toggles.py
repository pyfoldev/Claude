"""Включение и выключение целых групп команд в чате (настройки → «Команды»).

Фильтр вешается на роутер целиком: `router.message.filter(Enabled("mod_on"))`. Если группа выключена, команды
этой группы в чате молча игнорируются (полезно, когда модерирует другой бот). В личке фильтр ничего не запрещает;
кнопки под уже отправленными сообщениями продолжают работать; настройки и веб-панель доступны всегда — включить обратно можно."""
from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import Message

from bot.db import Database

# ключ настройки -> подпись (порядок = порядок в меню настроек)
# ВКЛЮЧАТЕЛИ ГРУПП КОМАНД. Новая группа, которую админ может выключить:
#   1) добавьте "ключ_on": "подпись" сюда;  2) заведите "ключ_on": 1 в DEFAULT_SETTINGS (db.py);
#   3) в вашем handlers/xxx.py: router.message.filter(Enabled("ключ_on"))
GROUPS = {
    "mod_on": "Модерация: бан, мут, кик, варн, чистка, откат, ранги, история, массовый кик",
    "svc_on": "Сервисы: калк, курс, крипто, вики, факт, маршрут, гороскоп",
    "cards_on": "Коллекционные карточки («карточка», «альбом», «обмен»)",
    "stats_on": "Статистика: «стата», топы",
    "rally_on": "«Общий сбор» (зовёт всех)",
    "quotes_on": "Цитатник",
    "mog_on": "Мог-баттлы",
    "giveaway_on": "Конкурсы (новые; идущие доиграют)",
    "suggest_on": "Предложка («+предложка текст»)",
    "img_on": "Генерация картинок («нарисуй …»)",
    "dl_on": "Скачивание видео/фото из соцсетей («скачай ссылка»)",
    "dl_auto": "…и сразу по ссылке на TikTok/Reels/Shorts без команды",
}


# Фильтр роутера: «группа команд включена в этом чате?» (в личке — всегда да)
class Enabled(Filter):
    def __init__(self, key: str):
        if key not in GROUPS:
            raise KeyError(key)
        self.key = key

    async def __call__(self, message: Message, db: Database) -> bool:
        if message.chat.type not in ("group", "supergroup"):
            return True
        return bool((await db.get_settings(message.chat.id))[self.key])


# То же самое для обычного кода: if await enabled(db, chat_id, "mod_on"): ...
async def enabled(db: Database, chat_id: int, key: str) -> bool:
    return bool((await db.get_settings(chat_id))[key])
