extends RefCounted
## Глава 2. Коммуналка на Садовой — они прячутся в вещах.

var blackout_done := false
var power_back := false
var fuse_taken := false
var mimics: Array = []

func build(L: Level) -> void:
	var b := L.b
	var legend := {
		"Y": Common.YARD_SPEC,
		"H": {"name": "Коридор", "floor": "floor_dark", "wall": "wall_peel", "light": 0.7, "wall_tint": Color(0.7, 0.75, 0.65)},
		"A": {"name": "Комната Семёновой", "floor": "floor_wood", "wall": "wall_paper", "light": 0.8},
		"B": {"name": "Комната Бочкарёва", "floor": "floor_carpet", "wall": "wall_blue", "light": 0.7},
		"K": {"name": "Общая кухня", "floor": "floor_lino", "wall": "wall_plaster", "light": 1.0, "wall_tint": Color(0.75, 0.8, 0.7)},
		"C": {"name": "Комната Лины", "floor": "floor_wood", "wall": "wall_peel", "light": 0.7},
		"W": {"name": "Санузел", "floor": "floor_tile", "wall": "wall_plaster", "light": 0.6, "wall_tint": Color(0.7, 0.8, 0.8)},
		"S": {"name": "Кладовая", "floor": "floor_conc", "wall": "wall_grey", "light": 0.45},
	}
	b.layout(["YYAABBKK", "YYHHHHHH", "YYCCWSSS"], legend, 0.0, 4.0)
	b.doors_from(["Y-H", "H-A", "H-B", "H-K", "H-C", "H-W", "H-S"])
	b.finish()
	b.spawn = b.P("Y", 0.7, 0.5) + Vector3(0, 0.1, 0)
	b.spawn_yaw = -90.0 + 180.0
	b.task("dust", "Протереть пыль в комнатах жильцов")
	b.task("floor", "Помыть полы в коридоре и на кухне")
	b.task("vac", "Пропылесосить ковры")
	b.task("sweep", "Подмести мусор")
	b.task("bath", "Привести в порядок санузел")
	b.task("trash", "Вынести мусор (3 мешка)", {"manual": true, "need": 3})
	b.task("fuse", "Вернуть свет: найти предохранитель", {"manual": true, "hidden": true})
	b.task("blood", "Отмыть тёмное пятно у плиты (спрей)", {"optional": true})
	Common.yard(L, "Y")
	# --- Комната Семёновой (A): мимик-сундук ---
	b.against("bed", "A", "W", 0.5, {}, 1.1)
	b.against("wardrobe", "A", "N", 0.7, {}, 0.35)
	b.prop("rug", b.P("A", 0.55, 0.55), 0, {"w": 2.2, "d": 1.6})
	b.prop("table", b.P("A", 0.75, 0.75), 20, {"w": 1.0, "d": 0.7})
	b.note_pickup("n2_a", b.P("A", 0.75, 0.75, 0.77), 10)
	b.dirt("dust", b.P("A", 0.75, 0.75, 0.775), Vector2(0.8, 0.5), Vector3.UP, "dust")
	b.dirt("dust", b.wp("A", "N", 0.3, 0.3, 0.92), Vector2(0.9, 0.5), Vector3.UP, "dust")
	b.dirt("crumbs", b.P("A", 0.55, 0.55, 0.03), Vector2(1.3, 1.0), Vector3.UP, "vac")
	mimics.append(Common.mimic(L, b.P("A", 0.85, 0.2), "crate", {"s": 0.8}, {"radius": 2.0}))
	Common.hide_wardrobe(L, "H", "N", 0.97)
	# --- Бочкарёв (B): куча одежды / кресло ---
	b.against("bed", "B", "E", 0.5, {"tint": Color(0.5, 0.4, 0.4)}, 1.1)
	b.prop("rug", b.P("B", 0.45, 0.5), 0, {"w": 2.0, "d": 1.4, "tint": Color(0.4, 0.5, 0.55)})
	b.against("bookshelf", "B", "N", 0.3, {"seed": 8}, 0.2)
	b.note_pickup("n2_b", b.P("B", 0.4, 0.8, 0.0), -20)
	b.dirt("dust", b.wp("B", "N", 0.75, 0.3, 0.9), Vector2(0.8, 0.5), Vector3.UP, "dust")
	b.dirt("crumbs", b.P("B", 0.45, 0.5, 0.03), Vector2(1.2, 0.9), Vector3.UP, "vac")
	b.floor_dirt("debris", "B", Vector2(-1.0, 1.0), Vector2(1.2, 1.0), "sweep")
	mimics.append(Common.mimic(L, b.P("B", 0.2, 0.75), "armchair", {}, {"radius": 2.0}))
	Common.bag(L, b.P("B", 0.1, 0.9))
	# --- Кухня (K) ---
	b.against("stove", "K", "N", 0.3, {}, 0.35)
	b.against("counter", "K", "N", 0.7, {"w": 2.0}, 0.35)
	b.against("fridge", "K", "E", 0.5, {}, 0.4)
	b.prop("table", b.P("K", 0.4, 0.62), 0)
	b.prop("chair", b.P("K", 0.28, 0.62), 90); b.prop("chair", b.P("K", 0.52, 0.62), -90)
	b.floor_dirt("stain", "K", Vector2(-0.5, 0.9), Vector2(1.6, 1.4), "floor")
	b.floor_dirt("mud", "K", Vector2(2.0, 1.0), Vector2(1.2, 1.2), "floor")
	var bl := b.dirt("blood", b.wp("K", "N", 0.3, 0.9, 0.0) + Vector3(0, 0.03, 0), Vector2(0.9, 0.9), Vector3.UP, "blood", {"story": true, "id": "ch2_blood"})
	b.note_pickup("n2_t1", b.wp("K", "N", 0.3, 0.9, 0.04), 0, Color(0.25, 0.22, 0.2))
	L.hide_note_later("n2_t1")
	Common.bag(L, b.P("K", 0.9, 0.9))
	Common.pickup(L, "key", b.P("K", 0.4, 0.62, 0.78), "Взять предохранитель", func(p): _fuse(L))
	b.interact(b.P("K", 0.6, 0.62, 1.0), Vector3(0.1, 0.1, 0.1), "", Callable())
	# --- Лина (C) ---
	b.against("bed", "C", "W", 0.4, {"tint": Color(0.7, 0.6, 0.55)}, 1.1)
	b.against("crib", "C", "N", 0.7, {}, 0.45)
	b.prop("rug", b.P("C", 0.5, 0.6), 0, {"w": 2.0, "d": 1.4, "tint": Color(0.5, 0.35, 0.4)})
	b.note_pickup("n2_c", b.P("C", 0.5, 0.6, 0.03), 40)
	b.dirt("dust", b.wp("C", "N", 0.3, 0.3, 0.8), Vector2(0.8, 0.5), Vector3.UP, "dust")
	b.dirt("crumbs", b.P("C", 0.5, 0.6, 0.03), Vector2(1.2, 0.9), Vector3.UP, "vac")
	b.floor_dirt("debris", "C", Vector2(1.0, 1.2), Vector2(1.2, 1.0), "sweep")
	mimics.append(Common.mimic(L, b.P("C", 0.88, 0.85), "box", {"s": 0.8}, {"radius": 2.0}))
	# --- коридор (H) ---
	b.floor_dirt("mud", "H", Vector2(-6.0, 0), Vector2(1.6, 1.2), "floor")
	b.floor_dirt("mud", "H", Vector2(-1.0, 0), Vector2(1.6, 1.2), "floor")
	b.floor_dirt("stain", "H", Vector2(4.0, 0), Vector2(1.6, 1.2), "floor")
	b.floor_dirt("debris", "H", Vector2(-3.0, 0.3), Vector2(1.2, 1.0), "sweep")
	b.against("dresser", "H", "S", 0.55, {}, 0.3)
	b.dirt("dust", b.wp("H", "S", 0.55, 0.3, 0.92), Vector2(0.9, 0.45), Vector3.UP, "dust")
	mimics.append(Common.mimic(L, b.wp("H", "S", 0.25, 0.3), "dresser", {}, {"radius": 1.8}))
	Common.bag(L, b.P("H", 0.8, 0.8))
	# --- санузел (W) ---
	b.against("toilet", "W", "N", 0.25, {}, 0.3)
	b.against("bathtub", "W", "E", 0.5, {}, 0.45)
	b.against("washbasin", "W", "N", 0.7, {}, 0.3)
	var mp := b.wp("W", "N", 0.7, 0.0, 1.5)
	b.prop("mirror", mp + Vector3(0, 0, 0.1), 0)
	var mg := b.dirt("glass", mp + Vector3(0, 0, 0.14), Vector2(0.8, 1.3), Vector3(0, 0, 1), "bath")
	b.floor_dirt("stain", "W", Vector2(0, 0.5), Vector2(1.0, 1.0), "bath")
	b.note_pickup("n2_t2", b.wp("W", "N", 0.7, 0.3, 0.05), 0, Color(0.25, 0.22, 0.2))
	L.hide_note_later("n2_t2")
	b.task("lina", "", {"optional": true, "hidden": true, "manual": true})
	# --- кладовая (S): щиток ---
	b.prop("crate", b.P("S", 0.2, 0.2), 10)
	b.prop("box", b.P("S", 0.5, 0.25), -20)
	b.floor_dirt("debris", "S", Vector2(0, 0.5), Vector2(1.4, 1.0), "sweep")
	b.dirt("dust", b.P("S", 0.7, 0.3, 0.65), Vector2(0.6, 0.6), Vector3.UP, "dust")
	mimics.append(Common.mimic(L, b.P("S", 0.85, 0.8), "crate", {"s": 0.7}, {"radius": 2.0}))
	b.interact(b.wp("S", "N", 0.6, 0.15, 1.3), Vector3(0.6, 0.8, 0.3), "Электрощиток", func(p):
		if power_back:
			Game.note("Свет уже работает.")
		elif Game.flag("fuse"):
			power_back = true
			Common.blackout(L, false)
			L.complete_task("fuse")
			Audio.say("h2_12")
		elif blackout_done:
			Game.note("Нужен предохранитель. Кажется, я видел его на кухне.")
		else:
			Game.note("Щиток. Всё в порядке."))
	b.prop("box", b.wp("S", "N", 0.6, 0.2, 1.2), 0, {"s": 0.4})
	b.trigger(b.P("H", 0.5, 0.5, 1.0), Vector3(20, 2.5, 3.5), func(): Audio.say("h2_02"))

func on_begin(L: Level) -> void:
	Game.note("Фонарь — кнопка «Фонарь». Свет отпугивает то, что дышит в вещах.")

func _fuse(L: Level) -> void:
	fuse_taken = true
	Game.set_flag("fuse")
	Game.note("Предохранитель взят.")
	Audio.say("h2_11")

func tick(L: Level, delta: float) -> void:
	if not blackout_done and L.progress() > 0.4:
		blackout_done = true
		Common.blackout(L, true)
		L.unlock_task("fuse")
		L.player.shake(0.02, 0.5)
		Audio.say("h2_10")
		L.objective_override = ""
		Game.set_flag("blackout")

func restore(L: Level) -> void:
	if Game.flag("blackout") and not Game.flag("power_back"):
		blackout_done = true
		Common.blackout(L, true)

func on_story_patch(L: Level, p: DirtPatch) -> void:
	if p.patch_id == "ch2_blood":
		L.reveal_note("n2_t1")
		Audio.say("h2_14")

func on_task_done(L: Level, id: String) -> void:
	match id:
		"bath": L.reveal_note("n2_t2")
		"trash": Audio.say("h2_09")
		"fuse":
			Game.set_flag("power_back")
			Game.set_flag("ch2_done")

func on_note_read(L: Level, id: String) -> void:
	match id:
		"n2_a": Audio.say("h2_05")
		"n2_c": Audio.say("h2_06")
		"n2_t1": Audio.say("h2_15")
		"n2_t2": Audio.say("h2_16")

func on_room_first(L: Level, r: String) -> void:
	if r == "S":
		Audio.say("h2_08")

func finish_gate(L: Level) -> Array:
	if blackout_done and not power_back:
		return [false, "Сначала верните свет."]
	return Common.gate(L, 0.55)
