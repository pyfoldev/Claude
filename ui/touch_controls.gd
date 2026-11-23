extends Control
## Виртуальные элементы управления: плавающий стик слева, взгляд справа, кнопки.

var player: Player
var hud
var stick_id := -1
var stick_origin := Vector2.ZERO
var stick_pos := Vector2.ZERO
var look_id := -1
var look_last := Vector2.ZERO
var btn_touch: Dictionary = {}     # touch id -> button name
var buttons: Dictionary = {}
var pressed_btn: Dictionary = {}
const STICK_R := 110.0

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_preset(Control.PRESET_FULL_RECT)
	resized.connect(_layout)
	_layout()

func _layout() -> void:
	var s := size
	var k := float(Game.settings.btn_scale)
	buttons = {
		"action": {"c": Vector2(s.x - 140 * k, s.y - 150 * k), "r": 82 * k, "label": "ДЕЙСТВИЕ"},
		"flash": {"c": Vector2(s.x - 300 * k, s.y - 95 * k), "r": 52 * k, "label": "ФОНАРЬ"},
		"crouch": {"c": Vector2(s.x - 300 * k, s.y - 225 * k), "r": 48 * k, "label": "ПРИСЕСТЬ"},
		"tool_next": {"c": Vector2(s.x - 140 * k, s.y - 320 * k), "r": 48 * k, "label": "СМЕНА"},
		"notebook": {"c": Vector2(s.x - 70, 62), "r": 40, "label": "БЛОКНОТ"},
		"pause": {"c": Vector2(s.x - 160, 62), "r": 34, "label": "II"},
	}

func _btn_at(p: Vector2) -> String:
	for n in buttons:
		var b: Dictionary = buttons[n]
		if p.distance_to(b.c) <= b.r + 12.0:
			return n
	return ""

func _input(event: InputEvent) -> void:
	if player == null or not visible:
		return
	if event is InputEventScreenTouch:
		var p: Vector2 = event.position * (size / get_viewport().get_visible_rect().size) if false else _to_local(event.position)
		if event.pressed and hud and hud.tool_box.visible and hud.tool_box.get_global_rect().has_point(p):
			return
		if event.pressed:
			var b := _btn_at(p)
			if b != "":
				btn_touch[event.index] = b
				_btn_down(b, true)
			elif p.x < size.x * 0.42 and p.y > size.y * 0.25 and stick_id == -1:
				stick_id = event.index
				stick_origin = p
				stick_pos = p
			elif look_id == -1:
				look_id = event.index
				look_last = p
		else:
			if btn_touch.has(event.index):
				_btn_down(btn_touch[event.index], false)
				btn_touch.erase(event.index)
			if event.index == stick_id:
				stick_id = -1
				player.move_input = Vector2.ZERO
			if event.index == look_id:
				look_id = -1
		queue_redraw()
	elif event is InputEventScreenDrag:
		var p2 := _to_local(event.position)
		if event.index == stick_id:
			stick_pos = p2
			var v := (stick_pos - stick_origin) / STICK_R
			player.move_input = Vector2(v.x, -v.y).limit_length(1.0)
			if v.length() > 1.0:
				stick_origin = stick_pos - v.normalized() * STICK_R
		elif event.index == look_id:
			player.look_delta += (p2 - look_last) * 0.55
			look_last = p2
		queue_redraw()

func _to_local(p: Vector2) -> Vector2:
	# позиции событий экрана приходят в координатах окна; приводим к координатам canvas
	return get_viewport().get_canvas_transform().affine_inverse() * p

func _btn_down(name: String, down: bool) -> void:
	pressed_btn[name] = down
	match name:
		"action":
			player.action_held = down
			if down:
				player.action_pressed = true
		"flash":
			if down: player.toggle_flash()
		"crouch":
			if down: player.crouching = not player.crouching
		"tool_next":
			if down: player.next_tool()
		"notebook":
			if down: hud.toggle_notebook()
		"pause":
			if down: hud.toggle_pause()

func _process(_d: float) -> void:
	if player and (stick_id != -1 or not btn_touch.is_empty()):
		queue_redraw()

func _draw() -> void:
	if player == null:
		return
	var a := 0.35
	for n in buttons:
		var b: Dictionary = buttons[n]
		var on: bool = pressed_btn.get(n, false)
		var col := Color(1, 1, 1, 0.5 if on else a)
		draw_circle(b.c, b.r, Color(0.05, 0.05, 0.06, 0.45))
		draw_arc(b.c, b.r, 0, TAU, 40, col, 3.0)
		var lbl: String = b.label
		if n == "action" and player.hiding:
			lbl = "ВЫЙТИ"
		if n == "crouch" and player.crouching:
			lbl = "ВСТАТЬ"
		var f := ThemeDB.fallback_font
		var fs := 15 if b.r > 45 else 12
		var ts := f.get_string_size(lbl, HORIZONTAL_ALIGNMENT_CENTER, -1, fs)
		draw_string(f, b.c + Vector2(-ts.x / 2.0, 5), lbl, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(1, 1, 1, 0.75))
	if stick_id != -1:
		draw_circle(stick_origin, STICK_R, Color(1, 1, 1, 0.08))
		draw_arc(stick_origin, STICK_R, 0, TAU, 48, Color(1, 1, 1, 0.3), 3.0)
		draw_circle(stick_pos if stick_pos.distance_to(stick_origin) < STICK_R else stick_origin + (stick_pos - stick_origin).normalized() * STICK_R, 40, Color(1, 1, 1, 0.25))
	else:
		draw_arc(Vector2(190, size.y - 170), STICK_R, 0, TAU, 48, Color(1, 1, 1, 0.12), 3.0)
