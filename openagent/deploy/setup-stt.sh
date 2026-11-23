#!/usr/bin/env bash
# Распознавание речи GigaAM Multilingual 600M (ai-sage, MIT) на CPU сервера. Запускать от root после основного setup.sh: bash deploy/setup-stt.sh
# Нужно ~5 ГБ диска (PyTorch + веса 2,4 ГБ) и ~3 ГБ свободной ОЗУ. Скорость на 4 ядрах: ~0,5–1 с на фразу (быстрее реального времени в 3–10 раз).
set -euo pipefail
APP=/opt/openagent; DIR=/opt/openagent-stt; SRC="$(cd "$(dirname "$0")/.." && pwd)"
apt-get install -y python3-venv ffmpeg >/dev/null
python3 -m venv "$DIR/venv"
"$DIR/venv/bin/pip" install -q --upgrade pip
"$DIR/venv/bin/pip" install -q torch torchaudio --index-url https://download.pytorch.org/whl/cpu
"$DIR/venv/bin/pip" install -q "transformers>=5" hydra-core omegaconf soundfile sentencepiece numpy
# Код модели импортирует pyannote только для встроенной нарезки длинных записей; сервис режет аудио сам — достаточно заглушки
SP=$("$DIR/venv/bin/python" -c "import site;print(site.getsitepackages()[0])"); mkdir -p "$SP/pyannote"
echo "# заглушка: нарезку длинных записей делает stt_service.py" > "$SP/pyannote/__init__.py"
cp "$SRC/server/py/stt_service.py" "$DIR/stt_service.py"
cat > /etc/systemd/system/openagent-stt.service <<EOP
[Unit]
Description=OpenAgent STT (GigaAM Multilingual 600M)
After=network-online.target

[Service]
WorkingDirectory=$DIR
Environment=HF_HOME=$DIR/hf
ExecStart=$DIR/venv/bin/python $DIR/stt_service.py 8792
Restart=always
RestartSec=3
Nice=5

[Install]
WantedBy=multi-user.target
EOP
systemctl daemon-reload && systemctl enable --now openagent-stt
grep -q '^STT_ENGINE=' $APP/.env || printf '\n# Распознавание речи: GigaAM Multilingual 600M на сервере (если сервис недоступен — Deepgram)\nSTT_ENGINE=gigaam\nGIGAAM_URL=http://127.0.0.1:8792\n' >> $APP/.env
systemctl restart openagent
echo "Первый запуск скачивает веса (~2,4 ГБ). Проверка: curl -s localhost:8792/ ; журнал: journalctl -u openagent-stt -f"
