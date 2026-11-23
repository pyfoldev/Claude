class_name Common extends RefCounted
## Общие сюжетные объекты: ведро, ящик с расходниками, контейнер, мешки, фургон, прятки, мимики.

static func bucket(L: Level, pos: Vector3) -> Node3D:
	var n := L.b.prop("bucket", pos)
	L.b.interact(pos + Vector3(0, 0.3, 0), Vector3(0.6, 0.6, 0.6), "Прополоскать швабру", func(p):
		p.rinse_mop()
		Audio.sfx("water", pos)
		Game.note("Швабра чистая.")
		if p.tool_id != "mop":
			Game.note("Ведро с водой."))
	return n

static func supply(L: Level, pos: Vector3, yaw := 0.0) -> Node3D:
	var n := L.b.prop("supply", pos, yaw)
	L.b.interact(pos + Vector3(0, 0.3, 0), Vector3(0.9, 0.7, 0.7), "Ящик с расходниками (спрей, батарейки)", func(p):
		p.spray_amount = 100.0
		p.battery = 100.0
		Audio.sfx("restock", pos)
		Game.note("Спрей и батарейки пополнены."))
	return n

static func dumpster(L: Level, pos: Vector3, task_id: String, yaw := 0.0) -> Node3D:
	var n := L.b.prop("dumpster", pos, yaw)
	L.b.interact(pos + Vector3(0, 0.7, 0), Vector3(1.9, 1.6, 1.3), "Выбросить мешок", func(p):
		if p.carrying_bag:
			p.drop_bag()
			Audio.sfx("trash_throw", pos)
			L.add_manual(task_id)
			if Game.level.b.tasks.has(task_id) and not L.b.tasks[task_id].done:
				Game.note("Мешков выброшено: %d/%d" % [L.b.tasks[task_id].count, L.b.tasks[task_id].need])
		else:
			Game.note("Нужен мешок с мусором."))
	return n

static func bag(L: Level, pos: Vector3, yaw := 0.0) -> Node3D:
	var n := L.b.prop("bag", pos, yaw)
	for c in n.get_children():
		if c is StaticBody3D:
			c.queue_free()
	var it: Interactable = L.b.interact(pos + Vector3(0, 0.3, 0), Vector3(0.6, 0.6, 0.6), "Взять мешок с мусором", Callable())
	it.callback = func(p):
		if p.carrying_bag:
			Game.note("Руки заняты: сначала выбросьте мешок.")
			return
		p.pickup_bag()
		Audio.sfx("paper", pos)
		it.enabled = false
		n.queue_free()
		Game.note("Мешок в руках. Несите к контейнеру.")
	return n

static func van_exit(L: Level, pos: Vector3, yaw := 0.0) -> void:
	var root := Node3D.new()
	root.position = pos
	root.rotation_degrees.y = yaw
	L.add_child(root)
	var vm := Props.ext_model("res://assets/vehicles/Van.fbx", "w", 5.0, false, 0.0)
	if vm != null:
		root.add_child(vm)
		vm.rotation_degrees.y = 0.0
		var lb0 := Label3D.new()
		lb0.text = "ЧистоДом"
		lb0.font_size = 90; lb0.pixel_size = 0.0035; lb0.outline_size = 22
		lb0.outline_modulate = Color(0.0, 0.0, 0.0)
		lb0.position = Vector3(1.2, 1.35, -0.3); lb0.rotation_degrees = Vector3(0, 90, 0)
		root.add_child(lb0)
		var lb1 := lb0.duplicate()
		lb1.position = Vector3(-1.2, 1.35, -0.3); lb1.rotation_degrees = Vector3(0, -90, 0)
		root.add_child(lb1)
		Props.col(root, Vector3(2.6, 2.4, 5.0), Vector3(0, 1.2, 0))
		var side0 := Vector3(cos(deg_to_rad(yaw)), 0, -sin(deg_to_rad(yaw)))
		L.b.interact(pos + Vector3(0, 1.0, 0) + side0 * 1.9, Vector3(2.0, 1.8, 3.0), "Фургон: закончить смену", func(p): L.try_finish(), {"layer": 2})
		L.b.interact(pos + Vector3(0, 1.0, 0) - side0 * 1.9, Vector3(2.0, 1.8, 3.0), "Фургон: закончить смену", func(p): L.try_finish(), {"layer": 2})
		return
	var white := Mats.color(Color(0.82, 0.83, 0.8), 0.35, 0.0, 0.3)
	var blue := Mats.color(Color(0.08, 0.28, 0.6), 0.4)
	var dark := Mats.color(Color(0.05, 0.05, 0.06), 0.6)
	# нижняя часть кузова, грузовой отсек, кабина, капот
	Props.box(root, Vector3(1.95, 0.75, 4.7), Vector3(0, 0.62, 0), white)
	Props.box(root, Vector3(1.9, 1.05, 2.9), Vector3(0, 1.5, -0.8), white)
	Props.box(root, Vector3(1.85, 0.85, 1.25), Vector3(0, 1.38, 1.15), white)
	var hood := Props.box(root, Vector3(1.85, 0.1, 1.2), Vector3(0, 1.1, 2.05), white, Vector3(-12, 0, 0))
	var ws := Props.box(root, Vector3(1.75, 0.8, 0.06), Vector3(0, 1.62, 1.82), Mats.glass(Color(0.15, 0.22, 0.3, 0.7)), Vector3(-28, 0, 0))
	for sx in [-1, 1]:
		Props.box(root, Vector3(0.04, 0.5, 0.9), Vector3(sx * 0.93, 1.55, 1.15), Mats.glass(Color(0.15, 0.22, 0.3, 0.7)))
		Props.box(root, Vector3(0.04, 0.22, 3.2), Vector3(sx * 0.98, 0.78, -0.2), blue)
		var wx: float = 0.9 * sx
		for wz in [1.35, -1.45]:
			var wh := Props.cyl(root, 0.38, 0.28, Vector3(wx, 0.38, wz), Mats.color(Color(0.03, 0.03, 0.03), 0.9), -1.0, 16)
			wh.rotation_degrees = Vector3(0, 0, 90)
			var hub := Props.cyl(root, 0.2, 0.3, Vector3(wx + sx * 0.02, 0.38, wz), Mats.color(Color(0.7, 0.7, 0.72), 0.3, 0.0, 0.9), -1.0, 10)
			hub.rotation_degrees = Vector3(0, 0, 90)
		Props.box(root, Vector3(0.1, 0.16, 0.3), Vector3(sx * 0.75, 0.85, 2.5), Mats.color(Color(1, 0.95, 0.75), 0.2, 3.0))   # фары
		Props.box(root, Vector3(0.1, 0.18, 0.1), Vector3(sx * 0.8, 0.85, -2.33), Mats.color(Color(0.8, 0.05, 0.05), 0.3, 1.5))  # задние огни
		Props.box(root, Vector3(0.12, 0.25, 0.12), Vector3(sx * 1.0, 1.55, 1.7), dark)   # зеркала
	Props.box(root, Vector3(1.98, 0.22, 0.2), Vector3(0, 0.38, 2.38), dark)   # бампер
	Props.box(root, Vector3(1.98, 0.22, 0.2), Vector3(0, 0.38, -2.4), dark)
	Props.box(root, Vector3(1.4, 0.04, 2.4), Vector3(0, 2.05, -0.8), dark)   # багажник на крыше
	var lbl := Label3D.new()
	lbl.text = "ЧистоДом"
	lbl.font_size = 96; lbl.pixel_size = 0.0035
	lbl.modulate = Color(1, 1, 1)
	lbl.outline_modulate = Color(0.05, 0.2, 0.5)
	lbl.outline_size = 24
	lbl.position = Vector3(1.0, 1.55, -0.8)
	lbl.rotation_degrees = Vector3(0, 90, 0)
	root.add_child(lbl)
	var lbl2 := lbl.duplicate()
	lbl2.position = Vector3(-1.0, 1.55, -0.8)
	lbl2.rotation_degrees = Vector3(0, -90, 0)
	root.add_child(lbl2)
	Props.col(root, Vector3(2.0, 1.9, 4.8), Vector3(0, 0.95, 0))
	var f := Vector3(sin(deg_to_rad(yaw)), 0, cos(deg_to_rad(yaw)))
	var side := Vector3(cos(deg_to_rad(yaw)), 0, -sin(deg_to_rad(yaw)))
	L.b.interact(pos + Vector3(0, 1.0, 0) + side * 1.4, Vector3(2.4, 1.8, 3.0), "Фургон: закончить смену", func(p): L.try_finish(), {"layer": 2})
	L.b.interact(pos + Vector3(0, 1.0, 0) - side * 1.4, Vector3(2.4, 1.8, 3.0), "Фургон: закончить смену", func(p): L.try_finish(), {"layer": 2})

static func hide_wardrobe(L: Level, room: String, side: String, frac: float, tint := Color(0.55, 0.42, 0.32)) -> Node3D:
	var n := L.b.against("wardrobe", room, side, frac, {"tint": tint}, 0.35)
	var spot := L.b.hide_spot(n.position + Vector3(0, 0, 0), n.rotation_degrees.y, "Спрятаться в шкафу")
	# позиция «внутри»: чуть за дверцей
	spot.set_meta("hide_pos", n.position)
	return n

static func hide_bed(L: Level, room: String, side: String, frac: float) -> Node3D:
	var n := L.b.against("bed", room, side, frac, {}, 1.1)
	var spot := L.b.hide_spot(n.position + Vector3(0, 0.0, 0), n.rotation_degrees.y, "Спрятаться под кроватью")
	spot.set_meta("hide_pos", n.position)
	return n

static func mimic(L: Level, pos: Vector3, disguise: String, popts := {}, mopts := {}) -> Node:
	var o := {"disguise": disguise, "popts": popts}
	for k in mopts:
		o[k] = mopts[k]
	return L.b.spawn_monster("mimic", pos, o)

## Включаемый телевизор: возвращает узел tv; screen мигает.
static func tv_set(L: Level, tv: Node3D, on: bool) -> void:
	var scr: MeshInstance3D = tv.get_node_or_null("screen")
	if scr == null:
		return
	if on:
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(0.7, 0.75, 0.8)
		m.emission_enabled = true
		m.emission = Color(0.6, 0.7, 0.8)
		m.emission_energy_multiplier = 1.2
		scr.material_override = m
		var li: OmniLight3D = tv.get_node_or_null("tvlight")
		if li == null:
			li = OmniLight3D.new()
			li.name = "tvlight"
			li.position = Vector3(0, 0.9, 0.7)
			li.light_color = Color(0.6, 0.75, 1.0)
			li.light_energy = 0.8
			li.omni_range = 5.0
			tv.add_child(li)
		Audio.sfx("radio_static", tv.global_position, 0.0)
		var tw := L.create_tween().set_loops()
		tw.tween_property(m, "emission_energy_multiplier", 0.3, 0.07)
		tw.tween_property(m, "emission_energy_multiplier", 1.4, 0.05)
		tv.set_meta("tw", tw)
	else:
		if tv.has_meta("tw"):
			tv.get_meta("tw").kill()
		scr.material_override = Mats.color(Color(0.1, 0.12, 0.13), 0.3)
		var li2: OmniLight3D = tv.get_node_or_null("tvlight")
		if li2:
			li2.queue_free()

## Блуждающий звук-источник: короткая реплика в точке.
static func sound_at(pos: Vector3, name: String, vol := 0.0) -> void:
	Audio.sfx(name, pos, vol)

static func eyes_flash(L: Level, node: Node3D, local_pos: Vector3, dur := 0.7) -> void:
	var eyes := Node3D.new()
	var em := Mats.color(Color(1, 1, 0.9), 0.3, 6.0)
	for s in [-1, 1]:
		var e := Props.box(eyes, Vector3(0.1, 0.05, 0.02), Vector3(s * 0.12, 0, 0), em)
	eyes.position = local_pos
	node.add_child(eyes)
	Audio.sfx("sting_soft", node.global_position)
	L.get_tree().create_timer(dur).timeout.connect(eyes.queue_free)

## Двор с фургоном, ведром, ящиком и контейнером.
static func yard(L: Level, room: String, trash_task := "trash") -> void:
	var b := L.b
	Common.bucket(L, b.P(room, 0.55, 0.45))
	Common.supply(L, b.P(room, 0.45, 0.3), 90)
	Common.dumpster(L, b.P(room, 0.8, 0.85), trash_task, 180)
	Common.van_exit(L, b.P(room, 0.4, 0.62), 90)
	b.lamp_light(b.P(room, 0.9, 0.5, 3.2), Color(1, 0.9, 0.6), 0.6, 9.0)

const YARD_SPEC := {"name": "Двор", "floor": "floor_conc", "wall": "wall_brick", "ceil": "wall_grey", "light": 1.4, "light_color": Color(0.7, 0.78, 1.0), "h": 4.0, "wall_tint": Color(0.5, 0.5, 0.55)}

## Сумма требований по умолчанию для finish_gate.
static func gate(L: Level, min_progress: float, flag_name := "") -> Array:
	if flag_name != "" and not Game.flag(flag_name):
		return [false, "Работа ещё не закончена."]
	if L.progress() < min_progress:
		return [false, "Слишком грязно: нужно убрать минимум %d%%." % int(min_progress * 100.0)]
	return [true, ""]

static func blackout(L: Level, on: bool) -> void:
	for l in L.b.lights:
		if on:
			l.set_meta("saved", l.light_energy)
			l.light_energy = 0.0
		else:
			l.light_energy = l.get_meta("base", 1.0)
	if on:
		Audio.sfx("power_down", null, 0.0)
	else:
		Audio.sfx("power_up", null, -2.0)

## Предмет, который можно подобрать (ключ, предохранитель, печать…)
static func pickup(L: Level, kind: String, pos: Vector3, prompt: String, cb: Callable, popts := {}) -> Node3D:
	var n := L.b.prop(kind, pos, 0, popts)
	var it: Interactable = L.b.interact(pos + Vector3(0, 0.15, 0), Vector3(0.5, 0.4, 0.5), prompt, Callable())
	it.callback = func(p):
		it.enabled = false
		n.queue_free()
		cb.call(p)
	return n

static func hide_wardrobe_free(L: Level, pos: Vector3) -> void:
	var n := L.b.prop("wardrobe", pos, 0, {"tint": Color(0.25, 0.2, 0.2)})
	var spot := L.b.hide_spot(pos, 0.0, "Спрятаться в шкафу")
	spot.set_meta("hide_pos", pos)
