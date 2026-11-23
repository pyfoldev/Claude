class_name HUD extends CanvasLayer
## Интерфейс уровня: прицел, подсказки, задачи, субтитры, блокнот, записки, пауза.

signal resume_requested

var player: Player
var level
var crosshair: Control
var prompt_lbl: Label
var toast_lbl: Label
var sub_panel: PanelContainer
var sub_lbl: RichTextLabel
var task_lbl: Label
var obj_lbl: Label
var tool_box: VBoxContainer
var tool_btns: Dictionary = {}
var bars: Control
var post: ColorRect
var post_mat: ShaderMaterial
var fade: ColorRect
var touch: Control
var notebook: Control
var note_view: Control
var pause_menu: Control
var center_msg: Label
var _toasts: Array = []
var _toast_t := 0.0
var _time := 0.0
var flash_v := 0.0
var tint_v := 0.0
var glitch_v := 0.0
var _sub_t := 0.0
var nb_tab := 0
var nb_content: RichTextLabel
var overlay_open := false

func _ready() -> void:
	layer = 10
	process_mode = Node.PROCESS_MODE_ALWAYS
	# --- постобработка ---
	post = ColorRect.new()
	post.set_anchors_preset(Control.PRESET_FULL_RECT)
	post.mouse_filter = Control.MOUSE_FILTER_IGNORE
	post_mat = ShaderMaterial.new()
	post_mat.shader = load("res://shaders/post.gdshader")
	post.material = post_mat
	add_child(post)
	# --- прицел ---
	crosshair = Control.new()
	crosshair.set_anchors_preset(Control.PRESET_CENTER)
	crosshair.mouse_filter = Control.MOUSE_FILTER_IGNORE
	crosshair.draw.connect(_draw_cross)
	add_child(crosshair)
	prompt_lbl = _label("", 22, Control.PRESET_CENTER)
	prompt_lbl.position = Vector2(-300, 40)
	prompt_lbl.size = Vector2(600, 40)
	prompt_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	prompt_lbl.add_theme_color_override("font_outline_color", Color.BLACK)
	prompt_lbl.add_theme_constant_override("outline_size", 6)
	toast_lbl = _label("", 22, Control.PRESET_CENTER_TOP)
	toast_lbl.position = Vector2(-380, 86)
	toast_lbl.size = Vector2(760, 60)
	toast_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	toast_lbl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	toast_lbl.add_theme_color_override("font_outline_color", Color.BLACK)
	toast_lbl.add_theme_constant_override("outline_size", 6)
	toast_lbl.modulate.a = 0.0
	task_lbl = _label("", 20, Control.PRESET_TOP_LEFT)
	task_lbl.position = Vector2(24, 18)
	task_lbl.add_theme_color_override("font_outline_color", Color.BLACK)
	task_lbl.add_theme_constant_override("outline_size", 5)
	obj_lbl = _label("", 17, Control.PRESET_TOP_LEFT)
	obj_lbl.position = Vector2(24, 48)
	obj_lbl.modulate = Color(1, 1, 1, 0.75)
	obj_lbl.add_theme_color_override("font_outline_color", Color.BLACK)
	obj_lbl.add_theme_constant_override("outline_size", 5)
	# --- субтитры ---
	sub_panel = PanelContainer.new()
	sub_panel.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	sub_panel.position = Vector2(-420, -120)
	sub_panel.custom_minimum_size = Vector2(840, 0)
	sub_panel.size = Vector2(840, 60)
	sub_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0, 0, 0, 0.55)
	sb.set_corner_radius_all(6)
	sb.set_content_margin_all(10)
	sub_panel.add_theme_stylebox_override("panel", sb)
	sub_lbl = RichTextLabel.new()
	sub_lbl.bbcode_enabled = true
	sub_lbl.fit_content = true
	sub_lbl.scroll_active = false
	sub_lbl.add_theme_font_size_override("normal_font_size", 22)
	sub_lbl.mouse_filter = Control.MOUSE_FILTER_IGNORE
	sub_panel.add_child(sub_lbl)
	sub_panel.visible = false
	add_child(sub_panel)
	# --- инструменты ---
	tool_box = VBoxContainer.new()
	tool_box.set_anchors_preset(Control.PRESET_CENTER_RIGHT)
	tool_box.position = Vector2(-110, -150)
	tool_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(tool_box)
	for t in Player.TOOLS:
		var b := Button.new()
		b.text = Player.TOOL_NAMES[t]
		b.custom_minimum_size = Vector2(100, 46)
		b.focus_mode = Control.FOCUS_NONE
		b.pressed.connect(func(): if player: player.set_tool(t))
		b.add_theme_font_size_override("font_size", 15)
		tool_box.add_child(b)
		tool_btns[t] = b
	bars = Control.new()
	bars.set_anchors_preset(Control.PRESET_TOP_LEFT)
	bars.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bars.draw.connect(_draw_bars)
	add_child(bars)
	# --- сенсорное управление ---
	touch = load("res://ui/touch_controls.gd").new()
	touch.hud = self
	touch.visible = Game.touch_mode
	add_child(touch)
	# --- центральное сообщение ---
	center_msg = _label("", 44, Control.PRESET_CENTER)
	center_msg.position = Vector2(-500, -60)
	center_msg.size = Vector2(1000, 120)
	center_msg.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	center_msg.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	center_msg.add_theme_color_override("font_outline_color", Color.BLACK)
	center_msg.add_theme_constant_override("outline_size", 10)
	center_msg.modulate.a = 0.0
	# --- затемнение ---
	fade = ColorRect.new()
	fade.color = Color.BLACK
	fade.set_anchors_preset(Control.PRESET_FULL_RECT)
	fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(fade)
	_build_notebook()
	_build_note_view()
	_build_pause()
	Audio.subtitle.connect(_on_subtitle)
	Audio.subtitle_end.connect(func(): sub_panel.visible = false)
	Game.toast.connect(show_toast)

func bind(p: Player, lv) -> void:
	player = p
	level = lv
	touch.player = p
	p.tool_changed.connect(_on_tool)
	_on_tool(p.tool_id)

func _label(t: String, size: int, preset: int) -> Label:
	var l := Label.new()
	l.text = t
	l.add_theme_font_size_override("font_size", size)
	l.set_anchors_preset(preset)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(l)
	return l

func _draw_cross() -> void:
	var active := player != null and player.target != null
	var col := Color(1, 1, 1, 0.85 if active else 0.35)
	crosshair.draw_circle(Vector2.ZERO, 5.0 if active else 2.5, col)

func _draw_bars() -> void:
	if player == null:
		return
	var y := 82.0
	_bar(Vector2(24, y), 120, player.battery / 100.0, Color(1, 0.9, 0.4), "Батарея")
	_bar(Vector2(24, y + 22), 120, player.spray_amount / 100.0, Color(0.4, 0.8, 1.0), "Спрей")
	_bar(Vector2(24, y + 44), 120, player.mop_clean, Color(0.6, 0.5, 0.35), "Швабра")
	_bar(Vector2(24, y + 66), 120, Game.sanity / 100.0, Color(0.7, 0.4, 0.9), "Рассудок")

func _bar(pos: Vector2, w: float, v: float, c: Color, label: String) -> void:
	bars.draw_rect(Rect2(pos, Vector2(w, 8)), Color(0, 0, 0, 0.55))
	bars.draw_rect(Rect2(pos, Vector2(w * clampf(v, 0, 1), 8)), c)
	bars.draw_string(ThemeDB.fallback_font, pos + Vector2(w + 8, 9), label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(1, 1, 1, 0.7))

func _on_tool(t: String) -> void:
	for k in tool_btns:
		tool_btns[k].modulate = Color(1, 1, 0.5) if k == t else Color(1, 1, 1, 0.65)

func _on_subtitle(speaker: String, text: String, dur: float) -> void:
	var col: String = {"hero": "#e8e8d0", "family": "#ffd9a0", "child": "#ffc0e0", "monster": "#ff6060", "sms": "#80c0ff", "artem": "#a0ffc0", "mother": "#ffb090", "house": "#ff4040"}.get(speaker, "#ffffff")
	var name: String = {"hero": "", "family": "", "child": "", "monster": "", "sms": "СМС: ", "artem": "Артём: ", "mother": "", "house": ""}.get(speaker, "")
	sub_lbl.text = "[center][color=%s]%s%s[/color][/center]" % [col, name, text]
	sub_panel.visible = true
	sub_panel.size = Vector2(840, 40)

func show_toast(text: String) -> void:
	if _toasts.size() > 0 and _toasts.back() == text:
		return
	_toasts.append(text)

func show_center(text: String, dur := 3.0) -> void:
	center_msg.text = text
	var tw := create_tween()
	tw.tween_property(center_msg, "modulate:a", 1.0, 0.6)
	tw.tween_interval(dur)
	tw.tween_property(center_msg, "modulate:a", 0.0, 1.0)

func fade_to(a: float, t := 1.0) -> Tween:
	var tw := create_tween()
	tw.tween_property(fade, "color:a", a, t)
	return tw

func flash_screen(v := 1.0, t := 0.5) -> void:
	if not Game.settings.flashes:
		v *= 0.25
	flash_v = v

func red_flash(v := 0.6) -> void:
	tint_v = v

func glitch(v := 1.0) -> void:
	glitch_v = v

func _process(delta: float) -> void:
	_time += delta
	if player == null:
		return
	# подсказка
	prompt_lbl.text = player.target_prompt if not overlay_open else ""
	if player.target_hint != "" and _toasts.is_empty():
		pass
	crosshair.queue_redraw()
	bars.queue_redraw()
	# тосты
	if _toast_t > 0.0:
		_toast_t -= delta
		if _toast_t < 0.5:
			toast_lbl.modulate.a = maxf(0.0, _toast_t / 0.5)
	elif not _toasts.is_empty():
		toast_lbl.text = _toasts.pop_front()
		toast_lbl.modulate.a = 1.0
		_toast_t = 2.8
	# задачи
	if level:
		task_lbl.text = "Чистота: %d%%" % int(level.progress() * 100.0)
		obj_lbl.text = level.current_objective()
	# шейдер
	var insane := clampf(1.0 - Game.sanity / 60.0, 0.0, 1.0)
	post_mat.set_shader_parameter("insanity", insane)
	post_mat.set_shader_parameter("t", _time)
	post_mat.set_shader_parameter("ps1", 1.0 if Game.settings.ps1 else 0.0)
	flash_v = maxf(0.0, flash_v - delta * 1.8)
	tint_v = maxf(0.0, tint_v - delta * 0.8)
	glitch_v = maxf(0.0, glitch_v - delta * 1.2)
	post_mat.set_shader_parameter("flash", flash_v)
	post_mat.set_shader_parameter("tint_amt", tint_v)
	post_mat.set_shader_parameter("glitch", glitch_v)
	Audio.set_muffle(insane * 0.6)
	# рука/кнопки видимость
	touch.visible = Game.touch_mode and not overlay_open
	tool_box.visible = not overlay_open

# ------------------------------------------------ блокнот
func _make_overlay() -> Control:
	var c := Control.new()
	c.set_anchors_preset(Control.PRESET_FULL_RECT)
	c.process_mode = Node.PROCESS_MODE_ALWAYS
	c.visible = false
	var bg := ColorRect.new()
	bg.color = Color(0, 0, 0, 0.82)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	c.add_child(bg)
	add_child(c)
	return c

func _build_notebook() -> void:
	notebook = _make_overlay()
	var panel := PanelContainer.new()
	panel.set_anchors_preset(Control.PRESET_CENTER)
	panel.position = Vector2(-420, -300)
	panel.size = Vector2(840, 600)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.86, 0.82, 0.68)
	sb.set_corner_radius_all(8)
	sb.set_content_margin_all(18)
	panel.add_theme_stylebox_override("panel", sb)
	notebook.add_child(panel)
	var vb := VBoxContainer.new()
	panel.add_child(vb)
	var hb := HBoxContainer.new()
	vb.add_child(hb)
	for i in 3:
		var b := Button.new()
		b.text = ["Задания", "Записки", "Дневник"][i]
		b.custom_minimum_size = Vector2(140, 48)
		b.pressed.connect(func(): nb_tab = i; _refresh_notebook())
		hb.add_child(b)
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	hb.add_child(spacer)
	var close := Button.new()
	close.text = "Закрыть"
	close.custom_minimum_size = Vector2(140, 48)
	close.pressed.connect(toggle_notebook)
	hb.add_child(close)
	var sc := ScrollContainer.new()
	sc.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sc.custom_minimum_size = Vector2(0, 500)
	vb.add_child(sc)
	nb_content = RichTextLabel.new()
	nb_content.bbcode_enabled = true
	nb_content.fit_content = true
	nb_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	nb_content.add_theme_color_override("default_color", Color(0.12, 0.1, 0.07))
	nb_content.add_theme_font_size_override("normal_font_size", 20)
	sc.add_child(nb_content)

func toggle_notebook() -> void:
	if note_view.visible or pause_menu.visible:
		return
	notebook.visible = not notebook.visible
	_set_overlay(notebook.visible)
	if notebook.visible:
		_refresh_notebook()

func _refresh_notebook() -> void:
	var t := ""
	if nb_tab == 0:
		t = "[b]Список дел[/b]  —  Чистота: %d%%\n\n" % int(level.progress() * 100.0)
		for id in level.b.task_order:
			var tk: Dictionary = level.b.tasks[id]
			if tk.hidden and not tk.done:
				continue
			var done: bool = tk.done
			var pr: float = level.task_progress(id)
			t += "%s %s%s %s\n" % ["[color=#2a6a2a]☑[/color]" if done else "☐", "[s]" if done else "", tk.text, ("(%d%%)" % int(pr * 100.0)) if not done and not tk.manual else ""]
			if done: t = t.rstrip("\n") + "[/s]\n"
		t += "\n[i]Инструменты: 1–5 или кнопка «Смена». Швабру полощите в ведре, спрей пополняйте в ящике с расходниками.[/i]"
	elif nb_tab == 1:
		t = "[b]Найденные записки[/b]\n\n"
		var any := false
		for id in NotesDB.NOTES:
			if Game.notes_found.has(id):
				any = true
				var n: Dictionary = NotesDB.NOTES[id]
				t += "[b]%s[/b]%s\n%s\n\n" % [n.title, "  [color=#8a1a1a](настоящая)[/color]" if n.kind == "true" else "", n.text]
		if not any:
			t += "Пока ничего."
	else:
		t = "[b]Дневник[/b]\n\n"
		t += Diary.text_for(Game.chapter, Game.truth)
	nb_content.text = t

func _set_overlay(open: bool) -> void:
	overlay_open = open
	get_tree().paused = open
	if not Game.touch_mode:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if open else Input.MOUSE_MODE_CAPTURED

# ------------------------------------------------ записка
func _build_note_view() -> void:
	note_view = _make_overlay()
	var panel := PanelContainer.new()
	panel.set_anchors_preset(Control.PRESET_CENTER)
	panel.position = Vector2(-300, -280)
	panel.size = Vector2(600, 560)
	note_view.set_meta("panel", panel)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.93, 0.9, 0.8)
	sb.set_corner_radius_all(4)
	sb.set_content_margin_all(26)
	panel.add_theme_stylebox_override("panel", sb)
	note_view.add_child(panel)
	var vb := VBoxContainer.new()
	vb.name = "vb"
	panel.add_child(vb)
	var title := Label.new(); title.name = "title"
	title.add_theme_font_size_override("font_size", 26)
	title.add_theme_color_override("font_color", Color(0.1, 0.08, 0.05))
	vb.add_child(title)
	var sc := ScrollContainer.new()
	sc.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sc.custom_minimum_size = Vector2(0, 360)
	vb.add_child(sc)
	var body := RichTextLabel.new(); body.name = "body"
	body.bbcode_enabled = true
	body.fit_content = true
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_theme_font_size_override("normal_font_size", 22)
	body.add_theme_color_override("default_color", Color(0.1, 0.08, 0.05))
	sc.add_child(body)
	var cl := Button.new(); cl.text = "Закрыть"
	cl.custom_minimum_size = Vector2(0, 54)
	cl.pressed.connect(close_note)
	vb.add_child(cl)

func show_note(id: String) -> void:
	var n: Dictionary = NotesDB.NOTES[id]
	var vb: Node = note_view.get_meta("panel").get_node("vb")
	vb.get_node("title").text = n.title
	vb.get_node("title").add_theme_color_override("font_color", Color(0.1, 0.08, 0.05) if n.kind != "true" else Color(0.45, 0.05, 0.05))
	var body: RichTextLabel = vb.get_child(1).get_node("body")
	body.text = n.text if n.kind != "true" else "[color=#3a0808]%s[/color]" % n.text
	var sb: StyleBoxFlat = note_view.get_meta("panel").get_theme_stylebox("panel")
	sb.bg_color = Color(0.93, 0.9, 0.8) if n.kind != "true" else Color(0.75, 0.7, 0.6)
	note_view.visible = true
	_set_overlay(true)

func close_note() -> void:
	note_view.visible = false
	_set_overlay(false)
	if level:
		level.on_note_closed()

# ------------------------------------------------ пауза
func _build_pause() -> void:
	pause_menu = _make_overlay()
	var vb := VBoxContainer.new()
	vb.set_anchors_preset(Control.PRESET_CENTER)
	vb.position = Vector2(-180, -210)
	vb.custom_minimum_size = Vector2(360, 0)
	vb.add_theme_constant_override("separation", 12)
	pause_menu.add_child(vb)
	var t := Label.new(); t.text = "ПАУЗА"; t.add_theme_font_size_override("font_size", 40)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(t)
	var mk := func(text: String, cb: Callable):
		var b := Button.new(); b.text = text; b.custom_minimum_size = Vector2(0, 58)
		b.add_theme_font_size_override("font_size", 22)
		b.pressed.connect(cb)
		vb.add_child(b)
	mk.call("Продолжить", toggle_pause)
	mk.call("Блокнот", func(): toggle_pause(); toggle_notebook())
	mk.call("Начать главу заново", func(): Game.start_chapter(Game.chapter))
	mk.call("Настройки", func(): _show_settings())
	mk.call("В главное меню", func(): Game.save_game(); Game.to_menu())
	_build_settings_inline(vb)

var _settings_box: VBoxContainer

func _build_settings_inline(vb: VBoxContainer) -> void:
	_settings_box = SettingsUI.build(self)
	_settings_box.visible = false
	pause_menu.add_child(_settings_box)

func _show_settings() -> void:
	_settings_box.visible = not _settings_box.visible
	pause_menu.get_child(1).visible = not _settings_box.visible

func toggle_pause() -> void:
	if notebook.visible or note_view.visible:
		return
	pause_menu.visible = not pause_menu.visible
	if not pause_menu.visible:
		_settings_box.visible = false
		pause_menu.get_child(1).visible = true
		Game.save_game()
	_set_overlay(pause_menu.visible)

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("notebook"):
		toggle_notebook()
	if event.is_action_pressed("pause"):
		if notebook.visible:
			toggle_notebook()
		elif note_view.visible:
			close_note()
		else:
			toggle_pause()
