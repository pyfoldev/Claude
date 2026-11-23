"""Симулятор телефона для проверки команд малой модели.
Принимает те же действия, что `phone` в приложении (PhoneControl.kt), проверяет схему и меняет состояние.
Сравнивая итоговое состояние «по модели» и «по эталону», проверяем смысл, а не побуквенное совпадение JSON.
"""
import json

TOGGLES = {"wifi", "bluetooth", "airplane", "dnd", "autorotate", "nfc", "hotspot", "location", "battery_saver"}
SYSTEM_OPS = {"home", "back", "recents", "notifications", "quick_settings", "lock"}
MEDIA_OPS = {"play", "pause", "toggle", "next", "prev", "stop", "forward", "rewind", "volume_up", "volume_down"}
STOPWATCH_OPS = {"start", "stop", "status"}
VOL_TARGETS = {"media", "ring", "alarm"}
MSG_APPS = {"whatsapp", "telegram"}

# действие → {поле: (тип, обязательное)}
SCHEMA = {
    "open_app": {"app": (str, True)},
    "close_app": {"app": (str, True)},
    "alarm": {"hour": (int, True), "minute": (int, False), "label": (str, False)},
    "timer": {"seconds": (int, True), "label": (str, False)},
    "stopwatch": {"op": (str, False)},
    "flashlight": {"on": (bool, False)},
    "toggle": {"target": (str, True), "on": (bool, False)},
    "volume": {"level": (int, True), "target": (str, False)},
    "brightness": {"level": (int, True)},
    "system": {"op": (str, True)},
    "media": {"op": (str, True)},
    "music_play": {"query": (str, True), "app": (str, False)},
    "call": {"to": (str, True)},
    "message": {"app": (str, True), "to": (str, True), "text": (str, True)},
    "remind": {"text": (str, True), "minutes": (int, True)},
}


class Invalid(Exception):
    pass


def validate(a):
    if not isinstance(a, dict) or "action" not in a:
        raise Invalid("нет поля action")
    name = a["action"]
    if name not in SCHEMA:
        raise Invalid(f"неизвестное действие {name}")
    spec = SCHEMA[name]
    for k, v in a.items():
        if k == "action":
            continue
        if k not in spec:
            raise Invalid(f"{name}: лишнее поле {k}")
        t = spec[k][0]
        if t is int and (isinstance(v, bool) or not isinstance(v, int)):
            raise Invalid(f"{name}.{k}: нужен int")
        if t is bool and not isinstance(v, bool):
            raise Invalid(f"{name}.{k}: нужен bool")
        if t is str and (not isinstance(v, str) or not v.strip()):
            raise Invalid(f"{name}.{k}: нужна непустая строка")
    for k, (_, req) in spec.items():
        if req and k not in a:
            raise Invalid(f"{name}: нет поля {k}")
    if name == "alarm" and not (0 <= a["hour"] <= 23 and 0 <= a.get("minute", 0) <= 59):
        raise Invalid("alarm: время вне диапазона")
    if name == "timer" and not (1 <= a["seconds"] <= 86400):
        raise Invalid("timer: длительность вне диапазона")
    if name in ("volume", "brightness") and not (0 <= a["level"] <= 100):
        raise Invalid(f"{name}: уровень вне 0..100")
    if name == "toggle" and a["target"] not in TOGGLES:
        raise Invalid("toggle: неизвестная цель")
    if name == "system" and a["op"] not in SYSTEM_OPS:
        raise Invalid("system: неизвестная операция")
    if name == "media" and a["op"] not in MEDIA_OPS:
        raise Invalid("media: неизвестная операция")
    if name == "stopwatch" and a.get("op", "start") not in STOPWATCH_OPS:
        raise Invalid("stopwatch: неизвестная операция")
    if name == "volume" and a.get("target", "media") not in VOL_TARGETS:
        raise Invalid("volume: неизвестная цель")
    if name == "message" and a["app"] not in MSG_APPS:
        raise Invalid("message: app должен быть whatsapp|telegram")
    if name == "remind" and not (1 <= a["minutes"] <= 60 * 24 * 30):
        raise Invalid("remind: minutes вне диапазона")


class PhoneSim:
    def __init__(self):
        self.alarms = []        # (hour, minute)
        self.timers = []        # секунды
        self.torch = False
        self.toggles = {t: False for t in TOGGLES}
        self.toggles["location"] = True
        self.volume = {"media": 50, "ring": 50, "alarm": 50}
        self.brightness = 50
        self.foreground = "home"
        self.closed = []
        self.nav = []
        self.music = {"playing": False, "query": None, "app": None}
        self.calls = []
        self.messages = []
        self.reminders = []
        self.stopwatch = "stopped"
        self.vol_steps = 0

    def apply(self, a):
        validate(a)
        n = a["action"]
        if n == "open_app":
            self.foreground = a["app"].strip().lower()
        elif n == "close_app":
            self.closed.append(a["app"].strip().lower())
            if self.foreground == a["app"].strip().lower():
                self.foreground = "home"
        elif n == "alarm":
            self.alarms.append((a["hour"], a.get("minute", 0)))
        elif n == "timer":
            self.timers.append(a["seconds"])
        elif n == "stopwatch":
            op = a.get("op", "start")
            if op == "start":
                self.stopwatch = "running"
            elif op == "stop":
                self.stopwatch = "stopped"
        elif n == "flashlight":
            self.torch = a.get("on", True)
        elif n == "toggle":
            self.toggles[a["target"]] = a.get("on", True) if "on" in a else not self.toggles[a["target"]]
        elif n == "volume":
            self.volume[a.get("target", "media")] = a["level"]
        elif n == "brightness":
            self.brightness = a["level"]
        elif n == "system":
            self.nav.append(a["op"])
        elif n == "media":
            op = a["op"]
            if op == "play":
                self.music["playing"] = True
            elif op in ("pause", "stop"):
                self.music["playing"] = False
            elif op == "volume_up":
                self.vol_steps += 1
            elif op == "volume_down":
                self.vol_steps -= 1
            else:
                self.nav.append("media:" + op)
        elif n == "music_play":
            self.music = {"playing": True, "query": a["query"].strip().lower(), "app": (a.get("app") or "").strip().lower() or None}
        elif n == "call":
            self.calls.append(a["to"].strip().lower())
        elif n == "message":
            self.messages.append((a["app"], a["to"].strip().lower(), a["text"].strip().lower()))
        elif n == "remind":
            self.reminders.append((a["text"].strip().lower(), a["minutes"]))

    def state(self):
        return json.dumps({
            "alarms": sorted(self.alarms), "timers": sorted(self.timers), "torch": self.torch, "toggles": self.toggles,
            "volume": self.volume, "brightness": self.brightness, "fg": self.foreground, "closed": sorted(self.closed), "nav": self.nav,
            "music": self.music, "calls": self.calls, "messages": self.messages, "reminders": self.reminders, "sw": self.stopwatch, "vs": self.vol_steps,
        }, sort_keys=True, ensure_ascii=False)


def run(actions):
    """Выполняет список действий в чистом симуляторе → (state, ошибка|None)."""
    s = PhoneSim()
    try:
        for a in actions:
            s.apply(a)
    except Invalid as e:
        return None, str(e)
    return s.state(), None
