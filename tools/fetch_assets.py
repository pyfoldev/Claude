#!/usr/bin/env python3
"""Скачивает CC0-текстуры Poly Haven (1k diffuse) в assets/tex и пишет реестр в CREDITS.md."""
import json, subprocess, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = {
 "floor_wood":"old_wood_floor","floor_dark":"dark_planks","floor_tile":"dirty_tiles","floor_lino":"old_linoleum_flooring_01",
 "floor_carpet":"dirty_carpet","floor_conc":"concrete_floor_painted",
 "wall_paper":"decrepit_wallpaper","wall_plaster":"painted_plaster_wall","wall_grey":"grey_plaster_02","wall_peel":"peeling_painted_wall",
 "wall_blue":"blue_plaster_wall","wall_brick":"painted_worn_brick","ceil":"grey_plaster_03",
 "wood":"brown_planks_03","leather":"brown_leather","fabric":"fabric_pattern_05","metal":"rusty_metal_02","dirt":"dirt_floor",
}
def curl(url, out=None):
    cmd = ["curl","-sL","-m","120","-A","Mozilla/5.0"] + (["-o",out] if out else []) + [url]
    r = subprocess.run(cmd, capture_output=True)
    return r.stdout
os.makedirs(f"{ROOT}/assets/tex", exist_ok=True)
for key, pid in TEX.items():
    out = f"{ROOT}/assets/tex/{key}.jpg"
    if os.path.exists(out) and os.path.getsize(out) > 1000: continue
    files = json.loads(curl(f"https://api.polyhaven.com/files/{pid}"))
    k = next(k for k in files if k.lower() in ("diffuse","color","albedo","base_color","col_01"))
    url = files[k]["1k"]["jpg"]["url"]
    curl(url, out)
    print(key, pid, os.path.getsize(out))
