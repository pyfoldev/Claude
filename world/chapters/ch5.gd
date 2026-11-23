extends RefCounted
## Глава 5. Дом заказчика — правда. Подвал и портал.

var host: Monster
var pages := 0
var portal_open := false
var entered := false
var portal_node: Node3D
var portal_light: OmniLight3D
var basement_chase := false

func build(L: Level) -> void:
	var b := L.b
	var legend := {
		"Y": Common.YARD_SPEC,
		"H": {"name": "Холл", "floor": "floor_dark", "wall": "wall_paper", "light": 0.55, "h": 3.4, "wall_tint": Color(0.6, 0.55, 0.6)},
		"L": {"name": "Гостиная", "floor": "floor_wood", "wall": "wall_paper", "light": 0.5, "h": 3.2},
		"K": {"name": "Кухня", "floor": "floor_tile", "wall": "wall_plaster", "light": 0.6},
		"T": {"name": "Кабинет Заказчика", "floor": "floor_wood", "wall": "wall_grey", "light": 0.45},
		"V": {"name": "Коридор", "floor": "floor_dark", "wall": "wall_peel", "light": 0.3},
		"S": {"name": "Спуск", "floor": "floor_conc", "wall": "wall_grey", "light": 0.2, "ramp": "x-", "rise": 3.0, "h": 5.7},
	}
	b.layout(["YYHHLLKK.", "YYHHLLKK.", "YYHHTTV.."], legend, 0.0, 4.0)
	b.room("S", Rect2(28, 8, 8, 4), -3.0, legend["S"])
	var base := {
		"u": {"name": "Подвальный коридор", "floor": "floor_conc", "wall": "wall_grey", "light": 0.3, "wall_tint": Color(0.5, 0.5, 0.5), "h": 2.8},
		"b": {"name": "Котельная", "floor": "floor_conc", "wall": "wall_brick", "light": 0.25, "wall_tint": Color(0.5, 0.45, 0.45), "h": 2.8},
		"a": {"name": "Архив", "floor": "floor_conc", "wall": "wall_grey", "light": 0.3, "h": 2.8},
		"c": {"name": "Винный погреб", "floor": "floor_conc", "wall": "wall_brick", "light": 0.2, "h": 2.8},
		"p": {"name": "Зал портала", "floor": "floor_dark", "wall": "wall_brick", "light": 0.15, "h": 4.0, "wall_tint": Color(0.4, 0.35, 0.4)},
	}
	b.layout(["bbaa", "bbaa", "uuuu", "ccpp", "ccpp"], base, -3.0, 4.0, Vector2(36, 0))
	b.doors_from(["Y-H", "H-L", "L-K", "H-T", "T-V", "K-V", "V-S", "S-u", "u-b", "u-a", "u-c", "u-p", "c-p"])
	b.finish()
	L.door_between("u", "p").set_locked(true, "portal")
	b.spawn = b.P("Y", 0.7, 0.5) + Vector3(0, 0.1, 0)
	b.spawn_yaw = 90.0 + 180.0
	b.task("pages", "Найти страницы договора (0/3)", {"manual": true, "need": 3})
	b.task("key", "Найти ключ от зала под домом", {"manual": true})
	b.task("portal", "Дойти до конца подвала", {"manual": true, "hidden": true})
	b.task("dust", "Привести дом в порядок", {"optional": true})
	Common.yard(L, "Y", "none")
	b.tasks["none"] = {"id": "none", "text": "", "patches": [], "optional": true, "manual": true, "done": false, "hidden": true, "count": 0, "need": 0}
	# холл
	b.prop("rug", b.P("H", 0.5, 0.5), 0, {"w": 3.0, "d": 4.0, "tint": Color(0.3, 0.25, 0.35)})
	b.note_pickup("n5_a", b.P("H", 0.5, 0.5, 0.03), 0)
	b.against("picture", "H", "N", 0.5, {"c": Color(0.2, 0.15, 0.15)}, 0.0).position.y = 2.0
	b.prop("plant", b.P("H", 0.12, 0.12)); b.prop("plant", b.P("H", 0.88, 0.12))
	b.floor_dirt("stain", "H", Vector2(0, 2.5), Vector2(1.6, 1.4), "dust")
	Common.hide_wardrobe(L, "H", "W", 0.8, Color(0.3, 0.25, 0.22))
	# гостиная и кухня
	b.prop("sofa", b.P("L", 0.5, 0.2), 180); b.prop("rug", b.P("L", 0.5, 0.6), 0, {"w": 3.0, "d": 2.2, "tint": Color(0.35, 0.2, 0.2)})
	b.against("piano", "L", "E", 0.4, {}, 0.5)
	b.prop("table", b.P("L", 0.5, 0.6), 0, {"w": 1.1, "d": 0.7})
	b.dirt("dust", b.P("L", 0.5, 0.6, 0.775), Vector2(1.0, 0.65), Vector3.UP, "dust")
	Common.mimic(L, b.P("L", 0.15, 0.85), "armchair", {}, {"radius": 2.2})
	b.against("counter", "K", "N", 0.4, {"w": 2.8}, 0.35); b.against("fridge", "K", "E", 0.5, {}, 0.4)
	b.prop("table", b.P("K", 0.4, 0.62), 0)
	b.floor_dirt("mud", "K", Vector2(0, 1.0), Vector2(1.6, 1.4), "dust")
	Common.mimic(L, b.P("K", 0.15, 0.85), "crate", {"s": 0.8}, {"radius": 2.2})
	# кабинет заказчика: договор 1, ключ
	b.against("bookshelf", "T", "N", 0.3, {"seed": 7}, 0.2); b.against("bookshelf", "T", "N", 0.7, {"seed": 8}, 0.2)
	b.prop("table", b.P("T", 0.5, 0.55), 0, {"w": 1.8, "d": 0.9})
	b.prop("candle", b.P("T", 0.4, 0.55, 0.77))
	Common.pickup(L, "paper", b.P("T", 0.6, 0.55, 0.77), "Взять страницу договора", func(p): _page(L, "n5_c1"), {"c": Color(0.85, 0.8, 0.7)})
	Common.pickup(L, "key", b.P("T", 0.5, 0.7, 0.0), "Взять ключ с биркой «Портал»", func(p):
		Game.set_flag("key_portal")
		L.complete_task("key")
		Audio.say("h5_08"))
	b.prop("phone", b.P("T", 0.45, 0.58, 0.77), 20)
	# коридор
	b.floor_dirt("mud", "V", Vector2(0, 0), Vector2(1.4, 1.0), "dust")
	# подвал
	b.floor_dirt("stain", "u", Vector2(-3.0, 0), Vector2(1.6, 1.2), "dust")
	b.floor_dirt("blood", "u", Vector2(2.0, 0), Vector2(1.4, 1.2), "dust")
	b.prop("crate", b.P("u", 0.1, 0.2), 15); b.prop("box", b.P("u", 0.12, 0.8), 45)
	# котельная — страница 3
	b.prop("pillar", b.P("b", 0.3, 0.3), 0, {"h": 2.8}); b.prop("pillar", b.P("b", 0.7, 0.7), 0, {"h": 2.8})
	Common.pickup(L, "paper", b.P("b", 0.5, 0.5, 0.0), "Взять страницу договора", func(p): _page(L, "n5_c3"), {"c": Color(0.85, 0.8, 0.7)})
	Common.mimic(L, b.P("b", 0.85, 0.2), "box", {"s": 0.8}, {"radius": 2.2})
	Common.hide_wardrobe(L, "b", "W", 0.8, Color(0.25, 0.22, 0.2))
	# архив — страница 2
	for i in 3:
		b.against("bookshelf", "a", "N", 0.2 + i * 0.3, {"seed": 30 + i}, 0.2)
	b.prop("table", b.P("a", 0.5, 0.6), 0, {"w": 1.6, "d": 0.9})
	Common.pickup(L, "paper", b.P("a", 0.5, 0.6, 0.77), "Взять страницу договора", func(p): _page(L, "n5_c2"), {"c": Color(0.85, 0.8, 0.7)})
	b.dirt("dust", b.P("a", 0.5, 0.6, 0.775), Vector2(1.3, 0.7), Vector3.UP, "dust")
	Common.mimic(L, b.P("a", 0.9, 0.9), "crate", {"s": 0.8}, {"radius": 2.2})
	# погреб
	b.prop("crate", b.P("c", 0.3, 0.3), 0); b.prop("crate", b.P("c", 0.6, 0.7), 20); b.prop("box", b.P("c", 0.8, 0.3), 5)
	b.prop("bars", b.P("c", 0.5, 0.95), 0)
	# зал портала
	portal_node = Node3D.new()
	portal_node.position = b.P("p", 0.5, 0.15, 0.0)
	L.add_child(portal_node)
	var ring := Props.cyl(portal_node, 1.5, 0.2, Vector3(0, 1.6, 0), Mats.color(Color(0.08, 0.05, 0.1), 0.4, 0.0, 0.5), 1.5, 24)
	ring.rotation_degrees = Vector3(90, 0, 0)
	var sw := Props.cyl(portal_node, 1.25, 0.05, Vector3(0, 1.6, 0.0), Mats.color(Color(0.45, 0.05, 0.12), 0.4, 3.0), 1.25, 24)
	sw.rotation_degrees = Vector3(90, 0, 0)
	sw.name = "swirl"
	portal_light = OmniLight3D.new()
	portal_light.position = Vector3(0, 1.6, 1.0)
	portal_light.light_color = Color(0.9, 0.1, 0.25)
	portal_light.light_energy = 1.4
	portal_light.omni_range = 8.0
	portal_node.add_child(portal_light)
	b.interact(portal_node.position + Vector3(0, 1.4, 0.6), Vector3(3.0, 3.0, 1.2), "Войти в портал", func(p): _enter_portal(L))
	for dx in [-0.35, 0.35]:
		var m := b.spawn_monster("shadow", b.P("p", 0.5 + dx, 0.85, 0.0), {"active": false, "speed": 2.4})
		m.state = "idle"
		m.set_meta("portal_guard", true)
	b.trigger(b.P("Y", 0.5, 0.5, 1.0), Vector3(8, 4, 8), func(): Audio.say("h5_02"), true)
	b.trigger(b.P("u", 0.5, 0.5, -2.0), Vector3(16, 3, 4), func(): _basement(L))
	b.trigger(b.P("p", 0.5, 0.5, -2.0), Vector3(8, 4, 8), func(): _portal_hall(L))

func start(L: Level) -> void:
	host = L.b.spawn_monster("host", L.b.P("H", 0.5, 0.5, 0.0), {"state": "patrol"})

func on_begin(L: Level) -> void:
	Game.note("Хозяин ходит по дому. Прячьтесь (шкафы, кровати), не шумите.")

func _page(L: Level, id: String) -> void:
	pages += 1
	L.read_note(id)
	L.b.tasks.pages.text = "Найти страницы договора (%d/3)" % pages
	L.add_manual("pages")

func on_note_read(L: Level, id: String) -> void:
	match id:
		"n5_a": Audio.say("h5_03")
		"n5_c1": Audio.say("h5_05")
		"n5_c2": Audio.say("h5_06")
		"n5_c3": Audio.say("h5_07"); _after_pages(L)

func _after_pages(L: Level) -> void:
	if pages >= 3 and not portal_open:
		portal_open = true
		L.unlock_task("portal")
		Game.note("В подвале что-то открылось.")
		L.objective_override = "• Спуститься в подвал и найти портал"

func _basement(L: Level) -> void:
	if Game.flag("basement"):
		return
	Game.set_flag("basement")
	Audio.say("h5_09")
	for m in get_tree_monsters(L):
		pass

func get_tree_monsters(L: Level) -> Array:
	return L.get_tree().get_nodes_in_group("monsters")

func _portal_hall(L: Level) -> void:
	if basement_chase:
		return
	basement_chase = true
	Audio.say("h5_10")
	for m in L.get_tree().get_nodes_in_group("monsters"):
		if m.get_meta("portal_guard", false):
			m.state = "stalk"
			m.active = true
	if host and is_instance_valid(host):
		host.global_position = L.b.P("u", 0.95, 0.5, 0.0)
		host.state = "chase"
		host.last_seen = L.player.global_position
		host.opts["chase_speed"] = 3.5
	L.objective_override = "• Войти в портал!"

func _enter_portal(L: Level) -> void:
	if entered:
		return
	if not portal_open:
		Game.note("Портал не отзывается. Сначала найдите все страницы договора.")
		return
	entered = true
	L.player.frozen = true
	Audio.stop_all_loops()
	Audio.sfx("portal", null, 2.0)
	L.hud.fade_to(1.0, 2.0)
	await L.get_tree().create_timer(2.5).timeout
	# темнота, дыхание, свет, голоса, резкий скример «ТЫ НАШ»
	Audio.sfx("breath", null, 4.0)
	L.hud.show_center("…", 2.0)
	await L.get_tree().create_timer(3.0).timeout
	Audio.say("hm_01", true)
	await L.get_tree().create_timer(4.5).timeout
	Audio.sfx("jumpscare", null, 4.0)
	Audio.sfx("scream", null, 0.0)
	L.hud.flash_screen(1.0)
	L.hud.fade.color.a = 0.0
	var lbl := Label.new()
	lbl.text = "ТЫ НАШ"
	lbl.add_theme_font_size_override("font_size", 150)
	lbl.add_theme_color_override("font_color", Color(0.8, 0.02, 0.02))
	lbl.set_anchors_preset(Control.PRESET_FULL_RECT)
	lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	lbl.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	L.hud.add_child(lbl)
	L.hud.glitch(1.5)
	await L.get_tree().create_timer(0.7).timeout
	L.hud.fade.color.a = 1.0
	await L.get_tree().create_timer(3.0).timeout
	lbl.queue_free()
	await L.end_chapter()

func tick(L: Level, delta: float) -> void:
	if portal_node:
		var sw := portal_node.get_node_or_null("swirl")
		if sw:
			sw.rotation.y += delta * 2.0
		portal_light.light_energy = 1.2 + sin(Time.get_ticks_msec() * 0.004) * 0.4

func finish_gate(L: Level) -> Array:
	return [false, "Выхода нет. Дверь за спиной исчезла."]
