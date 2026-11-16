extends "res://tools/level_player.gd"
## Run with the compiled Paper Lantern City campaign and --transitions-dir.

var problems: Array[String] = []

func require(condition: bool, message: String) -> void:
	if not condition:
		problems.append(message)

func open():
	super.open()
	if model == null:
		return
	call_deferred("exercise_transitions")

func exercise_transitions() -> void:
	require(transition_clips.size() == 15, "campaign must load every transition")
	var book: Variant = JSON.parse_string(FileAccess.get_file_as_string(transition_directory.path_join("transitions.json")))
	if not book is Dictionary:
		quit(1)
		return
	var boundaries := {
		"cinema.ticket_office": "story.cinema_intro",
		"waiting_room": "story.train_station_intro",
		"lantern_base.workbench": "lantern_base.pullback",
	}
	for clip in book.transitions:
		previous_scene = clip.from
		var destination := String(clip.to)
		model.current_section = boundaries.get(destination, destination if "." in destination else destination + ".arrival")
		check_transition()
		require(transition != null, "missing transition " + clip.file)
		if transition == null:
			continue
		require(transition.video.is_playing(), "video did not start " + clip.file)
		require(transition.position == preview.position and transition.size == preview.size, "clip escaped content rect")
		require(session.pause_reasons.has("transition"), "gameplay did not pause")
		var tick := int(session.clock.tick)
		session.advance(0.2)
		require(session.clock.tick == tick, "gameplay tick advanced during playback")
		require(not session.enqueue("SHOT", Vector2(600, 400)), "shot accepted during transition")
		var state: Dictionary = handle_http("STATE", {}, Callable())
		require(state.lifecycle == "transition" and not state.shot_input_enabled, "remote state did not report transition")
		var shot: Dictionary = handle_http("SHOT", {"x": .5, "y": .5}, Callable())
		require(not shot.ok, "remote shot accepted during transition")
		if clip == book.transitions[0]:
			await create_timer(4).timeout
			require(transition == null, "natural video completion did not resume gameplay")
		else:
			enqueue_device({"event": "START"})
			require(transition == null, "START did not skip video")
		require(not session.pause_reasons.has("transition"), "transition pause did not clear")
		check_transition()
		require(transition == null, "scene change played twice")
	var clock := preload("res://core/fixed_clock.gd").new()
	var visited: Array[int] = []
	clock.advance_frame(0.2, func(at, _dt): visited.append(at), func(): return visited.size() == 1)
	require(visited == [1] and clock.debt == 0, "catch-up continued beyond transition tick")
	print(JSON.stringify({"transitions_tested": book.transitions.size(), "failures": problems}))
	gun.close()
	http.close()
	discovered_http.close()
	quit(0 if problems.is_empty() else 1)
