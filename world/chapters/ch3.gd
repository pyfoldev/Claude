extends RefCounted
## Глава 3. Особняк Вороновых — они следят.

var shadows: Array = []
var photos_cleaned := 0
var radio_done := false
var gift_taken := false
var mirror_done := 0
var radio_node: Node3D

func build(L: Level) -> void:
	var b := L.b
	var legend := {
		"Y": Common.YARD_SPEC,
		"H": {"name": "Холл", "floor": "floor_dark", "wall": "wall_paper", "light": 0.8, "h": 3.4, "wall_tint": Color(0.6, 0.55, 0.6)},
		"D": {"name": "Столовая", "floor": "floor_wood", "wall": "wall_paper", "light": 0.7, "h": 3.2},
		"K": {"name": "Кухня", "floor": "floor_tile", "wall": "wall_plaster", "light": 0.9},
		"G": {"name": "Библиотека", "floor": "floor_dark", "wall": "wall_peel", "light": 0.6, "wall_tint": Color(0.6, 0.55, 0.5)},
		"C": {"name": "Коридор", "floor": "floor_dark", "wall": "wall_paper", "light": 0.4},
		"W": {"name": "Ванная комната", "floor": "floor_tile", "wall": "wall_blue", "light": 0.6},
		"S": {"name": "Лестница", "floor": "floor_dark", "wall": "wall_paper", "light": 0.4, "ramp": "x+", "rise": 3.0, "h": 5.7},
	}
	b.layout([
		"YYHHDDKK",
		"YYHHDDKK",
		"YYHHGGCC",
		"YYWWGGSS",
	], legend, 0.0, 4.0)
	var up := {
		"n": {"name": "Детская", "floor": "floor_carpet", "wall": "wall_blue", "light": 0.5, "wall_tint": Color(0.8, 0.8, 1.0)},
		"m": {"name": "Спальня Вороновых", "floor": "floor_wood", "wall": "wall_paper", "light": 0.5},
		"u": {"name": "Галерея", "floor": "floor_dark", "wall": "wall_paper", "light": 0.3, "wall_tint": Color(0.55, 0.5, 0.55)},
		"k": {"name": "Зеркальная комната", "floor": "floor_wood", "wall": "wall_grey", "light": 0.4},
	}
	b.layout(["nnmm", "uuuu", "kkk."], up, 3.0, 4.0, Vector2(32, 8))
	b.doors_from(["Y-H", "H-D", "D-K", "H-G", "G-C", "G-S", "H-W", "W-G", "G-D", "K-C", "S-u", "u-n", "u-m", "u-k"])
	b.finish()
	b.spawn = b.P("Y", 0.7, 0.5) + Vector3(0, 0.1, 0)
	b.spawn_yaw = 90.0 + 180.0
	b.task("dust", "Протереть пыль в доме")
	b.task("floor", "Помыть полы")
	b.task("vac", "Пропылесосить ковры")
	b.task("sweep", "Подмести мусор")
	b.task("mirror", "Вымыть зеркала", {})
	b.task("photos", "Отмыть семейные фотографии в галерее (спрей)")
	b.task("trash", "Вынести мусор (3 мешка)", {"manual": true, "need": 3})
	b.task("gift", "Найти «подарок» в детской", {"manual": true})
	Common.yard(L, "Y")
	# холл
	b.prop("rug", b.P("H", 0.5, 0.5), 0, {"w": 3.0, "d": 4.0, "tint": Color(0.5, 0.25, 0.3)})
	b.against("picture", "H", "N", 0.5, {}, 0.0).position.y = 2.0
	b.prop("plant", b.P("H", 0.15, 0.1)); b.prop("plant", b.P("H", 0.85, 0.1))
	b.against("dresser", "H", "W", 0.2, {}, 0.3)
	b.note_pickup("n3_a", b.P("H", 0.15, 0.4, 0.92), 0)
	b.dirt("dust", b.P("H", 0.15, 0.4, 0.92), Vector2(0.9, 0.45), Vector3(0, 1, 0), "dust")
	b.floor_dirt("stain", "H", Vector2(0, 2.2), Vector2(1.5, 1.4), "floor")
	b.floor_dirt("debris", "H", Vector2(-0.8, -1.5), Vector2(1.3, 1.0), "sweep")
	b.dirt("crumbs", b.P("H", 0.5, 0.5, 0.03), Vector2(1.6, 1.4), Vector3.UP, "vac")
	var hm := b.wp("H", "E", 0.5, 0.0, 1.5)
	b.prop("mirror", hm + Vector3(-0.1, 0, 0), 90)
	var hg := b.dirt("glass", hm + Vector3(-0.14, 0, 0), Vector2(0.8, 1.3), Vector3(-1, 0, 0), "mirror")
	Common.hide_wardrobe(L, "H", "S", 0.85, Color(0.35, 0.28, 0.25))
	Common.bag(L, b.P("H", 0.1, 0.9))
	# столовая
	b.prop("table", b.P("D", 0.5, 0.5), 0, {"w": 3.0, "d": 1.2})
	for i in 4:
		b.prop("chair", b.P("D", 0.34 + i * 0.1, 0.38), 0); b.prop("chair", b.P("D", 0.34 + i * 0.1, 0.62), 180)
	b.prop("candle", b.P("D", 0.5, 0.5, 0.77))
	b.note_pickup("n3_b", b.P("D", 0.35, 0.5, 0.78), 20)
	b.dirt("dust", b.P("D", 0.5, 0.5, 0.775), Vector2(2.2, 0.9), Vector3.UP, "dust")
	b.floor_dirt("stain", "D", Vector2(0, 2.6), Vector2(1.6, 1.4), "floor")
	b.against("bookshelf", "D", "W", 0.5, {"seed": 21}, 0.25)
	# кухня
	b.against("counter", "K", "N", 0.4, {"w": 2.8}, 0.35)
	b.against("stove", "K", "N", 0.85, {}, 0.35)
	b.against("fridge", "K", "E", 0.5, {}, 0.4)
	b.prop("table", b.P("K", 0.4, 0.62), 0, {"w": 1.2, "d": 0.8})
	b.floor_dirt("mud", "K", Vector2(0, 1.0), Vector2(1.6, 1.4), "floor")
	b.floor_dirt("debris", "K", Vector2(-1.5, 0), Vector2(1.2, 1.0), "sweep")
	Common.bag(L, b.P("K", 0.1, 0.9)); Common.bucket(L, b.P("K", 0.9, 0.9))
	# библиотека
	b.against("bookshelf", "G", "N", 0.3, {"seed": 2}, 0.2); b.against("bookshelf", "G", "N", 0.7, {"seed": 3}, 0.2)
	b.against("bookshelf", "G", "W", 0.5, {"seed": 4}, 0.2)
	b.prop("armchair", b.P("G", 0.6, 0.6), 200)
	b.note_pickup("n3_c", b.P("G", 0.5, 0.35, 0.0), 12)
	radio_node = b.prop("radio", b.P("G", 0.8, 0.9, 0.0) + Vector3(0, 0.45, 0), 180)
	b.prop("table", b.P("G", 0.8, 0.9), 0, {"w": 0.7, "d": 0.5})
	b.dirt("dust", b.P("G", 0.8, 0.9, 0.775), Vector2(0.55, 0.4), Vector3.UP, "dust")
	b.dirt("dust", b.P("G", 0.6, 0.6, 0.62), Vector2(0.7, 0.7), Vector3.UP, "dust")
	b.dirt("crumbs", b.P("G", 0.5, 0.5, 0.03), Vector2(1.4, 1.2), Vector3.UP, "vac")
	b.floor_dirt("debris", "G", Vector2(1.2, -1.2), Vector2(1.2, 1.0), "sweep")
	# коридор
	b.floor_dirt("mud", "C", Vector2(0, 0), Vector2(1.6, 1.2), "floor")
	b.floor_dirt("debris", "C", Vector2(-2, 0), Vector2(1.2, 1.0), "sweep")
	Common.bag(L, b.P("C", 0.5, 0.15))
	# ванная
	b.against("bathtub", "W", "W", 0.5, {}, 0.45); b.against("toilet", "W", "N", 0.3, {}, 0.3); b.against("washbasin", "W", "N", 0.7, {}, 0.3)
	var wm := b.wp("W", "N", 0.7, 0.0, 1.5)
	b.prop("mirror", wm + Vector3(0, 0, 0.1), 0)
	var wg := b.dirt("glass", wm + Vector3(0, 0, 0.14), Vector2(0.8, 1.3), Vector3(0, 0, 1), "mirror", {"story": true, "id": "m_bath"})
	b.floor_dirt("stain", "W", Vector2(0, 0.6), Vector2(1.2, 1.2), "floor")
	# верх: галерея с фото
	for i in 4:
		var fp := b.wp("u", "N", 0.14 + i * 0.24, 0.0, 1.55) + Vector3(0, 0, 0.1)
		b.prop("picture", fp, 0, {"c": Color(0.28, 0.25, 0.22)})
		var ph := b.dirt("glass", fp + Vector3(0, 0, 0.04), Vector2(0.55, 0.38), Vector3(0, 0, 1), "photos", {"story": true, "id": "photo%d" % i})
		ph.kind = "blood"
		ph.mat.set_shader_parameter("dirt_color", Color(0.15, 0.1, 0.07))
	b.floor_dirt("mud", "u", Vector2(0, 0), Vector2(1.6, 1.2), "floor")
	b.floor_dirt("crumbs", "u", Vector2(4.0, 0.0), Vector2(1.2, 1.0), "vac")
	# детская
	b.against("crib", "n", "N", 0.3, {}, 0.45)
	b.prop("bed", b.wp("n", "E", 0.7, 0.9), -90, {"tint": Color(0.7, 0.55, 0.65)})
	b.prop("rug", b.P("n", 0.5, 0.55), 0, {"w": 2.4, "d": 1.8, "tint": Color(0.5, 0.55, 0.7)})
	var teddy := b.prop("teddy", b.P("n", 0.5, 0.55, 0.02), 0)
	b.interact(b.P("n", 0.5, 0.55, 0.2), Vector3(0.5, 0.5, 0.5), "Взять «подарок»", func(p): _gift(L, teddy))
	b.note_pickup("n3_t2", b.P("n", 0.5, 0.55, 0.03) + Vector3(0.2, 0, 0.1), 0, Color(0.25, 0.22, 0.2))
	L.hide_note_later("n3_t2")
	b.dirt("dust", b.wp("n", "N", 0.7, 0.3, 0.2), Vector2(1.0, 0.5), Vector3.UP, "dust")
	b.floor_dirt("debris", "n", Vector2(-1.5, 1.0), Vector2(1.2, 1.0), "sweep")
	# спальня
	b.against("bed", "m", "E", 0.5, {}, 1.2)
	Common.hide_wardrobe(L, "m", "N", 0.3)
	b.dirt("dust", b.P("m", 0.5, 0.45, 0.02), Vector2(1.0, 0.8), Vector3.UP, "dust")
	b.floor_dirt("stain", "m", Vector2(-1.0, 0.7), Vector2(1.5, 1.2), "floor")
	Common.bag(L, b.P("m", 0.12, 0.85))
	# зеркальная комната
	for i in 3:
		var mm := b.wp("k", "N", 0.2 + i * 0.3, 0.0, 1.4) + Vector3(0, 0, 0.1)
		b.prop("mirror", mm, 0)
		var mgl := b.dirt("glass", mm + Vector3(0, 0, 0.04), Vector2(0.8, 1.3), Vector3(0, 0, 1), "mirror", {"story": true, "id": "km%d" % i})
	b.note_pickup("n3_t1", b.wp("k", "N", 0.5, 0.35, 0.0) + Vector3(0, 0.02, 0), 0, Color(0.25, 0.22, 0.2))
	L.hide_note_later("n3_t1")
	b.prop("rug", b.P("k", 0.5, 0.6), 0, {"w": 2.4, "d": 1.4, "tint": Color(0.3, 0.3, 0.4)})
	# тени-ангелы
	for sp in [b.P("H", 0.5, 0.15), b.P("u", 0.5, 0.5, 0.0)]:
		pass
	b.trigger(b.P("H", 0.5, 0.5, 1.0), Vector3(7, 3, 15), func(): Audio.say("h3_02"))
	b.trigger(b.P("G", 0.5, 0.5, 1.0), Vector3(7, 3, 7), func(): _radio(L))
	b.trigger(b.P("u", 0.5, 0.5, 4.0), Vector3(15, 3, 3), func(): _gallery(L))

func on_begin(L: Level) -> void:
	Game.note("Тени двигаются, пока вы не смотрите. Держите их в поле зрения или светите фонарём.")

func _radio(L: Level) -> void:
	if radio_done:
		return
	radio_done = true
	Audio.sfx("radio_static", L.b.P("G", 0.8, 0.9, 1.0), 3.0)
	L.get_tree().create_timer(2.0).timeout.connect(func(): Audio.say("r3_name", true))
	L.get_tree().create_timer(5.5).timeout.connect(func(): Audio.say("h3_05"))
	L.player.shake(0.02, 0.6)
	L.hud.glitch(0.8)
	Game.sanity -= 8.0

func _gallery(L: Level) -> void:
	if Game.flag("gal"):
		return
	Game.set_flag("gal")
	Audio.say("h3_08")
	var m := L.b.spawn_monster("shadow", L.b.P("u", 0.95, 0.5, 0.0), {"speed": 2.0})
	shadows.append(m)

func _gift(L: Level, teddy: Node3D) -> void:
	if gift_taken:
		return
	gift_taken = true
	teddy.queue_free()
	L.reveal_note("n3_t2")
	L.complete_task("gift")
	Audio.say("h3_12")
	Audio.sfx("sting", null, 0.0)
	L.hud.flash_screen(0.4)
	# три тени оживают, двери захлопываются
	await L.get_tree().create_timer(2.5).timeout
	for d in L.b.doors:
		var n: Door = d.node
		if n and d.a in ["u", "n", "m", "k"] and n.is_open:
			n.set_open(false, true)
	Common.blackout(L, true)
	await L.get_tree().create_timer(1.5).timeout
	Common.blackout(L, false)
	for pos in [L.b.P("u", 0.9, 0.5), L.b.P("S", 0.5, 0.5, 3.0), L.b.P("C", 0.5, 0.5)]:
		L.b.spawn_monster("shadow", pos, {"speed": 2.4})
	Audio.say("h3_13")
	L.objective_override = "• Выбраться из особняка (не поворачиваться спиной к теням)"
	Game.set_flag("ch3_gift")

func on_story_patch(L: Level, p: DirtPatch) -> void:
	if p.patch_id.begins_with("photo"):
		photos_cleaned += 1
		L.hud.flash_screen(0.3)
		L.hud.glitch(0.6)
		Audio.sfx("sting_soft", null, -2.0)
		Game.sanity -= 4.0
		if photos_cleaned == 1:
			Audio.say("h3_09")
		elif photos_cleaned == 4:
			Audio.say("h3_10")
	elif p.patch_id.begins_with("km"):
		mirror_done += 1
		Audio.sfx("sting_soft", null, -4.0)
		L.hud.glitch(0.8)
		L.make_monster("phantom", p.global_position + Vector3(0, -1.0, 1.6), {"model": "shadow", "life": 3.0, "vanish_after": 0.6})
		Game.sanity -= 5.0
		if mirror_done == 3:
			L.reveal_note("n3_t1")
	elif p.patch_id == "m_bath":
		Audio.say("h3_07")
		L.make_monster("phantom", p.global_position + Vector3(0, -1.0, 1.5), {"model": "shadow", "life": 3.0, "vanish_after": 0.5})
		Game.sanity -= 4.0

func on_note_read(L: Level, id: String) -> void:
	match id:
		"n3_a": Audio.say("h3_03")
		"n3_t1": Audio.say("h3_14")
		"n3_t2": Audio.say("h3_15")

func on_task_done(L: Level, id: String) -> void:
	if id == "trash":
		Audio.say("h3_06")

func finish_gate(L: Level) -> Array:
	if not gift_taken:
		return [false, "Сначала загляните в детскую: там что-то оставили."]
	return Common.gate(L, 0.5)
