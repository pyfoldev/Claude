"""Детектор «двойной хлопок», версия 2 (зеркало ClapDetector.kt). Отличия от v1:
— конец удара ищется от ПИКА (громкость упала на 25 дБ от пика), а не от шумового пола: в тихой комнате «хвост» эха держится дольше 170 мс над полом, и настоящие хлопки отбрасывались;
— длинные звуки (речь, музыка, >250 мс) не выбрасываются молча, а считаются помехой: пара не засчитывается, если рядом было что-то ещё."""
import numpy as np
SR = 16000; FRAME = 160
ONSET_DB = 17.0; RISE_DB = 11.0; MAX_CLAP_MS = 250; REFRACT_MS = 80
GAP_MIN_MS, GAP_MAX_MS = 170, 650; QUIET_BEFORE_MS = 900; QUIET_AFTER_MS = 750; DROP_DB = 25.0

def frame_db(x):
    n = len(x) // FRAME; f = x[: n * FRAME].reshape(n, FRAME).astype(np.float32)
    return 20 * np.log10(np.sqrt((f ** 2).mean(1)) + 1e-5)

def events(x):
    """→ список (начало_мс, это_хлопок)"""
    db = frame_db(x); floor = db[:20].mean(); out = []; last = -1e9; i = 3
    while i < len(db):
        if db[i] - floor > ONSET_DB and db[i] - db[i - 3] > RISE_DB and i * 10 - last > REFRACT_MS:
            peak = db[i]; j = i
            while j < len(db) and (j - i) * 10 <= 600:
                peak = max(peak, db[j])
                if db[j] < max(floor + 6, peak - DROP_DB) and j > i: break
                j += 1
            dur = (j - i) * 10
            out.append((i * 10, dur <= MAX_CLAP_MS)); last = i * 10 + dur; i = j; continue
        floor = min(floor + 0.002, db[i]) if db[i] < floor + 6 else floor + 0.002
        i += 1
    return out

def find_pair(ev, now_ms):
    for k in range(len(ev) - 1):
        (t1, c1), (t2, c2) = ev[k], ev[k + 1]
        if not (c1 and c2) or not (GAP_MIN_MS <= t2 - t1 <= GAP_MAX_MS): continue
        if any(t1 - QUIET_BEFORE_MS <= t < t1 for t, _ in ev): continue
        if any(t2 < t <= t2 + QUIET_AFTER_MS for t, _ in ev): continue
        if now_ms >= t2 + QUIET_AFTER_MS: return t1, t2
    return None

def window(x, t1_ms):
    s = max(0, int((t1_ms - 120) * SR / 1000)); w = x[s: s + 15600]
    return np.pad(w, (0, 15600 - len(w))).astype(np.float32)
