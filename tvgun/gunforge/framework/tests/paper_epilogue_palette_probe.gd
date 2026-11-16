extends "res://tests/paper_gallery_capture.gd"
## Capture the city-to-panorama dissolve at equal simulation ticks for the color comparison.

const FADE_TICKS := 108
const DISSOLVE_OFFSETS := [0, 27, 54, 81, FADE_TICKS, 1368]
var dissolve_frames: Array[Dictionary] = []

func sample_panorama() -> void:
	await super.sample_panorama()
	var elapsed: int = model.tick - wide_tick
	if elapsed not in DISSOLVE_OFFSETS:
		return
	var panorama: Dictionary = model.entities[ENDING_WIDE_VIEW]
	var street: Dictionary = model.entities[ENDING_CITY_VIEW]
	var progress := minf(1, float(elapsed) / FADE_TICKS)
	var expected := progress * progress * (3 - 2 * progress)
	var opacity: float = model.active_opacity(panorama)
	check(is_equal_approx(opacity, expected) and street.active == (elapsed < FADE_TICKS),
		"street and panorama crossfade at tick " + str(elapsed))
	dissolve_frames.append({"offset": elapsed, "tick": model.tick, "opacity": opacity,
		"street_active": street.active, "scale": panorama.pose_scale, "input_enabled": model.input_enabled})
	if elapsed < FADE_TICKS:
		await capture("ending_dissolve_%03d" % elapsed)

func play() -> void:
	await super.play()
	check(dissolve_frames.size() == DISSOLVE_OFFSETS.size(), "capture every panorama comparison pose")
	print(JSON.stringify({"build_id": model.build.build_id, "ending_dissolve": dissolve_frames}))
