"""Картинки-карточки (цитаты, мог-баттлы): шрифты с кириллицей, цветные эмодзи, круглые аватарки, перенос строк.

Шрифты — системные (в Docker ставятся fonts-dejavu-core и fonts-noto-color-emoji). Нет шрифта — встроенный в Pillow
(без кириллицы, но бот не падает); нет шрифта эмодзи — эмодзи пропускаются."""
from __future__ import annotations

import io
import math
from functools import lru_cache
from pathlib import Path

import regex
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

_FONT_DIRS = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/local/share/fonts")
_EMOJI_PATHS = ("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf", "/usr/share/fonts/noto/NotoColorEmoji.ttf")
_EMOJI_RE = regex.compile(r"\p{Extended_Pictographic}|\p{Regional_Indicator}")
_GRAPHEME = regex.compile(r"\X")
EMOJI_NATIVE = 109           # Noto Color Emoji — растровый шрифт, рисуется только этим размером

BG = (14, 14, 18)
FG = (240, 240, 245)
DIM = (150, 150, 162)
ACCENT = (110, 160, 255)


@lru_cache(maxsize=64)
def font(size: int, bold: bool = False, mono: bool = False):
    names = ((["DejaVuSansMono-Bold.ttf"] if bold else ["DejaVuSansMono.ttf"]) if mono else []) + \
        (["DejaVuSans-Bold.ttf"] if bold else ["DejaVuSans.ttf"])           # нет моноширинного — обычный
    for name in names:
        for d in _FONT_DIRS:
            p = Path(d) / name
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size=size)


@lru_cache(maxsize=1)
def _emoji_font():
    for p in _EMOJI_PATHS:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, EMOJI_NATIVE)
            except OSError:
                return None
    return None


@lru_cache(maxsize=512)
def _emoji_image(cluster: str, size: int) -> Image.Image | None:
    f = _emoji_font()
    if f is None:
        return None
    tile = Image.new("RGBA", (EMOJI_NATIVE * 2, EMOJI_NATIVE * 2), (0, 0, 0, 0))
    try:
        ImageDraw.Draw(tile).text((0, 0), cluster, font=f, embedded_color=True)
    except Exception:
        return None
    box = tile.getbbox()
    if box is None:
        return None
    return tile.crop(box).resize((size, size), Image.LANCZOS)


def _segments(text: str) -> list[tuple[bool, str]]:
    """[(эмодзи?, кусок)] — обычный текст склеивается, каждый эмодзи отдельно."""
    out: list[tuple[bool, str]] = []
    for g in _GRAPHEME.findall(text):
        is_e = bool(_EMOJI_RE.search(g))
        if not is_e and out and not out[-1][0]:
            out[-1] = (False, out[-1][1] + g)
        else:
            out.append((is_e, g))
    return out


def text_width(text: str, f) -> int:
    w = 0
    for is_e, s in _segments(text):
        w += int(f.size * 1.15) if is_e else int(f.getlength(s))
    return w


def draw_text(img: Image.Image, xy: tuple[int, int], text: str, f, fill=FG) -> int:
    """Рисует одну строку с эмодзи; возвращает ширину."""
    x, y = xy
    d = ImageDraw.Draw(img)
    for is_e, s in _segments(text):
        if is_e:
            em = _emoji_image(s, f.size)
            if em is not None:
                img.paste(em, (int(x), int(y + f.size * 0.12)), em)
            x += int(f.size * 1.15)
        else:
            d.text((x, y), s, font=f, fill=fill)
            x += f.getlength(s)
    return int(x - xy[0])


def fit(text: str, f, max_w: int) -> str:
    """Обрезает строку с «…», чтобы влезла в max_w."""
    if text_width(text, f) <= max_w:
        return text
    while text and text_width(text + "…", f) > max_w:
        text = text[:-1]
    return text + "…"


def wrap(text: str, f, max_w: int, max_lines: int | None = None) -> list[str]:
    lines: list[str] = []
    for para in (text or "").split("\n"):
        line = ""
        for word in para.split(" "):
            cand = f"{line} {word}" if line else word
            if text_width(cand, f) <= max_w:
                line = cand
                continue
            if line:
                lines.append(line)
            while text_width(word, f) > max_w:                 # очень длинное слово режем по буквам
                cut = len(word)
                while cut > 1 and text_width(word[:cut], f) > max_w:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        lines.append(line)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit(lines[-1] + "…", f, max_w)
    return lines


_PALETTE = [(231, 76, 60), (230, 126, 34), (241, 196, 15), (46, 204, 113), (26, 188, 156), (52, 152, 219),
            (155, 89, 182), (233, 30, 99)]


def avatar(data: bytes | None, size: int, name: str, uid: int) -> Image.Image:
    """Круглая аватарка; нет фото — цветной круг с первой буквой имени (как в Telegram)."""
    img = None
    if data:
        try:
            img = ImageOps.fit(Image.open(io.BytesIO(data)).convert("RGB"), (size, size), Image.LANCZOS)
        except Exception:
            img = None
    if img is None:
        img = Image.new("RGB", (size, size), _PALETTE[abs(uid) % len(_PALETTE)])
        letter = next((ch for ch in (name or "?") if ch.isalnum()), "?").upper()
        f = font(int(size * 0.45), bold=True)
        d = ImageDraw.Draw(img)
        w = f.getlength(letter)
        d.text(((size - w) / 2, size * 0.24), letter, font=f, fill=(255, 255, 255))
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask.resize((size, size), Image.LANCZOS))
    return out


def jpeg(img: Image.Image, quality: int = 90) -> bytes:
    """Для отправки в Telegram: JPEG кодируется в ~30 раз быстрее PNG с optimize и весит в разы меньше
    (Telegram всё равно пережимает фото). subsampling=0 — красный и зелёный текст без грязных краёв."""
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality, subsampling=0)
    return buf.getvalue()


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def rotated_text(text: str, f, fill, angle: float, stroke: int = 0) -> Image.Image:
    w = int(f.getlength(text)) + 20 + stroke * 2
    h = int(f.size * 1.4) + stroke * 2
    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((10 + stroke, stroke), text, font=f, fill=fill, stroke_width=stroke,
                              stroke_fill=(255, 255, 255, 255) if stroke else None)
    return tile.rotate(angle, expand=True, resample=Image.BICUBIC)


def angle_deg(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dy, dx))




# ---------- общие эффекты ----------

def gradient(size: tuple[int, int], c1, c2, horizontal: bool = False) -> Image.Image:
    """Плавный переход c1 → c2 (сверху вниз или слева направо)."""
    small = Image.new("RGBA", (2, 1) if horizontal else (1, 2))
    small.putdata([tuple(c1) + (() if len(c1) == 4 else (255,)), tuple(c2) + (() if len(c2) == 4 else (255,))])
    return small.resize(size, Image.BILINEAR)


def blurred_bg(data: bytes | None, size: tuple[int, int], uid: int, brightness: float = 0.33, blur: int = 22) -> Image.Image:
    """Фон из аватарки: увеличенная, размытая и затемнённая; без фото — тёмный градиент в цвет аватарки-заглушки."""
    w, h = size
    if data:
        try:
            src = ImageOps.fit(Image.open(io.BytesIO(data)).convert("RGB"), (w // 4, h // 4), Image.LANCZOS)
            src = src.filter(ImageFilter.GaussianBlur(blur / 4)).resize((w, h), Image.BICUBIC)
            return ImageEnhance.Brightness(src).enhance(brightness).convert("RGBA")
        except Exception:
            pass
    c = _PALETTE[abs(uid) % len(_PALETTE)]
    dark = tuple(int(v * 0.35) for v in c)
    small = Image.new("RGB", (2, 2))
    small.putdata([dark, (10, 10, 14), (12, 12, 16), tuple(int(v * 0.18) for v in c)])
    return small.resize((w, h), Image.BICUBIC).convert("RGBA")


def vignette(size: tuple[int, int], strength: int = 170) -> Image.Image:
    w, h = size
    mask = Image.new("L", (w // 8, h // 8), strength)
    ImageDraw.Draw(mask).ellipse((-w // 40, -h // 40, w // 8 + w // 40, h // 8 + h // 40), fill=0)
    mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) // 40)).resize((w, h), Image.BICUBIC)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    layer.putalpha(mask)
    return layer


def put_glow(img: Image.Image, box: tuple[int, int, int, int], color, radius: int = 28, ellipse: bool = True) -> None:
    """Мягкое свечение вокруг box. Размываем только нужный кусок, а не весь холст — в разы быстрее."""
    pad = radius * 3
    x0, y0 = int(box[0]) - pad, int(box[1]) - pad
    layer = Image.new("RGBA", (int(box[2] - box[0]) + 2 * pad, int(box[3] - box[1]) + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    inner = (pad, pad, pad + box[2] - box[0], pad + box[3] - box[1])
    (d.ellipse if ellipse else d.rectangle)(inner, fill=tuple(color) + (200,))
    _paste_clipped(img, layer.filter(ImageFilter.GaussianBlur(radius)), x0, y0)


def _paste_clipped(img: Image.Image, layer: Image.Image, x: int, y: int) -> None:
    """alpha_composite, которому можно отдать кусок, частично вылезающий за края картинки."""
    cx0, cy0 = max(0, -x), max(0, -y)
    cx1, cy1 = min(layer.width, img.width - x), min(layer.height, img.height - y)
    if cx1 > cx0 and cy1 > cy0:
        img.alpha_composite(layer.crop((cx0, cy0, cx1, cy1)), (x + cx0, y + cy0))


def panel(img: Image.Image, box: tuple[int, int, int, int], radius: int = 28, alpha: int = 150) -> None:
    """Полупрозрачная «стеклянная» плашка с тонкой рамкой."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=radius, fill=(8, 8, 12, alpha), outline=(255, 255, 255, 34), width=2)
    img.alpha_composite(layer)


def shadow_text(img: Image.Image, xy, text: str, f, fill=FG, shadow=(0, 0, 0), blur: int = 6, spread: int = 0) -> None:
    pad = blur * 3 + spread
    w, h = int(f.getlength(text)) + 2 * pad, int(f.size * 1.4) + 2 * pad
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((pad, pad + 3), text, font=f, fill=tuple(shadow) + (220,), stroke_width=spread,
                               stroke_fill=tuple(shadow) + (220,))
    _paste_clipped(img, layer.filter(ImageFilter.GaussianBlur(blur)), int(xy[0]) - pad, int(xy[1]) - pad)
    ImageDraw.Draw(img).text(xy, text, font=f, fill=fill)


# ---------- карточка цитаты ----------

QUOTE_BLUE = (92, 152, 255)


def quote_card(text: str, name: str, uid: int, avatar_bytes: bytes | None, date: str, chat_title: str,
               number: int | None = None) -> bytes:
    """Как скриншот-цитата: фон — размытая аватарка автора, слева большая круглая аватарка, справа текст моноширинным
    жирным и «— имя» синим. Длинный текст — меньше кегль, совсем длинный — обрезается."""
    W, H, av = 1200, 600, 400
    img = blurred_bg(avatar_bytes, (W, H), uid)
    img.alpha_composite(gradient((W, H), (0, 0, 0, 40), (0, 0, 0, 150), horizontal=True))   # справа темнее — текст читается
    img.alpha_composite(vignette((W, H), 150))
    ax, ay = 50, (H - av) // 2
    put_glow(img, (ax + 10, ay + 18, ax + av - 10, ay + av + 14), (0, 0, 0), radius=24)
    circle = avatar(avatar_bytes, av, name, uid)
    img.alpha_composite(circle, (ax, ay))

    tx, tw = ax + av + 50, W - (ax + av + 50) - 50
    body = " ".join(text.split()) if "\n" not in text else "\n".join(" ".join(ln.split()) for ln in text.split("\n"))
    for size in range(40, 19, -2):
        f = font(size, bold=True, mono=True)
        lines = wrap(body, f, tw)
        line_h = int(size * 1.35)
        if len(lines) * line_h <= H - 190:
            break
    else:
        f = font(20, bold=True, mono=True)
        line_h = 27
        lines = wrap(body, f, tw, max_lines=(H - 190) // line_h)
    af = font(max(22, min(30, int(f.size * 0.75))), bold=True, mono=True)
    author = fit("— " + (name or "аноним"), af, tw)
    block = len(lines) * line_h + 18 + int(af.size * 1.3)
    y = (H - block) // 2
    for ln in lines:
        draw_text(img, (tx, y), ln, f, FG)
        y += line_h
    draw_text(img, (tx, y + 18), author, af, QUOTE_BLUE)
    foot = font(17, mono=True)
    meta = " · ".join(x for x in (f"#{number}" if number is not None else "", date, chat_title) if x)
    meta = fit(meta, foot, W - tx - 40)
    draw_text(img, (W - 40 - text_width(meta, foot), H - 40), meta, foot, (170, 170, 185))
    return jpeg(img)


# ---------- иконки (свои, векторные — вместо эмодзи) ----------

def _ln(d, pts, w, fill):
    """Линия со скруглёнными концами и стыками."""
    d.line(pts, fill=fill, width=w, joint="curve")
    r = w / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def _star(cx, cy, r_out, r_in, points=4, rot=-90):
    out = []
    for i in range(points * 2):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 180 / points)
        out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return out


@lru_cache(maxsize=128)
def icon(name: str, size: int, color: tuple = (235, 235, 240), fill: tuple | None = None) -> Image.Image:
    """Линейная иконка в стиле Lucide: рисуется в 4× и уменьшается — гладкие края. name: image | tag | doc | sparkle |
    chat | crown | swords | dice."""
    N = size * 4
    w = max(int(N * 0.085), 4)
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = tuple(color) + (255,)
    f = tuple(fill) + (255,) if fill else c
    if name == "image":
        d.rounded_rectangle((w, N * 0.16, N - w, N * 0.84), radius=N * 0.12, outline=c, width=w)
        d.ellipse((N * 0.27, N * 0.3, N * 0.43, N * 0.46), outline=c, width=w)
        _ln(d, [(N * 0.14, N * 0.76), (N * 0.4, N * 0.52), (N * 0.6, N * 0.7), (N * 0.72, N * 0.6), (N * 0.86, N * 0.72)], w, c)
    elif name == "tag":
        pts = [(N * 0.12, N * 0.14), (N * 0.52, N * 0.14), (N * 0.88, N * 0.5), (N * 0.5, N * 0.88), (N * 0.12, N * 0.52)]
        d.polygon(pts, outline=c, width=w)
        for x, y in pts:
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=c)
        d.ellipse((N * 0.27, N * 0.29, N * 0.39, N * 0.41), fill=c)
    elif name == "doc":
        pts = [(N * 0.2, N * 0.08), (N * 0.6, N * 0.08), (N * 0.82, N * 0.3), (N * 0.82, N * 0.92), (N * 0.2, N * 0.92)]
        d.polygon(pts, outline=c, width=w)
        _ln(d, [(N * 0.6, N * 0.1), (N * 0.6, N * 0.3), (N * 0.8, N * 0.3)], w, c)
        for y in (0.5, 0.64, 0.78):
            _ln(d, [(N * 0.34, N * y), (N * 0.68, N * y)], w, c)
    elif name == "sparkle":
        d.polygon(_star(N * 0.42, N * 0.56, N * 0.38, N * 0.1), fill=f)
        d.polygon(_star(N * 0.8, N * 0.2, N * 0.16, N * 0.045), fill=f)
        d.polygon(_star(N * 0.82, N * 0.8, N * 0.1, N * 0.03), fill=f)
    elif name == "chat":
        d.rounded_rectangle((w, N * 0.12, N - w, N * 0.7), radius=N * 0.16, outline=c, width=w)
        d.polygon([(N * 0.24, N * 0.66), (N * 0.24, N * 0.92), (N * 0.48, N * 0.7)], fill=c)
        for x in (0.32, 0.5, 0.68):
            d.ellipse((N * x - w * 0.75, N * 0.41 - w * 0.75, N * x + w * 0.75, N * 0.41 + w * 0.75), fill=c)
    elif name == "crown":
        pts = [(N * 0.1, N * 0.74), (N * 0.06, N * 0.3), (N * 0.31, N * 0.5), (N * 0.5, N * 0.14), (N * 0.69, N * 0.5),
               (N * 0.94, N * 0.3), (N * 0.9, N * 0.74)]
        d.polygon(pts, fill=f, outline=c, width=w)
        d.rounded_rectangle((N * 0.1, N * 0.78, N * 0.9, N * 0.92), radius=N * 0.04, fill=f, outline=c, width=max(w // 2, 2))
        for x, y in ((0.06, 0.28), (0.5, 0.12), (0.94, 0.28)):
            d.ellipse((N * x - w, N * y - w, N * x + w, N * y + w), fill=c)
    elif name == "swords":
        for a, b in (((0.12, 0.12), (0.72, 0.72)), ((0.88, 0.12), (0.28, 0.72))):
            _ln(d, [(N * a[0], N * a[1]), (N * b[0], N * b[1])], w, c)
        for a, b in (((0.6, 0.84), (0.84, 0.6)), ((0.4, 0.84), (0.16, 0.6))):
            _ln(d, [(N * a[0], N * a[1]), (N * b[0], N * b[1])], w, c)
        for x, y in ((0.82, 0.82), (0.18, 0.82)):
            d.ellipse((N * x - w * 1.1, N * y - w * 1.1, N * x + w * 1.1, N * y + w * 1.1), fill=c)
    elif name == "at":
        d.ellipse((N * 0.33, N * 0.33, N * 0.67, N * 0.67), outline=c, width=w)
        d.arc((w * 0.6, w * 0.6, N - w * 0.6, N - w * 0.6), start=10, end=320, fill=c, width=w)
        _ln(d, [(N * 0.67, N * 0.34), (N * 0.67, N * 0.56), (N * 0.72, N * 0.64), (N * 0.8, N * 0.66),
                (N * 0.87, N * 0.62), (N * 0.92, N * 0.52), (N * 0.93, N * 0.46)], w, c)
    elif name == "star":
        d.polygon(_star(N * 0.5, N * 0.54, N * 0.46, N * 0.19, points=5), fill=f)
    elif name == "calendar":
        d.rounded_rectangle((w, N * 0.16, N - w, N - w), radius=N * 0.12, outline=c, width=w)
        _ln(d, [(w, N * 0.38), (N - w, N * 0.38)], w, c)
        for x in (0.3, 0.7):
            _ln(d, [(N * x, N * 0.06), (N * x, N * 0.24)], w, c)
        for x, y in ((0.3, 0.56), (0.5, 0.56), (0.7, 0.56), (0.3, 0.74), (0.5, 0.74)):
            d.ellipse((N * x - w * 0.8, N * y - w * 0.8, N * x + w * 0.8, N * y + w * 0.8), fill=c)
    elif name == "gift":
        d.rounded_rectangle((w, N * 0.34, N - w, N * 0.54), radius=N * 0.05, outline=c, width=w)
        d.rounded_rectangle((N * 0.14, N * 0.54, N * 0.86, N - w), radius=N * 0.06, outline=c, width=w)
        _ln(d, [(N * 0.5, N * 0.34), (N * 0.5, N - w)], w, c)
        d.arc((N * 0.2, N * 0.06, N * 0.52, N * 0.38), start=180, end=360, fill=c, width=w)
        d.arc((N * 0.48, N * 0.06, N * 0.8, N * 0.38), start=180, end=360, fill=c, width=w)
        _ln(d, [(N * 0.2, N * 0.22), (N * 0.5, N * 0.34), (N * 0.8, N * 0.22)], w, c)
    elif name == "dice":
        d.rounded_rectangle((w, w, N - w, N - w), radius=N * 0.18, outline=c, width=w)
        for x, y in ((0.32, 0.32), (0.5, 0.5), (0.68, 0.68)):
            d.ellipse((N * x - w, N * y - w, N * x + w, N * y + w), fill=c)
    return img.resize((size, size), Image.LANCZOS)


# ---------- карточка мог-баттла ----------

WIN_C = (34, 197, 94)          # победа — зелёный
WIN_DARK = (21, 128, 61)
WIN_DEEP = (5, 46, 22)
LOSE_C = (239, 68, 68)         # поражение — красный
LOSE_DARK = (153, 27, 27)
LOSE_DEEP = (60, 8, 10)
TIE_C = ((200, 200, 210), (130, 130, 145))
RED = LOSE_C
ICONS = {"avatar": "image", "name": "tag", "username": "at", "premium": "star", "age": "calendar", "gifts": "gift",
         "bio": "doc", "aura": "sparkle", "activity": "chat"}


def normalized_jpeg(data: bytes, size: int = 512) -> bytes:
    """Аватарка для ИИ: квадрат 512×512 JPEG — одинаковый вид для всех, независимо от исходного размера."""
    try:
        img = ImageOps.fit(Image.open(io.BytesIO(data)).convert("RGB"), (size, size), Image.LANCZOS)
    except Exception:
        return data
    return jpeg(img, 88)


def side_by_side(a: bytes | None, b: bytes | None, names: tuple[str, str], uids: tuple[int, int], size: int = 256) -> bytes:
    """Две аватарки рядом (A слева, B справа) — одна картинка для ИИ."""
    img = Image.new("RGB", (size * 2 + 16, size), (0, 0, 0))
    for i, (data, name, uid) in enumerate(zip((a, b), names, uids)):
        av = avatar(data, size, name, uid)
        img.paste(av, (i * (size + 16), 0), av)
    return jpeg(img, 85)


def _mogged(av: Image.Image) -> Image.Image:
    """Проигравший: обесцвеченная аватарка с красным оттенком, красный крест и штамп MOGGED."""
    size = av.width
    alpha = av.split()[-1]
    grey = ImageOps.grayscale(av.convert("RGB")).point(lambda v: int(v * 0.5))
    tinted = ImageOps.colorize(grey, black=(18, 4, 6), white=(150, 90, 95))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(tinted, (0, 0), alpha)
    d = ImageDraw.Draw(out)
    w = max(size // 16, 6)
    m = size * 0.17
    for line in ((m, m, size - m, size - m), (size - m, m, m, size - m)):
        d.line(line, fill=(0, 0, 0, 170), width=w + 6)
        d.line(line, fill=LOSE_C + (245,), width=w)
    stamp = rotated_text("MOGGED", font(int(size * 0.19), bold=True), LOSE_C + (255,), 16, stroke=max(size // 55, 3))
    out.alpha_composite(stamp, ((size - stamp.width) // 2, (size - stamp.height) // 2))
    return out


def _pill(img: Image.Image, center_x: int, y: int, text: str, bg, fg, f, ico: str | None = None) -> None:
    isz = int(f.size * 1.05) if ico else 0
    w = int(f.getlength(text)) + 40 + (isz + 10 if ico else 0)
    h = int(f.size * 1.6)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((center_x - w // 2, y, center_x + w // 2, y + h), radius=h // 2, fill=bg)
    img.alpha_composite(layer)
    x = center_x - w // 2 + 20
    if ico:
        img.alpha_composite(icon(ico, isz, fg, fg), (int(x), int(y + (h - isz) / 2)))
        x += isz + 10
    ImageDraw.Draw(img).text((x, y + (h - f.size) / 2 - 2), text, font=f, fill=fg)


def _bar(img: Image.Image, x0: int, x1: int, y: int, h: int, value: int, to_left: bool, colors) -> None:
    """Шкала 0..10: дорожка и заливка (у левого игрока растёт к центру справа налево — зеркально)."""
    track = Image.new("RGBA", (x1 - x0 + 1, h + 1), (0, 0, 0, 0))     # полупрозрачное — отдельным слоем, иначе выйдет белым
    ImageDraw.Draw(track).rounded_rectangle((0, 0, x1 - x0, h), radius=h // 2, fill=(255, 255, 255, 26))
    img.alpha_composite(track, (x0, y))
    fill_w = int((x1 - x0) * max(0, min(value, 10)) / 10)
    if fill_w < h:
        return
    bx0, bx1 = (x1 - fill_w, x1) if to_left else (x0, x0 + fill_w)
    grad = gradient((bx1 - bx0, h), colors[1] if to_left else colors[0], colors[0] if to_left else colors[1], horizontal=True)
    mask = Image.new("L", (bx1 - bx0, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, bx1 - bx0 - 1, h - 1), radius=h // 2, fill=255)
    img.paste(grad, (bx0, y), mask)


def _side_tint(size: tuple[int, int], left, right) -> Image.Image:
    """Цветная дымка: слева своим цветом, справа своим, в середине прозрачно."""
    small = Image.new("RGBA", (3, 1))
    small.putdata([left, (0, 0, 0, 0), right])
    return small.resize(size, Image.BILINEAR)


def mog_card(players: list[dict], scores: list[dict], criteria: list[tuple[str, str]], win: int, verdict: str,
             by_ai: bool) -> bytes:
    """players: [{name, username, uid, avatar}]; scores: [{критерий: 0..10}] для A и B; win — индекс победителя.
    Цвета: победа — тёмно-зелёный, поражение — красный; иконки свои, векторные."""
    W, av_size = 1200, 320
    vf = font(30)
    vlines = wrap(f"«{verdict}»", vf, W - 300, max_lines=3) if verdict else []
    row_h = 70
    stats_top = 756
    stats_h = 40 + len(criteria) * row_h + 130
    H = stats_top + stats_h + (60 + len(vlines) * 42 + 30 if vlines else 0) + 90
    half = W // 2
    layers = []
    for i, p in enumerate(players):                       # фон: слева размытая аватарка A, справа — B (проигравший — серый)
        bg = blurred_bg(p.get("avatar"), (W, H), p["uid"], brightness=0.4 if i == win else 0.24)
        if i != win:
            bg = ImageOps.grayscale(bg.convert("RGB")).convert("RGBA")
        layers.append(bg)
    ramp = gradient((W // 3, 1), (0, 0, 0, 0), (0, 0, 0, 255), horizontal=True).split()[-1]
    mask = Image.new("L", (W, 1), 0)
    mask.paste(ramp, (W // 3, 0))
    mask.paste(255, (2 * W // 3, 0, W, 1))
    img = Image.composite(layers[1], layers[0], mask.resize((W, H)))   # плавный переход в середине, без шва
    tint = (WIN_DARK + (90,), LOSE_DARK + (80,))
    img.alpha_composite(_side_tint((W, H), tint[0] if win == 0 else tint[1], tint[0] if win == 1 else tint[1]))
    img.alpha_composite(gradient((W, H), (0, 0, 0, 50), (0, 0, 0, 210)))
    img.alpha_composite(vignette((W, H), 190))

    title = font(66, bold=True)
    t = "MOG BATTLE"
    tx = (W - title.getlength(t)) / 2
    shadow_text(img, (tx, 40), t, title, (255, 255, 255), shadow=WIN_C, blur=16)
    sw = icon("swords", 56, (235, 235, 240))
    img.alpha_composite(sw, (int(tx - 80), 50))
    img.alpha_composite(sw, (int(tx + title.getlength(t) + 24), 50))

    centers = (W // 4 + 10, W * 3 // 4 - 10)
    top = 215
    for i, (p, cx) in enumerate(zip(players, centers)):
        av = avatar(p.get("avatar"), av_size, p["name"], p["uid"])
        x0 = cx - av_size // 2
        if i == win:
            put_glow(img, (x0 - 20, top - 20, x0 + av_size + 20, top + av_size + 20), WIN_C, radius=32)
            ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(ring).ellipse((x0 - 11, top - 11, x0 + av_size + 11, top + av_size + 11), outline=WIN_C + (255,), width=9)
            img.alpha_composite(ring)
            img.alpha_composite(av, (x0, top))
            crown = icon("crown", 96, (255, 255, 255), WIN_C).rotate(-20, expand=True, resample=Image.BICUBIC)
            shadow = Image.new("RGBA", crown.size, (0, 0, 0, 0))
            shadow.putalpha(crown.split()[-1].point(lambda v: int(v * 0.7)))
            cx0, cy0 = x0 + av_size - crown.width // 2 - 26, top - crown.height // 2 + 6
            img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6)), (cx0 + 3, cy0 + 6))
            img.alpha_composite(crown, (cx0, cy0))
        else:
            put_glow(img, (x0 - 6, top - 6, x0 + av_size + 6, top + av_size + 6), LOSE_DARK, radius=26)
            img.alpha_composite(_mogged(av), (x0, top))
        nf = font(40, bold=True)
        name = fit(p["name"], nf, 500)
        draw_text(img, (cx - text_width(name, nf) // 2, top + av_size + 28), name, nf, FG if i == win else (180, 170, 172))
        uy = top + av_size + 82
        uf = font(24)
        meta = " · ".join(x for x in (("@" + p["username"]) if p.get("username") else "без юзернейма",
                                       p.get("since") or "") if x)
        meta = fit(meta, uf, 540)
        mw = text_width(meta, uf) + (34 if p.get("premium") else 0)
        mx = cx - mw // 2
        if p.get("premium"):
            img.alpha_composite(icon("star", 26, (168, 85, 247), (168, 85, 247)), (int(mx), uy + 2))   # Premium — фиолетовая звезда
            mx += 34
        draw_text(img, (mx, uy), meta, uf, (165, 165, 180))
        g_reg, g_uni, g_nft = p.get("gifts_regular", 0), p.get("gifts_unique", 0), p.get("nft_usernames", 0)
        if g_reg or g_uni or g_nft:                                   # строка про подарки и NFT
            parts = [f"подарков {g_reg + g_uni}"] + ([f"NFT {g_uni + g_nft}"] if g_uni or g_nft else [])
            gtxt = " · ".join(parts)
            gw = text_width(gtxt, uf) + 34
            gx = cx - gw // 2
            img.alpha_composite(icon("gift", 26, (200, 205, 215)), (int(gx), uy + 36))
            draw_text(img, (gx + 34, uy + 34), gtxt, uf, (200, 205, 215))
        pf = font(24, bold=True)
        if i == win:
            _pill(img, cx, uy + 78, "MOGGER", WIN_DARK + (255,), (255, 255, 255), pf, "crown")
        else:
            _pill(img, cx, uy + 78, "MOGGED", LOSE_DARK + (255,), (255, 255, 255), pf)
    vy = top + av_size // 2 - 64
    badge = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(badge).ellipse((half - 64, vy, half + 64, vy + 128), fill=(12, 12, 16, 240), outline=(255, 255, 255, 70), width=4)
    img.alpha_composite(badge)
    vs = font(50, bold=True)
    ImageDraw.Draw(img).text((half - vs.getlength("VS") / 2, vy + 34), "VS", font=vs, fill=(255, 255, 255))

    panel(img, (50, stats_top, W - 50, stats_top + stats_h))
    d = ImageDraw.Draw(img)
    lf, sf = font(26, bold=True), font(34, bold=True)
    y = stats_top + 34
    track_l = (150, half - 160)
    track_r = (half + 160, W - 150)
    for key, label in criteria:
        a, b = scores[0][key], scores[1][key]
        ico = icon(ICONS[key], 34, (200, 205, 215)) if key in ICONS else None
        lw = lf.getlength(label) + (42 if ico is not None else 0)
        lx = half - lw / 2
        if ico is not None:
            img.alpha_composite(ico, (int(lx), y + 5))
            lx += 42
        d.text((lx, y + 6), label, font=lf, fill=(205, 205, 218))
        for side, (v, other) in enumerate(((a, b), (b, a))):
            colors = (WIN_DARK, WIN_C) if v > other else TIE_C if v == other else (LOSE_DARK, LOSE_C)
            x0, x1 = track_l if side == 0 else track_r
            _bar(img, x0, x1, y + 12, 22, v, side == 0, (colors[1], colors[0]))
            s = str(v)
            nx = (x0 - 22 - sf.getlength(s)) if side == 0 else (x1 + 22)
            d.text((nx, y + 2), s, font=sf, fill=WIN_C if v > other else (FG if v == other else LOSE_C))
        y += row_h
    sep = Image.new("RGBA", (W - 180, 2), (255, 255, 255, 40))
    img.alpha_composite(sep, (90, y + 4))
    tf = font(72, bold=True)
    ta, tb = sum(scores[0][k] for k, _ in criteria), sum(scores[1][k] for k, _ in criteria)
    for i, (v, cx) in enumerate(((ta, centers[0]), (tb, centers[1]))):
        s = str(v)
        if i == win:
            shadow_text(img, (cx - tf.getlength(s) / 2, y + 22), s, tf, WIN_C, shadow=WIN_DARK, blur=14, spread=2)
        else:
            shadow_text(img, (cx - tf.getlength(s) / 2, y + 22), s, tf, LOSE_C, shadow=LOSE_DEEP, blur=10)
    _pill(img, half, y + 46, "ИТОГ", (255, 255, 255, 235), (12, 12, 16), font(26, bold=True))
    y = stats_top + stats_h + 30
    if vlines:
        vh = len(vlines) * 42 + 40
        panel(img, (110, y, W - 110, y + vh), radius=24, alpha=120)
        y += 20
        for ln in vlines:
            draw_text(img, ((W - text_width(ln, vf)) // 2, y), ln, vf, FG)
            y += 42
    foot = font(22)
    note = ("оценка ИИ по шкале" if by_ai else "оценка по правилам (ИИ недоступен)") + " · Nori"
    ico = icon("sparkle" if by_ai else "dice", 24, (160, 160, 175))
    nw = foot.getlength(note) + 34
    nx = (W - nw) / 2
    img.alpha_composite(ico, (int(nx), H - 52))
    ImageDraw.Draw(img).text((nx + 34, H - 52), note, font=foot, fill=(160, 160, 175))
    return jpeg(img)
