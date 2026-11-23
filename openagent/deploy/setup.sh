#!/usr/bin/env bash
# Запускать НА СЕРВЕРЕ (Ubuntu/Debian, root): bash setup.sh
# Ставит Node 22, Caddy (HTTPS), JDK 17 + Android SDK (чтобы агент собирал APK), сервис openagent.
set -euo pipefail
DOMAIN="${DOMAIN:-openagents.duckdns.org}"
APP=/opt/openagent
SRC="$(cd "$(dirname "$0")/.." && pwd)"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y curl ca-certificates gnupg git unzip zip build-essential python3 openjdk-17-jdk-headless rsync jq poppler-utils ripgrep graphviz python3-pip ffmpeg tesseract-ocr tesseract-ocr-rus antiword catdoc sqlite3 python3-numpy python3-scipy python3-sympy python3-matplotlib python3-pandas fonts-dejavu-core debian-keyring debian-archive-keyring apt-transport-https
# библиотеки для создания/правки документов (docx, xlsx, pptx, pdf)
pip3 install --break-system-packages -q python-docx openpyxl python-pptx reportlab xlrd pypdf || true

# Node 22
if ! command -v node >/dev/null || [ "$(node -v | cut -d. -f1 | tr -d v)" -lt 22 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

# Caddy
if ! command -v caddy >/dev/null; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -y && apt-get install -y caddy
fi

# GitHub CLI (необязательно, но удобно агенту)
if ! command -v gh >/dev/null; then
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /usr/share/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list
  apt-get update -y && apt-get install -y gh
fi

# Android SDK
export ANDROID_HOME=/opt/android-sdk
if [ ! -d "$ANDROID_HOME/cmdline-tools/latest" ]; then
  mkdir -p "$ANDROID_HOME/cmdline-tools"
  curl -fsSL -o /tmp/clt.zip https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
  unzip -q /tmp/clt.zip -d "$ANDROID_HOME/cmdline-tools" && mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
fi
yes | "$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" --licenses >/dev/null || true
"$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager" "platforms;android-35" "build-tools;35.0.0" "platform-tools"
cat > /etc/profile.d/android.sh <<EOP
export ANDROID_HOME=$ANDROID_HOME
export ANDROID_SDK_ROOT=$ANDROID_HOME
export PATH=\$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools
EOP

# Приложение
mkdir -p $APP /srv/openagent/data /srv/openagent/workspaces
rsync -a --delete --exclude node_modules --exclude .env "$SRC/server/" $APP/
(cd $APP && npm install --omit=dev --no-audit --no-fund)
if [ -f "$SRC/server/.env" ] && [ ! -f $APP/.env ]; then
  cp "$SRC/server/.env" $APP/.env; chmod 600 $APP/.env
fi
if [ ! -f $APP/.env ]; then
  cp $APP/.env.example $APP/.env
  sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$(openssl rand -hex 32)|" $APP/.env
  sed -i "s|^PUBLIC_URL=.*|PUBLIC_URL=https://$DOMAIN|" $APP/.env
  chmod 600 $APP/.env
  echo ">>> Заполни ключи: nano $APP/.env  затем: systemctl restart openagent"
fi

cat > /etc/systemd/system/openagent.service <<EOP
[Unit]
Description=OpenAgent server
After=network-online.target

[Service]
WorkingDirectory=$APP
EnvironmentFile=-/etc/profile.d/android.sh
Environment=ANDROID_HOME=$ANDROID_HOME
ExecStart=/usr/bin/node --env-file-if-exists=$APP/.env src/index.js
Restart=always
RestartSec=3
KillMode=process

[Install]
WantedBy=multi-user.target
EOP

PORT=$(grep -E '^PORT=' $APP/.env | cut -d= -f2); PORT=${PORT:-8787}
cat > /etc/caddy/Caddyfile <<EOP
$DOMAIN {
    encode zstd gzip
    request_body {
        max_size 2GB
    }
    reverse_proxy 127.0.0.1:$PORT {
        flush_interval -1
        transport http {
            read_timeout 0
        }
    }
}
EOP

systemctl daemon-reload
systemctl enable --now openagent caddy
systemctl restart openagent caddy
sleep 2
curl -fsS http://127.0.0.1:$PORT/health && echo " — сервер работает: https://$DOMAIN"
