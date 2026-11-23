#!/usr/bin/env python3
"""lines.py -> audio/script/lines.csv и data/strings_ru.json"""
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from script_lines import LINES
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(f"{ROOT}/audio/script", exist_ok=True)
with open(f"{ROOT}/audio/script/lines.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["id", "speaker", "text"])
    for i, s, t in LINES: w.writerow([i, s, t])
d = {i: {"speaker": s, "text": t} for i, s, t in LINES}
with open(f"{ROOT}/data/strings_ru.json", "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=1)
print(len(d), "lines")
