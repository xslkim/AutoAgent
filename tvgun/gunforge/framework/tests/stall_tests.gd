extends SceneTree
## Exercise the authored light windows through the actual hit resolver and scheduler.

const Loader = preload("res://core/level_loader.gd")
var model
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, label: String) -> void:
	if not condition:
		failures.append(label)

func step_to(target: int) -> void:
	while model.tick < target and model.phase == "running":
		model.step()

func crow_tint() -> Color:
	for item in model.visual_items():
		if item.id == "crow_1_1":
			return item.tint
	return Color.TRANSPARENT

func has_effect(id: String) -> bool:
	for effect in model.active_effects.values():
		if effect.effect == id:
			return true
	return false

func shoot(target: String) -> Dictionary:
	var pose = model.geometry()
	for item in pose:
		if item.id != target:
			continue
		var area: Rect2 = item.bounds()
		for y in range(ceili(area.position.y), floori(area.end.y), 4):
			for x in range(ceili(area.position.x), floori(area.end.x), 4):
				var point = Vector2(x, y)
				if model.resolver.exact(point, pose).get("id") == target:
					return model.command("SHOT", point, pose)
	return {}

func run() -> void:
	var args = {}
	for arg in OS.get_cmdline_user_args():
		var pair = arg.split("=", true, 1)
		if pair.size() == 2:
			args[pair[0]] = pair[1]
	var compiled = JSON.parse_string(FileAccess.get_file_as_string(args["--build"]))
	model = Loader.open(compiled, args["--assets"])
	if model == null:
		quit(2)
		return
	model.start()
	step_to(108)
	var dark_tint := crow_tint()
	check(shoot("crow_1_1").get("kind") == "invalid" and model.entities.crow_1_1.health == 1, "dark_crow_cannot_be_hurt")
	step_to(120)
	check(shoot("lamp_1").get("hit") == true, "first_lamp_is_shootable")
	model.step()
	var first_open: int = model.tick
	check(model.entities.crow_1_1.kind == "primary" and not model.entities.lamp_cover.active, "light_exposes_target_and_clears_ink")
	check(dark_tint != Color.TRANSPARENT and crow_tint() == Color.WHITE and dark_tint != crow_tint(), "crow_visibly_changes_with_light")
	step_to(first_open + 359)
	check(model.entities.crow_1_1.kind == "primary", "exposure_holds_until_six_seconds")
	model.step()
	check(model.entities.crow_1_1.kind == "invalid" and model.entities.lamp_cover.active, "exposure_closes_at_six_seconds")
	check(crow_tint() == dark_tint, "crow_looks_hardened_again_when_lamp_expires")
	check(shoot("lamp_1").get("hit") == true, "lamp_can_be_relit")
	step_to(model.tick + 12)
	check(shoot("crow_1_1").get("target") == "crow_1_1", "relit_crow_can_be_cleared")
	step_to(model.tick + 130)
	check(model.current_section == "round_2" and model.entities.lamp_2.next_activation < model.tick, "second_round_has_a_fresh_lamp")
	var start: int = model.fired_time["round_2.start"] / 1000
	step_to(start + 184)
	check(model.fired.has("crow_2_1.warning") and model.entities.lamp_2.value == 0 and model.resources.lives == 5, "dark_crow_warns_without_player_lighting_the_lamp")
	var dark_checkpoint = model.save_state()
	step_to(start + 292)
	check(model.fired.has("crow_2_1.release") and has_effect("stall_slash") and model.resources.lives == 5, "release_draws_slash_before_damage")
	step_to(start + 331)
	check(model.entities.lamp_2.value == 0 and model.resources.lives == 4 and has_effect("player_hurt"), "dark_crow_attack_lands_with_hit_feedback")
	model.restore_state(dark_checkpoint)
	check(shoot("lamp_2").get("hit") == true, "second_lamp_can_be_hit_immediately")
	step_to(model.tick + 10)
	var checkpoint = bytes_to_var(var_to_bytes(model.save_state()))
	check(shoot("crow_2_1").get("target") == "crow_2_1", "shot_hits_during_warning")
	step_to(start + 390)
	check(not model.fired.has("crow_2_1.release") and not model.fired.has("crow_2_1.attack") and model.fired.has("crow_2_2.attack") and model.resources.lives == 4, "only_the_uninterrupted_crow_deals_damage")
	var expected = var_to_bytes(model.save_state())
	model.restore_state(checkpoint)
	shoot("crow_2_1")
	step_to(start + 390)
	check(expected == var_to_bytes(model.save_state()), "warning_checkpoint_replays_bit_exactly")

	var report = {"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id}
	if args.has("--report"):
		var output = FileAccess.open(args["--report"], FileAccess.WRITE)
		output.store_string(JSON.stringify(report, "\t"))
	print(JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
