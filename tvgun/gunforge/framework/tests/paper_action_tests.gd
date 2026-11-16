extends "res://tools/level_player.gd"
## Exercise the paper UI through Godot input and localhost UDP.

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
	var image: Image = preview.native_viewport.get_texture().get_image()
	check(image.save_png(capture_dir.path_join(name + ".png")) == OK, "save " + name)

func window_point(point: Vector2) -> Vector2:
	return preview.position + preview.origin + point * preview.scale_factor

func mouse(point: Vector2, pressed: bool) -> void:
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_LEFT
	event.button_mask = MOUSE_BUTTON_MASK_LEFT if pressed else 0
	event.position = window_point(point)
	event.global_position = event.position
	event.pressed = pressed
	root.push_input(event, true)

func enter() -> void:
	var event := InputEventKey.new()
	event.keycode = KEY_ENTER
	event.pressed = true
	root.push_input(event, true)

func show_result(result: String) -> void:
	model.phase = "result"
	model.result = result
	model.shots = 8
	model.resources.score = 800

func send(packet: String) -> void:
	check(device.put_packet(packet.to_ascii_buffer()) == OK, "send " + packet)

func aim_at(point: Vector2) -> Vector2:
	sequence += 1
	var raw := frame.window_to_norm(window_point(point), root.size)
	send("%.5f,%.5f,4,%d" % [raw.x, raw.y, sequence])
	return raw

func await_shot(raw: Vector2) -> void:
	send("SHOT %.5f,%.5f,%d" % [raw.x, raw.y, sequence])
	for attempt in range(30):
		if gun.shot_sequences.has(sequence):
			return
		await process_frame
	check(false, "receive shot %d" % sequence)

func check_tracking() -> void:
	var hud = model.render_scene.paper_hud
	var point := Vector2(1020, 460)
	session.seek(int(model.level.events["alley.lesson.lamp"].at_tick))
	check(model.input_enabled, "reticle fixture is in an active shooting section")
	aim_at(point)
	await process_frame
	await process_frame
	check(hud.aim.distance_to(point) < .01, "tracked aim maps to the paper reticle")
	await capture("reticle_on")
	handle_key(KEY_H)
	await process_frame
	await process_frame
	check(not hud.aim.is_finite(), "H hides the reticle while tracking")
	await capture("reticle_off")
	handle_key(KEY_H)
	session.submit(model.geometry())
	check(session.enqueue("SHOT", point), "queue a shot before losing tracking")
	var held_tick: int = model.tick
	sequence += 1
	send("LOST,%d" % sequence)
	for attempt in range(30):
		if hud.tracking_lost:
			break
		await process_frame
	check(hud.tracking_lost and not hud.aim.is_finite(), "loss shows guidance and hides reticle")
	check(session.queue.pending.is_empty(), "loss drops the queued shot")
	await capture("tracking_lost")
	check(model.tick == held_tick and model.shots == 0 and model.resources.ammo == model.level.initial_resources.ammo,
		"loss holds simulation and consumes no ammo")
	handle_key(KEY_ESCAPE)
	await process_frame
	await process_frame
	check(not hud.tracking_lost and session.pause_reasons.has("manual"), "manual pause takes precedence")
	handle_key(KEY_ESCAPE)
	handle_key(KEY_F2)
	await process_frame
	await process_frame
	check(not hud.tracking_lost and display_setup.visible, "display setup takes precedence")
	handle_key(KEY_ESCAPE)
	aim_at(point)
	for attempt in range(30):
		if model.tick > held_tick:
			break
		await process_frame
	check(model.tick > held_tick and not hud.tracking_lost and hud.aim.distance_to(point) < .01,
		"reacquiring tracking restores gameplay and reticle")

func open():
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--capture-dir="):
			capture_dir = arg.trim_prefix("--capture-dir=")
	isolated_settings = true
	super.open()
	if model == null:
		return
	var hud = model.render_scene.paper_hud
	var start: Vector2 = hud.action_rect(false).get_center()
	var retry: Vector2 = hud.action_rect(true).get_center()
	var outside := Vector2(100, 100)
	await process_frame
	await process_frame
	if DisplayServer.get_name() != "headless":
		root.warp_mouse(window_point(outside))
	await capture("start_button")
	mouse(start, true)
	check(menu_action() == "start" and pressed_action == "start", "press holds the title until release")
	if DisplayServer.get_name() != "headless":
		root.warp_mouse(window_point(start))
	await capture("start_pressed")
	mouse(outside, false)
	check(menu_action() == "start" and pressed_action.is_empty(), "release outside cancels the click")
	mouse(start, true)
	mouse(start, false)
	if opening != null:
		check(opening.visible and session.pause_reasons.has("ready"), "start button plays the opening before combat")
		enter()
		check(not opening.visible, "Enter skips the opening")
	check(menu_action().is_empty() and model.shots == 0, "mouse starts without firing")
	show_result("overrun")
	await capture("retry_button")
	mouse(retry, true)
	mouse(retry, false)
	check(model.phase == "running" and model.shots == 0 and model.resources.score == 0, "mouse retry resets run")
	session.set_pause("ready", true)
	enter()
	check(menu_action().is_empty(), "Enter starts the run")
	show_result("clear")
	enter()
	check(model.phase == "running" and model.shots == 0, "Enter retries after clear")
	session.set_pause("ready", true)
	mouse(outside, true)
	mouse(outside, false)
	check(menu_action().is_empty(), "existing mouse start shortcut works")

	check(gun.bind_errors.is_empty() and http.bind_error == OK, "player network ready")
	check(device.connect_to_host("127.0.0.1", gun.port) == OK, "connect simulated light gun")
	network = true
	session.set_pause("ready", true)
	await await_shot(aim_at(outside))
	check(menu_action() == "start" and model.shots == 0, "trigger outside button leaves title visible")
	aim_at(start)
	await process_frame
	await process_frame
	check(hud.action_hovered, "tracked gun aim highlights the start button")
	await capture("start_hover")
	await await_shot(aim_at(start))
	check(menu_action().is_empty() and model.shots == 0 and model.resources.ammo == model.level.initial_resources.ammo, "trigger starts without firing")
	show_result("overrun")
	await await_shot(aim_at(retry))
	check(model.phase == "running" and model.shots == 0 and model.resources.score == 0, "trigger retries without firing")
	show_result("clear")
	send("START")
	for attempt in range(30):
		if model.phase == "running":
			break
		await process_frame
	check(model.phase == "running" and model.shots == 0, "device START retries after clear")
	await check_tracking()
	print(JSON.stringify({"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"udp_shots": gun.shot_sequences.size(), "opening": opening != null,
		"captures": not capture_dir.is_empty() and DisplayServer.get_name() != "headless"}))
	device.close()
	gun.close()
	http.close()
	quit(0 if failures.is_empty() else 1)
