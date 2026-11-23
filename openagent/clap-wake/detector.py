"""Эталонная реализация детектора «двойной хлопок» (то же, что в Android-сервисе ClapService.kt) — для калибровки на данных.
Идея в два этапа: (1) дешёвый детектор коротких резких звуков по огибающей громкости работает всегда; (2) только когда найдена ровно пара
ударов в нужном интервале и вокруг тишина — окно звука проверяет YAMNet (хлопок ли это, а не стук, щелчок мыши, речь или аплодисменты)."""
import numpy as np

SR = 16000
FRAME = 160                      # 10 мс
ONSET_DB = 17.0                  # пик над шумовым полом
RISE_DB = 11.0                   # нарастание за 30 мс
MAX_EVENT_MS = 170               # хлопок короткий; речь/музыка длиннее
REFRACT_MS = 80
GAP_MIN_MS, GAP_MAX_MS = 170, 650   # расстояние между началами двух хлопков
QUIET_BEFORE_MS = 900            # до первого хлопка событий не было
QUIET_AFTER_MS = 750             # после второго — тоже (иначе это аплодисменты / серия)


def frame_db(x):
    n = len(x) // FRAME
    f = x[: n * FRAME].reshape(n, FRAME).astype(np.float32)
    return 20 * np.log10(np.sqrt((f ** 2).mean(1)) + 1e-5)


def events(x):
    """Резкие короткие звуки → список времён начала (мс)."""
    db = frame_db(x); floor = db[:20].mean() if len(db) > 20 else -60.0; out = []; last = -1e9; i = 3
    while i < len(db):
        floor = min(floor + 0.002, db[i]) if db[i] < floor + 6 else floor + 0.002   # медленно ползущий шумовой пол
        if db[i] - floor > ONSET_DB and db[i] - db[i - 3] > RISE_DB and i * 10 - last > REFRACT_MS:
            j = i
            while j < len(db) and db[j] - floor > 8 and (j - i) * 10 <= 400: j += 1
            dur = (j - i) * 10
            if dur <= MAX_EVENT_MS: out.append(i * 10); last = i * 10 + dur
            else: last = i * 10 + dur       # длинный звук (речь, музыка) — не хлопок, но и подряд не считаем
            i = j; continue
        i += 1
    return out


def find_pair(ev, now_ms):
    """Есть ли «пара» к моменту now_ms (с учётом ожидания тишины после второго)? → (t1, t2) или None."""
    for k in range(len(ev) - 1):
        t1, t2 = ev[k], ev[k + 1]
        if not (GAP_MIN_MS <= t2 - t1 <= GAP_MAX_MS): continue
        if any(t1 - QUIET_BEFORE_MS <= e < t1 for e in ev): continue                   # перед первым не было других ударов
        if any(t2 < e <= t2 + QUIET_AFTER_MS for e in ev): continue                    # после второго нет третьего
        if now_ms >= t2 + QUIET_AFTER_MS: return t1, t2
    return None


def window(x, t1_ms):
    s = max(0, int((t1_ms - 120) * SR / 1000)); w = x[s: s + 15600]
    return np.pad(w, (0, 15600 - len(w))).astype(np.float32)
