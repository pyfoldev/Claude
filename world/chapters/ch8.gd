extends RefCounted
## Глава 8. Сердце Дома — финальная уборка, выбор, концовки.

var heart: Node3D
var heart_light: OmniLight3D
var phase := 0
var host: Monster
var arteries_done := 0
var core_done := 0
var choice_shown := false
var ending_started := false
var pulse_t := 0.0
var overlay: Control

func build(L: Level) -> void:
	var b := L.b
	L.set_ambient(Color(0.2, 0.08, 0.1), 0.6)
	var red := Color(0.9, 0.2, 0.25)
	var g := Color(0.5, 0.3, 0.35)
	var legend := {
		"E": {"name": "Спуск к Сердцу", "floor": "floor_conc", "wall": "wall_brick", "light": 0.5, "light_color": Color(1.0, 0.6, 0.3), "wall_tint": g},
		"H": {"name": "Сердце Дома", "floor": "floor_dark", "wall": "wall_brick", "light": 0.7, "light_color": red, "h": 6.0, "wall_tint": g, "floor_tint": g},
	}
	b.layout(["EHHHH", ".HHHH", ".HHHH", ".HHHH"], legend, 0.0, 4.0)
	b.doors_from(["E-H"])
	b.finish()
	b.spawn = b.P("E", 0.5, 0.5) + Vector3(0, 0.1, 0)
	b.spawn_yaw = 0.0 + 90.0 + 90.0
	b.task("arteries", "Отмыть четыре «артерии» на стенах зала (спрей)", {"manual": true, "need": 4})
	b.task("core", "Очистить Сердце (всеми инструментами)", {"manual": true, "need": 5, "hidden": true})
	b.task("choice", "Принять решение", {"manual": true, "hidden": true})
	Common.supply(L, b.P("E", 0.2, 0.2), 0)
	Common.bucket(L, b.P("E", 0.8, 0.2))
	# сердце
	var hc := b.room_center("H") + Vector3(0, 0, 0)
	heart = Node3D.new()
	heart.position = hc
	L.add_child(heart)
	var blob := Mats.color(Color(0.35, 0.02, 0.05), 0.3, 0.8)
	Props.sph(heart, 1.6, Vector3(0, 2.2, 0), blob, 1.15).name = "blob"
	Props.sph(heart, 1.0, Vector3(0.9, 2.8, 0.3), blob, 1.0)
	Props.sph(heart, 0.8, Vector3(-0.9, 1.7, -0.4), blob, 1.0)
	for i in 8:
		var a := i * TAU / 8.0
		var tend := Props.cyl(heart, 0.18, 6.0, Vector3(cos(a) * 3.0, 3.2, sin(a) * 3.0), Mats.color(Color(0.05, 0.01, 0.02), 0.4), 0.06)
		tend.look_at_from_position(Vector3(cos(a) * 3.0, 3.2, sin(a) * 3.0) + hc, hc + Vector3(0, 2.0, 0))
		tend.rotate_object_local(Vector3(1, 0, 0), PI / 2.0)
	Props.col(heart, Vector3(3.2, 4.0, 3.2), Vector3(0, 2.0, 0))
	heart_light = OmniLight3D.new()
	heart_light.position = Vector3(0, 2.4, 0)
	heart_light.light_color = red; heart_light.light_energy = 2.0; heart_light.omni_range = 14.0
	heart.add_child(heart_light)
	# артерии на стенах
	var sides := ["N", "S", "E", "W"]
	for i in 4:
		var d := b.dirt("grime", b.wp("H", sides[i], 0.5, 0.0, 1.4) + Heart_n(sides[i]) * 0.12, Vector2(1.8, 2.2), Heart_n(sides[i]), "", {"id": "art%d" % i, "story": true})
		d.glow(0.25)
	# ядро: 5 пятен вокруг сердца, разные инструменты
	var kinds := ["dust", "stain", "debris", "crumbs", "blood"]
	for i in 5:
		var a2 := i * TAU / 5.0
		var pos := hc + Vector3(cos(a2) * 2.3, 0.02, sin(a2) * 2.3)
		var p := b.dirt(kinds[i], pos, Vector2(1.4, 1.4), Vector3.UP, "", {"id": "core%d" % i, "story": true})
		p.visible = false
		if p.body:
			p.body.collision_layer = 0
	for pos2 in [b.P("H", 0.12, 0.12), b.P("H", 0.88, 0.12), b.P("H", 0.12, 0.88), b.P("H", 0.88, 0.88)]:
		Common.hide_wardrobe_free(L, pos2)
	b.note_pickup("n8_t1", b.P("E", 0.6, 0.6, 0.0), 0, Color(0.25, 0.22, 0.2))
	b.trigger(b.P("H", 0.5, 0.5, 1.5), Vector3(10, 4, 10), func(): _enter_arena(L))

func Heart_n(side: String) -> Vector3:
	return Builder.side_normal(side)

func on_begin(L: Level) -> void:
	Audio.say("h8_02")

func _enter_arena(L: Level) -> void:
	if Game.flag("arena"):
		return
	Game.set_flag("arena")
	Audio.say("hs_01", true)
	L.get_tree().create_timer(10.0).timeout.connect(func(): Audio.say("h8_03"))
	L.objective_override = ""
	Audio.sfx("heartbeat", null, 0.0)

func on_story_patch(L: Level, p: DirtPatch) -> void:
	if p.patch_id.begins_with("art"):
		arteries_done += 1
		L.add_manual("arteries")
		heart_light.light_energy = 2.0 - arteries_done * 0.3
		Audio.sfx("heart_hit", null, 2.0)
		L.hud.flash_screen(0.3)
		L.player.shake(0.03, 0.6)
		var n := 2 + arteries_done
		for i in n:
			var pos := L.b.P("H", randf_range(0.1, 0.9), randf_range(0.1, 0.9))
			if pos.distance_to(L.player.global_position) > 6.0:
				L.b.spawn_monster("crawler", pos, {"speed": 3.0})
		if arteries_done == 2:
			Audio.say("h8_05")
		if arteries_done == 4:
			_phase2(L)
	elif p.patch_id.begins_with("core"):
		core_done += 1
		L.add_manual("core")
		Audio.sfx("heart_hit", null, 2.0)
		L.hud.glitch(0.8)
		L.player.shake(0.03, 0.6)
		L.b.spawn_monster("crawler", L.b.P("H", randf_range(0.1, 0.9), randf_range(0.1, 0.9)), {"speed": 3.4})
		if core_done == 5:
			_phase3(L)

func _phase2(L: Level) -> void:
	phase = 2
	L.unlock_task("core")
	for i in 5:
		var p: DirtPatch = L.b.patches["core%d" % i]
		p.visible = true
		if p.body:
			p.body.collision_layer = 4
	Audio.say("h8_06", true)
	L.objective_override = "• Очистить ядро: тряпка, швабра, веник, пылесос, спрей"
	L.hud.flash_screen(0.5)
	host = L.b.spawn_monster("host", L.b.P("E", 0.5, 0.5, 0.0), {"state": "patrol", "chase_speed": 3.4})
	Audio.sfx("host_roar", L.b.P("E", 0.5, 0.5), 3.0)

func _phase3(L: Level) -> void:
	phase = 3
	if host and is_instance_valid(host):
		host.queue_free()
	for m in L.get_tree().get_nodes_in_group("monsters"):
		m.queue_free()
	L.unlock_task("choice")
	L.objective_override = "• Принять решение"
	L.player.frozen = true
	Audio.sfx("heart_hit", null, 4.0)
	heart_light.light_energy = 0.4
	await L.get_tree().create_timer(1.5).timeout
	Audio.say("hs_02", true)
	await L.get_tree().create_timer(9.0).timeout
	Audio.say("a8_01")
	await L.get_tree().create_timer(10.0).timeout
	Audio.say("hs_03")
	await L.get_tree().create_timer(9.0).timeout
	_show_choice(L)

func _show_choice(L: Level) -> void:
	choice_shown = true
	overlay = Control.new()
	overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.process_mode = Node.PROCESS_MODE_ALWAYS
	var bg := ColorRect.new(); bg.color = Color(0, 0, 0, 0.75); bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	overlay.add_child(bg)
	var vb := VBoxContainer.new()
	vb.set_anchors_preset(Control.PRESET_CENTER)
	vb.position = Vector2(-340, -200)
	vb.custom_minimum_size = Vector2(680, 0)
	vb.add_theme_constant_override("separation", 14)
	overlay.add_child(vb)
	var t := Label.new()
	t.text = "Сердце затихло. Договор лежит на полу.\nЗаказчик ждёт ответа."
	t.add_theme_font_size_override("font_size", 28)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(t)
	var mk := func(text: String, cb: Callable):
		var b := Button.new(); b.text = text; b.custom_minimum_size = Vector2(0, 74)
		b.add_theme_font_size_override("font_size", 22)
		b.pressed.connect(cb)
		vb.add_child(b)
	mk.call("Подписать договор: стать новым Заказчиком (Алиса будет жить)", func(): _choose(L, "bad"))
	mk.call("Вымыть Сердце до дна: отпустить всех", func(): _choose(L, "good"))
	L.hud.add_child(overlay)
	if not Game.touch_mode:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

func _choose(L: Level, which: String) -> void:
	if ending_started:
		return
	ending_started = true
	overlay.queue_free()
	if which == "bad":
		_bad_ending(L)
	else:
		_good_ending(L)

func _cards(L: Level, items: Array) -> void:
	var l := Label.new()
	l.add_theme_font_size_override("font_size", 34)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	l.set_anchors_preset(Control.PRESET_FULL_RECT)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.custom_minimum_size = Vector2(1000, 0)
	L.hud.add_child(l)
	for it in items:
		l.text = it[0]
		l.modulate.a = 0.0
		var tw := L.create_tween()
		tw.tween_property(l, "modulate:a", 1.0, 1.0)
		if it.size() > 2 and it[2] != "":
			Audio.say(it[2], true)
		await L.get_tree().create_timer(it[1]).timeout
		var tw2 := L.create_tween()
		tw2.tween_property(l, "modulate:a", 0.0, 0.8)
		await tw2.finished
	l.queue_free()

func _bad_ending(L: Level) -> void:
	Game.ending = "bad"
	var tw := L.hud.fade_to(1.0, 2.0)
	await tw.finished
	Audio.sfx("breath", null, 4.0)
	await _cards(L, [["Ты подписал.", 3.0, "hs_04"], ["Дом вздохнул. Впервые за много лет — сытый.", 4.0, ""]])
	Audio.sfx("jumpscare", null, 4.0)
	L.hud.fade.color.a = 0.0
	L.hud.flash_screen(1.0)
	var lbl := Label.new()
	lbl.text = "ТЫ НАШ"
	lbl.add_theme_font_size_override("font_size", 150)
	lbl.add_theme_color_override("font_color", Color(0.8, 0.02, 0.02))
	lbl.set_anchors_preset(Control.PRESET_FULL_RECT)
	lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	lbl.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	L.hud.add_child(lbl)
	await L.get_tree().create_timer(2.0).timeout
	lbl.queue_free()
	L.hud.fade.color.a = 1.0
	Audio.sfx("sms", null, 0.0)
	await _cards(L, [["Новая СМС с твоего номера:\n«Лесная, 12. Код 4471. Оплата по факту.»", 6.0, ""], ["Где-то новый уборщик открывает дверь…", 4.0, ""]])
	await _credits(L)

func _good_ending(L: Level) -> void:
	var secret := NotesDB.true_found() >= NotesDB.true_ids().size() - 1 and Game.deaths_total <= 5
	Game.ending = "secret" if secret else "good"
	# финальная отмывка
	L.hud.flash_screen(1.0)
	Audio.sfx("note_true", null, 2.0)
	var tw := L.hud.fade_to(1.0, 2.5)
	await tw.finished
	await _cards(L, [["Он вымыл Сердце до дна. Тряпкой, водой и спреем.", 4.5, "hs_05"], ["Дом закричал. И затих.", 3.5, ""], ["Из стен вышли люди. Громовы, Вороновы, жильцы Садовой. Они были усталые и живые.", 6.0, "m8_01"], ["Артём Ситников положил ладонь ему на плечо. Бейдж — на место.", 5.0, "a8_02"]])
	await _cards(L, [["Рассвет. Фургон. Термос горячий.", 4.0, "h8_10"], ["СМС: «Папа, ты придёшь на день рождения?»", 4.0, "a8_03"], ["— Конечно, зайка. Я уже еду. С тортом.", 4.5, "h8_11"]])
	if secret:
		await _cards(L, [["Он собрал все настоящие записки.\nВ каждой — один и тот же номер: офис «ЧистоДома».", 6.0, "h8_12"], ["Диспетчер Семён Львович всегда знал заказчика.", 4.0, ""], ["Новый заказ: ЧистоДом. Офис.", 5.0, "h8_13"]])
	else:
		Audio.sfx("sms", null, 0.0)
		await _cards(L, [["СМС от ЧистоДома: «Новый заказ. Лесная, 12. Оплата по факту.»", 6.0, "h8_14"]])
	await _credits(L)

func _credits(L: Level) -> void:
	var r := RichTextLabel.new()
	r.bbcode_enabled = true
	r.set_anchors_preset(Control.PRESET_FULL_RECT)
	r.text = "\n\n[center]" + Story.CREDITS + "\n\nКонцовка: %s\nСмертей: %d   Настоящих записок: %d/%d[/center]" % [{"bad": "ТЫ НАШ", "good": "Чистый рассвет", "secret": "Новый заказ"}.get(Game.ending, ""), Game.deaths_total, NotesDB.true_found(), NotesDB.true_ids().size()]
	r.add_theme_font_size_override("normal_font_size", 30)
	r.add_theme_font_size_override("bold_font_size", 50)
	L.hud.add_child(r)
	await L.get_tree().create_timer(10.0).timeout
	Game.unlocked = 8
	Game.save_game()
	Game.to_menu()

func tick(L: Level, delta: float) -> void:
	pulse_t += delta
	if heart:
		var s := 1.0 + sin(pulse_t * 2.2) * 0.03 * (1.0 + (4 - arteries_done) * 0.2)
		heart.scale = Vector3(s, s, s)

func finish_gate(L: Level) -> Array:
	return [false, ""]

func on_note_read(L: Level, id: String) -> void:
	if id == "n8_t1":
		Audio.say("h8_04")
