extends Node
## Автотест уборки: ведёт игрока к пятнам и чистит их, печатает прогресс.
var level: Node
var frames := 0
var patches: Array = []
var idx := 0
var hold := 0
func _ready() -> void:
	Game.chapter = 1
	Game.checkpoint = {}
	level = load("res://world/level.tscn").instantiate()
	add_child(level)
func _physics_process(_d: float) -> void:
	frames += 1
	var p = Game.player
	if frames == 3:
		level.hud.fade.color.a = 0.0
		p.frozen = false
		level.gameplay_locked = false
		for k in level.b.patches:
			var pt = level.b.patches[k]
			if pt.visible and pt.task_id in ["dust", "floor"]:
				patches.append(pt)
		print("patches to clean: ", patches.size())
	if frames < 5 or idx >= patches.size():
		if idx >= patches.size() and frames > 5:
			print("progress=", level.progress(), " tasks dust=", level.b.tasks.dust.done, " floor=", level.b.tasks.floor.done)
			get_tree().quit()
		return
	var pt: DirtPatch = patches[idx]
	if pt.done:
		idx += 1; hold = 0
		return
	var tool_need: String = pt.required_tools()[0]
	if p.tool_id != tool_need:
		p.set_tool(tool_need)
	# встать над пятном и смотреть вниз/вперёд на него
	var off := Vector3(0.0, 0, 0.9) if absf(pt.basis.y.y) > 0.5 else pt.basis.y * 0.9
	p.global_position = pt.global_position + off + Vector3(0, 0.05, 0)
	p.velocity = Vector3.ZERO
	p.look_at_point(pt.global_position, 0.0)
	p.rotation_degrees.y = rad_to_deg(atan2(-(pt.global_position.x - p.global_position.x), -(pt.global_position.z - p.global_position.z)))
	var dh: float = pt.global_position.y - (p.global_position.y + 1.62)
	var hz := Vector2(pt.global_position.x - p.global_position.x, pt.global_position.z - p.global_position.z).length()
	p.pitch = rad_to_deg(atan2(dh, hz))
	p.action_held = true
	hold += 1
	if hold % 60 == 0:
		print("patch ", pt.patch_id, " kind=", pt.kind, " amount=", snappedf(pt.amount, 0.01), " target=", p.target)
	if hold > 600:
		print("STUCK on ", pt.patch_id)
		idx += 1; hold = 0
