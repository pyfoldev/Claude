"""LoRA-дообучение малой модели (Qwen3-0.6B) на CPU: фраза → JSON-действия. python train.py data_dir out_dir [epochs] [base]"""
import json, math, os, random, sys, time
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model

data_dir, out_dir = sys.argv[1], sys.argv[2]
epochs = float(sys.argv[3]) if len(sys.argv) > 3 else 2
base = sys.argv[4] if len(sys.argv) > 4 else "Qwen/Qwen3-0.6B"
MAXSTEPS = int(os.environ.get("MAXSTEPS", "0"))
BS, ACC, LR, MAXLEN = 8, 2, 3e-4, 128   # эффективный батч 16; по 8 — чтобы не упереться в память (логиты 150k слов × токены)
torch.manual_seed(0); random.seed(0)
torch.set_num_threads(os.cpu_count())

PROMPT = "<|im_start|>user\n{}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
tok = AutoTokenizer.from_pretrained(base)
model = AutoModelForCausalLM.from_pretrained(base, torch_dtype=torch.float32)
RESUME = os.environ.get("RESUME")
LR = float(os.environ.get("LR", LR))
if RESUME:
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, RESUME, is_trainable=True)
else:
  model = get_peft_model(model, LoraConfig(r=32, lora_alpha=64, lora_dropout=0.05, target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"], task_type="CAUSAL_LM"))
model.config.use_cache = False
model.print_trainable_parameters()

rows = [json.loads(l) for l in open(f"{data_dir}/train.jsonl", encoding="utf8")]
def enc(r):
    p = tok(PROMPT.format(r["text"]), add_special_tokens=False)["input_ids"]
    t = tok(r["out"] + "<|im_end|>", add_special_tokens=False)["input_ids"]
    ids = (p + t)[:MAXLEN]
    return ids, ([-100] * len(p) + t)[:MAXLEN]
data = [enc(r) for r in rows]
print("примеров", len(data), "средняя длина", sum(len(d[0]) for d in data) / len(data), flush=True)

steps_per_epoch = math.ceil(len(data) / (BS * ACC))
total = int(steps_per_epoch * epochs) if not MAXSTEPS else MAXSTEPS
opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LR, weight_decay=0.0)
sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / 30) * 0.5 * (1 + math.cos(math.pi * min(s, total) / total)))
model.train(); t0 = time.time(); step = 0; ema = None
while step < total:
    # сортируем в корзины по длине внутри эпохи — меньше паддинга
    idx = list(range(len(data))); random.shuffle(idx)
    chunks = [sorted(idx[i:i + BS * 20], key=lambda j: len(data[j][0])) for i in range(0, len(idx), BS * 20)]
    batches = [c[i:i + BS] for c in chunks for i in range(0, len(c), BS)]; random.shuffle(batches)
    for bi in range(0, len(batches) - ACC + 1, ACC):
        if step >= total: break
        for b in batches[bi:bi + ACC]:
            L = max(len(data[j][0]) for j in b)
            ids = torch.tensor([data[j][0] + [tok.pad_token_id] * (L - len(data[j][0])) for j in b])
            lab = torch.tensor([data[j][1] + [-100] * (L - len(data[j][1])) for j in b])
            att = torch.tensor([[1] * len(data[j][0]) + [0] * (L - len(data[j][0])) for j in b])
            loss = model(input_ids=ids, attention_mask=att, labels=lab).loss
            (loss / ACC).backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step(); sched.step(); opt.zero_grad(set_to_none=True); step += 1
        ema = loss.item() if ema is None else 0.95 * ema + 0.05 * loss.item()
        if step % 10 == 0 or step == 1:
            el = time.time() - t0
            print(f"step {step}/{total} loss {loss.item():.4f} ema {ema:.4f} lr {sched.get_last_lr()[0]:.2e} {el:.0f}s eta {el / step * (total - step) / 60:.1f} мин", flush=True)
        if step % 200 == 0:
            model.save_pretrained(out_dir)
model.save_pretrained(out_dir); tok.save_pretrained(out_dir)
print("готово", time.time() - t0, "с", flush=True)
