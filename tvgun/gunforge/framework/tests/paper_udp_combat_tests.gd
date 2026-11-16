extends "res://tools/level_player.gd"
## Branch a campaign replay and fire through the production localhost controls.

const TADPOLE := "puddle.puddle.tadpole"
const CYCLIST := "footbridge.bridge.cyclist"
const RESIDENT := "platform.platform.resident"
const RESCUE := "platform.platform.rescue"

var failures: Array[String] = []
var results: Dictionary = {}
var device := PacketPeerUDP.new()
var sequence := 0
var pending_delta := 0.0
var http_reply: Dictionary = {}

func check(passed: bool, message: String) -> void:
	if not passed:
		failures.append(message)

func _process(_delta):
	var step := pending_delta
	pending_delta = 0.0
	super._process(step)

func paint() -> void:
	await process_frame
	await process_frame

func send(packet: String) -> void:
	check(device.put_packet(packet.to_ascii_buffer()) == OK, "send " + packet)

func aim(raw: Vector2) -> void:
	sequence += 1
	send("%.5f,%.5f,4,%d" % [raw.x, raw.y, sequence])

func step_to(at: int) -> void:
	while model.tick < at:
		var before: int = model.tick
		# Keep the tracked session alive while traversing authored delays.
		aim(Vector2(960, 540))
		pending_delta = mini(at - before, 24) / 60.0
		await paint()
		if model.tick <= before:
			check(false, "advance from tick %d" % before)
			return

func seek(record: Dictionary, at: int) -> void:
	session.load_recording(record)
	session.seek(at)
	session.tape.clear()
	session.real_time_inputs = true
	await paint()
	check(model.tick == at and not session.submission_id.is_empty(), "player paints branch at tick %d" % at)

func pose() -> Array:
	return Codec.decode(session.submission, model.geometry_assets())

func point_on(id: String, kind: String) -> Variant:
	var shown := pose()
	for item in shown:
		if item.id != id or item.kind != kind:
			continue
		var bounds: Rect2 = item.bounds().intersection(Rect2(Vector2.ZERO, frame.content_size()))
		for y in range(ceili(bounds.position.y), floori(bounds.end.y), 3):
			for x in range(ceili(bounds.position.x), floori(bounds.end.x), 3):
				var point := Vector2(x + .5, y + .5)
				if item.sample(point).a < .5:
					continue
				var exact: Dictionary = model.resolver.exact(point, shown)
				if (kind.is_empty() and exact.is_empty()) or (exact.get("id") == id and exact.get("kind") == kind):
					return point
	return null

func tail_point() -> Variant:
	var shown := pose()
	for body in shown:
		if body.id != TADPOLE + "1" or body.kind != "primary":
			continue
		for y in range(120, 240):
			for x in range(280, 343):
				if body.image.get_pixel(x, y).a < .5:
					continue
				var point: Vector2 = body.transform * (body.size * Vector2(x + .5, y + .5) / body.source.size)
				if in_playfield(point) and body.sample(point).a == 0 and model.resolver.exact(point, shown).is_empty():
					return point
	return null

func fire(label: String, raw: Vector2, duplicate := false) -> Dictionary:
	aim(raw)
	var packet := "SHOT %.5f,%.5f,%d" % [raw.x, raw.y, sequence]
	send(packet)
	if duplicate:
		send(packet)
	for attempt in range(24):
		await process_frame
		if gun.shot_sequences.has(sequence):
			break
	check(gun.shot_sequences.has(sequence), "receive UDP trigger " + label)
	check(session.queue.pending.size() == 1, "queue one command for " + label)
	if session.queue.pending.is_empty():
		return {}
	var input_tick: int = model.tick + 1
	var tape_size: int = session.tape.size()
	pending_delta = 1.0 / 60.0
	await paint()
	check(model.tick == input_tick and session.tape.size() == tape_size + 1, "consume one UDP command for " + label)
	if session.tape.size() <= tape_size:
		return {}
	var entry: Dictionary = session.tape[-1]
	var reply: Dictionary = entry.result
	results[label] = {"tick": entry.tick, "command": entry.input.event, "reply": reply,
		"bound_shapes": entry.input.get("geometry", []).size(), "submission": entry.binding.submission,
		"ammo": model.resources.ammo, "score": model.resources.score, "rescued": model.resources.rescued}
	return reply

func fire_at(label: String, point: Variant, duplicate := false) -> Dictionary:
	check(point != null, "find visible aim point for " + label)
	if point == null:
		return {}
	var window_point: Vector2 = preview.position + preview.origin + point * preview.scale_factor
	return await fire(label, frame.window_to_norm(window_point, root.size), duplicate)

func margin(label: String, raw: Vector2) -> void:
	await step_to(model.next_shot)
	var ammo: int = model.resources.ammo
	var hits: int = model.hits
	var reply := await fire(label, raw)
	check(reply.get("kind") == "miss" and model.resources.ammo == ammo - 1 and model.hits == hits
		and results.get(label, {}).get("bound_shapes", -1) == 0, label + " spends one round as a geometry-free miss")

func puddle(record: Dictionary) -> void:
	await seek(record, int(model.level.events["puddle.puddle.start"].at_tick))
	check(model.current_section == "puddle.puddle" and model.input_enabled, "puddle is live")
	await step_to(model.next_shot)
	var hits: int = model.hits
	var tail_ammo: int = model.resources.ammo
	var miss := await fire_at("tadpole_tail", tail_point(), true)
	check(miss.get("kind") == "miss" and model.entities[TADPOLE + "1"].health == 1
		and model.hits == hits and model.resources.ammo == tail_ammo - 1,
		"duplicate tail trigger spends only one round and deals no damage")
	await margin("white_border", Vector2(12, 500))
	await margin("dark_band", Vector2(44, 500))
	calibration.matrix[2] = 32.0
	await margin("calibrated_white_border", Vector2(-20, 500))
	calibration.matrix[2] = 0.0
	var ammo: int = model.resources.ammo
	var shots: int = model.shots
	var reload := await fire("offscreen", Vector2(-20, 500))
	check(reload.get("ok", false) and model.reload_at > model.tick and model.resources.ammo == ammo
		and model.shots == shots and results.get("offscreen", {}).get("command") == "RELOAD",
		"true offscreen trigger starts reload without firing")
	await step_to(model.reload_at)
	check(model.resources.ammo == model.level.initial_resources.ammo, "offscreen reload refills the magazine")

	var score: int = model.resources.score
	for index in range(1, 4):
		await step_to(model.next_shot)
		var id := TADPOLE + str(index)
		var kind := "weak" if index == 2 else "primary"
		var hit := await fire_at("tadpole_%d" % index, point_on(id, kind))
		check(hit.get("target") == id and hit.get("kind") == kind and not model.entities[id].active,
			"tadpole %d takes the expected precise hit" % index)
	check(model.resources.score == score + 325 and not model.input_enabled, "puddle clears with three defeats and one weak bonus")
	var counters := player_counters()
	var held := await fire("transition", Vector2(960, 540))
	check(held.get("reason") == "not_running" and player_counters() == counters, "hold rejects a trigger without spending a round")
	for attempt in range(120):
		if model.current_section == "stall.arrival":
			break
		await step_to(model.tick + 1)
	check(model.current_section == "stall.arrival" and player_counters() == counters
		and not pose().any(func(item): return item.id.begins_with("puddle.")), "stall handoff preserves counters and removes the puddle")

func player_counters() -> Array:
	return [model.resources.ammo, model.resources.score, model.resources.lives, model.resources.rescued, model.shots]

func bridge(record: Dictionary, at: int) -> void:
	await seek(record, at)
	var score: int = model.resources.score
	var hits: int = model.hits
	for id in [CYCLIST + "_resident", "footbridge.bridge.bicycle"]:
		await step_to(model.next_shot)
		var miss := await fire_at(id, point_on(id, ""))
		check(miss.get("kind") == "miss", id + " is visible and cannot intercept a shot")
	check(model.resources.score == score and model.hits == hits, "bridge scenery leaves score and hits unchanged")
	await step_to(model.next_shot)
	var hit := await fire_at("hostile_cart", point_on(CYCLIST, "primary"))
	check(hit.get("target") == CYCLIST and model.resources.score == score + 100, "the ink cart remains hittable")

func platform(record: Dictionary, at: int) -> void:
	await seek(record, at)
	var score: int = model.resources.score
	var rescued: int = model.resources.rescued
	await step_to(model.next_shot)
	var paper := await fire_at("protected_paper", point_on(RESIDENT, "protected"))
	check(paper.get("kind") == "protected" and model.resources.score == score - 50
		and model.entities[RESIDENT].health == 1 and model.entities[RESCUE].health == 1,
		"paper subtracts 50 points without damaging paper or ink")
	await step_to(model.next_shot)
	var ink := await fire_at("rescue_ink", point_on(RESCUE, "primary"))
	check(ink.get("target") == RESCUE and model.resources.score == score + 50 and model.resources.rescued == rescued + 1,
		"chest ink awards one rescue and 100 points")
	await step_to(model.next_shot)
	var safe := await fire_at("freed_paper", point_on(RESIDENT, ""))
	check(safe.get("kind") == "miss" and model.resources.score == score + 50 and model.resources.rescued == rescued + 1,
		"freed paper remains visible and incurs no penalty")

func http_trigger(raw: Vector2) -> Dictionary:
	http_reply = {}
	var request := HTTPRequest.new()
	request.timeout = 2
	root.add_child(request)
	request.request_completed.connect(func(result, status_code, _headers, body):
		var data = JSON.parse_string(body.get_string_from_utf8())
		http_reply = {"result": result, "status": status_code, "body": data if data is Dictionary else {}}
	)
	check(request.request("http://127.0.0.1:8080/shot", ["Content-Type: application/json"],
		HTTPClient.METHOD_POST, JSON.stringify({"x": raw.x, "y": raw.y})) == OK, "send loopback HTTP trigger")
	for attempt in range(120):
		await process_frame
		if not session.queue.pending.is_empty():
			pending_delta = 1.0 / 60.0
		if not http_reply.is_empty():
			break
	request.queue_free()
	check(http_reply.get("status") == 200, "receive HTTP trigger response")
	return http_reply

func check_http_triggers() -> void:
	await step_to(model.next_shot)
	var ammo: int = model.resources.ammo
	var border_reply := await http_trigger(Vector2(12, 500))
	check(border_reply.get("body", {}).get("kind") == "miss" and model.resources.ammo == ammo - 1,
		"HTTP border spends a round as a miss")
	var shots: int = model.shots
	var reload_reply := await http_trigger(Vector2(-20, 500))
	check(reload_reply.get("body", {}).get("ok", false) and model.reload_at > model.tick and model.shots == shots,
		"HTTP offscreen trigger starts reload without firing")
	results["http_border"] = border_reply
	results["http_offscreen"] = reload_reply

func finish() -> void:
	print(JSON.stringify({"passed": failures.is_empty(), "build_id": model.build.build_id,
		"failures": failures, "checks": results, "udp_sequences": gun.shot_sequences.size()}))
	device.close()
	gun.close()
	http.close()
	quit(0 if failures.is_empty() else 1)

func open_udp_player() -> bool:
	isolated_settings = true
	network = true
	super.open()
	if model == null:
		return false
	check(gun.bind_errors.is_empty() and http.bind_error == OK, "player binds UDP and HTTP")
	check(device.connect_to_host("127.0.0.1", gun.port) == OK, "connect simulated light gun")
	return true

func open():
	var fixture_path := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--recording="):
			fixture_path = arg.trim_prefix("--recording=")
	if not open_udp_player():
		return
	var file := FileAccess.open(fixture_path, FileAccess.READ)
	var fixture = file.get_var() if file != null else null
	if not fixture is Dictionary or fixture.recording.build_id != model.build.build_id:
		check(false, "load replay fixture for the same build")
		finish()
		return
	send("HELLO paper-udp-combat")
	aim(Vector2(960, 540))
	await paint()
	check(gun.valid, "tracking accepts simulated aim")
	var frames := []
	while device.get_available_packet_count() > 0:
		frames.append(device.get_packet().get_string_from_ascii())
	check(frames.has("FRAME 24,48"), "player advertises the white and dark frame widths")
	results["frame_packets"] = frames
	var handoffs := {}
	for entry in fixture.handoffs:
		handoffs[entry.station] = entry.tick
	await puddle(fixture.recording)
	await bridge(fixture.recording, handoffs.footbridge)
	await platform(fixture.recording, handoffs.platform)
	await check_http_triggers()
	finish()
