class_name Interactable extends StaticBody3D
## Объект, с которым можно взаимодействовать лучом из камеры.

var prompt: String = ""
var callback: Callable = Callable()
var enabled := true
var once := false
var id := ""
var meta_info: Dictionary = {}

func _init() -> void:
	collision_layer = 3   # world + interact
	collision_mask = 0

func get_prompt() -> String:
	return prompt if enabled else ""

func interact(p) -> void:
	if not enabled:
		return
	if callback.is_valid():
		callback.call(p)
	if once:
		enabled = false
