class_name Story extends RefCounted
## Метаданные глав.

const CHAPTERS := {
	1: {"title": "Дом Громовых", "sub": "обычный заказ", "music": "drone_a", "ambience": "amb_house", "tension": 0.8,
		"sms": "ЗАКАЗЧИК: Лесная, 12. Код 4471. Оплата по факту.", "outro_sms": "Хорошо. Следующий адрес скоро придёт.", "intro_line": "h1_01",
		"events": {"small": ["flicker", "creak", "laugh", "drip", "steps_far", "radio_static"], "medium": ["door_slam", "tv_on"], "big": []}},
	2: {"title": "Коммуналка на Садовой", "sub": "они прячутся в вещах", "music": "drone_b", "ambience": "amb_house", "tension": 1.0,
		"sms": "ЗАКАЗЧИК: Садовая, 7, кв. 3. Код 1905. Не опаздывай.", "outro_sms": "Ты быстро учишься.", "intro_line": "h2_01",
		"events": {"small": ["flicker", "creak", "whisper", "knock", "thump", "drip", "breath"], "medium": ["door_slam", "lights_out", "phantom_child"], "big": ["shadow_behind"]}},
	3: {"title": "Особняк Вороновых", "sub": "они следят", "music": "drone_c", "ambience": "amb_mansion", "tension": 1.1,
		"sms": "ЗАКАЗЧИК: Особняк Вороновых. Ключ под ковриком. Не выключай свет.", "outro_sms": "Мы видели, как ты смотрел.", "intro_line": "h3_01",
		"events": {"small": ["flicker", "whisper", "knock", "breath", "cold", "laugh", "steps_far"], "medium": ["door_slam", "lights_out", "phantom", "phantom_child", "fake_sms"], "big": ["shadow_behind", "face_flash"]}},
	4: {"title": "Тот же дом", "sub": "ты уже был здесь", "music": "drone_d", "ambience": "amb_house", "tension": 1.0,
		"sms": "ЗАКАЗЧИК: Тот же адрес. Ты знаешь код.", "outro_sms": "Приходи один. Я жду.", "intro_line": "h4_01",
		"events": {"small": ["flicker", "whisper", "creak", "knock", "breath", "steps_far"], "medium": ["door_slam", "lights_out", "fake_sms", "phantom"], "big": ["scream", "shadow_behind"]}},
	5: {"title": "Дом заказчика", "sub": "правда", "music": "drone_e", "ambience": "amb_mansion", "tension": 1.2,
		"sms": "ЗАКАЗЧИК: Тихая, 1. Заходи. Дверь открыта. Подвал — внизу.", "outro_sms": "ТЫ НАШ.", "intro_line": "h5_01",
		"events": {"small": ["flicker", "whisper", "knock", "breath", "cold", "thump", "drip"], "medium": ["door_slam", "lights_out", "phantom", "fake_sms"], "big": ["shadow_behind", "face_flash", "scream"]}},
	6: {"title": "Изнанка", "sub": "то, что осталось", "music": "drone_f", "ambience": "amb_under", "tension": 1.3,
		"sms": "НОМЕР СКРЫТ: Проснись, Андрей. Тебе тут убирать.", "outro_sms": "Он слушает. Идём дальше.", "intro_line": "h6_01",
		"events": {"small": ["flicker", "whisper", "breath", "cold", "thump", "drip"], "medium": ["lights_out", "phantom", "phantom_child"], "big": ["shadow_behind", "scream"]}},
	7: {"title": "Коридор домов", "sub": "голос дочери", "music": "drone_f", "ambience": "amb_under", "tension": 1.2,
		"sms": "АЛИСА: Пап, ты где? Мне страшно.", "outro_sms": "Папа, ты придёшь?", "intro_line": "h7_01",
		"events": {"small": ["flicker", "whisper", "breath", "laugh", "knock"], "medium": ["door_slam", "lights_out", "phantom_child", "fake_sms"], "big": ["shadow_behind", "face_flash"]}},
	8: {"title": "Сердце Дома", "sub": "последний заказ", "music": "drone_g", "ambience": "amb_under", "tension": 1.0,
		"sms": "ЗАКАЗЧИК: Остался один заказ. Самый чистый.", "outro_sms": "Заказ выполнен.", "intro_line": "h8_01",
		"events": {"small": ["flicker", "whisper", "thump", "breath"], "medium": ["lights_out", "phantom"], "big": []}},
}

const CREDITS := """[b]ГРЯЗНАЯ РАБОТА[/b]

Идея, сюжет, код и сборка — Claude Code

Движок — Godot 4 (MIT)
Текстуры — Poly Haven (CC0)
Озвучка — Fish Audio TTS
Звуки и музыка — синтез (скрипты tools/gen_audio.py)

Спасибо, что убрали за всех.
"""
