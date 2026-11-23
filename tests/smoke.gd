extends Node
## Дымовой тест: godot --headless --path . tests/smoke.tscn -- <глава>
var frames := 0
var chapter := 1
var level: Node
func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() > 0:
		chapter = int(args[0])
	Game.chapter = chapter
	Game.checkpoint = {}
	level = load("res://world/level.tscn").instantiate()
	add_child(level)
func _process(_d: float) -> void:
	frames += 1
	if frames == 8:
		print("scene: ", level.name, " rooms=", level.b.rooms.size(), " patches=", level.b.patches.size(), " doors=", level.b.doors.size())
	if frames == 40:
		var p = Game.player
		print("player pos: ", p.global_position, " room=", level.cur_room, " on_floor=", p.is_on_floor())
	if frames > 100:
		print("OK frames=", frames)
		get_tree().quit(0)
