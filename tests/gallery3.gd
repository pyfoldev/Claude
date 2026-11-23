extends Node3D
func _ready() -> void:
	var paths := ["res://assets/vehicles/Van.fbx", "res://assets/monsters/darsh/Darsh.glb", "res://assets/monsters/kenney/characterMedium.fbx"]
	var d := DirAccess.open("res://assets/kenney")
	for f in d.get_files():
		if f.ends_with(".fbx"): paths.append("res://assets/kenney/" + f)
	var env := WorldEnvironment.new(); var e := Environment.new()
	e.background_mode = Environment.BG_COLOR; e.background_color = Color(0.25,0.25,0.3)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR; e.ambient_light_color = Color(0.7,0.7,0.75); e.ambient_light_energy = 0.9
	env.environment = e; add_child(env)
	var l := DirectionalLight3D.new(); l.rotation_degrees = Vector3(-50, 20, 0); add_child(l)
	for i in paths.size():
		var ps = load(paths[i])
		if ps == null: print("FAIL ", paths[i]); continue
		var inst: Node3D = ps.instantiate()
		var acc := [null]; Props._aabb_rec(inst, Transform3D.IDENTITY, acc)
		var bb: AABB = acc[0]
		if bb == null: print("noaabb ", paths[i]); continue
		print(paths[i].get_file(), " size=", bb.size)
		var s := 1.5 / maxf(bb.size.x, maxf(bb.size.y, bb.size.z))
		var h := Node3D.new(); h.position = Vector3((i % 8) * 2.0 - 7.0, 0, floor(i / 8) * 2.6 - 4.0)
		inst.scale = Vector3.ONE * s; inst.position = Vector3(-bb.get_center().x * s, -bb.position.y * s, -bb.get_center().z * s)
		h.add_child(inst); add_child(h)
		var lb := Label3D.new(); lb.text = paths[i].get_file().get_basename(); lb.font_size = 36; lb.pixel_size = 0.004; lb.position = h.position + Vector3(0, 1.8, 0); lb.billboard = BaseMaterial3D.BILLBOARD_ENABLED; add_child(lb)
	var cam := Camera3D.new(); add_child(cam); cam.position = Vector3(0, 7.0, 8.5); cam.rotation_degrees = Vector3(-42, 0, 0); cam.current = true
	await get_tree().create_timer(1.0).timeout
	get_viewport().get_texture().get_image().save_png("/tmp/gal3.png"); get_tree().quit()
