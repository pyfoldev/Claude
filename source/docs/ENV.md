<!-- АВТОГЕНЕРАЦИЯ: tools/gen_docs.py. Не редактируйте вручную. -->

# Переменные окружения

Источник: `.env.example`. Читаются в `bot/config.py`.

| Переменная | Пример / по умолчанию | Описание |
|---|---|---|
| `BOT_TOKEN` | `123456:replace-me` |  |
| `WEBAPP_URL` | `https://bot.example.com` |  |
| `OWNER_ID` | `0` | ваш Telegram id (узнать у @userinfobot); можно несколько через запятую: 123,456 |
| `WEBHOOK_SECRET` | `change-me-long-random` |  |
| `WEBHOOK_URL` | `—` | куда Telegram шлёт обновления в режиме webhook: https://домен:88 (порты 443, 80, 88, 8443); по умолчанию — WEBAPP_URL |
| `DB_PATH` | `data/bot.db` |  |
| `MODE` | `polling` | webhook | polling |
| `UPDATE_WORKERS` *(необязательно)* | `64` | сколько обновлений Telegram обрабатывается одновременно в режиме webhook (по умолчанию 64) |
| `PORT` | `8080` | порт встроенного веб-сервера (капча + webhook) |
| `RIVER_API_KEY` | `—` | --- ИИ и расшифровка (необязательно: без ключей эти функции выключены) --- |
| `RIVER_MODEL` | `deepseek-ai/DeepSeek-V4.1-Flash` |  |
| `RIVER_VISION_MODEL` *(необязательно)* | `—` | модель для второго мнения по сомнительным картинкам (по умолчанию Nemotron VL); работает, только если в чате включено «ИИ-проверка сомнительных» |
| `MISTRAL_API_KEY` | `—` |  |
| `MISTRAL_STT_MODEL` | `voxtral-mini-latest` |  |
| `GIGAAM_URL` | `—` | URL своего GigaAM, например http://172.18.0.1:8792; пусто — расшифровка выключена |
| `CF_ACCOUNT_ID` | `—` | --- генерация картинок: Cloudflare Workers AI (бесплатно в рамках суточного лимита Workers AI) --- dash.cloudflare.com → Workers AI → «Use REST API»: Account ID и API-токен с правом Workers AI |
| `CF_API_TOKEN` | `—` |  |
| `CF_IMAGE_MODEL` *(необязательно)* | `@cf/black-forest-labs/flux-1-schnell` |  |
| `YTDLP_COOKIES` *(необязательно)* | `/data/cookies.txt` | --- скачивание из соцсетей (yt-dlp) --- необязательно: путь к cookies.txt (формат Netscape) для Instagram/YouTube, которые часто требуют вход. Лучше завести отдельный аккаунт, а не свой основной. Файл положить в ./data (он смонтирован в контейнер как /data). |
| `PREMIUM_PRICE` | `70` | --- Nori Premium (подписка за звёзды Telegram, 30 дней, автопродление) --- |
| `AI_MODELS` *(необязательно)* | `deepseek-ai/DeepSeek-V4.1-Flash,Qwen/Qwen3-235B-A22B` | модели ИИ на выбор для Premium через запятую; пусто — бот сам берёт список у River (GET /models) |
| `TRUSTED_PROXY_IPS` *(необязательно)* | `127.0.0.1` | IP доверенных reverse proxy через запятую; только от них панель принимает X-Forwarded-For. |
| `POSTGRES_PASSWORD` *(необязательно)* | `—` | Для профиля pg задайте собственный пароль: PostgreSQL не запустится с пустым. |
| `DATABASE_URL` *(необязательно)* | `—` | --- дополнительно (необязательно) --- PostgreSQL вместо SQLite: postgresql://chat:ПАРОЛЬ@postgres:5432/chat (запуск: docker compose --profile pg up -d) |
| `RIVER_BASE_URL` *(необязательно)* | `https://api.river.ai/v1` | адрес и модель для River-совместимого API ИИ (по умолчанию см. bot/config.py) |
| `RIVER_CHAT_VISION_MODEL` *(необязательно)* | `—` | модель для «живого» общения с картинками |
| `MISTRAL_BASE_URL` *(необязательно)* | `https://api.mistral.ai/v1` | Mistral: адрес API (для расшифровки голосовых) |
