extends "train_station_tests.gd"
## Measure the dragon in the three-chapter route with the actual pose resolver.

const ANCHOR := "dragon.anchor"
const MOUTH := "dragon.mouth"
const WARN := "plaza.dragon.breath1.warn"
const RELEASE := "plaza.dragon.breath1.release"
const FRAME := Rect2(0, 0, 1776, 936)

var samples: Array[Dictionary] = []
var hud_layout: Dictionary = {}
var maximum_joint_gap := 0.0

func ready_fire() -> void:
	step_to(model.next_shot)
	if model.resources.ammo == 0:
		check(session.enqueue("RELOAD"), "queue reload before the next dragon shot")
		session.step()
		check(model.reload_at > model.tick, "dragon reload starts")
		step_to(model.reload_at)

func trigger_tail(point: Vector2) -> Dictionary:
	check(session.enqueue("SHOT", point), "queue a shot using the original tail submission")
	session.step()
	check(session.last_results.size() == 1, "one result for the original tail submission")
	return session.last_results[0] if not session.last_results.is_empty() else {}

func damageable(pose: Array) -> Array:
	return pose.filter(func(item): return item.kind in ["primary", "weak"]).map(func(item): return item.id)

func event_tick(id: String) -> int:
	for entry in model.trace:
		if entry.get("event_id") == id:
			return int(entry.tick)
	return -1

func safe_bounds(bounds: Rect2) -> bool:
	if not FRAME.grow(-hud_layout.edge_band).encloses(bounds):
		return false
	for entry in hud_layout.reserved.values():
		if entry.when == "playing":
			var rect: Array = entry.rect
			if bounds.intersects(Rect2(rect[0], rect[1], rect[2], rect[3])):
				return false
	return true

func joint_gap() -> float:
	var posed: Array[Transform2D] = model.dragon.body_pose(model.dragon_clock())
	var pivots: Array = model.dragon.pivots
	var gap := 0.0
	for index in range(1, posed.size()):
		var previous: Vector2 = posed[index - 1] * pivots[index - 1][1]
		var current: Vector2 = posed[index] * pivots[index][0]
		gap = maxf(gap, previous.distance_to(current))
	return gap

func sample_mask(id: String, stem: String, phase: String) -> void:
	var pose: Array = model.geometry()
	var geometry := pose.filter(func(item): return item.id == id)
	var painted: Array = model.visual_items()
	var visuals := painted.filter(func(item): return item.id == id)
	check(damageable(pose) == [id] and geometry.size() == 1 and visuals.size() == 1,
		"only " + id + " is damageable in " + stem)
	if geometry.size() != 1 or visuals.size() != 1:
		return
	var item = geometry[0]
	var visual = visuals[0]
	check(item.image == visual.image and item.transform.is_equal_approx(visual.transform),
		"ink and hit geometry share the same moving transform in " + stem)
	var bounds: Rect2 = item.bounds().intersection(FRAME)
	var foreground := painted.slice(painted.find(visual) + 1).filter(func(layer): return layer.bounds().intersects(bounds))
	for layer in foreground:
		layer.hit_image = null
	var mask := Image.create(int(FRAME.size.x), int(FRAME.size.y), false, Image.FORMAT_L8)
	var pixels := 0
	var covered := {}
	var hidden_hits := 0
	var extent := Rect2()
	for y in range(floori(bounds.position.y), ceili(bounds.end.y)):
		for x in range(floori(bounds.position.x), ceili(bounds.end.x)):
			var point := Vector2(x + .5, y + .5)
			if visual.sample(point).a < .5:
				continue
			var exact: Dictionary = model.resolver.exact(point, pose)
			if exact.get("id") == id:
				var transmission := 1.0
				for layer in foreground:
					transmission *= 1.0 - layer.sample(point).a
				hidden_hits += int(transmission <= .01)
				mask.set_pixel(x, y, Color.WHITE)
				var pixel := Rect2(x, y, 1, 1)
				extent = extent.merge(pixel) if extent.has_area() else pixel
				pixels += 1
			else:
				var owner: String = exact.get("id", "")
				covered[owner] = int(covered.get(owner, 0)) + 1
	var safe := pixels > 0 and safe_bounds(extent)
	check(safe, "visible hit region stays inside the playable area in " + stem)
	check(hidden_hits == 0, "foreground artwork does not hide any hittable ink in " + stem)
	check(mask.save_png(captures.path_join(stem + "_mask.png")) == OK, "save " + stem + " mask")
	var gap := joint_gap()
	maximum_joint_gap = maxf(maximum_joint_gap, gap)
	check(gap < .001, "adjacent copper pivots stay joined in " + stem)
	samples.append({"target": id, "sample": stem, "phase": phase, "tick": model.tick, "hittable_pixels": pixels,
		"covered_pixels": covered, "hidden_hittable_pixels": hidden_hits, "hud_clear": safe,
		"joint_gap_px": gap, "head_swing_degrees": rad_to_deg(model.dragon_swing())})

func capture_ink_pair(stem: String, path: String) -> void:
	await capture(stem)
	var ink: Image = model.dragon.images[path]
	var blank := Image.create(ink.get_width(), ink.get_height(), false, Image.FORMAT_RGBA8)
	blank.fill(Color.TRANSPARENT)
	model.dragon.images[path] = blank
	await capture(stem + "_reference")
	model.dragon.images[path] = ink

func shows_paper(id: String) -> bool:
	var nodes: Array = model.dragon.layout.body_nodes.filter(func(node): return node.id == id)
	var textures: Dictionary = nodes[0].textures
	var paper: Image = model.dragon.images[textures.paper]
	var afterglow: Image = model.dragon.images[textures.purified]
	var visuals: Array = model.visual_items()
	return visuals.any(func(item): return item.image == paper) and visuals.any(func(item):
		return item.image == afterglow and item.tint.a > 0.0
	) and not damageable(model.geometry()).has(id)

func play_dragon() -> Dictionary:
	var before := counters()
	var order: Array = model.dragon.layout.opening_order
	var cleared: Array = []
	var moved_px := 0.0
	var stale := {}
	var tail_submission := ""
	for index in order.size():
		var id: String = order[index]
		ready_fire()
		var start: int = model.tick
		var early_pose: Array = model.geometry()
		var early_aim = target_point(id, early_pose)
		if index == 0:
			session.submit(early_pose)
			tail_submission = session.submission_id
		for offset in [0, 18, 36]:
			step_to(start + offset)
			check(not model.entities[MOUTH].active, "mouth remains locked during " + id)
			sample_mask(id, "%s_%02d" % [id, offset], "body_swim")
		var node: Dictionary = model.dragon.layout.body_nodes[order.size() - index - 1]
		await capture_ink_pair(id + "_active", node.textures.ink)
		var reply: Dictionary
		if index == 0 and early_aim != null:
			var moved = target_point(id, model.geometry())
			moved_px = moved.distance_to(early_aim) if moved != null else 0.0
			check(moved_px > 4, "the tail aim has moved since the original submission")
			reply = trigger_tail(early_aim)
			check(session.tape[-1].binding.submission == tail_submission, "the moving tail is hit using the earlier binding")
			ready_fire()
			stale = trigger_tail(early_aim)
			check(stale.get("reason") == "target_inactive" and session.tape[-1].binding.submission == tail_submission,
				"stale tail submission cannot damage the next segment")
		else:
			reply = shoot(id)
		check(reply.get("target") == id and reply.get("kind") == "primary" and shows_paper(id),
			"one shot replaces " + id + " with warm paper and no hit geometry")
		cleared.append({"id": id, "reply": reply, "paper_visible": shows_paper(id)})
	var opened: int = model.tick
	check(model.entities[MOUTH].active and damageable(model.geometry()) == [MOUTH], "mouth opens after all eight segments")
	for offset in [0, 18, 36]:
		step_to(opened + offset)
		sample_mask(MOUTH, "mouth_idle_%02d" % offset, "mouth_open")
	await capture_ink_pair("mouth_open", model.dragon.layout.mouth.core)
	var jaw_hits := []
	for jaw in ["upper_jaw", "lower_jaw"]:
		ready_fire()
		var reply := shoot(jaw)
		check(reply.get("kind") == "blocker" and model.entities[MOUTH].health == 1, jaw + " blocks without hurting the core")
		jaw_hits.append({"jaw": jaw, "reply": reply})
	var deadline := opened + 240
	while not model.fired.has(WARN) and model.tick < deadline:
		session.step()
	var warning := event_tick(WARN)
	check(warning >= opened, "the mouth breath warning is reached")
	for offset in [12, 35, 60]:
		step_to(warning + offset)
		sample_mask(MOUTH, "mouth_warning_%02d" % offset, "head_swing")
		if offset == 35:
			await capture_ink_pair("mouth_warning", model.dragon.layout.mouth.core)
	ready_fire()
	var hit := shoot(MOUTH)
	check(hit.get("target") == MOUTH and hit.get("kind") == "weak" and not model.input_enabled,
		"the visible core accepts the finishing shot during the warning")
	check(model.entities[ANCHOR].active and damageable(model.geometry()).is_empty()
		and order.all(func(id): return shows_paper(id)), "the cleansed dragon stays visible without any damageable zones")
	await capture("dragon_purified")
	var after := counters()
	check(after.lives == before.lives and after.rescued == before.rescued and after.score == before.score + 900,
		"nine dragon targets award 900 points and preserve the inherited lives and rescues")
	step_to(model.tick + 150)
	check(model.current_section == "cinema.ticket_office" and not model.entities[ANCHOR].active and not model.fired.has(RELEASE)
		and counters() == after, "finishing the core cancels breath and carries the result to the cinema")
	return {"before": before, "after": after, "opening_order": cleared, "early_tail_aim_moved_px": moved_px,
		"stale_tail": stale, "tail_submission": tail_submission, "jaw_shots": jaw_hits,
		"mouth_open_tick": opened, "warning_tick": warning,
		"mouth_hit": hit, "next_section": model.current_section, "next_tick": model.tick,
		"breath_released": model.fired.has(RELEASE)}

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
	var entries: Array = fixture.handoffs.filter(func(entry): return entry.station == "plaza")
	if entries.size() != 1:
		push_error("Expected one plaza handoff")
		quit(2)
		return
	var layout: Dictionary = model.level.resources[model.level.presentation.hud_art.layout]
	hud_layout = JSON.parse_string(FileAccess.get_file_as_string(model.root_path.path_join(layout.path)))
	session.setup(model)
	session.load_recording(fixture.recording)
	var entry: int = entries[0].tick
	session.seek(entry)
	while not model.entities[ANCHOR].active and model.tick < entry + 500:
		session.step()
	if model.current_section != "plaza.ink_dragon" or not model.input_enabled:
		push_error("Expected the campaign recording to reach the active dragon")
		quit(2)
		return
	session.tape.clear()
	model.set_presentation_context("player", "running")
	var boss_tick: int = model.tick
	var evidence := await play_dragon()
	evidence.merge({"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"source_revision": model.build.source_revision, "gpu": RenderingServer.get_video_adapter_name(),
		"plaza_entry_tick": entry, "dragon_start_tick": boss_tick, "samples": samples, "maximum_joint_gap_px": maximum_joint_gap})
	var receipt := FileAccess.open(captures.path_join("samples.json"), FileAccess.WRITE)
	if receipt == null:
		quit(2)
		return
	receipt.store_string(JSON.stringify(evidence, "  ") + "\n")
	print(JSON.stringify(evidence))
	quit(0 if failures.is_empty() else 1)
