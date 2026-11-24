# Малая модель управления телефоном

Qwen3-0.6B + LoRA, обучена переводить русскую фразу в действия `phone` (JSON), которые приложение выполняет как есть.
Запускается на CPU сервера (GGUF, `node-llama-cpp`). Всё, что не распознано, → пустой список → обычный агент.

- `sim.py` — симулятор телефона (схема + состояние). Проверяет каждый пример и каждый ответ модели по итоговому состоянию.
- `lang.py`, `gen.py` — генератор датасета (русские числа, время, склонения, приложения, шум распознавания, команды из двух действий, отрицательные примеры).
- `handwritten.py` — ручной тест (139 фраз, не из шаблонов; часть — «вне распределения»). В обучение не попадает.
- `train.py` — LoRA на CPU. `evaluate.py` — оценка. `export.sh` — слияние и GGUF.

```
python gen.py data 14000
python train.py data7k lora_v1 1.6         # ~1,5 ч на 4 ядрах
python evaluate.py lora_v1 --val 300
./export.sh lora_v1 out
```

## Запуск на сервере (без GPU)
Основной вариант — CTranslate2 int8 (~0,9 с на команду на 4 ядрах; PyTorch fp32 — ~1,8 с):
```
pip install torch transformers peft ctranslate2
# слить LoRA с базой и сконвертировать:
python - <<PY
import torch; from transformers import AutoModelForCausalLM, AutoTokenizer; from peft import PeftModel
m = PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-0.6B", dtype=torch.float32), "../dist/phone-lora-v2").merge_and_unload()
m.save_pretrained("merged"); AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B").save_pretrained("merged")
PY
ct2-transformers-converter --model merged --output_dir ct2-int8 --quantization int8
python serve_ct2.py ct2-int8 merged 8791        # затем в .env сервера: PHONE_MODEL_URL=http://127.0.0.1:8791
```
Без `PHONE_MODEL_URL` и без файла модели быстрый путь выключен, всё идёт через обычного агента (`PHONE_MODEL=0` — выключить явно).
Перед выполнением ответ проходит проверки на сервере (`server/src/slotCheck.js`): схема, числа (время/длительность/уровни независимым разбором фразы), привязка к фразе (имена, направление «включи/выключи», приложение из известного списка). Не прошло — команду берёт большая модель.
Результаты на 139 ручных фразах: верно 101 из 114 команд, неверно выполнено 0, 13 ушли большой модели, 25 из 25 «не команд» переданы правильно.

## Оффлайн-режим в приложении (v11)
`make-phone-gguf.sh` собирает `phone.gguf` (Qwen3-0.6B + LoRA, Q5_K_M). Файл кладётся на сервер в `DATA_DIR/models/phone.gguf` (раздаётся по `/models/phone.gguf`, с докачкой) либо выбирается вручную в приложении. Чат оффлайн — Ministral 3 3B Instruct (Q4_K_M) с Hugging Face.
