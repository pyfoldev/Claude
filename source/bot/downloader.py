"""Скачивание видео и фото из соцсетей через yt-dlp.

Безопасность: принимаем только ссылки на известные соцсети (белый список доменов) и отключаем «универсальный»
загрузчик yt-dlp — иначе «скачай http://127.0.0.1:…» или ссылка на внутренний сервис отдала бы в чат то, что видно
только с сервера. Ограничения Telegram: бот отправляет файлы до 50 МБ — берём качество, которое влезает."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

MAX_BYTES = 48 * 1024 * 1024         # лимит отправки файла ботом — 50 МБ, держим запас
MAX_DURATION = 20 * 60               # дольше 20 минут не качаем
MAX_ITEMS = 10                       # карусель/альбом — до 10 штук (столько влезает в один альбом Telegram)
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}

# домен → название (для подписи). Поддомены разрешены (m.tiktok.com, www.instagram.com и т. п.).
SITES = {
    "tiktok.com": "TikTok", "instagram.com": "Instagram", "youtube.com": "YouTube", "youtu.be": "YouTube",
    "x.com": "X", "twitter.com": "X", "vk.com": "VK", "vkvideo.ru": "VK Видео", "vk.ru": "VK",
    "pinterest.com": "Pinterest", "pinterest.ru": "Pinterest", "pin.it": "Pinterest", "reddit.com": "Reddit",
    "redd.it": "Reddit", "twitch.tv": "Twitch", "likee.video": "Likee", "coub.com": "Coub", "dzen.ru": "Дзен",
    "rutube.ru": "Rutube", "ok.ru": "Одноклассники", "facebook.com": "Facebook", "fb.watch": "Facebook",
    "threads.net": "Threads", "threads.com": "Threads", "soundcloud.com": "SoundCloud", "vimeo.com": "Vimeo",
    "snapchat.com": "Snapchat", "tumblr.com": "Tumblr", "bilibili.com": "Bilibili", "kick.com": "Kick",
}
_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


def site_of(url: str) -> str | None:
    """Название соцсети или None, если домен не из белого списка (или это не http/https)."""
    try:
        p = urlparse(url)
        port = p.port
    except (ValueError, TypeError, AttributeError):
        return None
    if p.scheme not in ("http", "https") or not p.hostname or port not in (None, 80, 443) or p.username is not None or p.password is not None:
        return None
    host = p.hostname.lower().rstrip(".")
    for dom, name in SITES.items():
        if host == dom or host.endswith("." + dom):
            return name
    return None


def find_url(text: str) -> str | None:
    m = _URL.search(text or "")
    return m.group(0).rstrip(").,!?;:»") if m else None


@dataclass
class Result:
    title: str = ""
    videos: list[str] = field(default_factory=list)
    photos: list[str] = field(default_factory=list)
    too_big: int = 0


class DownloadFailed(Exception):
    pass


def _opts(tmpdir: str, cookies: str | None) -> dict:
    from yt_dlp.utils import match_filter_func
    o = {
        "outtmpl": os.path.join(tmpdir, "%(autonumber)02d_%(id).40s.%(ext)s"),
        # mp4 до ~45 МБ; если размер неизвестен — не выше 720p; иначе лучшее (размер проверим после)
        "format": ("bv*[ext=mp4][filesize<45M]+ba[ext=m4a]/b[ext=mp4][filesize<45M]/"
                   "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]/bv*[height<=720]+ba/b/best"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "playlist_items": f"1-{MAX_ITEMS}",
        "max_filesize": MAX_BYTES,
        "match_filter": match_filter_func(f"!duration | duration <= {MAX_DURATION}"),
        "allowed_extractors": ["default", "-generic"],     # без «универсального» загрузчика — только сайты
        "socket_timeout": 20,
        "retries": 2,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "restrictfilenames": True,
    }
    if cookies and os.path.exists(cookies):
        o["cookiefile"] = cookies                          # для Instagram/YouTube, которые просят вход
    return o


def download(url: str, tmpdir: str, cookies: str | None = None) -> Result:
    """Блокирующее скачивание (вызывать через asyncio.to_thread). DownloadFailed — с понятной причиной."""
    import yt_dlp
    if site_of(url) is None:
        raise DownloadFailed("эта ссылка не из поддерживаемых соцсетей")
    try:
        with yt_dlp.YoutubeDL(_opts(tmpdir, cookies)) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as e:
        msg = str(e).lower()
        if any(x in msg for x in ("login", "sign in", "private", "cookies", "authentication", "age")):
            raise DownloadFailed("сайт требует вход или это закрытый аккаунт") from e
        if "unsupported url" in msg or "no video" in msg:
            raise DownloadFailed("по этой ссылке нет видео или фото") from e
        raise DownloadFailed("не получилось скачать — ссылка недоступна или сайт её не отдал") from e
    res = Result(title=((info or {}).get("title") or "")[:200] if isinstance(info, dict) else "")
    for name in sorted(os.listdir(tmpdir)):
        path = os.path.join(tmpdir, name)
        ext = os.path.splitext(name)[1].lower()
        if not os.path.isfile(path) or name.endswith((".part", ".ytdl")):
            continue
        if os.path.getsize(path) > MAX_BYTES:
            res.too_big += 1
        elif ext in VIDEO_EXT:
            res.videos.append(path)
        elif ext in PHOTO_EXT:
            res.photos.append(path)
    if not res.videos and not res.photos:
        if res.too_big or (isinstance(info, dict) and info.get("duration") and info["duration"] > MAX_DURATION):
            raise DownloadFailed("файл слишком большой для Telegram (больше 50 МБ или длиннее 20 минут)")
        raise DownloadFailed("не нашёл в посте видео или фото")
    return res
