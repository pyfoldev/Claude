class_name Door extends Node3D
## Дверь на петле. Интерактивна, может быть заперта (нужен ключ) или заколочена.

signal opened(door)
signal closed(door)

var leaf: Interactable
var is_open := false
var locked := false
var key_id := ""
var jammed := false          # заклинена навсегда (по сюжету)
var open_angle := 100.0
var side := 1.0
var width := 1.0
var a_id := ""
var b_id := ""
var tween: Tween
var base_yaw := 0.0

func setup(w: float, h: float, mat: Material, flip := 1.0) -> void:
	width = w
	side = flip
	leaf = Interactable.new()
	leaf.collision_layer = 3
	leaf.position = Vector3(w / 2.0 * flip, h / 2.0, 0)
	var mi := MeshInstance3D.new()
	var b := BoxMesh.new(); b.size = Vector3(w - 0.04, h, 0.05)
	mi.mesh = b; mi.material_override = mat
	leaf.add_child(mi)
	var knob := MeshInstance3D.new()
	var s := SphereMesh.new(); s.radius = 0.04; s.height = 0.08
	knob.mesh = s
	knob.material_override = Mats.color(Color(0.7, 0.62, 0.3), 0.3, 0.0, 0.9)
	knob.position = Vector3((w / 2.0 - 0.1) * -flip, -0.05, 0.05)
	leaf.add_child(knob)
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new(); bs.size = Vector3(w - 0.04, h, 0.07)
	cs.shape = bs
	leaf.add_child(cs)
	leaf.callback = _on_interact
	add_child(leaf)
	_update_prompt()

func _update_prompt() -> void:
	if jammed:
		leaf.prompt = "Не открывается"
	elif locked:
		leaf.prompt = "Заперто"
	else:
		leaf.prompt = "Закрыть" if is_open else "Открыть"

func _on_interact(p) -> void:
	if jammed:
		Audio.sfx("door_locked", global_position)
		Game.note("Дверь не поддаётся.")
		return
	if locked:
		if key_id != "" and Game.flag("key_" + key_id):
			locked = false
			Game.note("Дверь отперта.")
			Audio.sfx("key_unlock", global_position)
		else:
			Audio.sfx("door_locked", global_position)
			Game.note("Заперто." + (" Нужен ключ." if key_id != "" else ""))
			if Game.level and Game.level.has_method("on_locked_door"):
				Game.level.on_locked_door(self)
			return
	toggle()

func toggle(force_slam := false) -> void:
	set_open(not is_open, force_slam)

func set_open(v: bool, slam := false) -> void:
	if jammed and v:
		return
	if v == is_open:
		return
	is_open = v
	if tween:
		tween.kill()
	tween = create_tween()
	var target := (-open_angle * side) if v else 0.0
	var dur := 0.25 if slam else 0.55
	tween.tween_property(self, "rotation_degrees:y", base_yaw + target, dur).set_trans(Tween.TRANS_QUAD)
	if v:
		Audio.sfx("door_open", global_position)
		opened.emit(self)
	else:
		Audio.sfx("door_slam" if slam else "door_close", global_position)
		if slam:
			Game.noise.emit(global_position, 12.0)
		closed.emit(self)
	_update_prompt()

func set_locked(v: bool, key := "") -> void:
	locked = v; key_id = key
	_update_prompt()
