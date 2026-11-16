extends "res://tools/level_player.gd"
## Exercise the player, settings file and UDP input without using the user's calibration.

var failures: Array[String] = []
var capture_dir := ""
var device := PacketPeerUDP.new()
var sequence := 0

func check(passed: bool, message: String) -> void:
	if not passed:
		failures.append(message)

func capture(name: String) -> void:
	if capture_dir.is_empty() or DisplayServer.get_name() == "headless":
		return
	await process_frame
	await RenderingServer.frame_post_draw
	check(root.get_texture().get_image().save_png(capture_dir.path_join(name + ".png")) == OK, "save " + name)

func send_calibration_shot(raw: Vector2, expected_stage: int) -> void:
	sequence += 1
	device.put_packet(("%.5f,%.5f,4,%d" % [raw.x, raw.y, sequence]).to_ascii_buffer())
	device.put_packet(("SHOT %.5f,%.5f,%d" % [raw.x, raw.y, sequence]).to_ascii_buffer())
	for attempt in range(30):
		if display_setup.stage == expected_stage:
			return
		await process_frame
	check(false, "UDP shot reached calibration stage %d" % expected_stage)

func calibrate(offset: Vector2, bad_check: bool) -> void:
	for index in DisplaySetup.POINTS.size():
		var raw: Vector2 = DisplaySetup.POINTS[index] + offset
		if bad_check and index == DisplaySetup.POINTS.size() - 1:
			raw.x += 100
		await send_calibration_shot(raw, -1 if index == DisplaySetup.POINTS.size() - 1 else index + 1)

func discover(local_port: int) -> int:
	var client := PacketPeerUDP.new()
	client.set_dest_address("127.0.0.1", local_port)
	check(client.put_packet("TVGUN_DISCOVER".to_ascii_buffer()) == OK, "send discovery on %d" % local_port)
	for attempt in range(30):
		await process_frame
		if client.get_available_packet_count() > 0:
			var reply := client.get_packet().get_string_from_ascii()
			check(reply == "TVGUN_HERE %d" % GUN_PORT, "discover player on %d" % local_port)
			client.close()
			return int(reply.get_slice(" ", 1))
	client.close()
	check(false, "receive discovery on %d" % local_port)
	return GUN_PORT

func post(port: int, path: String, payload: Dictionary) -> Dictionary:
	var request := HTTPRequest.new()
	request.timeout = 2
	root.add_child(request)
	if request.request("http://127.0.0.1:%d%s" % [port, path], ["Content-Type: application/json"],
			HTTPClient.METHOD_POST, JSON.stringify(payload)) != OK:
		request.queue_free()
		return {}
	var response: Array = await request.request_completed
	request.queue_free()
	var body = JSON.parse_string(response[3].get_string_from_utf8())
	return body if response[1] == 200 and body is Dictionary else {}

func open():
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--capture-dir="):
			capture_dir = arg.trim_prefix("--capture-dir=")
	display_settings_path = "user://display-setup-test-%d.cfg" % OS.get_process_id()
	var settings := ConfigFile.new()
	settings.set_value("display", "profile", "monitor")
	settings.set_value("monitor", "white", 26)
	settings.set_value("other", "keep", "test")
	check(settings.save(display_settings_path) == OK, "seed isolated settings")
	super.open()
	if model == null:
		return
	check(gun.bind_errors.is_empty() and http.bind_error == OK and discovered_http.bind_error == OK, "player network ready")
	check(frame.profile == "monitor" and frame.white == 26, "load prior display settings")
	check(device.connect_to_host("127.0.0.1", gun.port) == OK, "connect simulated light gun")
	await discover(8001)
	await discover(HTTP_PORT + 1)
	var discovered_port := await discover(GUN_PORT + 1)
	var start := await post(discovered_port, "/start", {})
	check(start.get("ok", false) and not session.pause_reasons.has("ready"), "HTTP start at the discovered port")
	session.submit(model.geometry())
	check(session.enqueue("SHOT", Vector2(300, 300)), "queue a shot before setup")
	handle_key(KEY_F2)
	var held_tick: int = model.tick
	check(display_setup.visible and session.queue.pending.is_empty(), "opening setup clears pending shots")
	await capture("overscan_monitor")
	handle_key(KEY_RIGHT)
	check(is_equal_approx(frame.outer, .027), "increase monitor margin")
	handle_key(KEY_F3)
	check(frame.profile == "tv" and frame.white == 24 and is_equal_approx(frame.outer, .045), "independent TV defaults")
	handle_key(KEY_RIGHT)
	check(is_equal_approx(frame.outer, .05), "increase TV margin")
	await capture("overscan_tv")
	handle_key(KEY_C)
	await capture("calibration_target")
	var shot := await post(discovered_port, "/shot", {"x": 972, "y": 531})
	check(shot.get("ok", false) and display_setup.stage == 1, "HTTP calibration shot at the discovered port")
	handle_key(KEY_ESCAPE)
	handle_key(KEY_C)
	await calibrate(Vector2(12, -9), false)
	var fitted: Array = calibration.matrix.duplicate()
	check(calibration.apply(Vector2(972, 531)).distance_to(Vector2(960, 540)) < .01, "apply fitted calibration")
	check(model.tick == held_tick and model.shots == 0, "display setup pauses combat")
	handle_key(KEY_ENTER)
	check(not display_setup.visible and not session.pause_reasons.has("display_setup"), "save closes setup")
	check(settings.load(display_settings_path) == OK and settings.get_value("display", "profile") == "tv", "save selected profile")
	check(is_equal_approx(settings.get_value("monitor", "outer", 0), .027)
		and is_equal_approx(settings.get_value("tv", "outer", 0), .05), "save both display margins")
	var restored := Calibration.new()
	restored.matrix = settings.get_value("tv", "calibration", restored.matrix)
	check(restored.apply(Vector2(972, 531)).distance_to(Vector2(960, 540)) < .01, "save fitted calibration")
	check(settings.get_value("other", "keep", "") == "test", "preserve unrelated settings")
	handle_key(KEY_C)
	await calibrate(Vector2(-20, 14), true)
	check(calibration.matrix == fitted and display_setup.feedback.contains("未通过"), "failed check keeps prior calibration")
	handle_key(KEY_C)
	await send_calibration_shot(Vector2(960, 540), 1)
	handle_key(KEY_ESCAPE)
	check(display_setup.visible and display_setup.stage == -1 and calibration.matrix == fitted, "cancel only the active calibration")
	handle_key(KEY_LEFT)
	handle_key(KEY_F3)
	handle_key(KEY_ESCAPE)
	check(not display_setup.visible and frame.profile == "tv" and is_equal_approx(frame.outer, .05)
		and calibration.matrix == fitted, "cancel restores the saved profile and calibration")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(display_settings_path))
	print(JSON.stringify({"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"udp_shots": sequence, "captures": not capture_dir.is_empty() and DisplayServer.get_name() != "headless"}))
	device.close()
	gun.close()
	http.close()
	quit(0 if failures.is_empty() else 1)
