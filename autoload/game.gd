extends Node
## Глобальное состояние: прогресс, настройки, сохранения, строки.

signal toast(text: String)
signal note_found(id: String)
signal noise(pos: Vector3, radius: float)
signal sanity_changed(v: float)

const SAVE_PATH := "user://save.json"
const MAX_CHAPTER := 8

var chapter: int = 1
var unlocked: int = 1
var truth: int = 0
var notes_found: Dictionary = {}
var flags: Dictionary = {}
var deaths_total: int = 0
var deaths_chapter: int = 0
var checkpoint: Dictionary = {}   # {pos, yaw, patches{}, flags{}}
var settings: Dictionary = {
	"sens": 1.0, "render_scale": 0.85, "ps1": false, "subtitles": true,
	"flashes": true, "vol_master": 1.0, "vol_music": 0.8, "vol_voice": 1.0,
	"invert": false, "btn_scale": 1.0, "shadows": false, "fov": 75.0,
}
var strings: Dictionary = {}
var level: Node = null
var player: Node = null
var touch_mode: bool = false
var sanity: float = 100.0 : set = _set_sanity
var ending: String = ""

func _set_sanity(v: float) -> void:
	sanity = clampf(v, 0.0, 100.0)
	sanity_changed.emit(sanity)

func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	touch_mode = DisplayServer.is_touchscreen_available() or OS.has_feature("android")
	_load_strings()
	_setup_input()
	load_game()

func _load_strings() -> void:
	var f := FileAccess.open("res://data/strings_ru.json", FileAccess.READ)
	if f:
		var d = JSON.parse_string(f.get_as_text())
		if d is Dictionary:
			strings = d

func tr_line(id: String) -> Dictionary:
	return strings.get(id, {})

func _setup_input() -> void:
	var map := {
		"move_forward": KEY_W, "move_back": KEY_S, "move_left": KEY_A, "move_right": KEY_D,
		"action": KEY_E, "flashlight": KEY_F, "crouch": KEY_C, "notebook": KEY_TAB,
		"tool_next": KEY_Q, "pause": KEY_ESCAPE, "sprint": KEY_SHIFT,
		"tool_1": KEY_1, "tool_2": KEY_2, "tool_3": KEY_3, "tool_4": KEY_4, "tool_5": KEY_5,
	}
	for a in map:
		if not InputMap.has_action(a):
			InputMap.add_action(a)
			var ev := InputEventKey.new()
			ev.physical_keycode = map[a]
			InputMap.action_add_event(a, ev)

# ---------- сохранение ----------
func save_game() -> void:
	var d := {
		"chapter": chapter, "unlocked": unlocked, "truth": truth,
		"notes": notes_found, "flags": flags, "settings": settings,
		"deaths": deaths_total,
	}
	var f := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(d))

func load_game() -> void:
	if not FileAccess.file_exists(SAVE_PATH):
		return
	var f := FileAccess.open(SAVE_PATH, FileAccess.READ)
	if not f:
		return
	var d = JSON.parse_string(f.get_as_text())
	if not d is Dictionary:
		return
	chapter = int(d.get("chapter", 1))
	unlocked = int(d.get("unlocked", 1))
	truth = int(d.get("truth", 0))
	notes_found = d.get("notes", {})
	flags = d.get("flags", {})
	deaths_total = int(d.get("deaths", 0))
	var s = d.get("settings", {})
	for k in s:
		settings[k] = s[k]

func new_game() -> void:
	chapter = 1; unlocked = 1; truth = 0; notes_found = {}; flags = {}
	deaths_total = 0; checkpoint = {}; ending = ""
	save_game()

func has_save() -> bool:
	return FileAccess.file_exists(SAVE_PATH) and (unlocked > 1 or not notes_found.is_empty())

# ---------- переходы ----------
func start_chapter(n: int, keep_checkpoint := false) -> void:
	chapter = clampi(n, 1, MAX_CHAPTER)
	if not keep_checkpoint:
		checkpoint = {}
		deaths_chapter = 0
	sanity = 100.0
	get_tree().paused = false
	get_tree().change_scene_to_file("res://world/level.tscn")

func finish_chapter() -> void:
	unlocked = maxi(unlocked, chapter + 1)
	save_game()

func to_menu() -> void:
	get_tree().paused = false
	Audio.stop_all_loops()
	get_tree().change_scene_to_file("res://main.tscn")

func note(text: String) -> void:
	toast.emit(text)

func set_flag(k: String, v = true) -> void:
	flags[k] = v

func flag(k: String) -> bool:
	return flags.get(k, false)

func found_count(prefix := "") -> int:
	var n := 0
	for k in notes_found:
		if prefix == "" or str(k).begins_with(prefix):
			n += 1
	return n
