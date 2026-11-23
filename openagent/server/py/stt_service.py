"""Сервис распознавания речи GigaAM Multilingual (large_ctc, 600M, MIT; ai-sage/GigaAM-Multilingual) на CPU.
POST /transcribe  — тело: сырой PCM 16 кГц / 16 бит / моно (application/octet-stream) → {"text": "...", "ms": N, "audio_s": X}
GET  /health      — {"ok": true}
Длинную речь режет на куски ≤ 22 с по самым тихим местам (модель принимает ≤ 25 с).
Запуск: python stt_service.py [port]   (первый запуск скачивает веса ~2,4 ГБ с Hugging Face)"""
import json, os, struct, sys, tempfile, threading, time, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import numpy as np
import torch
from transformers import AutoModel

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8792
REV = os.environ.get("GIGAAM_REVISION", "large_ctc")          # large_ctc — 600M; ctc — 220M (быстрее, чуть хуже)
torch.set_num_threads(int(os.environ.get("STT_THREADS", os.cpu_count())))
model = AutoModel.from_pretrained("ai-sage/GigaAM-Multilingual", revision=REV, trust_remote_code=True)
model.eval()
lock = threading.Lock()
SR = 16000
MAXS = 22 * SR

def _wav(pcm: np.ndarray) -> str:
    f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(f, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.astype("<i2").tobytes())
    return f.name

def _text(r):
    return (r if isinstance(r, str) else getattr(r, "text", None) or (r[0] if isinstance(r, (list, tuple)) and r else str(r))).strip()

def _split(pcm: np.ndarray):
    """Куски ≤ 22 с; граница — самое тихое место в последних 4 с куска."""
    out, i = [], 0
    while len(pcm) - i > MAXS:
        lo, hi = i + MAXS - 4 * SR, i + MAXS
        win = np.abs(pcm[lo:hi].astype(np.float32)); k = 1600
        e = np.convolve(win, np.ones(k) / k, mode="valid")
        cut = lo + int(np.argmin(e)) + k // 2
        out.append(pcm[i:cut]); i = cut
    out.append(pcm[i:])
    return [c for c in out if len(c) > SR // 10]

def transcribe(pcm: np.ndarray) -> str:
    if len(pcm) < SR // 10:
        return ""
    parts = []
    for c in _split(pcm):
        path = _wav(c)
        try:
            with lock, torch.inference_mode():
                parts.append(_text(model.transcribe(path)))
        finally:
            os.unlink(path)
    return " ".join(p for p in parts if p).strip()

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        d = json.dumps(obj, ensure_ascii=False).encode(); self.send_response(code); self.send_header("content-type", "application/json"); self.end_headers(); self.wfile.write(d)
    def do_GET(self): self._send(200, {"ok": True, "model": f"GigaAM-Multilingual/{REV}"})
    def do_POST(self):
        n = int(self.headers.get("content-length", 0)); raw = self.rfile.read(n)
        if n > 1_920_000 * 10: return self._send(413, {"error": "слишком длинная запись"})
        t0 = time.time()
        try:
            pcm = np.frombuffer(raw[: len(raw) // 2 * 2], dtype="<i2")
            txt = transcribe(pcm)
            self._send(200, {"text": txt, "ms": int((time.time() - t0) * 1000), "audio_s": round(len(pcm) / SR, 2)})
        except Exception as e:
            self._send(500, {"error": str(e)[:300]})

if __name__ == "__main__":
    transcribe(np.zeros(SR, dtype="<i2"))   # прогрев
    print("gigaam stt ready on", PORT, flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
