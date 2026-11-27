# Короткие команды: `make help`
.PHONY: help check test run pyz new

help:        ## показать команды
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/ —/'

check:       ## проверить целостность проекта
	python tools/check_project.py

test:        ## автотесты (нужен pytest)
	python -m pytest -q

run:         ## локальный запуск (нужен .env с BOT_TOKEN, MODE=polling)
	python -m bot.main

pyz:         ## собрать bot.pyz для Dockerfile (рядом с docker-compose.yml)
	python -m zipapp . -o ../bot.pyz

new:         ## новый модуль команд: make new NAME=pets KIND=text
	python tools/new_handler.py $(NAME) --kind $(or $(KIND),text)
