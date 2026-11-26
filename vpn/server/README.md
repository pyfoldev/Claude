# Veil VPN — сервер

WireGuard (ядро Linux) + собственный DNS (unbound, без логов). Нужен VPS с Ubuntu/Debian и публичным IP.

```bash
tar xzf veil-server.tar.gz && cd veil-server
sudo bash install.sh          # опционально: WG_PORT=443 ENDPOINT=vpn.example.com
sudo vpnctl add phone         # выдаст ссылку vpn://… и QR
```
В приложении Veil: «Сервер» → вставить ссылку → «Сохранить» → кнопка питания.

Откройте UDP-порт (по умолчанию 51820) в файрволе хостера.
`vpnctl list | show <имя> | remove <имя>` — управление клиентами.

Приватность: нет логов подключений, DNS-запросы обрабатываются на вашем сервере, у каждого клиента свои ключи + preshared key, IPv6 заблокирован на клиенте (нет утечек).

## Блокировщик рекламы и трекеров
Работает на уровне DNS сервера (список StevenBlack, ~80 тыс. доменов), действует для всех клиентов и приложений, обновляется раз в неделю.
`sudo veil-adblock update` — обновить сейчас · `sudo veil-adblock off` — выключить · `sudo systemctl enable --now veil-adblock.timer` + `veil-adblock update` — включить снова.
