# Чек-лист новой функции

- [ ] Файл `bot/handlers/<имя>.py` с `router = Router(name="<имя>")`
- [ ] Импорт и `router` добавлены в `bot/main.py` (список `ROUTERS`, выше `ai_handlers`)
- [ ] Права: `effective_rank` / `need_rank`; в личке и в группе ведёт себя правильно
- [ ] Включатель группы (`toggles.GROUPS` + `DEFAULT_SETTINGS`), если админ должен уметь выключить
- [ ] Кулдауны/лимиты (константы вверху файла), кэши очищаются в `rollup_loop`
- [ ] Тексты через `style.*` / `ux.tell`; весь пользовательский ввод экранирован `html.escape`
- [ ] SQL только в `db.py`, параметры через `?`; деньги — в `db.atomic()`
- [ ] Строка в справке: `handlers/menu.py` → `SECTION_DATA`
- [ ] Перевод/алиасы: `i18n.py` (если нужен английский)
- [ ] Новые переменные: `config.py` + `.env.example`
- [ ] Тест на парсер команды (`tests/`)
- [ ] `python tools/check_project.py` — зелёный
- [ ] Запись в `CHANGELOG.md`
