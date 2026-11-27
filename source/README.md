# Chat Helper — исходники

Telegram-бот для чатов: модерация, защита, статистика, игры, РП/семья, ИИ, веб-панель.

## С чего начать
1. **Хочу понять проект** → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), затем открыть `bot/main.py` (размечен по шагам).
2. **Хочу что-то поменять/добавить** → [docs/COOKBOOK.md](docs/COOKBOOK.md) («хочу X → куда идти»).
3. **Хочу новую команду** → `python tools/new_handler.py имя --kind text` или шаблоны в [templates/](templates/README.md).
4. **Что-то сломалось** → [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) и `python tools/check_project.py`.
5. **Все гайды** → [docs/README.md](docs/README.md). Краткая карта — [EXTENDING.md](EXTENDING.md).

## Запуск локально
```bash
pip install -r ../requirements.lock
cp ../.env.example .env      # BOT_TOKEN, OWNER_ID, MODE=polling
python -m bot.main           # или: make run
```
Прод — [docs/DEPLOY.md](docs/DEPLOY.md).

## Структура
```
bot/          код бота (handlers/, middlewares/, db.py, main.py …)
webapp/       фронтенд Mini App (капча, панель, конкурсы)
templates/    шаблоны для копирования
docs/         гайды + автосправочники
tools/        генератор модулей, проверки, генератор доков
tests/        автотесты
```
