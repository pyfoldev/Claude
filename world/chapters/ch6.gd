extends RefCounted
## Глава 6. Изнанка — мир за порталом: дом из чёрной жижи, Артём в стенах, три печати.

var seals := 0
var crawlers_wave := 0
var host: Monster
var respawn_t := 0.0
var radio_said := 0
var corridor_open := false

func build(L: Level) -> void:
	var b := L.b
	L.set_ambient(Color(0.25, 0.15, 0.2), 0.6)
	var g := Color(0.5, 0.35, 0.4)
	var legend := {
		"H": {"name": "Прихожая Изнанки", "floor": "floor_dark", "wall": "wall_peel", "light": 0.5, "light_color": Color(0.9, 0.3, 0.3), "wall_tint": g, "floor_tint": g},
		"K": {"name": "Кухня Изнанки", "floor": "floor_tile", "wall": "wall_peel", "light": 0.5, "light_color": Color(0.9, 0.3, 0.3), "wall_tint": g},
		"L": {"name": "Гостиная Изнанки", "floor": "floor_dark", "wall": "wall_paper", "light": 0.45, "light_color": Color(0.9, 0.3, 0.3), "wall_tint": g},
		"C": {"name": "Длинный коридор", "floor": "floor_dark", "wall": "wall_peel", "light": 0.3, "light_color": Color(0.8, 0.2, 0.3), "wall_tint": g},
		"D": {"name": "Спальня Изнанки", "floor": "floor_carpet", "wall": "wall_blue", "light": 0.4, "light_color": Color(0.8, 0.2, 0.35), "wall_tint": g},
		"E": {"name": "Зал Печатей", "floor": "floor_dark", "wall": "wall_brick", "light": 0.5, "light_color": Color(0.9, 0.5, 0.2), "h": 4.0, "wall_tint": g},
		"S": {"name": "Лестница", "floor": "floor_dark", "wall": "wall_peel", "light": 0.3, "light_color": Color(0.8, 0.2, 0.3), "ramp": "x+", "rise": 3.0, "h": 5.7, "wall_tint": g},
	}
	b.layout(["HHKKLL", "HHKKLL", "CCCCDD", "EEEE.."], legend, 0.0, 4.0)
	var up := {
		"n": {"name": "Детская Изнанки", "floor": "floor_carpet", "wall": "wall_blue", "light": 0.4, "light_color": Color(0.8, 0.3, 0.5), "wall_tint": g},
		"u": {"name": "Верхний коридор", "floor": "floor_dark", "wall": "wall_peel", "light": 0.25, "light_color": Color(0.8, 0.2, 0.3), "wall_tint": g},
		"m": {"name": "Комната Артёма", "floor": "floor_wood", "wall": "wall_grey", "light": 0.5, "light_color": Color(0.4, 0.8, 0.5)},
	}
	b.layout(["nnmm", "uuuu"], up, 3.0, 4.0, Vector2(32, 4))
	b.room("T", Rect2(24, 8, 8, 4), 0.0, {"name": "Подъём", "floor": "floor_dark", "wall": "wall_peel", "light": 0.3, "light_color": Color(0.8, 0.2, 0.3), "ramp": "x+", "rise": 3.0, "h": 5.7, "wall_tint": g})
	b.doors_from(["H-K", "K-L", "H-C", "K-C", "L-D", "C-D", "C-E", "D-T", "T-u", "u-n", "u-m"])
	b.finish()
	b.spawn = b.P("H", 0.5, 0.5) + Vector3(0, 0.1, 0)
	b.spawn_yaw = 0.0
	b.task("seals", "Найти печати трёх семей (0/3)", {"manual": true, "need": 3})
	b.task("grime", "Отмыть чёрную жижу (спреем)")
	b.task("door", "Открыть дверь в Коридор домов", {"manual": true, "hidden": true})
	Common.supply(L, b.P("H", 0.2, 0.2), 0)
	Common.bucket(L, b.P("H", 0.8, 0.2))
	# жижа на полу и стенах
	for r in ["H", "K", "L", "C", "D", "E", "n", "u"]:
		var n := 3 if r in ["C", "u"] else 2
		for i in n:
			b.floor_dirt("grime", r, Vector2(-1.2 + i * 1.6, (i % 2) * 0.8 - 0.4), Vector2(1.6, 1.4), "grime")
	b.against("table", "K", "N", 0.4, {"w": 1.6}, 0.4)
	b.prop("sofa", b.P("L", 0.5, 0.25), 180, {"tint": Color(0.3, 0.2, 0.25)})
	b.prop("tv", b.P("L", 0.5, 0.9), 180)
	b.prop("rug", b.P("L", 0.5, 0.6), 0, {"w": 3.0, "d": 2.0, "tint": Color(0.3, 0.1, 0.12)})
	b.against("bed", "D", "W", 0.5, {"tint": Color(0.3, 0.2, 0.25)}, 1.1)
	Common.hide_wardrobe(L, "D", "N", 0.7, Color(0.25, 0.2, 0.2))
	Common.hide_wardrobe(L, "H", "W", 0.8, Color(0.25, 0.2, 0.2))
	# печати (ценные вещи семей)
	_seal(L, "Громовых: музыкальная шкатулка", b.P("K", 0.5, 0.5, 0.78) , "teddy", 1)
	_seal(L, "Вороновых: осколок зеркала", b.P("n", 0.5, 0.5, 0.0), "tape", 2)
	_seal(L, "Коммуналки: ключ от чужой двери", b.P("D", 0.8, 0.8, 0.0), "key", 3)
	# Артём
	b.prop("radio", b.P("m", 0.5, 0.5, 0.0), 0)
	b.note_pickup("n6_t2", b.P("m", 0.3, 0.5, 0.0), 0, Color(0.2, 0.2, 0.25))
	b.note_pickup("n6_t1", b.P("E", 0.5, 0.2, 0.0), 0, Color(0.25, 0.22, 0.2))
	b.prop("tape", b.P("m", 0.3, 0.5, 0.0))
	# дверь в Коридор домов: колонна в зале печатей
	var door_it: Interactable = b.interact(b.P("E", 0.5, 0.95, 1.2), Vector3(2.0, 2.4, 0.6), "Дверь в Коридор домов", func(p): _door(L))
	b.prop("bars", b.P("E", 0.5, 0.95), 0)
	b.trigger(b.P("H", 0.5, 0.5, 1.0), Vector3(7, 2.5, 7), func(): Audio.say("h6_02"))
	b.trigger(b.P("C", 0.5, 0.5, 1.0), Vector3(15, 2.5, 3.5), func(): Audio.say("h6_05"))
	b.trigger(b.P("m", 0.5, 0.5, 4.0), Vector3(7, 3, 3.5), func(): _artem_room(L))
	host = null

func _seal(L: Level, label: String, pos: Vector3, kind: String, n: int) -> void:
	var node := L.b.prop(kind, pos, 0)
	var lt := OmniLight3D.new()
	lt.light_color = Color(1.0, 0.8, 0.4); lt.light_energy = 0.6; lt.omni_range = 3.0
	lt.position = pos + Vector3(0, 0.4, 0)
	L.add_child(lt)
	L.b.interact(pos + Vector3(0, 0.3, 0), Vector3(0.6, 0.6, 0.6), "Взять печать: " + label, func(p):
		node.queue_free(); lt.queue_free()
		seals += 1
		L.b.tasks.seals.text = "Найти печати трёх семей (%d/3)" % seals
		L.add_manual("seals")
		Audio.sfx("note_true", null, 0.0)
		Audio.say("h6_seal%d" % n)
		_wave(L)
		if seals >= 3:
			L.unlock_task("door")
			L.objective_override = "• Вернуться в Зал Печатей и открыть дверь"
			Game.set_flag("seals"))

func _wave(L: Level) -> void:
	for i in 2 + seals:
		var rooms: Array = L.b.rooms.keys().filter(func(r): return L.b.room_center(r).distance_to(L.player.global_position) > 10.0)
		if rooms.is_empty():
			return
		var r: String = rooms[randi() % rooms.size()]
		var m := L.b.spawn_monster("crawler", L.b.room_center(r), {"speed": 3.0 + seals * 0.3})
	Audio.sfx("scream_far", L.player.global_position + Vector3(8, 0, 0), 0.0)

func _artem_room(L: Level) -> void:
	if Game.flag("artem_room"):
		return
	Game.set_flag("artem_room")
	Audio.say("a6_01", true)
	L.get_tree().create_timer(9.0).timeout.connect(func(): Audio.say("a6_02"))
	L.get_tree().create_timer(19.0).timeout.connect(func(): Audio.say("a6_03"))
	L.get_tree().create_timer(30.0).timeout.connect(func(): Audio.say("h6_08"))

func _door(L: Level) -> void:
	if seals < 3:
		Game.note("Дверь запечатана. Нужны три печати.")
		return
	if corridor_open:
		return
	corridor_open = true
	L.complete_task("door")
	Audio.sfx("door_open", null, 2.0)
	Audio.say("h6_09")
	L.get_tree().create_timer(3.5).timeout.connect(func(): L.end_chapter())

func tick(L: Level, delta: float) -> void:
	# жижа «зарастает» заново, если оставить её надолго (давление на игрока)
	respawn_t += delta
	if respawn_t > 70.0:
		respawn_t = 0.0
		var cands: Array = []
		for pid in L.b.patches:
			var p: DirtPatch = L.b.patches[pid]
			if p.done and p.kind == "grime" and p.global_position.distance_to(L.player.global_position) > 8.0:
				cands.append(p)
		if not cands.is_empty():
			var p2: DirtPatch = cands[randi() % cands.size()]
			p2.done = false
			p2.amount = 0.6
			p2._apply()
			Game.note("Жижа расползается обратно…")

func on_note_read(L: Level, id: String) -> void:
	match id:
		"n6_t1": Audio.say("h6_06")
		"n6_t2": Audio.say("h6_07")

func finish_gate(L: Level) -> Array:
	return [false, ""]
