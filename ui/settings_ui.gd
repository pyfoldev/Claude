class_name SettingsUI extends RefCounted
## Панель настроек (используется в меню и паузе).

static func build(owner_node: Node) -> VBoxContainer:
	var vb := VBoxContainer.new()
	vb.set_anchors_preset(Control.PRESET_CENTER)
	vb.position = Vector2(-300, -300)
	vb.custom_minimum_size = Vector2(600, 0)
	vb.add_theme_constant_override("separation", 8)
	var t := Label.new(); t.text = "НАСТРОЙКИ"; t.add_theme_font_size_override("font_size", 34)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(t)
	_slider(vb, "Чувствительность камеры", "sens", 0.3, 2.5, 0.05)
	_slider(vb, "Размер кнопок", "btn_scale", 0.7, 1.4, 0.05)
	_slider(vb, "Масштаб рендера (FPS)", "render_scale", 0.5, 1.0, 0.05)
	_slider(vb, "Поле зрения", "fov", 60.0, 95.0, 1.0)
	_slider(vb, "Громкость", "vol_master", 0.0, 1.0, 0.05)
	_slider(vb, "Музыка", "vol_music", 0.0, 1.0, 0.05)
	_slider(vb, "Голоса", "vol_voice", 0.0, 1.0, 0.05)
	_check(vb, "Стиль PS1 (зернистость)", "ps1")
	_check(vb, "Субтитры", "subtitles")
	_check(vb, "Сильные вспышки (выкл. — мягче)", "flashes")
	_check(vb, "Тени от фонарика (тяжело)", "shadows")
	_check(vb, "Инвертировать взгляд по вертикали", "invert")
	var back := Button.new(); back.text = "Назад"; back.custom_minimum_size = Vector2(0, 54)
	back.pressed.connect(func():
		Game.save_game()
		if owner_node.has_method("_show_settings"):
			owner_node._show_settings()
		elif owner_node.has_method("close_settings"):
			owner_node.close_settings())
	vb.add_child(back)
	return vb

static func apply_all(vp: Viewport = null) -> void:
	Audio.apply_volumes()
	if vp:
		vp.scaling_3d_scale = float(Game.settings.render_scale)
		vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR

static func _slider(parent: Control, label: String, key: String, mn: float, mx: float, step: float) -> void:
	var hb := HBoxContainer.new()
	var l := Label.new(); l.text = label; l.custom_minimum_size = Vector2(300, 0)
	hb.add_child(l)
	var s := HSlider.new()
	s.min_value = mn; s.max_value = mx; s.step = step
	s.value = float(Game.settings[key])
	s.custom_minimum_size = Vector2(260, 36)
	s.value_changed.connect(func(v):
		Game.settings[key] = v
		var vp := parent.get_viewport()
		apply_all(vp)
		if key == "fov" and Game.player:
			Game.player.cam.fov = v)
	hb.add_child(s)
	parent.add_child(hb)

static func _check(parent: Control, label: String, key: String) -> void:
	var c := CheckButton.new()
	c.text = label
	c.button_pressed = bool(Game.settings[key])
	c.toggled.connect(func(v): Game.settings[key] = v)
	c.custom_minimum_size = Vector2(0, 40)
	parent.add_child(c)
