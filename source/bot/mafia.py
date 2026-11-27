"""Мафия: ведущий-бот для классической игры в группе (набор → роли в личке → ночь → день → голосование → итог).

Состояние игры живёт в памяти (игра идёт минуты; после перезапуска бота идущая игра прекращается). Всё, что решает ход игры
(роли, ночь, подсчёт голосов, победа), — обычные синхронные методы `Game`: их можно проверять без Telegram. Связь с Telegram — функции
`run_game` и вспомогательные ниже; команды и кнопки подключены в bot/handlers/mafia.py.

Роли: Мирный житель, Мафия, Дон (глава мафии), Доктор, Комиссар. Минимум 4 игрока: Дон, Доктор и двое мирных."""
from __future__ import annotations

import asyncio
import html
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from aiogram.types import FSInputFile, InlineKeyboardButton as B, InlineKeyboardMarkup

from bot.targets import mention

MIN_PLAYERS = 4
MAX_PLAYERS = 25
REG_SECONDS = 120          # сколько идёт набор, если ведущий не начал раньше
NIGHT_SECONDS = 60
DAY_SECONDS = 90           # обсуждение
VOTE_SECONDS = 45
CONFIRM_SECONDS = 25       # «Вы точно хотите линчевать?»
LAST_WORDS_MAX = 200
COUNTDOWN_STEP = 20
ASSETS = Path(__file__).with_name("assets") / "mafia"

ROLES = {
    "civ": ("Мирный житель", "👨🏼"),
    "mafia": ("Мафия", "🤵🏽"),
    "don": ("Дон", "🤵🏻"),
    "doc": ("Доктор", "👨🏼‍⚕️"),
    "com": ("Комиссар", "🕵🏼"),
}
MAFIA = {"mafia", "don"}
ROLE_ORDER = ("don", "mafia", "doc", "com", "civ")
ROLE_TEXT = {
    "civ": "Ты - {e} Мирный житель.\nТвоя задача вычислить мафию и на городском собрании линчевать засранцев",
    "don": "Ты - {e} Дон (глава мафии)!\nТебе решать кто не проснётся этой ночью...",
    "mafia": "Ты - {e} Мафия!\nТвоя задача - вместе с Доном избавиться от всех мирных жителей. По ночам вы голосуете за жертву.",
    "doc": "Ты - {e} Доктор!\nТебе решать кого спасти этой ночью...",
    "com": "Ты - {e} Комиссар!\nТебе решать кого проверить этой ночью: ты узнаешь, мафия это или нет.",
}


def role_name(role: str) -> str:
    return ROLES[role][0]


def role_plan(n: int) -> list[str]:
    """Набор ролей на n игроков: мафии n//4 (первая — Дон), Доктор, с 5 игроков — Комиссар, остальные — мирные."""
    if n < MIN_PLAYERS:
        raise ValueError("мало игроков")
    roles = ["don"] + ["mafia"] * (max(1, n // 4) - 1) + ["doc"]
    if n >= 5:
        roles.append("com")
    return roles + ["civ"] * (n - len(roles))


@dataclass
class Player:
    uid: int
    name: str
    num: int
    role: str = "civ"
    alive: bool = True
    can_speak: bool = False        # убит и ещё может прислать предсмертное сообщение


@dataclass
class Game:
    chat_id: int
    title: str
    host: int
    players: dict[int, Player] = field(default_factory=dict)
    phase: str = "reg"             # reg | night | day | vote | confirm | done
    day: int = 0
    created: float = field(default_factory=time.time)
    started: float = 0.0
    cancelled: bool = False
    # ночь
    mafia_votes: dict[int, int] = field(default_factory=dict)
    doc_pick: int | None = None
    com_pick: int | None = None
    last_heal: int | None = None
    # день
    votes: dict[int, int] = field(default_factory=dict)
    accused: int | None = None
    confirm: dict[int, bool] = field(default_factory=dict)
    # служебное
    reg_msg: int | None = None
    start_event: asyncio.Event = field(default_factory=asyncio.Event)
    step_event: asyncio.Event = field(default_factory=asyncio.Event)       # все нужные игроки сходили — фазу можно закончить
    task: asyncio.Task | None = None
    night_result: dict = field(default_factory=dict)

    # ----- игроки -----
    def mention(self, uid: int) -> str:
        return str(mention(uid, self.players[uid].name))

    def alive(self) -> list[Player]:
        return [p for p in self.players.values() if p.alive]

    def alive_ids(self, role: set[str] | None = None) -> list[int]:
        return [p.uid for p in self.alive() if role is None or p.role in role]

    def join(self, uid: int, name: str) -> str | None:
        """None — присоединился; иначе причина отказа."""
        if self.phase != "reg":
            return "Набор в игру уже закончен."
        if uid in self.players:
            return "Ты уже в игре."
        if len(self.players) >= MAX_PLAYERS:
            return f"В игре уже максимум игроков ({MAX_PLAYERS})."
        self.players[uid] = Player(uid, name or f"id{uid}", len(self.players) + 1)
        return None

    def leave(self, uid: int) -> bool:
        if self.phase != "reg" or uid not in self.players:
            return False
        del self.players[uid]
        for i, p in enumerate(self.players.values(), 1):
            p.num = i
        return True

    def assign(self, rnd: random.Random | None = None) -> None:
        rnd = rnd or random
        roles = role_plan(len(self.players))
        rnd.shuffle(roles)
        for p, r in zip(self.players.values(), roles):
            p.role = r
        self.started = time.time()

    # ----- ночь -----
    def begin_night(self) -> None:
        self.phase = "night"
        self.mafia_votes.clear()
        self.doc_pick = self.com_pick = None
        self.step_event.clear()

    def night_actors(self) -> list[int]:
        return [p.uid for p in self.alive() if p.role in MAFIA or p.role in ("doc", "com")]

    def night_options(self, uid: int) -> list[int]:
        """Кого можно выбрать этой ночью (пусто — роль без ночного действия)."""
        p = self.players.get(uid)
        if p is None or not p.alive:
            return []
        if p.role in MAFIA:
            return [x for x in self.alive_ids() if self.players[x].role not in MAFIA]
        if p.role == "doc":
            return [x for x in self.alive_ids() if x != self.last_heal]
        if p.role == "com":
            return [x for x in self.alive_ids() if x != uid]
        return []

    def night_pick(self, uid: int, target: int) -> str | None:
        """None — выбор принят; иначе причина отказа."""
        if self.phase != "night":
            return "Сейчас не ночь."
        p = self.players.get(uid)
        if p is None or not p.alive:
            return "Ты не в игре."
        if target not in self.night_options(uid):
            return "Этого игрока выбрать нельзя."
        if p.role in MAFIA:
            if uid in self.mafia_votes:
                return "Ты уже сделал выбор."
            self.mafia_votes[uid] = target
        elif p.role == "doc":
            if self.doc_pick is not None:
                return "Ты уже сделал выбор."
            self.doc_pick = target
        elif p.role == "com":
            if self.com_pick is not None:
                return "Ты уже сделал выбор."
            self.com_pick = target
        else:
            return "Ночью тебе делать нечего. Спи."
        self._check_night_done()
        return None

    def _check_night_done(self) -> None:
        mafia_done = all(u in self.mafia_votes for u in self.alive_ids(MAFIA))
        doc_done = all(self.doc_pick is not None for _ in self.alive_ids({"doc"}))
        com_done = all(self.com_pick is not None for _ in self.alive_ids({"com"}))
        if mafia_done and doc_done and com_done:
            self.step_event.set()

    def mafia_target(self, rnd: random.Random | None = None) -> int | None:
        """Жертва мафии: больше всего голосов; при равенстве решает Дон, а если его нет — случай."""
        if not self.mafia_votes:
            return None
        count: dict[int, int] = {}
        for t in self.mafia_votes.values():
            count[t] = count.get(t, 0) + 1
        top = max(count.values())
        tied = [t for t, n in count.items() if n == top]
        if len(tied) == 1:
            return tied[0]
        for uid, t in self.mafia_votes.items():
            if self.players[uid].role == "don" and t in tied:
                return t
        return (rnd or random).choice(tied)

    def resolve_night(self, rnd: random.Random | None = None) -> dict:
        """Итог ночи: {"victim": uid|None (выбранная мафией), "saved": bool, "killed": uid|None, "check": (uid, is_mafia)|None}."""
        victim = self.mafia_target(rnd)
        saved = victim is not None and victim == self.doc_pick
        killed = None if saved else victim
        check = None
        if self.com_pick is not None:
            check = (self.com_pick, self.players[self.com_pick].role in MAFIA)
        self.last_heal = self.doc_pick
        if killed is not None:
            self.kill(killed)
        self.day += 1
        return {"victim": victim, "saved": saved, "killed": killed, "check": check}

    def kill(self, uid: int) -> None:
        p = self.players[uid]
        p.alive = False
        p.can_speak = True

    # ----- день -----
    def begin_vote(self) -> None:
        self.phase = "vote"
        self.votes.clear()
        self.accused = None
        self.step_event.clear()

    def vote_options(self, uid: int) -> list[int]:
        return [x for x in self.alive_ids() if x != uid]

    def cast_vote(self, voter: int, target: int) -> str | None:
        if self.phase != "vote":
            return "Сейчас не голосование."
        p = self.players.get(voter)
        if p is None or not p.alive:
            return "Ты не в игре."
        if target not in self.vote_options(voter):
            return "Этого игрока выбрать нельзя."
        if voter in self.votes:
            return "Ты уже проголосовал."
        self.votes[voter] = target
        if all(u in self.votes for u in self.alive_ids()):
            self.step_event.set()
        return None

    def tally(self) -> int | None:
        """Кого линчевать: больше всего голосов у одного игрока; ничья или никто не голосовал — None."""
        if not self.votes:
            return None
        count: dict[int, int] = {}
        for t in self.votes.values():
            count[t] = count.get(t, 0) + 1
        top = max(count.values())
        tied = [t for t, n in count.items() if n == top]
        return tied[0] if len(tied) == 1 else None

    def begin_confirm(self, accused: int) -> None:
        self.phase = "confirm"
        self.accused = accused
        self.confirm.clear()
        self.step_event.clear()

    def confirm_voters(self) -> list[int]:
        return [u for u in self.alive_ids() if u != self.accused]

    def cast_confirm(self, voter: int, yes: bool) -> str | None:
        if self.phase != "confirm":
            return "Голосование уже закончено."
        if voter not in self.confirm_voters():
            return "Голосовать могут только живые игроки (кроме обвиняемого)."
        if voter in self.confirm:
            return "Ты уже проголосовал."
        self.confirm[voter] = yes
        if all(u in self.confirm for u in self.confirm_voters()):
            self.step_event.set()
        return None

    def confirm_result(self) -> tuple[int, int, bool]:
        yes = sum(1 for v in self.confirm.values() if v)
        no = len(self.confirm) - yes
        return yes, no, yes > no

    # ----- победа -----
    def winner(self) -> str | None:
        mafia = len(self.alive_ids(MAFIA))
        town = len(self.alive()) - mafia
        if mafia == 0:
            return "town"
        if mafia >= town:
            return "mafia"
        return None


# ---------- тексты ----------
def alive_list(g: Game) -> str:
    return "Живые игроки:\n" + "\n".join(f"{p.num}. {g.mention(p.uid)}" for p in g.alive())


def role_summary(g: Game) -> str:
    """«👨🏼 Мирный житель - 2, 🤵🏻 Дон»: кто остался, без имён."""
    count: dict[str, int] = {}
    for p in g.alive():
        count[p.role] = count.get(p.role, 0) + 1
    parts = [f"{ROLES[r][1]} {ROLES[r][0]}" + (f" - {count[r]}" if count[r] > 1 else "") for r in ROLE_ORDER if r in count]
    return ", ".join(parts)


def left_text(seconds: float) -> str:
    s = max(int(seconds + 0.5), 0)
    return f"{round(s / 60)} мин." if s >= 60 else f"{s} сек."


def duration_text(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60} мин. {s % 60} сек." if s >= 60 else f"{s} сек."


def final_text(g: Game, winner: str) -> str:
    win_side = (lambda p: p.role in MAFIA) if winner == "mafia" else (lambda p: p.role not in MAFIA)
    winners = [p for p in g.players.values() if win_side(p)]
    others = [p for p in g.players.values() if not win_side(p)]

    def line(p: Player) -> str:
        return f"    {g.mention(p.uid)} - {ROLES[p.role][1]} {ROLES[p.role][0]}"
    text = f"Игра окончена!\nПобедили: {'Мафия' if winner == 'mafia' else 'Мирные жители'}\n\nПобедители:\n" + "\n".join(map(line, winners))
    if others:
        text += "\n\nОстальные участники:\n" + "\n".join(map(line, others))
    return text + f"\n\nИгра длилась: {duration_text(time.time() - g.started)}."


# ---------- Telegram ----------
_file_ids: dict[str, str] = {}
_games: dict[int, Game] = {}               # chat_id -> игра
_in_game: dict[int, int] = {}              # user_id -> chat_id (игрок записан в идущую игру)
_bg: set[asyncio.Task] = set()


def get_game(chat_id: int) -> Game | None:
    return _games.get(chat_id)


ACTIVE_PHASES = {"night", "day", "vote", "confirm"}


def must_delete(chat_id: int, uid: int | None) -> bool:
    """Идёт партия, а автор сообщения не играет или уже убит — его сообщения в чате удаляются (чтобы не подсказывали и не мешали)."""
    g = _games.get(chat_id)
    if g is None or g.phase not in ACTIVE_PHASES:
        return False
    p = g.players.get(uid) if uid is not None else None
    return p is None or not p.alive


def game_of_user(uid: int) -> Game | None:
    chat = _in_game.get(uid)
    return _games.get(chat) if chat is not None else None


def link_kb(username: str, text: str, payload: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text=text, url=f"https://t.me/{username}?start={payload}")]])


async def _say(bot, chat_id: int, text: str, **kw):
    try:
        return await bot.send_message(chat_id, text, disable_web_page_preview=True, **kw)
    except Exception as e:
        logging.info("мафия: сообщение не отправилось (%s)", e)
        return None


async def _gif(bot, chat_id: int, name: str, caption: str, reply_markup=None):
    """Гифка дня или ночи с подписью; не вышла — просто текст."""
    path = ASSETS / f"{name}.mp4"
    try:
        msg = await bot.send_animation(chat_id, _file_ids.get(name) or FSInputFile(path), caption=caption, reply_markup=reply_markup)
        if name not in _file_ids and getattr(msg, "animation", None):
            _file_ids[name] = msg.animation.file_id
        return msg
    except Exception as e:
        _file_ids.pop(name, None)
        logging.info("мафия: гифка %s не отправилась (%s)", name, e)
        return await _say(bot, chat_id, caption, reply_markup=reply_markup)


async def _edit(bot, chat_id: int, message_id: int | None, text: str, reply_markup=None) -> None:
    if message_id is None:
        return
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup,
                                    disable_web_page_preview=True)
    except Exception as e:
        if "not modified" not in str(e).lower():
            logging.info("мафия: правка не удалась (%s)", e)


def pick_kb(prefix: str, chat_id: int, g: Game, options: list[int]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [B(text=g.players[u].name[:40], callback_data=f"mf:{prefix}:{chat_id}:{u}")] for u in options])


def confirm_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[B(text="👍", callback_data=f"mf:c:{chat_id}:1"), B(text="👎", callback_data=f"mf:c:{chat_id}:0")]])


async def _wait(g: Game, seconds: float, on_tick=None) -> None:
    """Ждёт конец фазы: время вышло, все сходили (step_event) или игру остановили. on_tick(осталось_сек) — для обратного отсчёта."""
    end = time.monotonic() + seconds
    while not g.cancelled and not g.step_event.is_set():
        left = end - time.monotonic()
        if left <= 0:
            return
        if on_tick is not None:
            await on_tick(left)
        try:
            await asyncio.wait_for(g.step_event.wait(), timeout=min(left, COUNTDOWN_STEP))
        except asyncio.TimeoutError:
            pass


def _forget(g: Game) -> None:
    for uid in g.players:
        if _in_game.get(uid) == g.chat_id:
            _in_game.pop(uid, None)
    if _games.get(g.chat_id) is g:
        _games.pop(g.chat_id, None)


async def open_registration(bot, chat_id: int, title: str, host: int, host_name: str, username: str):
    """Создаёт игру и сообщение с набором. Возвращает (игра, None) или (None, причина)."""
    if chat_id in _games:
        return None, "В этом чате уже идёт игра."
    if host in _in_game:
        return None, "Ты уже участвуешь в другой игре."
    g = Game(chat_id, title, host)
    _games[chat_id] = g
    err = g.join(host, host_name)
    if err is None:
        _in_game[host] = chat_id
    msg = await _say(bot, chat_id, reg_text(g), reply_markup=link_kb(username, "🤵🏻 Присоединиться", f"mafia_{chat_id}"))
    g.reg_msg = getattr(msg, "message_id", None)
    g.task = asyncio.create_task(run_game(bot, g, username))
    _bg.add(g.task)
    g.task.add_done_callback(_bg.discard)
    return g, None


def reg_text(g: Game) -> str:
    names = ", ".join(g.mention(u) for u in g.players) or "пока никого"
    return (f"Ведётся набор в игру\n\nЗарегистрировались: {names}\n\nИтого {len(g.players)} чел.\n"
            f"<i>Начать: /startgame (нужно минимум {MIN_PLAYERS}). Присоединиться — кнопкой ниже.</i>")


async def join(bot, g: Game, uid: int, name: str, username: str) -> str | None:
    """Вызывается из личного /start mafia_<chat>. None — присоединился."""
    if uid in _in_game and _in_game[uid] != g.chat_id:
        return "Ты уже участвуешь в другой игре."
    err = g.join(uid, name)
    if err is None:
        _in_game[uid] = g.chat_id
        await _edit(bot, g.chat_id, g.reg_msg, reg_text(g),
                    link_kb(username, "🤵🏻 Присоединиться", f"mafia_{g.chat_id}"))
    return err


def request_start(g: Game) -> str | None:
    """Ведущий просит начать досрочно. None — игра начнётся; иначе причина."""
    if g.phase != "reg":
        return "Игра уже идёт."
    if len(g.players) < MIN_PLAYERS:
        return f"Нужно минимум {MIN_PLAYERS} игрока, сейчас {len(g.players)}."
    g.start_event.set()
    return None


def stop(g: Game) -> None:
    g.cancelled = True
    g.start_event.set()
    g.step_event.set()


async def run_game(bot, g: Game, username: str) -> None:
    try:
        await _run(bot, g, username)
    except asyncio.CancelledError:
        raise
    except Exception:
        logging.exception("мафия: игра в %s упала", g.chat_id)
        await _say(bot, g.chat_id, "⚠️ В игре что-то сломалось, игра остановлена.")
    finally:
        g.phase = "done"
        _forget(g)


async def _run(bot, g: Game, username: str) -> None:
    # ----- набор -----
    try:
        await asyncio.wait_for(g.start_event.wait(), timeout=REG_SECONDS)
    except asyncio.TimeoutError:
        pass
    if g.cancelled:
        await _edit(bot, g.chat_id, g.reg_msg, "Набор в игру отменён.")
        return
    if len(g.players) < MIN_PLAYERS:
        await _edit(bot, g.chat_id, g.reg_msg, f"Набор закончен: нужно минимум {MIN_PLAYERS} игрока, а пришло {len(g.players)}. Игра не состоялась.")
        return
    g.assign()
    g.phase = "night"
    await _edit(bot, g.chat_id, g.reg_msg, reg_text(g).split("\n<i>")[0] + "\n\nНабор закончен.")
    await _say(bot, g.chat_id, "Игра начинается!\n\nВ течение нескольких секунд бот пришлёт вам личное сообщение с ролью и её описанием.",
               reply_markup=link_kb(username, "Посмотреть роль", "mafia_role"))
    await _warn_if_cannot_delete(bot, g)
    blocked = await _send_roles(bot, g)
    if blocked:
        names = ", ".join(g.mention(u) for u in blocked)
        await _say(bot, g.chat_id, f"⚠️ Не могу написать в личку: {names}. Нажмите «Присоединиться» → Start у бота и начните заново.")
        g.cancelled = True
        return

    # ----- игровой цикл -----
    while not g.cancelled:
        await _night(bot, g, username)
        if g.cancelled:
            break
        await _day(bot, g, username)                         # утром объявляет погибшего и проверяет победу
        if g.cancelled or await _finish_if_won(bot, g):
            return
    if g.cancelled:
        await _say(bot, g.chat_id, "Игра остановлена.")


async def _warn_if_cannot_delete(bot, g: Game) -> None:
    """Сообщения не-игроков и убитых бот удаляет — для этого нужно право админа «Удаление сообщений»."""
    try:
        m = await bot.get_chat_member(g.chat_id, (await bot.me()).id)
        ok = m.status == "creator" or (m.status == "administrator" and getattr(m, "can_delete_messages", False))
    except Exception:
        return
    if not ok:
        await _say(bot, g.chat_id, "⚠️ Дайте боту право админа «Удаление сообщений»: во время игры он удаляет сообщения тех, кто не играет или уже убит.")


async def _send_roles(bot, g: Game) -> list[int]:
    blocked = []
    mafia = [p for p in g.players.values() if p.role in MAFIA]
    for p in g.players.values():
        text = ROLE_TEXT[p.role].format(e=ROLES[p.role][1])
        if p.role in MAFIA and len(mafia) > 1:
            text += "\n\nТвоя команда: " + ", ".join(f"{html.escape(m.name)} ({ROLES[m.role][0]})" for m in mafia if m.uid != p.uid)
        if await _say(bot, p.uid, text) is None:
            blocked.append(p.uid)
    return blocked


async def _finish_if_won(bot, g: Game) -> bool:
    if g.phase == "done":
        return True
    w = g.winner()
    if w is None:
        return False
    g.phase = "done"
    await _say(bot, g.chat_id, final_text(g, w))
    return True


async def _night(bot, g: Game, username: str) -> None:
    g.begin_night()
    kb = link_kb(username, "Перейти к боту", "mafia_go")
    await _gif(bot, g.chat_id, "night", "🌃 Наступает ночь\nНа улицы города выходят лишь самые отважные и бесстрашные. Утром попробуем сосчитать их головы…", kb)
    timer = await _say(bot, g.chat_id, alive_list(g) + f"\n\nСпать осталось {left_text(NIGHT_SECONDS)}", reply_markup=kb)
    timer_id = getattr(timer, "message_id", None)

    # ночные приглашения в личку (параллельно: до 25 игроков)
    async def invite(p: Player) -> None:
        opts = g.night_options(p.uid)
        if not opts:
            return
        if p.role in MAFIA:
            await _say(bot, p.uid, "Мафия проводит голосование за следующую жертву:", reply_markup=pick_kb("n", g.chat_id, g, opts))
        elif p.role == "doc":
            note = f"\n\nВчера ты лечил {html.escape(g.players[g.last_heal].name)} — сегодня ему придётся продержаться без тебя." \
                if g.last_heal in g.players and g.players[g.last_heal].alive else ""
            await _say(bot, p.uid, "Кого будем лечить?" + note, reply_markup=pick_kb("n", g.chat_id, g, opts))
        else:
            await _say(bot, p.uid, "Кого проверим этой ночью?", reply_markup=pick_kb("n", g.chat_id, g, opts))
    await asyncio.gather(*(invite(p) for p in g.alive()))

    async def tick(left: float) -> None:
        await _edit(bot, g.chat_id, timer_id, alive_list(g) + f"\n\nСпать осталось {left_text(left)}", kb)
    await _wait(g, NIGHT_SECONDS, tick)
    await _edit(bot, g.chat_id, timer_id, alive_list(g) + "\n\nНочь закончилась.", kb)
    if g.cancelled:
        return

    had_mafia, had_doc, had_com = bool(g.mafia_votes), g.doc_pick is not None, g.com_pick is not None
    g.night_result = g.resolve_night()
    if had_mafia:
        await _say(bot, g.chat_id, "🤵🏻 Мафия выбрала жертву…")
    if had_doc:
        await _say(bot, g.chat_id, "👨🏼‍⚕️ Доктор вышел на ночное дежурство…")
    if had_com:
        await _say(bot, g.chat_id, "🕵🏼 Комиссар отправился на поиски мафии…")


async def _day(bot, g: Game, username: str) -> None:
    res = g.night_result
    g.phase = "day"
    await _gif(bot, g.chat_id, "day", f"🏙 День {g.day}\nСолнце всходит, подсушивая на тротуарах пролитую ночью кровь…")
    killed = res.get("killed")
    if killed is None:
        await _say(bot, g.chat_id, "🤷‍♂️ Удивительно, но этой ночью все выжили")
    else:
        p = g.players[killed]
        await _say(bot, g.chat_id, f"Сегодня был жестоко убит {ROLES[p.role][1]} {ROLES[p.role][0]} {g.mention(killed)}…")
        await _say(bot, killed, "Тебя убили :(\nТы можешь отправить сюда своё предсмертное сообщение")
    if await _finish_if_won(bot, g):
        return
    await _say(bot, g.chat_id, f"{alive_list(g)}\n\nКто-то из них:\n{role_summary(g)}\nВсего: {len(g.alive())} чел.\n\n"
                               "Сейчас самое время обсудить результаты ночи, разобраться в причинах и следствиях…")
    g.step_event.clear()
    await _wait(g, DAY_SECONDS)
    if g.cancelled:
        return

    # ----- голосование -----
    g.begin_vote()
    await _say(bot, g.chat_id, f"Пришло время определить и наказать виноватых.\nГолосование продлится {VOTE_SECONDS} секунд",
               reply_markup=link_kb(username, "Голосовать", "mafia_go"))
    await asyncio.gather(*(_say(bot, p.uid, "Пришло время искать виноватых!\nКого ты хочешь линчевать?",
                                reply_markup=pick_kb("v", g.chat_id, g, g.vote_options(p.uid))) for p in g.alive()))
    await _wait(g, VOTE_SECONDS)
    if g.cancelled:
        return
    target = g.tally()
    if target is None:
        await _say(bot, g.chat_id, "Голосование окончено\nМнения жителей разошлись…\nРазошлись и сами жители, так никого и не повесив…")
        return

    # ----- подтверждение -----
    g.begin_confirm(target)
    name = g.mention(target)
    msg = await _say(bot, g.chat_id, f"Вы точно хотите линчевать {name}?", reply_markup=confirm_kb(g.chat_id))
    await _wait(g, CONFIRM_SECONDS)
    await _edit(bot, g.chat_id, getattr(msg, "message_id", None), f"Вы точно хотите линчевать {name}?\n\nГолосование завершено")
    if g.cancelled:
        return
    yes, no, hang = g.confirm_result()
    if not hang:
        await _say(bot, g.chat_id, f"Результаты голосования:\n{yes}👍 | {no}👎\n\n{name} остаётся жить. Пока что…")
        g.accused = None
        return
    await _say(bot, g.chat_id, f"Результаты голосования:\n{yes}👍 | {no}👎\n\nВешаем {name}! :)")
    g.kill(target)
    p = g.players[target]
    await _say(bot, g.chat_id, f"{name} был {ROLES[p.role][1]} {ROLES[p.role][0]}")
    await _say(bot, target, "Тебя повесили :(\nТы можешь отправить сюда своё предсмертное сообщение")
    g.accused = None


# ---------- действия игроков (вызываются из кнопок) ----------
def night_action(g: Game, uid: int, target: int) -> tuple[str, list[tuple[int, str]]]:
    """(что ответить игроку, [(кому ещё, что написать)]). Текст ошибки начинается с «⚠️»."""
    err = g.night_pick(uid, target)
    if err:
        return "⚠️ " + err, []
    p = g.players[uid]
    name = html.escape(g.players[target].name)
    extra: list[tuple[int, str]] = []
    if p.role in MAFIA:
        extra = [(m, f"{html.escape(p.name)} ({ROLES[p.role][0]}) проголосовал за {name}") for m in g.alive_ids(MAFIA) if m != uid]
    if p.role == "com":
        is_m = g.players[target].role in MAFIA
        return f"Ты выбрал {name}\n\n" + (f"🔴 {name} — МАФИЯ!" if is_m else f"🟢 {name} — мирный житель."), []
    return f"Ты выбрал {name}", extra


def vote_action(g: Game, uid: int, target: int) -> tuple[str, str | None]:
    """(ответ игроку, объявление в группу или None)."""
    err = g.cast_vote(uid, target)
    if err:
        return "⚠️ " + err, None
    return f"Ты выбрал {html.escape(g.players[target].name)}", f"{g.mention(uid)} проголосовал за {g.mention(target)}"


def last_words(g: Game, uid: int, text: str) -> str | None:
    """Предсмертное сообщение: текст для группы или None (нельзя / нечего)."""
    p = g.players.get(uid)
    text = " ".join((text or "").split())[:LAST_WORDS_MAX]
    if p is None or p.alive or not p.can_speak or not text or g.phase == "done":
        return None
    p.can_speak = False
    return f"Кто-то из жителей слышал, как {g.mention(uid)} кричал перед смертью:\n<i>{html.escape(text)}</i>"
