# Заметки к выпуску (читает агент после обновления)
Этот файл я обновляю при каждом изменении сервера. Если что-то нужно сделать руками (новые ключи в .env, миграции) — это написано здесь.

## Сервер v11 — обновление из GitHub
- Ничего делать не нужно: код обновляется командой `openagent-update`, `.env`, `data/` и `workspaces/` не затрагиваются.
- Необязательно, для Gmail/Календаря: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` в `/opt/openagent/.env` (см. README).
- Необязательно, для мгновенного обновления: вебхук GitHub на `/hooks/deploy` (секрет — `DEPLOY_WEBHOOK_SECRET` в `.env`, его создаёт `install-autoupdate.sh`).
- Файл телефона для оффлайн-режима: `/srv/openagent/data/models/phone-gguf/` (части `phone.gguf.partNN` из `dist/phone-gguf/` репозитория).
