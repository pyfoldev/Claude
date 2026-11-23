extends RefCounted
## Глава 4. Тот же дом — ты уже был здесь. Хозяин.

var host: Monster
var clock_nodes: Array = []
var pages := 0
var host_spawned := false
var chase_started := false

func build(L: Level) -> void:
	var b := L.b
	var legend := {
		"Y": Common.YARD_SPEC,
		"H": {"name": "Прихожая", "floor": "floor_wood", "wall": "wall_paper", "light": 0.55},
		"K": {"name": "Кухня", "floor": "floor_tile", "wall": "wall_plaster", "wall_tint": Color(0.8, 0.8, 0.7), "light": 0.7},
		"P": {"name": "Кладовая", "floor": "floor_lino", "wall": "wall_grey", "light": 0.3},
		"L": {"name": "Гостиная", "floor": "floor_wood", "wall": "wall_paper", "light": 0.6},
		"R": {"name": "Столовая", "floor": "floor_wood", "wall": "wall_peel", "light": 0.5},
		"C": {"name": "Коридор", "floor": "floor_dark", "wall": "wall_paper", "light": 0.35},
		"D": {"name": "Спальня", "floor": "floor_carpet", "wall": "wall_blue", "light": 0.45},
		"B": {"name": "Ванная", "floor": "floor_tile", "wall": "wall_plaster", "wall_tint": Color(0.7, 0.8, 0.8), "light": 0.5},
		"X": {"name": "Дверь в подвал", "floor": "floor_conc", "wall": "wall_grey", "light": 0.0, "dark": true},
		"S": {"name": "Лестница", "floor": "floor_dark", "wall": "wall_paper", "light": 0.3, "ramp": "x+", "rise": 3.0, "h": 5.7},
	}
	b.layout(["YYHKKPP.", "YYHLLRR.", "YYHLLRR.", "YYCCCCSS", "YYXDDB.."], legend, 0.0, 4.0)
	var up := {
		"n": {"name": "Детская", "floor": "floor_carpet", "wall": "wall_blue", "light": 0.4},
		"m": {"name": "Родительская", "floor": "floor_wood", "wall": "wall_paper", "light": 0.4},
		"u": {"name": "Верхний коридор", "floor": "floor_dark", "wall": "wall_paper", "light": 0.25},
		"k": {"name": "Кабинет", "floor": "floor_wood", "wall": "wall_grey", "light": 0.3},
		"w": {"name": "Ванная наверху", "floor": "floor_tile", "wall": "wall_plaster", "light": 0.4},
	}
	b.layout(["nnmm", "nnmm", "uuuu", "kkww"], up, 3.0, 4.0, Vector2(32, 4))
	b.doors_from(["Y-H", "H-K", "H-L", "H-C", "K-P", "K-L", "L-R", "P-R", "L-C", "R-C", "C-D", "C-B", "C-S", "C-X", "S-u", "u-n", "u-m", "u-k", "u-w"])
	b.finish()
	L.door_between("C", "X").set_locked(true, "")
	L.door_between("C", "X").locked = false
	b.spawn = b.P("Y", 0.7, 0.2) + Vector3(0, 0.1, 0)
	b.spawn_yaw = 0.0
	b.task("pages", "Найти страницы дневника Артёма (0/5)", {"manual": true, "need": 5})
	b.task("dust", "Протереть пыль", {"optional": true})
	b.task("floor", "Помыть пол", {"optional": true})
	b.task("sweep", "Подмести мусор", {"optional": true})
	b.task("run", "Добежать до фургона", {"manual": true, "hidden": true})
	Common.yard(L, "Y", "none")
	b.tasks["none"] = {"id": "none", "text": "", "patches": [], "optional": true, "manual": true, "done": false, "hidden": true, "count": 0, "need": 0}
	# прихожая
	b.against("dresser", "H", "W", 0.5, {}, 0.3)
	b.note_pickup("n4_a", b.wp("H", "W", 0.5, 0.35, 0.92), 0)
	var badge := b.prop("badge", b.wp("H", "W", 0.62, 0.35, 0.92), 30)
	b.interact(b.wp("H", "W", 0.62, 0.35, 1.0), Vector3(0.3, 0.3, 0.3), "Осмотреть бейдж", func(p):
		Audio.say("h4_04")
		Game.note("«А. Ситников, ЧистоДом». Бейдж Артёма."))
	b.floor_dirt("debris", "H", Vector2(0.3, 1.5), Vector2(1.4, 1.2), "sweep")
	b.floor_dirt("mud", "H", Vector2(0, 0), Vector2(1.2, 1.2), "floor")
	var c1 := b.prop("clock", b.wp("H", "E", 0.5, 0.0, 2.0) + Vector3(-0.1, 0, 0), 90)
	c1.rotation_degrees = Vector3(0, 90, 0)
	clock_nodes.append(c1)
	b.prop("plant", b.P("H", 0.85, 0.9))
	# кухня
	b.against("counter", "K", "N", 0.35, {"w": 2.4}, 0.35)
	b.against("stove", "K", "N", 0.8, {}, 0.35)
	b.against("fridge", "K", "E", 0.3, {}, 0.4)
	b.prop("table", b.P("K", 0.5, 0.62), 90)
	b.prop("chair", b.P("K", 0.5, 0.45), 0); b.prop("chair", b.P("K", 0.62, 0.8), 160)
	var drawer := b.interact(b.wp("K", "N", 0.35, 0.5, 0.8), Vector3(1.0, 0.4, 0.4), "Открыть ящик", func(p): pass)
	Common.pickup(L, "paper", b.P("K", 0.5, 0.62, 0.77), "Взять страницу дневника", func(p): _page(L, "n4_p1"), {"c": Color(0.2, 0.2, 0.25)})
	var thermos := b.prop("crate", b.P("K", 0.45, 0.62, 0.77), 0, {"s": 0.001})
	Props.cyl(thermos, 0.05, 0.25, Vector3(0, 0.12, 0), Mats.color(Color(0.2, 0.5, 0.3), 0.3, 0, 0.7))
	b.interact(b.P("K", 0.45, 0.62, 0.9), Vector3(0.3, 0.4, 0.3), "Осмотреть термос", func(p):
		Audio.say("h4_05")
		Game.note("Мой термос. С моими инициалами. Я оставлял его в машине."))
	b.floor_dirt("stain", "K", Vector2(-1.0, 0.8), Vector2(1.6, 1.4), "floor")
	var c2 := b.prop("clock", b.wp("K", "S", 0.8, 0.0, 2.0) + Vector3(0, 0, 0.1), 180)
	clock_nodes.append(c2)
	# гостиная
	b.prop("sofa", b.P("L", 0.5, 0.2), 180, {"tint": Color(0.45, 0.4, 0.38)})   # диван «переставлен»
	b.prop("table", b.P("L", 0.5, 0.55), 90, {"w": 1.1, "d": 0.7})
	b.prop("tv", b.P("L", 0.5, 0.92), 180)
	b.prop("armchair", b.P("L", 0.15, 0.7), 90)
	b.prop("rug", b.P("L", 0.5, 0.55), 0, {"w": 3.2, "d": 2.4})
	b.dirt("dust", b.P("L", 0.5, 0.55, 0.775), Vector2(1.0, 0.65), Vector3.UP, "dust")
	b.dirt("crumbs", b.P("L", 0.5, 0.55, 0.03), Vector2(1.4, 1.0), Vector3.UP, "dust")
	Common.hide_wardrobe(L, "L", "W", 0.2, Color(0.4, 0.32, 0.26))
	# столовая / кладовая / коридор
	b.prop("table", b.P("R", 0.5, 0.5), 0, {"w": 2.0, "d": 1.0})
	b.prop("chair", b.P("R", 0.4, 0.3), 30); b.prop("chair", b.P("R", 0.6, 0.7), 200)
	b.dirt("dust", b.P("R", 0.5, 0.5, 0.77), Vector2(1.5, 0.8), Vector3.UP, "dust")
	b.against("bookshelf", "P", "N", 0.5, {"seed": 11}, 0.2)
	Common.pickup(L, "paper", b.P("P", 0.5, 0.6, 0.0), "Взять страницу дневника", func(p): _page(L, "n4_p2"), {"c": Color(0.2, 0.2, 0.25)})
	b.floor_dirt("debris", "C", Vector2(-3.0, 0), Vector2(1.3, 1.0), "sweep")
	b.floor_dirt("mud", "C", Vector2(1.0, 0.2), Vector2(1.4, 1.0), "floor")
	# спальня
	Common.hide_bed(L, "D", "W", 0.5)
	Common.hide_wardrobe(L, "D", "N", 0.7)
	Common.pickup(L, "paper", b.P("D", 0.8, 0.8, 0.0), "Взять страницу дневника", func(p): _page(L, "n4_p4"), {"c": Color(0.2, 0.2, 0.25)})
	# ванная
	b.against("toilet", "B", "N", 0.25, {}, 0.3); b.against("bathtub", "B", "W", 0.4, {}, 0.45)
	# подвальный тамбур
	Common.pickup(L, "paper", b.P("X", 0.5, 0.5, 0.0), "Взять страницу дневника", func(p): _page(L, "n4_p5"), {"c": Color(0.2, 0.2, 0.25)})
	b.prop("box", b.P("X", 0.2, 0.2), 20)
	# верх
	b.against("crib", "n", "W", 0.3, {}, 0.45)
	b.prop("bed", b.wp("n", "E", 0.7, 0.9), -90, {"tint": Color(0.7, 0.55, 0.65)})
	Common.pickup(L, "paper", b.P("n", 0.4, 0.4, 0.0), "Взять страницу дневника", func(p): _page(L, "n4_p3"), {"c": Color(0.2, 0.2, 0.25)})
	Common.hide_wardrobe(L, "m", "N", 0.3)
	b.against("bed", "m", "E", 0.5, {}, 1.2)
	b.against("bathtub", "w", "E", 0.5, {}, 0.45); b.against("toilet", "w", "N", 0.25, {}, 0.3)
	b.against("bookshelf", "k", "N", 0.5, {"seed": 4}, 0.2)
	L.door_between("u", "k").jammed = true
	# события
	b.trigger(b.P("H", 0.5, 0.5, 1.0), Vector3(3.5, 2.5, 8.0), func(): Audio.say("h4_02"))
	b.trigger(b.P("C", 0.5, 0.5, 1.0), Vector3(20, 2.5, 3.5), func(): _spawn_host(L))
	b.trigger(b.P("X", 0.5, 0.5, 1.0), Vector3(3.5, 2.5, 3.5), func(): _cellar(L))

func _page(L: Level, id: String) -> void:
	pages += 1
	L.read_note(id)
	L.b.tasks.pages.text = "Найти страницы дневника Артёма (%d/5)" % pages
	L.add_manual("pages")

func on_note_read(L: Level, id: String) -> void:
	match id:
		"n4_p1": Audio.say("h4_06")
		"n4_p2": Audio.say("h4_07")
		"n4_p3": Audio.say("h4_08")
		"n4_p4": Audio.say("h4_09")
		"n4_p5": _final_page(L)
		"n4_a": Audio.say("h4_03")

func _spawn_host(L: Level) -> void:
	if host_spawned:
		return
	host_spawned = true
	Audio.say("h4_10")
	host = L.b.spawn_monster("host", L.b.P("u", 0.5, 0.5, 0.0), {"state": "patrol"})
	L.hud.glitch(0.8)
	Audio.sfx("host_roar", L.b.P("u", 0.5, 0.5), 0.0)
	L.objective_override = ""

func _final_page(L: Level) -> void:
	if chase_started:
		return
	chase_started = true
	Audio.say("h4_12")
	await L.get_tree().create_timer(2.0).timeout
	if host == null or not is_instance_valid(host):
		_spawn_host(L)
	host.global_position = L.b.P("C", 0.1, 0.5, 0.0)
	host.state = "chase"
	host.last_seen = L.player.global_position
	host.opts["chase_speed"] = 3.4
	L.objective_override = "• Добежать до фургона!"
	L.b.tasks.run.hidden = false
	Audio.sfx("host_roar", host.global_position, 4.0)
	Common.blackout(L, true)
	await L.get_tree().create_timer(0.8).timeout
	Common.blackout(L, false)

func _cellar(L: Level) -> void:
	if not Game.flag("cellar"):
		Game.set_flag("cellar")
		Audio.say("h4_11")

func tick(L: Level, delta: float) -> void:
	for c in clock_nodes:
		var h: Node3D = c.get_node_or_null("hour")
		var m: Node3D = c.get_node_or_null("min")
		if m:
			m.rotation.z += delta * 2.5
		if h:
			h.rotation.z += delta * 0.4

func finish_gate(L: Level) -> Array:
	if pages < 5:
		return [false, "Работа не закончена. Найдите страницы дневника."]
	return [true, ""]
