# Веб-панель, капча, конкурсы (Mini App)

Бэкенд: `aiohttp` внутри бота (порт `PORT`, по умолчанию 8080), наружу — через Caddy (`Caddyfile`) по HTTPS.
Фронтенд — статика в `webapp/`.

| Часть | Бэкенд | Фронтенд |
|---|---|---|
| Капча | `captcha_server.py` | `webapp/index.html`, `captcha.js`, `style.css` |
| Веб-панель админа/владельца | `panel_server.py` (`add_panel_routes`) | `webapp/panel.html`, `panel.js`, `panel.css` |
| Конкурсы | `giveaway_server.py` | `webapp/giveaway.html`, `.js`, `.css` |
| Иконки / переводы | — | `webapp/icons.js`, `webapp/i18n.js` |

## Безопасность (не ломайте)
- Все API панели проходят `guard` в `panel_server.py`: проверка подписи Telegram WebApp (`initData`), лимиты запросов, единый формат ошибок.
- Права в чате проверяются заново на каждый запрос (`rank_in(cid, uid)`).
- `TRUSTED_PROXY_IPS` — только от этих IP принимается `X-Forwarded-For`.
- В Caddy наружу открыты только нужные пути (`/captcha`, `/panel`, `/giveaway`, `/webapp`, `/webhook`).

## Добавить API-метод панели
`templates/web_route_template.py` → функция внутри `add_panel_routes` + `r.add_get/post(...)` + вызов из `panel.js`.

## Добавить пункт в панель
1. Метод API (см. выше) и метод БД. 2. Разметка — `panel.html`. 3. Логика — `panel.js`. 4. Перевод — `i18n.js`.

## Как открыть из чата
Кнопка `web_app=` работает только в личке: `handlers/webpanel.py`; из группы ведёт ссылка в личку бота.
