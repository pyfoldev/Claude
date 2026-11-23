class_name Monster extends CharacterBody3D
## Универсальный монстр. Тип задаёт поведение: mimic, shadow, host, crawler, phantom, npc.

var type := "shadow"
var opts: Dictionary = {}
var model: Node3D
var level: Level
var player: Player
var head_height := 1.6
var state := "idle"
var timer := 0.0
var speed := 2.0
var hp := 3.0
var path: PackedVector3Array = PackedVector3Array()
var path_i := 0
var repath_cd := 0.0
var last_seen := Vector3.ZERO
var heard_pos := Vector3.ZERO
var anim_t := 0.0
var moving := false
var seen_time := 0.0
var disguise: Node3D
var maw: Node3D
var active := true
var catch_dist := 1.0
var _lunge_t := 0.0
var _lunge_dir := Vector3.ZERO
var _patrol_target := ""
var _door_cd := 0.0
var _search_t := 0.0
var _start_pos := Vector3.ZERO
var script_target := Vector3.ZERO
var has_target := false
var lifetime := -1.0

func is_chasing() -> bool:
	return state in ["chase", "lunge", "stalk"] and active

func _ready() -> void:
	level = Game.level
	add_to_group("monsters")
	collision_layer = 32
	collision_mask = 1
	_start_pos = global_position
	var cs := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.3
	cap.height = 1.6 if type != "crawler" else 0.7
	cs.shape = cap
	cs.position.y = cap.height / 2.0
	add_child(cs)
	match type:
		"mimic":
			_setup_mimic()
		"shadow":
			model = MonsterModels.build("shadow", opts)
			speed = opts.get("speed", 2.6)
			state = "stalk" if opts.get("active", true) else "idle"
		"host":
			model = MonsterModels.build("host")
			speed = opts.get("speed", 1.5)
			state = opts.get("state", "patrol")
			catch_dist = 1.2
		"crawler":
			model = MonsterModels.build("crawler")
			speed = opts.get("speed", 3.4)
			state = "stalk"
		"phantom":
			model = MonsterModels.build(opts.get("model", "shadow"), opts)
			state = "phantom"
			lifetime = opts.get("life", 6.0)
		"npc":
			model = MonsterModels.build(opts.get("model", "mother"))
			state = "npc"
		_:
			model = MonsterModels.build("shadow")
	if model:
		add_child(model)
		head_height = float(model.get_meta("head", 1.6))
	if opts.get("hidden", false):
		visible = false
		active = false

func _setup_mimic() -> void:
	model = Node3D.new()
	var kind: String = opts.get("disguise", "crate")
	disguise = Props.make(kind, opts.get("popts", {}))
	for c in disguise.get_children():
		if c is StaticBody3D:
			c.queue_free()
	model.add_child(disguise)
	head_height = 0.6
	state = "dormant"
	speed = 6.5
	catch_dist = 0.95

func wake() -> void:
	active = true
	visible = true
	if state == "idle":
		state = "stalk"

# ----------------------------------------------------------------- вспомогательное
func seen_by_player(margin := 0.0) -> bool:
	if player == null or not visible:
		return false
	var cam := player.cam
	var tgt := global_position + Vector3(0, head_height * 0.6, 0)
	var to := tgt - cam.global_position
	var d := to.length()
	if d < 0.4:
		return true
	var fwd := -cam.global_transform.basis.z
	if rad_to_deg(fwd.angle_to(to)) > 48.0 + margin:
		return false
	return _los(cam.global_position, tgt)

func _los(from: Vector3, to: Vector3) -> bool:
	var q := PhysicsRayQueryParameters3D.create(from, to, 1)
	q.exclude = [player.get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	return hit.is_empty()

func lit_by_flashlight() -> bool:
	if player == null or not player.flash.visible:
		return false
	var cam := player.cam
	var tgt := global_position + Vector3(0, head_height * 0.5, 0)
	var to := tgt - cam.global_position
	if to.length() > 12.0:
		return false
	var fwd := -cam.global_transform.basis.z
	if rad_to_deg(fwd.angle_to(to)) > 22.0:
		return false
	return _los(cam.global_position, tgt)

func dist_player() -> float:
	return global_position.distance_to(player.global_position)

func flat_dir_to(p: Vector3) -> Vector3:
	var d := p - global_position
	d.y = 0
	return d.normalized() if d.length() > 0.01 else Vector3.ZERO

func face(p: Vector3, rate := 8.0, delta := 0.016) -> void:
	var d := flat_dir_to(p)
	if d == Vector3.ZERO:
		return
	var target_yaw := atan2(-d.x, -d.z)
	# модели смотрят в -Z
	rotation.y = lerp_angle(rotation.y, target_yaw, minf(1.0, rate * delta))

func step_towards(p: Vector3, spd: float, delta: float) -> bool:
	# движение по прямой с вертикальным следованием за графом
	var d := p - global_position
	var flat := Vector3(d.x, 0, d.z)
	if flat.length() < 0.15:
		return true
	var dir := flat.normalized()
	velocity.x = dir.x * spd
	velocity.z = dir.z * spd
	var ty := p.y - 0.1
	velocity.y = clampf((ty - global_position.y) * 6.0, -4.0, 4.0) if absf(ty - global_position.y) > 0.05 else 0.0
	move_and_slide()
	face(p, 10.0, delta)
	moving = true
	return false

func follow_path(spd: float, delta: float) -> bool:
	if path_i >= path.size():
		return true
	if step_towards(path[path_i], spd, delta):
		path_i += 1
	return path_i >= path.size()

func plan(to: Vector3) -> void:
	path = level.b.find_path(global_position, to)
	path_i = 0
	# убрать точки позади
	if path.size() > 1 and path_i + 1 < path.size():
		var d0 := global_position.distance_to(path[0])
		if d0 < 0.8:
			path_i = 1
	repath_cd = 0.6

func path_chase(to: Vector3, spd: float, delta: float) -> void:
	repath_cd -= delta
	var los := _los(global_position + Vector3(0, 1.0, 0), to + Vector3(0, 1.0, 0)) and absf(global_position.y - to.y) < 0.8
	if los and dist_player() < 12.0 and to == player.global_position:
		step_towards(to, spd, delta)
		path = PackedVector3Array()
		return
	if repath_cd <= 0.0 or path.is_empty():
		plan(to)
	follow_path(spd, delta)

func open_doors_near(delta: float) -> void:
	_door_cd -= delta
	if _door_cd > 0.0:
		return
	_door_cd = 0.25
	for d in level.b.doors:
		var n: Door = d.get("node")
		if n == null or n.is_open:
			continue
		if n.global_position.distance_to(global_position) < 1.5:
			if n.jammed:
				continue
			if n.locked:
				n.locked = false
			n.set_open(true)

func animate(delta: float) -> void:
	var body := model.get_node_or_null("body") if model else null
	if body == null:
		return
	anim_t += delta * (6.0 if moving else 1.5)
	var amp := 0.7 if moving else 0.05
	for nm in ["arm_l", "arm_r", "leg_l", "leg_r"]:
		var n: Node3D = body.get_node_or_null(nm)
		if n:
			var ph := 0.0 if nm.ends_with("_l") else PI
			if nm.begins_with("arm"):
				ph += PI
			n.rotation.x = sin(anim_t + ph) * amp
	for i in 6:
		var l: Node3D = body.get_node_or_null("leg_%d" % i)
		if l:
			l.rotation.x = sin(anim_t * 1.5 + i) * 0.4 * (1.0 if moving else 0.2)
	moving = false

# ----------------------------------------------------------------- главный цикл
func _physics_process(delta: float) -> void:
	if level == null or level.ended:
		return
	if player == null:
		player = Game.player
		if player == null:
			return
	if not active:
		return
	if lifetime > 0.0:
		lifetime -= delta
		if lifetime <= 0.0:
			queue_free()
			return
	match type:
		"mimic": _tick_mimic(delta)
		"shadow": _tick_shadow(delta)
		"host": _tick_host(delta)
		"crawler": _tick_crawler(delta)
		"phantom": _tick_phantom(delta)
		"npc": _tick_npc(delta)
	animate(delta)

func catch_player() -> void:
	if level.ended or player.frozen:
		return
	# ставим монстра перед камерой
	var fwd := -player.global_transform.basis.z
	fwd.y = 0
	global_position = player.global_position + fwd.normalized() * 1.05
	global_position.y = player.global_position.y
	look_at(Vector3(player.global_position.x, global_position.y, player.global_position.z), Vector3.UP)
	rotate_y(PI)
	level.jumpscare(self)

func play_scare() -> void:
	if model:
		var tw := create_tween()
		tw.tween_property(model, "scale", model.scale * 1.35, 0.2)
		for e in model.find_children("eye", "MeshInstance3D", true, false):
			e.scale = Vector3(1.8, 1.8, 1.0)
	if type == "mimic":
		_reveal_form()
		var m := maw
		if m:
			m.scale = Vector3(1.5, 1.5, 1.5)

func _reveal_form() -> void:
	if disguise:
		disguise.scale = Vector3(1, 0.7, 1)
	if maw == null:
		maw = MonsterModels.add_maw(model, 0.8)
		maw.position = Vector3(0, 0.05, 0.35)

# ----------------------------------------------------------------- Мимик
func _tick_mimic(delta: float) -> void:
	var d := dist_player()
	match state:
		"dormant":
			# «дыхание» — едва заметное дрожание
			var br := 1.0 + sin(Time.get_ticks_msec() * 0.004) * 0.012
			disguise.scale = Vector3(br, br + 0.004, br)
			var trig: float = opts.get("radius", 2.0)
			if d < trig and not player.is_hidden() and _los(global_position + Vector3(0, 0.5, 0), player.global_position + Vector3(0, 1.2, 0)):
				timer += delta
				if timer > opts.get("delay", 0.7):
					state = "wake"; timer = 0.0
					Audio.sfx("mimic_growl", global_position, 2.0)
					_reveal_form()
					Game.sanity -= 8.0
			else:
				timer = maxf(0.0, timer - delta)
		"wake":
			timer += delta
			face(player.global_position, 12.0, delta)
			disguise.position.x = sin(timer * 60.0) * 0.02
			# игрок может отпугнуть фонариком
			if lit_by_flashlight():
				_banish()
				return
			if timer > 0.9:
				state = "lunge"; timer = 0.0
				_lunge_t = 1.1
				Audio.sfx("mimic_lunge", global_position, 0.0)
		"lunge":
			_lunge_t -= delta
			if lit_by_flashlight():
				_banish()
				return
			var tgt := player.global_position
			if not player.is_hidden():
				step_towards(tgt, speed, delta)
			else:
				_lunge_t = 0
			if d < catch_dist and not player.is_hidden():
				catch_player()
			if _lunge_t <= 0.0:
				state = "tired"; timer = 0.0
		"tired":
			timer += delta
			if timer > 2.0 or lit_by_flashlight():
				_banish()
		"gone":
			pass

func _banish() -> void:
	state = "gone"
	Audio.sfx("mimic_screech", global_position, 0.0)
	Game.sanity += 6.0
	Game.note("Оно отпрянуло от света.")
	var tw := create_tween()
	tw.tween_property(model, "scale", Vector3(0.01, 0.01, 0.01), 0.35)
	tw.tween_callback(queue_free)

# ----------------------------------------------------------------- Тень
func _tick_shadow(delta: float) -> void:
	if state == "idle":
		return
	var d := dist_player()
	var seen := seen_by_player(6.0)
	if seen:
		seen_time += delta
		if d < 9.0:
			Game.sanity -= 2.5 * delta
		if lit_by_flashlight():
			timer += delta
			if timer > 1.4:
				_dissolve()
				return
		moving = false
		# отступает от света понемногу
		if lit_by_flashlight():
			var away := (global_position - player.global_position)
			away.y = 0
			velocity = away.normalized() * 1.2
			move_and_slide()
		return
	timer = maxf(0.0, timer - delta * 0.5)
	var spd := speed
	if d > 12.0:
		spd *= 1.4
	path_chase(player.global_position, spd, delta)
	open_doors_near(delta)
	if d < catch_dist + 0.1 and not player.is_hidden():
		catch_player()

func _dissolve() -> void:
	Audio.sfx("shadow_die", global_position, 0.0)
	Game.sanity += 4.0
	active = false
	var tw := create_tween()
	tw.tween_property(model, "scale", Vector3(0.01, 1.6, 0.01), 0.5)
	tw.tween_callback(queue_free)

# ----------------------------------------------------------------- Хозяин
func _ready_host_signals() -> void:
	Game.noise.connect(_on_noise)

var _host_init := false

func _on_noise(pos: Vector3, radius: float) -> void:
	if type != "host" or not active or state == "chase":
		return
	var d := global_position.distance_to(pos)
	if d <= radius * 1.6:
		heard_pos = pos
		if state != "investigate" or global_position.distance_to(heard_pos) > 1.0:
			state = "investigate"
			timer = 0.0
			plan(pos)

func _tick_host(delta: float) -> void:
	if not _host_init:
		_host_init = true
		_ready_host_signals()
	var d := dist_player()
	var can_see := false
	if not player.is_hidden() and d < (16.0 if player.flash.visible else 11.0) and absf(player.global_position.y - global_position.y) < 2.0:
		var dirp := flat_dir_to(player.global_position)
		var fwd := -global_transform.basis.z
		var ang := rad_to_deg(fwd.angle_to(dirp))
		if (ang < 70.0 or d < 3.0) and _los(global_position + Vector3(0, 1.8, 0), player.global_position + Vector3(0, 1.2, 0)):
			can_see = true
	open_doors_near(delta)
	match state:
		"patrol":
			speed = 1.5
			if _patrol_target == "" or path_i >= path.size():
				_patrol_target = level.b.random_room()
				plan(level.b.room_center(_patrol_target))
				timer = 0.0
			follow_path(speed, delta)
			if path_i >= path.size():
				timer += delta
				if timer > 1.5:
					_patrol_target = ""
			if can_see:
				_begin_chase()
		"investigate":
			speed = 2.2
			follow_path(speed, delta)
			if path_i >= path.size():
				timer += delta
				if timer > 2.0:
					state = "patrol"; _patrol_target = ""
			if can_see:
				_begin_chase()
		"chase":
			speed = opts.get("chase_speed", 3.6)
			if can_see:
				last_seen = player.global_position
				path_chase(player.global_position, speed, delta)
				_search_t = 0.0
				if d < catch_dist and not player.is_hidden():
					catch_player()
			else:
				_search_t += delta
				path_chase(last_seen, speed, delta)
				if (global_position.distance_to(last_seen) < 1.3 and _search_t > 0.5) or _search_t > 6.0:
					state = "search"; timer = 0.0
		"search":
			speed = 1.6
			timer += delta
			moving = false
			# оглядывается; если игрок спрятан рядом — шанс найти
			rotation.y += delta * 1.5
			if player.is_hidden() and d < 3.2 and timer > 2.5:
				if randf() < 0.45 or opts.get("always_find", false):
					catch_player()
				else:
					timer = 0.0
					state = "patrol"; _patrol_target = ""
					Game.note("Он ушёл…")
			elif timer > 4.0:
				state = "patrol"; _patrol_target = ""
			if can_see:
				_begin_chase()
		"scripted":
			if has_target:
				if step_towards(script_target, opts.get("script_speed", 2.0), delta):
					has_target = false
	# присутствие: нагнетает страх
	if d < 8.0 and state != "scripted":
		Game.sanity -= 0.6 * delta
	if state == "chase":
		Audio.loop("host_chase", -6.0, "SFX")
	else:
		Audio.loop_set("host_chase", -40.0)

func _begin_chase() -> void:
	if state == "chase":
		return
	state = "chase"
	last_seen = player.global_position
	Audio.sfx("host_roar", global_position, 2.0)
	Game.note("Он заметил тебя!")
	level.hud.glitch(0.7)
	player.shake(0.02, 0.5)

# ----------------------------------------------------------------- Ползун
func _tick_crawler(delta: float) -> void:
	var d := dist_player()
	if lit_by_flashlight() and d < 8.0:
		timer += delta
		var away := (global_position - player.global_position)
		away.y = 0
		velocity = away.normalized() * 2.5
		move_and_slide()
		if timer > 2.0:
			_dissolve()
		return
	path_chase(player.global_position, speed, delta)
	if d < 1.0 and not player.is_hidden():
		catch_player()

func hit_spray(delta: float) -> void:
	hp -= delta * 1.6
	if hp <= 0.0:
		Audio.sfx("crawler_die", global_position)
		active = false
		var tw := create_tween()
		tw.tween_property(model, "scale", Vector3(1.6, 0.05, 1.6), 0.4)
		tw.tween_callback(queue_free)

# ----------------------------------------------------------------- Фантом (не опасен)
func _tick_phantom(delta: float) -> void:
	face(player.global_position, 6.0, delta)
	if seen_by_player(0.0):
		seen_time += delta
		if seen_time > opts.get("vanish_after", 1.0):
			Game.sanity -= opts.get("sanity", 4.0)
			level.hud.glitch(0.6)
			queue_free()
	if opts.get("walk", false):
		step_towards(player.global_position, opts.get("speed", 0.8), delta)

func _tick_npc(delta: float) -> void:
	if has_target:
		if step_towards(script_target, opts.get("script_speed", 1.2), delta):
			has_target = false
	elif opts.get("face_player", true):
		face(player.global_position, 4.0, delta)

func walk_to(p: Vector3) -> void:
	script_target = p
	has_target = true
