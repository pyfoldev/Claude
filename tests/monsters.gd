extends Node3D
func _ready() -> void:
	var env := WorldEnvironment.new(); var e := Environment.new()
	e.background_mode = Environment.BG_COLOR; e.background_color = Color(0.1,0.1,0.14)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR; e.ambient_light_color = Color(0.7,0.7,0.75); e.ambient_light_energy = 0.9
	env.environment = e; add_child(env)
	var l := DirectionalLight3D.new(); l.rotation_degrees = Vector3(-40, 30, 0); add_child(l)
	var kinds := ["shadow","child","host","crawler","mother","artem"]
	for i in kinds.size():
		var m := MonsterModels.build(kinds[i]); m.position = Vector3(i * 1.8 - 4.5, 0, 0); m.rotation_degrees.y = 180; add_child(m)
	var cam := Camera3D.new(); add_child(cam); cam.position = Vector3(0, 1.4, -6); cam.rotation_degrees = Vector3(-5, 180, 0); cam.current = true
	await get_tree().create_timer(0.6).timeout
	get_viewport().get_texture().get_image().save_png("/tmp/monsters.png"); get_tree().quit()
