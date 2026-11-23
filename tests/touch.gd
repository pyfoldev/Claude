extends Node
var level
var frames := 0
func _ready() -> void:
	Game.touch_mode = true
	Game.chapter = 1; Game.checkpoint = {}
	level = load("res://world/level.tscn").instantiate()
	add_child(level)
func _physics_process(_d: float) -> void:
	frames += 1
	var p = Game.player
	if frames == 3:
		level.hud.fade.color.a = 0.0
		for c in level.hud.get_children():
			if c is Label and c.text.begins_with("ГЛАВА"): c.queue_free()
		p.frozen = false; level.gameplay_locked = false
		print("touch ctrl size=", level.hud.touch.size, " visible=", level.hud.touch.visible, " player=", level.hud.touch.player)
	if frames == 6:
		var e := InputEventScreenTouch.new(); e.index = 0; e.pressed = true; e.position = Vector2(200, 500)
		Input.parse_input_event(e)
	if frames == 8:
		var d := InputEventScreenDrag.new(); d.index = 0; d.position = Vector2(200, 400); d.relative = Vector2(0, -100)
		Input.parse_input_event(d)
	if frames == 10:
		print("move_input=", p.move_input)
	if frames == 12:
		var e2 := InputEventScreenTouch.new(); e2.index = 1; e2.pressed = true; e2.position = Vector2(800, 300)
		Input.parse_input_event(e2)
		var d2 := InputEventScreenDrag.new(); d2.index = 1; d2.position = Vector2(900, 300); d2.relative = Vector2(100, 0)
		Input.parse_input_event(d2)
	if frames == 14:
		print("yaw=", p.rotation_degrees.y, " pos=", p.global_position)
	if frames == 40:
		print("pos after=", p.global_position)
		get_viewport().get_texture().get_image().save_png("/tmp/touch.png")
		get_tree().quit()
