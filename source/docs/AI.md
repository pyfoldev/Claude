# ИИ в боте

Все вызовы — через `AiClient` (`bot/ai.py`, объект `ai` в хендлерах). Провайдеры настраиваются в `.env`.

| Возможность | Ключи `.env` | Где в коде |
|---|---|---|
| Ответы «ии, вопрос» / «нори, …» | `RIVER_API_KEY`, `RIVER_MODEL` | `handlers/ai.py` → `ai.ask`, `ask_stream` |
| «Живое» общение в чате | то же + настройка чата `ai_chat` | `chatmind.py`, `middlewares/memory.py` |
| ИИ-модерация текста | `RIVER_API_KEY`, настройка `ai_mod` | `aimod.py`, `ai.moderate` |
| Проверка картинок 18+ (2-е мнение) | `RIVER_VISION_MODEL` | `nsfw.py`, `ai.vision_is_nsfw` |
| Расшифровка голосовых | `MISTRAL_API_KEY` или `GIGAAM_URL` | `ai.transcribe` |
| Рисование «нарисуй» | `CF_ACCOUNT_ID`, `CF_API_TOKEN` | `imagegen.py` |
| Выбор модели (Premium) | `AI_MODELS` | `handlers/premium.py` |

## Выключатели
- нет ключа → `ai.has_river == False`: функции тихо выключены (в логе — «RIVER_API_KEY не задан»);
- владелец: `rt.flag("ai")`, `rt.flag("stt")`, `rt.flag("aimod")`, `rt.flag("nsfw")`;
- админ чата: настройки `ai_on`, `ai_mod`, `ai_chat`, `transcribe_on`.

## Как править промпты
- Системные промпты — константы в `ai.py` (`MOD_SYSTEM`, `VISION_SYSTEM`) и рядом с командами (`handlers/ai.py`, `chatmind.py`).
- В любом промпте пользовательский текст объявляйте **данными, а не инструкциями** — защита от prompt-injection.
- Ответ ИИ всегда экранируйте (`html.escape`), если шлёте в HTML-режиме.

## Как добавить свою команду с ИИ
`templates/ai_command_template.py`. Помните про `AiError`, таймауты (`TIMEOUT`, `MOD_TIMEOUT`) и ограничение длины входа.
