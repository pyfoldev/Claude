"""ШАБЛОН: свой HTTP-маршрут (например, для веб-панели). Подключается в bot/panel_server.py → add_panel_routes().

Как устроена панель: все маршруты /api/... идут через middleware `guard` (проверка подписи Telegram WebApp, лимит
запросов, единый формат ошибок). Пользователь доступен как request[UID]. Образец — функция `me` в panel_server.py.

Шаги:
  1) добавьте функцию ниже внутрь add_panel_routes (ей доступны db, bot, ctx);
  2) зарегистрируйте:  r.add_get("/chats/{cid}/notes", notes_get)   (рядом с остальными r.add_*);
  3) фронтенд — webapp/panel.js (вызов API) и webapp/panel.html (разметка).
"""
from aiohttp import web

# --- вставить функцию notes_get внутрь add_panel_routes(app, ctx); обёртка ниже — чтобы файл был валидным Python ---
UID = rank_in = db = None  # заглушки: в panel_server.py эти имена уже есть


def add_panel_routes(app, ctx):

    async def notes_get(request: web.Request):
        uid = request[UID]                                   # id пользователя, проверенный по подписи Telegram
        cid = int(request.match_info["cid"])
        if await rank_in(cid, uid) < 1:                      # проверка прав в этом чате (как в других маршрутах)
            return web.json_response({"error": "forbidden"}, status=403)
        return web.json_response({"notes": await db.note_list(cid)})
