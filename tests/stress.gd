extends Node
## Нагрузочный тест: для главы N форсит все события и монстров и гоняет кадры.
var level: Node
var frames := 0
var chapter := 1
func _ready() -> void:
	var a := OS.get_cmdline_user_args()
	chapter = int(a[0]) if a.size() > 0 else 1
	Game.chapter = chapter
	Game.checkpoint = {}
	level = load("res://world/level.tscn").instantiate()
	add_child(level)
func _physics_process(_d: float) -> void:
	frames += 1
	var p = Game.player
	if frames == 3:
		level.hud.fade.color.a = 0.0
		p.frozen = false; level.gameplay_locked = false
		Game.checkpoint = {}
	if frames == 10:
		for ev in ["flicker","whisper","steps_far","knock","creak","breath","laugh","radio_static","cold","drip","thump","door_slam","lights_out","phantom","phantom_child","fake_sms","tv_on","shadow_behind","scream","face_flash"]:
			Director.force(ev)
		level.autosave()
		for ty in ["shadow","crawler","host","mimic"]:
			var m = level.make_monster(ty, p.global_position + Vector3(0, 0, -2.5), {"disguise": "crate", "popts": {"s": 0.7}})
			m.player = p
	if frames == 20:
		p.set_tool("spray"); p.action_held = true
	if frames == 200:
		# жёсткое прохождение: поймать игрока
		for m in get_tree().get_nodes_in_group("monsters"):
			m.global_position = p.global_position + Vector3(0, 0, -0.6)
	if frames > 400:
		print("OK ch", chapter, " frames=", frames, " frozen=", p.frozen, " sanity=", snappedf(Game.sanity, 0.1))
		get_tree().quit()
