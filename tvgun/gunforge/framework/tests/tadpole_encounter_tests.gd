extends "train_stop_probe.gd"
## Exercise the head mask through the same submitted-pose path as the player.

const Session = preload("res://core/level_session.gd")
const ENEMIES := ["puddle.tadpole1", "puddle.tadpole2", "puddle.tadpole3"]
const SAFE_FIELD := Rect2(60, 60, 1656, 816)

var session = Session.new()
var smallest_diameter := INF
var largest_diameter := 0.0
var smallest_gap := INF
var smallest_body_gap := INF
var motion_bounds := Rect2()

func step_to(target: int) -> void:
	while model.tick < target and model.phase == "running":
		session.step()

func body_in(id: String, pose: Array):
	for item in pose:
		if item.id == id and item.kind == "primary":
			return item
	return null

func pixel_point(body, pixel: Vector2) -> Vector2:
	return body.transform * (body.size * (pixel + Vector2(0.5, 0.5)) / body.source.size)

func inspect_approach() -> void:
	# All three poses reach maximum scale by tick 274 and keep bobbing until defeat.
	while model.phase == "running" and model.tick < 600:
		var pose: Array = model.geometry()
		var bodies := []
		for id in ENEMIES:
			var item = body_in(id, pose)
			if item == null:
				failures.append("missing body at tick %d: %s" % [model.tick, id])
				return
			var pixels: Rect2 = Rect2(item.image.get_used_rect())
			var ratio: Vector2 = item.size / item.source.size
			var alpha_bounds: Rect2 = item.transform * Rect2(pixels.position * ratio, pixels.size * ratio)
			var hit_bounds: Rect2i = item.hit_image.get_used_rect()
			var center := pixel_point(item, Vector2(hit_bounds.position) + Vector2(hit_bounds.size - Vector2i.ONE) * .5)
			var diameter: float = hit_bounds.size.x * ratio.x * item.transform.x.length()
			if model.resolver.exact(center, pose).get("id") != id:
				failures.append("head blocked at tick %d: %s" % [model.tick, id])
				return
			bodies.append({"center": center, "diameter": diameter, "bounds": alpha_bounds})
			smallest_diameter = minf(smallest_diameter, diameter)
			largest_diameter = maxf(largest_diameter, diameter)
			motion_bounds = alpha_bounds if motion_bounds.size == Vector2.ZERO else motion_bounds.merge(alpha_bounds)
		for index in range(bodies.size() - 1):
			var left: Dictionary = bodies[index]
			var right: Dictionary = bodies[index + 1]
			smallest_gap = minf(smallest_gap, left.center.distance_to(right.center) - (left.diameter + right.diameter) * .5)
			smallest_body_gap = minf(smallest_body_gap, right.bounds.position.x - left.bounds.end.x)
		if model.tick == 0:
			await capture("puddle_start")
		if model.tick == 200:
			await capture("puddle_warning")
			check(model.active_cues.values().any(func(cue): return cue.cue == "water_warning"), "water cue active during warning")
		session.step()
	check(smallest_diameter >= 90 and largest_diameter <= 130, "head diameter stays within 90–130 pixels")
	check(smallest_gap > 0 and smallest_body_gap > 0, "heads and full silhouettes remain disjoint at every tick")
	check(SAFE_FIELD.encloses(motion_bounds), "visible group stays inside the 60-pixel safe field")

func aim(id: String, weak: bool, pose: Array) -> Variant:
	var body = body_in(id, pose)
	if body == null:
		return null
	for y in range(140, 220, 2):
		for x in range(140, 220, 2):
			var point := pixel_point(body, Vector2(x, y))
			var hit: Dictionary = model.resolver.exact(point, pose)
			if hit.get("id") == id and hit.get("kind") == ("weak" if weak else "primary"):
				return point
	return null

func fire(point: Vector2, pose: Array) -> Dictionary:
	session.submit(pose)
	check(session.enqueue("SHOT", point), "queue shot against the submitted pose")
	session.step()
	check(session.last_results.size() == 1, "one pose-bound shot result")
	return session.last_results[0] if not session.last_results.is_empty() else {}

func play() -> void:
	await inspect_approach()
	check(model.result == "overrun" and model.resources.lives == 0, "uncancelled contacts can cause defeat")
	var defeat_tick: int = model.tick
	await capture("puddle_failure")
	session.start()
	check(model.resources == model.level.initial_resources and model.tick == 0 and model.current_section == "puddle", "retry resets the encounter and counters")
	var pose: Array = model.geometry()
	var body = body_in(ENEMIES[0], pose)
	if body == null:
		failures.append("first tadpole absent on retry")
		return
	var tail: Variant = null
	for y in range(120, 240):
		for x in range(280, 343):
			if body.image.get_pixel(x, y).a >= .5:
				tail = pixel_point(body, Vector2(x, y))
				break
		if tail != null:
			break
	if tail == null:
		failures.append("no opaque tail found")
		return
	check(body.sample(tail).a == 0 and model.resolver.exact(tail, pose).is_empty(), "visible tail contributes zero hit coverage")
	var miss := fire(tail, pose)
	check(miss.get("kind") == "miss" and model.entities[ENEMIES[0]].health == 1 and model.resources.ammo == 11, "shooting the tail spends a round without damaging the enemy")

	step_to(225)
	for index in ENEMIES.size():
		step_to(model.next_shot)
		pose = model.geometry()
		var id: String = ENEMIES[index]
		var point = aim(id, index == 1, pose)
		if point == null:
			failures.append("cannot aim at " + id)
			return
		var hit := fire(point, pose)
		check(hit.get("target") == id and hit.get("kind") == ("weak" if index == 1 else "primary") and not model.entities[id].active, "one precise shot clears " + id)
		if index == 0:
			# The first contact was already scheduled before its owner was cleared.
			step_to(244)
			check(model.resources.lives == 5, "clearing the owner during its warning cancels contact")
			check(session.enqueue("RELOAD"), "queue reload while the others remain active")
			session.step()
			check(session.last_results.size() == 1 and session.last_results[0].get("ok", false), "reload starts")
			step_to(model.reload_at + 1)
			check(model.resources.ammo == 12 and model.resources.score == 100, "reload refills ammo and retains score")
	await capture("puddle_clear_effect")
	step_to(model.tick + 60)
	check(model.result == "clear" and model.resources.score == 325 and model.resources.ammo == 10 and model.resources.lives == 3, "clear awards 300 + 25 after the other two contacts")
	await capture("puddle_result")
	var saved: Dictionary = model.save_state()
	var record: Dictionary = session.recording()
	session.load_recording(record)
	step_to(record.end_tick)
	check(model.save_state() == saved, "replay reproduces the full final state and trace")
	print(JSON.stringify({"build_id": model.build.build_id, "gpu_capture": viewport != null,
		"head_diameter_px": [smallest_diameter, largest_diameter], "min_head_gap_px": smallest_gap,
		"min_silhouette_horizontal_gap_px": smallest_body_gap,
		"motion_bbox": [motion_bounds.position.x, motion_bounds.position.y, motion_bounds.size.x, motion_bounds.size.y],
		"defeat_tick": defeat_tick, "replayed_inputs": record.tape.size(), "final_resources": model.resources}))

func run() -> void:
	if not open_candidate():
		quit(2)
		return
	session.setup(model)
	await play()
	print(JSON.stringify({"passed": failures.is_empty(), "failures": failures}))
	quit(0 if failures.is_empty() else 1)
