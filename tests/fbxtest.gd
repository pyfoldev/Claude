extends Node3D
func _ready() -> void:
	var env := WorldEnvironment.new(); var e := Environment.new()
	e.background_mode = Environment.BG_COLOR; e.background_color = Color(0.2,0.2,0.25)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR; e.ambient_light_color = Color(0.7,0.7,0.75); e.ambient_light_energy = 0.9
	env.environment = e; add_child(env)
	var l := DirectionalLight3D.new(); l.rotation_degrees = Vector3(-40, 30, 0); add_child(l)
	var ps = load("res://assets/monsters/horror/Walk.fbx")
	var m: Node3D = ps.instantiate(); add_child(m)
	var acc := [null]; Props._aabb_rec(m, Transform3D.IDENTITY, acc)
	print("AABB ", acc[0])
	var ap = m.find_children("*", "AnimationPlayer", true, false)
	print("anims: ", ap.size(), " ", ap[0].get_animation_list() if ap.size() > 0 else [])
	for mi in m.find_children("*", "MeshInstance3D", true, false): print("mesh ", mi.name, " mats ", mi.get_surface_override_material_count(), " ", mi.mesh.get_surface_count())
	var cam := Camera3D.new(); add_child(cam); cam.position = Vector3(0, 1.5, 5); cam.current = true
	if ap.size() > 0 and ap[0].get_animation_list().size() > 0:
		ap[0].play(ap[0].get_animation_list()[ap[0].get_animation_list().size()-1])
	await get_tree().create_timer(0.8).timeout
	get_viewport().get_texture().get_image().save_png("/tmp/fbx.png"); get_tree().quit()
