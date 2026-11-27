"""Работа с файлами сообщений: скачивание, кадры из видео, звук для расшифровки (ffmpeg)."""
from __future__ import annotations

import asyncio
import io
import math
import shutil
import tempfile
from pathlib import Path

class DownloadTooLarge(ValueError):
    pass


class LimitedBuffer(io.BytesIO):
    """Прерывает скачивание до записи данных сверх лимита в память."""

    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def write(self, data):
        if self.tell() + len(data) > self.limit:
            raise DownloadTooLarge
        return super().write(data)


MAX_DOWNLOAD = 20 * 1024 * 1024  # лимит Bot API на скачивание файлов
MAX_AUDIO_SECONDS = 20 * 60
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MAX_FRAME_PIXELS = 30_000_000
FRAME_SCALE = "scale='min(1280,iw)':'min(1280,ih)':force_original_aspect_ratio=decrease"


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


async def download(bot, file_id: str, size: int | None = None, limit: int = MAX_DOWNLOAD) -> bytes | None:
    """Скачать файл в память. None — если файл больше лимита."""
    if size is not None and size > limit:
        return None
    with LimitedBuffer(limit) as buf:
        try:
            await bot.download(file_id, destination=buf)
        except DownloadTooLarge:
            return None
        return buf.getvalue()


async def avatar_info(bot, user_id: int) -> tuple[bytes | None, str | None]:
    """(картинка, постоянный id аватарки) — id нужен, чтобы понимать, сменил ли человек аватарку."""
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if not photos or not photos.total_count or not photos.photos:
            return None, None
        sizes = photos.photos[0]
        pick = next((p for p in sizes if max(p.width, p.height) >= 480), sizes[-1])
        data = await download(bot, pick.file_id, getattr(pick, "file_size", None), 5 * 1024 * 1024)
        return data, getattr(sizes[0], "file_unique_id", None) if data else None
    except Exception:
        return None, None


async def avatar(bot, user_id: int) -> bytes | None:
    """Текущая аватарка пользователя (средний размер, ~640 px). None — фото нет, скрыто настройками или сбой."""
    return (await avatar_info(bot, user_id))[0]


async def _run(*args: str) -> int:
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try:
        return await asyncio.wait_for(proc.wait(), timeout=60)
    except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass  # процесс успел завершиться после проверки
        await proc.wait()
        if isinstance(exc, asyncio.CancelledError):
            raise
        return -1


async def _duration(src: Path) -> float | None:
    """Длительность ролика в секундах (ffprobe), None — не удалось."""
    if shutil.which("ffprobe") is None:
        return None
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-protocol_whitelist", "file", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(src),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        value = float(out.decode().strip())
        return value if math.isfinite(value) and value > 0 else None
    except (asyncio.TimeoutError, ValueError, asyncio.CancelledError) as exc:
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass  # процесс успел завершиться после проверки
        await proc.wait()
        if isinstance(exc, asyncio.CancelledError):
            raise
        return None


async def extract_frames(data: bytes, suffix: str = ".mp4", count: int = 3) -> list[bytes]:
    """До `count` кадров, равномерно по всей длине видео/гиф/кружка (JPEG): откровенный кадр может быть и в конце ролика."""
    if not ffmpeg_available():
        return []
    count = max(1, min(int(count), 8))
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / f"in{suffix}"
        src.write_bytes(data)
        out = Path(d) / "f_%d.jpg"
        dur = await _duration(src)
        rate = f"{count}/{max(dur, 0.5):.2f}" if dur else "1/2"          # count кадров на всю длину; нет длины — раз в 2 с
        await _run("ffmpeg", "-v", "error", "-protocol_whitelist", "file", "-max_pixels", str(MAX_FRAME_PIXELS), "-i", str(src), "-vf", f"fps={rate},{FRAME_SCALE}",
                   "-frames:v", str(count), str(out))
        frames = sorted(Path(d).glob("f_*.jpg"))
        if not frames:  # очень короткий ролик: берём первый кадр
            await _run("ffmpeg", "-v", "error", "-protocol_whitelist", "file", "-max_pixels", str(MAX_FRAME_PIXELS), "-i", str(src), "-vf", FRAME_SCALE, "-frames:v", "1", str(Path(d) / "f_1.jpg"))
            frames = sorted(Path(d).glob("f_*.jpg"))
        return [f.read_bytes() for f in frames]


async def to_mp3(data: bytes, suffix: str = ".ogg") -> bytes | None:
    """Звук любого файла (голосовое, кружок, видео) → моно mp3 16 кГц для расшифровки."""
    if not ffmpeg_available():
        return None
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d) / f"in{suffix}", Path(d) / "out.mp3"
        src.write_bytes(data)
        rc = await _run("ffmpeg", "-v", "error", "-protocol_whitelist", "file", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
                        "-b:a", "48k", "-t", str(MAX_AUDIO_SECONDS), "-fs", str(MAX_AUDIO_BYTES), str(dst))
        return dst.read_bytes() if rc == 0 and dst.exists() and dst.stat().st_size <= MAX_AUDIO_BYTES else None
