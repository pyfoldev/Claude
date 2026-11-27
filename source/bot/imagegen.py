"""Генерация картинок через Cloudflare Workers AI (по умолчанию FLUX.1 [schnell] — бесплатная модель хорошего качества
в рамках суточного лимита Workers AI). Нужны CF_ACCOUNT_ID и CF_API_TOKEN (токен с правом «Workers AI»)."""
from __future__ import annotations

import base64
import binascii
import json

import aiohttp

DEFAULT_MODEL = "@cf/black-forest-labs/flux-1-schnell"
TIMEOUT = aiohttp.ClientTimeout(total=60)
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_RESPONSE_BYTES = 14 * 1024 * 1024


class ImageError(Exception):
    pass


class ImageGen:
    def __init__(self, session: aiohttp.ClientSession | None, account_id: str, token: str, model: str = DEFAULT_MODEL,
                 base: str = "https://api.cloudflare.com/client/v4"):
        self.session, self.account_id, self.token = session, account_id.strip(), token.strip()
        self.model = model or DEFAULT_MODEL
        self.base = base.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.session and self.account_id and self.token)

    async def generate(self, prompt: str, steps: int = 6) -> bytes:
        """Картинка (JPEG/PNG байты). ImageError — с понятным текстом."""
        if not self.configured:
            raise ImageError("генерация картинок не настроена")
        url = f"{self.base}/accounts/{self.account_id}/ai/run/{self.model}"
        try:
            async with self.session.post(url, timeout=TIMEOUT, headers={"Authorization": f"Bearer {self.token}"},
                                         json={"prompt": prompt[:2000], "steps": max(1, min(steps, 8))}) as r:
                ctype = r.headers.get("Content-Type", "")
                if r.status == 429:
                    raise ImageError("суточный лимит генерации исчерпан, попробуйте завтра")
                if r.status != 200:
                    raise ImageError(f"Cloudflare: HTTP {r.status}")
                limit = MAX_IMAGE_BYTES if ctype.startswith("image/") else MAX_RESPONSE_BYTES
                if r.content_length is not None and r.content_length > limit:
                    raise ImageError("Cloudflare: ответ слишком большой")
                body = bytearray()
                async for chunk in r.content.iter_chunked(64 * 1024):
                    body.extend(chunk)
                    if len(body) > limit:
                        raise ImageError("Cloudflare: ответ слишком большой")
                if ctype.startswith("image/"):
                    return bytes(body)
                data = json.loads(body)
        except (aiohttp.ClientError, TimeoutError, ValueError) as e:
            raise ImageError(f"Cloudflare недоступен: {e}") from e
        if not isinstance(data, dict) or not data.get("success", True):
            raise ImageError("Cloudflare: модель отказала (возможно, запрос нарушает правила)")
        img = (data.get("result") or {}).get("image") if isinstance(data.get("result"), dict) else None
        if not isinstance(img, str):
            raise ImageError("Cloudflare: неожиданный ответ")
        try:
            decoded = base64.b64decode(img, validate=True)
            if len(decoded) > MAX_IMAGE_BYTES:
                raise ImageError("Cloudflare: картинка слишком большая")
            return decoded
        except (binascii.Error, ValueError) as e:
            raise ImageError("Cloudflare: битая картинка") from e
