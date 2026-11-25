# Стайка: сервер

Go-сервер: аккаунты, агенты, чаты, цикл агента с инструментами и подтверждениями, расписания, мосты Deepgram.

## Запуск на сервере (Docker)

```bash
cd server
cp .env.example .env
# сгенерируйте секреты
echo "STAIKA_JWT_SECRET=$(openssl rand -base64 48)"
echo "STAIKA_MASTER_KEY=$(openssl rand -base64 48)"
nano .env            # вставьте секреты, пароль БД, ключи, домен, почту владельца
docker compose up -d --build
docker compose logs -f app
```

Проверка: `curl https://ВАШ_ДОМЕН/health` должен вернуть `{"status":"ok"}`.

Без домена (проверка по IP): оставьте `STAIKA_DOMAIN=:80` и в приложении укажите `http://IP_СЕРВЕРА`.
Для продакшена нужен домен и HTTPS: без TLS токены и голос идут открытым текстом.

## Первый вход

1. Откройте приложение, укажите адрес сервера, зарегистрируйтесь (почта STAIKA_OWNER_EMAIL получит роль owner).
2. Модели: если у вас роль owner/family, работают серверные ключи из `.env`. Остальным пользователям нужно добавить свои ключи в «Настройки → Провайдеры».
3. Роли других пользователей меняет владелец («Настройки → Пользователи»): member (свои ключи), family (серверные ключи), owner.

## Письма

Без `BREVO_API_KEY` коды входа не отправляются, а пишутся в лог: `docker compose logs app`. Для рабочей почты нужен домен отправителя с SPF/DKIM в Brevo.

## Вход через Google

В Google Cloud Console создайте OAuth client типа **Web** и укажите его ID в `STAIKA_GOOGLE_CLIENT_IDS`.
Для Android создайте ещё один client типа **Android** (пакет `app.staika`, SHA-1 подписи вашего APK).

## Песочница для команд (необязательно, опасно)

Инструмент `shell_exec` выключен по умолчанию. Чтобы включить: соберите образ песочницы (например `alpine`), задайте `STAIKA_SANDBOX_IMAGE`,
установите docker CLI в контейнер приложения и смонтируйте `/var/run/docker.sock`. Это даёт приложению права на уровне root хоста, включайте осознанно.
Команды всё равно доступны только роли owner, у агента должен быть включён доступ к серверу, и каждая команда требует вашего подтверждения.

## Резервные копии

```bash
docker compose exec db pg_dump -U staika staika > backup.sql
docker run --rm -v server_workspaces:/w -v $PWD:/b alpine tar czf /b/workspaces.tgz -C /w .
```
Сохраните также `STAIKA_MASTER_KEY`.

## Разработка и тесты

```bash
go test -race ./...                                  # на SQLite
STAIKA_TEST_PG='postgres://user@host/db?sslmode=disable' go test ./internal/httpapi   # на PostgreSQL
```
