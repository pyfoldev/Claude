extends Node3D
func _ready() -> void:
	var ids := []
	var d := DirAccess.open("res://assets/models")
	for n in d.get_directories(): ids.append(n)
	ids.sort()
	var a := OS.get_cmdline_user_args()
	var part := int(a[0]) if a.size() > 0 else 0
	ids = ids.slice(part * 30, part * 30 + 30)
	var env := WorldEnvironment.new(); var e := Environment.new()
	e.background_mode = Environment.BG_COLOR; e.background_color = Color(0.25,0.25,0.3)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR; e.ambient_light_color = Color(0.7,0.7,0.75); e.ambient_light_energy = 0.9
	env.environment = e; add_child(env)
	var l := DirectionalLight3D.new(); l.rotation_degrees = Vector3(-50, 20, 0); add_child(l)
	for i in ids.size():
		var path := "res://assets/models/%s/%s.gltf" % [ids[i], ids[i]]
		var ps = load(path)
		if ps == null: continue
		var inst: Node3D = ps.instantiate()
		var acc := [null]
		Props._aabb_rec(inst, Transform3D.IDENTITY, acc)
		var bb: AABB = acc[0]
		var s := 1.4 / maxf(bb.size.x, maxf(bb.size.y, bb.size.z))
		var holder := Node3D.new(); holder.position = Vector3((i % 6) * 2.0 - 5.0, 0, floor(i / 6) * 2.4 - 4.0)
		inst.scale = Vector3.ONE * s; inst.position = Vector3(-bb.get_center().x * s, -bb.position.y * s, -bb.get_center().z * s)
		holder.add_child(inst); add_child(holder)
		var lb := Label3D.new(); lb.text = ids[i]; lb.font_size = 40; lb.pixel_size = 0.004; lb.position = holder.position + Vector3(0, 1.6, 0); lb.billboard = BaseMaterial3D.BILLBOARD_ENABLED; add_child(lb)
	var cam := Camera3D.new(); add_child(cam); cam.position = Vector3(0, 6.5, 8.0); cam.rotation_degrees = Vector3(-40, 0, 0); cam.current = true
	await get_tree().create_timer(1.0).timeout
	get_viewport().get_texture().get_image().save_png("/tmp/gal%d.png" % part); get_tree().quit()
