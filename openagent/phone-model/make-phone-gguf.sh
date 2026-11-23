#!/usr/bin/env bash
# Делает phone.gguf — модель управления телефоном для оффлайн-режима приложения (Qwen3-0.6B + наша LoRA, Q8_0, ~640 МБ).
# Запуск на любом компьютере с Python 3.10+, git, cmake и ~6 ГБ места:   ./make-phone-gguf.sh [папка_с_LoRA]
# Результат — ./out/phone.gguf. Положите его на сервер в DATA_DIR/models/ (приложение скачает само) либо выберите «Файл…» в Настройки → Оффлайн-режим.
set -euo pipefail
LORA="${1:-../../dist/phone-lora-v2}"; OUT="$(pwd)/out"; mkdir -p "$OUT"; cd "$OUT"
python3 -m venv venv && . venv/bin/activate
pip install -q torch --index-url https://download.pytorch.org/whl/cpu
pip install -q transformers peft gguf sentencepiece safetensors numpy
python - <<PY
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
m = AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-0.6B", torch_dtype=torch.float32)
m = PeftModel.from_pretrained(m, "$(cd "$OLDPWD" && cd "$LORA" && pwd)").merge_and_unload()
m.save_pretrained("merged", safe_serialization=True); AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B").save_pretrained("merged")
PY
[ -d llama.cpp ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp
python llama.cpp/convert_hf_to_gguf.py merged --outfile phone-f16.gguf --outtype f16
cmake -S llama.cpp -B llama.cpp/build -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_SERVER=OFF >/dev/null
cmake --build llama.cpp/build -j --target llama-quantize
llama.cpp/build/bin/llama-quantize phone-f16.gguf phone.gguf Q8_0
ls -la phone.gguf
