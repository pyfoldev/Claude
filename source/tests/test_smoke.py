"""Дымовые тесты: проект цел. Не требуют сети, Telegram и зависимостей бота (только стандартная библиотека + pytest)."""
import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_check_project_passes():
    """tools/check_project.py (синтаксис, роутеры, настройки, ранги) завершается с кодом 0."""
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_project.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_templates_are_valid_python():
    for f in (ROOT / "templates").glob("*.py"):
        ast.parse(f.read_text(encoding="utf-8"), filename=str(f))


def test_ai_router_is_last():
    main = (ROOT / "bot" / "main.py").read_text(encoding="utf-8")
    body = main.split("ROUTERS = [", 1)[1].split("\n        ]", 1)[0]
    lines = [l.strip() for l in body.splitlines() if l.strip() and not l.strip().startswith("#")]
    assert lines[-1] == "ai_handlers.router,"
