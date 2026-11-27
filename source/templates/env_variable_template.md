# Шаблон: новая переменная окружения

1. `bot/config.py` → `Config`: поле с значением по умолчанию, например `my_limit: int = 10`
2. `bot/config.py` → `load_config()`: `my_limit=_int_env("MY_LIMIT", 10),`
3. (если нужна проверка) `Config.validate()`: `if self.my_limit < 1: raise SystemExit("MY_LIMIT должен быть ≥ 1")`
4. `bot/main.py`, шаг 2.2: `dp["my_limit"] = cfg.my_limit` → в хендлере параметр `my_limit`
5. `.env.example`: строка с комментарием «что это и какое значение по умолчанию»
6. Docker: переменные берутся из `.env` автоматически (`env_file: .env` в docker-compose.yml)
Секреты (ключи API) — только в `.env`, никогда в коде и не в git.
