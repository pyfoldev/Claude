#!/usr/bin/env bash
# Veil VPN — установка сервера (Ubuntu 20.04+/Debian 11+). Запуск: sudo bash install.sh
# Необязательные переменные: WG_PORT=51820  ENDPOINT=<ip или домен>
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Запустите от root: sudo bash install.sh"; exit 1; }

PORT="${WG_PORT:-51820}"
SUBNET="10.66.66"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq wireguard-tools qrencode iptables curl python3 unbound >/dev/null

IFACE="$(ip -4 route show default | awk '{print $5; exit}')"
ENDPOINT="${ENDPOINT:-$(curl -4 -fsS --max-time 8 https://api.ipify.org || true)}"
[ -n "$ENDPOINT" ] || { echo "Не удалось определить IP. Задайте: ENDPOINT=1.2.3.4 bash install.sh"; exit 1; }

install -d -m 700 /etc/veil /etc/wireguard
install -m 755 "$(dirname "$0")/vpnctl" /usr/local/bin/vpnctl
install -m 755 "$(dirname "$0")/veil-adblock" /usr/local/bin/veil-adblock

if [ ! -f /etc/wireguard/wg0.conf ]; then
  umask 077
  SK="$(wg genkey)"
  cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = ${SUBNET}.1/24
ListenPort = ${PORT}
PrivateKey = ${SK}
SaveConfig = false
PostUp = iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT; iptables -t nat -A POSTROUTING -s ${SUBNET}.0/24 -o ${IFACE} -j MASQUERADE; iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
PostDown = iptables -D FORWARD -i wg0 -j ACCEPT; iptables -D FORWARD -o wg0 -j ACCEPT; iptables -t nat -D POSTROUTING -s ${SUBNET}.0/24 -o ${IFACE} -j MASQUERADE; iptables -t mangle -D FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
EOF
fi
cat > /etc/veil/server.env <<EOF
ENDPOINT=${ENDPOINT}
PORT=${PORT}
SUBNET=${SUBNET}
DNS=${SUBNET}.1
MTU=1380
EOF
chmod 600 /etc/veil/server.env

# Скорость и стабильность: форвардинг + BBR
cat > /etc/sysctl.d/99-veil.conf <<EOF
net.ipv4.ip_forward=1
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
net.core.rmem_max=4194304
net.core.wmem_max=4194304
EOF
sysctl --system >/dev/null || true

# Приватный DNS: собственный резолвер, без сторонних провайдеров и без логов
cat > /etc/unbound/unbound.conf.d/veil.conf <<EOF
server:
    interface: ${SUBNET}.1
    ip-freebind: yes
    access-control: ${SUBNET}.0/24 allow
    access-control: 0.0.0.0/0 refuse
    do-ip6: no
    qname-minimisation: yes
    hide-identity: yes
    hide-version: yes
    use-caps-for-id: yes
    prefetch: yes
    cache-min-ttl: 300
    verbosity: 0
    log-queries: no
    log-replies: no
    use-syslog: no
    logfile: ""
    include: /etc/unbound/veil-blocklist.conf
EOF
[ -f /etc/unbound/veil-blocklist.conf ] || : > /etc/unbound/veil-blocklist.conf
systemctl enable --now unbound >/dev/null 2>&1 || true
systemctl restart unbound || true

# Блокировщик рекламы и трекеров (DNS), обновление раз в неделю
cat > /etc/systemd/system/veil-adblock.service <<EOF
[Unit]
Description=Update Veil ad/tracker blocklist
[Service]
Type=oneshot
ExecStart=/usr/local/bin/veil-adblock update
EOF
cat > /etc/systemd/system/veil-adblock.timer <<EOF
[Unit]
Description=Weekly Veil blocklist update
[Timer]
OnCalendar=weekly
Persistent=true
RandomizedDelaySec=1h
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now veil-adblock.timer >/dev/null 2>&1 || true
/usr/local/bin/veil-adblock update || echo "Блоклист не загружен, повторите: sudo veil-adblock update"

# Без логов
systemctl disable --now systemd-journald-audit.socket >/dev/null 2>&1 || true

command -v ufw >/dev/null && ufw status | grep -q active && { ufw allow "${PORT}/udp" >/dev/null; ufw route allow in on wg0 >/dev/null || true; }

systemctl enable --now wg-quick@wg0 >/dev/null 2>&1
systemctl restart wg-quick@wg0

echo
echo "Готово. Сервер: ${ENDPOINT}:${PORT}/udp  (откройте этот порт в файрволе хостера)"
echo "Создайте клиента:   sudo vpnctl add phone"
