extends Control
## Главное меню.

var box: VBoxContainer
var settings_box: VBoxContainer
var chapters_box: VBoxContainer
var about_box: VBoxContainer
var title: Label
var _t := 0.0
var bg: ColorRect

func _ready() -> void:
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	get_tree().paused = false
	set_anchors_preset(Control.PRESET_FULL_RECT)
	bg = ColorRect.new()
	bg.color = Color(0.03, 0.03, 0.04)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(bg)
	title = Label.new()
	title.text = "ГРЯЗНАЯ РАБОТА"
	title.add_theme_font_size_override("font_size", 72)
	title.add_theme_color_override("font_color", Color(0.85, 0.82, 0.7))
	title.set_anchors_preset(Control.PRESET_CENTER_TOP)
	title.position = Vector2(-380, 40)
	title.size = Vector2(760, 90)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	add_child(title)
	var sub := Label.new()
	sub.text = "хоррор про уборщика"
	sub.add_theme_font_size_override("font_size", 22)
	sub.modulate = Color(1, 1, 1, 0.5)
	sub.set_anchors_preset(Control.PRESET_CENTER_TOP)
	sub.position = Vector2(-380, 125)
	sub.size = Vector2(760, 30)
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	add_child(sub)
	box = VBoxContainer.new()
	box.set_anchors_preset(Control.PRESET_CENTER)
	box.position = Vector2(-190, -150)
	box.custom_minimum_size = Vector2(380, 0)
	box.add_theme_constant_override("separation", 10)
	add_child(box)
	_btn("Продолжить", _continue).visible = Game.has_save()
	_btn("Новая игра", _new_game)
	_btn("Главы", func(): _show(chapters_box))
	_btn("Настройки", func(): _show(settings_box))
	_btn("Об игре", func(): _show(about_box))
	if not OS.has_feature("android"):
		_btn("Выход", func(): get_tree().quit())
	var warn := Label.new()
	warn.text = "Игра содержит пугающие сцены, резкие звуки и вспышки. В настройках можно ослабить вспышки."
	warn.add_theme_font_size_override("font_size", 14)
	warn.modulate = Color(1, 1, 1, 0.45)
	warn.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	warn.position = Vector2(-400, -40)
	warn.size = Vector2(800, 24)
	warn.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	add_child(warn)
	settings_box = SettingsUI.build(self)
	settings_box.visible = false
	add_child(settings_box)
	_build_chapters()
	_build_about()
	Audio.music("drone_a", -8.0)
	SettingsUI.apply_all(get_viewport())

func _btn(text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(0, 62)
	b.add_theme_font_size_override("font_size", 26)
	b.pressed.connect(cb)
	box.add_child(b)
	return b

func _show(which: Control) -> void:
	box.visible = false
	title.visible = false
	which.visible = true

func close_settings() -> void:
	_back()

func _back() -> void:
	for c in [settings_box, chapters_box, about_box]:
		c.visible = false
	box.visible = true
	title.visible = true

func _build_chapters() -> void:
	chapters_box = VBoxContainer.new()
	chapters_box.set_anchors_preset(Control.PRESET_CENTER)
	chapters_box.position = Vector2(-260, -300)
	chapters_box.custom_minimum_size = Vector2(520, 0)
	chapters_box.add_theme_constant_override("separation", 6)
	chapters_box.visible = false
	add_child(chapters_box)
	var t := Label.new(); t.text = "ГЛАВЫ"; t.add_theme_font_size_override("font_size", 34)
	t.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	chapters_box.add_child(t)
	for i in range(1, 9):
		var b := Button.new()
		var info: Dictionary = Story.CHAPTERS[i]
		var ok: bool = i <= Game.unlocked
		b.text = "%d. %s — %s" % [i, info.title, info.sub] if ok else "%d. ???" % i
		b.disabled = not ok
		b.custom_minimum_size = Vector2(0, 50)
		b.pressed.connect(func(): Game.start_chapter(i))
		chapters_box.add_child(b)
	var back := Button.new(); back.text = "Назад"; back.custom_minimum_size = Vector2(0, 54)
	back.pressed.connect(_back)
	chapters_box.add_child(back)

func _build_about() -> void:
	about_box = VBoxContainer.new()
	about_box.set_anchors_preset(Control.PRESET_CENTER)
	about_box.position = Vector2(-330, -260)
	about_box.custom_minimum_size = Vector2(660, 0)
	about_box.visible = false
	add_child(about_box)
	var r := RichTextLabel.new()
	r.bbcode_enabled = true
	r.fit_content = true
	r.custom_minimum_size = Vector2(660, 360)
	r.text = Story.CREDITS + "\n\n[b]Управление[/b]: левый стик — ходьба; правая часть экрана — камера; «Действие» (зажать) — уборка и взаимодействие; кнопки: фонарь, присесть/спрятаться, смена инструмента, блокнот.\nНа ПК: WASD, мышь, E/ЛКМ, F, C, Q, 1–5, Tab."
	about_box.add_child(r)
	var back := Button.new(); back.text = "Назад"; back.custom_minimum_size = Vector2(0, 54)
	back.pressed.connect(_back)
	about_box.add_child(back)

func _continue() -> void:
	Game.start_chapter(clampi(Game.unlocked, 1, Game.MAX_CHAPTER))

func _new_game() -> void:
	Game.new_game()
	Game.start_chapter(1)
