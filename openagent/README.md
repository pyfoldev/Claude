# OpenAgent

ИИ-агент с телефона: чёрный минималистичный клиент (Kotlin/Compose) + сервер (Node.js), на котором агент
работает как Claude Code — терминал, файлы, git/GitHub, сборка APK.

| Что | Чем |
|---|---|
| Движок Code | **opencode** (`opencode serve`, MIT) — цикл агента, инструменты, сжатие контекста; модели river.ai; инструменты OpenAgent (сайты, файлы, документы, графики, поиск, память) подключены через MCP (`ocMcp.js`). Сайты и интерфейсы — через **OpenDesign** (навык `opendesign`: 150+ дизайн-систем, шаблоны, правила ремесла; ставится в `/opt/opendesign`) |
| Провайдеры | river.ai (по умолчанию), **kie.ai** (адаптер протоколов: Claude/GPT-6/Grok/Gemini/DeepSeek/Kimi), **Puter**, **Dahl Inference**, **Cohere**, **Vyce AI**, Coarena, UnoRouter, Groq, Perplexity и любой OpenAI-совместимый («Свой»). Ключи — в `.env` (см. `.env.example`) или в приложении |
| Движок Чат | **Vercel AI SDK** (`ai`) — цикл модель↔инструменты со стримингом; инструменты выполняет OpenAgent |
| Модель | river.ai (OpenAI-совместимый `/chat/completions`, стриминг, tool calls) |
| Голосовой режим | **Deepgram Voice Agent**: распознавание `nova-3` + мозг **Claude Haiku 4.5** + голос **Flux «Владимир»** в одном потоке (`/api/voice-agent`); сложное агент делегирует функцией `run_task` полному агенту OpenAgent |
| Речь → текст | Deepgram (`nova-3`) или **GigaAM Multilingual 600M** на CPU сервера (`deploy/setup-stt.sh`, `STT_ENGINE=gigaam`) |
| Голос «GigaAM + Flux» | второй режим звонка (выбор в окне звонка): GigaAM распознаёт → модель отвечает → Deepgram Flux («Владимир») озвучивает |
| Текст → речь | Fish Audio (`/v1/tts`) |
| Вход | код на e-mail через Brevo SMTP или Google; капча Cloudflare Turnstile |
| Память | SQLite: факты + эмбеддинги `mistral-embed` + BM25 (FTS5), гибридный поиск, слияние дублей, вытеснение; резюме длинных чатов; `MEMORY.md` |
| GitHub | OAuth Device Flow или PAT; токен подставляется агенту как `GITHUB_TOKEN`/`gh` |

## Деплой сервера
```bash
./deploy/deploy.sh root@114.29.238.123      # или скопировать папку и запустить на сервере: bash deploy/setup.sh
nano /opt/openagent/.env                      # ключи (см. .env.example)
systemctl restart openagent
```
Скрипт ставит Node 22, Caddy (HTTPS для `openagents.duckdns.org`), JDK 17 + Android SDK, `gh`, systemd-сервис.
Домен должен указывать на IP сервера, порты 80/443 открыты.

## Оффлайн-режим: модель управления телефоном
Приложение (Настройки → Оффлайн-режим) скачивает модель команд телефону с вашего сервера по `/models/phone.gguf`. Чат (Ministral 3 3B) оно качает само с Hugging Face.
1. Скачайте из репозитория папку `dist/phone-gguf/` (9 файлов `phone.gguf.part00` … `part08`, всего 424 МБ) — репозиторий закрытый, поэтому с телефона они недоступны.
2. Положите их на сервер в `DATA_DIR/models/phone-gguf/` (по умолчанию `server/data/models/phone-gguf/`):
   `scp dist/phone-gguf/* user@сервер:/путь/к/data/models/phone-gguf/`
   Если сервер развёрнут из git-клона — достаточно `git pull`, сервер сам найдёт `dist/phone-gguf/`.
3. Перезапускать сервер не нужно. Проверка: `curl -sI https://ваш-сервер/models/phone.gguf` — должен быть `200` и `Content-Length: 444414816`.
Вместо частей можно положить один файл: `cat phone.gguf.part* > DATA_DIR/models/phone.gguf`. Либо в приложении кнопка «Файл…» — выбрать готовый `phone.gguf`.

## Агенты и коннекторы
- **Агенты** (приложение: инструменты → «Агенты»): у каждого своя задача, набор коннекторов, память-заметки и расписание (раз в N минут). Чат с агентом, запуск вручную, пауза. Шаблоны: дайджест новостей, секретарь почты, охотник за ценами, дежурный по GitHub, менеджер задач, умный дом и др.
- **Главный агент** — обычный чат: знает команду агентов, поручает им работу (`agent_ask`), по просьбе создаёт новых (`agent_save`: «заведи агента, который каждое утро собирает новости»).
- **Коннекторы** (инструменты → «Коннекторы»), 22 штуки: Telegram-бот, Slack, Discord, GitHub, GitLab, Notion, Linear, Todoist, Trello, Jira, Airtable, Home Assistant, календарь iCal (Google/Яндекс/Apple), ntfy-пуши, вебхуки (Zapier/Make/n8n), YouTube, Stripe, Vercel, Sentry, SMS Twilio. **Gmail и Google Календарь** подключаются кнопкой «Войти через Google» (OAuth): в Google Cloud создайте OAuth client ID типа «Web application», redirect URI `PUBLIC_URL/oauth/google/callback`, включите Gmail API и Google Calendar API, впишите `GOOGLE_OAUTH_CLIENT_ID` и `GOOGLE_OAUTH_CLIENT_SECRET` в `.env`; экран согласия переведите в «In production» (иначе доступ истекает через 7 дней). Тесты: `node test/google.mjs`. Ещё тысячи сервисов — через MCP («Подключения»).
- **Безопасность:** действия, которые меняют данные или что-то отправляют (✎), в чате требуют вашего «да»; автономный агент выполняет их только если включено «Разрешить действия». Токены лежат в базе сервера (`integrations`), клиенту не отдаются.
- API: `GET/POST/PATCH/DELETE /api/agents`, `POST /api/agents/:id/run|chat`, `GET /api/integrations`, `PUT/DELETE /api/integrations/:id`, `POST /api/integrations/:id/test`. Тесты: `node test/agents.mjs`, `node test/integrations.mjs` (без сети и модели).

## Что нужно заполнить в `.env`
- `OWNER_EMAILS` — ваш e-mail (только владелец получает shell на сервере).
- `RIVER_API_KEY`, `RIVER_BASE_URL`, `RIVER_MODEL`.
- `DEEPGRAM_API_KEY` (распознавание речи), `MISTRAL_API_KEY` (эмбеддинги памяти), `FISH_API_KEY` (+ `FISH_REFERENCE_ID` — id голоса).
- `SMTP_USER`, `SMTP_PASS`, `SENDER_EMAIL` (Brevo).
- `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET` — в панели Turnstile добавьте hostname `openagents.duckdns.org`.
- `GITHUB_CLIENT_ID` — GitHub → Settings → Developer settings → OAuth Apps, включить Device Flow.

## Вход через Google
В `app/google-services.json` есть только Web client ID. Для работы Credential Manager добавьте в Firebase/Google Cloud
**Android OAuth client** для `openagent.app.com` с SHA-1 вашего ключа подписи (`./gradlew signingReport`).

## Сборка приложения
`cd android && ./gradlew :app:assembleDebug` (нужен Android SDK) или workflow **OpenAgent APK** в GitHub Actions.
Адрес сервера — `SERVER_URL` в `app/build.gradle.kts`, меняется и в настройках приложения.

## Безопасность
Агент с shell на сервере = полный доступ к серверу. Доступ только у `OWNER_EMAILS`; остальные пользователи (`ALLOWED_EMAILS`)
работают без shell и только в своей папке. Не коммитьте `.env`.

## Возможности агента
- **Режимы Чат / Code.** Чат — ассистент с веб-поиском и памятью; Code — инженер с терминалом сервера, файлами, git, сборкой APK.
- **Инструменты:** bash (в т.ч. фон), read/write/edit, grep, glob, http_request, github_api, process, web_search/web_fetch,
  память, todo_write (план-чеклист), ask_user (вопрос с кнопками), delegate (параллельные под-агенты),
  навыки (skill_load/skill_save), автоматизации по расписанию (schedule_*), send_file.
- **Модели:** встроенный river.ai (+ выбор любой модели из `/models`) и свои OpenAI-совместимые провайдеры (ключи шифруются AES-GCM).
  «Усилие»: Быстро / Авто / Глубоко — влияет на `reasoning_effort` и лимит шагов.
- **Приложение:** файловый менеджер с редактором, терминал (владелец), автоматизации, навыки, память.

## Решение задач, визуализации, навыки с GitHub
- **Режим «Авто» для моделей:** картинка → vision-модель, Code → модель для кода, математика/задачи → модель-решатель, остальное → быстрая. Модели задаются в `.env` (`RIVER_CODE_MODEL`, `RIVER_SOLVE_MODEL`, `RIVER_VISION_MODEL`, `RIVER_FAST_MODEL`). Сравнение моделей: `node scripts/bench.mjs`.
- **Точные решения:** агент проверяет вычисления через `python` (sympy/numpy), `calculate`, подстановкой/вторым способом.
- **Визуализации:** инструменты `chart` (столбцы/линии/области/точки/круговые/гистограммы/таблицы), `plot_function` (функции и параметрические кривые), `geometry` (чертежи по координатам), `diagram` (Graphviz), `draw_svg` (любые схемы и рисунки), матплотлиб-графики из `python`. Картинки (SVG) открываются в чате с зумом.
- **Навыки и плагины с GitHub:** вкладка «Навыки → GitHub» — поиск и установка в один клик (SKILL.md, commands, agents), либо вставьте `owner/repo` или ссылку. Агент тоже умеет `skill_search` / `skill_install`.

## Экономия токенов (всегда включена)
Только дешёвые модели (DeepSeek Flash по умолчанию; GLM-5.3/Qwen/Kimi скрыты, список — `RIVER_ALLOWED_MODELS`), короткий системный промпт,
инструменты подбираются под запрос (в запрос уходит 4–12 вместо 35), лимиты `max_tokens`, жёсткая обрезка истории и результатов, мало шагов (8/20/45),
название чата без вызова модели, извлечение памяти только по явным фразам. Расход виден в Настройки → Расход токенов.

## Сайты и интерактив
`deploy_site` публикует статический сайт на `https://<домен>/s/<имя>/`, `html_app` — живое мини-приложение прямо в чате; превью в приложении (телефон/компьютер).
Интерактив: вопросы агента (один/несколько вариантов/текст), быстрые ответы, правка и повтор сообщений, слэш-команды `/`.

## Провайдеры
Свой провайдер: Модель → «Свой» → шаблон (Coarena, OpenRouter, DeepSeek, OpenAI) + ключ; подключение проверяется сразу, первая модель выбирается автоматически.
Coarena: база `https://coarena.ai/api/v1`, бесплатный ключ на https://coarena.ai/api; модели `gpt-6-luna`, `gemini-3-8-flash`, `deepseek-v4-1-flash-1017`.
Можно задать ключ на сервере: `COARENA_API_KEY=...` в `.env` — провайдер появится у всех без ввода ключа.

## Веб-поиск Exa
Укажите `EXA_API_KEY` в `/opt/openagent/.env` (ключ: https://dashboard.exa.ai/api-keys) — `web_search` будет использовать Exa: сразу возвращает ключевые фрагменты и текст страниц, поддерживает `category` (news, research paper, github, pdf…), `days` (только свежее) и `domains`. Без ключа или при ошибке работает запасной поиск (Tavily/Brave/Bing/DuckDuckGo).

## Сборка и плавность
Релизная сборка (`./gradlew :app:assembleRelease`) с R8 и baseline-профилями заметно плавнее debug. Debug-APK оставлен как запасной вариант.

## Тесты
```bash
cd server && npm ci
# нужен .env с ключами; данные тестов — во временной папке:
DATA_DIR=/tmp/oa/data WORKSPACES_DIR=/tmp/oa/ws node --env-file=.env test/tools.mjs                 # все инструменты напрямую (84 проверки)
DATA_DIR=... WORKSPACES_DIR=... node --env-file=.env test/run.mjs all                                # 10 задач Code + 10 задач Chat, живая модель
HARD=1 node --env-file=.env test/run.mjs all                                                         # сложные задачи (баги, поиск, графики)
STRESS=1 node --env-file=.env test/run.mjs code                                                      # многофайловые баги, git, сервер, npm test
ENVFILE=.env DATA_DIR=... WORKSPACES_DIR=... node --env-file=.env test/voice.mjs                     # голосовой цикл: Voice Agent + инструменты + реальный аудиопоток
```
Каждая задача проверяется скриптом (файлы/вывод) и лимитом шагов — видно, где агент делает лишнее.

## Движки
- Code: `CODE_ENGINE=legacy` возвращает встроенный цикл; без opencode/для не-владельцев работает встроенный. Модель Code — `RIVER_CODE_MODEL`. Каталог OpenDesign — `OPENDESIGN_DIR` (по умолчанию `/opt/opendesign`, ставит `deploy/setup.sh`).
- Чат: `CHAT_ENGINE=legacy` — встроенный цикл. При сбое запуска движка до первого вывода агент автоматически переключается на встроенный.
- Тесты сайтов: `SITES=1 OPENDESIGN_DIR=... node --env-file=.env test/run.mjs code`.
