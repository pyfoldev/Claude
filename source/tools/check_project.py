#!/usr/bin/env python3
"""Проверка проекта БЕЗ запуска бота и без установки зависимостей:  python tools/check_project.py

Что проверяет:
  1. все .py файлы компилируются (нет синтаксических ошибок);
  2. каждый handlers/*.py, где есть `router = Router(...)`, подключён в main.py (импорт + ROUTERS);
  3. все ключи из toggles.GROUPS и из страниц настроек (settings.PAGES) заведены в db.DEFAULT_SETTINGS;
  4. все ключи DEFAULT_ACCESS (ранги команд) — целые числа 0..5;
  5. ai_handlers.router — последний в ROUTERS (иначе ИИ «съедает» команды);
  6. переменные из config.py есть в .env.example (предупреждение).
Код выхода 0 — всё хорошо, 1 — есть ошибки (удобно для CI).
"""
from __future__ import annotations

import ast
import compileall
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOT = ROOT / "bot"
errors: list[str] = []
warnings: list[str] = []


def read(rel: str) -> str:
    return (BOT / rel).read_text(encoding="utf-8")


def check_compile() -> None:
    ok = compileall.compile_dir(str(ROOT), quiet=1, force=True, rx=re.compile(r"(__pycache__|\.git)"))
    if not ok:
        errors.append("Есть файлы с синтаксическими ошибками (см. вывод выше)")


def check_routers() -> None:
    main = read("main.py")
    m = re.search(r"ROUTERS = \[(.*?)\n        \]", main, re.S)
    if not m:
        errors.append("main.py: не найден список ROUTERS")
        return
    body = "\n".join(l for l in m.group(1).splitlines() if not l.strip().startswith("#"))   # без комментариев
    used = re.findall(r"([A-Za-z_]+)\.(?:router|guard)", body)
    aliases_rev: dict[str, str] = {}                    # алиас → имя модуля (учитывает «import a as x, b as y» в одной строке)
    for line in re.findall(r"from bot\.handlers import ([^\n]+)", main):
        for part in line.split(","):
            bits = part.split(" as ")
            aliases_rev[bits[-1].strip()] = bits[0].strip()
    registered = {aliases_rev.get(u, u) for u in used}
    for f in sorted((BOT / "handlers").glob("*.py")):
        if f.stem == "__init__":
            continue
        if re.search(r"^router\s*=\s*Router", f.read_text(encoding="utf-8"), re.M) and f.stem not in registered:
            errors.append(f"handlers/{f.name}: есть router, но он не подключён в main.py → ROUTERS")
    if used and used[-1] != "ai_handlers":
        errors.append("ROUTERS: ai_handlers.router должен быть ПОСЛЕДНИМ (иначе ИИ перехватывает команды)")


def check_settings() -> None:
    db = read("db.py")
    defaults = set()
    for node in ast.parse(db).body:        # разбор через ast: в одной строке может быть несколько ключей
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DEFAULT_SETTINGS":
            defaults = set(ast.literal_eval(node.value))
    if not defaults:
        errors.append("db.py: не найден DEFAULT_SETTINGS")
        return
    for key in re.findall(r'^\s*"([a-z0-9_]+)":\s*"', read("toggles.py"), re.M):
        if key not in defaults:
            errors.append(f"toggles.GROUPS: ключ «{key}» не заведён в DEFAULT_SETTINGS")
    for _, key in re.findall(r'\("(toggle|choice)",\s*"([a-z0-9_]+)"', read("handlers/settings.py")):
        if key not in defaults:
            errors.append(f"settings.PAGES: ключ «{key}» не заведён в DEFAULT_SETTINGS")


def check_access() -> None:
    tree = ast.parse(read("ranks.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DEFAULT_ACCESS":
            for k, v in zip(node.value.keys, node.value.values):
                if not (isinstance(v, ast.Constant) and isinstance(v.value, int) and 0 <= v.value <= 5):
                    errors.append(f"ranks.DEFAULT_ACCESS[{ast.literal_eval(k)!r}]: ранг должен быть числом 0..5")


def check_env() -> None:
    cfg = read("config.py")
    example = (ROOT.parent / ".env.example")
    if not example.exists():
        return
    text = example.read_text(encoding="utf-8")
    for var in sorted(set(re.findall(r'os\.environ\.get\("([A-Z0-9_]+)"', cfg))):
        if var not in text:
            warnings.append(f".env.example: нет переменной {var} (описана в config.py)")


def main() -> int:
    for fn in (check_compile, check_routers, check_settings, check_access, check_env):
        fn()
    for w in warnings:
        print("⚠️ ", w)
    for e in errors:
        print("❌", e)
    print("\n" + ("✅ Всё в порядке" if not errors else f"Найдено ошибок: {len(errors)}"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
