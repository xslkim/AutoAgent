extends "train_stop_probe.gd"
## Capture target and reference pixels at the same pose, light and camera tick.

const VIEW := Rect2(0, 0, 1776, 936)
const Session = preload("res://core/level_session.gd")
const SAMPLES := {
	"waiting_room": [["crow", "normal", 112, true], ["umbrella", "normal", 190, false], ["crow", "hardened", 112, false],
		["crow", "warning", 220, false], ["umbrella", "warning", 451, false]],
	"platform": [["crow", "normal", 102, false], ["umbrella", "normal", 232, true], ["umbrella", "hardened", 190, false],
		["crow", "warning", 194, false], ["umbrella", "warning", 422, false]],
	"green_car": [["crow", "normal", 112, true], ["umbrella", "normal", 190, false], ["crow", "hardened", 112, false],
		["crow", "warning", 229, false], ["umbrella", "warning", 374, false]],
	"lantern_base": [["crow", "normal", 185, true], ["umbrella", "normal", 185, true],
		["crow", "hardened", 185, false], ["umbrella", "hardened", 185, false],
		["crow", "warning", 220, false], ["umbrella", "warning", 404, false]],
}
const CONTRAST_SAMPLES := {
	"paper.waiting_room_contrast": [["crow", "normal", 160, true], ["crow", "normal", 255, true],
		["umbrella", "normal", 250, false], ["umbrella", "normal", 350, false]],
	"paper.platform_contrast": [["crow", "normal", 38, false], ["crow", "normal", 260, false],
		["umbrella", "normal", 190, true], ["umbrella", "normal", 315, true]],
	"paper.green_car_contrast": [["crow", "normal", 98, true], ["crow", "normal", 265, true],
		["umbrella", "normal", 250, false], ["umbrella", "normal", 330, false]],
}

func raster_mask(id: String, selected, stem: String, pose: Array, require_containment := false) -> Variant:
	var area: Rect2 = selected.bounds().intersection(VIEW)
	var mask := Image.create(int(VIEW.size.x), int(VIEW.size.y), false, Image.FORMAT_L8)
	var pixels := 0
	var outside := 0
	var aim = null
	for y in range(floori(area.position.y), ceili(area.end.y)):
		for x in range(floori(area.position.x), ceili(area.end.x)):
			var point := Vector2(x + .5, y + .5)
			if selected.sample(point).a < .5:
				continue
			if model.resolver.exact(point, pose).get("id") == id:
				mask.set_pixel(x, y, Color.WHITE)
				pixels += 1
				if aim == null:
					aim = point
			else:
				outside += 1
	check(pixels > 0 and mask.save_png(captures.path_join(stem + "_mask.png")) == OK, "save visible raster mask for " + stem)
	check(not require_containment or outside == 0, "hardened eyes stay within the actor in " + stem)
	return aim

func sample(prefix: String, row: Array, include_tick: bool, start_state: Dictionary) -> Dictionary:
	var actor: String = row[0]
	var state: String = row[1]
	var id := prefix + "." + actor
	var stem := actor + "_" + state
	if include_tick:
		stem += "_" + str(row[2])
	if start_state.is_empty():
		model.start()
	else:
		model.restore_state(start_state)
	var entry_tick: int = model.tick
	if not start_state.is_empty() and (row[3] or state == "hardened"):
		if model.resources.ammo == 0 and model.reload_at < 0:
			check(model.command("RELOAD").get("ok", false), "reload the carried magazine before " + stem)
		step_to(model.reload_at)
	if row[3]:
		var lamp := prefix + ".lamp"
		check(shoot(lamp).get("target") == lamp, "light station before " + stem)
	step_to(entry_tick + int(row[2]))
	var entity: Dictionary = model.entities[id]
	check(entity.active and model.tick == entry_tick + int(row[2]), "sample active target " + stem)
	var kind: String = model.effective_kind(entity)
	var cue := ""
	await capture(stem)
	match state:
		"normal":
			check(kind == "primary", "damageable target in " + stem)
			var pose: Array = model.geometry()
			var parts := pose.filter(func(item): return item.id == id)
			check(parts.size() == 2, "body and stamp exist in " + stem)
			if parts.size() == 2:
				raster_mask(id, parts[0], stem, pose)
			check(not model.visual_items().any(func(item): return item.id == id and item.state_visual),
				"normal target draws its stamp in " + stem)
			entity.visible = false
			await capture(stem + "_reference")
			entity.visible = true
		"hardened":
			check(kind == "invalid", "hardened target in " + stem)
			var pose: Array = model.geometry()
			var parts := pose.filter(func(item): return item.id == id)
			var order: Array = entity.part_order
			check(parts.size() == 2 and order.size() == 2, "body and stamp hit pose exist in " + stem)
			if parts.size() != 2 or order.size() != 2:
				return {}
			var eyes: Array = model.visual_items().filter(func(item): return item.id == id and item.state_visual)
			var expects_eyes: bool = entity.parts[order[1]].has("hardened_visual")
			check(eyes.size() == int(expects_eyes), "hardened mark binding in " + stem)
			cue = "eyes" if eyes.size() == 1 else "stamp"
			var aim = raster_mask(id, eyes[0] if cue == "eyes" else parts[1], stem, pose, cue == "eyes")
			entity.part_order = [order[0]]
			await capture(stem + "_reference")
			entity.part_order = order
			if cue == "eyes" and aim != null:
				var health = entity.health
				var assets: Dictionary = model.geometry_assets()
				var submitted: Array = Codec.decode(Codec.encode(pose, assets), assets)
				var shot: Dictionary = model.command("SHOT", aim, submitted)
				check(shot.get("kind") == "invalid" and not shot.get("hit", true) and entity.health == health,
					"hardened eyes remain invalid in " + stem)
		"warning":
			var original: Dictionary = model.active_effects.duplicate()
			for key in original:
				var effect: Dictionary = original[key]
				if effect.entity == id and model.level.effects[effect.effect].kind == "warning":
					model.active_effects.erase(key)
			check(original.size() == model.active_effects.size() + 1, "exactly one warning effect in " + stem)
			await capture(stem + "_reference")
			model.active_effects = original
	var result := {"actor": actor, "state": state, "tick": model.tick - entry_tick, "lamp_lit": row[3], "kind": kind, "frame": stem}
	if not start_state.is_empty():
		result["campaign_tick"] = model.tick
	if not cue.is_empty():
		result["hardened_cue"] = cue
	return result

func capture_stop(stage: String, prefix: String, extra: Array, start_state: Dictionary) -> void:
	var first_failure := failures.size()
	var results: Array[Dictionary] = []
	for row in SAMPLES[stage]:
		results.append(await sample(prefix, row, false, start_state))
	for row in extra:
		results.append(await sample(prefix, row, true, start_state))
	var stop_failures := failures.slice(first_failure)
	var evidence := {"build_id": model.build.build_id, "source_revision": model.build.source_revision, "stage": stage,
		"gpu": RenderingServer.get_video_adapter_name(), "passed": stop_failures.is_empty(), "failures": stop_failures, "samples": results}
	if not start_state.is_empty():
		evidence["campaign_entry_tick"] = start_state.public.tick
	var file := FileAccess.open(captures.path_join("samples.json"), FileAccess.WRITE)
	check(file != null, "write samples for " + stage)
	if file != null:
		file.store_string(JSON.stringify(evidence, "  ") + "\n")
	print(JSON.stringify({"stage": stage, "samples": results.size(), "failures": stop_failures}))

func capture_campaign(path: String) -> void:
	var file := FileAccess.open(path, FileAccess.READ)
	var fixture = file.get_var() if file != null else null
	if not fixture is Dictionary or fixture.get("recording", {}).get("build_id") != model.build.build_id:
		check(false, "load campaign recording for the current build")
		return
	var session := Session.new()
	session.setup(model)
	session.load_recording(fixture.recording)
	model.set_presentation_context("player", "running")
	var output := captures
	var visited := []
	for handoff in fixture.handoffs:
		var stage: String = handoff.station
		if not SAMPLES.has(stage):
			continue
		var prefix := stage + "." + stage
		session.seek(handoff.tick)
		if model.current_section != prefix or not model.input_enabled:
			check(false, "replay reaches combat in " + stage)
			continue
		captures = output.path_join(stage)
		if DirAccess.make_dir_recursive_absolute(captures) != OK:
			check(false, "create capture directory for " + stage)
			continue
		var extra: Array = CONTRAST_SAMPLES.get("paper." + stage + "_contrast", [])
		await capture_stop(stage, prefix, extra, model.save_state())
		visited.append(stage)
	check(visited.size() == SAMPLES.size(), "capture all four campaign combat stops")

func run() -> void:
	if not open_candidate() or viewport == null:
		quit(2)
		return
	var recording := ""
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--recording="):
			recording = argument.trim_prefix("--recording=")
	if not recording.is_empty():
		await capture_campaign(recording)
	else:
		var stage: String = model.level.id.trim_prefix("paper.").trim_suffix("_contrast")
		if stage == "lantern_pullback":
			stage = "lantern_base"
		if not SAMPLES.has(stage):
			quit(2)
			return
		await capture_stop(stage, stage, CONTRAST_SAMPLES.get(model.level.id, []), {})
	print(JSON.stringify({"build_id": model.build.build_id, "passed": failures.is_empty(), "failures": failures}))
	quit(0 if failures.is_empty() else 1)
