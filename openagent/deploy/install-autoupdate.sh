#!/usr/bin/env bash
# Один раз на сервере (root): настраивает обновление из GitHub без архивов.
#   DEPLOY_REPO=https://github.com/pyfoldev/Claude.git DEPLOY_BRANCH=ccr-a3a4ce88-j9zjtg DEPLOY_TOKEN=github_pat_... bash install-autoupdate.sh
# DEPLOY_TOKEN — fine-grained токен GitHub с правом только «Contents: Read-only» на этот репозиторий (github.com/settings/personal-access-tokens).
# Что делает: ставит команду openagent-update, таймер systemd (проверка каждые 3 минуты), секрет для мгновенного обновления по вебхуку GitHub.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
: "${DEPLOY_REPO:?нужен DEPLOY_REPO}"; : "${DEPLOY_TOKEN:?нужен DEPLOY_TOKEN}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"; APP="${APP:-/opt/openagent}"
command -v rsync >/dev/null || apt-get install -y rsync
mkdir -p /etc/openagent /var/lib/openagent-deploy
install -m 755 "$HERE/update.sh" /usr/local/bin/openagent-update
[ -f /etc/openagent/targets.conf ] || cp "$HERE/targets.conf.example" /etc/openagent/targets.conf
SECRET="$(grep -E '^DEPLOY_WEBHOOK_SECRET=' "$APP/.env" 2>/dev/null | cut -d= -f2- || true)"; SECRET="${SECRET:-$(openssl rand -hex 24)}"
umask 077
cat > /etc/openagent/deploy.env <<EOP
DEPLOY_REPO=$DEPLOY_REPO
DEPLOY_BRANCH=$DEPLOY_BRANCH
DEPLOY_TOKEN=$DEPLOY_TOKEN
EOP
chmod 600 /etc/openagent/deploy.env
# вебхук GitHub → сервер OpenAgent (мгновенное обновление после каждого push)
if [ -f "$APP/.env" ]; then
  for kv in "DEPLOY_WEBHOOK_SECRET=$SECRET" "DEPLOY_BRANCH=$DEPLOY_BRANCH"; do k="${kv%%=*}"; grep -q "^$k=" "$APP/.env" && sed -i "s|^$k=.*|$kv|" "$APP/.env" || echo "$kv" >> "$APP/.env"; done
fi
cat > /etc/systemd/system/openagent-update.service <<'EOP'
[Unit]
Description=OpenAgent: обновление из GitHub
[Service]
Type=oneshot
ExecStart=/usr/local/bin/openagent-update
EOP
cat > /etc/systemd/system/openagent-update.timer <<'EOP'
[Unit]
Description=OpenAgent: проверка обновлений каждые 3 минуты
[Timer]
OnBootSec=2min
OnUnitActiveSec=3min
[Install]
WantedBy=timers.target
EOP
systemctl daemon-reload && systemctl enable --now openagent-update.timer
echo; echo "Первое обновление:"; /usr/local/bin/openagent-update || true
PUB="$(grep -E '^PUBLIC_URL=' "$APP/.env" 2>/dev/null | cut -d= -f2- || true)"
cat <<EOP

Готово. Команды:  openagent-update  |  openagent-update --check  |  openagent-update --status
Файлы:            /etc/openagent/deploy.env (репозиторий, токен), /etc/openagent/targets.conf (что куда ставить — добавьте сюда своих ботов)
Автообновление:   таймер проверяет GitHub каждые 3 минуты.
Мгновенно (необязательно): GitHub → Settings → Webhooks → Add webhook:
   Payload URL  ${PUB:-https://ВАШ-ДОМЕН}/hooks/deploy
   Content type application/json
   Secret       $SECRET
   События      Just the push event
Затем перезапустите сервер: systemctl restart openagent
EOP
