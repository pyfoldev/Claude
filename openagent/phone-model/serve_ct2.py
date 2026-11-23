"""Сервис малой модели на CTranslate2 (int8, быстрый CPU-инференс): POST / {"text": "..."} → {"out": "<json>", "ms": N}.
Запуск: python serve_ct2.py <ct2_dir> <tokenizer_dir> [port]"""
import json, os, sys, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ctranslate2
from transformers import AutoTokenizer

ct2_dir, tok_dir = sys.argv[1], sys.argv[2]; port = int(sys.argv[3]) if len(sys.argv) > 3 else 8791
tok = AutoTokenizer.from_pretrained(tok_dir)
gen = ctranslate2.Generator(ct2_dir, device="cpu", compute_type="int8", inter_threads=1, intra_threads=int(os.environ.get("PHONE_THREADS", os.cpu_count())))
PROMPT = "<|im_start|>user\n{}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
lock = threading.Lock()

def infer(text):
    toks = tok.convert_ids_to_tokens(tok(PROMPT.format(text[:300]), add_special_tokens=False)["input_ids"])
    with lock:
        r = gen.generate_batch([toks], max_length=110, sampling_topk=1, include_prompt_in_result=False, end_token="<|im_end|>")[0]
    return tok.decode(r.sequences_ids[0], skip_special_tokens=True).strip()

infer("привет")
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
