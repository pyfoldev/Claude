#!/usr/bin/env bash
# LoRA → слитая модель → GGUF (Q8_0 или Q4). Использование: ./export.sh <lora_dir> <out_dir>
# Нужны: python venv с transformers/peft/torch, исходники llama.cpp (convert_hf_to_gguf.py; есть в sdist llama-cpp-python).
set -euo pipefail
LORA="$1"; OUT="$2"; BASE="${BASE:-Qwen/Qwen3-0.6B}"; CONV="${CONVERT:-convert_hf_to_gguf.py}"
mkdir -p "$OUT"
python - <<PY
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
m = AutoModelForCausalLM.from_pretrained("$BASE", dtype=torch.float32)
m = PeftModel.from_pretrained(m, "$LORA").merge_and_unload()
m.save_pretrained("$OUT/merged", safe_serialization=True); AutoTokenizer.from_pretrained("$BASE").save_pretrained("$OUT/merged")
PY
python "$CONV" "$OUT/merged" --outfile "$OUT/phone-f16.gguf" --outtype f16
python "$CONV" "$OUT/merged" --outfile "$OUT/phone-q8.gguf" --outtype q8_0
ls -la "$OUT"/*.gguf
