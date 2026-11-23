extends Node
func _ready() -> void:
	var c = load("res://assets/monsters/kenney/characterMedium.fbx").instantiate()
	add_child(c)
	print("CHAR tree:"); _p(c, 0)
	var i = load("res://assets/monsters/kenney/idle.fbx").instantiate()
	add_child(i)
	print("IDLE tree:"); _p(i, 0)
	for ap in i.find_children("*", "AnimationPlayer", true, false):
		for n in ap.get_animation_list():
			var a: Animation = ap.get_animation(n)
			print("anim ", n, " tracks=", a.get_track_count(), " first=", a.track_get_path(0) if a.get_track_count() > 0 else "")
	get_tree().quit()
func _p(n: Node, d: int) -> void:
	if d > 3: return
	print("  ".repeat(d), n.name, " (", n.get_class(), ")")
	for ch in n.get_children(): _p(ch, d + 1)
