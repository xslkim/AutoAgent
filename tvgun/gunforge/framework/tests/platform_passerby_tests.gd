extends "train_stop_probe.gd"
## Verify Passerby A's raster permissions and animations using submitted player poses.

const Session = preload("res://core/level_session.gd")
const RESIDENT := "platform.resident"
const RESCUE := "platform.rescue"
const RIG := "passerby_a"
const SAFE_FIELD := Rect2(60, 60, 1656, 816)

var session = Session.new()
var shortest_body := INF
var motion_bounds := Rect2()

func step_to(target: int) -> void:
	while model.tick < target and model.phase == "running":
		session.step()

func submit_shot(point: Vector2, pose: Array) -> Dictionary:
	session.submit(pose)
	check(session.enqueue("SHOT", point), "queue pose-bound shot")
	session.step()
	check(session.last_results.size() == 1, "one shot result")
	return session.last_results[0] if not session.last_results.is_empty() else {}

func shoot(id: String) -> Dictionary:
	step_to(model.next_shot)
	var pose: Array = model.geometry()
	var point = target_point(id, pose)
	if point == null:
		failures.append("cannot aim at " + id)
		return {}
	return submit_shot(point, pose)

func actor_bounds(pose: Array) -> Rect2:
	var merged := Rect2()
	for item in pose:
		if item.id != RESIDENT:
			continue
		var used := Rect2(item.image.get_region(Rect2i(item.source)).get_used_rect())
		var ratio: Vector2 = item.size / item.source.size
		var bounds: Rect2 = item.transform * Rect2(used.position * ratio, used.size * ratio)
		merged = merged.merge(bounds) if merged.has_area() else bounds
	return merged

func sample_ink(label: String, pose: Array, bounds: Rect2) -> Dictionary:
	var ink := Image.create_empty(1776, 936, false, Image.FORMAT_L8)
	var protected := Image.create_empty(1776, 936, false, Image.FORMAT_L8)
	var body: Array = pose.filter(func(item): return item.id == RESIDENT)
	var mark: Array = pose.filter(func(item): return item.id == RESCUE)
	if mark.size() != 1:
		failures.append("one chest attachment at " + label)
		return {}
	var region: Rect2 = bounds.merge(mark[0].bounds())
	var on_paper := 0
	var total_ink := 0
	var visible_ink := 0
	var off_paper := Rect2i()
	for y in range(floori(region.position.y), ceili(region.end.y)):
		for x in range(floori(region.position.x), ceili(region.end.x)):
			var at := Vector2(x + .5, y + .5)
			var hit: Dictionary = model.resolver.exact(at, pose)
			if mark[0].sample(at).a >= .5:
				total_ink += 1
				if body.any(func(item): return item.sample(at).a >= .5):
					on_paper += 1
				else:
					var pixel := Rect2i(x, y, 1, 1)
					off_paper = off_paper.merge(pixel) if off_paper.has_area() else pixel
			if hit.get("id") == RESCUE:
				ink.set_pixel(x, y, Color.WHITE)
				visible_ink += 1
			elif hit.get("id") == RESIDENT:
				protected.set_pixel(x, y, Color.WHITE)
	check(visible_ink > 0 and visible_ink == total_ink, "entire chest attachment is reachable at " + label)
	check(on_paper == total_ink, "chest attachment stays on visible paper at %s (%s)" % [label, off_paper])
	if viewport != null:
		check(ink.save_png(captures.path_join(label + "_primary.png")) == OK, "capture ink mask " + label)
		check(protected.save_png(captures.path_join(label + "_protected.png")) == OK, "capture paper mask " + label)
		await capture(label)
		var rig: Dictionary = model.puppets[RIG].rig
		var attachments: Array = rig.attachments
		rig.attachments = attachments.filter(func(slot): return slot.part != "rescue_ink")
		await capture(label + "_background")
		rig.attachments = attachments
	return {"pose": label, "tick": model.tick, "ink_on_paper_pixels": on_paper, "visible_ink_pixels": visible_ink,
		"body_height_px": bounds.size.y}

func exposed_paper_point(pose: Array) -> Variant:
	for item in pose:
		if item.id != RESIDENT:
			continue
		var bounds: Rect2 = item.bounds()
		for y in range(ceili(bounds.position.y), floori(bounds.end.y), 3):
			for x in range(ceili(bounds.position.x), floori(bounds.end.x), 3):
				var at := Vector2(x + .5, y + .5)
				if item.sample(at).a >= .5 and model.resolver.exact(at, pose).is_empty():
					return at
	return null

func play() -> Dictionary:
	check(model.entities[RESIDENT].puppet.rig == RIG and model.entities[RESIDENT].template == "protected",
		"platform spawns the protected Passerby A rig")
	var samples := []
	for tick in range(0, 90, 6):
		step_to(tick)
		var pose: Array = model.geometry()
		var bounds := actor_bounds(pose)
		shortest_body = minf(shortest_body, bounds.size.y)
		motion_bounds = motion_bounds.merge(bounds) if motion_bounds.has_area() else bounds
		check(SAFE_FIELD.encloses(bounds) and bounds.size.y >= 300, "full-scale paper body in safe field at %d" % tick)
		if tick in [0, 24, 48, 72]:
			samples.append(await sample_ink("struggle_%02d" % tick, pose, bounds))

	check(shoot("platform.crow").get("target") == "platform.crow" and model.resources.score == 100, "earn score on the crow before testing misfire")
	var paper := shoot(RESIDENT)
	check(paper.get("kind") == "protected" and not paper.get("hit") and model.resources.score == 50
		and model.entities[RESIDENT].health == 1 and model.entities[RESCUE].health == 1 and model.resources.rescued == 0,
		"paper shot subtracts 50 without harming the person or the ink")
	step_to(model.next_shot)
	var stale: Array = model.geometry()
	var chest = target_point(RESCUE, stale)
	var stale_paper = target_point(RESIDENT, stale)
	if chest == null or stale_paper == null:
		failures.append("missing chest or paper before rescue")
		return {}
	var reply := submit_shot(chest, stale)
	check(reply.get("target") == RESCUE and reply.get("kind") == "primary" and model.resources.rescued == 1
		and model.resources.score == 150 and not model.entities[RESCUE].active and model.entities[RESIDENT].kind == "decoration",
		"one chest shot rescues the passerby and releases paper hit protection")
	check(model.active_effects.values().any(func(effect): return effect.effect == "clear_fx"), "rescue burst starts")
	step_to(model.tick + 14)
	await capture("rescue_bounce")
	var fresh: Array = model.geometry()
	check(fresh.any(func(item): return item.id == RESIDENT) and not fresh.any(func(item):
		return item.id == RESCUE or (item.id == RESIDENT and not item.kind.is_empty())), "thankful puppet remains visible with no hit geometry")
	var safe = exposed_paper_point(fresh)
	if safe == null:
		failures.append("cannot find visible paper after rescue")
		return {}
	check(submit_shot(safe, fresh).get("kind") == "miss", "fresh shot at freed paper passes through")
	step_to(model.next_shot)
	check(submit_shot(chest, stale).get("reason") == "target_inactive", "stale chest pose cannot award a second rescue")
	step_to(model.next_shot)
	check(submit_shot(stale_paper, stale).get("reason") == "target_inactive", "stale paper pose cannot penalize a freed resident")
	check(model.resources.score == 150 and model.resources.rescued == 1 and model.resources.lives == 5,
		"later shots do not penalize or rescue the safe resident again")
	step_to(model.tick + 36)
	await capture("thank")
	check(shoot("platform.lamp").get("target") == "platform.lamp", "light the platform signal")
	step_to(maxi(185, model.next_shot))
	check(shoot("platform.umbrella").get("target") == "platform.umbrella", "neutralize the softened umbrella")
	step_to(model.tick + 100)
	check(model.result == "clear", "station settles successfully")
	check(model.resources.lives == 5 and model.resources.ammo == 4 and model.resources.score == 250
		and model.resources.rescued == 1, "station settles with exact resources")
	var state: Dictionary = model.save_state()
	var record: Dictionary = session.recording()
	session.load_recording(record)
	step_to(record.end_tick)
	check(model.save_state() == state, "eight pose-bound shots replay exactly")
	session.start()
	check(model.resources == model.level.initial_resources and model.entities[RESIDENT].kind == "protected"
		and model.entities[RESCUE].active and model.entities[RESCUE].health == 1, "retry resets protection, rescue ink and counters")
	return {"body_min_height_px": shortest_body, "motion_bbox": [motion_bounds.position.x, motion_bounds.position.y,
		motion_bounds.size.x, motion_bounds.size.y], "mask_samples": samples, "replayed_inputs": record.tape.size(),
		"final_resources": state.public.resources}

func run() -> void:
	if not open_candidate():
		quit(2)
		return
	session.setup(model)
	var evidence := await play()
	evidence.merge({"build_id": model.build.build_id, "gpu_capture": viewport != null,
		"passed": failures.is_empty(), "failures": failures})
	print(JSON.stringify(evidence))
	quit(0 if failures.is_empty() else 1)
