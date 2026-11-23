extends Node
## «Режиссёр страха»: решает когда и какое событие запускать, соблюдая паузы и лимиты.

var level: Level
var paused := true
var tension := 0.0
var threshold := 50.0
var cd_small := 25.0
var cd_med := 70.0
var cd_big := 240.0
var since_small := 0.0
var since_med := 0.0
var since_big := 0.0
var recent: Array = []
var t_total := 0.0
var rng := RandomNumberGenerator.new()
var forced_quiet := 0.0

func start(lv: Level) -> void:
	level = lv
	paused = false
	tension = 0.0
	threshold = rng.randf_range(40.0, 70.0)
	since_small = 0.0; since_med = 0.0; since_big = 0.0
	forced_quiet = 35.0
	rng.randomize()

func quiet(seconds: float) -> void:
	forced_quiet = maxf(forced_quiet, seconds)

func _process(delta: float) -> void:
	if level == null or not is_instance_valid(level) or paused or level.ended or level.gameplay_locked or level.player.frozen:
		return
	since_small += delta; since_med += delta; since_big += delta
	forced_quiet = maxf(0.0, forced_quiet - delta)
	var info: Dictionary = Story.CHAPTERS[level.chapter]
	var rate: float = info.get("tension", 1.0)
	if Game.sanity < 40.0:
		rate *= 1.8
	# рост напряжения; во время погони тихо
	if level._any_monster_chasing():
		tension = 0.0
		return
	tension += delta * rate * (1.0 + level.progress())
	if forced_quiet > 0.0 or tension < threshold:
		return
	_fire(info)

func _fire(info: Dictionary) -> void:
	var ev: Dictionary = info.get("events", {})
	var roll := rng.randf()
	var cls := "small"
	if roll > 0.93 and since_big > cd_big and ev.get("big", []).size() > 0 and level.chapter >= 2:
		cls = "big"
	elif roll > 0.55 and since_med > cd_med and ev.get("medium", []).size() > 0:
		cls = "medium"
	elif since_small < cd_small:
		return
	var pool: Array = ev.get(cls, [])
	if pool.is_empty():
		return
	var choices := pool.filter(func(n): return not (n in recent))
	if choices.is_empty():
		choices = pool
	var name: String = choices[rng.randi() % choices.size()]
	if not has_method("ev_" + name):
		return
	call("ev_" + name)
	recent.append(name)
	if recent.size() > 5:
		recent.pop_front()
	tension = 0.0
	threshold = rng.randf_range(40.0, 75.0)
	match cls:
		"small": since_small = 0.0
		"medium": since_med = 0.0; since_small = 0.0
		"big": since_big = 0.0; since_med = 0.0; since_small = 0.0; forced_quiet = 50.0

func force(name: String) -> void:
	if has_method("ev_" + name):
		call("ev_" + name)

# ------------------------------------------------ вспомогательное
func _ppos() -> Vector3:
	return level.player.global_position

func _behind(dist: float) -> Vector3:
	var back := level.player.global_transform.basis.z
	back.y = 0
	return _ppos() + back.normalized() * dist

func _random_room_pos(far := true) -> Vector3:
	var best := Vector3.ZERO
	var tries := 8
	for i in tries:
		var id := level.b.random_room()
		var p := level.b.room_center(id)
		if far and p.distance_to(_ppos()) < 6.0:
			continue
		best = p
		break
	return best if best != Vector3.ZERO else _ppos() + Vector3(5, 0, 0)

# ------------------------------------------------ малые события
func ev_flicker() -> void:
	var lights := level.b.lights.filter(func(l): return l.get_meta("room", "") == level.cur_room)
	if lights.is_empty():
		return
	Audio.sfx("light_buzz", _ppos())
	var l: OmniLight3D = lights[0]
	var base: float = l.get_meta("base", 1.0)
	var tw := create_tween()
	for i in 7:
		tw.tween_property(l, "light_energy", rng.randf_range(0.0, base * 0.3), 0.06)
		tw.tween_property(l, "light_energy", base, 0.08)
	Game.sanity -= 2.0

func ev_whisper() -> void:
	Audio.sfx_rand("whisper", 3, _behind(2.0), 3.0)
	Game.sanity -= 3.0

func ev_steps_far() -> void:
	Audio.sfx("steps_far", _random_room_pos(), 2.0)

func ev_knock() -> void:
	var near: Door = null
	var bd := 1e9
	for d in level.b.doors:
		var n: Door = d.get("node")
		if n and not n.is_open:
			var dd := n.global_position.distance_to(_ppos())
			if dd < bd and dd > 2.0:
				bd = dd; near = n
	Audio.sfx("knock", near.global_position if near else _random_room_pos(), 4.0)
	Game.sanity -= 2.0

func ev_creak() -> void:
	Audio.sfx("creak", _random_room_pos(false), 0.0)

func ev_breath() -> void:
	Audio.sfx("breath", _behind(1.2), 2.0)
	Game.sanity -= 3.0

func ev_laugh() -> void:
	Audio.sfx("child_laugh", _random_room_pos(), 3.0)
	Game.sanity -= 2.0

func ev_radio_static() -> void:
	Audio.sfx("radio_static", _random_room_pos(false), 2.0)

func ev_cold() -> void:
	Game.note("Стало холодно. Слышно чьё-то дыхание.")
	Audio.sfx("breath", _behind(1.0), -2.0)
	Game.sanity -= 4.0

func ev_drip() -> void:
	Audio.sfx("drip", _random_room_pos(false), 2.0)

func ev_thump() -> void:
	Audio.sfx("thump", _random_room_pos(), 6.0)
	level.player.shake(0.006, 0.3)

# ------------------------------------------------ средние события
func ev_door_slam() -> void:
	var cands: Array = []
	for d in level.b.doors:
		var n: Door = d.get("node")
		if n and n.is_open and n.global_position.distance_to(_ppos()) < 14.0 and n.global_position.distance_to(_ppos()) > 2.5 and not n.jammed:
			cands.append(n)
	if cands.is_empty():
		ev_knock()
		return
	var n: Door = cands[rng.randi() % cands.size()]
	n.set_open(false, true)
	level.player.shake(0.01, 0.3)
	Game.sanity -= 3.0

func ev_lights_out() -> void:
	Audio.sfx("power_down", null, 0.0)
	var saved := []
	for l in level.b.lights:
		saved.append([l, l.light_energy])
		l.light_energy = 0.0
	Game.sanity -= 4.0
	await get_tree().create_timer(rng.randf_range(2.5, 4.5)).timeout
	if not is_instance_valid(level):
		return
	for s in saved:
		if is_instance_valid(s[0]):
			s[0].light_energy = s[0].get_meta("base", 1.0)
	Audio.sfx("power_up", null, -2.0)

func ev_phantom() -> void:
	if level.b.rooms.size() < 2:
		return
	var dir := -level.player.global_transform.basis.z
	var p := _ppos() + dir * rng.randf_range(6.0, 9.0)
	p.y = level.b.rooms.get(level.cur_room, {"y": 0.0}).y
	var m := level.make_monster("phantom", p, {"model": "shadow", "life": 6.0, "vanish_after": 0.9})
	Audio.sfx("sting_soft", null, -4.0)

func ev_phantom_child() -> void:
	var p := _random_room_pos()
	var m := level.make_monster("phantom", p, {"model": "child", "life": 6.0, "vanish_after": 0.8})
	Audio.sfx("child_laugh", p, 2.0)

func ev_fake_sms() -> void:
	Audio.sfx("sms", null, 0.0)
	var texts := ["СМС: «Я уже в доме»", "СМС: «Ты хорошо убираешь»", "СМС: «Не оборачивайся»", "СМС: «Оплата по факту»", "СМС: «Мы ждём»"]
	Game.note(texts[rng.randi() % texts.size()])
	Game.sanity -= 4.0

func ev_tv_on() -> void:
	Audio.sfx("radio_static", level.player.global_position + Vector3(0, 0, 3), 0.0)
	Game.sanity -= 2.0
	level.hud.glitch(0.4)

# ------------------------------------------------ большие события
func ev_shadow_behind() -> void:
	var p := _behind(2.2)
	p.y = level.b.rooms.get(level.cur_room, {"y": 0.0}).y
	level.make_monster("phantom", p, {"model": "shadow", "life": 4.0, "vanish_after": 0.35, "sanity": 10.0})
	Audio.sfx("sting", null, -2.0)
	level.hud.flash_screen(0.25)
	level.player.shake(0.02, 0.5)

func ev_scream() -> void:
	Audio.sfx("scream_far", _random_room_pos(), 4.0)
	Game.sanity -= 8.0
	level.hud.glitch(0.8)

func ev_face_flash() -> void:
	var dir := -level.player.global_transform.basis.z
	var p := _ppos() + dir * 2.6
	p.y = level.b.rooms.get(level.cur_room, {"y": 0.0}).y
	level.make_monster("phantom", p, {"model": "host", "life": 1.3, "vanish_after": 0.2, "sanity": 8.0})
	Audio.sfx("sting", null, 0.0)
	level.hud.flash_screen(0.5)
	level.hud.glitch(1.0)
	Game.sanity -= 6.0
