"""Скачивание видео и фото из соцсетей: «скачай <ссылка>» (или /dl), а если в чате включено — сразу по сообщению,
в котором только ссылка на соцсеть (TikTok, Reels, Shorts, X, VK, Pinterest…). Альбомы и карусели — до 10 штук.

Лимиты: DL_DAILY в сутки на человека, раз в DL_COOLDOWN с, не больше DL_PARALLEL загрузок одновременно на весь бот.
Выключается в чате: настройки → «Команды» (скачивание и отдельно — автоскачивание по ссылке)."""
from __future__ import annotations

import asyncio
import html
import logging
import re
import tempfile
import time

from aiogram import F, Router
from aiogram.types import FSInputFile, InputMediaPhoto, InputMediaVideo, Message

from bot import ux
from bot import downloader as dl
from bot import perf
from bot.db import Database
from bot.toggles import Enabled

router = Router(name="download")
router.message.filter(Enabled("dl_on"))   # группу команд можно выключить в настройках → «Команды»
DL_DAILY = 20
DL_COOLDOWN = 10
DL_PARALLEL = 2
DL_TIMEOUT = 240
_sem = asyncio.Semaphore(DL_PARALLEL)
_last: dict[int, float] = {}
_CMD = re.compile(r"^(?:скачай|скачать|/dl(?:@\w+)?|/download(?:@\w+)?)\s+(\S+)$", re.IGNORECASE)


def _bare_link(text: str | None) -> str | None:
    """Сообщение — только ссылка на соцсеть (без другого текста): для автоскачивания."""
    t = (text or "").strip()
    if not t or " " in t or "\n" in t:
        return None
    url = dl.find_url(t)
    return url if url and url == t.rstrip(").,!?;:»") and dl.site_of(url) else None


@router.message(F.text.func(lambda t: bool(t) and _CMD.match(t.strip()) is not None))
async def download_cmd(message: Message, bot, db: Database, downloader=None, ytdlp_cookies: str | None = None) -> None:
    url = dl.find_url(_CMD.match(message.text.strip()).group(1))
    if not url or dl.site_of(url) is None:
        await message.reply("Пришлите ссылку на пост из соцсети: TikTok, Instagram, YouTube, X, VK, Pinterest, Reddit…\n"
                            "Например: <code>скачай https://vt.tiktok.com/…</code>")
        return
    await _run(message, bot, db, url, downloader, ytdlp_cookies, auto=False)


@router.message(Enabled("dl_auto"), F.chat.type.in_({"group", "supergroup", "private"}),
                F.text.func(lambda t: _bare_link(t) is not None))
async def download_auto(message: Message, bot, db: Database, downloader=None, ytdlp_cookies: str | None = None) -> None:
    await _run(message, bot, db, _bare_link(message.text), downloader, ytdlp_cookies, auto=True)


async def _run(message: Message, bot, db: Database, url: str, downloader, cookies, auto: bool) -> None:
    uid, now = message.from_user.id, int(time.time())
    wait = DL_COOLDOWN - (time.time() - _last.get(uid, 0))
    if wait > 0:
        if not auto:
            await ux.tell(message, f"⚠️ Подождите {int(wait) + 1} с перед следующим скачиванием.")
        return
    # Резервируем кулдаун до обращения к БД, чтобы параллельные сообщения
    # одного человека не запускали сразу несколько скачиваний.
    reserved = time.time()
    _last[uid] = reserved
    try:
        allowed = await db.take_quota(uid, "udl", now, DL_DAILY)
    except BaseException:
        if _last.get(uid) == reserved:
            _last.pop(uid, None)
        raise
    if not allowed:
        if _last.get(uid) == reserved:
            _last.pop(uid, None)
        if not auto:
            await ux.tell(message, f"⚠️ Лимит скачиваний на сегодня ({DL_DAILY}) исчерпан — завтра можно ещё.")
        return
    if len(_last) > 20000:
        cutoff = time.time() - DL_COOLDOWN
        for key, value in list(_last.items()):
            if value < cutoff:
                _last.pop(key, None)
    site = dl.site_of(url) or "соцсеть"
    try:
        status = await message.reply(f"⬇ Скачиваю из {site}…")
    except BaseException:
        await db.refund_quota(uid, "udl", now)
        if _last.get(uid) == reserved:
            _last.pop(uid, None)
        raise
    fetch = downloader or dl.download
    tmp = tempfile.TemporaryDirectory(prefix="nori-dl-")
    # A timed-out thread cannot be cancelled. It must retain its semaphore slot and
    # directory until it actually finishes, including when the handler is cancelled.
    started = False
    async def fetch_limited():
        nonlocal started
        async with _sem:
            started = True
            perf.chat_action(bot, message.chat.id, "upload_video")
            return await asyncio.to_thread(fetch, url, tmp.name, cookies)

    task = asyncio.create_task(fetch_limited())
    deferred_cleanup = False
    try:
        res = await asyncio.wait_for(asyncio.shield(task), DL_TIMEOUT)
        await _send(message, bot, res, site, url)
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        deferred_cleanup = True
        def cleanup_when_done(completed):
            if not completed.cancelled():
                completed.exception()  # retrieve errors from abandoned downloads
            tmp.cleanup()
        task.add_done_callback(cleanup_when_done)
        # Задачу, ещё ожидающую слот, можно отменить: иначе она начнёт
        # скачивание уже после того, как пользователь получил тайм-аут.
        if not started:
            task.cancel()
        if isinstance(exc, asyncio.CancelledError):
            raise
        await db.refund_quota(uid, "udl", now)
        await _drop(bot, status)
        if not auto:
            await message.reply("😕 Не получилось скачать: сайт отвечает слишком долго. Попробуйте позже.")
        return
    except dl.DownloadFailed as e:
        await db.refund_quota(uid, "udl", now)                  # не скачалось — лимит не тратим
        reason = str(e) if isinstance(e, dl.DownloadFailed) else "слишком долго, сайт не отдал файл"
        await _drop(bot, status)
        if not auto:                                             # автоскачивание при неудаче молчит — не мусорим в чат
            await message.reply(f"😕 Не получилось: {html.escape(reason)}.")
        return
    except Exception as exc:
        # Ссылки могут содержать приватные токены в параметрах; в журнале они не нужны.
        logging.warning("download from %s failed: %s", site, type(exc).__name__)
        await db.refund_quota(uid, "udl", now)
        await _drop(bot, status)
        if not auto:
            await message.reply("😕 Не получилось скачать. Попробуйте позже.")
        return
    finally:
        if not deferred_cleanup:
            tmp.cleanup()
    await _drop(bot, status)


async def _drop(bot, m: Message | None) -> None:
    try:
        await bot.delete_message(m.chat.id, m.message_id)
    except Exception:
        pass


def _caption(site: str, title: str, url: str) -> str:
    """Не обрезать HTML-теги и сущности в подписи Telegram."""
    caption = f"🎥 <b>{html.escape(site[:40])}</b>"
    if title:
        fragments, used = [], 0
        for char in title[:150]:
            part = html.escape(char)
            if used + len(part) > 360:
                fragments.append("…")
                break
            fragments.append(part)
            used += len(part)
        caption += " · " + "".join(fragments)
    escaped_url = html.escape(url, quote=True)
    if len(escaped_url) <= 500:
        caption += f'\n<a href="{escaped_url}">источник</a>'
    return caption


async def _send(message: Message, bot, res: dl.Result, site: str, url: str) -> None:
    caption = _caption(site, res.title, url)
    items = [("video", p) for p in res.videos] + [("photo", p) for p in res.photos]
    items = items[:dl.MAX_ITEMS]
    if len(items) == 1:
        kind, path = items[0]
        if kind == "video":
            await message.reply_video(FSInputFile(path), caption=caption, supports_streaming=True)
        else:
            await message.reply_photo(FSInputFile(path), caption=caption)
        return
    media = []
    for i, (k, p) in enumerate(items):                       # подпись — только у первого (так её показывает Telegram);
        extra = {"caption": caption, "parse_mode": "HTML"} if i == 0 else {}   # объекты неизменяемые — задаём сразу
        media.append(InputMediaVideo(media=FSInputFile(p), supports_streaming=True, **extra) if k == "video"
                     else InputMediaPhoto(media=FSInputFile(p), **extra))
    await bot.send_media_group(message.chat.id, media=media, reply_to_message_id=message.message_id)
