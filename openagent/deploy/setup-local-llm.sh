#!/usr/bin/env bash
# Локальная модель Qwen3.5-2B на сервере без GPU (llama.cpp, Q4_K_M + зрение mmproj): обычный чат, документы, анализ фото.
# Запускать на сервере от root: bash setup-local-llm.sh   (после основного setup.sh). Нужно ~3 ГБ диска и ~3 ГБ свободной ОЗУ.
set -euo pipefail
APP=/opt/openagent; DIR=/opt/llm; mkdir -p "$DIR"; cd "$DIR"
REPO="unsloth/Qwen3.5-2B-GGUF"; QUANT="${QUANT:-Qwen3.5-2B-Q4_K_M.gguf}"; MMPROJ="${MMPROJ:-mmproj-F16.gguf}"

# 1) llama.cpp (готовая сборка из релизов; если не нашлась — сборка из исходников)
if [ ! -x "$DIR/llama/llama-server" ]; then
  URL=$(curl -fsSL https://api.github.com/repos/ggml-org/llama.cpp/releases/latest | jq -r '.assets[].browser_download_url' | grep -E 'bin-ubuntu-x64\.(zip|tar\.gz)$' | head -1 || true)
  if [ -n "$URL" ]; then
    curl -fsSL "$URL" -o llama.pkg && mkdir -p llama && (unzip -qo llama.pkg -d llama 2>/dev/null || tar xzf llama.pkg -C llama)
    SRV=$(find llama -name llama-server -type f | head -1); [ -n "$SRV" ] && ln -sf "$(readlink -f "$SRV")" "$DIR/llama/llama-server"
  fi
  if [ ! -x "$DIR/llama/llama-server" ]; then
    apt-get install -y cmake build-essential git
    git clone --depth 1 https://github.com/ggml-org/llama.cpp src && cmake -S src -B src/build -DCMAKE_BUILD_TYPE=Release && cmake --build src/build -j"$(nproc)" --target llama-server
    mkdir -p llama && cp src/build/bin/llama-server llama/ && cp src/build/bin/*.so* llama/ 2>/dev/null || true
  fi
fi
chmod +x "$DIR/llama/llama-server"

# 2) веса (скачиваются один раз; докачка при обрыве)
[ -f "$QUANT" ]  || curl -fL -C - "https://huggingface.co/$REPO/resolve/main/$QUANT" -o "$QUANT"
[ -f "$MMPROJ" ] || curl -fL -C - "https://huggingface.co/$REPO/resolve/main/$MMPROJ" -o "$MMPROJ"

# 3) сервис
cat > /etc/systemd/system/openagent-llm.service <<EOP
[Unit]
Description=OpenAgent local LLM (Qwen3.5-2B, llama.cpp)
After=network-online.target

[Service]
WorkingDirectory=$DIR
Environment=LD_LIBRARY_PATH=$DIR/llama
ExecStart=$DIR/llama/llama-server -m $DIR/$QUANT --mmproj $DIR/$MMPROJ --host 127.0.0.1 --port 8080 --alias qwen3.5-2b -c 16384 -t $(nproc) --parallel 1 --jinja --chat-template-kwargs '{"enable_thinking":false}'
Restart=always
RestartSec=3
Nice=5

[Install]
WantedBy=multi-user.target
EOP
systemctl daemon-reload && systemctl enable --now openagent-llm

# 4) подключение к OpenAgent
grep -q '^LOCAL_LLM_URL=' $APP/.env || printf '\n# Локальная модель (Qwen3.5-2B): чат, документы, фото. Code остаётся на river.ai\nLOCAL_LLM_URL=http://127.0.0.1:8080/v1\nLOCAL_LLM_MODEL=qwen3.5-2b\nLOCAL_LLM_VISION=1\n' >> $APP/.env
systemctl restart openagent
echo "Готово. Проверка: curl -s localhost:8080/health ; журнал: journalctl -u openagent-llm -f"
