import os
import re
from urllib.parse import urlsplit
from dataclasses import dataclass


# ======= НАСТРОЙКИ БОТА =======
# Новая настройка из .env — три шага:
#   1) поле в Config ниже (с значением по умолчанию);
#   2) чтение в load_config(): os.environ.get("ИМЯ", ...);
#   3) пример в .env.example (+ проверка в validate(), если нужно).
# Потом в main.py её можно положить в dp["имя"] и получать в хендлерах параметром.
@dataclass
class Config:
    bot_token: str
    webapp_url: str
    owner_id: int
    webhook_secret: str
    db_path: str
    mode: str
    port: int = 8080
    webhook_url: str = ""   # куда Telegram шлёт обновления (порт 88/443/8443); по умолчанию — WEBAPP_URL
    owner_ids: frozenset = frozenset()
    database_url: str = ""
    river_api_key: str = ""
    river_base_url: str = "https://api.river.ai/v1"
    river_model: str = "deepseek-ai/DeepSeek-V4.1-Flash"
    river_vision_model: str = ""
    river_chat_vision_model: str = ""
    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai/v1"
    mistral_stt_model: str = "voxtral-mini-latest"
    update_workers: int = 64   # сколько обновлений обрабатывается одновременно (режим webhook)
    cf_account_id: str = ""        # Cloudflare Workers AI — генерация картинок
    cf_api_token: str = ""
    cf_image_model: str = "@cf/black-forest-labs/flux-1-schnell"
    premium_price: int = 70        # звёзд за 30 дней Premium

    # Проверка значений при старте: бот не запустится с ошибочной конфигурацией (SystemExit с понятным текстом)
    def validate(self) -> None:
        if not self.database_url and not self.db_path:
            raise SystemExit("DB_PATH не должен быть пустым")
        if self.mode not in ("polling", "webhook"):
            raise SystemExit("MODE должен быть polling или webhook")
        if not 1 <= self.port <= 65535:
            raise SystemExit("PORT должен быть от 1 до 65535")
        if self.update_workers < 1 or self.premium_price < 1:
            raise SystemExit("UPDATE_WORKERS и PREMIUM_PRICE должны быть положительными")
        if self.mode == "webhook":
            if not 16 <= len(self.webhook_secret) <= 256 or self.webhook_secret == "change-me-long-random" or not re.fullmatch(r"[A-Za-z0-9_-]+", self.webhook_secret):
                raise SystemExit("В режиме webhook задайте WEBHOOK_SECRET: 16–256 символов A–Z, a–z, 0–9, _ или -")
            try:
                base = self.webhook_url or self.webapp_url
                parsed = urlsplit(base)
                valid = parsed.scheme == "https" and parsed.hostname and parsed.port in (None, 80, 88, 443, 8443) and parsed.username is None and parsed.password is None and not parsed.query and not parsed.fragment and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in base)
            except ValueError:
                valid = False
            if not valid:
                raise SystemExit("WEBHOOK_URL должен быть HTTPS-адресом без пароля, query/fragment, порт 443, 80, 88 или 8443")


def _owner_ids() -> list[int]:
    """OWNER_ID=123 или несколько через запятую: OWNER_ID=123,456"""
    out = []
    for part in os.environ.get("OWNER_ID", "").replace(";", ",").split(","):
        part = part.strip()
        if not part or part == "0":
            continue
        if not re.fullmatch(r"[0-9]{1,19}", part) or not 0 < int(part) < 2**63:
            raise SystemExit("OWNER_ID должен содержать положительные числовые id через запятую")
        uid = int(part)
        if uid not in out:
            out.append(uid)
    return out


# Целое из переменной окружения: _int_env("PORT", 8080); при мусоре — понятная ошибка
def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        raise SystemExit(f"{name} должен быть целым числом")


# Читает .env / переменные окружения и собирает Config. СЮДА добавляйте чтение новых переменных.
def load_config() -> Config:
    from bot import _load_dotenv
    _load_dotenv()
    token = os.environ.get("BOT_TOKEN", "")
    if not token:
        raise SystemExit("BOT_TOKEN не задан (см. .env.example)")
    owners = _owner_ids()
    cfg = Config(
        bot_token=token,
        webapp_url=os.environ.get("WEBAPP_URL", "").rstrip("/"),
        owner_id=owners[0] if owners else 0,
        owner_ids=frozenset(owners),
        webhook_secret=os.environ.get("WEBHOOK_SECRET", ""),
        webhook_url=os.environ.get("WEBHOOK_URL", "").rstrip("/"),
        db_path=os.environ.get("DB_PATH", "data/bot.db") or "data/bot.db",
        mode=os.environ.get("MODE", "polling").strip().lower(),
        port=_int_env("PORT", 8080),
        database_url=os.environ.get("DATABASE_URL", ""),
        cf_account_id=os.environ.get("CF_ACCOUNT_ID", ""),
        cf_api_token=os.environ.get("CF_API_TOKEN", ""),
        cf_image_model=os.environ.get("CF_IMAGE_MODEL", "") or "@cf/black-forest-labs/flux-1-schnell",
        premium_price=_int_env("PREMIUM_PRICE", 70),
        river_api_key=os.environ.get("RIVER_API_KEY", ""),
        river_base_url=os.environ.get("RIVER_BASE_URL", "https://api.river.ai/v1").rstrip("/"),
        river_model=os.environ.get("RIVER_MODEL", "deepseek-ai/DeepSeek-V4.1-Flash"),
        river_vision_model=os.environ.get("RIVER_VISION_MODEL", ""),
        river_chat_vision_model=os.environ.get("RIVER_CHAT_VISION_MODEL", ""),
        mistral_api_key=os.environ.get("MISTRAL_API_KEY", ""),
        mistral_base_url=os.environ.get("MISTRAL_BASE_URL", "https://api.mistral.ai/v1").rstrip("/"),
        mistral_stt_model=os.environ.get("MISTRAL_STT_MODEL", "voxtral-mini-latest"),
        update_workers=_int_env("UPDATE_WORKERS", 64),
    )
    cfg.validate()
    return cfg
