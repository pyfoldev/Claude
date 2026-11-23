extends RefCounted
## Глава 7. Коридор домов — голос дочери, Мать Громовых, погоня.

var mother: Monster
var host: Monster
var freed := false
var chase := false
var alisa_door: Door
var escaped := false

func build(L: Level) -> void:
	var b := L.b
	L.set_ambient(Color(0.2, 0.12, 0.18), 0.55)
	var g := Color(0.55, 0.4, 0.45)
	var red := Color(0.9, 0.3, 0.3)
	var legend := {
		"A": {"name": "Коридор домов", "floor": "floor_dark", "wall": "wall_paper", "light": 0.45, "light_color": red, "wall_tint": g, "h": 3.2},
		"1": {"name": "Прихожая Громовых", "floor": "floor_wood", "wall": "wall_paper", "light": 0.5, "light_color": red, "wall_tint": g},
		"2": {"name": "Квартира на Садовой", "floor": "floor_lino", "wall": "wall_peel", "light": 0.5, "light_color": red, "wall_tint": g},
		"3": {"name": "Детская Вороновых", "floor": "floor_carpet", "wall": "wall_blue", "light": 0.5, "light_color": Color(0.9, 0.5, 0.6), "wall_tint": g},
		"4": {"name": "Комната Алисы", "floor": "floor_carpet", "wall": "wall_blue", "light": 0.7, "light_color": Color(1.0, 0.85, 0.7), "wall_tint": Color(0.9, 0.8, 0.9)},
		"5": {"name": "Зеркальная комната", "floor": "floor_wood", "wall": "wall_grey", "light": 0.4, "light_color": red, "wall_tint": g},
		"E": {"name": "Лифт вниз", "floor": "floor_conc", "wall": "wall_brick", "light": 0.6, "light_color": Color(1.0, 0.6, 0.3), "wall_tint": g},
	}
	b.layout(["AAAAAAAAAAE", "1122334455."], legend, 0.0, 4.0)
	b.doors_from(["A-1", "A-2", "A-3", "A-4", "A-5", "A-E"])
	b.finish()
	alisa_door = L.door_between("A", "4")
	L.door_between("A", "E").set_locked(true, "lift")
	b.spawn = b.P("A", 0.03, 0.5) + Vector3(0, 0.1, 0)
	b.spawn_yaw = -90.0
	b.task("mother", "Выслушать Мать Громовых", {"manual": true})
	b.task("grime", "Отмыть Мать Громовых (спрей)")
	b.task("lift", "Добраться до лифта", {"manual": true, "hidden": true})
	Common.supply(L, b.P("A", 0.06, 0.2), 0)
	# комнаты
	b.against("dresser", "1", "N", 0.5, {}, 0.3); b.prop("rug", b.P("1", 0.5, 0.5), 0, {"w": 2.4, "d": 1.8})
	Common.hide_wardrobe(L, "1", "W", 0.75, Color(0.3, 0.25, 0.22))
	b.against("bed", "2", "W", 0.5, {}, 1.1); b.against("fridge", "2", "E", 0.3, {}, 0.4)
	Common.hide_wardrobe(L, "2", "N", 0.6, Color(0.3, 0.25, 0.22))
	b.against("crib", "3", "N", 0.3, {}, 0.45); b.prop("rug", b.P("3", 0.5, 0.55), 0, {"w": 2.4, "d": 1.8})
	b.against("bed", "4", "E", 0.5, {"tint": Color(0.9, 0.6, 0.8)}, 1.1)
	b.prop("teddy", b.P("4", 0.6, 0.5, 0.0))
	b.prop("rug", b.P("4", 0.4, 0.55), 0, {"w": 2.0, "d": 1.6, "tint": Color(0.8, 0.6, 0.8)})
	for i in 4:
		var mm := b.wp("5", "N", 0.15 + i * 0.23, 0.0, 1.4) + Vector3(0, 0, 0.1)
		b.prop("mirror", mm, 0)
	b.prop("rug", b.P("5", 0.5, 0.6), 0, {"w": 2.4, "d": 1.4, "tint": Color(0.3, 0.3, 0.4)})
	b.prop("lamp", b.P("E", 0.5, 0.5), 0)
	# мать: фигура в комнате 3
	mother = b.spawn_monster("npc", b.P("3", 0.75, 0.6), {"model": "mother", "face_player": true})
	b.dirt("grime", b.P("3", 0.75, 0.6, 1.0) + Vector3(-0.7, 0.0, 0.0), Vector2(0.9, 1.2), Vector3(1, 0, 0), "grime", {"id": "mg0"})
	b.dirt("grime", b.P("3", 0.75, 0.6, 0.5) + Vector3(0.0, 0.0, -0.7), Vector2(0.9, 1.0), Vector3(0, 0, 1), "grime", {"id": "mg1"})
	b.dirt("grime", b.P("3", 0.75, 0.6, 0.02), Vector2(1.6, 1.6), Vector3.UP, "grime", {"id": "mg2"})
	b.note_pickup("n7_t1", b.P("3", 0.6, 0.6, 0.0), 0, Color(0.25, 0.22, 0.2))
	L.hide_note_later("n7_t1")
	# ловушка: «Алиса» за дверью 4
	b.trigger(b.P("A", 0.5, 0.5, 1.0), Vector3(4, 2.5, 4), func(): _alisa_call(L), true)
	b.trigger(b.P("3", 0.5, 0.5, 1.0), Vector3(7, 2.5, 3.5), func(): _mother_scene(L))
	alisa_door.opened.connect(func(d): _alisa_trap(L))

func on_begin(L: Level) -> void:
	Audio.say("a7_01")
	L.get_tree().create_timer(6.0).timeout.connect(func(): Audio.say("h7_02"))

func _alisa_call(L: Level) -> void:
	await L.get_tree().create_timer(14.0).timeout
	if escaped or L.ended:
		return
	Audio.say("a7_02")
	Audio.sfx("knock", alisa_door.global_position, 0.0)
	L.get_tree().create_timer(9.0).timeout.connect(func(): Audio.say("h7_03"))

func _alisa_trap(L: Level) -> void:
	if escaped:
		return
	# дверь открыта «на голос» — это не Алиса
	Audio.say("hh_alisa", true)
	var m := L.b.spawn_monster("shadow", L.b.P("4", 0.5, 0.5), {"speed": 5.0})
	m.state = "stalk"
	m.catch_dist = 5.0
	L.get_tree().create_timer(1.2).timeout.connect(func(): if is_instance_valid(m): m.catch_player())

func _mother_scene(L: Level) -> void:
	if Game.flag("mother_met"):
		return
	Game.set_flag("mother_met")
	Audio.say("m7_01", true)
	L.get_tree().create_timer(8.0).timeout.connect(func(): Audio.say("m7_02"))
	L.get_tree().create_timer(18.0).timeout.connect(func(): Audio.say("m7_03"))
	L.objective_override = "• Отмыть Мать Громовых (спрей): она покрыта жижей"

func on_task_done(L: Level, id: String) -> void:
	if id == "grime" and not freed:
		freed = true
		L.hud.flash_screen(0.5)
		Audio.sfx("note_true", null, 0.0)
		L.reveal_note("n7_t1")
		Audio.say("m7_04", true)
		L.get_tree().create_timer(10.0).timeout.connect(func(): Audio.say("m7_05"))
		L.objective_override = "• Прочитать записку Матери"

func on_note_read(L: Level, id: String) -> void:
	if id == "n7_t1":
		L.complete_task("mother")
		Audio.say("m7_06")
		L.get_tree().create_timer(9.0).timeout.connect(func(): _start_chase(L))

func _start_chase(L: Level) -> void:
	if chase:
		return
	chase = true
	Game.set_flag("key_lift")
	L.unlock_task("lift")
	L.objective_override = "• Бежать к лифту (в восточном конце коридора)!"
	Common.blackout(L, true)
	Audio.sfx("host_roar", L.b.P("A", 0.02, 0.5), 6.0)
	L.get_tree().create_timer(1.5).timeout.connect(func(): Common.blackout(L, false))
	host = L.b.spawn_monster("host", L.b.P("A", 0.02, 0.5, 0.0), {"state": "chase", "chase_speed": 3.3})
	host.last_seen = L.player.global_position
	for r in ["A"]:
		pass

func tick(L: Level, delta: float) -> void:
	if chase and not escaped:
		var lift_pos: Vector3 = L.b.P("E", 0.5, 0.5, 0.0)
		if L.player.global_position.distance_to(lift_pos) < 3.0:
			escaped = true
			Audio.say("h7_08")
			L.get_tree().create_timer(2.5).timeout.connect(func(): L.end_chapter())

func finish_gate(L: Level) -> Array:
	return [false, ""]
