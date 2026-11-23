"""Локальный сервис малой модели (PyTorch, без GGUF): POST /phone {"text": "..."} → {"out": "<json>", "ms": N}.
Запуск: python serve.py <lora_dir> [port]   (база Qwen/Qwen3-0.6B скачивается один раз с Hugging Face)
PHONE_INT8=1 — динамическая int8-квантизация (быстрее на CPU), PHONE_THREADS — число потоков."""
import json, os, sys, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

lora = sys.argv[1]; port = int(sys.argv[2]) if len(sys.argv) > 2 else 8791
BASE = os.environ.get("PHONE_BASE", "Qwen/Qwen3-0.6B")
torch.set_num_threads(int(os.environ.get("PHONE_THREADS", os.cpu_count())))
tok = AutoTokenizer.from_pretrained(BASE)
model = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.float32)
model = PeftModel.from_pretrained(model, lora).merge_and_unload().eval()
if os.environ.get("PHONE_INT8") == "1":
    model = torch.ao.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
PROMPT = "<|im_start|>user\n{}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
END = tok.convert_tokens_to_ids("<|im_end|>")
lock = threading.Lock()

def infer(text):
    x = tok(PROMPT.format(text[:300]), return_tensors="pt", add_special_tokens=False)
    with lock, torch.inference_mode():
        y = model.generate(**x, max_new_tokens=110, do_sample=False, pad_token_id=tok.pad_token_id, eos_token_id=END)
    return tok.decode(y[0][x["input_ids"].shape[1]:], skip_special_tokens=True).strip()

infer("привет")   # прогрев

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        t0 = time.time(); out = infer(str(body.get("text", "")))
        data = json.dumps({"out": out, "ms": int((time.time() - t0) * 1000)}, ensure_ascii=False).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(data)

print("phone-model ready on", port, flush=True)
ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
