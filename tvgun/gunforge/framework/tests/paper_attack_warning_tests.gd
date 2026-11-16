extends "train_station_tests.gd"
## Replay the cast campaign through two authored attack sequences.

const Audio = preload("res://core/level_audio.gd")
const CART := "footbridge.bridge.cyclist"
const CART_ATTACK := "footbridge.bridge.cart1"
const REACTION := "footbridge.bridge.cyclist_reaction"
const RIDER := "footbridge.bridge.cyclist_resident"
const BELL := "footbridge.bell"
const SIDES := ["left", "center", "right"]

var audio := Audio.new()
var frames: Array[Dictionary] = []

func event_tick(id: String) -> int:
	for entry in model.trace:
		if entry.get("event_id") == id:
			return int(entry.tick)
	return -1

func expected_tick(id: String) -> int:
	var trigger: Dictionary = model.level.events[id].trigger
	var due: int = model.fired_time[trigger.after] + int(trigger.delay_ms) * int(model.level.tick_hz)
	return ceili(due / 1000.0)

func advance_event(id: String) -> int:
	var expected := expected_tick(id)
	step_to(expected)
	check(event_tick(id) == expected, "authored timing for " + id)
	return expected

func cue_at(cue: String, at: int) -> Dictionary:
	audio.sync()
	var matches: Array = model.active_cues.keys().filter(func(key):
		var instance: Dictionary = model.active_cues[key]
		return instance.cue == cue and instance.start_tick == at
	)
	check(matches.size() == 1, "one same-tick audio envelope for " + cue)
	if matches.size() != 1:
		return {}
	var key: String = matches[0]
	var player: AudioStreamPlayer = audio.players.get(key)
	check(player != null and player.stream is AudioStreamWAV and player.stream.get_length() > 0.0
		and player.playing, "Godot starts the decoded cue " + cue)
	var row: Dictionary = model.active_cues[key].duplicate()
	if player != null and player.stream != null:
		row["decoded_seconds"] = player.stream.get_length()
		row["volume_db"] = player.volume_db
		row["resource"] = model.level.cues[cue].resource
	return row

func seek_branch(at: int) -> void:
	session.seek(at)
	session.tape.clear()
	audio.sync(true)

func restore_branch(state: Dictionary) -> void:
	session.restore(state)
	audio.sync(true)

func capture_pair(stem: String, label: String, phase: String, effect: String, entity: String, started: int) -> void:
	var before: Dictionary = model.active_effects
	var matches: Array = before.keys().filter(func(key):
		var instance: Dictionary = before[key]
		return instance.effect == effect and instance.entity == entity and instance.start_tick == started
	)
	check(matches.size() == 1, "find exactly one effect for " + stem)
	if matches.size() != 1:
		return
	await capture(stem)
	model.active_effects = before.duplicate()
	model.active_effects.erase(matches[0])
	await capture(stem + "_reference")
	model.active_effects = before
	frames.append({"frame": stem, "label": label, "phase": phase, "state": "warning", "effect": effect,
		"entity": entity, "section": model.current_section, "tick": model.tick, "effect_age_ticks": model.tick - started})

func observe_damage(id: String, at: int, expected_loss: int) -> Dictionary:
	step_to(at - 1)
	var lives: int = model.resources.lives
	step_to(at)
	var fired := event_tick(id)
	var correct_event := fired == at if expected_loss > 0 else fired < 0
	check(correct_event and model.resources.lives == lives - expected_loss,
		"expected loss of %d lives for %s" % [expected_loss, id])
	return {"tick": at, "lives_before": lives, "lives_after": model.resources.lives}

func bridge(at: int) -> Dictionary:
	seek_branch(at)
	var warning := advance_event(CART_ATTACK + ".warn")
	var bell := cue_at(BELL, warning)
	check(event_tick("footbridge.bridge.cyclist_resident.react1") == warning and model.entities[REACTION].visible
		and not model.entities[RIDER].visible, "the upper-deck cyclist reacts on the bell tick")
	var branch: Dictionary = session.snapshot()
	step_to(warning + 12)
	await capture_pair("bridge_warning_early", "天桥 · 铃响甩墨", "预警 200 ms", "footbridge.cart_warn", CART, warning)
	var settled := advance_event("footbridge.bridge.cyclist_resident.react1.end")
	check(model.entities[RIDER].visible and not model.entities[REACTION].visible, "cyclist returns to idle on schedule")
	step_to(warning + 60)
	await capture_pair("bridge_warning_late", "天桥 · 铃响甩墨", "预警 1000 ms", "footbridge.cart_warn", CART, warning)
	var release := advance_event(CART_ATTACK + ".release")
	var launch_audio := cue_at(model.level.presentation.sound_bindings["attack.launched"], release)
	step_to(release + 8)
	await capture_pair("bridge_release", "天桥 · 甩墨", "墨流离手 133 ms", "footbridge.cart_spit", CART, release)
	var damage_id := CART_ATTACK + ".hit"
	var damage := observe_damage(damage_id, expected_tick(damage_id), 1)
	restore_branch(branch)
	var reply := shoot(CART)
	var interrupted_damage := observe_damage(damage_id, damage.tick, 0)
	check(reply.get("target") == CART and event_tick(CART_ATTACK + ".release") < 0,
		"shooting the warned cart cancels its release")
	return {"entry_tick": at, "warning_tick": warning, "bell": bell, "resident_idle_tick": settled,
		"release_tick": release, "release_audio": launch_audio, "damage": damage,
		"interrupted": reply, "interrupted_damage": interrupted_damage}

func cinema(slot: int, branch: Dictionary) -> Dictionary:
	restore_branch(branch)
	var side: String = SIDES[slot]
	var projector := "cinema.projector_" + side
	var tape := "cinema.sweep_tape_%d" % (slot + 1)
	var sweep := projector + ".sweep"
	var side_name: String = ["左", "中", "右"][slot]
	var label := "影院 · " + side_name + "放映机"
	var sweep_tick := advance_event(sweep)
	var matching: Array = model.active_effects.values().filter(func(effect):
		return effect.effect == "cinema.sweep_fx" and effect.entity == tape and effect.start_tick == sweep_tick
	)
	check(matching.size() == 1 and matching[0].get("source") == projector + ".lens"
		and not model.entities[tape].active, "sweep starts at the correct lens before spawning " + tape)
	step_to(sweep_tick + 18)
	await capture_pair(side + "_sweep", label, "墨光扫过 300 ms", "cinema.sweep_fx", tape, sweep_tick)
	var spawn_tick := advance_event(sweep + ".spawn")
	check(model.entities[tape].active, "projector spawns its own tape")
	var warn_tick := advance_event(tape + ".warn")
	var warning_audio := cue_at(model.level.presentation.sound_bindings["attack.warning"], warn_tick)
	step_to(warn_tick + 12)
	await capture_pair(side + "_warning_early", label, "磁带预警 200 ms", "cinema.warn_fx", tape, warn_tick)
	step_to(warn_tick + 60)
	await capture_pair(side + "_warning_late", label, "磁带预警 1000 ms", "cinema.warn_fx", tape, warn_tick)
	var damage_id := tape + ".damage"
	var damage := observe_damage(damage_id, expected_tick(damage_id), 1)

	restore_branch(branch)
	var interruption_ticks := [sweep_tick - 9, sweep_tick + 9, warn_tick + 12]
	step_to(interruption_ticks[slot])
	var reel := "cinema.reel_" + side
	var reply := shoot(reel)
	var interrupted_damage := observe_damage(damage_id, damage.tick, 0)
	check(reply.get("target") == reel and not model.entities[tape].active,
		"purifying the reel leaves no active " + tape)
	check((event_tick(sweep) >= 0) == (slot > 0) and (event_tick(sweep + ".spawn") >= 0) == (slot == 2),
		"reel cut exercises the intended phase for " + tape)
	return {"side": side, "sweep_tick": sweep_tick, "spawn_tick": spawn_tick, "warning_tick": warn_tick,
		"warning_audio": warning_audio, "damage": damage, "interrupted": reply,
		"interrupted_damage": interrupted_damage, "interrupt_tick": model.entities[reel].defeated_at}

func run() -> void:
	if not open_candidate() or viewport == null:
		quit(2)
		return
	var path := ""
	var asset_root := ""
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--recording="):
			path = argument.trim_prefix("--recording=")
		if argument.begins_with("--assets="):
			asset_root = argument.trim_prefix("--assets=")
	var file := FileAccess.open(path, FileAccess.READ)
	var fixture = file.get_var() if file != null else null
	if not fixture is Dictionary or fixture.get("recording", {}).get("build_id") != model.build.build_id:
		push_error("Expected a campaign recording for this build")
		quit(2)
		return
	var entries := {}
	for entry in fixture.handoffs:
		entries[entry.station] = int(entry.tick)
	if not entries.has_all(["footbridge", "screen_stage"]):
		push_error("Expected bridge and cinema handoffs")
		quit(2)
		return
	session.setup(model)
	session.load_recording(fixture.recording)
	root.add_child(audio)
	audio.setup(model, asset_root)
	audio.enabled = true
	model.set_presentation_context("player", "running")
	var bridge_result := await bridge(entries.footbridge)
	# Reload the full fixture after branching the tape at the bridge.
	session.load_recording(fixture.recording)
	seek_branch(entries.screen_stage)
	var branch: Dictionary = session.snapshot()
	var projectors := []
	for slot in SIDES.size():
		projectors.append(await cinema(slot, branch))
	var evidence := {"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"source_revision": model.build.source_revision, "gpu": RenderingServer.get_video_adapter_name(),
		"bridge": bridge_result, "screen_entry_tick": entries.screen_stage, "projectors": projectors, "frames": frames}
	var receipt := FileAccess.open(captures.path_join("samples.json"), FileAccess.WRITE)
	if receipt == null:
		quit(2)
		return
	receipt.store_string(JSON.stringify(evidence, "  ") + "\n")
	print(JSON.stringify(evidence))
	audio.clear()
	quit(0 if failures.is_empty() else 1)
