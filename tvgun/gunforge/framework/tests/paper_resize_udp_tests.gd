extends "paper_udp_combat_tests.gd"
## Feed a simulated camera through the production player before and after a resize.

const VIEW := Vector2(1920, 1080)
const INSET := Vector2(72, 72)
const LAMP := "footbridge.footbridge.lamp"

var output_dir := ""
var pending_resize := Vector2i.ZERO
var race: Dictionary = {}
var calibrations: Dictionary = {}
var cases: Array[Dictionary] = []
var max_mapping_error := 0.0

func _process(delta):
	if pending_resize != Vector2i.ZERO:
		# Process the real datagrams in the same frame as the layout change, before Preview._draw.
		if gun.transport.get_available_packet_count() < 2:
			return
		var requested := pending_resize
		pending_resize = Vector2i.ZERO
		var old_size := root.size
		var old_scale: float = preview.scale_factor
		root.size = requested
		layout()
		race = {"from": [old_size.x, old_size.y], "to": [root.size.x, root.size.y],
			"old_scale": old_scale, "rendered_scale_before_udp": preview.scale_factor}
		super._process(delta)
		race["trigger_before_draw"] = gun.shot_sequences.has(sequence)
		return
	super._process(delta)

func press(key: Key) -> void:
	var input := InputEventKey.new()
	input.keycode = key
	input.pressed = true
	root.push_input(input, true)

func camera(norm: Vector2) -> Vector2:
	var p := norm / VIEW
	var direction := 1.0 if frame.profile == "monitor" else -1.0
	var w := 1.0 + direction * (.09 * p.x - .05 * p.y)
	return Vector2((1.03 * p.x + .03 * p.y + .045 * direction) / w,
		(-.02 * p.x + .97 * p.y - .036 * direction) / w) * VIEW

func setup_profile(profile: String) -> void:
	press(KEY_F2)
	check(display_setup.visible, "open display settings")
	if frame.profile != profile:
		press(KEY_F3)
	check(frame.profile == profile, "select the requested display profile")
	press(KEY_C)
	for index in DisplaySetup.POINTS.size():
		var raw := camera(DisplaySetup.POINTS[index])
		aim(raw)
		send("SHOT %.5f,%.5f,%d" % [raw.x, raw.y, sequence])
		var expected := index + 1 if index + 1 < DisplaySetup.POINTS.size() else -1
		for attempt in range(30):
			await process_frame
			if display_setup.stage == expected and gun.shot_sequences.has(sequence):
				break
		check(display_setup.stage == expected and gun.shot_sequences.has(sequence), "receive calibration point %d" % index)
	check(display_setup.feedback.begins_with("校准通过"), "independent calibration samples pass for " + profile)
	calibrations[profile] = {"check_error_px": display_setup.max_error, "matrix": calibration.matrix.duplicate(),
		"white": frame.white, "dark": frame.dark, "outer": frame.outer}
	press(KEY_ENTER)
	await paint()
	check(not display_setup.visible and frame.white == 24 and frame.dark == 48, "save profile with default frame widths")

func restore_pose(state: Dictionary) -> void:
	audio.clear()
	session.restore(state)
	session.real_time_inputs = true
	await paint()
	check(not session.submission_id.is_empty(), "draw a pose in the new window")

func resize(size: Vector2i) -> void:
	root.size = size
	for attempt in range(40):
		await process_frame
		if root.size == size:
			break
	await paint()
	check(root.size == size, "requested window size is active")

func toggle_fullscreen(expected: bool) -> void:
	press(KEY_F11)
	for attempt in range(60):
		await process_frame
		if (DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_FULLSCREEN) == expected:
			break
	await paint()
	check((DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_FULLSCREEN) == expected,
		"F11 switches the native Windows mode")

func is_white(color: Color) -> bool:
	return minf(color.r, minf(color.g, color.b)) >= .98

func white_span(image: Image, horizontal: bool) -> Vector2i:
	var length := image.get_width() if horizontal else image.get_height()
	var middle := int(image.get_height() / 2.0) if horizontal else int(image.get_width() / 2.0)
	var first := -1
	var last := -1
	for pixel in length:
		var color := image.get_pixel(pixel, middle) if horizontal else image.get_pixel(middle, pixel)
		if is_white(color):
			first = pixel if first == -1 else first
			last = pixel
	return Vector2i(first, last + 1)

func capture_layout(label: String) -> Dictionary:
	await process_frame
	await RenderingServer.frame_post_draw
	var image: Image = root.get_texture().get_image()
	var size := Vector2(image.get_size())
	check(size == Vector2(root.size), "the renderer covers the entire native window for " + label)
	var fit: float = minf(size.x / VIEW.x, size.y / VIEW.y) * (1.0 - 2.0 * frame.outer)
	var expected := Rect2((size - VIEW * fit) / 2.0, VIEW * fit)
	var x := white_span(image, true)
	var y := white_span(image, false)
	var actual := Rect2(x.x, y.x, x.y - x.x, y.y - y.x)
	var delta := maxf(actual.position.distance_to(expected.position), actual.end.distance_to(expected.end))
	check(delta <= 2.0, "actual white frame fits the window for " + label)
	var inner_x := floori(expected.position.x + (frame.white + frame.dark * .5) * fit)
	var inner_color := image.get_pixel(inner_x, int(size.y / 2.0))
	check(maxf(inner_color.r, maxf(inner_color.g, inner_color.b)) < .02, "dark band is drawn next to the white frame")
	check(image.save_png(output_dir.path_join(label + ".png")) == OK, "write window evidence")
	return {"case": label, "profile": frame.profile, "window": [root.size.x, root.size.y], "capture": [size.x, size.y],
		"fullscreen": DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_FULLSCREEN,
		"frame_edges": [x.x, y.x, x.y, y.y], "frame_edge_error_px": delta}

func fire_norm(label: String, norm: Vector2) -> Dictionary:
	var reply := await fire(label, camera(norm))
	if session.tape.is_empty() or session.tape[-1].input.event != "SHOT":
		return reply
	var entry: Dictionary = session.tape[-1]
	var point: Vector2 = entry.input.point
	var error := point.distance_to(norm - INSET)
	max_mapping_error = maxf(max_mapping_error, error)
	results[label]["point"] = [point.x, point.y]
	results[label]["mapping_error_px"] = error
	check(error < .01, "calibrated point stays in the same canvas location for " + label)
	return reply

func hit_norm(label: String, id: String) -> void:
	var point = point_on(id, "primary")
	check(point != null, "find the visible aim point for " + id)
	if point != null:
		var reply := await fire_norm(label, point + INSET)
		check(reply.get("target") == id, "calibrated shot hits " + id + " in " + label)

func edge_point(side: int, inward: float) -> Vector2:
	return [Vector2(inward, 540), Vector2(VIEW.x - inward, 540),
		Vector2(960, inward), Vector2(960, VIEW.y - inward)][side]

func borders(label: String, side: int) -> void:
	for row in [["content", 74, true], ["white", 12, false], ["dark", 44, false]]:
		await step_to(model.next_shot)
		var ammo: int = model.resources.ammo
		var name: String = label + "_" + row[0]
		var at := edge_point(side, row[1])
		var expected: String = model.resolver.exact(at - INSET, pose()).get("kind", "miss") if row[2] else "miss"
		var reply := await fire_norm(name, at)
		var shapes: int = results.get(name, {}).get("bound_shapes", -1)
		check(reply.get("kind") == expected and model.resources.ammo == ammo - 1
			and (shapes > 0 if row[2] else shapes == 0), "correct shot zone for " + name)
	var shots: int = model.shots
	var reply := await fire(label + "_offscreen", camera(edge_point(side, -20)))
	check(reply.get("ok", false) and model.reload_at > model.tick and model.shots == shots,
		"only the outer trigger starts reload")
	await step_to(model.reload_at)
	check(model.resources.ammo == model.level.initial_resources.ammo, "outer trigger refills the magazine")

func verify_case(label: String, side: int, center: Dictionary, edge: Dictionary) -> void:
	await restore_pose(center)
	cases.append(await capture_layout(label))
	await hit_norm(label + "_center", TADPOLE + "2")
	await restore_pose(edge)
	await hit_norm(label + "_upper_right", LAMP)
	await borders(label, side)

func open():
	var fixture_path := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--recording="):
			fixture_path = arg.trim_prefix("--recording=")
		if arg.begins_with("--evidence="):
			output_dir = arg.trim_prefix("--evidence=")
	if not open_udp_player():
		return
	var file := FileAccess.open(fixture_path, FileAccess.READ)
	var fixture = file.get_var() if file != null else null
	if not fixture is Dictionary or fixture.get("recording", {}).get("build_id") != model.build.build_id or output_dir.is_empty():
		check(false, "load the exact campaign fixture and evidence path")
		finish()
		return
	check(DirAccess.make_dir_recursive_absolute(output_dir) == OK, "create evidence directory")
	send("HELLO paper-resize-check")
	aim(camera(Vector2(960, 540)))
	await paint()
	var bridge_entry: Array = fixture.handoffs.filter(func(entry): return entry.station == "footbridge")
	await seek(fixture.recording, int(model.level.events["puddle.puddle.start"].at_tick))
	var center: Dictionary = session.snapshot()
	await seek(fixture.recording, bridge_entry[0].tick)
	var edge: Dictionary = session.snapshot()
	for profile in ["monitor", "tv"]:
		await setup_profile(profile)
		var size := Vector2i(1280, 720) if profile == "monitor" else Vector2i(1120, 700)
		await resize(size)
		await verify_case(profile + "_window", 0 if profile == "monitor" else 2, center, edge)
		await toggle_fullscreen(true)
		await verify_case(profile + "_fullscreen", 1 if profile == "monitor" else 3, center, edge)
		await toggle_fullscreen(false)
		check(root.size == size, "F11 restores the previous window dimensions")
		await resize(Vector2i(960, 720))
		await verify_case(profile + "_four_three", 2 if profile == "monitor" else 0, center, edge)
	await restore_pose(edge)
	pending_resize = Vector2i(1120, 700)
	await hit_norm("same_frame_resize", LAMP)
	check(race.get("trigger_before_draw", false) and race.get("to") == [1120, 700]
		and race.get("old_scale") == race.get("rendered_scale_before_udp"),
		"resize and shot happen before the next draw")
	var evidence := {"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"source_revision": model.build.source_revision, "cases": cases, "calibrations": calibrations,
		"race": race, "max_mapping_error_px": max_mapping_error, "shots": results}
	var receipt := FileAccess.open(output_dir.path_join("checks.json"), FileAccess.WRITE)
	if receipt != null:
		receipt.store_string(JSON.stringify(evidence, "  ") + "\n")
	else:
		check(false, "write resize receipt")
	finish()
