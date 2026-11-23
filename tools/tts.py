#!/usr/bin/env python3
"""Конвейер озвучки: audio/script/lines.csv -> Fish Audio TTS -> ffmpeg (эффекты) -> audio/vo/<speaker>/<id>.ogg
Ключ API не нужен: его подставляет прокси сессии. Использование: tts.py [--only id,id] [--force]"""
import csv, os, subprocess, sys, json, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOICES = {
    "hero": "c962ed46edfd419abc530d1e33a7435f",
    "family": "f14e1f9fb32d4dbd8cd5b40a0fef86a5",
    "mother": "2a1036d645634680b3cc69aeeb60375b",
    "child": "a8e5015454944692be752b3c7b00e3d5",
    "artem": "868377a7b08f4c0d9acf8c9f059571aa",
    "house": "bf36604cb53d41e19a8bec710d0af12e",
}
# эффекты ffmpeg по говорящему
FX = {
    "hero": "loudnorm=I=-18",
    "family": "loudnorm=I=-19,aecho=0.8:0.6:40:0.2",
    "mother": "loudnorm=I=-19,aecho=0.8:0.7:60:0.25",
    "child": "loudnorm=I=-18,aecho=0.8:0.6:30:0.2",
    "artem": "loudnorm=I=-19,highpass=f=200,aecho=0.8:0.7:80:0.3",
    "house": "asetrate=44100*0.78,aresample=44100,atempo=1.1,aecho=0.8:0.8:120|240:0.5|0.3,loudnorm=I=-15,acrusher=bits=12:mix=0.3",
}
def synth(i, spk, text, force):
    out = f"{ROOT}/audio/vo/{spk}/{i}.ogg"
    fx_extra = ""
    if i.startswith("sfx_"):
        out = f"{ROOT}/audio/sfx/{i[4:]}.ogg"
        fx_extra = ",highpass=f=250,aecho=0.8:0.8:150:0.5,volume=0.8" if "whisper" in i else ",aecho=0.8:0.6:80:0.3"
    if os.path.exists(out) and not force: return i, True
    os.makedirs(os.path.dirname(out), exist_ok=True)
    body = json.dumps({"text": text, "format": "mp3", "reference_id": VOICES[spk]}).encode()
    for attempt in range(4):
        try:
            req = urllib.request.Request("https://api.fish.audio/v1/tts", body, {"Content-Type": "application/json", "model": "s2.1-pro-free"})
            data = urllib.request.urlopen(req, timeout=120).read()
            tmp = f"/tmp/tts_{i}.mp3"; open(tmp, "wb").write(data)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-af", FX[spk] + fx_extra, "-ac", "1", "-ar", "44100", "-c:a", "libvorbis", "-q:a", "3", out], check=True)
            os.remove(tmp)
            return i, True
        except Exception as e:
            err = str(e)
            time.sleep(3 + attempt * 4)
    print("FAIL", i, err); return i, False
def main():
    only = None; force = "--force" in sys.argv
    for a in sys.argv:
        if a.startswith("--only"): only = set(sys.argv[sys.argv.index(a) + 1].split(","))
    rows = list(csv.DictReader(open(f"{ROOT}/audio/script/lines.csv", encoding="utf-8")))
    rows = [r for r in rows if not only or r["id"] in only]
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(lambda r: synth(r["id"], r["speaker"], r["text"], force), rows))
    ok = sum(1 for _, s in res if s); print(f"{ok}/{len(res)} ok")
main()
