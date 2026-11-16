extends "train_stop_probe.gd"
## Exercise the crow's occlusion and light transitions in the train car.

const LAMP := "green_car.lamp"
const LIGHT := "green_car.light"
const CROW := "green_car.crow"
const CANOPY := "green_car.canopy"
const UMBRELLA := "green_car.umbrella"
const LEFT_SEAT := "layer.green_car.near_left_seat"
const RIGHT_SEAT := "layer.green_car.near_right_seat"

var longest_light_window := 0

func check_covered_crow() -> void:
	var assets: Dictionary = model.geometry_assets()
	var pose := Codec.decode(Codec.encode(model.geometry(), assets), assets)
	for item in pose:
		if item.id != CROW:
			continue
		var area: Rect2 = item.bounds()
		for y in range(ceili(area.position.y), floori(area.end.y), 4):
			for x in range(ceili(area.position.x), floori(area.end.x), 4):
				var point := Vector2(x, y)
				if item.sample(point).a >= .5 and model.resolver.exact(point, pose).get("id") == LEFT_SEAT:
					var result: Dictionary = model.command("SHOT", point, pose)
					check(result.get("kind") == "blocker" and model.entities[CROW].health > 0, "seat blocks the crow behind it")
					model.step()
					return
	failures.append("left seat and entry crow do not overlap")

func check_unlit_attack_and_retry() -> void:
	step_to(223)
	check(model.fired.has("green_car.crow1.warning") and not model.entities[LIGHT].active, "crow warns in darkness")
	check(model.effective_kind(model.entities[UMBRELLA]) == "primary", "closed umbrella is vulnerable with the ceiling lamp off")
	await capture("green_car_warning")
	step_to(295)
	check(model.active_effects.values().any(func(effect): return effect.effect == "crow_release")
		and model.resources.lives == 5, "crow releases a visible strike before damage")
	await capture("green_car_crow_attack")
	step_to(336)
	check(model.resources.lives == 4, "uninterrupted crow attack damages the player")
	step_to(1100)
	check(model.result == "overrun" and model.resources.lives == 0, "uninterrupted attacks fail the run")
	model.start()
	check(model.resources.lives == 5 and model.resources.ammo == 12 and model.shots == 0, "retry resets the car encounter")

func check_patrol_and_relight() -> void:
	var saved: Dictionary = model.save_state()
	var expiry: int = model.tick + 360
	var streak := 0
	var hardened_after_exit := false
	while model.tick < expiry and model.phase == "running":
		if model.effective_kind(model.entities[CROW]) == "primary":
			streak += 1
			longest_light_window = maxi(longest_light_window, streak)
		else:
			hardened_after_exit = hardened_after_exit or (longest_light_window > 0 and model.active_opacity(model.entities[LIGHT]) > .95)
			streak = 0
		model.step()
	check(longest_light_window >= 120 and hardened_after_exit, "crow softens in the spill and hardens after exiting while lit")
	check(not model.entities[LIGHT].active, "ceiling lamp expires")
	check(shoot(LAMP).get("target") == LAMP and model.entities[LIGHT].active, "ceiling lamp can be relit")
	model.restore_state(saved)

func play() -> void:
	check(model.current_section == "green_car", "opens in the green car")
	await capture("green_car_entry")
	check_covered_crow()
	check(shoot(RIGHT_SEAT).get("kind") == "blocker", "right seat blocks the submitted shot")
	check(shoot(CANOPY).get("kind") == "invalid", "fully open umbrella is invalid")
	var ammo: int = model.resources.ammo
	check(shoot(LAMP).get("target") == LAMP and model.resources.ammo == ammo - 1 and model.entities[LIGHT].active,
		"ceiling lamp consumes one round and lights")
	check_patrol_and_relight()
	step_to(62)
	check(model.effective_kind(model.entities[CROW]) == "invalid", "crow remains hard outside the lit area")
	await capture("green_car_outside_spill")
	step_to(112)
	check(model.effective_kind(model.entities[CROW]) == "primary", "crow softens after entering the spill")
	await capture("green_car_lit")
	check(shoot(CROW).get("target") == CROW and model.entities[CROW].health == 0, "softened crow can be purified")
	step_to(153)
	check(shoot(CANOPY).get("kind") == "blocker", "moving umbrella blocks during the fold")
	await capture("green_car_folding")
	step_to(188)
	check(shoot(UMBRELLA).get("target") == UMBRELLA and model.entities[UMBRELLA].health == 0, "fold exposes the umbrella ink")
	step_to(235)
	await capture("green_car_clear")
	step_to(305)
	check(model.result == "clear" and model.resources.lives == 5 and model.resources.score == 200, "car clears without damage")
	check(not model.fired.has("green_car.crow1.release") and not model.fired.has("green_car.umbrella1.release"),
		"purification cancels both attacks")

func run() -> void:
	if not open_candidate():
		quit(2)
		return
	await check_unlit_attack_and_retry()
	await play()
	print(JSON.stringify({"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"gpu_capture": viewport != null, "shots": model.shots, "lives": model.resources.lives,
		"longest_light_window_ticks": longest_light_window}))
	quit(0 if failures.is_empty() else 1)
