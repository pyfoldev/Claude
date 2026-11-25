# Техплан: «Команда агентов» — Android-мессенджер с автономными ИИ-агентами

Версия 0.1 · 2026-11-25 · статус: черновик на согласование

## 0. Суть продукта

Android-приложение, похожее на мессенджер. Вы — основатель компании. Внутри — команда ИИ-агентов:

- **Главный агент** (секретарь / chief of staff). Единственный, кто пишет вам напрямую по умолчанию.
- **Агенты-помощники**, у каждого роль, промпт, внешность, набор инструментов, модель и бюджет.
- Вы ставите задачу главному, он раздаёт её по помощникам, собирает отчёты и приходит к вам за решениями и разрешениями.
- Всё исполняется **на вашем сервере**, а не на телефоне. Телефон может быть выключен, агенты продолжают работать, а результат придёт пушем.

Дополнительно: 100+ коннекторов (Google, Gmail, Calendar и др.), диктовка, голосовые звонки агентам, выбор провайдера и модели.

## 1. Что подтверждено документацией

Читал документацию 2026-11-25. Источники: docs.river.ai, developers.deepgram.com.

### 1.1 River AI (`river.ai`)

- Это API для обучения и инференса LLM. Инференс есть, он **OpenAI-совместимый**.
- Base URL: `https://api.river.ai/v1`. Эндпоинты: `POST /chat/completions`, `POST /responses`, `GET /models`.
- Авторизация: `Authorization: Bearer rv_...`. Ключ создаётся в console.river.ai/keys, хранить только на сервере.
- Поддерживаются streaming (SSE), function calling (`tools`, `tool_choice`), `response_format` (json_schema), `reasoning_effort`, `stream_options.include_usage`.
- Модели только open-weight: Kimi K3 / K3.1 Pro, DeepSeek V4.1 Flash, GLM-5.3 / 5.3 Flash, Qwen3.8-27B, Nemotron 3.5 Super. Актуальный список берём через `GET /v1/models`.
- Цены (превью-тарифы): DeepSeek V4.1 Flash $0.12 / $0.48 за 1M токенов (вход / выход), GLM-5.3 Flash $0.12 / $0.40, GLM-5.3 $1.12 / $3.52.
- Следствие: River подключается как ещё один OpenAI-совместимый провайдер, отдельного адаптера не нужно.

**Нужно уточнить.** Правильно ли я понял «River AI» как river.ai? Если вы имели в виду другой сервис, скажите.

### 1.2 Deepgram: диктовка (STT)

| Модель | Эндпоинт | Для чего | Цена (PAYG, мин) |
|---|---|---|---|
| `nova-3` | `wss://api.deepgram.com/v1/listen` | Диктовка. 55+ языков, `language=ru` или `multi`. Нет детекции конца реплики. | $0.0048 моно, $0.0058 multi |
| `flux-general-en` | `wss://api.deepgram.com/v2/listen` | Только английский, встроенная детекция конца реплики. | $0.0065 |
| `flux-general-multi` | `wss://api.deepgram.com/v2/listen` | 10 языков, включая русский. | $0.0078 |

- Flux работает **только** на `/v2/listen` и отдаёт события `StartOfTurn`, `Update`, `EagerEndOfTurn`, `TurnResumed`, `EndOfTurn`.
- Параметры Flux: `eot_threshold` 0.5–1.0, `eager_eot_threshold` 0.3–0.9, `eot_timeout_ms`.
- Аудио: linear16, 16 кГц, чанки около 80 мс.
- Авторизация: `Authorization: Token <key>`. Для клиентов выдаём временный токен через `POST /v1/auth/grant` (по умолчанию TTL 30 секунд).

**Решение по диктовке:** Nova-3 для диктовки в поле ввода, потому что нужен непрерывный текст, а не диалоговые реплики. Flux используется внутри голосовых звонков. Если вы имели в виду именно Flux для диктовки, это одна строка в настройках.

### 1.3 Deepgram Voice Agent (голосовые звонки)

- Эндпоинт: `wss://agent.deepgram.com/v1/agent/converse`.
- Порядок: ждём `Welcome` → шлём `Settings` → ждём `SettingsApplied` → шлём бинарное PCM-аудио.
- В `Settings` три блока:
  - `listen` — Deepgram `nova-3`, `flux-general-en` или `flux-general-multi` (для русского нужен multi).
  - `think` — LLM.
  - `speak` — TTS (Deepgram Flux TTS / Aura-2, Cartesia, ElevenLabs, OpenAI, Polly).
- **Управляемые LLM** (ключ не нужен, оплата через Deepgram):
  - `anthropic`: `claude-sonnet-5`, `claude-sonnet-4-6`, `claude-sonnet-4-5`, **`claude-haiku-4-5`**, `claude-3-5-haiku-latest`.
  - `open_ai`: `gpt-5.x`, `gpt-4.1`, `gpt-4o` и мини-версии.
  - `google`: `gemini-3.5-flash`, `gemini-3.1-flash-lite` и др.
  - `nvidia`, `deepgram` (ранний доступ).
  - Актуальный список: `GET https://agent.deepgram.com/v1/agent/settings/think/models`.
- **Свой ключ (BYO)**: добавляем `think.endpoint {url, headers}`. Так можно подключить River (`type: open_ai`, URL River) или собственный бэкенд.
- Можно задать массив `think` и `speak`. Это fallback по порядку.
- Функции: клиентские (`FunctionCallRequest` → `FunctionCallResponse`) и серверные (с `endpoint`).
- Управление в ходе звонка: `UpdatePrompt`, `UpdateThink`, `UpdateSpeak`, `InjectAgentMessage`, `InjectUserMessage`, `KeepAlive`, `ForceEndTurn`.
- События: `ConversationText`, `UserStartedSpeaking` (для barge-in), `AgentAudioDone`, `Error` и `Warning`.

**Не подтверждено:**
- Цена Voice Agent за минуту. Страницу тарифов в разделе Voice Agent я не нашёл.
- Какие русские голоса есть у TTS (Aura-2, Flux TTS, Cartesia). Это главный риск для русскоязычных звонков, проверим в Фазе 0.
- Формат заголовка авторизации у agent-сокета. Скорее всего `Token <key>`, проверим на живом соединении.
- Дефолтная частота входного аудио: страницы расходятся (16000 против 24000). Всегда задаём явно.

### 1.4 Haiku 4.5

Для звонков по умолчанию `type: anthropic`, `model: claude-haiku-4-5`. Этот ID есть в списке управляемых моделей Deepgram.

## 2. Архитектура

```
┌─────────────────┐   WSS + REST (JWT)    ┌───────────────────────────── ВАШ СЕРВЕР ─────────────────────────────┐
│ Android-клиент  │◄─────────────────────►│  API Gateway (Caddy/TLS) → Core API (TypeScript, Fastify)            │
│ Kotlin/Compose  │◄── FCM push ──────────│   ├ Messaging (диалоги, статусы, вложения)                           │
│ - чаты          │                       │   ├ Org Engine (агенты, иерархия, делегирование, бюджеты)            │
│ - диктовка      │                       │   ├ Agent Runtime (цикл агента, провайдеры LLM, инструменты)         │
│ - звонок        │                       │   ├ Approval Service (запросы разрешений)                            │
└─────────────────┘                       │   ├ Scheduler (cron, события, будильники агентов)                    │
        │ аудио 16/24 кГц                 │   ├ Connector Hub (OAuth, vault, 100+ интеграций)                    │
        ▼                                 │   ├ Voice Gateway (прокси к Deepgram: dictation + Voice Agent)       │
  Voice Gateway ──────────────────────────┼──►wss://agent.deepgram.com/v1/agent/converse                       │
                                          │   └ Sandbox Manager (Docker-контейнеры на агента)                    │
                                          │  PostgreSQL · Redis (очереди, pub/sub) · MinIO/диск (файлы)          │
                                          └──────────────────────────────────────────────────────────────────────┘
```

### 2.1 Выбор стека

| Слой | Выбор | Почему |
|---|---|---|
| Android | Kotlin + Jetpack Compose, MVVM, Hilt, Room (кэш), OkHttp WebSocket | Нативный аудиоввод/вывод, foreground-сервис для звонка, FCM, `ConnectionService` для «настоящего» звонка |
| Бэкенд | TypeScript, Node 22, Fastify, Zod | Единый язык с протоколами, зрелые SDK Anthropic/OpenAI, удобный WebSocket |
| БД | PostgreSQL 16 + pgvector | Память агентов (векторный поиск), транзакции, очередь через `pg-boss` или BullMQ на Redis |
| Очереди/события | Redis + BullMQ | Фоновые задачи агентов, расписание, pub/sub для WebSocket |
| Файлы | Диск сервера + MinIO (S3-совместимо) | Артефакты агентов, вложения чата |
| Деплой самой платформы | Docker Compose, Caddy (авто-TLS) | Просто, воспроизводимо |
| Доступ | Домен + Caddy либо Cloudflare Tunnel или Tailscale | Сервер не обязан иметь открытые порты |

Оговорка: серверный язык не фиксирован. Если вы лучше знаете Python, цикл агента и коннекторы так же хорошо пишутся на нём. Скажите, если предпочитаете.

### 2.2 Компоненты бэкенда

**Messaging.** Диалог — это поток сообщений. Типы: `user`, `agent`, `system`, `approval_request`, `task_update`, `artifact`. Есть статусы доставки, вложения, ответы на сообщение, реакции. Клиент получает события через WebSocket, а если приложение закрыто, то через FCM-пуш с ID сообщения. Тексты в пуш не кладём.

**Org Engine.** Организационная модель:
- `Workspace` → `Agent` (роль, system prompt, аватар, модель, инструменты, бюджет, `parent_agent_id`).
- Один агент помечен `is_chief = true`.
- Главный агент владеет инструментами делегирования: `create_agent`, `delegate_task`, `list_team`, `ask_owner`, `report_status`.
- Помощники отчитываются родителю. С вами напрямую они говорят только через родителя, если вы не разрешили иное.

**Agent Runtime.** Один «ход» агента — это цикл: собрать контекст → вызвать LLM → выполнить tool calls → повторить до финала. Особенности:
- Работает как фоновый воркер, не привязан к соединению телефона.
- Состояние хранится в БД: можно приостановить на ожидании разрешения и продолжить после ответа.
- Лимиты: максимум шагов, токенов, денег на задачу и на день.
- Сжатие контекста и долговременная память (pgvector): факты о вас, заметки, итоги задач.
- Параллельное выполнение нескольких помощников.

**Provider Layer.** Единый интерфейс `LLMProvider.stream(messages, tools, opts)` с адаптерами:

| Адаптер | Покрывает |
|---|---|
| `anthropic` | Claude (Opus/Sonnet/Haiku), нативный Messages API |
| `openai-compatible` | OpenAI, **River** (`https://api.river.ai/v1`), OpenRouter, Groq, свои vLLM |
| `google` | Gemini |

- Каталог моделей в БД, выбор на уровне агента. Модель можно сменить без пересоздания агента.
- Ключи провайдеров хранятся в хранилище секретов (см. раздел 6).
- Учёт стоимости по каждому вызову, так как River и остальные возвращают usage.
- Tool calling приводим к общему формату, чтобы агент не зависел от провайдера.

**Approval Service.** Каждый инструмент имеет уровень риска:

| Уровень | Примеры | Политика |
|---|---|---|
| `read` | чтение файлов, поиск, чтение почты | Автоматически |
| `write-local` | запись в рабочую папку агента | Автоматически |
| `write-external` | отправка письма, создание события, пост в соцсети | Спрашивать (можно «всегда разрешать для этого агента») |
| `system` | деплой, установка пакетов, запуск сервисов | Спрашивать, показывать точную команду |
| `destructive` / `money` | удаление, оплата, ротация ключей | Всегда спрашивать, без «запомнить» |

Запрос приходит в чат как карточка с кнопками «Разрешить / Отклонить / Разрешить всегда». Таймаут и действие по умолчанию задаются. Цепочка: помощник просит родителя, родитель либо решает сам в рамках своих прав, либо эскалирует вам.

**Scheduler.** Cron и события («каждое утро в 8:00 собери сводку почты», «когда пришло письмо от X»). Планировщик запускает ход агента, ваш телефон не нужен.

**Sandbox Manager.** Подробности в разделе 3.

**Voice Gateway.** Подробности в разделе 5.

### 2.3 Модель данных (основное)

```
users(id, email, ...)               devices(id, user_id, fcm_token, public_key)
workspaces(id, owner_id)
agents(id, workspace_id, parent_id, name, role, avatar, system_prompt, model_id, is_chief,
       tool_policy jsonb, budget_daily_usd, status)
conversations(id, workspace_id, kind[direct|group|task], participants[])
messages(id, conversation_id, sender_type, sender_id, type, content jsonb, created_at)
tasks(id, workspace_id, assigner_id, assignee_id, parent_task_id, title, brief, status,
      due_at, result_ref)
runs(id, agent_id, task_id, status, steps, tokens_in, tokens_out, cost_usd, started_at, ended_at)
tool_calls(id, run_id, tool, args jsonb, risk, status, approval_id, result jsonb)
approvals(id, run_id, requester_agent_id, tool_call_id, summary, risk, status, decided_at)
schedules(id, agent_id, cron, prompt, enabled)
memories(id, agent_id, scope, text, embedding vector, source_id)
connectors(id, workspace_id, provider, account_label, secret_ref, scopes, status)
secrets(id, name, ciphertext, key_id)
audit_log(id, actor, action, target, details jsonb, created_at)
```

## 3. Доступ агентов к серверу

Цель: агенты могут деплоить, сохранять файлы, запускать задачи без вашего телефона, но не получают полный root-доступ к хосту.

### 3.1 Уровни изоляции

1. **Рабочая область агента.** Каждому агенту свой том `/workspaces/<agent_id>`. Файловые инструменты ограничены этим путём. Общая папка `/shared` для обмена артефактами.
2. **Песочница выполнения.** Команды агента выполняются в отдельном Docker-контейнере (без `--privileged`, непривилегированный пользователь, лимиты CPU/RAM/диска/времени, сеть по allowlist). Контейнер создаётся на сессию задачи и уничтожается, том остаётся.
3. **Брокер деплоя.** Для деплоя агент не получает Docker-сокет. Он вызывает инструмент `deploy(service, ref)`, а небольшой привилегированный сервис-брокер:
   - принимает только предопределённые операции (`docker compose up` для зарегистрированных проектов, обновление Caddy-конфига, перезапуск сервиса),
   - проверяет, что операция одобрена,
   - пишет запись в журнал аудита.
4. **Сеть.** Исходящий трафик из песочницы через прокси с allowlist доменов. Новые домены запрашиваем через approval.
5. **Хост.** Платформа работает от отдельного пользователя, не root. Брокер — единственный компонент с повышенными правами, и его код маленький и проверяемый.

### 3.2 Набор серверных инструментов

`fs_read`, `fs_write`, `fs_list`, `fs_search`, `shell_exec` (в песочнице), `git_*`, `http_fetch` (через прокси), `deploy`, `service_status`, `service_logs`, `cron_schedule`, `process_start/stop` (в песочнице), `browser_*` (headless Chromium в отдельном контейнере для веб-задач).

### 3.3 Автономность

- Долгие задачи идут как фоновые runs в очереди, с чекпоинтами. После рестарта сервера run продолжается.
- Прогресс отправляется в чат как `task_update`. Уведомление приходит только по значимым событиям (нужно решение, завершено, ошибка).

## 4. Коннекторы (100+)

Вы просили не «безымянные MCP-серверы», а полноценные коннекторы: красивый каталог, подключение одной кнопкой через OAuth, понятные права.

### 4.1 Подход

Два слоя:

1. **Нативные коннекторы** для ядра (пишем сами, полный контроль над scope, качеством и UX): Google (Gmail, Calendar, Drive, Docs, Sheets, Contacts, Tasks), GitHub, Telegram, Notion, Slack, Microsoft 365 (Outlook, OneDrive, Teams), Dropbox.
2. **Длинный хвост через агрегатор** (кандидаты: Composio, Nango, Pipedream Connect). Они дают управляемый OAuth и сотни интеграций, мы подключаем их за единым интерфейсом. Это я ещё не исследовал по документации, оценю в Фазе 0 по критериям: цена, self-host, хранение токенов у нас, количество готовых интеграций.

Внутри все коннекторы выглядят одинаково:

```
Connector { id, name, category, auth: oauth2|apikey|none,
            scopes[], tools: [{name, schema, risk}], triggers? }
```

Каждый инструмент коннектора размечен уровнем риска (раздел 2.2), поэтому отправка письма всегда идёт через approval, а чтение — нет. Для MCP-серверов тоже есть мост, но каталог «первого класса» — это наши коннекторы.

Права выдаются **на агента**: помощнику-бухгалтеру можно дать Sheets и Gmail (только чтение), помощнику-SMM — только соцсети.

### 4.2 Каталог 100+ (целевой список)

**Google (10):** Gmail, Calendar, Drive, Docs, Sheets, Slides, Contacts, Tasks, Meet, YouTube.
**Microsoft (7):** Outlook, Outlook Calendar, OneDrive, Teams, SharePoint, Excel, To Do.
**Почта и календари (5):** IMAP/SMTP, iCloud Calendar (CalDAV), Calendly, Cal.com, Fastmail.
**Мессенджеры (10):** Telegram, WhatsApp Business, Slack, Discord, Signal (через мост), Viber, Messenger, SMS (Twilio), Zoom, Mattermost.
**Документы и знания (9):** Notion, Confluence, Obsidian (файлы), Evernote, Coda, Airtable, Dropbox, Box, Google Keep.
**Задачи и проекты (10):** Linear, Jira, Asana, Trello, ClickUp, Monday, Todoist, Basecamp, Height, Shortcut.
**Разработка (12):** GitHub, GitLab, Bitbucket, Sentry, Vercel, Netlify, Cloudflare, Docker Hub, AWS, DigitalOcean, Hetzner, npm.
**CRM и продажи (9):** HubSpot, Salesforce, Pipedrive, amoCRM, Bitrix24, Zoho CRM, Close, Apollo, Intercom.
**Маркетинг и соцсети (10):** X (Twitter), LinkedIn, Instagram, Facebook Pages, Mailchimp, SendGrid, Buffer, Google Ads, Meta Ads, Google Analytics.
**Финансы и платежи (9):** Stripe, PayPal, QuickBooks, Xero, Wise, Tinkoff/T-Bank, Revolut, Plaid, CoinGecko.
**Поддержка (5):** Zendesk, Freshdesk, Help Scout, Crisp, Front.
**E-commerce (6):** Shopify, WooCommerce, Wildberries, Ozon, Etsy, Amazon Seller.
**Данные и аналитика (8):** Postgres, MySQL, BigQuery, Snowflake, Metabase, Mixpanel, PostHog, Supabase.
**ИИ и медиа (8):** Fish Audio (TTS, уже подключён к этой среде), ElevenLabs, Replicate, Hugging Face, Figma, Canva, Spotify, YouTube Music.
**Поиск и веб (6):** Brave Search, Tavily, Exa, Firecrawl, Browserbase, Wikipedia.
**Утилиты и умный дом (6):** Погода, Карты, Home Assistant, Яндекс.Карты, Яндекс.Диск, VK.

Итого около 130. Порядок реализации: в MVP нативные Google и несколько ключевых, остальное по волнам (раздел 8).

### 4.3 Хранение и безопасность токенов

OAuth-токены шифруются (envelope encryption), хранятся только на вашем сервере, в промпт никогда не попадают. Агент вызывает инструмент по ID коннектора, токен подставляет Connector Hub.

## 5. Голос

### 5.1 Диктовка

```
Android (AudioRecord, 16 кГц PCM16, ~80 мс) → WS /voice/dictate → Voice Gateway → Deepgram nova-3
                                                  ◄ interim/final текст в поле ввода ◄
```

- Телефон открывает WebSocket к **вашему серверу**, а не к Deepgram. Ключ Deepgram остаётся на сервере.
- Альтернатива для меньшей задержки: сервер выдаёт временный токен (`/v1/auth/grant`), клиент подключается напрямую. Оставляем как оптимизацию.
- Режимы: нажал-и-держи и «свободная диктовка». Промежуточные результаты подсвечиваются серым, финальные становятся текстом.
- Язык по умолчанию `ru`, режим `multi` для смешанной речи. Ключевые слова (`keyterms`) подставляем из имён ваших агентов и проектов.

### 5.2 Голосовые звонки

Звонок идёт **через сервер**, а не напрямую в Deepgram. Причины: ключи не на телефоне, серверные инструменты и память агента доступны сразу, звонок можно записать и расшифровать в чат.

```
Android (микрофон/динамик, PCM) ◄── WS ──► Voice Gateway ◄── WS ──► Deepgram Voice Agent
                                                │
                                                └─ FunctionCallRequest → Agent Runtime → FunctionCallResponse
```

- На звонок выбираем агента. Gateway собирает `Settings`:
  - `agent.think.prompt` из system prompt агента плюс сжатый контекст, свежие задачи, память;
  - `agent.listen`: `flux-general-multi` для русского (английский: `flux-general-en`);
  - `agent.think.provider`: по умолчанию `{type: anthropic, model: claude-haiku-4-5}`;
  - `agent.speak`: управляемый TTS Deepgram или Cartesia, голос на агента (после проверки русских голосов);
  - `agent.greeting`.
- **Выбор модели в приложении**: список из `GET /v1/agent/settings/think/models` (Anthropic, OpenAI, Google и др., оплата через Deepgram, свой ключ не нужен). Опция «свой ключ / River»: `think.endpoint` на `https://api.river.ai/v1`, `type: open_ai`. Для fallback задаём массив `think`.
- **Инструменты в звонке.** Голосовой агент не тяжёлый исполнитель. Он вызывает клиентские функции: `delegate_to_team(task)`, `get_status()`, `ask_agent(agent, question)`, `remember(note)`, `end_call()`. Тяжёлую работу делает Agent Runtime в фоне, а в чат приходит итог. Так звонок остаётся быстрым на Haiku.
- Barge-in: по `UserStartedSpeaking` клиент немедленно очищает буфер воспроизведения.
- Android: foreground-сервис с типом `microphone`, аудиофокус, Bluetooth-гарнитура, эхоподавление (`VOICE_COMMUNICATION` источник), `KeepAlive` каждые несколько секунд.
- Расшифровка (`ConversationText`) пишется в чат, в итоге звонка добавляется резюме.
- Учёт: длительность звонка и стоимость по минутам показываем в статистике.

## 6. Безопасность

- **Аутентификация:** вход на телефоне (passkey или e-mail + код), токены короткоживущие (JWT 15 мин) + refresh, привязка к устройству. Единственный владелец в MVP.
- **Транспорт:** только TLS. Рассмотреть Tailscale/WireGuard как дополнительный закрытый путь.
- **Секреты:** envelope-шифрование (ключ в файле/KMS вне БД), ключи провайдеров и токены коннекторов в хранилище, в логи и промпты не попадают.
- **Prompt injection:** содержимое писем, веб-страниц и файлов помечается как недоверенные данные. Любое внешнее действие после чтения недоверенного контента идёт через approval, даже если для агента оно «всегда разрешено».
- **Бюджеты и лимиты:** дневной бюджет на агента и на workspace, лимит шагов, автоматическая пауза и уведомление при превышении.
- **Аудит:** журнал всех вызовов инструментов и решений по approval, доступен в приложении.
- **Kill switch:** кнопка «остановить всех агентов» в приложении и на сервере.
- **Резервные копии:** ежедневный дамп БД и томов, шифрованный, вне сервера.

## 7. Android-приложение: экраны

1. **Список чатов** (как в мессенджере): главный агент закреплён сверху, помощники, групповые чаты, неподтверждённые approvals с бейджем.
2. **Чат**: пузыри, вложения, карточки `approval_request`, карточки задач со статусом, индикатор «агент печатает / работает», поле ввода с микрофоном (диктовка) и кнопкой звонка.
3. **Создание агента**: имя, роль, внешность (аватар/цвет), описание задачи, модель, коннекторы и инструменты, уровни разрешений, бюджет, расписание. Мастер: можно просто описать словами, а главный агент сам предложит конфигурацию.
4. **Команда / оргструктура**: дерево «главный → помощники», статус каждого, текущая задача, расход за день.
5. **Задачи**: общая доска, фильтры по агентам, детали с историей шагов.
6. **Коннекторы**: каталог по категориям, подключение, права по агентам.
7. **Статистика**: токены, деньги, время, успешность по агентам, звонки.
8. **Звонок**: экран разговора с волной, мьют, динамик, выбор модели, расшифровка.
9. **Настройки**: провайдеры и ключи, сервер, уведомления, безопасность, журнал аудита.

Дизайн и UI-кит делаем после ваших референсов.

## 8. План работ по фазам

| Фаза | Содержание | Результат |
|---|---|---|
| **0. Проверки (2–3 дня)** | Живые пробы Deepgram (Flux multi на русском, Voice Agent: заголовок авторизации, русский TTS, цена), River (список моделей, tool calling), выбор агрегатора коннекторов, согласование стека | Список рисков закрыт, ADR-записи |
| **1. Ядро (≈2 недели)** | Docker Compose, БД, Auth, Messaging + WebSocket + FCM, Provider Layer (Anthropic, OpenAI-compatible/River, Gemini), базовый Agent Runtime | Чат с одним агентом на сервере, пуши |
| **2. Команда (≈2 недели)** | Org Engine, главный агент, `create_agent`, `delegate_task`, отчёты, Approval Service, задачи, бюджеты | Главный агент создаёт и ведёт помощников, спрашивает разрешения |
| **3. Сервер (≈2 недели)** | Sandbox Manager, файловые инструменты, shell в песочнице, брокер деплоя, Scheduler, аудит | Агенты работают автономно, деплоят |
| **4. Коннекторы (≈3 недели)** | Connector Hub, vault, нативные Google (Gmail/Calendar/Drive/Docs/Sheets), каталог в приложении, агрегатор, волны по 15–20 интеграций | 30+ коннекторов, затем наращивание до 100+ |
| **5. Голос (≈2 недели)** | Диктовка (Nova-3), Voice Gateway, звонки (Voice Agent, Haiku 4.5), выбор модели, функции делегирования | Диктовка и звонки |
| **6. Полировка (≈2 недели)** | Дизайн по референсам, статистика, память, kill switch, бэкапы, нагрузочные тесты | Бета |

Сроки ориентировочные для одного разработчика с моей помощью и зависят от дизайна.

## 9. Риски

| Риск | Что делаем |
|---|---|
| Русский язык в Voice Agent (STT или TTS) может быть слабым | Проба в Фазе 0, запасные TTS-провайдеры (Cartesia/ElevenLabs через BYO) |
| Цена звонков не подтверждена | Проверить на странице тарифов, поставить лимиты минут |
| Агент с доступом к серверу сделает что-то разрушительное | Песочница, брокер, approvals, бэкапы, kill switch |
| Prompt injection через почту и веб | Пометка недоверенных данных, approvals на внешние действия |
| Лимиты и политика Google OAuth (проверка приложения для чувствительных scope) | Для личного использования режим «testing» подходит, для публикации нужна верификация |
| Android убивает фон (Doze) | Вся логика на сервере, телефон только клиент и пуши FCM, high-priority для approvals |
| Документация Deepgram местами противоречива | Всё критичное проверяем живыми запросами |
| Рост стоимости токенов при многоагентной работе | Бюджеты, дешёвые модели для помощников (River/Haiku), кэширование промптов |

## 10. Вопросы к вам

1. **River AI** — это river.ai (open-weight модели через OpenAI-совместимый API)? Если нет, пришлите ссылку.
2. **Диктовка:** Nova-3 (моя рекомендация) или Flux? Основной язык русский?
3. **Сервер:** ОС, ресурсы (CPU/RAM/диск), есть ли публичный IP и домен? Docker уже стоит?
4. **Стек бэкенда:** TypeScript устраивает или предпочитаете Python?
5. **Пользователи:** только вы, или потом мультипользовательность / продажа другим?
6. **Агрегатор коннекторов:** готовы платить за сервис вроде Composio/Nango или хотите всё self-host?
7. **Распространение:** только APK для себя или Google Play?
8. **Референсы дизайна** — жду, когда будут.
