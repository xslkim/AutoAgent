extends "workbench_boss_tests.gd"
## Sample the visible and hittable ink in a branch of the latest campaign.

const FRAME := Rect2(0, 0, 1776, 936)
const MARKER_CENTER := Color("#ebc58e")
var crossing: Dictionary = {}

func stroke_geometry(id: String, pose: Array):
	for item in pose:
		if item.id == id:
			return item
	return null

func save_mask(mask: Image, stem: String) -> void:
	check(mask.save_png(captures.path_join(stem + ".png")) == OK, "save mask " + stem)

func cue_marker(id: String) -> Variant:
	var cue = stroke_geometry(id + ".outline", model.visual_items())
	if cue == null:
		return null
	var area: Rect2i = cue.image.get_used_rect()
	var sum := Vector2.ZERO
	var count := 0
	for y in range(area.position.y, area.end.y):
		for x in range(area.position.x, area.end.x):
			if cue.image.get_pixel(x, y).to_rgba32() == MARKER_CENTER.to_rgba32():
				sum += Vector2(x + .5, y + .5)
				count += 1
	if count == 0:
		return null
	return cue.transform * (cue.size * (sum / count - cue.source.position) / cue.source.size)

func sample_ink(id: String, stem: String, pose: Array) -> Dictionary:
	var ink = stroke_geometry(id, pose)
	if ink == null:
		check(false, "find current stroke " + id)
		return {}
	var bounds: Rect2 = ink.bounds().intersection(FRAME)
	var mask := Image.create(int(FRAME.size.x), int(FRAME.size.y), false, Image.FORMAT_L8)
	var visible := 0
	var covered := 0
	for y in range(floori(bounds.position.y), ceili(bounds.end.y)):
		for x in range(floori(bounds.position.x), ceili(bounds.end.x)):
			var point := Vector2(x + .5, y + .5)
			if ink.sample(point).a < .5:
				continue
			var hit: Dictionary = model.resolver.exact(point, pose)
			if hit.get("id") == id and hit.get("kind") == "weak":
				mask.set_pixel(x, y, Color.WHITE)
				visible += 1
			else:
				covered += 1
	check(visible > 0, "visible ink is hittable for " + id)
	save_mask(mask, stem + "_ink_mask")
	return {"hittable_pixels": visible, "covered_pixels": covered}

func sample_crossing(pose: Array) -> Variant:
	var lower = stroke_geometry(stroke(2), pose)
	var upper = stroke_geometry(stroke(3), pose)
	if lower == null or upper == null:
		check(false, "find both crossing strokes")
		return null
	var bounds: Rect2 = lower.bounds().intersection(upper.bounds()).intersection(FRAME)
	var mask := Image.create(int(FRAME.size.x), int(FRAME.size.y), false, Image.FORMAT_L8)
	var overlap := 0
	var owned_by_third := 0
	var opaque := 0
	var aim = null
	for y in range(floori(bounds.position.y), ceili(bounds.end.y)):
		for x in range(floori(bounds.position.x), ceili(bounds.end.x)):
			var point := Vector2(x + .5, y + .5)
			var upper_alpha: float = upper.sample(point).a
			if lower.sample(point).a < .5 or upper_alpha < .5:
				continue
			overlap += 1
			var hit: Dictionary = model.resolver.exact(point, pose)
			if hit.get("id") == stroke(3) and hit.get("kind") == "invalid":
				owned_by_third += 1
			if upper_alpha >= .99:
				mask.set_pixel(x, y, Color.WHITE)
				opaque += 1
				if aim == null:
					aim = point
	check(overlap > 0 and owned_by_third == overlap and aim != null,
		"the locked third stroke owns the entire 2/3 crossing")
	save_mask(mask, "stroke_02_crossing_opaque")
	crossing = {"overlap_pixels": overlap, "owned_by_locked_third_pixels": owned_by_third, "opaque_pixels": opaque}
	return aim

func sample_stroke(number: int) -> Dictionary:
	var stem := "stroke_%02d" % number
	var id := stroke(number)
	var ink: Dictionary = model.entities[id]
	var cue: Dictionary = model.entities[id + ".outline"]
	expect_current(number)
	var bright_tick: int = model.tick
	var bright_opacity: float = model.active_opacity(cue)
	check(bright_opacity >= .99, stem + " cue starts bright")
	await capture(stem + "_bright")
	var pulse_ms: int = model.level.entities[id + ".outline"].motion.frames[1].at_ms
	step_to(bright_tick + ceili(pulse_ms * model.level.tick_hz / 1000.0))
	var dim_tick: int = model.tick
	var dim_opacity: float = model.active_opacity(cue)
	check(dim_opacity >= .49 and dim_opacity <= .52, stem + " cue reaches the low pulse")
	await capture(stem + "_dim")
	var pose: Array = model.geometry()
	var dim_marker = cue_marker(id)
	check(dim_marker != null and model.resolver.exact(dim_marker, pose).get("id") == id,
		stem + " dim marker lies on the current stroke")
	var result := sample_ink(id, stem, pose)
	var crossing_aim = sample_crossing(pose) if number == 2 else null
	cue.visible = false
	await capture(stem + "_cue_off")
	ink.visible = false
	await capture(stem + "_background")
	ink.visible = true
	cue.visible = true
	if crossing_aim != null:
		var health: int = model.entities[stroke(2)].health
		var upper_health: int = model.entities[stroke(3)].health
		var reply := submitted_shot(crossing_aim, pose)
		check(reply.get("kind") == "invalid" and model.entities[stroke(2)].health == health
			and model.entities[stroke(3)].health == upper_health - 1,
			"crossing grazes stroke 3 while the cued stroke 2 stays untouched")
		crossing["shot"] = reply
		crossing["shot_point"] = [crossing_aim.x, crossing_aim.y]
		await capture("stroke_02_crossing_graze")
	if model.resources.ammo == 0:
		check(session.enqueue("RELOAD"), "queue reload before " + stem)
		session.step()
		check(model.reload_at > model.tick, "reload starts before " + stem)
		step_to(model.reload_at)
	step_to(model.next_shot)
	var score: int = model.resources.score
	var marker = cue_marker(id)
	check(marker != null, "find the lit aim marker for " + stem)
	var hit := submitted_shot(marker, model.geometry()) if marker != null else {}
	check(hit.get("target") == id and hit.get("kind") == "weak" and model.resources.score == score + 100,
		"aiming at the drawn marker clears " + stem)
	check(not ink.active and not cue.active and model.entities[id + ".residue"].active,
		"only the faded residue stays after " + stem)
	result.merge({"number": number, "stem": stem, "bright_tick": bright_tick, "dim_tick": dim_tick,
		"bright_opacity": bright_opacity, "dim_opacity": dim_opacity,
		"dim_marker": [dim_marker.x, dim_marker.y] if dim_marker != null else [], "hit": hit})
	return result

func run() -> void:
	if not open_candidate() or viewport == null:
		quit(2)
		return
	var recording := ""
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--recording="):
			recording = argument.trim_prefix("--recording=")
	var file := FileAccess.open(recording, FileAccess.READ)
	var fixture = file.get_var() if file != null else null
	if not fixture is Dictionary or fixture.get("recording", {}).get("build_id") != model.build.build_id:
		push_error("Expected a campaign recording for the current build")
		quit(2)
		return
	var entries: Array = fixture.handoffs.filter(func(entry): return entry.station == "workbench")
	if entries.size() != 1:
		push_error("Expected one workbench handoff")
		quit(2)
		return
	session.setup(model)
	session.load_recording(fixture.recording)
	var entered: int = entries[0].tick
	session.seek(entered)
	session.tape.clear()
	model.set_presentation_context("player", "running")
	var deadline := entered + 240
	while not model.input_enabled and model.tick < deadline:
		session.step()
	if model.current_section != WORKBENCH or not model.input_enabled:
		push_error("The recording did not reach the workbench encounter")
		quit(2)
		return
	var before := counters()
	var samples := []
	for number in range(1, 8):
		samples.append(await sample_stroke(number))
	var after := counters()
	check(after.score == before.score + 700 and after.shots == before.shots + 8
		and after.lives == before.lives and after.rescued == before.rescued and not model.input_enabled,
		"all seven strokes settle and the one graze spends a round")
	await capture("final_residue")
	step_to(model.tick + 90)
	check(model.current_section == "lantern_base.ending_light", "clear enters the campaign epilogue")
	var evidence := {"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"source_revision": model.build.source_revision, "workbench_entry_tick": entered,
		"gpu": RenderingServer.get_video_adapter_name(), "samples": samples, "crossing": crossing,
		"before": before, "after": after, "next_section": model.current_section}
	var receipt := FileAccess.open(captures.path_join("samples.json"), FileAccess.WRITE)
	if receipt == null:
		quit(2)
		return
	receipt.store_string(JSON.stringify(evidence, "  ") + "\n")
	print(JSON.stringify(evidence))
	quit(0 if failures.is_empty() else 1)
