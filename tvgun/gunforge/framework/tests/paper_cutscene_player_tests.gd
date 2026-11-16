extends "res://tools/level_player.gd"
## Exercise the opening and epilogue through the isolated production player.

const TAPE := "lantern_base.ending.tape"
const ENDING := ["lantern_base.ending_light", "lantern_base.ending_city",
	"lantern_base.ending_wide", "lantern_base.ending_quote"]
const VOICE := [
	{"section": "lantern_base.ending_city", "text": "夜市的灯，又亮了起来。", "times": [9.0, 11.56]},
	{"section": "lantern_base.ending_quote", "text": "灯亮着，就还在。", "times": [49.0, 51.24]},
]

var failures: Array[String] = []
var device := PacketPeerUDP.new()
var sequence := 0
var live_ticks := false
var pending_delta := 0.0
var output_dir := ""
var frames: Dictionary = {}

func check(passed: bool, message: String) -> void:
	if not passed:
		failures.append(message)

func _process(delta):
	var step: float = delta if live_ticks else pending_delta
	pending_delta = 0.0
	super._process(step)

func keypress(key: Key) -> void:
	var input := InputEventKey.new()
	input.keycode = key
	input.pressed = true
	root.push_input(input, true)

func send(packet: String) -> void:
	check(device.put_packet(packet.to_ascii_buffer()) == OK, "send UDP " + packet)

func track() -> void:
	network = true
	sequence += 1
	send("960,540,4,%d" % sequence)
	for attempt in range(30):
		await process_frame
		if gun.valid:
			break
	check(gun.valid, "simulated lightgun is tracked")

func capture(name: String, opening_frame := false) -> void:
	if output_dir.is_empty():
		return
	await process_frame
	await RenderingServer.frame_post_draw
	var view: Viewport = root if opening_frame else preview.native_viewport
	frames[name] = view.get_texture().get_image()

func counts() -> Dictionary:
	return {"lives": model.resources.lives, "ammo": model.resources.ammo, "score": model.resources.score,
		"rescued": model.resources.rescued, "shots": model.shots}

func tape_id() -> String:
	for id in model.active_cues:
		if model.active_cues[id].cue == TAPE:
			return id
	return ""

func opening_test(path: String) -> Dictionary:
	check(opening_pending and not opening.visible and model.tick == 0 and menu_action() == "start",
		"player opens on the start card")
	if path == "udp":
		await track()
		send("START")
	else:
		keypress(KEY_ENTER)
	for attempt in range(30):
		await process_frame
		if opening.visible:
			break
	check(opening.visible and opening.video.is_playing() and session.pause_reasons.has("ready"),
		"first input opens the video with combat paused")
	if not opening.visible:
		return {}
	var started := Time.get_ticks_msec()
	var latest := 0.0
	var captions := {}
	var gap_checked := false
	var before := counts()
	var skip_sent := false
	while opening.visible and Time.get_ticks_msec() - started < 105000:
		await process_frame
		if not opening.visible:
			break
		var position := opening.video.stream_position
		latest = maxf(latest, position)
		check(model.tick == 0 and counts() == before, "combat holds during opening")
		if path != "natural":
			if position >= .35 and not skip_sent:
				skip_sent = true
				if path == "udp":
					send("EXIT")
				else:
					keypress(KEY_ESCAPE)
			if Time.get_ticks_msec() - started > 5000:
				break
			continue
		if not gap_checked and position >= .5 and position < 1.8:
			check(opening.subtitle.text.is_empty(), "opening gap is subtitle-free")
			gap_checked = true
		for index in opening.captions.size():
			if captions.has(index):
				continue
			var line: Dictionary = opening.captions[index]
			var center := (float(line.start) + float(line.end)) / 2.0
			if position >= center and position < float(line.end):
				var matches: bool = opening.subtitle.text == line.text
				check(matches, "opening subtitle %d displays inside its interval" % (index + 1))
				captions[index] = {"text": opening.subtitle.text, "media_seconds": position, "matches": matches}
				if index == 0:
					await capture("opening_caption", true)
	check(not opening.visible and not opening.video.is_playing() and not session.pause_reasons.has("ready")
		and counts() == before and model.shots == 0, "opening exits to an unspent first station")
	if path == "natural":
		check(latest >= 89.0 and captions.size() == opening.captions.size() and gap_checked,
			"opening plays to the end and renders every caption")
	else:
		check(skip_sent and latest < 5.0, "opening skip is taken promptly")
	return {"path": path, "last_media_seconds": latest, "caption_samples": captions.values(),
		"caption_gap_checked": gap_checked, "tick_after_opening": model.tick, "combat_counters": counts()}

func prepare_ending(state: Dictionary, offset := 0) -> String:
	live_ticks = false
	network = false
	audio.clear()
	session.restore(state)
	session.tape.clear()
	session.real_time_inputs = true
	var target: int = model.tick + offset
	while model.tick < target:
		session.step()
	var id := tape_id()
	check(not id.is_empty() and not model.input_enabled and model.phase == "running", "ending starts with live tape and combat locked")
	audio.sync()
	var speaker: AudioStreamPlayer = audio.players.get(id)
	check(speaker != null and speaker.playing and absf(speaker.stream.get_length() - 58.0) < .001,
		"production player decodes and starts the 58-second tape")
	return id

func natural_ending(state: Dictionary) -> Dictionary:
	var id := prepare_ending(state)
	if id.is_empty() or not audio.players.has(id):
		return {}
	var start: int = model.active_cues[id].start_tick
	var expected_counts := counts()
	var started := Time.get_ticks_msec()
	var phase_times := {}
	var voice := []
	var next_marker := 0
	live_ticks = true
	while model.phase == "running" and Time.get_ticks_msec() - started < 70000:
		var section: String = model.current_section
		var seconds: float = (model.tick - start) / 60.0
		if not phase_times.has(section):
			phase_times[section] = seconds
		if next_marker < 4 and audio.players.has(id):
			var line: Dictionary = VOICE[next_marker / 2]
			var expected: float = line.times[next_marker % 2]
			var speaker: AudioStreamPlayer = audio.players[id]
			var position := speaker.get_playback_position()
			if position >= expected:
				var subtitle: String = model.level.sections[section].get("hint", "")
				check(section == line.section and subtitle == line.text, "voice marker has its authored subtitle")
				voice.append({"marker_seconds": expected, "audio_seconds": position, "simulation_seconds": seconds,
					"drift_seconds": position - seconds, "section": section, "subtitle": subtitle})
				if next_marker % 2 == 0:
					await capture("ending_voice_%d" % next_marker)
				next_marker += 1
		await process_frame
	live_ticks = false
	var duration: float = (model.tick - start) / 60.0
	check(model.result == "clear" and model.current_section == ENDING[-1] and counts() == expected_counts
		and tape_id().is_empty() and not audio.players.has(id), "natural ending stops audio and preserves the clear result")
	check(absf(duration - 58.0) <= .04 and voice.size() == 4 and phase_times.size() == 4, "all four phases and both lines play in 58 seconds")
	await capture("ending_result")
	return {"duration_seconds": duration, "wall_seconds": (Time.get_ticks_msec() - started) / 1000.0,
		"phase_times": phase_times, "voice_samples": voice, "counters": counts(),
		"tape_stopped": not audio.players.has(id), "result": model.result}

func skip_ending(state: Dictionary, index: int) -> Dictionary:
	var offsets := [24, 520, 1350, 2950]
	var methods := ["Enter", "Esc", "UDP START", "UDP EXIT"]
	var id := prepare_ending(state, offsets[index])
	var section: String = model.current_section
	var before := counts()
	check(section == ENDING[index] and not id.is_empty(), "reach the intended skip phase")
	var pause_checked := false
	if index == 1 and audio.players.has(id):
		keypress(KEY_F2)
		var tick: int = model.tick
		pending_delta = .05
		await process_frame
		await process_frame
		var speaker: AudioStreamPlayer = audio.players[id]
		check(display_setup.visible and speaker.stream_paused and model.tick == tick, "display setup pauses the tape and simulation")
		keypress(KEY_ESCAPE)
		await process_frame
		await process_frame
		check(not display_setup.visible and not speaker.stream_paused, "leaving display setup resumes the tape")
		pause_checked = true
	if index >= 2:
		await track()
		send("START" if index == 2 else "EXIT")
	else:
		keypress(KEY_ENTER if index == 0 else KEY_ESCAPE)
	for attempt in range(30):
		if model.phase == "result":
			break
		pending_delta = 1.0 / 60.0
		await process_frame
	check(model.phase == "result" and model.result == "clear" and model.current_section == ENDING[-1]
		and counts() == before and tape_id().is_empty() and not audio.players.has(id), "skip stops the tape and preserves the result")
	return {"path": methods[index], "section": section, "result": model.result,
		"counters": counts(), "tape_stopped": not audio.players.has(id), "display_pause_checked": pause_checked}

func open():
	var recording := ""
	var path := "natural"
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--recording="):
			recording = argument.trim_prefix("--recording=")
		if argument.begins_with("--opening-case="):
			path = argument.trim_prefix("--opening-case=")
		if argument.begins_with("--evidence="):
			output_dir = argument.trim_prefix("--evidence=")
	isolated_settings = true
	AudioServer.set_bus_mute(0, true)
	super.open()
	if model == null:
		return
	if opening == null or output_dir.is_empty() or DirAccess.make_dir_recursive_absolute(output_dir) != OK:
		push_error("Expected an opening package and evidence directory")
		quit(2)
		return
	check(gun.bind_errors.is_empty() and http.bind_error == OK, "production controls bind")
	check(device.connect_to_host("127.0.0.1", gun.port) == OK, "connect simulated device")
	send("HELLO cutscene-check")
	var opening_result := await opening_test(path)
	var evidence := {"build_id": model.build.build_id, "source_revision": model.build.source_revision,
		"audio_driver": AudioServer.get_driver_name(), "opening": opening_result}
	if path == "natural":
		var file := FileAccess.open(recording, FileAccess.READ)
		var fixture = file.get_var() if file != null else null
		if not fixture is Dictionary or fixture.get("recording", {}).get("build_id") != model.build.build_id:
			push_error("Expected a campaign recording for the current build")
			quit(2)
			return
		var workbench: Array = fixture.handoffs.filter(func(entry): return entry.station == "workbench")
		if workbench.size() != 1:
			push_error("Expected one workbench handoff")
			quit(2)
			return
		session.load_recording(fixture.recording)
		session.seek(workbench[0].tick)
		var deadline: int = model.tick + 500
		while tape_id().is_empty() and model.tick < deadline:
			session.step()
		if tape_id().is_empty() or model.current_section != ENDING[0]:
			push_error("Campaign replay did not reach the tape onset")
			quit(2)
			return
		var start: Dictionary = session.snapshot()
		await process_frame
		evidence["natural_ending"] = await natural_ending(start)
		var skips := []
		for index in ENDING.size():
			skips.append(await skip_ending(start, index))
		evidence["skips"] = skips
		send("START")
		for attempt in range(30):
			if model.phase == "running":
				break
			await process_frame
		var retry: bool = model.phase == "running" and model.current_section == "alley.arrival"
		retry = retry and model.shots == 0 and tape_id().is_empty() and audio.players.is_empty()
		check(retry, "UDP retry resets combat without playing the old tape")
		evidence["retry"] = retry
	# PNG compression and disk writes must not interrupt the playback being measured.
	for name in frames:
		var image: Image = frames[name]
		check(image.save_png(output_dir.path_join(name + ".png")) == OK, "save cutscene frame " + name)
	evidence["passed"] = failures.is_empty()
	evidence["failures"] = failures
	var output := FileAccess.open(output_dir.path_join("checks.json"), FileAccess.WRITE)
	if output == null:
		quit(2)
		return
	output.store_string(JSON.stringify(evidence, "  ") + "\n")
	print(JSON.stringify(evidence))
	device.close()
	gun.close()
	http.close()
	quit(0 if failures.is_empty() else 1)
