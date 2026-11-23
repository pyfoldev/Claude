extends Node
## Звук: шины, SFX, голос с субтитрами, музыка, петли.

signal subtitle(speaker: String, text: String, duration: float)
signal subtitle_end

var _cache: Dictionary = {}
var _loops: Dictionary = {}
var _voice: AudioStreamPlayer
var _music: AudioStreamPlayer
var _music2: AudioStreamPlayer
var _music_name := ""
var _vo_queue: Array = []
var _vo_busy := false
var _lowpass: AudioEffectLowPassFilter

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for b in ["SFX", "Voice", "Music", "Ambience", "UI"]:
		if AudioServer.get_bus_index(b) == -1:
			AudioServer.add_bus()
			var i := AudioServer.bus_count - 1
			AudioServer.set_bus_name(i, b)
			AudioServer.set_bus_send(i, "Master")
	var rv := AudioEffectReverb.new()
	rv.room_size = 0.55; rv.wet = 0.18; rv.damping = 0.6
	AudioServer.add_bus_effect(AudioServer.get_bus_index("SFX"), rv)
	_lowpass = AudioEffectLowPassFilter.new()
	_lowpass.cutoff_hz = 20000
	AudioServer.add_bus_effect(0, _lowpass)
	_voice = _mk_player("Voice")
	_voice.finished.connect(_on_voice_done)
	_music = _mk_player("Music")
	_music2 = _mk_player("Music")
	apply_volumes()

func _mk_player(bus: String) -> AudioStreamPlayer:
	var p := AudioStreamPlayer.new()
	p.bus = bus
	add_child(p)
	return p

func apply_volumes() -> void:
	var s: Dictionary = Game.settings
	AudioServer.set_bus_volume_db(0, linear_to_db(maxf(0.001, float(s.vol_master))))
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index("Music"), linear_to_db(maxf(0.001, float(s.vol_music))))
	AudioServer.set_bus_volume_db(AudioServer.get_bus_index("Voice"), linear_to_db(maxf(0.001, float(s.vol_voice))))

## Приглушение звука при низком рассудке (0..1)
func set_muffle(amount: float) -> void:
	_lowpass.cutoff_hz = lerpf(20000.0, 1400.0, clampf(amount, 0.0, 1.0))

func _load(path: String) -> AudioStream:
	if _cache.has(path):
		return _cache[path]
	var st: AudioStream = null
	if ResourceLoader.exists(path):
		st = load(path)
	_cache[path] = st
	return st

func sfx(name: String, pos = null, vol_db := 0.0, pitch := 1.0, bus := "SFX") -> void:
	var st := _load("res://audio/sfx/%s.ogg" % name)
	if st == null:
		return
	var parent: Node = Game.level if Game.level else self
	if pos is Vector3 and Game.level:
		var p := AudioStreamPlayer3D.new()
		p.stream = st; p.volume_db = vol_db; p.pitch_scale = pitch; p.bus = bus
		p.unit_size = 4.0; p.max_distance = 40.0
		parent.add_child(p)
		p.global_position = pos
		p.finished.connect(p.queue_free)
		p.play()
	else:
		var p2 := AudioStreamPlayer.new()
		p2.stream = st; p2.volume_db = vol_db; p2.pitch_scale = pitch; p2.bus = bus
		add_child(p2)
		p2.finished.connect(p2.queue_free)
		p2.play()

func sfx_rand(base: String, n: int, pos = null, vol_db := 0.0) -> void:
	sfx("%s%d" % [base, randi_range(1, n)], pos, vol_db, randf_range(0.93, 1.07))

func loop(name: String, vol_db := 0.0, bus := "Ambience") -> void:
	if _loops.has(name):
		_loops[name].volume_db = vol_db
		if not _loops[name].playing:
			_loops[name].play()
		return
	var st := _load("res://audio/sfx/%s.ogg" % name)
	if st == null:
		return
	if st is AudioStreamOggVorbis:
		st = st.duplicate()
		st.loop = true
	var p := AudioStreamPlayer.new()
	p.stream = st; p.bus = bus; p.volume_db = vol_db
	add_child(p)
	p.play()
	_loops[name] = p

func loop_set(name: String, vol_db: float) -> void:
	if _loops.has(name):
		_loops[name].volume_db = vol_db

func loop_stop(name: String) -> void:
	if _loops.has(name):
		_loops[name].stop()

func stop_all_loops() -> void:
	for k in _loops:
		_loops[k].queue_free()
	_loops.clear()
	_vo_queue.clear()
	_voice.stop()
	_vo_busy = false
	subtitle_end.emit()
	_music.stop(); _music2.stop(); _music_name = ""

func music(name: String, vol_db := -6.0) -> void:
	if name == _music_name:
		return
	_music_name = name
	var st := _load("res://audio/music/%s.ogg" % name)
	var old := _music
	var nw := _music2
	_music = nw; _music2 = old
	if st:
		if st is AudioStreamOggVorbis:
			st = st.duplicate(); st.loop = true
		nw.stream = st; nw.volume_db = -40.0; nw.play()
		create_tween().tween_property(nw, "volume_db", vol_db, 3.0)
	if old.playing:
		var t := create_tween()
		t.tween_property(old, "volume_db", -50.0, 3.0)
		t.tween_callback(old.stop)

## Голосовая реплика. id из strings_ru.json. Возвращает длительность.
func say(id: String, priority := false) -> void:
	if priority:
		_vo_queue.clear()
		_voice.stop()
		_vo_busy = false
	_vo_queue.append(id)
	if not _vo_busy:
		_next_vo()

func _next_vo() -> void:
	if _vo_queue.is_empty():
		_vo_busy = false
		subtitle_end.emit()
		return
	_vo_busy = true
	var id: String = _vo_queue.pop_front()
	var info: Dictionary = Game.tr_line(id)
	var text: String = info.get("text", id)
	var speaker: String = info.get("speaker", "hero")
	var st := _load("res://audio/vo/%s/%s.ogg" % [speaker, id])
	var dur := maxf(2.0, text.length() * 0.07)
	if st:
		_voice.stream = st
		dur = st.get_length()
		_voice.play()
		var duck := create_tween()
		duck.tween_property(_music, "volume_db", -14.0, 0.3)
		duck.tween_interval(maxf(0.1, dur - 0.5))
		duck.tween_property(_music, "volume_db", -6.0, 1.0)
	else:
		get_tree().create_timer(dur).timeout.connect(_on_voice_done)
	if Game.settings.subtitles:
		subtitle.emit(speaker, text, dur)

func _on_voice_done() -> void:
	await get_tree().create_timer(0.25).timeout
	_next_vo()
