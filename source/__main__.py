"""Запуск Chat Helper из одного файла: распаковать себя в кэш (один раз на версию) и запустить bot.main."""
import hashlib
import os
import runpy
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path


def _unpack() -> Path:
    archive = Path(os.path.dirname(os.path.abspath(__file__)))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()[:16]
    # Не используем общий /tmp напрямую: другой пользователь мог бы заранее
    # подложить исполняемый код в предсказуемый каталог версии.
    base = Path(os.environ.get("CHAT_HELPER_CACHE") or (Path(tempfile.gettempdir()) / f"chat-helper-cache-{os.getuid()}"))
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = base.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise RuntimeError(f"Небезопасный каталог кэша {base}: нужен каталог текущего пользователя без записи для других")
    target = base / f"chat-helper-{digest}"
    if not (target / ".ok").is_file():
        tmp = Path(tempfile.mkdtemp(prefix="chat-helper-tmp-", dir=base))
        try:
            with zipfile.ZipFile(archive) as z:
                z.extractall(tmp)
            (tmp / ".ok").write_text("ok")
            try:
                tmp.rename(target)
            except OSError:
                if not (target / ".ok").is_file():
                    raise RuntimeError(f"Неполный каталог кэша {target}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return target


def main() -> None:
    root = str(_unpack())
    sys.path[:] = [root] + [p for p in sys.path if not p.endswith(".pyz")]
    # перезапуск по команде владельца делает `python -m bot.main` — ему нужен тот же путь к коду
    os.environ["PYTHONPATH"] = root + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")
    if len(sys.argv) > 1 and sys.argv[1] == "probe":          # python bot.pyz probe <chat_id> — диагностика эмодзи
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        runpy.run_module("bot.probe_emoji", run_name="__main__", alter_sys=True)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "gifs":           # python bot.pyz gifs — скачать гифки Gifukai в data/gifs
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        runpy.run_module("bot.gifs_fetch", run_name="__main__", alter_sys=True)
        return
    runpy.run_module("bot.main", run_name="__main__", alter_sys=True)


main()
