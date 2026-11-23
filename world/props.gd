class_name Props extends RefCounted
## Процедурная мебель и предметы из примитивов (low-poly).

const WOOD := "wood"

static func _mi(parent: Node, mesh: Mesh, pos: Vector3, mat: Material, rot := Vector3.ZERO) -> MeshInstance3D:
	var m := MeshInstance3D.new()
	m.mesh = mesh
	m.position = pos
	m.rotation_degrees = rot
	m.material_override = mat
	parent.add_child(m)
	return m

static func box(parent: Node, size: Vector3, pos: Vector3, mat: Material, rot := Vector3.ZERO) -> MeshInstance3D:
	var b := BoxMesh.new(); b.size = size
	return _mi(parent, b, pos, mat, rot)

static func cyl(parent: Node, r: float, h: float, pos: Vector3, mat: Material, r2 := -1.0, seg := 10) -> MeshInstance3D:
	var c := CylinderMesh.new()
	c.top_radius = r if r2 < 0 else r2
	c.bottom_radius = r
	c.height = h
	c.radial_segments = seg
	c.rings = 1
	return _mi(parent, c, pos, mat)

static func sph(parent: Node, r: float, pos: Vector3, mat: Material, sy := 1.0) -> MeshInstance3D:
	var s := SphereMesh.new()
	s.radius = r; s.height = r * 2.0
	s.radial_segments = 10; s.rings = 6
	var m := _mi(parent, s, pos, mat)
	m.scale.y = sy
	return m

static func cap(parent: Node, r: float, h: float, pos: Vector3, mat: Material, sx := 1.0, sz := 1.0) -> MeshInstance3D:
	var c := CapsuleMesh.new()
	c.radius = r; c.height = maxf(h, r * 2.0 + 0.01)
	c.radial_segments = 12; c.rings = 4
	var m := _mi(parent, c, pos, mat)
	m.scale = Vector3(sx, 1.0, sz)
	return m

static func col(root: Node3D, size: Vector3, center: Vector3, layer := 8) -> StaticBody3D:
	var sb := StaticBody3D.new()
	sb.collision_layer = layer
	sb.collision_mask = 0
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new(); bs.size = size
	cs.shape = bs
	cs.position = center
	sb.add_child(cs)
	root.add_child(sb)
	return sb

# Реалистичные модели Poly Haven (CC0). fit: h — по высоте, w — по большей стороне основания, box — по трём осям.
const MODELS := {
	"sofa": {"id": "sofa_02", "fit": "w", "v": 2.0},
	"armchair": {"id": "ArmChair_01", "fit": "h", "v": 0.95},
	"table": {"id": "dining_table", "fit": "box", "v": Vector3(1.6, 0.78, 0.95)},
	"chair": {"id": "dining_chair_02", "fit": "h", "v": 0.95},
	"stool": {"id": "wooden_stool_01", "fit": "h", "v": 0.5},
	"bed": {"id": "GothicBed_01", "fit": "w", "v": 2.1},
	"wardrobe": {"id": "GothicCabinet_01", "fit": "h", "v": 2.0},
	"bookshelf": {"id": "wooden_bookshelf_worn", "fit": "h", "v": 2.0},
	"dresser": {"id": "vintage_wooden_drawer_01", "fit": "h", "v": 0.9},
	"stove": {"id": "electric_stove", "fit": "h", "v": 0.9},
	"mirror": {"id": "ornate_mirror_01", "fit": "h", "v": 1.5},
	"radio": {"id": "vintage_radio_transceiver", "fit": "h", "v": 0.3},
	"plant": {"id": "potted_plant_01", "fit": "h", "v": 1.1},
	"bucket": {"id": "wooden_bucket_01", "fit": "h", "v": 0.35},
	"crate": {"id": "wooden_crate_01", "fit": "h", "v": 0.6},
	"box": {"id": "cardboard_box_01", "fit": "h", "v": 0.45},
	"bag": {"id": "trashbag", "fit": "h", "v": 0.55},
	"kettle": {"id": "vintage_electric_kettle", "fit": "h", "v": 0.22},
	"suitcase": {"id": "vintage_suitcase", "fit": "h", "v": 0.55},
	"statue": {"id": "gothic_statue", "fit": "h", "v": 1.8},
	"nightstand": {"id": "ClassicNightstand_01", "fit": "h", "v": 0.6},
	"vase": {"id": "ceramic_vase_01", "fit": "h", "v": 0.35},
	"vase2": {"id": "antique_ceramic_vase_01", "fit": "h", "v": 0.4},
	"books": {"id": "decorative_book_set_01", "fit": "w", "v": 0.35},
	"chest": {"id": "treasure_chest", "fit": "w", "v": 0.9},
	"toolchest": {"id": "metal_tool_chest", "fit": "h", "v": 0.7},
	"fusebox": {"id": "power_box_01", "fit": "h", "v": 0.7},
	"ceilinglamp": {"id": "modern_ceiling_lamp_01", "fit": "h", "v": 0.5},
	"chandelier": {"id": "Chandelier_01", "fit": "h", "v": 0.9},
	"frame1": {"id": "fancy_picture_frame_01", "fit": "w", "v": 0.8},
	"frame2": {"id": "fancy_picture_frame_02", "fit": "w", "v": 0.7},
	"frame3": {"id": "hanging_picture_frame_01", "fit": "w", "v": 0.7},
	"frame4": {"id": "hanging_picture_frame_02", "fit": "w", "v": 0.6},
	"frame5": {"id": "hanging_picture_frame_03", "fit": "w", "v": 0.6},
	"alarmclock": {"id": "alarm_clock_01", "fit": "h", "v": 0.14},
	"mantel": {"id": "mantel_clock_01", "fit": "h", "v": 0.25},
	"bottles": {"id": "wine_bottles_01", "fit": "w", "v": 0.4},
	"candles": {"id": "brass_candleholders", "fit": "h", "v": 0.35},
	"deskl": {"id": "desk_lamp_arm_01", "fit": "h", "v": 0.4},
	"boombox": {"id": "boombox", "fit": "w", "v": 0.4},
	"pot": {"id": "pot_enamel_01", "fit": "w", "v": 0.3},
	"barrel": {"id": "Barrel_01", "fit": "h", "v": 0.9},
	"ladder": {"id": "wooden_ladder", "fit": "h", "v": 1.5},
	"rocker": {"id": "Rockingchair_01", "fit": "h", "v": 1.0},
	"bench": {"id": "painted_wooden_bench", "fit": "w", "v": 1.2},
	"coffeetable": {"id": "gothic_coffee_table", "fit": "box", "v": Vector3(1.1, 0.45, 0.7)},
	"covered_car": {"id": "covered_car", "fit": "w", "v": 4.2},
	"desk": {"id": "metal_office_desk", "fit": "w", "v": 1.4},
	"crate_red": {"id": "plastic_crate_01", "fit": "w", "v": 0.5},
	"broom": {"id": "wooden_broom", "fit": "h", "v": 1.3},
	"spraybottle": {"id": "multi_cleaner_bottle", "fit": "h", "v": 0.28},
}
static var _scenes: Dictionary = {}

static func _aabb_rec(n: Node3D, parent_xf: Transform3D, acc: Array) -> void:
	var xf := parent_xf * n.transform
	if n is MeshInstance3D and n.mesh:
		var a: AABB = xf * n.get_aabb()
		acc[0] = a if acc[0] == null else (acc[0] as AABB).merge(a)
	for c in n.get_children():
		if c is Node3D:
			_aabb_rec(c, xf, acc)

static func model(kind: String, o := {}) -> Node3D:
	if not MODELS.has(kind):
		return null
	var m: Dictionary = MODELS[kind]
	var path := "res://assets/models/%s/%s.gltf" % [m.id, m.id]
	if not _scenes.has(path):
		_scenes[path] = load(path) if ResourceLoader.exists(path) else null
	var ps: PackedScene = _scenes[path]
	if ps == null:
		return null
	var inst: Node3D = ps.instantiate()
	var acc := [null]
	_aabb_rec(inst, Transform3D.IDENTITY, acc)
	if acc[0] == null:
		inst.queue_free()
		return null
	var bb: AABB = acc[0]
	var sc := Vector3.ONE
	match m.fit:
		"h": sc = Vector3.ONE * (float(m.v) / maxf(bb.size.y, 0.001))
		"w": sc = Vector3.ONE * (float(m.v) / maxf(maxf(bb.size.x, bb.size.z), 0.001))
		"box":
			var v: Vector3 = m.v
			if o.has("w"): v.x = o.w
			if o.has("d"): v.z = o.d
			sc = Vector3(v.x / maxf(bb.size.x, 0.001), v.y / maxf(bb.size.y, 0.001), v.z / maxf(bb.size.z, 0.001))
	if o.has("s") and kind in ["crate", "box"]:
		sc = Vector3.ONE * (float(o.s) / maxf(bb.size.y, 0.001))
	var holder := Node3D.new()
	holder.name = kind
	var yaw: float = float(m.get("yaw", 0.0))
	inst.scale = sc
	var ctr := bb.get_center()
	inst.position = Vector3(-ctr.x * sc.x, -bb.position.y * sc.y, -ctr.z * sc.z)
	holder.add_child(inst)
	var size := bb.size * sc
	holder.set_meta("size", size)
	if kind not in ["bag", "mirror", "radio", "kettle", "books", "vase", "vase2", "alarmclock", "mantel", "bottles", "candles", "deskl", "boombox", "pot", "ceilinglamp", "chandelier", "frame1", "frame2", "frame3", "frame4", "frame5", "broom", "spraybottle"]:
		col(holder, size, Vector3(0, size.y / 2.0, 0))
	return holder

static func _clutter(holder: Node3D, kind: String, o: Dictionary) -> void:
	var sz: Vector3 = holder.get_meta("size", Vector3(1, 0.8, 0.8))
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(str(o) + kind + str(Time.get_ticks_usec() % 7))
	var pool: Array = ["vase", "books", "candles", "bottles", "pot", "alarmclock"] if kind == "table" else ["mantel", "vase2", "books", "alarmclock", "deskl"]
	var n := 1 if sz.x < 1.2 else 2
	for i in n:
		var k: String = pool[rng.randi() % pool.size()]
		var it := model(k, {})
		if it:
			it.position = Vector3(rng.randf_range(-sz.x * 0.35, sz.x * 0.35), sz.y, rng.randf_range(-sz.z * 0.25, sz.z * 0.25))
			it.rotation_degrees.y = rng.randf() * 360.0
			holder.add_child(it)

static func make(kind: String, o := {}) -> Node3D:
	if kind == "picture":
		var fk := "frame%d" % (1 + int(abs(hash(str(o))) + int(o.get("fr", 0))) % 5)
		var fm := model(fk, o)
		if fm != null:
			fm.name = "picture"
			# повернуть: рама лежит в плоскости XY лицом +Z (после проверки при необходимости меняется yaw модели)
			return fm
	var mdl := model(kind, o)
	if mdl != null:
		mdl.name = kind
		if kind in ["table", "dresser", "coffeetable"] and not o.get("noclutter", false):
			_clutter(mdl, kind, o)
		return mdl
	var r := Node3D.new()
	r.name = kind
	var wood := Mats.tex("wood", 0.8, Color(0.75, 0.62, 0.5))
	var dark_wood := Mats.tex("wood", 0.8, Color(0.35, 0.26, 0.2))
	match kind:
		"table":
			var w: float = o.get("w", 1.4); var d: float = o.get("d", 0.8)
			box(r, Vector3(w, 0.05, d), Vector3(0, 0.74, 0), wood)
			for sx in [-1, 1]:
				for sz in [-1, 1]:
					box(r, Vector3(0.06, 0.72, 0.06), Vector3(sx * (w / 2 - 0.06), 0.36, sz * (d / 2 - 0.06)), dark_wood)
			col(r, Vector3(w, 0.78, d), Vector3(0, 0.39, 0))
		"chair":
			box(r, Vector3(0.42, 0.04, 0.42), Vector3(0, 0.45, 0), wood)
			box(r, Vector3(0.42, 0.5, 0.04), Vector3(0, 0.72, -0.19), wood)
			for sx in [-1, 1]:
				for sz in [-1, 1]:
					box(r, Vector3(0.04, 0.45, 0.04), Vector3(sx * 0.18, 0.22, sz * 0.18), dark_wood)
			col(r, Vector3(0.45, 0.95, 0.45), Vector3(0, 0.47, 0))
		"stool":
			cyl(r, 0.2, 0.05, Vector3(0, 0.5, 0), wood)
			cyl(r, 0.03, 0.5, Vector3(0, 0.25, 0), dark_wood)
			col(r, Vector3(0.4, 0.55, 0.4), Vector3(0, 0.27, 0))
		"sofa":
			var fab := Mats.tex("fabric", 0.9, o.get("tint", Color(0.55, 0.45, 0.4)))
			box(r, Vector3(2.0, 0.4, 0.9), Vector3(0, 0.25, 0), fab)
			box(r, Vector3(2.0, 0.55, 0.22), Vector3(0, 0.7, -0.34), fab)
			box(r, Vector3(0.2, 0.55, 0.9), Vector3(-0.9, 0.5, 0), fab)
			box(r, Vector3(0.2, 0.55, 0.9), Vector3(0.9, 0.5, 0), fab)
			box(r, Vector3(1.5, 0.15, 0.7), Vector3(0, 0.5, 0.05), fab)
			col(r, Vector3(2.0, 0.9, 0.9), Vector3(0, 0.45, 0))
		"armchair":
			var fab2 := Mats.tex("leather", 0.9, Color(0.7, 0.6, 0.55))
			box(r, Vector3(0.9, 0.4, 0.9), Vector3(0, 0.25, 0), fab2)
			box(r, Vector3(0.9, 0.6, 0.2), Vector3(0, 0.7, -0.35), fab2)
			box(r, Vector3(0.15, 0.5, 0.9), Vector3(-0.38, 0.5, 0), fab2)
			box(r, Vector3(0.15, 0.5, 0.9), Vector3(0.38, 0.5, 0), fab2)
			col(r, Vector3(0.9, 0.9, 0.9), Vector3(0, 0.45, 0))
		"bed":
			var fab3 := Mats.tex("fabric", 0.9, o.get("tint", Color(0.6, 0.6, 0.65)))
			box(r, Vector3(2.0, 0.3, 1.4), Vector3(0, 0.25, 0), dark_wood)
			box(r, Vector3(1.9, 0.18, 1.3), Vector3(0, 0.49, 0), Mats.color(Color(0.8, 0.78, 0.72)))
			box(r, Vector3(1.4, 0.1, 1.35), Vector3(0.25, 0.6, 0), fab3)
			box(r, Vector3(0.4, 0.12, 0.8), Vector3(-0.75, 0.62, 0), Mats.color(Color(0.9, 0.9, 0.88)))
			box(r, Vector3(0.08, 0.9, 1.4), Vector3(-1.0, 0.6, 0), dark_wood)
			col(r, Vector3(2.0, 0.7, 1.4), Vector3(0, 0.35, 0))
		"crib":
			box(r, Vector3(1.2, 0.05, 0.65), Vector3(0, 0.4, 0), wood)
			for i in 9:
				box(r, Vector3(0.03, 0.55, 0.03), Vector3(-0.55 + i * 0.1375, 0.7, 0.3), wood)
				box(r, Vector3(0.03, 0.55, 0.03), Vector3(-0.55 + i * 0.1375, 0.7, -0.3), wood)
			box(r, Vector3(1.2, 0.04, 0.04), Vector3(0, 0.98, 0.3), wood)
			box(r, Vector3(1.2, 0.04, 0.04), Vector3(0, 0.98, -0.3), wood)
			box(r, Vector3(0.04, 0.7, 0.65), Vector3(-0.6, 0.7, 0), wood)
			box(r, Vector3(0.04, 0.7, 0.65), Vector3(0.6, 0.7, 0), wood)
			col(r, Vector3(1.2, 1.0, 0.65), Vector3(0, 0.5, 0))
		"wardrobe":
			var wm := Mats.tex("wood", 0.7, o.get("tint", Color(0.55, 0.42, 0.32)))
			box(r, Vector3(1.1, 2.0, 0.55), Vector3(0, 1.0, 0), wm)
			box(r, Vector3(0.02, 1.8, 0.02), Vector3(0, 1.0, 0.28), Mats.color(Color(0.05, 0.04, 0.03)))
			box(r, Vector3(0.04, 0.18, 0.03), Vector3(-0.07, 1.0, 0.29), Mats.color(Color(0.6, 0.55, 0.3), 0.3, 0.0, 0.8))
			box(r, Vector3(0.04, 0.18, 0.03), Vector3(0.07, 1.0, 0.29), Mats.color(Color(0.6, 0.55, 0.3), 0.3, 0.0, 0.8))
			col(r, Vector3(1.1, 2.0, 0.55), Vector3(0, 1.0, 0))
		"bookshelf":
			box(r, Vector3(1.2, 2.0, 0.3), Vector3(0, 1.0, 0), dark_wood)
			var rng := RandomNumberGenerator.new(); rng.seed = int(o.get("seed", 3))
			for sh in 5:
				var sy := 0.25 + sh * 0.38
				box(r, Vector3(1.14, 0.03, 0.28), Vector3(0, sy, 0.02), wood)
				var x := -0.5
				while x < 0.5:
					var bw := rng.randf_range(0.04, 0.1)
					var bh := rng.randf_range(0.2, 0.32)
					box(r, Vector3(bw, bh, 0.2), Vector3(x + bw / 2, sy + bh / 2 + 0.02, 0.04),
						Mats.color(Color.from_hsv(rng.randf(), rng.randf_range(0.2, 0.5), rng.randf_range(0.25, 0.55))))
					x += bw + 0.01
			col(r, Vector3(1.2, 2.0, 0.3), Vector3(0, 1.0, 0))
		"dresser":
			box(r, Vector3(1.0, 0.9, 0.5), Vector3(0, 0.45, 0), wood)
			for i in 3:
				box(r, Vector3(0.9, 0.02, 0.02), Vector3(0, 0.2 + i * 0.27, 0.26), Mats.color(Color(0.1, 0.08, 0.06)))
				box(r, Vector3(0.12, 0.03, 0.03), Vector3(0, 0.3 + i * 0.27, 0.27), Mats.color(Color(0.6, 0.55, 0.3), 0.3, 0, 0.8))
			col(r, Vector3(1.0, 0.9, 0.5), Vector3(0, 0.45, 0))
		"tv":
			box(r, Vector3(1.0, 0.5, 0.45), Vector3(0, 0.25, 0), dark_wood)
			box(r, Vector3(0.9, 0.55, 0.12), Vector3(0, 0.78, 0), Mats.color(Color(0.04, 0.04, 0.05)))
			var scr := box(r, Vector3(0.8, 0.45, 0.01), Vector3(0, 0.78, 0.065), Mats.color(Color(0.1, 0.12, 0.13), 0.3))
			scr.name = "screen"
			col(r, Vector3(1.0, 1.1, 0.45), Vector3(0, 0.55, 0))
		"lamp":
			cyl(r, 0.12, 0.03, Vector3(0, 0.015, 0), Mats.color(Color(0.1, 0.1, 0.1)))
			cyl(r, 0.015, 1.5, Vector3(0, 0.75, 0), Mats.color(Color(0.1, 0.1, 0.1)))
			var sh := cyl(r, 0.22, 0.28, Vector3(0, 1.55, 0), Mats.color(Color(1.0, 0.85, 0.55), 0.8, 0.7), 0.14)
			sh.name = "shade"
			var li := OmniLight3D.new()
			li.position = Vector3(0, 1.5, 0)
			li.light_color = Color(1.0, 0.8, 0.5)
			li.light_energy = o.get("energy", 0.9)
			li.omni_range = 6.0
			li.name = "light"
			r.add_child(li)
			col(r, Vector3(0.3, 1.7, 0.3), Vector3(0, 0.85, 0))
		"fridge":
			box(r, Vector3(0.7, 1.8, 0.7), Vector3(0, 0.9, 0), Mats.color(Color(0.8, 0.8, 0.78), 0.4))
			box(r, Vector3(0.66, 0.02, 0.02), Vector3(0, 1.25, 0.36), Mats.color(Color(0.1, 0.1, 0.1)))
			box(r, Vector3(0.03, 0.4, 0.03), Vector3(0.28, 1.5, 0.37), Mats.color(Color(0.5, 0.5, 0.5), 0.3, 0, 0.8))
			box(r, Vector3(0.03, 0.4, 0.03), Vector3(0.28, 0.9, 0.37), Mats.color(Color(0.5, 0.5, 0.5), 0.3, 0, 0.8))
			col(r, Vector3(0.7, 1.8, 0.7), Vector3(0, 0.9, 0))
		"stove":
			box(r, Vector3(0.6, 0.9, 0.6), Vector3(0, 0.45, 0), Mats.color(Color(0.75, 0.75, 0.72), 0.4))
			for ox in [-0.14, 0.14]:
				for oz in [-0.14, 0.14]:
					cyl(r, 0.08, 0.02, Vector3(ox, 0.91, oz), Mats.color(Color(0.05, 0.05, 0.05)))
			box(r, Vector3(0.5, 0.35, 0.02), Vector3(0, 0.4, 0.31), Mats.color(Color(0.08, 0.08, 0.1), 0.2))
			col(r, Vector3(0.6, 0.9, 0.6), Vector3(0, 0.45, 0))
		"counter":
			var w2: float = o.get("w", 2.0)
			box(r, Vector3(w2, 0.86, 0.6), Vector3(0, 0.43, 0), Mats.tex("wood", 0.7, Color(0.6, 0.55, 0.5)))
			box(r, Vector3(w2 + 0.04, 0.04, 0.64), Vector3(0, 0.88, 0), Mats.color(Color(0.55, 0.55, 0.52), 0.4))
			if o.get("sink", true):
				box(r, Vector3(0.5, 0.02, 0.4), Vector3(0.0, 0.9, 0), Mats.color(Color(0.3, 0.3, 0.32), 0.3, 0, 0.7))
				cyl(r, 0.015, 0.25, Vector3(0, 1.0, -0.22), Mats.color(Color(0.6, 0.6, 0.6), 0.3, 0, 0.9))
			col(r, Vector3(w2, 0.9, 0.6), Vector3(0, 0.45, 0))
		"toilet":
			var wh := Mats.color(Color(0.85, 0.85, 0.82), 0.3)
			box(r, Vector3(0.4, 0.4, 0.5), Vector3(0, 0.2, 0.05), wh)
			box(r, Vector3(0.4, 0.4, 0.18), Vector3(0, 0.6, -0.2), wh)
			col(r, Vector3(0.4, 0.8, 0.55), Vector3(0, 0.4, 0))
		"bathtub":
			var wh2 := Mats.color(Color(0.86, 0.86, 0.83), 0.3)
			box(r, Vector3(1.7, 0.55, 0.75), Vector3(0, 0.28, 0), wh2)
			box(r, Vector3(1.5, 0.04, 0.55), Vector3(0, 0.56, 0), Mats.color(Color(0.12, 0.14, 0.12), 0.2))
			col(r, Vector3(1.7, 0.6, 0.75), Vector3(0, 0.3, 0))
		"washbasin":
			var wh3 := Mats.color(Color(0.86, 0.86, 0.83), 0.3)
			box(r, Vector3(0.55, 0.12, 0.42), Vector3(0, 0.85, 0), wh3)
			cyl(r, 0.06, 0.8, Vector3(0, 0.4, 0), wh3)
			col(r, Vector3(0.55, 0.95, 0.42), Vector3(0, 0.47, 0))
		"crate":
			var s: float = o.get("s", 0.6)
			box(r, Vector3(s, s, s), Vector3(0, s / 2, 0), Mats.tex("wood", 0.9, Color(0.65, 0.55, 0.42)))
			col(r, Vector3(s, s, s), Vector3(0, s / 2, 0))
		"box":
			var s2: float = o.get("s", 0.5)
			box(r, Vector3(s2, s2 * 0.8, s2), Vector3(0, s2 * 0.4, 0), Mats.color(Color(0.55, 0.42, 0.28), 1.0))
			box(r, Vector3(s2 * 0.05, 0.005 + s2 * 0.8, s2 + 0.01), Vector3(0, s2 * 0.4, 0), Mats.color(Color(0.7, 0.6, 0.4), 1.0))
			col(r, Vector3(s2, s2 * 0.8, s2), Vector3(0, s2 * 0.4, 0))
		"bag":
			sph(r, 0.25, Vector3(0, 0.25, 0), Mats.color(Color(0.04, 0.04, 0.05), 0.4), 1.15)
			cyl(r, 0.04, 0.12, Vector3(0, 0.55, 0), Mats.color(Color(0.04, 0.04, 0.05), 0.4))
			col(r, Vector3(0.5, 0.55, 0.5), Vector3(0, 0.27, 0), 0)
		"rug":
			var rw: float = o.get("w", 2.4); var rd: float = o.get("d", 1.6)
			box(r, Vector3(rw, 0.02, rd), Vector3(0, 0.011, 0), Mats.tex("floor_carpet", 0.6, o.get("tint", Color(0.55, 0.3, 0.3))))
			box(r, Vector3(rw - 0.3, 0.025, rd - 0.3), Vector3(0, 0.012, 0), Mats.color(o.get("tint2", Color(0.35, 0.15, 0.15)), 1.0))
		"picture":
			box(r, Vector3(0.7, 0.5, 0.04), Vector3(0, 0, 0), Mats.color(Color(0.15, 0.1, 0.07)))
			var pic := box(r, Vector3(0.6, 0.4, 0.01), Vector3(0, 0, 0.022), Mats.color(o.get("c", Color(0.35, 0.4, 0.3)), 0.9))
			pic.name = "pic"
		"mirror":
			box(r, Vector3(0.9, 1.4, 0.05), Vector3(0, 0, 0), Mats.color(Color(0.2, 0.17, 0.12)))
			var gl := box(r, Vector3(0.8, 1.3, 0.01), Vector3(0, 0, 0.028), Mats.color(Color(0.28, 0.32, 0.34), 0.05, 0.0, 0.95))
			gl.name = "glass"
		"window":
			box(r, Vector3(1.2, 1.2, 0.08), Vector3(0, 0, 0), Mats.color(Color(0.2, 0.2, 0.22)))
			var pane := box(r, Vector3(1.08, 1.08, 0.02), Vector3(0, 0, 0.03), Mats.color(o.get("c", Color(0.06, 0.09, 0.16)), 0.2, 0.9))
			pane.name = "pane"
			box(r, Vector3(1.14, 0.04, 0.05), Vector3(0, 0, 0.04), Mats.color(Color(0.8, 0.8, 0.8)))
			box(r, Vector3(0.04, 1.14, 0.05), Vector3(0, 0, 0.04), Mats.color(Color(0.8, 0.8, 0.8)))
		"radio":
			box(r, Vector3(0.35, 0.2, 0.12), Vector3(0, 0.1, 0), Mats.color(Color(0.4, 0.28, 0.15)))
			cyl(r, 0.045, 0.02, Vector3(-0.09, 0.1, 0.07), Mats.color(Color(0.8, 0.8, 0.7)))
			box(r, Vector3(0.14, 0.08, 0.01), Vector3(0.07, 0.1, 0.061), Mats.color(Color(0.9, 0.7, 0.3), 0.5, 0.2)).name = "dial"
			col(r, Vector3(0.35, 0.2, 0.12), Vector3(0, 0.1, 0), 0)
		"clock":
			cyl(r, 0.2, 0.04, Vector3(0, 0, 0), Mats.color(Color(0.85, 0.82, 0.7)))
			r.get_child(0).rotation_degrees = Vector3(90, 0, 0)
			var hh := Node3D.new(); hh.name = "hour"; r.add_child(hh)
			box(hh, Vector3(0.015, 0.09, 0.01), Vector3(0, 0.045, 0.03), Mats.color(Color(0.05, 0.05, 0.05)))
			var mh := Node3D.new(); mh.name = "min"; r.add_child(mh)
			box(mh, Vector3(0.01, 0.15, 0.01), Vector3(0, 0.075, 0.035), Mats.color(Color(0.05, 0.05, 0.05)))
		"plant":
			cyl(r, 0.16, 0.3, Vector3(0, 0.15, 0), Mats.color(Color(0.45, 0.25, 0.15)), 0.12)
			for i in 6:
				var a := i * TAU / 6.0
				sph(r, 0.12, Vector3(cos(a) * 0.12, 0.5 + (i % 3) * 0.1, sin(a) * 0.12), Mats.color(Color(0.15, 0.3, 0.12), 0.8), 1.6)
			col(r, Vector3(0.35, 0.9, 0.35), Vector3(0, 0.45, 0))
		"piano":
			box(r, Vector3(1.5, 1.2, 0.6), Vector3(0, 0.6, 0), Mats.color(Color(0.06, 0.05, 0.05), 0.35))
			box(r, Vector3(1.4, 0.04, 0.3), Vector3(0, 0.8, 0.4), Mats.color(Color(0.9, 0.9, 0.85)))
			box(r, Vector3(1.4, 0.06, 0.12), Vector3(0, 0.84, 0.35), Mats.color(Color(0.02, 0.02, 0.02)))
			col(r, Vector3(1.5, 1.2, 0.9), Vector3(0, 0.6, 0.15))
		"teddy":
			var tm := Mats.color(Color(0.5, 0.33, 0.2), 1.0)
			sph(r, 0.1, Vector3(0, 0.1, 0), tm, 1.2)
			sph(r, 0.07, Vector3(0, 0.26, 0), tm)
			sph(r, 0.025, Vector3(-0.055, 0.32, 0), tm); sph(r, 0.025, Vector3(0.055, 0.32, 0), tm)
			sph(r, 0.01, Vector3(-0.025, 0.27, 0.06), Mats.color(Color.BLACK)); sph(r, 0.01, Vector3(0.025, 0.27, 0.06), Mats.color(Color.BLACK))
		"bucket":
			cyl(r, 0.2, 0.34, Vector3(0, 0.17, 0), Mats.color(Color(0.15, 0.3, 0.55), 0.5), 0.25)
			var w3 := cyl(r, 0.18, 0.01, Vector3(0, 0.32, 0), Mats.color(Color(0.3, 0.45, 0.5), 0.1, 0.0, 0.5))
			w3.name = "water"
			col(r, Vector3(0.5, 0.35, 0.5), Vector3(0, 0.17, 0))
		"dumpster":
			box(r, Vector3(1.6, 1.1, 0.9), Vector3(0, 0.55, 0), Mats.tex("metal", 0.6, Color(0.25, 0.4, 0.3)))
			box(r, Vector3(1.7, 0.08, 1.0), Vector3(0, 1.12, 0), Mats.color(Color(0.1, 0.18, 0.12)))
			col(r, Vector3(1.6, 1.1, 0.9), Vector3(0, 0.55, 0))
		"supply":
			box(r, Vector3(0.7, 0.45, 0.45), Vector3(0, 0.225, 0), Mats.color(Color(0.8, 0.55, 0.1), 0.6))
			box(r, Vector3(0.72, 0.04, 0.47), Vector3(0, 0.47, 0), Mats.color(Color(0.2, 0.2, 0.2)))
			box(r, Vector3(0.2, 0.12, 0.01), Vector3(0, 0.25, 0.23), Mats.color(Color(0.95, 0.95, 0.9)))
			col(r, Vector3(0.7, 0.5, 0.45), Vector3(0, 0.25, 0))
		"candle":
			cyl(r, 0.03, 0.15, Vector3(0, 0.075, 0), Mats.color(Color(0.9, 0.88, 0.8)))
			var fl := sph(r, 0.015, Vector3(0, 0.17, 0), Mats.color(Color(1, 0.7, 0.2), 0.5, 3.0), 1.8)
			fl.name = "flame"
			var cl := OmniLight3D.new()
			cl.position = Vector3(0, 0.25, 0)
			cl.light_color = Color(1, 0.65, 0.3); cl.light_energy = 0.6; cl.omni_range = 3.5
			cl.name = "light"
			r.add_child(cl)
		"phone":
			box(r, Vector3(0.07, 0.01, 0.14), Vector3(0, 0.005, 0), Mats.color(Color(0.05, 0.05, 0.06)))
			box(r, Vector3(0.06, 0.002, 0.12), Vector3(0, 0.011, 0), Mats.color(Color(0.4, 0.7, 1.0), 0.3, 1.0))
		"tape":
			box(r, Vector3(0.12, 0.03, 0.08), Vector3(0, 0.015, 0), Mats.color(Color(0.1, 0.1, 0.12)))
			cyl(r, 0.02, 0.005, Vector3(-0.03, 0.032, 0), Mats.color(Color(0.7, 0.7, 0.7), 0.3, 0, 0.9))
			cyl(r, 0.02, 0.005, Vector3(0.03, 0.032, 0), Mats.color(Color(0.7, 0.7, 0.7), 0.3, 0, 0.9))
		"badge":
			box(r, Vector3(0.09, 0.005, 0.06), Vector3(0, 0.003, 0), Mats.color(Color(0.8, 0.8, 0.85), 0.5))
			box(r, Vector3(0.03, 0.006, 0.03), Vector3(-0.025, 0.004, 0), Mats.color(Color(0.2, 0.3, 0.6)))
		"key":
			cyl(r, 0.02, 0.005, Vector3(0, 0.003, 0), Mats.color(Color(0.8, 0.7, 0.2), 0.3, 0.2, 0.9))
			box(r, Vector3(0.07, 0.005, 0.012), Vector3(0.05, 0.003, 0), Mats.color(Color(0.8, 0.7, 0.2), 0.3, 0.2, 0.9))
		"paper":
			box(r, Vector3(0.21, 0.004, 0.3), Vector3(0, 0.003, 0), Mats.color(o.get("c", Color(0.9, 0.88, 0.8)), 0.9, 0.12))
		"bars":
			for i in 7:
				box(r, Vector3(0.03, 2.2, 0.03), Vector3(-0.9 + i * 0.3, 1.1, 0), Mats.color(Color(0.1, 0.1, 0.1), 0.5, 0, 0.8))
			col(r, Vector3(1.9, 2.2, 0.1), Vector3(0, 1.1, 0))
		"pillar":
			cyl(r, 0.3, o.get("h", 3.0), Vector3(0, o.get("h", 3.0) / 2, 0), Mats.tex("wall_grey", 0.5, Color(0.7, 0.7, 0.7)))
			col(r, Vector3(0.6, o.get("h", 3.0), 0.6), Vector3(0, o.get("h", 3.0) / 2, 0))
		_:
			box(r, Vector3(0.5, 0.5, 0.5), Vector3(0, 0.25, 0), Mats.color(Color(1, 0, 1)))
	return r
