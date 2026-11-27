"""Пакет бота. Файл .env читается СРАЗУ при импорте: часть модулей (rich_ui, ux, …) читает переключатели вроде RICH_UI или
EPHEMERAL при загрузке, а load_config() вызывается позже. В Docker (env_file) переменные и так уже в окружении."""
from dotenv import load_dotenv


def _load_dotenv(path: str = ".env") -> None:
    # Не подставляем ${...}: секреты и URL читаются буквально, окружение имеет приоритет.
    load_dotenv(path, override=False, interpolate=False)


_load_dotenv()

from bot import perf  # noqa: F401, E402 — ускорение фильтров aiogram (см. bot/perf.py), действует при любом импорте бота
