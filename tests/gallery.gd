extends Node3D
## Галерея пропов для проверки масштаба/ориентации: tests/gallery.tscn
func _ready() -> void:
	var kinds := ["sofa","armchair","table","chair","stool","bed","wardrobe","bookshelf","dresser","stove","mirror","radio","plant","bucket","crate","box","bag","kettle","statue","tv","fridge","counter","lamp","piano"]
	var env := WorldEnvironment.new(); var e := Environment.new()
	e.background_mode = Environment.BG_COLOR; e.background_color = Color(0.2,0.2,0.25)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR; e.ambient_light_color = Color(0.6,0.6,0.65); e.ambient_light_energy = 0.8
	env.environment = e; add_child(env)
	var fl := MeshInstance3D.new(); var pm := PlaneMesh.new(); pm.size = Vector2(40, 20); fl.mesh = pm; add_child(fl)
	var l := DirectionalLight3D.new(); l.rotation_degrees = Vector3(-50, 20, 0); add_child(l)
	for i in kinds.size():
		var n := Props.make(kinds[i])
		n.position = Vector3((i % 8) * 2.4 - 8.4, 0, floor(i / 8) * 3.0 - 2.5)
		add_child(n)
	var cam := Camera3D.new(); add_child(cam)
	cam.position = Vector3(0, 5.0, 8.5); cam.rotation_degrees = Vector3(-30, 0, 0); cam.current = true
	await get_tree().create_timer(0.8).timeout
	get_viewport().get_texture().get_image().save_png("/tmp/gallery.png")
	get_tree().quit()
