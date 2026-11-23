extends RefCounted
## Глава 1. Дом Громовых — обычный заказ.

var tv: Node3D
var sofa: Node3D
var cleaned_dust := 0.0
var sofa_done := false
var laugh_done := false
var kettle_done := false

func build(L: Level) -> void:
	var b := L.b
	var legend := {
		"Y": {"name": "Двор", "floor": "floor_conc", "wall": "wall_brick", "ceil": "wall_grey", "light": 1.4, "light_color": Color(0.7, 0.78, 1.0), "h": 4.0, "wall_tint": Color(0.5, 0.5, 0.55)},
		"H": {"name": "Прихожая", "floor": "floor_wood", "wall": "wall_paper", "light": 0.9},
		"K": {"name": "Кухня", "floor": "floor_tile", "wall": "wall_plaster", "wall_tint": Color(0.8, 0.8, 0.7), "light": 1.1},
		"P": {"name": "Кладовая", "floor": "floor_lino", "wall": "wall_grey", "light": 0.6},
		"L": {"name": "Гостиная", "floor": "floor_wood", "wall": "wall_paper", "light": 1.0},
		"R": {"name": "Столовая", "floor": "floor_wood", "wall": "wall_peel", "light": 0.8},
		"C": {"name": "Коридор", "floor": "floor_dark", "wall": "wall_paper", "light": 0.55},
		"D": {"name": "Спальня", "floor": "floor_carpet", "wall": "wall_blue", "light": 0.7},
		"B": {"name": "Ванная", "floor": "floor_tile", "wall": "wall_plaster", "wall_tint": Color(0.7, 0.8, 0.8), "light": 0.8},
		"S": {"name": "Лестница", "floor": "floor_dark", "wall": "wall_paper", "light": 0.5, "ramp": "x+", "rise": 3.0, "h": 5.7},
	}
	b.layout([
		"YYHKKPP.",
		"YYHLLRR.",
		"YYHLLRR.",
		"YYCCCCSS",
		"YY.DDB..",
	], legend, 0.0, 4.0)
	var up := {
		"n": {"name": "Детская", "floor": "floor_carpet", "wall": "wall_blue", "light": 0.6, "wall_tint": Color(0.8, 0.8, 0.95)},
		"m": {"name": "Родительская", "floor": "floor_wood", "wall": "wall_paper", "light": 0.6},
		"u": {"name": "Верхний коридор", "floor": "floor_dark", "wall": "wall_paper", "light": 0.35},
		"k": {"name": "Кабинет", "floor": "floor_wood", "wall": "wall_grey", "light": 0.5},
		"w": {"name": "Ванная наверху", "floor": "floor_tile", "wall": "wall_plaster", "light": 0.6},
	}
	b.layout([
		"nnmm",
		"nnmm",
		"uuuu",
		"kkww",
	], up, 3.0, 4.0, Vector2(32, 4))
	b.doors_from(["Y-H", "H-K", "H-L", "H-C", "K-P", "K-L", "L-R", "P-R", "L-C", "R-C", "C-D", "C-B", "C-S", "S-u", "u-n", "u-m", "u-k", "u-w"])
	b.door("Y", "H", {"open": false, "tint": Color(0.35, 0.28, 0.22)})
	b.finish()
	# запертый кабинет и дверь, которая «не открывается»
	L.door_between("u", "k").jammed = true
	L.door_between("u", "k")._update_prompt()
	L.door_between("C", "D").locked = false

	b.spawn = b.P("Y", 0.7, 0.2) + Vector3(0, 0.1, 0)
	b.spawn_yaw = -90.0 + 180.0

	# ---------- задачи ----------
	b.task("enter", "Зайти в дом", {"manual": true})
	b.task("dust", "Протереть пыль на первом этаже")
	b.task("floor", "Помыть пол на кухне")
	b.task("sweep", "Подмести мусор в прихожей и коридоре")
	b.task("vac", "Пропылесосить ковёр в гостиной")
	b.task("mirror", "Протереть зеркало в ванной")
	b.task("trash", "Вынести мусор (3 мешка)", {"manual": true, "need": 3})
	b.task("upstairs", "Убраться на втором этаже")
	b.task("steps", "Смыть странные следы", {"hidden": true})
	b.task("leave", "Вернуться к фургону", {"manual": true, "hidden": true})
	b.tasks.enter.done = false

	# ---------- двор ----------
	Common.bucket(L, b.P("Y", 0.55, 0.45))
	Common.supply(L, b.P("Y", 0.45, 0.3), 90)
	Common.dumpster(L, b.P("Y", 0.8, 0.8), "trash", 180)
	Common.van_exit(L, b.P("Y", 0.45, 0.6), 90)
	b.prop("plant", b.P("Y", 0.2, 0.1))
	b.prop("crate", b.P("Y", 0.2, 0.85), 20, {"s": 0.8})
	b.prop("box", b.P("Y", 0.28, 0.9), 40)
	b.lamp_light(b.P("Y", 0.9, 0.5, 3.4), Color(1, 0.9, 0.6), 0.6, 9.0)

	# ---------- прихожая ----------
	b.against("dresser", "H", "W", 0.5, {}, 0.3)
	b.against("picture", "H", "E", 0.5, {}, 0.0).position.y = 1.7
	b.note_pickup("n1_a", b.wp("H", "W", 0.5, 0.35, 0.92), 0)
	b.prop("rug", b.P("H", 0.5, 0.35), 0, {"w": 1.4, "d": 2.0})
	b.prop("plant", b.P("H", 0.85, 0.9))
	b.floor_dirt("debris", "H", Vector2(0.4, 1.5), Vector2(1.4, 1.2), "sweep")
	b.floor_dirt("debris", "H", Vector2(-0.3, -3.0), Vector2(1.0, 1.0), "sweep")
	Common.bag(L, b.P("H", 0.15, 0.75))

	# ---------- кухня ----------
	b.against("counter", "K", "N", 0.35, {"w": 2.4}, 0.35)
	b.against("stove", "K", "N", 0.8, {}, 0.35)
	b.against("fridge", "K", "E", 0.3, {}, 0.4)
	b.prop("table", b.P("K", 0.5, 0.62), 0)
	b.prop("chair", b.P("K", 0.38, 0.62), 90)
	b.prop("chair", b.P("K", 0.62, 0.62), -90)
	b.prop("chair", b.P("K", 0.5, 0.82), 180)
	b.note_pickup("n1_b", b.P("K", 0.5, 0.62, 0.77), 25)
	var kettle := b.prop("crate", b.wp("K", "N", 0.78, 0.55, 0.93), 0, {"s": 0.001})
	b.interact(b.wp("K", "N", 0.78, 0.55, 1.05), Vector3(0.4, 0.4, 0.4), "Потрогать чайник", func(p):
		if not kettle_done:
			kettle_done = true
			Audio.say("h1_06")
		Game.note("Чайник тёплый. Кто-то им пользовался.")
		Audio.sfx("kettle", b.wp("K", "N", 0.78, 0.55)))
	Props.cyl(kettle, 0.1, 0.18, Vector3(0, 0.1, 0), Mats.color(Color(0.65, 0.65, 0.68), 0.3, 0, 0.9), 0.07)
	Common.bucket(L, b.P("K", 0.85, 0.9))
	b.floor_dirt("stain", "K", Vector2(-1.0, 0.8), Vector2(1.6, 1.4), "floor")
	b.floor_dirt("stain", "K", Vector2(2.2, -0.2), Vector2(1.2, 1.2), "floor")
	b.floor_dirt("mud", "K", Vector2(-2.6, -0.4), Vector2(1.0, 1.0), "floor")
	Common.bag(L, b.P("K", 0.12, 0.9))

	# ---------- кладовая ----------
	b.against("bookshelf", "P", "N", 0.5, {"seed": 11}, 0.2)
	b.prop("box", b.P("P", 0.3, 0.7), 20)
	b.prop("box", b.P("P", 0.45, 0.78), -10, {"s": 0.6})
	b.prop("crate", b.P("P", 0.8, 0.8), 30)

	# ---------- гостиная ----------
	var rugpos := b.P("L", 0.5, 0.55)
	b.prop("rug", rugpos, 0, {"w": 3.2, "d": 2.4})
	sofa = b.against("sofa", "L", "S", 0.5, {"tint": Color(0.45, 0.4, 0.38)}, 0.55)
	b.prop("table", b.P("L", 0.5, 0.5, 0.0), 0, {"w": 1.1, "d": 0.7})
	tv = b.against("tv", "L", "N", 0.5, {}, 0.35)
	b.prop("armchair", b.P("L", 0.15, 0.55), 70)
	b.prop("lamp", b.P("L", 0.9, 0.2), 0)
	b.against("bookshelf", "L", "W", 0.3, {"seed": 5}, 0.25)
	b.prop("picture", b.wp("L", "W", 0.7, 0.0, 1.7) + Vector3(0.12, 0, 0), 90)
	b.dirt("dust", b.P("L", 0.5, 0.5, 0.775), Vector2(1.0, 0.65), Vector3.UP, "dust")
	b.dirt("dust", b.wp("L", "N", 0.5, 0.35, 0.52), Vector2(0.9, 0.5), Vector3.UP, "dust")
	b.dirt("dust", b.P("L", 0.15, 0.55, 0.9), Vector2(0.7, 0.7), Vector3.UP, "dust")
	b.dirt("crumbs", rugpos + Vector3(-0.5, 0.03, -0.3), Vector2(1.4, 1.0), Vector3.UP, "vac")
	b.dirt("crumbs", rugpos + Vector3(0.8, 0.03, 0.4), Vector2(1.2, 0.9), Vector3.UP, "vac")
	# кровь под ковром — сюжетная
	var bl := b.dirt("blood", rugpos + Vector3(1.6, 0.03, 0.9), Vector2(0.9, 0.9), Vector3.UP, "", {"story": true, "id": "ch1_blood"})
	b.note_pickup("n1_t", rugpos + Vector3(1.6, 0.04, 0.9), 15, Color(0.25, 0.22, 0.2))
	b.notes_nodes["n1_t"].node.visible = false
	b.notes_nodes["n1_t"].it.enabled = false
	b.task("blood", "Отмыть странное пятно (спрей)", {"optional": true, "hidden": true})
	bl.task_id = "blood"
	b.tasks.blood.patches.append(bl)

	# ---------- столовая ----------
	b.prop("table", b.P("R", 0.5, 0.5), 0, {"w": 2.0, "d": 1.0})
	for i in 3:
		b.prop("chair", b.P("R", 0.35 + i * 0.15, 0.36), 0)
		b.prop("chair", b.P("R", 0.35 + i * 0.15, 0.64), 180)
	b.against("window", "R", "E", 0.5, {}, 0.0).position.y = 1.5
	b.dirt("dust", b.P("R", 0.5, 0.5, 0.77), Vector2(1.5, 0.8), Vector3.UP, "dust")
	b.floor_dirt("debris", "R", Vector2(0.0, 2.5), Vector2(1.2, 1.0), "sweep")
	Common.bag(L, b.P("R", 0.88, 0.85))

	# ---------- коридор ----------
	b.floor_dirt("debris", "C", Vector2(-3.0, 0), Vector2(1.3, 1.0), "sweep")
	b.floor_dirt("mud", "C", Vector2(1.0, 0.2), Vector2(1.4, 1.0), "floor")
	b.prop("picture", b.wp("C", "N", 0.3, 0.0, 1.6) + Vector3(0, 0, 0.12), 0)
	b.prop("picture", b.wp("C", "N", 0.6, 0.0, 1.6) + Vector3(0, 0, 0.12), 0, {"c": Color(0.4, 0.3, 0.3)})

	# ---------- спальня внизу ----------
	Common.hide_bed(L, "D", "W", 0.5)
	Common.hide_wardrobe(L, "D", "N", 0.7)
	b.prop("dresser", b.P("D", 0.8, 0.85), 180)
	b.dirt("dust", b.P("D", 0.8, 0.85, 0.92), Vector2(0.9, 0.45), Vector3.UP, "dust")

	# ---------- ванная ----------
	b.against("toilet", "B", "N", 0.25, {}, 0.3)
	b.against("washbasin", "B", "N", 0.7, {}, 0.3)
	b.against("bathtub", "B", "W", 0.4, {}, 0.45)
	var mp := b.wp("B", "N", 0.7, 0.0, 1.5)
	b.prop("mirror", mp + Vector3(0, 0, 0.1), 0)
	var mg := b.dirt("glass", mp + Vector3(0, 0, 0.14), Vector2(0.8, 1.3), Vector3(0, 0, 1), "mirror", {"id": "bath_mirror"})
	b.floor_dirt("mud", "B", Vector2(0.4, 0.5), Vector2(0.9, 0.9), "floor")

	# ---------- верхний этаж ----------
	b.against("crib", "n", "W", 0.3, {}, 0.45)
	b.prop("bed", b.wp("n", "E", 0.7, 0.9), -90, {"tint": Color(0.7, 0.55, 0.65)})
	b.prop("teddy", b.wp("n", "E", 0.7, 0.9, 0.62) + Vector3(0.3, 0, 0), 30)
	b.prop("rug", b.P("n", 0.5, 0.5), 0, {"w": 2.4, "d": 1.8, "tint": Color(0.6, 0.45, 0.6)})
	b.note_pickup("n1_c", b.P("n", 0.5, 0.5, 0.03), 10, Color(0.95, 0.85, 0.85))
	b.dirt("dust", b.wp("n", "N", 0.5, 0.3, 0.9), Vector2(1.0, 0.5), Vector3.UP, "upstairs")
	b.floor_dirt("debris", "n", Vector2(-1.5, 1.0), Vector2(1.2, 1.0), "upstairs")
	b.floor_dirt("stain", "n", Vector2(1.5, -0.5), Vector2(1.3, 1.3), "upstairs")
	b.against("bed", "m", "E", 0.5, {}, 1.2)
	b.against("wardrobe", "m", "N", 0.3, {}, 0.35)
	b.dirt("dust", b.P("m", 0.5, 0.45, 0.02), Vector2(1.0, 0.8), Vector3.UP, "upstairs")
	b.floor_dirt("stain", "m", Vector2(-1.0, 0.7), Vector2(1.5, 1.2), "upstairs")
	b.floor_dirt("crumbs", "u", Vector2(0.5, 0.0), Vector2(1.6, 0.9), "upstairs")
	Common.bag(L, b.P("m", 0.12, 0.85))
	Common.bucket(L, b.P("w", 0.85, 0.85))
	b.against("toilet", "w", "N", 0.25, {}, 0.3)
	b.against("bathtub", "w", "E", 0.5, {}, 0.45)
	b.floor_dirt("mud", "w", Vector2(0.0, 0.4), Vector2(1.0, 1.0), "upstairs")
	b.against("bookshelf", "k", "N", 0.5, {"seed": 4}, 0.2)   # кабинет (за заклинившей дверью)
	b.prop("table", b.P("k", 0.5, 0.6), 0)

	# ---------- следы (скрыты до конца) ----------
	var kc := b.room_center("K")
	for i in 5:
		var pt := Vector3(kc.x - 1.6 + i * 0.0, 0.02, kc.z + 1.3 - i * 0.65)
		var fp := b.dirt("mud", pt, Vector2(0.55, 0.55), Vector3.UP, "steps", {"id": "fp%d" % i})
		fp.visible = false
		if fp.body:
			fp.body.collision_layer = 0
	b.interact(b.wp("K", "W", 0.5, 0.2, 1.0), Vector3(0.3, 2.0, 1.6), "", Callable())  # заглушка

	# события
	b.trigger(b.P("H", 0.5, 0.5, 1.0), Vector3(3.5, 2.5, 8.0), func():
		L.b.tasks.enter.done = true
		Audio.say("h1_02"))
	b.trigger(b.P("L", 0.5, 0.5, 1.0), Vector3(7, 2.5, 7), func(): _on_living(L))
	b.trigger(b.P("S", 0.5, 0.5, 1.5), Vector3(3, 3, 3), func(): Audio.say("h1_16"))
	b.trigger(b.P("n", 0.5, 0.5, 4.0), Vector3(7, 3, 7), func(): _on_nursery(L))
	b.trigger(b.P("K", 0.5, 0.5, 1.0), Vector3(7, 2.5, 3.5), func(): Audio.say("h1_05b"))

func start(L: Level) -> void:
	L.objective_override = ""
	# телевизор в гостиной уже «заряжен»
	pass

func on_begin(L: Level) -> void:
	L.hud.show_toast("Касайтесь экрана: левый стик — ходьба, справа — камера. Зажмите «Действие», целясь в грязь.")

func _on_living(L: Level) -> void:
	if tv and not L.b.tasks.dust.done and not Game.flag("tv_on"):
		Game.set_flag("tv_on")
		Common.tv_set(L, tv, true)
		L.get_tree().create_timer(2.0).timeout.connect(func(): Audio.say("h1_07"))
		L.get_tree().create_timer(14.0).timeout.connect(func(): Common.tv_set(L, tv, false))

func _on_nursery(L: Level) -> void:
	if not laugh_done:
		laugh_done = true
		Audio.sfx("child_laugh", L.b.P("n", 0.5, 0.5, 1.0), 4.0)
		L.get_tree().create_timer(1.5).timeout.connect(func(): Audio.say("h1_08"))
		L.make_monster("phantom", L.b.P("u", 0.5, 0.5), {"model": "child", "life": 4.0, "vanish_after": 0.5})

func tick(L: Level, delta: float) -> void:
	# мини-скример с диваном: когда отмыто 50% пыли — диван «открывает глаза»
	if not sofa_done and L.b.tasks.dust.patches.size() > 0 and L.task_progress("dust") > 0.45:
		sofa_done = true
		Common.eyes_flash(L, sofa, Vector3(0, 0.75, 0.2), 0.9)
		L.hud.glitch(0.5)
		L.player.shake(0.015, 0.4)
		L.get_tree().create_timer(1.4).timeout.connect(func(): Audio.say("h1_11"))
	# вторая половина: открыть следы
	if not Game.flag("ch1_steps") and L.progress() >= 0.88 and L.b.tasks.trash.done:
		Game.set_flag("ch1_steps")
		_reveal_steps(L)

func _reveal_steps(L: Level) -> void:
	for i in 5:
		var p: DirtPatch = L.b.patches["fp%d" % i]
		p.visible = true
		if p.body:
			p.body.collision_layer = 4
	L.unlock_task("steps")
	Audio.sfx("sting_soft", null, -4.0)
	Audio.say("h1_14")
	L.hud.glitch(0.6)

func on_story_patch(L: Level, p: DirtPatch) -> void:
	if p.patch_id == "ch1_blood":
		Audio.say("h1_19")
		L.reveal_note("n1_t")
		L.hud.flash_screen(0.2)

func on_task_done(L: Level, id: String) -> void:
	match id:
		"dust": Audio.say("h1_04b")
		"floor": Audio.say("h1_10")
		"mirror": Audio.say("h1_17b")
		"trash": Audio.say("h1_13")
		"steps":
			L.unlock_task("leave")
			L.b.tasks.leave.hidden = false
			Audio.sfx("knock", L.b.wp("K", "N", 0.2, 0.2, 1.4), 6.0)
			Audio.sfx("knock", L.b.wp("K", "N", 0.2, 0.2, 1.4), 6.0)
			L.get_tree().create_timer(1.2).timeout.connect(func(): Audio.sfx("knock", L.b.wp("K", "N", 0.2, 0.2, 1.4), 6.0))
			L.hud.flash_screen(0.3)
			L.get_tree().create_timer(2.6).timeout.connect(func(): Audio.say("h1_15"))
			L.objective_override = "• Вернуться к фургону"

func on_note_read(L: Level, id: String) -> void:
	match id:
		"n1_a": Audio.say("h1_05")
		"n1_t": Audio.say("h1_20")

func on_room_first(L: Level, r: String) -> void:
	match r:
		"B": Audio.say("h1_17")
		"u": pass

func on_locked_door(L: Level, d: Door) -> void:
	Audio.say("h1_12")

func finish_gate(L: Level) -> Array:
	if not L.b.tasks.steps.done:
		return [false, "Работа ещё не закончена: дом грязный."]
	return [true, ""]
