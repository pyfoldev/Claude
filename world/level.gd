class_name Level extends Node3D
## Корневая сцена главы: строит мир, игрока, HUD, задачи, чекпоинты, скримеры.

var b: Builder
var player: Player
var hud: HUD
var chap
var chapter := 1
var cur_room := ""
var prev_room := ""
var ended := false
var time_in := 0.0
var save_cd := 0.0
var objective_override := ""
var carrying_note_id := ""
var noise_events := 0
var monsters_node: Node3D
var _note_open_cb: Callable = Callable()
var rooms_visited: Dictionary = {}
var scared_flag := false
var gameplay_locked := false

func _ready() -> void:
	Game.level = self
	chapter = Game.chapter
	get_viewport().scaling_3d_scale = float(Game.settings.render_scale)
	SettingsUI.apply_all(get_viewport())
	_make_env()
	b = Builder.new(self, self)
	chap = load("res://world/chapters/ch%d.gd" % chapter).new()
	chap.build(self)
	# игрок
	player = Player.new()
	add_child(player)
	player.position = b.spawn
	player.rotation_degrees.y = b.spawn_yaw
	hud = HUD.new()
	add_child(hud)
	hud.bind(player, self)
	for t in b.tasks.values():
		pass
	for pid in b.patches:
		var p: DirtPatch = b.patches[pid]
		p.cleaned.connect(_on_patch_cleaned)
	_restore_checkpoint()
	Director.start(self)
	if chap.has_method("start"):
		chap.start(self)
	Game.note_found.connect(func(_i): pass)
	if Game.touch_mode == false:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	_intro()

func _make_env() -> void:
	var we := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.01, 0.01, 0.02)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.32, 0.34, 0.45)
	e.ambient_light_energy = 0.55
	e.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	e.tonemap_exposure = 1.1
	e.adjustment_enabled = true
	e.adjustment_contrast = 1.12
	e.adjustment_saturation = 0.82
	e.fog_enabled = true
	e.fog_light_color = Color(0.03, 0.03, 0.05)
	e.fog_density = 0.035
	we.environment = e
	add_child(we)
	env_node = we
var env_node: WorldEnvironment

func set_ambient(c: Color, energy := 0.55) -> void:
	env_node.environment.ambient_light_color = c
	env_node.environment.ambient_light_energy = energy

# ------------------------------------------------ вступление
func _intro() -> void:
	gameplay_locked = true
	player.frozen = true
	hud.fade.color.a = 1.0
	var info: Dictionary = Story.CHAPTERS[chapter]
	var card := Label.new()
	card.text = "ГЛАВА %d\n%s\n\n[ %s ]" % [chapter, info.title, info.sub]
	card.add_theme_font_size_override("font_size", 40)
	card.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	card.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	card.set_anchors_preset(Control.PRESET_FULL_RECT)
	card.modulate.a = 0.0
	hud.add_child(card)
	var sms := Label.new()
	sms.text = info.sms
	sms.add_theme_font_size_override("font_size", 24)
	sms.add_theme_color_override("font_color", Color(0.5, 0.75, 1.0))
	sms.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sms.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	sms.position = Vector2(-400, -150)
	sms.size = Vector2(800, 80)
	sms.modulate.a = 0.0
	hud.add_child(sms)
	var tw := create_tween()
	tw.tween_property(card, "modulate:a", 1.0, 1.2)
	tw.tween_callback(func(): Audio.sfx("sms", null, -2.0))
	tw.tween_property(sms, "modulate:a", 1.0, 0.6)
	tw.tween_interval(3.2)
	tw.tween_property(card, "modulate:a", 0.0, 1.0)
	tw.parallel().tween_property(sms, "modulate:a", 0.0, 1.0)
	tw.tween_callback(func():
		card.queue_free(); sms.queue_free()
		hud.fade_to(0.0, 1.5)
		player.frozen = false
		gameplay_locked = false
		Audio.music(info.music)
		Audio.loop(info.ambience, -14.0)
		if info.has("intro_line") and Game.checkpoint.is_empty():
			Audio.say(info.intro_line)
		if chap.has_method("on_begin"):
			chap.on_begin(self))
	if not Game.checkpoint.is_empty():
		tw.kill()
		card.queue_free(); sms.queue_free()
		hud.fade.color.a = 1.0
		hud.fade_to(0.0, 1.2)
		player.frozen = false
		gameplay_locked = false
		Audio.music(info.music)
		Audio.loop(info.ambience, -14.0)
		if chap.has_method("on_begin"):
			chap.on_begin(self)

# ------------------------------------------------ комнаты и время
func _physics_process(delta: float) -> void:
	if ended:
		return
	time_in += delta
	var r := b.room_at(player.global_position)
	if r != cur_room:
		prev_room = cur_room
		cur_room = r
		if r != "" and not rooms_visited.has(r):
			rooms_visited[r] = true
			if chap.has_method("on_room_first"):
				chap.on_room_first(self, r)
		if chap.has_method("on_room"):
			chap.on_room(self, r)
	_update_sanity(delta)
	if chap.has_method("tick"):
		chap.tick(self, delta)
	save_cd -= delta
	if save_cd <= 0.0:
		save_cd = 45.0
		if not _any_monster_chasing():
			autosave()

func _any_monster_chasing() -> bool:
	for m in get_tree().get_nodes_in_group("monsters"):
		if m.has_method("is_chasing") and m.is_chasing():
			return true
	return false

func _update_sanity(delta: float) -> void:
	if player.frozen:
		return
	var rm: Dictionary = b.rooms.get(cur_room, {})
	var lit := true
	if rm.size() > 0:
		var ln = rm.get("light_node")
		lit = ln != null and ln.light_energy > 0.25 and ln.visible
	if player.flash.visible:
		lit = true
	if not lit:
		Game.sanity -= 1.4 * delta
	elif Game.sanity < 100.0:
		Game.sanity += (0.5 if cur_room != "" else 0.2) * delta

# ------------------------------------------------ задачи
func task_progress(id: String) -> float:
	var t: Dictionary = b.tasks[id]
	if t.done:
		return 1.0
	if t.manual:
		if t.need > 0:
			return float(t.count) / float(t.need)
		return 0.0
	if t.patches.is_empty():
		return 0.0
	var tot := 0.0
	var wsum := 0.0
	for p in t.patches:
		var w := _weight(p)
		wsum += w
		tot += w * (1.0 - p.amount)
	return tot / maxf(wsum, 0.001)

func _weight(p: DirtPatch) -> float:
	return clampf(sqrt(p.size.x * p.size.y), 0.5, 2.0)

func progress() -> float:
	var tot := 0.0
	var wsum := 0.0
	for id in b.task_order:
		var t: Dictionary = b.tasks[id]
		if t.optional:
			continue
		if t.manual:
			wsum += 1.0
			tot += task_progress(id)
		else:
			for p in t.patches:
				var w := _weight(p)
				wsum += w
				tot += w * (1.0 - p.amount)
	return tot / maxf(wsum, 0.001)

func current_objective() -> String:
	if objective_override != "":
		return objective_override
	for id in b.task_order:
		var t: Dictionary = b.tasks[id]
		if not t.done and not t.optional and not t.hidden:
			return "• " + t.text
	return "• Закончить работу"

func complete_task(id: String) -> void:
	if not b.tasks.has(id):
		return
	var t: Dictionary = b.tasks[id]
	if t.done:
		return
	t.done = true
	Audio.sfx("task_done", null, -6.0)
	Game.note("✓ " + t.text)
	if chap.has_method("on_task_done"):
		chap.on_task_done(self, id)
	autosave()

func add_manual(id: String, n := 1) -> void:
	var t: Dictionary = b.tasks[id]
	t.count += n
	if t.need > 0 and t.count >= t.need:
		complete_task(id)

func unlock_task(id: String) -> void:
	if b.tasks.has(id):
		b.tasks[id].hidden = false
		Game.note("Новое задание: " + b.tasks[id].text)

func _on_patch_cleaned(p: DirtPatch) -> void:
	Audio.sfx("clean_done", null, -10.0)
	if p.task_id != "" and b.tasks.has(p.task_id):
		var t: Dictionary = b.tasks[p.task_id]
		var all := true
		for q in t.patches:
			if not q.done:
				all = false
				break
		if all and not t.manual:
			complete_task(p.task_id)
	if p.story and chap.has_method("on_story_patch"):
		chap.on_story_patch(self, p)
	Game.sanity += 1.5

func all_required_done() -> bool:
	for id in b.task_order:
		var t: Dictionary = b.tasks[id]
		if not t.optional and not t.done:
			return false
	return true

# ------------------------------------------------ записки
func read_note(id: String) -> void:
	if not NotesDB.NOTES.has(id):
		return
	var first := not Game.notes_found.has(id)
	Game.notes_found[id] = true
	var n: Dictionary = NotesDB.NOTES[id]
	if first and n.kind == "true":
		Game.truth += 1
		Audio.sfx("note_true", null, -2.0)
	else:
		Audio.sfx("paper", null, -4.0)
	carrying_note_id = id
	hud.show_note(id)
	if first and b.notes_nodes.has(id):
		var nn: Node3D = b.notes_nodes[id].node
		if is_instance_valid(nn):
			nn.visible = true
	if n.has("vo"):
		Audio.say(n.vo, true)
	Game.save_game()

func on_note_closed() -> void:
	var id := carrying_note_id
	carrying_note_id = ""
	if id != "" and chap.has_method("on_note_read"):
		chap.on_note_read(self, id)

func reveal_note(id: String) -> void:
	if b.notes_nodes.has(id):
		var nn: Node3D = b.notes_nodes[id].node
		nn.visible = true
		b.notes_nodes[id].it.enabled = true

func hide_note(id: String) -> void:
	if b.notes_nodes.has(id):
		b.notes_nodes[id].node.visible = false
		b.notes_nodes[id].it.enabled = false

# ------------------------------------------------ монстры
func make_monster(type: String, pos: Vector3, opts := {}) -> Node:
	var m := Monster.new()
	m.type = type
	m.opts = opts
	add_child(m)
	m.global_position = pos
	return m

func say(id: String, priority := false) -> void:
	Audio.say(id, priority)

func door_between(a: String, c: String) -> Door:
	for d in b.doors:
		if (d.a == a and d.b == c) or (d.a == c and d.b == a):
			return d.node
	return null

# ------------------------------------------------ скример и смерть
func jumpscare(m: Node, big := true) -> void:
	if ended or player.frozen:
		return
	player.frozen = true
	player.exit_hide()
	player.flash.visible = false
	Director.paused = true
	Audio.stop_all_loops()
	var head_pos: Vector3 = m.global_position + Vector3(0, m.head_height, 0)
	player.look_at_point(head_pos, 0.12)
	if m.has_method("play_scare"):
		m.play_scare()
	Audio.sfx("jumpscare", null, 3.0)
	Audio.sfx("scream", null, -2.0)
	hud.flash_screen(1.0)
	hud.red_flash(0.5)
	hud.glitch(1.0)
	player.shake(0.06, 1.2)
	var cam := player.cam
	var tw := create_tween()
	tw.tween_property(cam, "fov", 45.0, 0.25)
	tw.tween_interval(0.9)
	tw.tween_callback(func(): hud.fade_to(1.0, 0.25))
	tw.tween_interval(0.5)
	tw.tween_callback(_after_death)

func _after_death() -> void:
	Game.deaths_total += 1
	Game.deaths_chapter += 1
	Game.save_game()
	var info := ["Они всегда рядом.", "Не оборачивайся.", "Дом не прощает шума.", "Попробуй ещё раз.", "Ты стал частью беспорядка."]
	hud.show_center(info[randi() % info.size()], 1.4)
	await get_tree().create_timer(2.0).timeout
	Game.start_chapter(chapter, true)

# ------------------------------------------------ чекпоинты
func autosave() -> void:
	var pd := {}
	for pid in b.patches:
		pd[pid] = b.patches[pid].amount
	var tdone := []
	for id in b.tasks:
		if b.tasks[id].done:
			tdone.append(id)
	var cnt := {}
	for id in b.tasks:
		cnt[id] = b.tasks[id].count
	Game.checkpoint = {
		"pos": [player.global_position.x, player.global_position.y, player.global_position.z],
		"yaw": player.rotation_degrees.y,
		"patches": pd, "tasks": tdone, "counts": cnt,
		"flags": Game.flags.duplicate(), "chapter": chapter,
		"battery": player.battery, "spray": player.spray_amount,
	}
	Game.note_found.emit("")
	Game.save_game()

func _restore_checkpoint() -> void:
	var cp: Dictionary = Game.checkpoint
	if cp.is_empty() or cp.get("chapter", -1) != chapter:
		Game.checkpoint = {}
		return
	for pid in cp.patches:
		if b.patches.has(pid):
			b.patches[pid].set_amount(cp.patches[pid])
	for id in cp.tasks:
		if b.tasks.has(id):
			b.tasks[id].done = true
	for id in cp.counts:
		if b.tasks.has(id):
			b.tasks[id].count = cp.counts[id]
	Game.flags = cp.flags.duplicate()
	var p = cp.pos
	player.global_position = Vector3(p[0], p[1] + 0.1, p[2])
	player.rotation_degrees.y = cp.yaw
	player.battery = cp.battery
	player.spray_amount = cp.spray
	if chap.has_method("restore"):
		chap.restore(self)

# ------------------------------------------------ конец главы
func try_finish() -> void:
	if ended:
		return
	var gate: Array = [true, ""]
	if chap.has_method("finish_gate"):
		gate = chap.finish_gate(self)
	if not gate[0]:
		Game.note(gate[1])
		return
	end_chapter()

func end_chapter(next_override := -1) -> void:
	if ended:
		return
	ended = true
	player.frozen = true
	Audio.stop_all_loops()
	Game.finish_chapter()
	var tw := hud.fade_to(1.0, 1.5)
	await tw.finished
	await _chapter_summary()
	var nxt := next_override if next_override > 0 else chapter + 1
	if nxt > Game.MAX_CHAPTER:
		Game.to_menu()
	else:
		Game.start_chapter(nxt)

func _chapter_summary() -> void:
	var pct := int(progress() * 100.0)
	var grade := "S" if pct >= 98 else ("A" if pct >= 85 else ("B" if pct >= 65 else ("C" if pct >= 40 else "D")))
	var l := Label.new()
	l.text = "ГЛАВА %d ЗАВЕРШЕНА\n\nЧистота: %d%%   Оценка: %s\nЗаписок найдено: %d   Смертей: %d\n\nСМС: «%s»" % [chapter, pct, grade, Game.found_count(), Game.deaths_chapter, Story.CHAPTERS[chapter].outro_sms]
	l.add_theme_font_size_override("font_size", 30)
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	l.set_anchors_preset(Control.PRESET_FULL_RECT)
	l.modulate.a = 0.0
	hud.add_child(l)
	var tw := create_tween()
	tw.tween_property(l, "modulate:a", 1.0, 1.0)
	tw.tween_interval(5.5)
	await tw.finished
