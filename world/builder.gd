class_name Builder extends RefCounted
## Строит уровень: комнаты по ASCII-плану, стены с проёмами, двери, свет, навигационный граф.

const WALL_T := 0.1
const DOOR_W := 1.0
const DOOR_H := 2.1

var root: Node3D
var level: Node
var rooms: Dictionary = {}
var doors: Array = []
var lights: Array = []
var tasks: Dictionary = {}
var task_order: Array = []
var patches: Dictionary = {}
var notes_nodes: Dictionary = {}
var monsters: Array = []
var hide_spots: Array = []
var graph := AStar3D.new()
var graph_ids: Dictionary = {}
var spawn := Vector3(0, 0.1, 0)
var spawn_yaw := 0.0
var _patch_n := 0
var trash_total := 0

func _init(r: Node3D, lv: Node) -> void:
	root = r
	level = lv

# ------------------------------------------------ комнаты
func layout(rows: Array, legend: Dictionary, y := 0.0, cell := 4.0, origin := Vector2.ZERO) -> void:
	var ext := {}
	for ri in rows.size():
		var row: String = rows[ri]
		for ci in row.length():
			var ch := row[ci]
			if ch == " " or ch == ".":
				continue
			if not ext.has(ch):
				ext[ch] = [ci, ri, ci, ri]
			else:
				ext[ch][0] = mini(ext[ch][0], ci); ext[ch][1] = mini(ext[ch][1], ri)
				ext[ch][2] = maxi(ext[ch][2], ci); ext[ch][3] = maxi(ext[ch][3], ri)
	for ch in ext:
		var e = ext[ch]
		var rect := Rect2(origin + Vector2(e[0], e[1]) * cell, Vector2(e[2] - e[0] + 1, e[3] - e[1] + 1) * cell)
		var spec: Dictionary = legend.get(ch, {})
		room(ch, rect, y, spec)

func room(id: String, rect: Rect2, y: float, spec := {}) -> void:
	var d := {
		"id": id, "rect": rect, "y": y, "h": spec.get("h", 2.7),
		"name": spec.get("name", id),
		"floor": spec.get("floor", "floor_wood"), "wall": spec.get("wall", "wall_paper"), "ceil": spec.get("ceil", "ceil"),
		"floor_tint": spec.get("floor_tint", Color(0.8, 0.75, 0.7)),
		"wall_tint": spec.get("wall_tint", Color(0.75, 0.7, 0.62)),
		"light": spec.get("light", 1.0), "light_color": spec.get("light_color", Color(1.0, 0.82, 0.6)),
		"ramp": spec.get("ramp", ""), "rise": spec.get("rise", 3.0),
		"dark": spec.get("dark", false),
	}
	rooms[id] = d

func room_at(p: Vector3) -> String:
	for id in rooms:
		var r: Dictionary = rooms[id]
		var rc: Rect2 = r.rect
		if rc.has_point(Vector2(p.x, p.z)) and p.y >= r.y - 0.5 and p.y <= r.y + r.h + 0.2:
			if r.ramp != "":
				return id
			return id
	return ""

func room_center(id: String) -> Vector3:
	var r: Dictionary = rooms[id]
	var c: Vector2 = r.rect.get_center()
	return Vector3(c.x, r.y, c.y)

# ------------------------------------------------ двери
func door(a: String, b: String, opts := {}) -> Dictionary:
	var ra: Rect2 = rooms[a].rect
	var rb: Rect2 = rooms[b].rect
	var d := {"a": a, "b": b, "w": opts.get("w", DOOR_W), "opts": opts}
	var eps := 0.05
	var frac: float = opts.get("at", 0.5)
	if absf(ra.end.x - rb.position.x) < eps or absf(rb.end.x - ra.position.x) < eps:
		var xline: float = ra.end.x if absf(ra.end.x - rb.position.x) < eps else ra.position.x
		var lo := maxf(ra.position.y, rb.position.y)
		var hi := minf(ra.end.y, rb.end.y)
		d.axis = "x"; d.line = xline
		d.center = lo + (hi - lo) * frac
	elif absf(ra.end.y - rb.position.y) < eps or absf(rb.end.y - ra.position.y) < eps:
		var zline: float = ra.end.y if absf(ra.end.y - rb.position.y) < eps else ra.position.y
		var lo2 := maxf(ra.position.x, rb.position.x)
		var hi2 := minf(ra.end.x, rb.end.x)
		d.axis = "z"; d.line = zline
		d.center = lo2 + (hi2 - lo2) * frac
	else:
		push_error("door: комнаты %s и %s не соседствуют" % [a, b])
		return {}
	var ya: float = rooms[a].y; var yb: float = rooms[b].y
	if rooms[a].ramp != "" and rooms[b].ramp == "":
		d.y = yb
	elif rooms[b].ramp != "" and rooms[a].ramp == "":
		d.y = ya
	else:
		d.y = maxf(ya, yb)
	doors.append(d)
	return d

func doors_from(list: Array) -> void:
	for s in list:
		var parts: PackedStringArray = str(s).split("-")
		door(parts[0], parts[1])

# ------------------------------------------------ сборка геометрии
func finish() -> void:
	for id in rooms:
		_build_room(id)
	for d in doors:
		_build_door(d)
	_build_graph()

func _mesh_box(parent: Node3D, pos: Vector3, size: Vector3, mat: Material, collide := true) -> void:
	if size.x <= 0.001 or size.y <= 0.001 or size.z <= 0.001:
		return
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new(); bm.size = size
	mi.mesh = bm; mi.material_override = mat; mi.position = pos
	parent.add_child(mi)
	if collide:
		var sb := StaticBody3D.new()
		sb.collision_layer = 1; sb.collision_mask = 0
		var cs := CollisionShape3D.new()
		var bs := BoxShape3D.new(); bs.size = size
		cs.shape = bs
		sb.add_child(cs); sb.position = pos
		parent.add_child(sb)

func _openings(room_id: String, axis: String, line: float) -> Array:
	var out := []
	for d in doors:
		if d.axis != axis or absf(d.line - line) > 0.06:
			continue
		if d.a != room_id and d.b != room_id:
			continue
		out.append(d)
	out.sort_custom(func(p, q): return p.center < q.center)
	return out

func _wall_line(parent: Node3D, room_id: String, axis_along: String, fixed: float, from: float, to: float, side_sign: float, r: Dictionary) -> void:
	# axis_along "x": стена вдоль X на z=fixed;  "z": вдоль Z на x=fixed
	var perp := "z" if axis_along == "x" else "x"
	var ops := _openings(room_id, perp, fixed)
	var wm := Mats.tex(r.wall, 0.45, r.wall_tint)
	var y0: float = r.y
	var h: float = r.h
	var cur := from
	for d in ops:
		var lo: float = d.center - d.w / 2.0
		var hi: float = d.center + d.w / 2.0
		_wall_seg(parent, axis_along, fixed, cur, lo, y0, y0 + h, side_sign, wm, true)
		var dy: float = d.y
		if dy > y0 + 0.01:
			_wall_seg(parent, axis_along, fixed, lo, hi, y0, dy, side_sign, wm)
		_wall_seg(parent, axis_along, fixed, lo, hi, dy + DOOR_H, y0 + h, side_sign, wm)
		cur = hi
	_wall_seg(parent, axis_along, fixed, cur, to, y0, y0 + h, side_sign, wm, true)

static var _base_mat: StandardMaterial3D

func _wall_seg(parent: Node3D, axis_along: String, fixed: float, a: float, b: float, ya: float, yb: float, side_sign: float, mat: Material, base := false) -> void:
	if b - a < 0.01 or yb - ya < 0.01:
		return
	var len := b - a
	var t := WALL_T
	var off := side_sign * t / 2.0
	if axis_along == "x":
		_mesh_box(parent, Vector3((a + b) / 2.0, (ya + yb) / 2.0, fixed + off), Vector3(len, yb - ya, t), mat)
	else:
		_mesh_box(parent, Vector3(fixed + off, (ya + yb) / 2.0, (a + b) / 2.0), Vector3(t, yb - ya, len), mat)
	if base and yb - ya > 1.5:
		if _base_mat == null:
			_base_mat = Mats.color(Color(0.16, 0.12, 0.09), 0.5)
		var bo := side_sign * (t + 0.014)
		if axis_along == "x":
			_mesh_box(parent, Vector3((a + b) / 2.0, ya + 0.07, fixed + bo), Vector3(len, 0.14, 0.028), _base_mat, false)
		else:
			_mesh_box(parent, Vector3(fixed + bo, ya + 0.07, (a + b) / 2.0), Vector3(0.028, 0.14, len), _base_mat, false)

func _build_room(id: String) -> void:
	var r: Dictionary = rooms[id]
	var rc: Rect2 = r.rect
	var holder := Node3D.new()
	holder.name = "Room_" + id
	root.add_child(holder)
	r.node = holder
	var y: float = r.y
	var c := rc.get_center()
	# пол и потолок
	var fm := Mats.tex(r.floor, 0.4, r.floor_tint)
	_mesh_box(holder, Vector3(c.x, y - 0.1, c.y), Vector3(rc.size.x, 0.2, rc.size.y), fm)
	_mesh_box(holder, Vector3(c.x, y + r.h + 0.1, c.y), Vector3(rc.size.x, 0.2, rc.size.y), Mats.tex(r.ceil, 0.4, Color(0.7, 0.68, 0.64)))
	# стены (внутрь комнаты)
	_wall_line(holder, id, "x", rc.position.y, rc.position.x, rc.end.x, 1.0, r)    # север
	_wall_line(holder, id, "x", rc.end.y, rc.position.x, rc.end.x, -1.0, r)       # юг
	_wall_line(holder, id, "z", rc.position.x, rc.position.y, rc.end.y, 1.0, r)   # запад
	_wall_line(holder, id, "z", rc.end.x, rc.position.y, rc.end.y, -1.0, r)       # восток
	# рампа лестницы
	if r.ramp != "":
		_build_ramp(holder, r)
	# окна на внешних стенах, потолочная лампа
	if y >= -0.5 and r.ramp == "" and not r.get("nowin", false) and r.h <= 3.6:
		for side in ["N", "S", "W", "E"]:
			if _side_free(id, side):
				_make_window(holder, r, side)
	if r.light > 0.0 and r.ramp == "" and y >= -0.5 and r.h <= 3.6:
		var cl := Props.make("ceilinglamp")
		cl.position = Vector3(c.x, y + r.h - 0.5, c.y)
		holder.add_child(cl)
	# свет
	if r.light > 0.0:
		var li := OmniLight3D.new()
		li.position = Vector3(c.x, y + minf(r.h, 3.0) - 0.35, c.y)
		li.light_color = r.light_color
		li.light_energy = r.light
		li.omni_range = maxf(rc.size.x, rc.size.y) * 0.85 + 2.5
		li.omni_attenuation = 1.3
		li.set_meta("base", r.light)
		li.set_meta("room", id)
		root.add_child(li)
		lights.append(li)
		r.light_node = li

func _side_free(id: String, side: String) -> bool:
	var rc: Rect2 = rooms[id].rect
	var len := rc.size.x if side in ["N", "S"] else rc.size.y
	if len < 6.0:
		return false
	var line := rc.position.y if side == "N" else (rc.end.y if side == "S" else (rc.position.x if side == "W" else rc.end.x))
	var axis := "z" if side in ["N", "S"] else "x"
	for d in doors:
		if (d.a == id or d.b == id) and d.axis == axis and absf(d.line - line) < 0.06:
			return false
	for oid in rooms:
		if oid == id:
			continue
		var o: Rect2 = rooms[oid].rect
		if side in ["N", "S"]:
			if absf((o.end.y if side == "N" else o.position.y) - line) < 0.06 and minf(o.end.x, rc.end.x) - maxf(o.position.x, rc.position.x) > 0.5:
				return false
		else:
			if absf((o.end.x if side == "W" else o.position.x) - line) < 0.06 and minf(o.end.y, rc.end.y) - maxf(o.position.y, rc.position.y) > 0.5:
				return false
	return true

func _make_window(holder: Node3D, r: Dictionary, side: String) -> void:
	var rc: Rect2 = r.rect
	var pos := wp(r.id, side, 0.5, 0.0, 0.0)
	var n := Node3D.new()
	var inner := WALL_T + 0.01
	n.position = pos + side_normal(side) * inner + Vector3(0, r.y + 1.0, 0)
	n.position.y = r.y + 1.0
	n.rotation_degrees.y = side_yaw(side)
	holder.add_child(n)
	var fr := Mats.color(Color(0.55, 0.5, 0.42), 0.6)
	var w := 1.3; var h := 1.3
	Props.box(n, Vector3(w, h, 0.02), Vector3(0, h / 2, 0.0), Mats.color(Color(0.05, 0.07, 0.13), 0.1, 0.8))
	for sx in [-1, 1]:
		Props.box(n, Vector3(0.07, h + 0.1, 0.06), Vector3(sx * (w / 2 + 0.03), h / 2, 0.03), fr)
	Props.box(n, Vector3(w + 0.2, 0.07, 0.07), Vector3(0, h + 0.04, 0.03), fr)
	Props.box(n, Vector3(w + 0.26, 0.06, 0.12), Vector3(0, -0.02, 0.05), fr)
	Props.box(n, Vector3(0.04, h, 0.03), Vector3(0, h / 2, 0.02), fr)
	Props.box(n, Vector3(w, 0.04, 0.03), Vector3(0, h / 2, 0.02), fr)
	var curt := Mats.tex("fabric", 1.2, Color(0.4, 0.15, 0.17), 1.0)
	for sx2 in [-1, 1]:
		Props.box(n, Vector3(0.32, h + 0.5, 0.07), Vector3(sx2 * (w / 2 + 0.2), h / 2 + 0.1, 0.07), curt)
	var li := OmniLight3D.new()
	li.position = Vector3(0, h / 2, 0.8)
	li.light_color = Color(0.5, 0.6, 1.0)
	li.light_energy = 0.35
	li.omni_range = 4.0
	n.add_child(li)

func _build_ramp(holder: Node3D, r: Dictionary) -> void:
	var rc: Rect2 = r.rect
	var rise: float = r.rise
	var dir: String = r.ramp
	var along := rc.size.x if dir.begins_with("x") else rc.size.y
	var ang := atan2(rise, along)
	var length := sqrt(along * along + rise * rise)
	var width := rc.size.y if dir.begins_with("x") else rc.size.x
	var c := rc.get_center()
	var thick := 0.2
	var sb := StaticBody3D.new()
	sb.collision_layer = 1; sb.collision_mask = 0
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new(); bs.size = Vector3(length, thick, width - 0.2)
	cs.shape = bs
	sb.add_child(cs)
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new(); bm.size = Vector3(length, thick, width - 0.2)
	mi.mesh = bm; mi.material_override = Mats.tex("floor_dark", 0.6, Color(0.6, 0.55, 0.5))
	sb.add_child(mi)
	var y: float = r.y
	sb.position = Vector3(c.x, y + rise / 2.0 - thick / 2.0 / cos(ang), c.y)
	match dir:
		"x+": sb.rotation = Vector3(0, 0, ang)
		"x-": sb.rotation = Vector3(0, 0, -ang)
		"z+": sb.rotation = Vector3(0, -PI / 2.0, ang)
		"z-": sb.rotation = Vector3(0, -PI / 2.0, -ang)
	holder.add_child(sb)

func _build_door(d: Dictionary) -> void:
	var opts: Dictionary = d.opts
	if opts.get("open_hole", false):
		return
	var dr := Door.new()
	var y: float = d.y
	var w: float = d.w
	var mat := Mats.tex("wood", 0.8, opts.get("tint", Color(0.6, 0.48, 0.38)))
	dr.setup(w - 0.04, DOOR_H - 0.04, mat, opts.get("flip", 1.0))
	dr.a_id = d.a; dr.b_id = d.b
	if d.axis == "x":
		dr.position = Vector3(d.line, y, d.center - (w / 2.0 - 0.02) * opts.get("flip", 1.0))
		dr.rotation.y = PI / 2.0
		dr.base_yaw = rad_to_deg(PI / 2.0)
		dr.rotation_degrees.y = dr.base_yaw
	else:
		dr.position = Vector3(d.center - (w / 2.0 - 0.02) * opts.get("flip", 1.0), y, d.line)
	root.add_child(dr)
	if opts.get("locked", false):
		dr.set_locked(true, opts.get("key", ""))
	if opts.get("jammed", false):
		dr.jammed = true
		dr._update_prompt()
	if opts.get("open", false):
		dr.set_open(true)
	d.node = dr
	# наличники
	var fm := Mats.color(Color(0.85, 0.82, 0.75), 0.8)
	var along := Vector3(0, 0, 1) if d.axis == "x" else Vector3(1, 0, 0)
	var thick := Vector3(0.3, 1, 1) if d.axis == "x" else Vector3(1, 1, 0.3)
	var cpos := Vector3(d.line, y, d.center) if d.axis == "x" else Vector3(d.center, y, d.line)
	_mesh_box(root, cpos + Vector3(0, DOOR_H + 0.03, 0), Vector3(0.28 if d.axis == "x" else w + 0.1, 0.06, w + 0.1 if d.axis == "x" else 0.28), fm, false)
	for s in [-1, 1]:
		var off: Vector3 = along * (w / 2.0 + 0.025) * s
		_mesh_box(root, cpos + off + Vector3(0, DOOR_H / 2.0, 0), Vector3(0.28 if d.axis == "x" else 0.05, DOOR_H, 0.05 if d.axis == "x" else 0.28), fm, false)

# ------------------------------------------------ навигационный граф (для монстров)
func _add_node(key: String, p: Vector3) -> int:
	var i := graph.get_available_point_id()
	graph.add_point(i, p)
	graph_ids[key] = i
	return i

func _build_graph() -> void:
	for id in rooms:
		var r: Dictionary = rooms[id]
		if r.ramp == "":
			_add_node("r_" + id, room_center(id) + Vector3(0, 0.1, 0))
		else:
			var rc: Rect2 = r.rect
			var c := rc.get_center()
			var d: String = r.ramp
			var lo := Vector3(c.x, r.y + 0.1, c.y)
			var hi := Vector3(c.x, r.y + r.rise + 0.1, c.y)
			var half := (rc.size.x if d.begins_with("x") else rc.size.y) / 2.0 - 0.7
			var sign := 1.0 if d.ends_with("+") else -1.0
			if d.begins_with("x"):
				lo.x -= sign * half; hi.x += sign * half
			else:
				lo.z -= sign * half; hi.z += sign * half
			lo.y = r.y + 0.1; hi.y = r.y + r.rise + 0.1
			var a := _add_node("r_" + id + "_lo", lo)
			var b := _add_node("r_" + id + "_hi", hi)
			graph.connect_points(a, b)
	for i in doors.size():
		var d: Dictionary = doors[i]
		var p := Vector3(d.line, d.y + 0.1, d.center) if d.axis == "x" else Vector3(d.center, d.y + 0.1, d.line)
		var n := _add_node("d_%d" % i, p)
		d.gid = n
		for rid in [d.a, d.b]:
			var rr: Dictionary = rooms[rid]
			if rr.ramp == "":
				graph.connect_points(n, graph_ids["r_" + rid])
			else:
				var lo_id: int = graph_ids["r_" + rid + "_lo"]
				var hi_id: int = graph_ids["r_" + rid + "_hi"]
				var nearest := lo_id if graph.get_point_position(lo_id).distance_to(p) < graph.get_point_position(hi_id).distance_to(p) else hi_id
				graph.connect_points(n, nearest)

func find_path(from: Vector3, to: Vector3) -> PackedVector3Array:
	var a := graph.get_closest_point(from)
	var b := graph.get_closest_point(to)
	var pts := graph.get_point_path(a, b)
	return pts

## Позиция в комнате по долям (fx, fz от 0 до 1) на уровне пола.
func P(room_id: String, fx: float, fz: float, dy := 0.0) -> Vector3:
	var r: Dictionary = rooms[room_id]
	var rc: Rect2 = r.rect
	return Vector3(rc.position.x + fx * rc.size.x, r.y + dy, rc.position.y + fz * rc.size.y)

## Позиция у стены: side N/S/W/E, frac вдоль стены, inset от стены (м).
func wp(room_id: String, side: String, frac: float, inset := 0.3, dy := 0.0) -> Vector3:
	var r: Dictionary = rooms[room_id]
	var rc: Rect2 = r.rect
	var t := WALL_T
	match side:
		"N": return Vector3(rc.position.x + frac * rc.size.x, r.y + dy, rc.position.y + t + inset)
		"S": return Vector3(rc.position.x + frac * rc.size.x, r.y + dy, rc.end.y - t - inset)
		"W": return Vector3(rc.position.x + t + inset, r.y + dy, rc.position.y + frac * rc.size.y)
		_:   return Vector3(rc.end.x - t - inset, r.y + dy, rc.position.y + frac * rc.size.y)

## Направление «лицом в комнату» для объекта у стены.
static func side_yaw(side: String) -> float:
	match side:
		"N": return 0.0
		"S": return 180.0
		"W": return 90.0
		_:   return -90.0

func against(kind: String, room_id: String, side: String, frac: float, opts := {}, inset := 0.3) -> Node3D:
	var pos := wp(room_id, side, frac, inset)
	return prop(kind, pos, side_yaw(side), opts)

## Нормаль «лицом в комнату» для настенного пятна.
static func side_normal(side: String) -> Vector3:
	match side:
		"N": return Vector3(0, 0, 1)
		"S": return Vector3(0, 0, -1)
		"W": return Vector3(1, 0, 0)
		_:   return Vector3(-1, 0, 0)

func wall_dirt(kind: String, room_id: String, side: String, frac: float, height: float, size := Vector2(1, 1), task_id := "", opts := {}) -> DirtPatch:
	var pos := wp(room_id, side, frac, 0.0, height)
	pos += side_normal(side) * (WALL_T + 0.005)
	return dirt(kind, pos, size, side_normal(side), task_id, opts)

func random_room() -> String:
	var keys := rooms.keys()
	return keys[randi() % keys.size()]

# ------------------------------------------------ объекты
const NO_KEEPOUT := ["rug", "picture", "mirror", "clock", "paper", "key", "phone", "tape", "badge", "teddy", "window", "candle", "bag", "radio", "lamp_fix", "bars"]

func prop(kind: String, pos: Vector3, yaw := 0.0, opts := {}) -> Node3D:
	var n := Props.make(kind, opts)
	n.position = pos
	n.rotation_degrees.y = yaw
	root.add_child(n)
	if not (kind in NO_KEEPOUT) and not opts.get("keep", false):
		_clear_doors(n)
	return n

func _prop_radius(n: Node3D) -> float:
	if n.has_meta("size"):
		var sz: Vector3 = n.get_meta("size")
		return maxf(sz.x, sz.z) * 0.5
	for c in n.get_children():
		if c is StaticBody3D:
			for cc in c.get_children():
				if cc is CollisionShape3D and cc.shape is BoxShape3D:
					var b: Vector3 = cc.shape.size
					return maxf(b.x, b.z) * 0.5
	return 0.3

## Не даём мебели перекрывать дверные проёмы: сдвигаем вдоль стены.
func _clear_doors(n: Node3D) -> void:
	var r := _prop_radius(n)
	for iter in 60:
		var moved := false
		for d in doors:
			var along := n.position.z if d.axis == "x" else n.position.x
			var across := n.position.x if d.axis == "x" else n.position.z
			var half: float = d.w / 2.0 + 0.45 + r
			var depth: float = 1.5 + r
			if absf(across - d.line) < depth and absf(along - d.center) < half and absf(n.position.y - d.y) < 3.0:
				var sgn := 1.0 if along >= d.center else -1.0
				if d.axis == "x":
					n.position.z += sgn * 0.2
				else:
					n.position.x += sgn * 0.2
				moved = true
		if not moved:
			return

func lamp_light(pos: Vector3, color := Color(1, 0.8, 0.5), energy := 0.8, rng := 5.0) -> OmniLight3D:
	var li := OmniLight3D.new()
	li.position = pos
	li.light_color = color; li.light_energy = energy; li.omni_range = rng
	li.set_meta("base", energy)
	root.add_child(li)
	lights.append(li)
	return li

func interact(pos: Vector3, size: Vector3, prompt: String, cb: Callable, opts := {}) -> Interactable:
	var it := Interactable.new()
	it.prompt = prompt
	it.callback = cb
	it.once = opts.get("once", false)
	it.id = opts.get("id", "")
	it.collision_layer = opts.get("layer", 2)
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new(); bs.size = size
	cs.shape = bs
	it.add_child(cs)
	it.position = pos
	root.add_child(it)
	return it

func task(id: String, text: String, opts := {}) -> void:
	tasks[id] = {"id": id, "text": text, "patches": [], "optional": opts.get("optional", false),
		"manual": opts.get("manual", false), "done": false, "hidden": opts.get("hidden", false), "count": 0, "need": opts.get("need", 0)}
	task_order.append(id)

func dirt(kind: String, pos: Vector3, size := Vector2(1, 1), normal := Vector3.UP, task_id := "", opts := {}) -> DirtPatch:
	var p := DirtPatch.new()
	p.patch_id = opts.get("id", "p%d" % _patch_n)
	_patch_n += 1
	p.task_id = task_id
	p.story = opts.get("story", false)
	root.add_child(p)
	p.setup(kind, size, normal)
	p.position = pos
	patches[p.patch_id] = p
	if task_id != "" and tasks.has(task_id):
		tasks[task_id].patches.append(p)
	return p

func floor_dirt(kind: String, room_id: String, off: Vector2, size: Vector2, task_id := "", opts := {}) -> DirtPatch:
	var c := room_center(room_id)
	return dirt(kind, Vector3(c.x + off.x, rooms[room_id].y + 0.02, c.z + off.y), size, Vector3.UP, task_id, opts)

func hide_spot(pos: Vector3, yaw: float, label := "Спрятаться") -> Interactable:
	var it := interact(pos, Vector3(1.0, 1.9, 1.1), label, Callable(), {"layer": 2})
	it.rotation_degrees.y = yaw
	it.set_meta("hide", true)
	it.set_meta("hide_pos", pos)
	it.set_meta("hide_yaw", yaw)
	it.callback = func(p): p.enter_hide(it)
	hide_spots.append(it)
	return it

func trigger(pos: Vector3, size: Vector3, cb: Callable, once := true) -> Area3D:
	var a := Area3D.new()
	a.collision_layer = 0
	a.collision_mask = 16
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new(); bs.size = size
	cs.shape = bs
	a.add_child(cs)
	a.position = pos
	root.add_child(a)
	var fired := [false]
	a.body_entered.connect(func(b):
		if b == Game.player and not (once and fired[0]):
			fired[0] = true
			cb.call())
	return a

func note_pickup(id: String, pos: Vector3, yaw := 0.0, tint := Color(0.92, 0.9, 0.82)) -> Node3D:
	var n := Props.make("paper", {"c": tint})
	n.position = pos
	n.rotation_degrees.y = yaw
	root.add_child(n)
	var it := Interactable.new()
	it.prompt = "Прочитать записку"
	it.collision_layer = 2
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new(); bs.size = Vector3(0.45, 0.25, 0.5)
	cs.shape = bs
	it.add_child(cs)
	it.position = Vector3(0, 0.05, 0)
	n.add_child(it)
	it.callback = func(p):
		level.read_note(id)
		if is_instance_valid(n):
			pass
	it.id = id
	notes_nodes[id] = {"node": n, "it": it}
	return n

func spawn_monster(type: String, pos: Vector3, opts := {}) -> Node:
	var m: Node = level.make_monster(type, pos, opts)
	monsters.append(m)
	return m
