extends "res://tests/night_market_tests.gd"
## Inspect the visible hit geometry at each shooting tick of the recorded route.

var reservations: Dictionary = {}
var samples := 0
var intersections: Dictionary = {}

func queue_action(index: int) -> bool:
	if reservations.is_empty():
		var layout = model.level.resources[model.level.presentation.hud_art.layout]
		var path: String = model.root_path.path_join(layout.path)
		var metadata: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
		for key in metadata.reserved:
			var reservation: Dictionary = metadata.reserved[key]
			if reservation.when == "playing":
				var rect: Array = reservation.rect
				reservations[key] = Rect2(rect[0], rect[1], rect[2], rect[3])
	if station() > 0 and model.input_enabled:
		samples += 1
		var pose: Array = model.geometry()
		for item in pose:
			if item.kind not in ["primary", "weak", "invalid", "protected"]:
				continue
			for key in reservations:
				var overlap: Rect2 = item.bounds().intersection(reservations[key])
				if overlap.has_area() and visible_in(item, pose, overlap):
					var pair: String = key + ":" + item.id
					if not intersections.has(pair):
						intersections[pair] = {"first_tick": model.tick, "station": station(), "sample_count": 0}
					intersections[pair].sample_count += 1
	return super.queue_action(index)

func visible_in(item, pose: Array, area: Rect2) -> bool:
	for y in range(ceili(area.position.y), ceili(area.end.y)):
		for x in range(ceili(area.position.x), ceili(area.end.x)):
			var point := Vector2(x, y)
			if item.sample(point).a >= .5 and model.resolver.exact(point, pose).get("id") == item.id:
				return true
	return false

func play() -> void:
	if not model.level.presentation.has("hud_art"):
		check(false, "reservation check requires the paper UI candidate")
		return
	await super.play()
	check(samples > 0 and intersections.is_empty(), "route keeps visible targets out of the HUD reservations")
	print(JSON.stringify({"hud_samples": samples, "reservation_intersections": intersections}))
