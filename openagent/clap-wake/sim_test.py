"""Проверка детектора на реалистичных синтетических хлопках (шумовой всплеск с быстрым затуханием + «хвост» комнаты) на фоне тихого шума."""
import numpy as np, sys, importlib
SR = 16000
R = np.random.default_rng(3)
def clap(peak=0.5, tau=0.025, tail=0.13, tail_db=-24):
    n = int(0.45 * SR); t = np.arange(n) / SR
    body = R.standard_normal(n) * np.exp(-t / tau); room = R.standard_normal(n) * np.exp(-t / tail) * 10 ** (tail_db / 20)
    x = body + room; x[:int(0.002 * SR)] *= np.linspace(0.2, 1, int(0.002 * SR))
    return (x / np.abs(x).max() * peak).astype(np.float32)
def scene(starts_ms, peak=0.5, bg_db=-52, secs=5.0, speech=False):
    x = (R.standard_normal(int(secs * SR)) * 10 ** (bg_db / 20) * 0.7).astype(np.float32)
    for s in starts_ms:
        c = clap(peak * R.uniform(0.6, 1.0)); a = int(s * SR / 1000); x[a:a + len(c)] += c[: len(x) - a]
    return x
def rate(D, name, make, n=100, want=True):
    hit = 0
    for _ in range(n):
        x = make(); ev = D.events(x); p = D.find_pair(ev, len(x) / 16 + 3000); hit += bool(p)
    print(f"  {name:38s} пара найдена: {hit}/{n}"); return hit
mod = sys.argv[1] if len(sys.argv) > 1 else 'detector'
D = importlib.import_module(mod)
print('детектор:', mod)
rate(D, 'ДВА хлопка (цель), тихая комната', lambda: scene([1500, 1500 + int(R.integers(220, 600))]), want=True)
rate(D, 'ДВА хлопка, шумно (-38 дБ)', lambda: scene([1500, 1500 + int(R.integers(220, 600))], bg_db=-38))
rate(D, 'ДВА тихих хлопка (пик 0.15)', lambda: scene([1500, 1500 + int(R.integers(220, 600))], peak=0.15))
rate(D, 'один хлопок (не должен)', lambda: scene([1500]))
rate(D, 'три хлопка (не должен)', lambda: scene([1500, 1900, 2300]))
rate(D, 'аплодисменты 8 хлопков (не должен)', lambda: scene([1200 + 260 * k + int(R.integers(-60, 60)) for k in range(8)]))
rate(D, 'два хлопка + третий вдали (не должен)', lambda: scene([1500, 1900, 2400]))
