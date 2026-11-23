"""Русские числа, склонения и разговорные формы времени/длительности для генератора датасета."""
import random

R = random.Random(7)
ONES = ["ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять", "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
        "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
TENS = {20: "двадцать", 30: "тридцать", 40: "сорок", 50: "пятьдесят", 60: "шестьдесят", 70: "семьдесят", 80: "восемьдесят", 90: "девяносто"}
FEM = {1: "одна", 2: "две"}
ORD_GEN = {1: "первого", 2: "второго", 3: "третьего", 4: "четвёртого", 5: "пятого", 6: "шестого", 7: "седьмого", 8: "восьмого", 9: "девятого", 10: "десятого", 11: "одиннадцатого", 12: "двенадцатого"}


def num(n, fem=False):
    if n == 100:
        return "сто"
    if n < 20:
        return FEM[n] if fem and n in FEM else ONES[n]
    t, o = n // 10 * 10, n % 10
    return TENS[t] + (" " + (FEM[o] if fem and o in FEM else ONES[o]) if o else "")


def plural(n, one, few, many):
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    return one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


def minutes_w(n):
    return plural(n, "минуту", "минуты", "минут")


def minutes_n(n):  # именительный: «одна минута»
    return plural(n, "минута", "минуты", "минут")


def hours_w(n):
    return plural(n, "час", "часа", "часов")


def secs_w(n):
    return plural(n, "секунду", "секунды", "секунд")


def maybe_words(n, p=0.3, fem=False):
    return num(n, fem) if R.random() < p else str(n)


# ---------- время суток для будильника ----------
def period(h):
    if h == 0:
        return "ночи"
    if h <= 3:
        return "ночи"
    if h <= 11:
        return "утра"
    if h <= 17:
        return "дня"
    return "вечера"


def alarm_forms(h, m):
    """Разговорные варианты времени, однозначно означающие h:m (после предлога «на»/«в»)."""
    h12 = h % 12 or 12
    per = period(h)
    f = []
    am_default = (4 <= h <= 11) or h == 12   # без слова-периода — только утро и полдень
    two = f"{h:02d}:{m:02d}"
    f += [f"{h}:{m:02d}", two, f"{h}.{m:02d}"] if R.random() < 0.5 else [f"{h}:{m:02d}"]
    if m == 0:
        f += [f"{h12} {per}", f"{num(h12)} {per}", f"{h12} часов {per}", f"{num(h12)} часов {per}", f"{h}:00", f"ровно {h12} {per}"]
        if am_default:
            f += [f"{num(h12)}", f"{h12} часов", f"{num(h12)} часов", f"{h12}", f"ровно {num(h12)}"]
        if h == 12:
            f += ["полдень", "12 дня"]
        if h == 0:
            f += ["полночь", "12 ночи"]
        if h > 12:
            f += [f"{num(h)} ноль ноль", f"{h} часов"]
    else:
        f += [f"{h12} {m:02d} {per}", f"{num(h12)} {num(m)} {per}"]
        if am_default:
            f += [f"{num(h12)} {num(m)}", f"{h12} {m:02d}", f"{h12}:{m:02d}"] + ([f"{num(h12)} ноль {num(m)}"] if m < 10 else [])
        nxt = h12 % 12 + 1
        if m == 30:
            if am_default:
                f += [f"половину {ORD_GEN[nxt]}", f"половине {ORD_GEN[nxt]}", f"пол {ORD_GEN[nxt]}"]
            f += [f"половину {ORD_GEN[nxt]} {per}"]
        elif m == 15:
            f += [f"четверть {ORD_GEN[nxt]} {per}", f"пятнадцать минут {ORD_GEN[nxt]} {per}"]
            if am_default:
                f += [f"четверть {ORD_GEN[nxt]}", f"пятнадцать минут {ORD_GEN[nxt]}"]
        elif m == 45:
            f += [f"без пятнадцати {num(nxt)} {per}", f"без четверти {num(nxt)} {per}"]
            if am_default or h == 11:
                f += [f"без четверти {num(nxt)}", f"без пятнадцати {num(nxt)}"]
        elif m in (40, 50, 55):
            w = {40: "без двадцати", 50: "без десяти", 55: "без пяти"}[m]
            f += [f"{w} {num(nxt)} {per}"] + ([f"{w} {num(nxt)}"] if am_default else [])
        elif m in (5, 10, 20, 25):
            f += [f"{num(m)} минут {ORD_GEN[nxt]} {per}"] if m not in (5,) else [f"пять минут {ORD_GEN[nxt]} {per}"]
        if h > 12:
            f += [f"{num(h)} {num(m)}", f"{h} {m:02d}"]
    return f


# ---------- длительности для таймера / напоминания ----------
def duration_forms(sec):
    """Фразы, означающие ровно sec секунд (sec кратно 5)."""
    f = []
    h, rest = divmod(sec, 3600)
    mi, s = divmod(rest, 60)
    if sec % 60 == 0 and sec < 3600:
        n = sec // 60
        f += [f"{n} {minutes_w(n)}", f"{num(n, fem=True)} {minutes_w(n)}", f"{n} мин", f"{n}м"] if n > 1 else ["минуту", "1 минуту", "одну минуту", "1 мин"]
        if n == 30:
            f += ["полчаса", "пол часа", "половину часа", "0.5 часа"]
        if n == 15:
            f += ["четверть часа", "пятнадцать минут"]
        if n == 45:
            f += ["три четверти часа", "сорок пять минут"]
    elif sec >= 3600 and sec % 3600 == 0:
        n = sec // 3600
        f += ["час", "1 час", "один час"] if n == 1 else [f"{n} {hours_w(n)}", f"{num(n)} {hours_w(n)}"]
    elif sec == 5400:
        f += ["полтора часа", "1.5 часа", "1 час 30 минут", "час тридцать минут", "час и тридцать минут", "90 минут", "девяносто минут", "час тридцать"]
    elif sec == 9000:
        f += ["два с половиной часа", "2.5 часа", "2 часа 30 минут", "150 минут"]
    elif sec >= 3600:
        hh = h
        hs = ("час" if hh == 1 else f"{hh} {hours_w(hh)}" if R.random() < 0.6 else f"{num(hh)} {hours_w(hh)}")
        f += [f"{hs} {mi} {minutes_w(mi)}" if mi else hs]
        if mi:
            f += [f"{hh} {hours_w(hh)} и {mi} {minutes_w(mi)}"]
    elif sec < 60:
        f += [f"{sec} {secs_w(sec)}", f"{num(sec, fem=True)} {secs_w(sec)}", f"{sec} сек"]
        if sec == 30:
            f += ["полминуты", "пол минуты"]
    else:
        if s == 0:
            pass
        else:
            f += [f"{mi} {minutes_w(mi)} {s} {secs_w(s)}", f"{'одну' if mi == 1 else num(mi, True)} {minutes_w(mi)} {num(s, True)} {secs_w(s)}", f"{sec} секунд"]
            if sec == 90:
                f += ["полторы минуты", "1.5 минуты", "минуту тридцать секунд", "минуту и тридцать секунд"]
    return f or [f"{sec} секунд"]


def clean_pick(lst):
    return R.choice(lst)
