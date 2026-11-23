#!/usr/bin/env bash
# Запускать С КОМПЬЮТЕРА: ./deploy/deploy.sh root@114.29.238.123
# Копирует server/ и deploy/ на сервер и запускает setup.sh (ключ SSH лучше пароля: ssh-copy-id).
set -euo pipefail
HOST="${1:?usage: deploy.sh user@host}"
cd "$(dirname "$0")/.."
rsync -az --delete --exclude node_modules --exclude data server deploy "$HOST:/root/openagent-src/"
ssh "$HOST" "bash /root/openagent-src/deploy/setup.sh"
