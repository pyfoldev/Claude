# Хендлеры: как писать и подключать

Шаблоны: `templates/` (см. `templates/README.md`). Быстрый старт: `python tools/new_handler.py pets --kind text`.

## Анатомия модуля `handlers/<имя>.py`

```python
router = Router(name="<имя>")                       # 1. роутер
COOLDOWN = 5                                         # 2. константы — вверху, с комментариями
_RE = re.compile(r"^команда\s+(.+)$", re.I)          # 3. регулярки команд
@router.message(F.text.func(lambda t: ...))          # 4. фильтр = «когда срабатывать»
async def cmd(message: Message, bot, db): ...        # 5. параметры подставляются по имени из dp[...]
```

## Какие параметры можно получить в хендлере

Всё, что положено в `dp["имя"]` в `main.py`: `db`, `ai`, `http`, `rt`, `owner_ids`, `webapp_url`, `premium_price`,
`imagegen`, `detector`, `metrics`, `uq`… Плюс стандартные aiogram: `bot`, `event_from_user`. Свой объект — шаг 2.2 в `main.py`.
Middleware могут добавлять свои (например `nori_addressed` из `NoriPrefixMiddleware`).

## Типы фильтров (частые)

| Нужно | Пишем |
|---|---|
| Точная фраза | `@router.message(F.text.lower() == "меню")` |
| Одна из фраз | `F.text.lower().in_({"меню", "команды"})` |
| Регулярка | `F.text.func(lambda t: bool(t) and _RE.match(t.strip()))` |
| Слэш-команда | `Command("menu", "help")` |
| Только личка | `F.chat.type == "private"` |
| Только группы | `F.chat.type.in_({"group", "supergroup"})` |
| Нажатие кнопки | `@router.callback_query(F.data.startswith("префикс:"))` |
| Вход участника | `ChatMemberUpdatedFilter(JOIN_TRANSITION)` (см. `handlers/captcha.py`) |
| Своё условие | класс-`Filter` (`templates/custom_filter_template.py`) |
| Вся группа вкл/выкл | `router.message.filter(Enabled("ключ_on"))` |

## Порядок = приоритет

Роутеры проверяются по порядку в `ROUTERS` (`main.py`). Хендлер, который «съел» сообщение, останавливает цепочку.
Поэтому: узкие команды выше, универсальные (`ИИ`) — самыми последними. Актуальный порядок: `docs/ROUTERS.md`.
Если нужно, чтобы хендлер пропустил сообщение дальше (не «съел» его) — вызовите `raise SkipHandler` (`from aiogram.dispatcher.event.bases import SkipHandler`)
или сделайте фильтр уже, чтобы он не срабатывал.

## Права

```python
rank = await ms.effective_rank(bot, db, chat_id, user_id)   # 0..5
ok, why = await ms.can_act(bot, chat_id, actor, target, "can_restrict_members", db, "команда")
```
Ранги и ДК — `docs/SETTINGS_AND_RANKS.md`.

## Как отвечать

`ux.tell` (замечание автору) · `ux.tell_cb` (ответ на кнопку) · `ux.react` (реакция) · `message.reply/answer` (публично).
Оформление — `style.*` (`docs/STYLE_GUIDE.md`).

## Callback-кнопки

`callback_data` ≤ 64 байт, формат `префикс:действие:владелец:аргумент`. Всегда `await cb.answer()`. Проверяйте,
что нажал тот, кому предназначено (`templates/inline_menu_template.py`). Префиксы разных модулей не должны пересекаться —
перед выбором выполните `grep -rn 'startswith("мойпрефикс' bot/`.

## Типичные ошибки

- Забыли подключить роутер в `main.py` → `python tools/check_project.py` покажет.
- Ответ ИИ/ввод пользователя без `html.escape` → «can't parse entities».
- Новый ключ настройки не заведён в `DEFAULT_SETTINGS` → `KeyError`.
- Кэш-словарь растёт бесконечно → добавьте в `rollup_loop`.
