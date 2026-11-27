#!/usr/bin/env python3
"""Генерирует справочники в docs/ ИЗ КОДА (чтобы не устаревали):  python tools/gen_docs.py

  docs/COMMANDS.md   — команды из справки меню (handlers/menu.py → SECTION_DATA)
  docs/SETTINGS.md   — настройки чата: страницы, ключи, значения по умолчанию (settings.PAGES + db.DEFAULT_SETTINGS)
  docs/ROUTERS.md    — порядок роутеров (приоритет обработки) и описание каждого модуля
  docs/DB_TABLES.md  — таблицы БД и их колонки (db.SCHEMA)
  docs/ENV.md        — переменные окружения (.env.example)
Файлы помечены «АВТОГЕНЕРАЦИЯ» — руками их не правьте, правьте код и запускайте скрипт заново.
Работает без установленных зависимостей бота (разбор через ast/regex).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOT = ROOT / "bot"
DOCS = ROOT / "docs"
MARK = "<!-- АВТОГЕНЕРАЦИЯ: tools/gen_docs.py. Не редактируйте вручную. -->\n\n"


def rd(rel: str) -> str:
    return (BOT / rel).read_text(encoding="utf-8")


def commands() -> str:
    tree = ast.parse(rd("handlers/menu.py"))
    data = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "SECTION_DATA":
            data = ast.literal_eval(n.value)
    out = [MARK + "# Команды бота\n\nИсточник: `bot/handlers/menu.py` → `SECTION_DATA`.\n"]
    for key, (title, rows, hint) in data.items():
        out.append(f"\n## {title}\n")
        if hint:
            out.append(f"_{hint}_\n")
        out.append("| Команда | Что делает |\n|---|---|")
        out += [f"| `{c}` | {d} |" for c, d in rows]
    return "\n".join(out) + "\n"


def settings() -> str:
    defaults = {}
    for node in ast.parse(rd("db.py")).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "DEFAULT_SETTINGS":
            defaults = {k: (repr(v), "") for k, v in ast.literal_eval(node.value).items()}
    src = rd("handlers/settings.py")
    out = [MARK + "# Настройки чата\n\nИсточники: `bot/db.py` → `DEFAULT_SETTINGS`, `bot/handlers/settings.py` → `PAGES`.\n"]
    shown = set()
    for pm in re.finditer(r'^    "(\w+)": \("([^"]+)", \[(.*?)\n    \]\),', src, re.S | re.M):
        out.append(f"\n## {pm.group(2)}  (`{pm.group(1)}`)\n\n| Ключ | Подпись | Тип | По умолчанию |\n|---|---|---|---|")
        for rm in re.finditer(r'\("(toggle|choice)",\s*"([a-z0-9_]+)",\s*"([^"]+)"', pm.group(3)):
            kind, key, label = rm.groups()
            shown.add(key)
            out.append(f"| `{key}` | {label} | {kind} | {defaults.get(key, ('—',))[0]} |")
    rest = [k for k in defaults if k not in shown]
    if rest:
        out.append("\n## Остальные ключи (без страницы в меню)\n\n| Ключ | По умолчанию |\n|---|---|")
        out += [f"| `{k}` | {defaults[k][0]} |" for k in rest]
    return "\n".join(out) + "\n"


def routers() -> str:
    main = rd("main.py")
    aliases = {}
    for line in re.findall(r"from bot\.handlers import ([^\n]+)", main):      # «import a as x, b as y» тоже
        for part in line.split(","):
            bits = part.split(" as ")
            aliases[bits[-1].strip()] = bits[0].strip()
    aliases.update({a: m for m, a in re.findall(r"from bot import (\w+) as (\w+)", main)})
    block = re.search(r"ROUTERS = \[(.*?)\n        \]", main, re.S).group(1)
    out = [MARK + "# Порядок роутеров\n\nСверху вниз = приоритет: первый подошедший хендлер обрабатывает сообщение.\n"
           "Источник: `bot/main.py` → `ROUTERS`.\n"]
    n = 0
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("# ---"):
            out.append(f"\n### {line.strip('# -')}\n\n| # | Модуль | Назначение |\n|---|---|---|")
        elif line.startswith("#") or not line:
            continue
        else:
            ref = line.rstrip(",")
            alias = ref.split(".")[0]
            mod = aliases.get(alias, alias)
            path = BOT / "handlers" / f"{mod}.py"
            if not path.exists():
                path = BOT / f"{mod}.py"
            doc = ""
            if path.exists():
                d = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
                doc = d.strip().splitlines()[0] if d else ""
            n += 1
            out.append(f"| {n} | `{ref}` | {doc} |")
    return "\n".join(out) + "\n"


def tables() -> str:
    schema = re.search(r'SCHEMA = """(.*?)"""', rd("db.py"), re.S).group(1)
    out = [MARK + "# Таблицы БД\n\nИсточник: `bot/db.py` → `SCHEMA` (пары/семья — `bot/pair/`).\n"]
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+)\((.*?)\);", schema, re.S):
        cols = [c.strip() for c in re.split(r",\s*\n|,(?![^()]*\))", m.group(2)) if c.strip()]
        out.append(f"\n## `{m.group(1)}`\n")
        out += [f"- `{' '.join(c.split())}`" for c in cols if not c.startswith("--")]
    return "\n".join(out) + "\n"


def env() -> str:
    out = [MARK + "# Переменные окружения\n\nИсточник: `.env.example`. Читаются в `bot/config.py`.\n\n| Переменная | Пример / по умолчанию | Описание |\n|---|---|---|"]
    note = ""
    for line in (ROOT.parent / ".env.example").read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("#") and "=" not in s:
            note = (note + " " + s.lstrip("# ").strip()).strip()
        else:
            mm = re.match(r"#?\s*([A-Z][A-Z0-9_]+)=(.*)$", s)
            if mm:
                out.append(f"| `{mm.group(1)}`{' *(необязательно)*' if s.startswith('#') else ''} | `{mm.group(2) or '—'}` | {note} |")
                note = ""
            else:
                note = ""
    return "\n".join(out) + "\n"


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    for name, fn in (("COMMANDS.md", commands), ("SETTINGS.md", settings), ("ROUTERS.md", routers),
                     ("DB_TABLES.md", tables), ("ENV.md", env)):
        (DOCS / name).write_text(fn(), encoding="utf-8")
        print("записан docs/" + name)


if __name__ == "__main__":
    main()
