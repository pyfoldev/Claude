#!/usr/bin/env python3
"""Генератор заготовки нового модуля команд и автоподключение в main.py.

  python tools/new_handler.py pets                    # простой текстовый хендлер
  python tools/new_handler.py pets --kind economy     # со ставкой и монетами
  python tools/new_handler.py pets --kind target      # «действие @ник»
  python tools/new_handler.py pets --kind ai|menu|confirm|admin|toggle
  python tools/new_handler.py pets --dry-run          # показать, что изменится, ничего не записывая

Что делает: копирует templates/<kind>_template.py → bot/handlers/<имя>.py, переименовывает Router, добавляет импорт
и `<имя>_handlers.router` в bot/main.py (в конец списка ROUTERS, перед ai_handlers). Дальше правьте файл руками.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KINDS = {"text": "handler_template.py", "target": "command_with_target_template.py",
         "economy": "economy_command_template.py", "ai": "ai_command_template.py",
         "menu": "inline_menu_template.py", "confirm": "confirm_dialog_template.py",
         "admin": "admin_command_template.py", "toggle": "toggle_group_template.py"}
IMPORT_ANCHOR = "from bot.handlers import ai as ai_handlers\n"
ROUTER_ANCHOR = "            # >>> СЮДА добавляйте свой роутер"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", help="имя модуля: латиница/цифры/_ (например pets)")
    ap.add_argument("--kind", choices=sorted(KINDS), default="text")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,30}", a.name):
        print("Имя: строчные латинские буквы, цифры и _, начинается с буквы")
        return 2
    target = ROOT / "bot" / "handlers" / f"{a.name}.py"
    if target.exists():
        print(f"Файл уже существует: {target}")
        return 2
    code = (ROOT / "templates" / KINDS[a.kind]).read_text(encoding="utf-8")
    code = re.sub(r'Router\(name="[^"]+"\)', f'Router(name="{a.name}")', code, count=1)
    code = re.sub(r'PREFIX = "[a-z]+"', f'PREFIX = "{a.name[:6]}"', code)
    main_py = ROOT / "bot" / "main.py"
    src = main_py.read_text(encoding="utf-8")
    alias = f"{a.name}_handlers"
    if alias in src:
        print(f"В main.py уже есть {alias}")
        return 2
    if IMPORT_ANCHOR not in src or ROUTER_ANCHOR not in src:
        print("Не нашёл якоря в main.py (их нельзя удалять: «from bot.handlers import ai as ai_handlers» и «>>> СЮДА добавляйте свой роутер»)")
        return 2
    src = src.replace(IMPORT_ANCHOR, f"from bot.handlers import {a.name} as {alias}\n" + IMPORT_ANCHOR, 1)
    src = src.replace(ROUTER_ANCHOR, f"            {alias}.router,\n" + ROUTER_ANCHOR, 1)
    print(f"{'[dry-run] ' if a.dry_run else ''}создаю {target.relative_to(ROOT)}; подключаю {alias}.router в bot/main.py")
    if not a.dry_run:
        target.write_text(code, encoding="utf-8")
        main_py.write_text(src, encoding="utf-8")
        print("Готово. Правьте файл, затем: python tools/check_project.py")
        if a.kind == "toggle":
            print("⚠️ Для kind=toggle заведите ключ группы в bot/toggles.py (GROUPS) и bot/db.py (DEFAULT_SETTINGS), иначе Enabled(...) упадёт с KeyError.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
