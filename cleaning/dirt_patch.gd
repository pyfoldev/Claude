class_name DirtPatch extends Node3D
## Пятно грязи. amount 1 -> 0 при чистке подходящим инструментом.

signal cleaned(patch)
signal progressed(patch, amount)

const KINDS := {
	"dust":   {"tools": ["rag"], "color": Color(0.45, 0.42, 0.36), "opacity": 0.75, "speed": 0.55, "name": "пыль"},
	"stain":  {"tools": ["mop"], "color": Color(0.22, 0.15, 0.10), "opacity": 0.88, "speed": 0.45, "name": "пятно"},
	"mud":    {"tools": ["mop"], "color": Color(0.17, 0.12, 0.08), "opacity": 0.9, "speed": 0.5, "name": "грязь"},
	"crumbs": {"tools": ["vacuum"], "color": Color(0.30, 0.25, 0.18), "opacity": 0.9, "speed": 0.7, "name": "крошки"},
	"debris": {"tools": ["broom", "vacuum"], "color": Color(0, 0, 0), "opacity": 0.0, "speed": 0.55, "name": "мусор"},
	"blood":  {"tools": ["spray"], "color": Color(0.36, 0.02, 0.02), "opacity": 0.95, "speed": 0.35, "name": "кровь"},
	"glass":  {"tools": ["spray", "rag"], "color": Color(0.5, 0.52, 0.5), "opacity": 0.7, "speed": 0.5, "name": "разводы"},
	"grime":  {"tools": ["spray", "mop"], "color": Color(0.03, 0.03, 0.04), "opacity": 0.97, "speed": 0.35, "name": "чёрная жижа"},
}
static var noise_tex: NoiseTexture2D

var kind := "dust"
var amount := 1.0
var task_id := ""
var patch_id := ""
var size := Vector2(1, 1)
var story := false          # сюжетное пятно (после очистки событие)
var mat: ShaderMaterial
var body: StaticBody3D
var bits: Array = []
var done := false

static func _get_noise() -> NoiseTexture2D:
	if noise_tex == null:
		var fn := FastNoiseLite.new()
		fn.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
		fn.frequency = 0.02
		fn.fractal_octaves = 3
		noise_tex = NoiseTexture2D.new()
		noise_tex.noise = fn
		noise_tex.width = 256
		noise_tex.height = 256
		noise_tex.seamless = true
	return noise_tex

## orient: Vector3 нормаль поверхности (вверх для пола).
func setup(k: String, sz: Vector2, normal: Vector3) -> void:
	kind = k
	size = sz
	var info: Dictionary = KINDS[k]
	var up := normal.normalized()
	# базис: нормаль = Y
	var basis_y := up
	var basis_x := Vector3.RIGHT if absf(up.dot(Vector3.RIGHT)) < 0.9 else Vector3.FORWARD
	basis_x = (basis_x - up * basis_x.dot(up)).normalized()
	var basis_z := basis_x.cross(basis_y).normalized()
	basis = Basis(basis_x, basis_y, basis_z)
	if k == "debris":
		_make_debris()
	else:
		var q := QuadMesh.new()
		q.size = sz
		q.orientation = PlaneMesh.FACE_Y
		var mi := MeshInstance3D.new()
		mi.mesh = q
		mi.position = Vector3(0, 0.012, 0)
		mat = ShaderMaterial.new()
		mat.shader = load("res://shaders/dirt.gdshader")
		mat.set_shader_parameter("noise_tex", _get_noise())
		mat.set_shader_parameter("dirt_color", info.color)
		mat.set_shader_parameter("opacity", info.opacity)
		mat.set_shader_parameter("seed", randf() * 10.0)
		mat.set_shader_parameter("emit_amount", 0.0)
		mi.material_override = mat
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(mi)
	body = StaticBody3D.new()
	body.collision_layer = 4
	body.collision_mask = 0
	body.set_meta("patch", self)
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = Vector3(sz.x, 0.25, sz.y)
	cs.shape = bs
	cs.position = Vector3(0, 0.05, 0)
	body.add_child(cs)
	add_child(body)

func _make_debris() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = hash(str(get_instance_id())) + 7
	var n := int(clampf(size.x * size.y * 10.0, 6, 22))
	var cols := [Color(0.35, 0.3, 0.22), Color(0.5, 0.45, 0.35), Color(0.18, 0.16, 0.14), Color(0.55, 0.5, 0.4)]
	for i in n:
		var m := MeshInstance3D.new()
		var b := BoxMesh.new()
		b.size = Vector3(rng.randf_range(0.04, 0.14), rng.randf_range(0.015, 0.05), rng.randf_range(0.04, 0.12))
		m.mesh = b
		var sm := StandardMaterial3D.new()
		sm.albedo_color = cols[rng.randi() % cols.size()]
		sm.roughness = 1.0
		m.material_override = sm
		m.position = Vector3(rng.randf_range(-size.x, size.x) * 0.45, 0.02, rng.randf_range(-size.y, size.y) * 0.45)
		m.rotation = Vector3(rng.randf_range(-0.3, 0.3), rng.randf() * TAU, rng.randf_range(-0.3, 0.3))
		add_child(m)
		bits.append(m)

func required_tools() -> Array:
	return KINDS[kind].tools

func name_ru() -> String:
	return KINDS[kind].name

func clean(tool_id: String, delta: float, power := 1.0) -> bool:
	if done:
		return false
	if not (tool_id in required_tools()):
		return false
	var sp: float = KINDS[kind].speed * power
	if tool_id == "rag" and kind == "glass":
		sp *= 0.6
	var before := amount
	amount = maxf(0.0, amount - delta * sp / maxf(0.5, sqrt(size.x * size.y) * 0.9))
	_apply()
	if amount != before:
		progressed.emit(self, amount)
	if amount <= 0.001:
		done = true
		cleaned.emit(self)
		if body:
			body.queue_free()
			body = null
	return true

func set_amount(a: float) -> void:
	amount = a
	if a <= 0.001:
		done = true
		if body:
			body.queue_free(); body = null
	_apply()

func _apply() -> void:
	if mat:
		mat.set_shader_parameter("amount", amount)
	if not bits.is_empty():
		var vis := int(ceil(amount * bits.size()))
		for i in bits.size():
			bits[i].visible = i < vis

## Сделать пятно «проклятым» — слабо светится.
func glow(v: float) -> void:
	if mat:
		mat.set_shader_parameter("emit_amount", v)
