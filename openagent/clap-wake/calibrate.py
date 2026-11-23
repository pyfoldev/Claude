"""Калибровка на ESC-50 (CC BY-NC 3.0): YAMNet-оценки для «двойного хлопка» против стуков/щелчков/аплодисментов/речи.
python calibrate.py <yamnet.tflite> <class_map.csv> <папка с 16к wav ESC-50> <esc_sel.json>"""
import sys, json, glob, csv, random, numpy as np, soundfile as sf
from ai_edge_litert.interpreter import Interpreter
import detector as D
tfl, cmap, wdir, sel = sys.argv[1:5]
it = Interpreter(tfl); it.allocate_tensors(); ii, oi = it.get_input_details()[0]['index'], it.get_output_details()[0]['index']
names = [r[2] for r in list(csv.reader(open(cmap)))[1:]]
IDX = {n: i for i, n in enumerate(names)}
def yam(w):
    it.set_tensor(ii, w.reshape(15600)); it.invoke(); return it.get_tensor(oi).reshape(-1)
SEL = json.load(open(sel)); R = random.Random(5)
def load(f):
    w, sr = sf.read(f"{wdir}/{f}"); return (w if w.ndim == 1 else w.mean(1)).astype(np.float32)
def segments(cat, n=60, pre=40, post=170):
    """Одиночные удары из клипов категории: сегменты вокруг начала события, пик нормирован."""
    out = []
    for f in SEL[cat]:
        try: x = load(f)
        except Exception: continue
        ev = D.events(x)
        for k, t in enumerate(ev):
            nxt = ev[k + 1] if k + 1 < len(ev) else 1e9
            if nxt - t < 220: continue                                      # рядом другой удар — сегмент «грязный»
            s = max(0, int((t - pre) * 16)); seg = x[s: s + int((pre + post) * 16)].copy()
            if len(seg) < 16 * (pre + post) // 2 or np.abs(seg).max() < 0.02: continue
            seg *= np.hanning(len(seg)) ** 0.3; out.append(seg / np.abs(seg).max())
            if len(out) >= n: return out
    return out
def noise(sec=4.0, db=-52):
    n = R.gauss; x = np.array([n(0, 1) for _ in range(int(sec * 16000))], np.float32)
    x = np.convolve(x, np.ones(6) / 6, 'same'); return x / np.abs(x).max() * 10 ** (db / 20) * 3
def compose(segs, gaps, level):
    x = noise(); t = 1200
    for k, s in enumerate(segs):
        a = int(t * 16); x[a: a + len(s)] += s[: len(x) - a] * level; t += gaps[k] if k < len(gaps) else 0
    return x
def run(x):
    """Потоковая имитация: события → пара → YAMNet → (сработало?, оценки)"""
    ev = D.events(x); pair = D.find_pair(ev, len(x) / 16 + 5000)
    if not pair: return None, {'events': len(ev)}
    s = yam(D.window(x, pair[0])); return pair, {'events': len(ev), 'clap': float(s[IDX['Clapping']]), 'hands': float(s[IDX['Hands']]), 'snap': float(s[IDX['Finger snapping']]), 'appl': float(s[IDX['Applause']]), 'speech': float(s[IDX['Speech']]), 'top': names[int(np.argmax(s))], 'topv': float(s.max())}

pos = segments('clapping', 70); print('одиночных хлопков найдено:', len(pos))
cats = {c: segments(c, 40) for c in ['door_wood_knock', 'mouse_click', 'keyboard_typing', 'footsteps', 'can_opening', 'glass_breaking', 'coughing', 'laughing']}
print({c: len(v) for c, v in cats.items()})
def trials(name, mk, n=50):
    res = [run(mk()) for _ in range(n)]; det = [r for p, r in res if p]
    print(f"\n== {name}: пара найдена в {len(det)}/{n}")
    if det:
        for key in ('clap', 'hands', 'snap', 'appl', 'speech'): v = np.array([d[key] for d in det]); print(f"   {key:7s} мин {v.min():.2f} медиана {np.median(v):.2f} макс {v.max():.2f}")
        from collections import Counter; print('   топ-класс:', Counter(d['top'] for d in det).most_common(4))
    return det
P = trials('ДВОЙНОЙ ХЛОПОК (цель)', lambda: compose([R.choice(pos), R.choice(pos)], [R.randint(220, 600)], R.uniform(0.3, 0.9)))
for c, segs in cats.items():
    if len(segs) >= 4: trials(f'два удара «{c}»', lambda: compose([R.choice(segs), R.choice(segs)], [R.randint(220, 600)], R.uniform(0.3, 0.9)))
trials('ТРИ хлопка', lambda: compose([R.choice(pos) for _ in range(3)], [R.randint(220, 450)] * 2, 0.6), 30)
trials('ОДИН хлопок', lambda: compose([R.choice(pos)], [], 0.6), 30)
# аплодисменты: реальные клипы целиком
print('\n== АПЛОДИСМЕНТЫ (реальные клипы ESC-50 clapping, 5 с): ложные срабатывания пары')
fp = 0
for f in SEL['clapping']:
    try: x = load(f)
    except Exception: continue
    x = np.concatenate([noise(1.5), x * 0.8, noise(1.5)])
    p, r = run(x); fp += bool(p)
print(f'   пар найдено в {fp}/{len(SEL["clapping"])} клипов')
json.dump({'pos': [d for d in P]}, open('/tmp/claude-0/yam/pos_scores.json', 'w'))
