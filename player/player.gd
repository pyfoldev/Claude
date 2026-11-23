class_name Player extends CharacterBody3D
## Игрок от первого лица: движение, камера, инструменты уборки, фонарик, прятки.

signal tool_changed(tool_id: String)
signal caught(monster)

const TOOLS := ["rag", "mop", "broom", "vacuum", "spray"]
const TOOL_NAMES := {"rag": "Тряпка", "mop": "Швабра", "broom": "Веник", "vacuum": "Пылесос", "spray": "Спрей"}
const TOOL_HINT := {
	"rag": "Тряпкой стирают пыль и протирают стёкла.",
	"mop": "Швабра нужна для пятен и грязи на полу.",
	"broom": "Мусор сметают веником.",
	"vacuum": "Крошки и мусор убирает пылесос.",
	"spray": "Кровь и чёрную жижу берёт только спрей.",
}

var cam: Camera3D
var head: Node3D
var flash: SpotLight3D
var ray: RayCast3D
var shape: CollisionShape3D
var capsule: CapsuleShape3D
var vm: Node3D                         # модель инструмента в руках
var vm_tools: Dictionary = {}
var pitch := 0.0
var move_input := Vector2.ZERO
var look_delta := Vector2.ZERO
var action_held := false
var action_pressed := false
var tool_id := "rag"
var spray_amount := 100.0
var battery := 100.0
var mop_clean := 1.0
var carrying_bag := false
var bag_node: Node3D
var hiding: Interactable = null
var frozen := false
var crouching := false
var sprint := false
var target: Object = null
var target_prompt := ""
var target_hint := ""
var has_flashlight := true
var step_dist := 0.0
var bob_t := 0.0
var shake_t := 0.0
var shake_amp := 0.0
var _hint_cd := 0.0
var _noise_cd := 0.0
var _vac_playing := false
var _rub_playing := false
var _prev_pos := Vector3.ZERO
var _prev_yaw := 0.0
var fov_base := 75.0
var cleaning_now := false
var scrub_t := 0.0
var look_lock := false

func _ready() -> void:
	collision_layer = 16
	collision_mask = 1 | 8
	floor_snap_length = 0.5
	floor_max_angle = deg_to_rad(52)
	capsule = CapsuleShape3D.new()
	capsule.radius = 0.28
	capsule.height = 1.7
	shape = CollisionShape3D.new()
	shape.shape = capsule
	shape.position.y = 0.85
	add_child(shape)
	head = Node3D.new()
	head.position.y = 1.62
	add_child(head)
	cam = Camera3D.new()
	cam.near = 0.04
	cam.far = 60.0
	fov_base = float(Game.settings.fov)
	cam.fov = fov_base
	cam.current = true
	head.add_child(cam)
	flash = SpotLight3D.new()
	flash.spot_range = 16.0
	flash.spot_angle = 32.0
	flash.spot_angle_attenuation = 1.4
	flash.light_energy = 2.6
	flash.light_color = Color(1.0, 0.95, 0.8)
	flash.shadow_enabled = bool(Game.settings.shadows)
	flash.visible = false
	cam.add_child(flash)
	ray = RayCast3D.new()
	ray.target_position = Vector3(0, 0, -2.6)
	ray.collision_mask = 1 | 2 | 4 | 8
	ray.collide_with_areas = false
	ray.collide_with_bodies = true
	cam.add_child(ray)
	vm = Node3D.new()
	vm.position = Vector3(0.28, -0.3, -0.55)
	cam.add_child(vm)
	_build_viewmodels()
	set_tool("rag")
	Game.player = self

func _build_viewmodels() -> void:
	var cloth := Mats.color(Color(0.85, 0.8, 0.2), 0.95)
	var rag := Node3D.new()
	Props.box(rag, Vector3(0.1, 0.03, 0.12), Vector3(0, 0, 0), cloth)
	Props.box(rag, Vector3(0.07, 0.02, 0.08), Vector3(0.02, 0.03, 0.0), Mats.color(Color(0.8, 0.75, 0.15)))
	var mop := Node3D.new()
	Props.cyl(mop, 0.012, 1.1, Vector3(0, 0.1, 0), Mats.color(Color(0.5, 0.35, 0.2)))
	Props.box(mop, Vector3(0.16, 0.05, 0.1), Vector3(0, -0.45, 0), Mats.color(Color(0.8, 0.8, 0.75), 1.0))
	mop.rotation_degrees = Vector3(-35, 10, 0)
	var broom := Node3D.new()
	Props.cyl(broom, 0.012, 1.0, Vector3(0, 0.1, 0), Mats.color(Color(0.55, 0.4, 0.22)))
	Props.box(broom, Vector3(0.28, 0.1, 0.05), Vector3(0, -0.4, 0), Mats.color(Color(0.75, 0.6, 0.25), 1.0))
	broom.rotation_degrees = Vector3(-30, 10, 0)
	var vac := Node3D.new()
	Props.box(vac, Vector3(0.22, 0.2, 0.34), Vector3(0, -0.02, 0.0), Mats.color(Color(0.7, 0.12, 0.1), 0.5))
	Props.cyl(vac, 0.02, 0.5, Vector3(0, 0.08, -0.25), Mats.color(Color(0.15, 0.15, 0.15)))
	vac.get_child(vac.get_child_count() - 1).rotation_degrees = Vector3(90, 0, 0)
	Props.box(vac, Vector3(0.14, 0.03, 0.12), Vector3(0, -0.14, -0.38), Mats.color(Color(0.1, 0.1, 0.1)))
	var spray := Node3D.new()
	Props.cyl(spray, 0.035, 0.18, Vector3(0, 0, 0), Mats.color(Color(0.2, 0.55, 0.75), 0.4))
	Props.box(spray, Vector3(0.04, 0.05, 0.1), Vector3(0, 0.12, -0.03), Mats.color(Color(0.9, 0.9, 0.9)))
	spray.rotation_degrees = Vector3(0, 0, 0)
	vm_tools = {"rag": rag, "mop": mop, "broom": broom, "vacuum": vac, "spray": spray}
	for k in vm_tools:
		vm.add_child(vm_tools[k])
		vm_tools[k].visible = false

func set_tool(t: String) -> void:
	tool_id = t
	for k in vm_tools:
		vm_tools[k].visible = (k == t)
	_stop_tool_loops()
	tool_changed.emit(t)
	Audio.sfx("tool_switch", null, -6.0)

func next_tool() -> void:
	set_tool(TOOLS[(TOOLS.find(tool_id) + 1) % TOOLS.size()])

func _unhandled_input(event: InputEvent) -> void:
	if Game.touch_mode:
		return
	if event is InputEventMouseButton and event.pressed and Input.mouse_mode != Input.MOUSE_MODE_CAPTURED and not get_tree().paused:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		look_delta += event.relative * 0.25
	if event is InputEventMouseButton and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		if event.button_index == MOUSE_BUTTON_LEFT:
			action_held = event.pressed
			if event.pressed:
				action_pressed = true
	if event.is_action_pressed("action"):
		action_pressed = true
	for i in TOOLS.size():
		if event.is_action_pressed("tool_%d" % (i + 1)):
			set_tool(TOOLS[i])
	if event.is_action_pressed("tool_next"):
		next_tool()
	if event.is_action_pressed("flashlight"):
		toggle_flash()
	if event.is_action_pressed("crouch"):
		crouching = not crouching

func toggle_flash() -> void:
	if not has_flashlight or frozen:
		return
	if battery <= 0.0:
		Game.note("Батарейки сели.")
		return
	flash.visible = not flash.visible
	Audio.sfx("click", null, -4.0)

func _physics_process(delta: float) -> void:
	if frozen:
		_stop_tool_loops()
		return
	# --- взгляд ---
	var sens := 0.12 * float(Game.settings.sens)
	var inv := -1.0 if Game.settings.invert else 1.0
	if not look_lock:
		rotation_degrees.y -= look_delta.x * sens
		pitch = clampf(pitch - look_delta.y * sens * inv, -85.0, 85.0)
	look_delta = Vector2.ZERO
	head.rotation_degrees.x = pitch
	if hiding:
		_hide_update(delta)
		return
	# --- движение ---
	var inp := move_input
	if not Game.touch_mode:
		inp += Input.get_vector("move_left", "move_right", "move_forward", "move_back") * Vector2(1, -1)
	inp = inp.limit_length(1.0)
	var run := (inp.length() > 0.93 and not crouching) or (Input.is_action_pressed("sprint") and not crouching)
	var speed := 2.3
	if crouching: speed = 1.2
	elif run: speed = 3.9
	var dir := (global_transform.basis * Vector3(inp.x, 0, -inp.y)).normalized() * inp.length()
	velocity.x = lerpf(velocity.x, dir.x * speed, minf(1.0, delta * 12.0))
	velocity.z = lerpf(velocity.z, dir.z * speed, minf(1.0, delta * 12.0))
	if not is_on_floor():
		velocity.y -= 18.0 * delta
	else:
		velocity.y = -1.0
	move_and_slide()
	var hv := Vector2(velocity.x, velocity.z).length()
	# приседание
	var target_h := 1.0 if crouching else 1.7
	capsule.height = lerpf(capsule.height, target_h, delta * 10.0)
	shape.position.y = capsule.height / 2.0
	var head_y := lerpf(head.position.y, 1.62 if not crouching else 1.05, delta * 10.0)
	# покачивание и шаги
	if hv > 0.3 and is_on_floor():
		bob_t += delta * hv * 2.6
		step_dist += hv * delta
		var stride := 1.8 if not run else 1.5
		if step_dist > stride:
			step_dist = 0.0
			var vol := -9.0 if not crouching else -18.0
			Audio.sfx_rand("step", 4, null, vol if not run else -5.0)
			var rad := 2.5 if crouching else (9.0 if run else 5.0)
			Game.noise.emit(global_position, rad)
	head.position.y = head_y + sin(bob_t) * 0.025 * minf(hv, 3.0) / 3.0 * (1.0 if Game.settings.get("bob", true) else 0.0)
	# тряска камеры
	if shake_t > 0.0:
		shake_t -= delta
		cam.h_offset = randf_range(-1, 1) * shake_amp
		cam.v_offset = randf_range(-1, 1) * shake_amp
	else:
		cam.h_offset = 0.0; cam.v_offset = 0.0
	# --- рука с инструментом ---
	_update_viewmodel(delta, hv)
	# --- фонарик ---
	if flash.visible:
		battery = maxf(0.0, battery - delta * 0.33)
		if battery <= 0.0:
			flash.visible = false
		elif battery < 15.0 and randf() < 0.04:
			flash.light_energy = randf_range(0.2, 2.6)
		else:
			flash.light_energy = lerpf(flash.light_energy, 2.6, delta * 6.0)
	# --- цель и взаимодействие ---
	_update_target(delta)
	action_pressed = false

func _update_target(delta: float) -> void:
	target = null
	target_prompt = ""
	target_hint = ""
	ray.force_raycast_update()
	cleaning_now = false
	if ray.is_colliding():
		var c := ray.get_collider()
		if c is Interactable and c.enabled and c.get_prompt() != "":
			target = c
			target_prompt = c.get_prompt()
		elif c is StaticBody3D and c.has_meta("patch"):
			var p: DirtPatch = c.get_meta("patch")
			if is_instance_valid(p) and not p.done:
				target = p
				var ok := tool_id in p.required_tools()
				target_prompt = ("Убрать: " + p.name_ru()) if ok else ("Не тем инструментом: " + p.name_ru())
				if not ok:
					target_hint = _wrong_tool_hint(p)
	# действия
	if target is Interactable:
		if action_pressed:
			if carrying_bag and bag_node and (target as Interactable).has_meta("dump"):
				pass
			(target as Interactable).interact(self)
	elif target is DirtPatch:
		_clean(target, delta)
	if not (target is DirtPatch and action_held):
		_stop_tool_loops()
	_hint_cd = maxf(0.0, _hint_cd - delta)

func _wrong_tool_hint(p: DirtPatch) -> String:
	var names := []
	for t in p.required_tools():
		names.append(TOOL_NAMES[t].to_lower())
	return "Здесь нужен инструмент: " + " или ".join(names)

func _clean(p: DirtPatch, delta: float) -> void:
	if not action_held:
		return
	var ok := tool_id in p.required_tools()
	if not ok:
		if _hint_cd <= 0.0:
			Game.note(_wrong_tool_hint(p))
			_hint_cd = 3.0
		return
	var power := 1.0
	if tool_id == "mop":
		power = lerpf(0.3, 1.0, mop_clean)
		mop_clean = maxf(0.0, mop_clean - delta * 0.035)
		if mop_clean < 0.3 and _hint_cd <= 0.0:
			Game.note("Швабра грязная — прополощи в ведре.")
			_hint_cd = 6.0
	elif tool_id == "spray":
		if spray_amount <= 0.0:
			if _hint_cd <= 0.0:
				Game.note("Спрей пуст. Пополни в ящике с расходниками.")
				_hint_cd = 4.0
			return
		spray_amount = maxf(0.0, spray_amount - delta * 7.0)
	cleaning_now = true
	scrub_t += delta
	p.clean(tool_id, delta, power)
	_tool_loop_start()
	_noise_cd -= delta
	if _noise_cd <= 0.0:
		_noise_cd = 0.6
		var r: float = {"rag": 2.5, "mop": 4.0, "broom": 5.0, "vacuum": 15.0, "spray": 2.0}[tool_id]
		Game.noise.emit(global_position, r)

func _tool_loop_start() -> void:
	match tool_id:
		"vacuum":
			Audio.loop("vacuum", -4.0, "SFX")
		"spray":
			Audio.loop("spray", -8.0, "SFX")
		_:
			Audio.loop("rub_" + tool_id, -8.0, "SFX")

func _stop_tool_loops() -> void:
	for n in ["vacuum", "spray", "rub_rag", "rub_mop", "rub_broom"]:
		Audio.loop_stop(n)

func _update_viewmodel(delta: float, hv: float) -> void:
	var base := Vector3(0.28, -0.3, -0.55)
	var sway := Vector3(sin(bob_t * 0.5) * 0.012 * minf(hv, 3.0), abs(sin(bob_t)) * 0.012 * minf(hv, 3.0), 0)
	var scrub := Vector3.ZERO
	var rot := Vector3.ZERO
	if cleaning_now:
		var s := sin(scrub_t * 11.0)
		match tool_id:
			"rag": scrub = Vector3(s * 0.12, 0, -0.1 + s * 0.04); rot = Vector3(-60, 0, 0)
			"mop": scrub = Vector3(s * 0.15, -0.05, -0.1)
			"broom": scrub = Vector3(s * 0.14, -0.05, -0.1)
			"vacuum": scrub = Vector3(s * 0.04, -0.1, -0.1)
			"spray": scrub = Vector3(0, 0, s * 0.01); rot = Vector3(-15, 0, 0)
	else:
		match tool_id:
			"rag": rot = Vector3(-50, 0, 0)
			"spray": rot = Vector3(-15, 0, 0)
	vm.position = vm.position.lerp(base + sway + scrub, minf(1.0, delta * 14.0))
	vm.rotation_degrees = vm.rotation_degrees.lerp(rot, minf(1.0, delta * 10.0))
	vm.visible = not hiding

func shake(amp := 0.02, t := 0.4) -> void:
	shake_amp = amp
	shake_t = t

# ---------- прятки ----------
func enter_hide(spot: Interactable) -> void:
	if hiding or frozen:
		return
	hiding = spot
	_prev_pos = global_position
	_prev_yaw = rotation_degrees.y
	var hp: Vector3 = spot.get_meta("hide_pos")
	global_position = hp + Vector3(0, 0.05, 0)
	rotation_degrees.y = spot.get_meta("hide_yaw") + 180.0
	pitch = 0.0
	velocity = Vector3.ZERO
	shape.disabled = true
	flash.visible = false
	Audio.sfx("door_close", global_position, -6.0)
	Game.note("Вы спрятались. Нажмите «Действие», чтобы выйти.")

func exit_hide() -> void:
	if not hiding:
		return
	var yaw := deg_to_rad(float(hiding.get_meta("hide_yaw")))
	var out: Vector3 = hiding.get_meta("hide_pos") + Vector3(sin(yaw), 0, cos(yaw)) * 0.9
	hiding = null
	global_position = out + Vector3(0, 0.05, 0)
	shape.disabled = false
	Audio.sfx("door_open", global_position, -6.0)

func _hide_update(delta: float) -> void:
	head.position.y = lerpf(head.position.y, 1.5, delta * 8.0)
	look_delta = Vector2.ZERO
	cleaning_now = false
	_stop_tool_loops()
	target = null; target_prompt = "Выйти"
	if action_pressed:
		action_pressed = false
		exit_hide()

# ---------- состояния ----------
func is_hidden() -> bool:
	return hiding != null

func pickup_bag() -> void:
	carrying_bag = true
	if bag_node == null:
		bag_node = Props.make("bag")
		for c in bag_node.get_children():
			if c is StaticBody3D:
				c.queue_free()
		bag_node.scale = Vector3(0.5, 0.5, 0.5)
		bag_node.position = Vector3(-0.3, -0.62, -0.5)
		cam.add_child(bag_node)
	bag_node.visible = true

func drop_bag() -> void:
	carrying_bag = false
	if bag_node:
		bag_node.visible = false

func rinse_mop() -> void:
	mop_clean = 1.0

func look_at_point(p: Vector3, t := 0.3) -> void:
	var to := (p - global_position)
	var yaw_t := rad_to_deg(atan2(-to.x, -to.z))
	var pitch_t := rad_to_deg(atan2(to.y - 1.62, Vector2(to.x, to.z).length()))
	var tw := create_tween().set_parallel()
	tw.tween_property(self, "rotation_degrees:y", _closest_angle(rotation_degrees.y, yaw_t), t)
	tw.tween_property(self, "pitch", clampf(pitch_t, -80, 80), t)

func _closest_angle(from: float, to: float) -> float:
	return from + wrapf(to - from, -180.0, 180.0)
