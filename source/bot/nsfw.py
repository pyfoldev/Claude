"""Локальный фильтр 18+ на NudeNet (ONNX, работает на CPU, ничего не отправляет наружу)."""
from __future__ import annotations

import asyncio
import io
import logging
import threading

from PIL import Image

from bot import media

# вес класса: насколько явным считаем найденное
WEIGHTS = {
    "FEMALE_GENITALIA_EXPOSED": 1.0,
    "MALE_GENITALIA_EXPOSED": 1.0,
    "ANUS_EXPOSED": 1.0,
    "FEMALE_BREAST_EXPOSED": 0.9,
    "BUTTOCKS_EXPOSED": 0.7,
}


def score_from_detections(dets: list[dict]) -> float:
    """Оценка 0..100 по найденным NudeNet классам (максимум по уверенности × вес)."""
    best = 0.0
    for d in dets:
        w = WEIGHTS.get(d.get("class", ""))
        if w:
            best = max(best, float(d.get("score", 0)) * w)
    return round(best * 100, 1)


MAX_PIXELS = 30_000_000  # защита от «картинок-бомб»: файл мал, а в памяти сотни МБ


def media_key(m) -> str | None:
    """Стабильный id содержимого — чтобы один и тот же стикер/фото не гонять через модель снова."""
    for obj in ((m.photo[-1] if m.photo else None), m.sticker, m.video, m.animation, m.video_note, m.document):
        if obj is not None:
            return obj.file_unique_id
    return None


def _to_png(data: bytes) -> bytes:
    """Любую картинку (jpg/webp/gif/png) → PNG с альфа-каналом, как ждёт NudeNet."""
    with Image.open(io.BytesIO(data)) as img:
        if img.width * img.height > MAX_PIXELS:
            raise ValueError("слишком большая картинка")
        img.seek(0)
        buf = io.BytesIO()
        img.convert("RGBA").save(buf, "PNG")
        return buf.getvalue()


class NsfwScanError(Exception):
    """Невозможно надёжно проверить все переданные изображения."""


class NsfwDetector:
    def __init__(self) -> None:
        self._det = None
        self._load_lock = threading.Lock()

    def _load(self):
        if self._det is None:
            with self._load_lock:
                if self._det is None:
                    from nudenet import NudeDetector
                    self._det = NudeDetector()
        return self._det

    def score_image(self, data: bytes) -> float:
        det = self._load()
        return score_from_detections(det.detect(_to_png(data)))

    def detect_labels(self, data: bytes) -> list[tuple[str, float]]:
        """Все найденные моделью классы (для команды «скан»): [(класс, уверенность 0..1)], по убыванию."""
        dets = self._load().detect(_to_png(data))
        return sorted(((d["class"], float(d["score"])) for d in dets), key=lambda x: -x[1])

    async def explain_images(self, images: list[bytes]) -> tuple[float, list[tuple[str, float]]]:
        def run():
            best, labels = 0.0, []
            for img in images:
                try:
                    dets = self._load().detect(_to_png(img))
                    labels += [(d["class"], float(d["score"])) for d in dets]
                    best = max(best, score_from_detections(dets))
                except Exception as exc:
                    raise NsfwScanError("не удалось проверить изображение") from exc
            return best, sorted(labels, key=lambda x: -x[1])[:8]
        if not images:
            raise NsfwScanError("нет изображений для проверки")
        return await asyncio.to_thread(run)

    async def score_images(self, images: list[bytes]) -> float:
        def run() -> float:
            best = 0.0
            for img in images:
                try:
                    best = max(best, self.score_image(img))
                except Exception as exc:
                    raise NsfwScanError("не удалось проверить изображение") from exc
            return best
        if not images:
            raise NsfwScanError("нет изображений для проверки")
        return await asyncio.to_thread(run)


async def images_from_message(bot, m) -> list[bytes]:
    """Картинки/кадры из сообщения для проверки. Пусто — если проверять нечего или файл слишком велик."""
    try:
        if m.photo:
            p = m.photo[-1]
            data = await media.download(bot, p.file_id, p.file_size, 8 * 1024 * 1024)
            return [data] if data else []
        if m.sticker:
            thumb = await _thumb(bot, m.sticker)
            if m.sticker.is_animated:  # .tgs (Lottie) не растровый: проверяем превью-картинку стикера
                return thumb
            data = await media.download(bot, m.sticker.file_id, m.sticker.file_size, 4 * 1024 * 1024)
            if not data:
                return thumb
            frames = await media.extract_frames(data, ".webm", 2) if m.sticker.is_video else [data]
            return frames or thumb
        for obj, suffix in ((m.video, ".mp4"), (m.animation, ".mp4"), (m.video_note, ".mp4")):
            if obj:
                thumb = await _thumb(bot, obj)  # превью — запасной вариант, если ffmpeg не справится
                data = await media.download(bot, obj.file_id, obj.file_size, 20 * 1024 * 1024)
                frames = await media.extract_frames(data, suffix, 6 if obj is m.animation else 4) if data else []
                return frames + thumb if frames else thumb
        if m.document and (m.document.mime_type or "").startswith("video/"):      # гиф/ролик, отправленные «как файл»
            thumb = await _thumb(bot, m.document)
            data = await media.download(bot, m.document.file_id, m.document.file_size, 20 * 1024 * 1024)
            frames = await media.extract_frames(data, ".mp4", 6) if data else []
            return frames + thumb if frames else thumb
        if m.document and (m.document.mime_type or "").startswith("image/"):
            data = await media.download(bot, m.document.file_id, m.document.file_size, 8 * 1024 * 1024)
            if data and (m.document.mime_type or "") == "image/gif":                   # анимированная гифка-файл: несколько кадров
                frames = await media.extract_frames(data, ".gif", 6)
                if frames:
                    return frames
            return [data] if data else []
    except Exception:
        logging.exception("nsfw: не удалось получить медиа")
    return []


async def _thumb(bot, obj) -> list[bytes]:
    t = getattr(obj, "thumbnail", None)
    if t is None:
        return []
    data = await media.download(bot, t.file_id, getattr(t, "file_size", None), 2 * 1024 * 1024)
    return [data] if data else []


def has_checkable_media(m) -> bool:
    return bool(m.photo or m.sticker or m.video or m.animation or m.video_note
                or (m.document and (m.document.mime_type or "").startswith(("image/", "video/"))))
