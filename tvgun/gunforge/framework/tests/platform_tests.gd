extends "train_stop_probe.gd"
## Verify the platform signal gates only the exposed umbrella and that rescue stays precise.

const SIGNAL := "platform.lamp"
const LIGHT := "platform.light"
const CROW := "platform.crow"
const CANOPY := "platform.canopy"
const UMBRELLA := "platform.umbrella"
const CLERK := "platform.resident"
const RESCUE := "platform.rescue"

var vulnerable_ticks := 0

func check_failure_and_retry() -> void:
	step_to(187)
	check(not model.entities[LIGHT].active and model.fired.has("platform.crow1.warning"), "crow warns before signal is lit")
	await capture("platform_crow_warning")
	step_to(260)
	check(model.active_effects.values().any(func(effect): return effect.effect == "crow_release")
		and model.resources.lives == 5, "crow release is visible before damage")
	await capture("platform_crow_attack")
	step_to(420)
	check(model.resources.lives == 4 and model.fired.has("platform.umbrella1.warning"), "both threats engage with the signal dark")
	step_to(486)
	check(model.active_effects.values().any(func(effect): return effect.effect == "umbrella_release")
		and model.resources.lives == 4, "umbrella release is visible before damage")
	await capture("platform_umbrella_attack")
	step_to(1100)
	check(model.result == "overrun" and model.resources.lives == 0, "untreated attacks fail the run")
	model.start()
	check(model.resources.lives == 5 and model.resources.ammo == 12 and model.resources.rescued == 0, "retry resets resources")

func check_signal_expiry() -> void:
	var saved: Dictionary = model.save_state()
	var expiry: int = model.tick + 360
	while model.tick < expiry and model.phase == "running":
		if model.effective_kind(model.entities[UMBRELLA]) == "primary":
			vulnerable_ticks += 1
		model.step()
	check(vulnerable_ticks >= 260, "signal gives a full aiming window after the canopy folds")
	check(not model.entities[LIGHT].active and model.effective_kind(model.entities[UMBRELLA]) == "invalid", "signal expiry hardens the umbrella")
	check(shoot(SIGNAL).get("target") == SIGNAL and model.entities[LIGHT].active, "signal can be relit after expiry")
	model.restore_state(saved)

func play() -> void:
	check(model.current_section == "platform", "opens on the platform")
	await capture("platform_off")
	check(shoot(CROW).get("target") == CROW and model.entities[CROW].health == 0, "crow can be intercepted with the signal off")
	check(shoot(CANOPY).get("kind") == "invalid", "open umbrella canopy is invalid")
	check(shoot(CLERK).get("kind") == "protected" and model.resources.rescued == 0, "the clerk body is protected")
	check(shoot("layer.platform.near_left_luggage").get("kind") == "blocker", "left luggage blocks the submitted shot")
	check(shoot("layer.platform.near_right_luggage").get("kind") == "blocker", "right luggage blocks the submitted shot")
	step_to(151)
	check(shoot(CANOPY).get("kind") == "blocker", "canopy blocks during the fold")
	await capture("platform_folding")
	step_to(189)
	check(shoot(UMBRELLA).get("kind") == "invalid" and model.entities[UMBRELLA].health > 0, "folded umbrella remains hard in darkness")
	await capture("platform_folded_dark")
	var ammo: int = model.resources.ammo
	check(shoot(SIGNAL).get("target") == SIGNAL and model.resources.ammo == ammo - 1 and model.entities[LIGHT].active,
		"signal consumes one round and lights the platform")
	check_signal_expiry()
	step_to(234)
	check(model.effective_kind(model.entities[UMBRELLA]) == "primary", "lit umbrella body becomes vulnerable")
	await capture("platform_lit")
	check(shoot(UMBRELLA).get("target") == UMBRELLA and model.entities[UMBRELLA].health == 0, "lit folded umbrella can be purified")
	check(shoot(RESCUE).get("target") == RESCUE and model.resources.rescued == 1, "chest ink is the only rescue target")
	step_to(305)
	await capture("platform_rescued")
	step_to(350)
	check(model.result == "clear" and model.resources.lives == 5 and model.resources.score == 250,
		"platform clears with all lives and the protected-hit penalty")
	check(not model.fired.has("platform.crow1.release") and not model.fired.has("platform.umbrella1.release"),
		"purification cancels both attacks")

func run() -> void:
	if not open_candidate():
		quit(2)
		return
	await check_failure_and_retry()
	await play()
	print(JSON.stringify({"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"gpu_capture": viewport != null, "shots": model.shots, "lives": model.resources.lives,
		"rescued": model.resources.rescued, "signal_vulnerable_ticks": vulnerable_ticks}))
	quit(0 if failures.is_empty() else 1)
