class_name Mats extends RefCounted
## Кэш материалов. Текстуры — Poly Haven (CC0), триплplanar в мировых координатах.

static var _cache: Dictionary = {}
static var _tex: Dictionary = {}

static func tex(key: String, scale := 0.5, tint := Color(1, 1, 1), rough := 0.92) -> StandardMaterial3D:
	var ck := "t|%s|%s|%s|%s" % [key, scale, tint.to_html(), rough]
	if _cache.has(ck):
		return _cache[ck]
	var m := StandardMaterial3D.new()
	var path := "res://assets/tex/%s.jpg" % key
	if not _tex.has(path):
		_tex[path] = load(path) if ResourceLoader.exists(path) else null
	if _tex[path]:
		m.albedo_texture = _tex[path]
	m.albedo_color = tint
	m.roughness = rough
	m.uv1_triplanar = true
	m.uv1_world_triplanar = true
	m.uv1_scale = Vector3(scale, scale, scale)
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS
	_cache[ck] = m
	return m

static func color(c: Color, rough := 0.85, emit := 0.0, metallic := 0.0) -> StandardMaterial3D:
	var ck := "c|%s|%s|%s|%s" % [c.to_html(), rough, emit, metallic]
	if _cache.has(ck):
		return _cache[ck]
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = rough
	m.metallic = metallic
	if emit > 0.0:
		m.emission_enabled = true
		m.emission = c
		m.emission_energy_multiplier = emit
	_cache[ck] = m
	return m

static func glass(c := Color(0.3, 0.4, 0.5, 0.35)) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.roughness = 0.05
	m.metallic = 0.6
	return m
