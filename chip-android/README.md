# Chip

Android-чат с облачком Chip. Chip отвечает эмодзи и видео-кружками с эмоциями.
ИИ (river.ai) только выбирает одну из 12 готовых эмоций, видео не генерируется.

- `app/` Kotlin + Jetpack Compose. Кружки лежат в `app/src/main/res/raw/clip_*.mp4`.
- `Chip-debug.apk` готовая сборка для установки.
- `../tools/` рендер кружков из дизайна (`record.js`: Playwright + ffmpeg), `../design/` макет персонажа.
- Настройки river.ai (адрес API, ключ, модель) открываются шестерёнкой в чате. Без ключа Chip отвечает офлайн по ключевым словам.

Сборка: `./gradlew assembleDebug` (нужен Android SDK 34).
