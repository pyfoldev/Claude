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
	var van := L.b.prop("crate", pos, yaw, {"s": 0.01})
	var root := Node3D.new()
	root.position = pos
	root.rotation_degrees.y = yaw
	L.add_child(root)
	var body := Mats.color(Color(0.85, 0.85, 0.82), 0.5)
	Props.box(root, Vector3(2.0, 1.5, 4.2), Vector3(0, 0.95, 0), body)
	Props.box(root, Vector3(1.9, 0.4, 1.3), Vector3(0, 0.9, 1.9), body)
	Props.box(root, Vector3(1.9, 0.5, 0.05), Vector3(0, 1.3, 2.55), Mats.glass(Color(0.2, 0.3, 0.4, 0.6)))
	Props.box(root, Vector3(2.02, 0.2, 2.4), Vector3(0, 0.95, -0.7), Mats.color(Color(0.1, 0.35, 0.65), 0.5))
	for sx in [-1, 1]:
		for z in [-1.3, 1.3]:
			Props.cyl(root, 0.35, 0.25, Vector3(sx * 1.0, 0.35, z), Mats.color(Color(0.04, 0.04, 0.04)))
			root.get_child(root.get_child_count() - 1).rotation_degrees = Vector3(0, 0, 90)
	var col := Props.col(root, Vector3(2.0, 1.8, 4.2), Vector3(0, 0.9, 0))
	var it: Interactable = L.b.interact(pos + Vector3(0, 1.0, 0) + Vector3(sin(deg_to_rad(yaw)), 0, cos(deg_to_rad(yaw))) * 1.5, Vector3(1.5, 1.8, 2.4), "Фургон: закончить смену", func(p): L.try_finish())
	van.queue_free()

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
