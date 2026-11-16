extends "train_stop_probe.gd"
## Verify both lantern-base lanes and the visible rim used for the camera handoff.

const LAMP := "lantern_base.lamp"
const LIGHT := "lantern_base.light"
const CROW := "lantern_base.crow"
const CANOPY := "lantern_base.canopy"
const UMBRELLA := "lantern_base.umbrella"
const RIM := "lantern_base.base_rim"
const PULLBACK_ORIGIN := Vector2(888, 723)

var joint_light_window := 0
var exit_anchor := Vector2.ZERO

func rim_anchor() -> Vector2:
	var layer: Dictionary = model.level.presentation.layers[RIM]
	var point: Vector2 = PULLBACK_ORIGIN + model.camera_shift() * float(layer.parallax)
	for item in model.layer_items():
		if item.id == "layer." + RIM and item.sample(point).a >= .5:
			return point
	return Vector2.ZERO

func check_dark_failure_and_retry() -> void:
	step_to(184)
	check(not model.entities[CANOPY].active and model.effective_kind(model.entities[UMBRELLA]) == "invalid",
		"the closed umbrella hardens with the lamp off")
	check(model.effective_kind(model.entities[CROW]) == "invalid", "crow is hardened with the lamp off")
	await capture("lantern_base_folded_dark")
	step_to(215)
	check(model.fired.has("lantern_base.crow1.warning") and not model.entities[LIGHT].active,
		"crow warns in darkness")
	step_to(290)
	check(model.active_effects.values().any(func(effect): return effect.effect == "crow_release")
		and model.resources.lives == 5, "crow strike appears before damage")
	await capture("lantern_base_crow_attack")
	step_to(470)
	check(model.active_effects.values().any(func(effect): return effect.effect == "umbrella_release")
		and model.resources.lives == 4, "umbrella strike appears in darkness before damage")
	await capture("lantern_base_umbrella_attack")
	step_to(1100)
	check(model.result == "overrun" and model.resources.lives == 0, "uninterrupted attacks fail the encounter")
	model.start()
	check(model.resources.lives == 5 and model.resources.ammo == 12 and model.shots == 0, "retry resets the lantern base")

func check_shared_light_window() -> void:
	var saved: Dictionary = model.save_state()
	var deadline: int = model.tick + 360
	var streak := 0
	while model.tick < deadline and model.phase == "running":
		if model.effective_kind(model.entities[CROW]) == "primary" and model.effective_kind(model.entities[UMBRELLA]) == "primary":
			streak += 1
			joint_light_window = maxi(joint_light_window, streak)
		else:
			streak = 0
		model.step()
	check(joint_light_window >= 120, "one activation gives both threats at least two seconds of joint vulnerability")
	check(not model.entities[LIGHT].active and model.effective_kind(model.entities[UMBRELLA]) == "invalid",
		"expired light hardens the umbrella again")
	check(shoot(LAMP).get("target") == LAMP and model.entities[LIGHT].active, "station lamp can be relit")
	model.restore_state(saved)

func play() -> void:
	check(model.current_section == "lantern_base", "opens in the lantern base")
	check(rim_anchor() != Vector2.ZERO, "pullback anchor starts on the opaque rim")
	await capture("lantern_base_off")
	check(shoot("layer.lantern_base.near_left_brace").get("kind") == "blocker", "left brace blocks shots")
	check(shoot("layer.lantern_base.near_right_brace").get("kind") == "blocker", "right brace blocks shots")
	check(shoot(CANOPY).get("kind") == "invalid", "open umbrella is not damageable")
	var ammo: int = model.resources.ammo
	check(shoot(LAMP).get("target") == LAMP and model.resources.ammo == ammo - 1 and model.entities[LIGHT].active,
		"station lamp consumes one round and lights")
	step_to(52)
	check(model.effective_kind(model.entities[CROW]) == "invalid", "active lamp does not soften the crow outside the spill")
	step_to(153)
	check(shoot(CANOPY).get("kind") == "blocker", "umbrella canopy blocks during the fold")
	await capture("lantern_base_folding")
	step_to(184)
	check(model.effective_kind(model.entities[CROW]) == "primary" and model.effective_kind(model.entities[UMBRELLA]) == "primary",
		"both threats soften under the same light after the umbrella folds")
	await capture("lantern_base_lit")
	check_shared_light_window()
	check(shoot(CROW).get("target") == CROW and model.entities[CROW].health == 0, "crow is purified")
	check(shoot(UMBRELLA).get("target") == UMBRELLA and model.entities[UMBRELLA].health == 0, "umbrella is purified")
	check(not model.input_enabled and model.phase == "running", "cleared combat releases control before the handoff")
	step_to(255)
	exit_anchor = rim_anchor()
	check(exit_anchor != Vector2.ZERO, "pullback anchor stays on the moving rim after the clear")
	await capture("lantern_base_handoff")
	step_to(325)
	check(model.result == "clear" and model.resources.lives == 5 and model.resources.score == 200, "clear without damage")
	check(not model.fired.has("lantern_base.crow1.release") and not model.fired.has("lantern_base.umbrella1.release"),
		"purification cancels both attacks")

func run() -> void:
	if not open_candidate():
		quit(2)
		return
	await check_dark_failure_and_retry()
	await play()
	print(JSON.stringify({"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"gpu_capture": viewport != null, "shots": model.shots, "lives": model.resources.lives,
		"joint_light_window_ticks": joint_light_window,
		"pullback_origin": [PULLBACK_ORIGIN.x, PULLBACK_ORIGIN.y], "exit_anchor": [exit_anchor.x, exit_anchor.y]}))
	quit(0 if failures.is_empty() else 1)
