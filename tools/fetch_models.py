#!/usr/bin/env python3
"""Скачивает CC0-модели Poly Haven (glTF 1k) в assets/models/<id>/, уменьшает текстуры до 512px."""
import json, subprocess, os, sys
from PIL import Image
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = ["Sofa_01","sofa_02","ArmChair_01","WoodenTable_01","CoffeeTable_01","WoodenChair_01","dining_chair_02","wooden_stool_01",
 "old_bed_frame","GothicBed_01","painted_wooden_cabinet_02","GothicCabinet_01","vintage_cabinet_01","wooden_bookshelf_worn","Shelf_01",
 "drawer_cabinet","vintage_wooden_drawer_01","Television_01","electric_stove","ornate_mirror_01","vintage_radio_transceiver","wall_clock",
 "potted_plant_01","wooden_bucket_01","wooden_crate_01","cardboard_box_01","trashbag","vintage_suitcase","vintage_electric_kettle",
 "wooden_broom","multi_cleaner_bottle","metal_trash_can","vintage_oil_lamp","ceramic_vase_01","book_encyclopedia_set_01","ClassicNightstand_01","old_military_crate","gothic_statue"]
def curl(url, out=None):
    cmd = ["curl","-sL","-m","180","-A","Mozilla/5.0"] + (["-o", out] if out else []) + [url]
    return subprocess.run(cmd, capture_output=True).stdout
for mid in MODELS:
    d = f"{ROOT}/assets/models/{mid}"
    if os.path.exists(f"{d}/ok"): continue
    try:
        f = json.loads(curl(f"https://api.polyhaven.com/files/{mid}"))
        g = f["gltf"]["1k"]["gltf"]
    except Exception as e:
        print("SKIP", mid, e); continue
    os.makedirs(d, exist_ok=True)
    curl(g["url"], f"{d}/{mid}.gltf")
    for rel, info in g.get("include", {}).items():
        out = f"{d}/{rel}"; os.makedirs(os.path.dirname(out), exist_ok=True)
        curl(info["url"], out)
        if rel.lower().endswith((".jpg", ".png")):
            try:
                im = Image.open(out); 
                if max(im.size) > 512: im = im.resize((512, 512 * im.size[1] // im.size[0]) if im.size[0] >= im.size[1] else (512 * im.size[0] // im.size[1], 512)); im.save(out)
            except Exception as e: print("img", rel, e)
    open(f"{d}/ok", "w").write("1")
    print("ok", mid, sum(os.path.getsize(os.path.join(r, x)) for r, _, fs in os.walk(d) for x in fs) // 1024, "KB")
