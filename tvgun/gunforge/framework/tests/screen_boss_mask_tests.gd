extends "train_station_tests.gd"
## Verify the final cinema encounter in the current cast campaign.

const CORE := "cinema.shadow_core"
const SIDES := ["left", "center", "right"]
const TAPES := ["cinema.sweep_tape_1", "cinema.sweep_tape_2", "cinema.sweep_tape_3"]
const FRAME := Rect2(0, 0, 1776, 936)

var hud_layout: Dictionary = {}

func ready_fire() -> void:
	step_to(model.next_shot)
	if model.resources.ammo == 0:
		check(session.enqueue("RELOAD"), "queue a reload from the inherited magazine")
		session.step()
		check(model.reload_at > model.tick, "reload starts")
		step_to(model.reload_at)

func hud_clear(id: String) -> bool:
	var entity: Dictionary = model.level.entities[id]
	var base := Rect2(entity.x, entity.y, entity.width, entity.height)
	var margin: Vector2 = model.camera_amplitude.abs() * absf(entity.get("parallax", 0))
	var extremes := Rect2(base.position - margin, base.size + 2.0 * margin)
	if not FRAME.grow(-hud_layout.edge_band).encloses(extremes):
		return false
	for entry in hud_layout.reserved.values():
		if entry.when == "playing":
			var rect: Array = entry.rect
			if extremes.intersects(Rect2(rect[0], rect[1], rect[2], rect[3])):
				return false
	return true

func sample_target(id: String, stem: String) -> Dictionary:
	var pose: Array = model.geometry()
	var visuals: Array = model.visual_items().filter(func(item): return item.id == id)
	check(visuals.size() == 1, "one visible ink sprite for " + id)
	if visuals.size() != 1:
		return {}
	var ink = visuals[0]
	# The draw uses the artwork alpha, while the resolver uses its own hit raster.
	ink.hit_image = null
	var bounds: Rect2 = ink.bounds().intersection(FRAME)
	var mask := Image.create(int(FRAME.size.x), int(FRAME.size.y), false, Image.FORMAT_L8)
	var hit_pixels := 0
	var visible_pixels := 0
	var outside := 0
	for y in range(floori(bounds.position.y), ceili(bounds.end.y)):
		for x in range(floori(bounds.position.x), ceili(bounds.end.x)):
			var point := Vector2(x + .5, y + .5)
			var visible: bool = ink.sample(point).a >= .5
			var exact: Dictionary = model.resolver.exact(point, pose)
			var hittable: bool = exact.get("id") == id and exact.get("kind") == "primary"
			visible_pixels += int(visible)
			if hittable:
				hit_pixels += 1
				outside += int(not visible)
				mask.set_pixel(x, y, Color.WHITE)
	var clear := hud_clear(id)
	check(hit_pixels > 0 and outside == 0 and clear, "ink coverage and HUD reservations for " + id)
	check(mask.save_png(captures.path_join(stem + "_mask.png")) == OK, "save hit mask for " + id)
	await capture(stem)
	model.entities[id].visible = false
	await capture(stem + "_reference")
	model.entities[id].visible = true
	return {"target": id, "frame": stem, "tick": model.tick, "hit_pixels": hit_pixels,
		"visual_alpha_pixels": visible_pixels, "hit_outside_ink_pixels": outside, "hud_clear_at_camera_extremes": clear}

func invalid_projector(side: String) -> Dictionary:
	var id := "cinema.projector_" + side
	ready_fire()
	var before := counters()
	var health: int = model.entities[id].health
	var trace_start: int = model.trace.size()
	var reply := shoot(id)
	var after := counters()
	var emitted: Array = model.trace.slice(trace_start)
	var cue: String = model.level.presentation.sound_bindings["target.blocked"]
	check(reply.get("kind") == "invalid" and not reply.get("hit", false)
		and after.ammo == before.ammo - 1 and after.score == before.score and model.entities[id].health == health,
		"machine body spends a shot without taking damage for " + side)
	check(emitted.any(func(row): return row.topic == "target.blocked" and row.entity == id)
		and emitted.any(func(row): return row.topic == "cue.started" and row.entity == cue),
		"blocked feedback and audio for " + side)
	if side == "center":
		await capture("projector_invalid")
	return {"target": id, "reply": reply, "before": before, "after": after, "feedback_cue": cue}

func purify_reel(index: int) -> Dictionary:
	var side: String = SIDES[index]
	var id := "cinema.reel_" + side
	var projector := "cinema.projector_" + side
	ready_fire()
	var sample := await sample_target(id, side + "_ink")
	var score: int = model.resources.score
	var reply := shoot(id)
	check(reply.get("target") == id and model.resources.score == score + 100 and not model.entities[id].active,
		"one shot purifies " + id)
	check(not model.entities[TAPES[index]].active, "cleared reel removes its tape")
	for other in SIDES.size():
		var prefix: String = "cinema.projector_" + SIDES[other]
		check(model.entities[prefix + ".warm"].active == (other <= index)
			and model.entities[prefix + ".dark"].active == (other > index),
			"only purified reels show warm light")
	check(model.entities[CORE].active == (index == SIDES.size() - 1), "core opens after the third reel only")
	await capture(side + "_warm")
	var dark: Dictionary = model.entities[projector + ".dark"]
	var warm: Dictionary = model.entities[projector + ".warm"]
	dark.active = true
	warm.visible = false
	await capture(side + "_warm_reference")
	dark.active = false
	warm.visible = true
	sample.merge({"hit": reply, "warm_tick": model.tick, "core_open": model.entities[CORE].active})
	return sample

func play_screen(entered: int) -> Dictionary:
	var before := counters()
	check(model.current_section == "cinema.screen_stage" and model.input_enabled and not model.entities[CORE].active,
		"screen encounter starts with a locked core")
	var invalid_shots := []
	for side in SIDES:
		invalid_shots.append(await invalid_projector(side))
	ready_fire()
	var point: Vector2 = model.display_center(model.entities[CORE])
	var premature := submitted_shot(point, model.geometry())
	check(premature.get("kind") == "miss" and not model.entities[CORE].active, "locked core cannot be hit")
	while not TAPES.all(func(id): return model.entities[id].active) and model.tick < entered + 350:
		session.step()
	check(TAPES.all(func(id): return model.entities[id].active), "all three tape threats reach the arena")
	await capture("screen_dark")
	var targets := []
	for index in SIDES.size():
		targets.append(await purify_reel(index))
	step_to(model.tick + 20)
	var core := await sample_target(CORE, "core_ink")
	var pose: Array = model.geometry()
	var aim = target_point(CORE, pose)
	check(aim != null, "pick a visible core aim")
	var hit := submitted_shot(aim, pose) if aim != null else {}
	core["hit"] = hit
	targets.append(core)
	check(hit.get("target") == CORE and not model.input_enabled
		and model.current_section == "story.train_station_intro", "core hit starts the train transition")
	var after := counters()
	check(after.score == before.score + 400 and after.shots == before.shots + 8
		and after.lives == before.lives and after.rescued == before.rescued, "boss counters match the eight test shots")
	var stale: Dictionary = {}
	if aim != null:
		stale = submitted_shot(aim, pose)
		check(stale.get("reason") == "not_running" and counters() == after,
			"cut rejects the stale core pose without spending ammo")
	step_to(model.tick + 90)
	check(model.current_section == WAITING and counters() == after, "waiting room inherits the cinema result")
	check(not model.visual_items().any(func(item):
		return item.id.begins_with("cinema.") or item.id.begins_with("layer.cinema.")),
		"cinema visuals leave the scene after the chapter cut")
	return {"entry_tick": entered, "before": before, "after": after, "invalid_shots": invalid_shots,
		"premature_core": premature, "stale_core_rejection": stale,
		"targets": targets, "next_section": model.current_section, "next_tick": model.tick}

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
	var entries: Array = fixture.handoffs.filter(func(entry): return entry.station == "screen_stage")
	if entries.size() != 1:
		push_error("Expected one screen-stage handoff")
		quit(2)
		return
	var layout: Dictionary = model.level.resources[model.level.presentation.hud_art.layout]
	hud_layout = JSON.parse_string(FileAccess.get_file_as_string(model.root_path.path_join(layout.path)))
	session.setup(model)
	session.load_recording(fixture.recording)
	session.seek(entries[0].tick)
	session.tape.clear()
	model.set_presentation_context("player", "running")
	var evidence := await play_screen(entries[0].tick)
	evidence.merge({"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"source_revision": model.build.source_revision, "gpu": RenderingServer.get_video_adapter_name()})
	var receipt := FileAccess.open(captures.path_join("samples.json"), FileAccess.WRITE)
	if receipt == null:
		quit(2)
		return
	receipt.store_string(JSON.stringify(evidence, "  ") + "\n")
	print(JSON.stringify(evidence))
	quit(0 if failures.is_empty() else 1)
