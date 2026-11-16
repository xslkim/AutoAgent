extends "train_station_tests.gd"
## Use the full station route, then verify order, overlap, defeat and replay at the workbench.

func stroke(number: int) -> String:
	return "lantern_base.forget.stroke_%d" % number

func expect_current(number: int) -> void:
	for index in range(number, 8):
		var id := stroke(index)
		var current := index == number
		check(model.entities[id].active and model.entities[id].kind == ("weak" if current else "invalid"),
			"stroke permission %d when on %d" % [index, number])
		check(model.entities[id + ".outline"].active == current, "one visible stroke cue at a time")

func crossing_point(pose: Array) -> Variant:
	var lower = pose.filter(func(item): return item.id == stroke(2))[0]
	var upper = pose.filter(func(item): return item.id == stroke(3))[0]
	var overlap: Rect2 = lower.bounds().intersection(upper.bounds())
	for y in range(ceili(overlap.position.y), floori(overlap.end.y)):
		for x in range(ceili(overlap.position.x), floori(overlap.end.x)):
			var at := Vector2(x + .5, y + .5)
			if lower.sample(at).a >= .5 and upper.sample(at).a >= .5:
				return at
	return null

func play_and_replay() -> void:
	var entered := await reach_workbench()
	step_to(entered + 115)
	var opacity: float = model.active_opacity(model.entities[stroke(1)])
	check(not model.input_enabled and opacity > 0 and opacity < 1, "ink rises after the pullback with shooting locked")
	await capture("forget_rise")
	step_to(entered + 200)
	check(model.input_enabled and model.phase == "running", "pullback starts the encounter without settling the level")
	expect_current(1)
	await capture("forget_first_stroke")
	step_to(entered + 1500)
	check(model.result == "overrun" and model.current_section == WORKBENCH and model.resources.lives == 0,
		"ignoring the workbench attack warnings can cause defeat")
	var defeated := counters()
	session.start()
	check(model.current_section == WAITING and model.tick == 0 and model.resources == model.level.initial_resources,
		"retry after the boss resets the full station route")
	check(not model.entities[stroke(1)].active and not model.entities[stroke(1) + ".outline"].active,
		"retry clears the workbench state")
	retry["workbench_defeated_resources"] = defeated
	handoffs.clear()
	entered = await reach_workbench()
	step_to(entered + 200)

	var second := stroke(2)
	check(shoot(second).get("kind") == "invalid" and model.entities[second].health == 4,
		"an out-of-order shot grazes the stroke")
	check(model.active_effects.values().any(func(effect): return effect.effect == "lantern_base.forget.wrong"),
		"wrong shot plays the gray feedback")
	await capture("forget_wrong_stroke")
	check(shoot(second).get("kind") == "invalid" and model.entities[second].health == 4,
		"repeated grazes cannot clear a locked stroke")
	expect_current(1)
	for number in range(1, 8):
		expect_current(number)
		if number == 2:
			step_to(model.next_shot)
			var pose: Array = model.geometry()
			var at = crossing_point(pose)
			check(at != null, "strokes 2 and 3 visibly overlap")
			if at != null:
				check(model.resolver.exact(at, pose).get("id") == stroke(3), "stroke 3 owns the crossing")
				check(submitted_shot(at, pose).get("kind") == "invalid" and model.entities[stroke(3)].health == 4,
					"a shot at the crossing grazes the visible stroke 3")
				check(model.entities[second].active and model.entities[second].health == 4, "covered stroke 2 receives no hit")
		var id := stroke(number)
		var result := shoot(id)
		check(result.get("target") == id and result.get("kind") == "weak" and not model.entities[id].active,
			"current stroke clears with one precise shot")
		check(model.entities[id + ".residue"].active and not model.entities[id + ".outline"].active,
			"a cleared stroke leaves only a residue")
		check(model.phase == "running", "settlement waits for the final dissolve")
	await capture("forget_final_residue")
	check(not model.input_enabled, "shooting locks after the seventh stroke")
	step_to(model.tick + 90)
	var finished := counters()
	check(model.result == "clear" and model.current_section == WORKBENCH, "the seventh stroke completes the level")
	check(finished == {"lives": 4, "ammo": 0, "score": 1700, "rescued": 2, "shots": 24}, "full route including the boss retains counters")
	var record: Dictionary = session.recording()
	var trace: Array = model.trace.duplicate(true)
	await replay_recording(record)
	check(model.result == "clear" and counters() == finished and model.trace == trace, "boss replay reproduces the entire route")
	replay = {"inputs": record.tape.size(), "end_tick": record.end_tick, "final_resources": finished}
