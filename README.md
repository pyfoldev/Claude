# Стайка

Команда ИИ-агентов в мессенджере: Android-приложение + свой сервер.

- `server/` — сервер на Go (Postgres, Docker). Запуск и настройка: `server/README.md`.
- `android/` — приложение (Kotlin, Jetpack Compose). Адрес сервера вводится в самом приложении.
- `docs/PLAN.md` — технический план и решения.
- `staika-debug.apk` — собранное приложение для установки.

## Быстрый старт

1. На сервере: `cd server && cp .env.example .env`, заполнить, `docker compose up -d --build`.
2. Установить `staika-debug.apk`, указать адрес сервера, зарегистрироваться.
3. Создать первого агента (он станет главным) и написать ему.

## Сборка приложения

```bash
cd android
echo "sdk.dir=/путь/к/Android/Sdk" > local.properties
./gradlew :app:assembleDebug        # app/build/outputs/apk/debug/app-debug.apk
./gradlew :app:testDebugUnitTest    # скриншоты экранов в app/build/shots
```
