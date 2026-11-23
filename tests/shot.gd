extends Node
## Скриншоты: xvfb-run godot --path . tests/shot.tscn -- <глава> <x> <y> <z> <yaw> <pitch> <out.png>
var frames := 0
var level: Node
var out := "/tmp/shot.png"
var pos := Vector3.ZERO
var yaw := 0.0
var pitch := 0.0
var custom := false
func _ready() -> void:
	var a := OS.get_cmdline_user_args()
	Game.chapter = int(a[0]) if a.size() > 0 else 1
	Game.checkpoint = {}
	if a.size() >= 7:
		custom = true
		pos = Vector3(float(a[1]), float(a[2]), float(a[3]))
		yaw = float(a[4]); pitch = float(a[5]); out = a[6]
	level = load("res://world/level.tscn").instantiate()
	add_child(level)
func _process(_d: float) -> void:
	frames += 1
	var p = Game.player
	if frames == 3:
		level.hud.fade.color.a = 0.0
		for c in level.hud.get_children():
			if c is Label and c.text.begins_with("ГЛАВА"):
				c.queue_free()
		p.frozen = true
		if custom:
			p.global_position = pos
			p.rotation_degrees.y = yaw
			p.pitch = pitch
			p.head.rotation_degrees.x = pitch
	if frames == 30:
		get_viewport().get_texture().get_image().save_png(out)
		print("saved ", out)
		get_tree().quit()
