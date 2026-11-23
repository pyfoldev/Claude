"""Оценка: модель → JSON → симулятор. Сравнивается итоговое состояние телефона (смысл), а не текст.
python evaluate.py <lora_or_merged_dir> [--val N] [--base Qwen/Qwen3-0.6B]"""
import json, sys, time, collections
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import sim, handwritten

d = sys.argv[1]
nval = int(sys.argv[sys.argv.index("--val") + 1]) if "--val" in sys.argv else 300
base = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "Qwen/Qwen3-0.6B"
data_dir = sys.argv[sys.argv.index("--data") + 1] if "--data" in sys.argv else "/tmp/claude-0/pm/data"
torch.set_num_threads(4)
PROMPT = "<|im_start|>user\n{}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
tok = AutoTokenizer.from_pretrained(base); tok.padding_side = "left"
model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.float32)
import os
if os.path.exists(os.path.join(d, "adapter_config.json")):
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, d).merge_and_unload()
model.eval()

def gen(texts, bs=16):
    out = []
    for i in range(0, len(texts), bs):
        b = [PROMPT.format(t) for t in texts[i:i + bs]]
        x = tok(b, return_tensors="pt", padding=True, add_special_tokens=False)
        with torch.no_grad():
            y = model.generate(**x, max_new_tokens=110, do_sample=False, pad_token_id=tok.pad_token_id, eos_token_id=tok.convert_tokens_to_ids("<|im_end|>"))
        out += [tok.decode(r[x["input_ids"].shape[1]:], skip_special_tokens=True).strip() for r in y]
    return out

def judge(pred, want):
    try:
        acts = json.loads(pred)
        if not isinstance(acts, list):
            return "bad_json"
    except Exception:
        return "bad_json"
    st, err = sim.run(acts)
    if err:
        return "invalid"
    ws, _ = sim.run(want)
    return "ok" if st == ws else "wrong"

def report(name, items):
    t0 = time.time(); preds = gen([t for t, _, _ in items]); dt = time.time() - t0
    res = [judge(p, w) for p, (_, w, _) in zip(preds, items)]
    c = collections.Counter(res)
    acc = c["ok"] / len(items)
    neg = [(r, w) for r, (_, w, _) in zip(res, items) if not w]
    pos = [(r, w) for r, (_, w, _) in zip(res, items) if w]
    print(f"\n== {name}: {c['ok']}/{len(items)} = {acc:.1%}  (неверно {c['wrong']}, невалидно {c['invalid']}, не JSON {c['bad_json']})  {dt / len(items):.2f} с/фраза (HF, CPU)")
    print(f"   команды: {sum(r == 'ok' for r, _ in pos)}/{len(pos)}   fallback ([]): {sum(r == 'ok' for r, _ in neg)}/{len(neg)}")
    return preds, res

val = [json.loads(l) for l in open(f"{data_dir}/val.jsonl", encoding="utf8")][:nval]
vitems = [(r["text"], json.loads(r["out"]), "val") for r in val]
report(f"val (шаблонные фразы, {len(vitems)})", vitems)
preds, res = report("РУЧНОЙ тест (фразы не из шаблонов)", handwritten.HAND)
for lab in ("id", "ood"):
    sub = [(r) for r, h in zip(res, handwritten.HAND) if h[2] == lab]
    print(f"   ручной/{lab}: {sum(r == 'ok' for r in sub)}/{len(sub)}")
print("\nОШИБКИ на ручном тесте:")
for p, r, (t, w, lab) in zip(preds, res, handwritten.HAND):
    if r != "ok":
        print(f"  [{lab}] {t!r}\n      ждали {json.dumps(w, ensure_ascii=False, separators=(',', ':'))}\n      вышло {p}")
