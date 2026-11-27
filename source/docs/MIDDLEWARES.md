# Middleware (прослойки)

Middleware выполняются **до** хендлеров, сверху вниз в порядке регистрации (`main.py`, раздел 2.3).

| # | Middleware | Тип | Зачем | Файл |
|---|---|---|---|---|
| 1 | `MetricsMiddleware` | update | замеряет время обработки | `metrics.py` |
| 2 | `BlockMiddleware` | update | блок-лист, режим обслуживания | `middlewares/blocklist.py` |
| 3 | `UserTrackerMiddleware` | update | запоминает людей, чаты, участников | `middlewares/tracker.py` |
| 4 | `CounterMiddleware` | message | счётчик сообщений (статистика) | `middlewares/counter.py` |
| 5 | `GuardMiddleware` | message, edited | антиспам, 18+, фишинг, стоп-слова | `middlewares/guard.py` |
| 6 | `RateLimitMiddleware` | message | защита бота от залпа команд | `middlewares/ratelimit.py` |
| 7 | `RulesMiddleware` | message | правила чата, триггеры, FAQ | `middlewares/rules.py` |
| 8 | `MembershipMiddleware` | chat_member | фейс-контроль, быстрый выход | `middlewares/rules.py` |
| 9 | `QuietTopicMiddleware` | message | «тихие» темы форума | `middlewares/quiet.py` |
| 10 | `ChatMemoryMiddleware` | message | память чата для ИИ | `middlewares/memory.py` |
| 11 | `NoriPrefixMiddleware` | message | «нори, <команда>» | `middlewares/prefix.py` |
| 12 | `CommandAliasMiddleware` | message | английские команды | `i18n.py` |

**Почему именно такой порядок:** блок-лист — до всего; счётчик — до защиты (считает и удалённое); память ИИ — после защиты
(спам не запоминается); префикс «нори» — предпоследним (защита видит исходный текст); алиасы — последним.

## Как работает

```python
async def __call__(self, handler, event, data):
    ...                                  # что-то до хендлера
    if нужно_остановить: return None     # событие не дойдёт дальше
    data["x"] = 1                        # добавить параметр хендлерам
    return await handler(event, data)    # пропустить дальше
```

## Как добавить

1. Скопируйте `templates/middleware_template.py` → `middlewares/<имя>.py`.
2. В `main.py`: импорт + `dp.message.outer_middleware(Имя(db))` в нужном месте списка.
3. Помните: middleware видят КАЖДОЕ сообщение — делайте быстро, тяжёлое кэшируйте, ошибки ловите (`try/except`), чтобы учёт не ронял обработку.
