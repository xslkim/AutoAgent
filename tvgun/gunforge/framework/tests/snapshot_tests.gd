extends SceneTree
var game
func _initialize():call_deferred("run")
func run():
	game = load("res://main.tscn").instantiate()
	root.add_child(game)
	game.sound.enabled = false
	game.set_process(false)
	game.set_process_unhandled_input(false)
	game.fixed = true
	game.debug_command({"op":"input","event":"START"})
	game.debug_command({"op":"step","frames":210})
	var point = game.scene.aim_points.lamp+Vector2(72,72)
	game.dispatch({"event":"SHOT","aim":point})
	# Binary roundtrip preserves native vectors/transforms; no object deserialization.
	var bytes = var_to_bytes(game.replay_snapshot())
	var saved = bytes_to_var(bytes)
	game.simulation_clock.step(game.fixed_tick)
	game.debug_command({"op":"step","frames":90})
	var expected = var_to_bytes(game.model.save_state())
	var expected_input = game.last_consumed_input.duplicate(true)
	game.restore_replay_snapshot(saved)
	game.link.shot_sequences[99] = true
	game.restore_replay_snapshot(saved)
	var immutable = not game.link.shot_sequences.has(99)
	game.simulation_clock.step(game.fixed_tick)
	game.debug_command({"op":"step","frames":90})
	var ok = immutable and expected == var_to_bytes(game.model.save_state()) and expected_input == game.last_consumed_input
	print(JSON.stringify({"passed":ok,"snapshot_bytes":bytes.size(),"pending_shot_replayed":game.model.ammo==5,"model_bit_exact":expected==var_to_bytes(game.model.save_state()),"restore_does_not_mutate_snapshot":immutable}))
	game.queue_free()
	await process_frame
	quit(0 if ok else 1)
