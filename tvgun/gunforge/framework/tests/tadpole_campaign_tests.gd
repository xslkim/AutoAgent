extends "res://tests/night_market_tests.gd"
## Branch from the recorded alley exit to verify the added encounter without replaying the opening by hand.

const PUDDLE := "puddle.puddle"
const TADPOLES := ["puddle.puddle.tadpole1", "puddle.puddle.tadpole2", "puddle.puddle.tadpole3"]
const SAFE_FIELD := Rect2(60, 60, 1656, 816)

func head_rect(item) -> Rect2:
	var mask: Rect2 = Rect2(item.hit_image.get_used_rect())
	var scale: Vector2 = item.size / item.source.size
	return item.transform * Rect2(mask.position * scale, mask.size * scale)

func capture_contrast(label: String, pose: Array) -> void:
	if viewport == null:
		return
	for item in pose:
		if item.kind != "primary" or item.id not in TADPOLES:
			continue
		var bounds := head_rect(item)
		var mask := Image.create_empty(1776, 936, false, Image.FORMAT_L8)
		for y in range(floori(bounds.position.y), ceili(bounds.end.y)):
			for x in range(floori(bounds.position.x), ceili(bounds.end.x)):
				var pixel := Vector2(x + .5, y + .5)
				if item.sample(pixel).a >= .5 and model.resolver.exact(pixel, pose).get("id") == item.id:
					mask.set_pixel(x, y, Color.WHITE)
		check(mask.save_png(captures.path_join("puddle_%s_%s_mask.png" % [label, item.id.get_slice(".", 2)])) == OK,
			"save displayed head mask for " + label)
	await capture("puddle_" + label)
	for id in TADPOLES:
		model.entities[id].visible = false
	await capture("puddle_" + label + "_background")
	for id in TADPOLES:
		model.entities[id].visible = true

func verify_no_fire_route(entry_tick: int) -> Dictionary:
	session.seek(entry_tick)
	check(session.enqueue("RELOAD"), "branch from the recorded water encounter")
	var inspected := 0
	var min_gap := INF
	var initial_lives: int = model.resources.lives
	while model.phase == "running" and model.tick < entry_tick + 800:
		var pose: Array = model.geometry()
		var heads: Array[Rect2] = []
		for item in pose:
			if item.id not in TADPOLES or item.kind != "primary":
				continue
			var area := head_rect(item)
			check(SAFE_FIELD.encloses(area) and model.resolver.exact(area.get_center(), pose).get("id") == item.id,
				"head stays visible and hittable at tick %d" % model.tick)
			heads.append(area)
		check(heads.size() == TADPOLES.size(), "all three heads are present until defeat")
		for index in range(heads.size() - 1):
			var left := heads[index]
			var right := heads[index + 1]
			min_gap = minf(min_gap, right.position.x - left.end.x)
		var age: int = model.tick - entry_tick
		match age:
			0:
				await capture_contrast("entry", pose)
			85:
				await capture_contrast("swim", pose)
			160:
				await capture_contrast("approach", pose)
			198:
				check(model.active_cues.values().any(func(cue): return cue.cue == "puddle.water_warning"),
					"water sound plays during the campaign warning")
				await capture("puddle_warning")
			315:
				await capture_contrast("near", pose)
		inspected += 1
		session.step()
	check(min_gap > 0, "displayed heads do not overlap with campaign camera movement")
	check(model.phase == "result" and model.result == "overrun" and model.current_section == PUDDLE,
		"unanswered attacks can end the run at the puddle")
	var defeated := carried()
	check(defeated.lives == 0 and model.trace.filter(func(entry):
		return entry.tick >= entry_tick and entry.topic == "player.damaged").size() == initial_lives,
		"each surviving attack spends one life until defeat")
	await capture("puddle_defeat")
	retry_from_defeat(1)
	check(station() == 1 and model.entities["flow.alley"].active and not model.entities["flow.puddle"].active
		and TADPOLES.all(func(id): return not model.entities[id].active), "retry resets the water encounter to the alley opening")
	return {"frames_inspected": inspected, "min_horizontal_head_gap_px": min_gap, "defeat": defeated,
		"retry": failure_retries.back() if not failure_retries.is_empty() else {}}

func play() -> void:
	await super.play()
	if not model.fired_time.has("puddle.puddle.start") or handoffs.is_empty() or campaign_replay.is_empty():
		check(false, "campaign route includes the puddle and completes its replay")
		return
	var finish: Dictionary = session.snapshot()
	var checkpoints: Dictionary = session.checkpoints.duplicate()
	var entry_tick := ceili(float(model.fired_time["puddle.puddle.start"]) / 1000.0)
	var stall_tick: int = handoffs[0].tick
	session.seek(entry_tick - 12)
	while model.tick < entry_tick - 1:
		session.step()
		if viewport != null:
			await process_frame
			await RenderingServer.frame_post_draw
	var arrival := carried()
	check(model.current_section == "alley.safe_exit" and not model.input_enabled, "puddle follows the six alley waves")
	var preloaded := false
	if viewport != null:
		var scene = model.render_scene
		var body: Image = model.images[model.level.entities[TADPOLES[0]].parts.body.resource]
		preloaded = scene.preloaded_section == PUDDLE and scene.preloaded_textures.has(body.get_instance_id())
		check(preloaded, "puddle art preloads during the alley exit hold")
		await capture("puddle_alley_exit")
	session.step()
	check(station() == 1 and model.current_section == PUDDLE and model.input_enabled, "puddle is playable inside station one")
	check(carried() == arrival and arrival.rescued == 1 and arrival.lives < 5, "puddle keeps the alley counters and rescue")
	check(not model.entities["flow.alley"].active and not model.entities["alley.lamp"].active
		and not model.entities["alley.resident"].visible, "alley wave actors and lamp interaction are cleared at the cut")
	session.seek(stall_tick - 1)
	var departure := carried()
	var weak_hits: Array = model.trace.filter(func(entry): return entry.topic == "target.weak_hit" and entry.entity in TADPOLES)
	check(departure.score == arrival.score + 300 + 25 * weak_hits.size() and departure.ammo == arrival.ammo - 3
		and departure.shots == arrival.shots + 3 and departure.lives == arrival.lives and departure.rescued == arrival.rescued,
		"three live shots award the group score and carry the shared magazine")
	check(model.current_section == PUDDLE and not model.input_enabled and not model.entities["flow.puddle"].active,
		"clearing the group disables the water encounter before the station cut")
	session.step()
	check(model.current_section == "stall.arrival" and carried() == departure, "stall receives all puddle resources")
	check(not model.visual_items().any(func(item): return item.id.begins_with("puddle.") or item.id.begins_with("layer.puddle.")),
		"water actors and layers leave the scene at the station cut")
	var branch := await verify_no_fire_route(entry_tick)
	session.restore(finish)
	session.checkpoints = checkpoints
	print(JSON.stringify({"build_id": model.build.build_id, "puddle_entry_tick": entry_tick, "stall_entry_tick": stall_tick,
		"entry_counters": arrival, "departure_counters": departure, "weak_hits": weak_hits.size(),
		"entry_art_preloaded": preloaded, "no_fire_branch": branch}))
