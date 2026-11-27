# Шаблон: новая настройка чата (переключатель в «настройки»)

1. `bot/db.py` → `DEFAULT_SETTINGS`: `"example_on": 0,`   (0/1 — переключатель; строка — выбор)
2. `bot/handlers/settings.py` → `PAGES`, в нужную страницу:
   `("toggle", "example_on", "Моя функция"),`
   или `("choice", "example_mode", "Режим", [("Выкл", "off"), ("Вкл", "on")]),`
3. В коде: `if (await db.get_settings(chat_id))["example_on"]: ...`
4. (по желанию) подпись в английском интерфейсе — `bot/i18n.py` → `EXACT`.
