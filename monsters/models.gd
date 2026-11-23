class_name MonsterModels extends RefCounted
## Процедурные low-poly модели монстров.

static func _limb(parent: Node3D, name: String, pos: Vector3, size: Vector3, mat: Material, pivot_off := Vector3.ZERO) -> Node3D:
	var piv := Node3D.new()
	piv.name = name
	piv.position = pos
	parent.add_child(piv)
	Props.cap(piv, maxf(size.x, size.z) * 0.55, size.y, Vector3(0, -size.y / 2.0, 0) + pivot_off, mat)
	return piv

static func _eyes(parent: Node3D, y: float, z: float, spread: float, size: float, color: Color) -> void:
	var em := Mats.color(color, 0.3, 4.0)
	for s in [-1, 1]:
		var e := Props.box(parent, Vector3(size, size * 0.5, 0.02), Vector3(s * spread, y, z), em)
		e.name = "eye"

static func build(type: String, o := {}) -> Node3D:
	var root := Node3D.new()
	var black := Mats.color(Color(0.02, 0.02, 0.03), 0.9)
	match type:
		"shadow":
			var sc: float = o.get("scale", 1.0)
			root.set_meta("head", 1.75 * sc)
			var body := Node3D.new(); body.name = "body"; root.add_child(body)
			Props.cap(body, 0.24, 0.95, Vector3(0, 1.15, 0), black, 1.0, 0.65)
			Props.sph(body, 0.17, Vector3(0, 1.68, 0), black, 1.15)
			_eyes(body, 1.7, 0.15, 0.07, 0.07, Color(1, 1, 0.95))
			_limb(body, "arm_l", Vector3(-0.32, 1.45, 0), Vector3(0.1, 0.95, 0.1), black)
			_limb(body, "arm_r", Vector3(0.32, 1.45, 0), Vector3(0.1, 0.95, 0.1), black)
			_limb(body, "leg_l", Vector3(-0.12, 0.7, 0), Vector3(0.14, 0.7, 0.14), black)
			_limb(body, "leg_r", Vector3(0.12, 0.7, 0), Vector3(0.14, 0.7, 0.14), black)
			root.scale = Vector3.ONE * sc
		"child":
			root.set_meta("head", 1.0)
			var body2 := Node3D.new(); body2.name = "body"; root.add_child(body2)
			var pale := Mats.color(Color(0.75, 0.72, 0.68), 0.9)
			Props.cap(body2, 0.14, 0.45, Vector3(0, 0.62, 0), Mats.color(Color(0.45, 0.1, 0.1)), 1.0, 0.7)
			Props.sph(body2, 0.11, Vector3(0, 0.95, 0), pale, 1.1)
			_eyes(body2, 0.96, 0.09, 0.04, 0.045, Color(0, 0, 0))
			_limb(body2, "arm_l", Vector3(-0.18, 0.8, 0), Vector3(0.06, 0.45, 0.06), pale)
			_limb(body2, "arm_r", Vector3(0.18, 0.8, 0), Vector3(0.06, 0.45, 0.06), pale)
			_limb(body2, "leg_l", Vector3(-0.07, 0.42, 0), Vector3(0.07, 0.42, 0.07), pale)
			_limb(body2, "leg_r", Vector3(0.07, 0.42, 0), Vector3(0.07, 0.42, 0.07), pale)
		"host":
			root.set_meta("head", 2.35)
			var suit := Mats.color(Color(0.04, 0.04, 0.05), 0.8)
			var skin := Mats.color(Color(0.78, 0.75, 0.7), 0.7)
			var body3 := Node3D.new(); body3.name = "body"; root.add_child(body3)
			Props.cap(body3, 0.31, 1.2, Vector3(0, 1.6, 0), suit, 1.0, 0.6)
			Props.sph(body3, 0.2, Vector3(0, 2.25, 0), skin, 1.3)
			Props.box(body3, Vector3(0.05, 0.22, 0.02), Vector3(0, 2.18, 0.2), Mats.color(Color(0.02, 0.0, 0.0)))   # тонкий рот
			_limb(body3, "arm_l", Vector3(-0.4, 2.0, 0), Vector3(0.1, 1.45, 0.1), suit)
			_limb(body3, "arm_r", Vector3(0.4, 2.0, 0), Vector3(0.1, 1.45, 0.1), suit)
			_limb(body3, "leg_l", Vector3(-0.15, 1.05, 0), Vector3(0.18, 1.05, 0.18), suit)
			_limb(body3, "leg_r", Vector3(0.15, 1.05, 0), Vector3(0.18, 1.05, 0.18), suit)
			for s in [-1, 1]:
				Props.box(body3, Vector3(0.04, 0.3, 0.02), Vector3(s * 0.4, 0.4, 0.0), skin)
		"crawler":
			root.set_meta("head", 0.5)
			var tar := Mats.color(Color(0.01, 0.01, 0.02), 0.2, 0.0, 0.3)
			var body4 := Node3D.new(); body4.name = "body"; root.add_child(body4)
			Props.sph(body4, 0.38, Vector3(0, 0.35, 0), tar, 0.7)
			Props.sph(body4, 0.2, Vector3(0, 0.3, 0.38), tar, 0.8)
			_eyes(body4, 0.38, 0.52, 0.07, 0.06, Color(1, 0.1, 0.05))
			for i in 6:
				var a := i * TAU / 6.0
				var l := _limb(body4, "leg_%d" % i, Vector3(cos(a) * 0.3, 0.35, sin(a) * 0.3), Vector3(0.05, 0.4, 0.05), tar)
				l.rotation = Vector3(0, -a, deg_to_rad(65))
		"mother":
			root.set_meta("head", 2.0)
			var dress := Mats.color(Color(0.12, 0.1, 0.12), 0.9)
			var pale2 := Mats.color(Color(0.8, 0.78, 0.74), 0.8)
			var hair := Mats.color(Color(0.03, 0.02, 0.02), 1.0)
			var b5 := Node3D.new(); b5.name = "body"; root.add_child(b5)
			Props.cyl(b5, 0.45, 1.25, Vector3(0, 0.62, 0), dress, 0.2)
			Props.cap(b5, 0.2, 0.7, Vector3(0, 1.5, 0), dress, 1.0, 0.7)
			Props.sph(b5, 0.14, Vector3(0, 1.95, 0), pale2, 1.25)
			Props.box(b5, Vector3(0.34, 1.0, 0.1), Vector3(0, 1.55, -0.1), hair)
			Props.box(b5, Vector3(0.28, 0.22, 0.08), Vector3(0, 2.0, -0.05), hair)
			for s in [-1, 1]:
				Props.box(b5, Vector3(0.012, 0.18, 0.01), Vector3(s * 0.05, 1.9, 0.13), Mats.color(Color(0, 0, 0)))
			_limb(b5, "arm_l", Vector3(-0.24, 1.7, 0), Vector3(0.07, 0.95, 0.07), pale2)
			_limb(b5, "arm_r", Vector3(0.24, 1.7, 0), Vector3(0.07, 0.95, 0.07), pale2)
		"artem":
			root.set_meta("head", 1.75)
			var ov := Mats.color(Color(0.2, 0.3, 0.55), 0.9)
			var sk := Mats.color(Color(0.7, 0.62, 0.55), 0.9)
			var b6 := Node3D.new(); b6.name = "body"; root.add_child(b6)
			Props.cap(b6, 0.24, 0.85, Vector3(0, 1.2, 0), ov, 1.0, 0.65)
			Props.sph(b6, 0.15, Vector3(0, 1.65, 0), sk, 1.15)
			_limb(b6, "arm_l", Vector3(-0.3, 1.45, 0), Vector3(0.1, 0.7, 0.1), ov)
			_limb(b6, "arm_r", Vector3(0.3, 1.45, 0), Vector3(0.1, 0.7, 0.1), ov)
			_limb(b6, "leg_l", Vector3(-0.12, 0.75, 0), Vector3(0.14, 0.75, 0.14), ov)
			_limb(b6, "leg_r", Vector3(0.12, 0.75, 0), Vector3(0.14, 0.75, 0.14), ov)
		_:
			root.set_meta("head", 1.0)
	return root

## Раскрытая пасть для мимика / скримера.
static func add_maw(parent: Node3D, size := 0.7) -> Node3D:
	var maw := Node3D.new()
	maw.name = "maw"
	var red := Mats.color(Color(0.45, 0.02, 0.03), 0.4, 0.5)
	var tooth := Mats.color(Color(0.92, 0.9, 0.8), 0.5)
	Props.box(maw, Vector3(size, 0.05, size * 0.8), Vector3(0, size * 0.62, 0), red)
	Props.box(maw, Vector3(size, 0.05, size * 0.8), Vector3(0, size * 0.05, 0), red)
	for i in 7:
		var x := -size * 0.44 + i * size * 0.147
		Props.box(maw, Vector3(0.04, 0.12, 0.04), Vector3(x, size * 0.55, size * 0.38), tooth)
		Props.box(maw, Vector3(0.04, 0.12, 0.04), Vector3(x, size * 0.12, size * 0.38), tooth)
	_eyes(maw, size * 0.95, size * 0.4, size * 0.22, 0.09, Color(1, 0.15, 0.05))
	parent.add_child(maw)
	return maw
