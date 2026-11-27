"""Скачивает гифки Gifukai в локальную папку, чтобы бот не ходил в API при каждом РП-действии.

    python bot.pyz gifs                       # всё нужное боту → data/gifs (по 12 гифок на действие и пару полов)
    python bot.pyz gifs --per 30 --max-mb 3   # больше гифок, файлы до 3 МБ
    python bot.pyz gifs --actions hug,kiss    # только эти действия
    python bot.pyz gifs --all-actions         # все 68 действий Gifukai, а не только используемые ботом
(из исходников: python -m bot.gifs_fetch ...)

Публичного списка у Gifukai нет, поэтому гифки собираются случайными запросами: для каждого действия и пары полов
(ff, fm, mf, mm) запрашиваем случайную гифку, пока не наберётся --per разных или пока новые не перестанут попадаться.
Повторный запуск докачивает недостающее и не качает уже скачанное. Результат: data/gifs/<действие>/<файл>.gif и
data/gifs/manifest.json (действие, тип, пара, аниме, размер) — по нему бот выбирает гифку (bot/gifs.py, GIFS_DIR).

Гифки конвертируются в mp4 (ffmpeg; Telegram показывает mp4 как гифку, а весит он в разы меньше); --keep-gif оставляет gif.
Объём: gif ~1 МБ, mp4 — порядка 100–200 КБ; по умолчанию получается около 100–300 МБ. Условия сервиса — https://gifukai.com
(гифки взяты из аниме; используйте для своего чата, не раздавайте как свой пакет)."""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.gifukai.com/v1"
UA = {"User-Agent": "ChatHelperBot-gif-fetch/1.0"}
PAIRINGS = ("ff", "fm", "mf", "mm")
KISS_TYPES = ("cheek", "forehead", "mouth")


_ALLOWED_HOSTS = frozenset({"api.gifukai.com", "cdn.gifukai.com"})
_ACTION = re.compile(r"[a-z0-9_-]{1,64}")


def _safe_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname in _ALLOWED_HOSTS
                and parsed.port in (None, 443) and parsed.username is None and parsed.password is None)
    except (TypeError, ValueError):
        return False


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _safe_url(newurl):
            raise urllib.error.URLError("redirect to an untrusted host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SafeRedirect())


def get_json(url: str, tries: int = 3):
    if not _safe_url(url):
        return None
    for i in range(tries):
        try:
            with _OPENER.open(urllib.request.Request(url, headers=UA), timeout=20) as r:
                raw = r.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            time.sleep(1 + i)
        except (urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(1 + i)
    return None


def bot_actions() -> dict[str, set[str | None]]:
    """Действия и типы, которые реально использует бот (bot/gifs.py: RP_MAP, PAIR_MAP, FAMILY_MAP)."""
    from bot import gifs
    out: dict[str, set] = {}
    for table in (gifs.RP_MAP, gifs.PAIR_MAP, gifs.FAMILY_MAP):
        for action, typ in table.values():
            out.setdefault(action, set()).add(typ)
    return out


def sample(action: str, typ: str | None, pair: str, per: int, max_bytes: int, known: set[str]) -> list[dict]:
    """Набирает до per разных гифок для (действие, тип, пара) случайными запросами."""
    found: dict[str, dict] = {}
    misses = 0
    for _ in range(per * 12):
        q = {"pairing": pair}
        if typ:
            q["type"] = typ
        d = get_json(f"{API}/{action}?{urllib.parse.urlencode(q)}")
        if d is None:
            break
        if not isinstance(d, dict):
            continue
        name = d.get("filename") or ""
        size = d.get("size_bytes")
        if not isinstance(name, str) or (size is not None and (type(size) is not int or size < 0)):
            continue
        if not re.fullmatch(r"[\w.-]+\.(gif|mp4|webm)", name) or not str(d.get("url", "")).startswith("https://cdn.gifukai.com/"):
            continue
        if name in found or (size is not None and size > max_bytes):
            misses += 1
        else:
            found[name] = d
            misses = 0
        if len(found) >= per or misses >= 25:      # 25 повторов подряд — гифки для этой пары кончились
            break
    return list(found.values())


def download(item: dict, dest: Path, max_bytes: int) -> bool:
    if not _safe_url(item.get("url", "")) or max_bytes <= 0:
        return False
    if dest.exists() and 0 < dest.stat().st_size <= max_bytes and dest.stat().st_size == item.get("size_bytes"):
        return True
    tmp = dest.with_suffix(".part")
    try:
        with _OPENER.open(urllib.request.Request(item["url"], headers=UA), timeout=60) as r, open(tmp, "wb") as f:
            size = 0
            while chunk := r.read(1 << 16):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("file too large")
                f.write(chunk)
        if item.get("size_bytes") and tmp.stat().st_size != item["size_bytes"]:
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(dest)
        return True
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        tmp.unlink(missing_ok=True)
        return False


def to_mp4(gif: Path, mp4: Path) -> bool:
    """gif → mp4 (h264, без звука, чётные размеры, faststart): Telegram показывает его как гифку, весит в разы меньше."""
    tmp = mp4.with_suffix(".part.mp4")
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(gif), "-an", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "27", "-movflags", "+faststart", str(tmp)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        tmp.unlink(missing_ok=True)
        return False
    if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(mp4)
    return True


def fetch_one(item: dict, folder: Path, convert: bool, max_bytes: int) -> str | None:
    """Скачивает гифку (и конвертирует в mp4). Возвращает имя итогового файла или None. Готовое не качает повторно."""
    name = item["filename"]
    if not isinstance(name, str) or not re.fullmatch(r"[\w.-]+\.(gif|mp4|webm)", name):
        return None
    final = folder / (Path(name).stem + ".mp4") if convert else folder / name
    if final.exists() and final.stat().st_size > 0:
        return final.name
    gif = folder / name
    if not download(item, gif, max_bytes):
        return None
    if not convert:
        return name
    ok = to_mp4(gif, final)
    if ok:
        gif.unlink(missing_ok=True)                                   # оригинал-gif больше не нужен
        return final.name
    return name                                                       # не сконвертировалось — оставляем gif


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default="data/gifs", help="папка (по умолчанию data/gifs в текущей папке)")
    ap.add_argument("--per", type=int, default=12, help="сколько разных гифок на действие и пару полов")
    ap.add_argument("--max-mb", type=float, default=2.5, help="не качать файлы тяжелее (МБ); Telegram плохо показывает тяжёлые")
    ap.add_argument("--actions", default="", help="через запятую; по умолчанию — те, что использует бот")
    ap.add_argument("--all-actions", action="store_true", help="все действия Gifukai")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--keep-gif", action="store_true", help="не конвертировать в mp4 (по умолчанию конвертируем через ffmpeg)")
    a = ap.parse_args()

    if a.per < 1 or a.workers < 1 or not 0 < a.max_mb <= 50:
        ap.error("--per и --workers должны быть положительными; --max-mb — от 0 до 50")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists() else {"items": []}
    have = {(i["file"]) for i in manifest["items"]}

    convert = not a.keep_gif
    if convert and not shutil.which("ffmpeg"):
        print("ffmpeg не найден — гифки останутся в gif (поставьте ffmpeg или используйте --keep-gif)", file=sys.stderr)
        convert = False

    listing = get_json(f"{API}/actions")
    if not listing:
        print("Gifukai API недоступен", file=sys.stderr)
        return 1
    available = {action for action in listing["actions"] if isinstance(action, str) and _ACTION.fullmatch(action)}
    if a.actions:
        wanted = {x.strip(): {None} for x in a.actions.split(",") if x.strip()}
        for k in wanted:
            if k == "kiss":
                wanted[k] = {None, *KISS_TYPES}
    elif a.all_actions:
        wanted = {k: ({None, *KISS_TYPES} if k == "kiss" else {None}) for k in available}
    else:
        wanted = bot_actions()
    jobs = [(act, typ, pair) for act, types in sorted(wanted.items()) if act in available
            for typ in sorted(t or "" for t in types) for pair in PAIRINGS]
    jobs = [(act, typ or None, pair) for act, typ, pair in jobs]
    print(f"действий: {len(wanted)}, заданий (действие × тип × пара): {len(jobs)}, по {a.per} гифок, до {a.max_mb} МБ")

    max_bytes = int(a.max_mb * 1e6)
    added = failed = 0
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for n, (job, items) in enumerate(zip(jobs, ex.map(lambda j: sample(*j, a.per, max_bytes, have), jobs)), 1):
            action, typ, pair = job
            (out / action).mkdir(exist_ok=True)
            # Один файл может относиться к нескольким парам: сохраняем каждую связь в манифесте.
            todo = items
            for item, fname in zip(todo, ex.map(lambda i: fetch_one(i, out / action, convert, max_bytes), todo)):
                if not fname:
                    failed += 1
                    continue
                rel = f'{action}/{fname}'
                if rel not in have:
                    manifest["items"].append({"action": action, "type": typ, "pairing": pair, "file": rel,
                                              "anime": item.get("anime"), "size": (out / rel).stat().st_size})
                    have.add(rel)
                    added += 1
                elif not any(i["file"] == rel and i["pairing"] == pair and i["type"] == typ for i in manifest["items"]):
                    manifest["items"].append({"action": action, "type": typ, "pairing": pair, "file": rel,
                                              "anime": item.get("anime"), "size": (out / rel).stat().st_size})
            print(f"[{n}/{len(jobs)}] {action}{'/' + typ if typ else ''} {pair}: найдено {len(items)}", flush=True)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
    total = sum(i["size"] or 0 for i in manifest["items"])
    print(f"готово: новых {added}, ошибок скачивания {failed}, всего записей {len(manifest['items'])}, файлов {len(have)}, "
          f"{total / 1e6:.0f} МБ → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
