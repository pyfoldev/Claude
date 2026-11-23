#!/usr/bin/env python3
"""Синтез всех звуковых эффектов, амбиентов и музыки (numpy + ffmpeg). Без внешних лицензий.
Запуск: python3 tools/gen_audio.py  ->  audio/sfx/*.ogg, audio/music/*.ogg"""
import numpy as np, subprocess, os, wave, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SR = 44100
rng = np.random.default_rng(7)
def t(d): return np.arange(int(SR * d)) / SR
def noise(d): return rng.standard_normal(int(SR * d))
def sine(f, d, ph=0): return np.sin(2 * np.pi * f * t(d) + ph)
def sweep(f0, f1, d):
    tt = t(d); f = f0 + (f1 - f0) * tt / d
    return np.sin(2 * np.pi * np.cumsum(f) / SR)
def saw(f, d):
    return 2 * ((f * t(d)) % 1.0) - 1
def env(n, a, r, power=1.0):
    e = np.ones(n); na = max(1, int(SR * a)); nr = max(1, int(SR * r))
    e[:na] = np.linspace(0, 1, na) ** power; e[-nr:] = np.minimum(e[-nr:], np.linspace(1, 0, nr) ** power); return e
def decay(d, k=6.0): return np.exp(-k * t(d) / d)
def norm(x, peak=0.9): return x / (np.max(np.abs(x)) + 1e-9) * peak
def lp(x, fc):
    n = len(x); X = np.fft.rfft(x); f = np.fft.rfftfreq(n, 1 / SR); X *= 1 / (1 + (f / fc) ** 4); return np.fft.irfft(X, n)
def hp(x, fc):
    return x - lp(x, fc)
def bp(x, f0, f1): return lp(hp(x, f0), f1)
def loopify(x, fade=1.0):
    nf = int(SR * fade); y = x.copy()
    w = np.linspace(0, 1, nf)
    y[:nf] = x[:nf] * w + x[-nf:] * (1 - w)
    return y[:-nf]
def mix(*xs):
    n = max(len(x) for x in xs); y = np.zeros(n)
    for x in xs: y[:len(x)] += x
    return y
def at(x, start, d): 
    y = np.zeros(int(SR * d)); s = int(SR * start); y[s:s + len(x)] += x[:max(0, len(y) - s)]; return y
def save(name, x, folder="sfx", af=None, sr=SR, q=3):
    x = np.clip(x, -1, 1)
    d = f"{ROOT}/audio/{folder}"; os.makedirs(d, exist_ok=True)
    wav = f"/tmp/gen_{name}.wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((x * 32767).astype(np.int16).tobytes())
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", wav]
    if af: cmd += ["-af", af]
    cmd += ["-ar", str(sr), "-ac", "1", "-c:a", "libvorbis", "-q:a", str(q), f"{d}/{name}.ogg"]
    subprocess.run(cmd, check=True); os.remove(wav)
    print("ok", folder, name)

# ---------- шаги ----------
for i in range(1, 5):
    d = 0.16; x = lp(noise(d), 380 + 80 * i) * decay(d, 9) + sine(70 + 8 * i, d) * decay(d, 14) * 0.6
    save(f"step{i}", norm(x, 0.7))
save("click", norm(hp(noise(0.03), 2000) * decay(0.03, 8), 0.6))
save("tool_switch", norm(lp(noise(0.12), 900) * decay(0.12, 7) + sine(180, 0.12) * decay(0.12, 10) * .4, 0.5))
# ---------- двери ----------
d = 1.3; cr = (sweep(110, 260, d) * (0.5 + 0.5 * np.sin(2 * np.pi * 14 * t(d))) + 0.4 * lp(noise(d), 600)) * env(int(SR * d), 0.1, 0.4)
save("door_open", norm(cr, 0.6), af="lowpass=f=2500")
save("door_close", norm(lp(noise(0.25), 500) * decay(0.25, 8) + sine(65, 0.25) * decay(0.25, 10), 0.8))
save("door_slam", norm(mix(lp(noise(0.6), 400) * decay(0.6, 6), sine(55, 0.6) * decay(0.6, 5), at(hp(noise(0.1), 1500) * decay(0.1, 8), 0, 0.6) * .6), 0.95), af="aecho=0.8:0.6:90:0.3")
dl = 0.5; save("door_locked", norm(mix(at(lp(noise(0.08), 900) * decay(0.08, 8) + sine(220, 0.08) * decay(0.08, 10), 0, dl), at(lp(noise(0.08), 900) * decay(0.08, 8) + sine(180, 0.08) * decay(0.08, 10), 0.18, dl)), 0.7))
save("key_unlock", norm(mix(at(hp(noise(0.04), 3000) * decay(0.04, 8) + sine(1800, 0.04) * decay(0.04, 10) * .5, 0, 0.5), at(hp(noise(0.05), 2500) * decay(0.05, 8) + sine(1300, 0.05) * decay(0.05, 8) * .5, 0.15, 0.5)), 0.7))
# ---------- интерфейс ----------
save("paper", norm(bp(noise(0.35), 1500, 7000) * env(int(SR * 0.35), 0.05, 0.2), 0.5))
save("note_true", norm(mix(sine(110, 2.5) * decay(2.5, 3), sine(165, 2.5) * decay(2.5, 3) * .6, sine(233, 2.5) * decay(2.5, 3) * .4), 0.7), af="aecho=0.8:0.8:300:0.4")
save("task_done", norm(mix(at(sine(660, 0.4) * decay(0.4, 5), 0, 0.8), at(sine(880, 0.5) * decay(0.5, 5), 0.15, 0.8)), 0.5))
save("clean_done", norm(sine(990, 0.18) * decay(0.18, 7), 0.35))
save("sms", norm(mix(at(sine(1320, 0.25) * decay(0.25, 6), 0, 0.7), at(sine(1760, 0.3) * decay(0.3, 6), 0.2, 0.7)), 0.5))
save("water", norm(lp(noise(1.2), 1200) * (0.6 + 0.4 * np.sin(2 * np.pi * 7 * t(1.2))) * env(int(SR * 1.2), 0.1, 0.5), 0.5))
save("restock", norm(mix(*[at(hp(noise(0.05), 2000) * decay(0.05, 8), 0.12 * i, 0.8) for i in range(5)]), 0.6))
save("trash_throw", norm(lp(noise(0.5), 700) * decay(0.5, 6) + sine(60, 0.5) * decay(0.5, 8), 0.7))
save("kettle", norm(hp(noise(1.5), 3000) * env(int(SR * 1.5), 0.3, 0.6), 0.3))
# ---------- страх: короткие события ----------
d = 1.0; buzz = sum(sine(100 * k, d) / k for k in range(1, 9)) * (0.6 + 0.4 * (rng.random(int(SR * d // 800) + 2).repeat(800)[:int(SR * d)] > 0.4))
save("light_buzz", norm(buzz, 0.4))
for i in range(1, 4):
    d = 1.8; syl = (0.5 + 0.5 * np.sin(2 * np.pi * (3.0 + i) * t(d) + i)) ** 2
    w = bp(noise(d), 600 + 200 * i, 3500 + 500 * i) * syl * env(int(SR * d), 0.3, 0.6)
    save(f"whisper{i}", norm(w, 0.6), af="aecho=0.8:0.7:120:0.35")
d = 3.0; st = mix(*[at(lp(noise(0.18), 250) * decay(0.18, 8) + sine(55, 0.18) * decay(0.18, 12), 0.7 * i, d) for i in range(4)])
save("steps_far", norm(st, 0.7), af="lowpass=f=420,aecho=0.8:0.6:200:0.3")
save("knock", norm(mix(*[at((sine(190, 0.2) + 0.5 * lp(noise(0.2), 700)) * decay(0.2, 14), 0.28 * i, 1.0) for i in range(3)]), 0.9))
d = 1.6; save("creak", norm(sweep(70, 150, d) * (0.5 + 0.5 * np.sin(2 * np.pi * 22 * t(d))) * env(int(SR * d), 0.2, 0.5) + 0.2 * bp(noise(d), 300, 1500) * env(int(SR * d), 0.3, 0.5), 0.5))
d = 2.2; save("breath", norm(bp(noise(d), 300, 2200) * (np.sin(np.pi * t(d) / d) ** 2) * (0.7 + 0.3 * np.sin(2 * np.pi * 3 * t(d))), 0.55))
d = 4.0; sg = bp(noise(d), 900, 7000) * (rng.random(int(d * 40) + 1).repeat(SR // 40)[:int(SR * d)] > 0.3) * 0.5 + 0.3 * noise(d) * 0.2
save("radio_static", norm(sg, 0.5), af="highpass=f=300,lowpass=f=6000")
save("drip", norm(mix(sine(1200, 0.25) * decay(0.25, 10), at(sine(900, 0.25) * decay(0.25, 10) * .4, 0.2, 0.5)), 0.4), af="aecho=0.8:0.7:150:0.4")
save("thump", norm(sine(48, 0.8) * decay(0.8, 5) + lp(noise(0.8), 200) * decay(0.8, 8), 0.95))
d = 2.0; save("power_down", norm(sweep(300, 40, d) * decay(d, 2.5) + 0.3 * lp(noise(d), 300) * decay(d, 4), 0.7))
d = 1.2; save("power_up", norm(sweep(40, 220, d) * env(int(SR * d), 0.8, 0.2) + 0.1 * noise(d) * env(int(SR * d), 0.8, 0.2), 0.5))
# ---------- стинги и скримеры ----------
d = 2.0; stg = mix(*[sine(f, d) for f in (220, 233, 311, 466, 622)]) * decay(d, 4) * env(int(SR * d), 0.005, 0.3) + hp(noise(d), 800) * decay(d, 14) * 0.7
save("sting", norm(stg, 0.9), af="aecho=0.8:0.7:200:0.4")
d = 1.6; sg2 = mix(*[sine(f, d) for f in (196, 208, 277)]) * decay(d, 3.5) * env(int(SR * d), 0.04, 0.4)
save("sting_soft", norm(sg2, 0.45), af="aecho=0.8:0.8:250:0.4")
d = 1.5; scr = (sweep(900, 1700, d) * (1 + 0.3 * np.sin(2 * np.pi * 9 * t(d))) + sweep(1300, 2400, d) * 0.5 + bp(noise(d), 1000, 5000) * 0.6) * env(int(SR * d), 0.03, 0.4)
save("scream", norm(np.tanh(norm(scr) * 3), 0.9))
save("scream_far", norm(np.tanh(norm(scr) * 2) * 0.8, 0.5), af="lowpass=f=2500,aecho=0.8:0.7:300:0.5")
d = 2.2; jc = mix(lp(noise(d), 900) * decay(d, 5), sine(45, d) * decay(d, 3), sweep(1200, 300, d) * decay(d, 4) * .7, mix(*[sine(f, d) for f in (233, 247, 311, 392)]) * 0.5 * decay(d, 4))
save("jumpscare", norm(np.tanh(norm(jc) * 4), 0.98))
# ---------- монстры ----------
d = 1.3; gr = np.tanh(saw(65, d) * (0.6 + 0.4 * np.sin(2 * np.pi * 18 * t(d))) * 2) + 0.5 * lp(noise(d), 500)
save("mimic_growl", norm(gr * env(int(SR * d), 0.1, 0.4), 0.8))
d = 0.7; save("mimic_lunge", norm(np.tanh(saw(90, d) * 2) * env(int(SR * d), 0.02, 0.3) + hp(noise(d), 800) * env(int(SR * d), 0.01, 0.4) * .5, 0.9))
d = 0.8; save("mimic_screech", norm(np.tanh(sweep(2800, 700, d) * 2) * env(int(SR * d), 0.01, 0.3), 0.7))
d = 1.0; save("shadow_die", norm(bp(noise(d), 200, 2500) * np.linspace(1, 0, int(SR * d)) ** 1.5 + sweep(400, 40, d) * decay(d, 4) * .5, 0.7), af="aecho=0.8:0.7:150:0.4")
d = 2.0; roar = np.tanh(saw(48, d) * 3 * (0.7 + 0.3 * np.sin(2 * np.pi * 11 * t(d)))) + 0.6 * lp(noise(d), 700) + 0.3 * saw(96, d)
save("host_roar", norm(roar * env(int(SR * d), 0.08, 0.7), 0.95), af="aecho=0.8:0.7:120:0.4")
d = 1.8; hc = mix(*[at(lp(noise(0.25), 220) * decay(0.25, 7) + sine(50, 0.25) * decay(0.25, 9), 0.9 * i, d) for i in range(2)])
save("host_chase", norm(hc, 0.9))
d = 0.6; save("crawler_die", norm(bp(noise(d), 100, 1500) * decay(d, 6) * (0.5 + 0.5 * np.sin(2 * np.pi * 30 * t(d))), 0.7))
d = 3.5; pt = (sweep(60, 900, d) * 0.5 + sweep(900, 180, d) * 0.3) * env(int(SR * d), 1.0, 0.5) + bp(noise(d), 300, 3000) * env(int(SR * d), 1.2, 0.5) * .5
save("portal", norm(pt, 0.9), af="aecho=0.8:0.8:200:0.4")
hb = mix(at(sine(55, 0.3) * decay(0.3, 8), 0, 2.0), at(sine(48, 0.3) * decay(0.3, 8) * .7, 0.3, 2.0), at(sine(55, 0.3) * decay(0.3, 8), 1.0, 2.0), at(sine(48, 0.3) * decay(0.3, 8) * .7, 1.3, 2.0))
save("heartbeat", norm(hb, 0.95))
d = 1.5; save("heart_hit", norm(sine(40, d) * decay(d, 3) + lp(noise(d), 300) * decay(d, 5) + sine(80, d) * decay(d, 4) * .5, 0.98))
# ---------- петли инструментов ----------
d = 2.0; vac = bp(noise(d + 1), 500, 4500) + 0.5 * sine(120, d + 1) + 0.3 * sine(240, d + 1)
save("vacuum", norm(loopify(vac, 0.5), 0.6))
d = 1.5; sp = hp(noise(d + 1), 3500)
save("spray", norm(loopify(sp, 0.5), 0.35))
for nm, (f0, f1, rate) in {"rub_rag": (800, 5000, 5), "rub_mop": (300, 2500, 3), "rub_broom": (1500, 8000, 6)}.items():
    d = 1.2; r = bp(noise(d + 1), f0, f1) * (0.4 + 0.6 * np.abs(np.sin(np.pi * rate * t(d + 1) / (1.0))))
    save(nm, norm(loopify(r, 0.5), 0.35))
# ---------- амбиенты и музыка ----------
def drone(freqs, d, noise_amt=0.06, wob=0.1, hi=0.0):
    x = np.zeros(int(SR * d))
    for i, f in enumerate(freqs):
        lfo = 0.6 + 0.4 * np.sin(2 * np.pi * (wob + 0.03 * i) * t(d) + i)
        x += np.sin(2 * np.pi * f * t(d) + 0.5 * np.sin(2 * np.pi * 0.07 * t(d))) * lfo / (1 + 0.3 * i)
        x += np.sin(2 * np.pi * f * 1.004 * t(d)) * lfo * 0.5 / (1 + 0.3 * i)
    x += lp(noise(d), 300) * noise_amt * 6
    if hi: x += bp(noise(d), 2000, 6000) * hi * (0.5 + 0.5 * np.sin(2 * np.pi * 0.05 * t(d)))
    return x
D = 40.0
amb = {"amb_house": ([55, 82.4, 110], 0.06, 0.08, 0.02), "amb_mansion": ([41.2, 61.7, 123.5], 0.08, 0.06, 0.03), "amb_under": ([36.7, 55, 73.4, 92.5], 0.1, 0.05, 0.04)}
for nm, (fr, na, wb, hi) in amb.items():
    save(nm, norm(loopify(drone(fr, D + 2, na, wb, hi), 2.0), 0.5), folder="sfx", sr=22050, q=1)
mus = {"drone_a": [55, 65.4, 82.4, 98], "drone_b": [49, 58.3, 73.4, 87.3], "drone_c": [43.7, 51.9, 65.4, 77.8, 103.8], "drone_d": [58.3, 69.3, 87.3, 103.8],
       "drone_e": [41.2, 46.2, 61.7, 77.8, 92.5], "drone_f": [36.7, 43.7, 55, 65.4, 82.4, 98], "drone_g": [32.7, 38.9, 49, 58.3, 77.8, 116.5]}
for nm, fr in mus.items():
    save(nm, norm(loopify(drone(fr, 60 + 3, 0.04, 0.07, 0.02), 3.0), 0.55), folder="music", sr=22050, q=1)
