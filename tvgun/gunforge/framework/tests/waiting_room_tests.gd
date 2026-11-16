extends "train_stop_probe.gd"
## Exercise the waiting room through the shared player and submitted hit geometry.

const LAMP := "waiting_room.lamp"
const LIGHT := "waiting_room.light"
const CROW := "waiting_room.crow"
const CANOPY := "waiting_room.canopy"
const UMBRELLA := "waiting_room.umbrella"
const RESIDENT := "waiting_room.resident"
const RESCUE := "waiting_room.rescue"

var longest_light_window := 0

func check_unlit_attack_and_retry() -> void:
	step_to(215)
	check(model.fired.has("waiting_room.crow1.warning") and model.resources.lives == 5, "unlit crow warns before damage")
	check(not model.entities[LIGHT].active, "warning does not require activating the light")
	await capture("crow_warning")
	step_to(290)
	check(model.active_effects.values().any(func(effect): return effect.effect == "crow_release")
		and model.resources.lives == 5, "crow release effect appears before damage")
	await capture("crow_attack")
	step_to(330)
	check(model.resources.lives == 4, "uninterrupted unlit attack reaches the player")
	step_to(1100)
	check(model.result == "overrun" and model.resources.lives == 0, "five uninterrupted attacks fail the run")
	model.start()
	check(model.resources.lives == 5 and model.resources.ammo == 12 and model.resources.rescued == 0, "retry resets resources")

func check_last_round_reload() -> void:
	model.resources.ammo = 1
	check(shoot(LAMP).get("target") == LAMP and model.resources.ammo == 0, "last round can light the lamp")
	check(model.command("RELOAD").get("ok", false), "reload is available with the last round spent")
	step_to(105)
	check(model.resources.ammo == 12 and model.effective_kind(model.entities[CROW]) == "primary",
		"reload finishes before the crow's vulnerable window closes")
	check(shoot(CROW).get("target") == CROW and model.entities[CROW].health == 0, "last-round sequence can interrupt the crow")
	model.start()

func check_light_window() -> void:
	var saved: Dictionary = model.save_state()
	var expiry: int = model.tick + 360
	var streak := 0
	while model.tick < expiry and model.phase == "running":
		if model.effective_kind(model.entities[CROW]) == "primary":
			streak += 1
			longest_light_window = maxi(streak, longest_light_window)
		else:
			streak = 0
		model.step()
	check(longest_light_window >= 60, "patrol has a usable light window")
	check(not model.entities[LIGHT].active and model.effective_kind(model.entities[CROW]) == "invalid", "light expires and crow hardens")
	check(shoot(LAMP).get("target") == LAMP and model.entities[LIGHT].active, "expired lamp can be relit")
	model.restore_state(saved)

func play() -> void:
	check(model.current_section == "waiting_room", "opens at the waiting room")
	await capture("waiting_room_off")
	check(shoot(CROW).get("kind") == "invalid", "unlit crow is hardened")
	check(shoot(CANOPY).get("kind") == "invalid", "open canopy is invalid")
	check(shoot(RESIDENT).get("kind") == "protected" and model.resources.rescued == 0, "resident is protected")
	var ammo: int = model.resources.ammo
	check(shoot(LAMP).get("target") == LAMP and model.entities[LIGHT].active and model.resources.ammo == ammo - 1,
		"station lamp activates and costs one round")
	await capture("waiting_room_light_rise")
	step_to(49)
	check(model.effective_kind(model.entities[CROW]) == "invalid", "active light does not soften crow outside the spill")
	check_light_window()
	step_to(105)
	check(model.effective_kind(model.entities[CROW]) == "primary", "crow softens in the light")
	await capture("waiting_room_lit")
	check(shoot(CROW).get("target") == CROW and model.entities[CROW].health == 0, "lit crow is purified")
	step_to(153)
	check(shoot(CANOPY).get("kind") == "blocker", "folding canopy blocks a shot")
	await capture("umbrella_folding")
	check(shoot(RESCUE).get("target") == RESCUE and model.resources.rescued == 1, "only the chest ink rescues the resident")
	step_to(188)
	check(shoot(UMBRELLA).get("target") == UMBRELLA and model.entities[UMBRELLA].health == 0, "folded umbrella exposes its body")
	step_to(225)
	await capture("waiting_room_rescue")
	step_to(310)
	check(model.result == "clear" and model.resources.lives == 5 and model.resources.rescued == 1, "clear with all lives and rescue")
	check(not model.fired.has("waiting_room.crow1.release") and not model.fired.has("waiting_room.umbrella1.release"),
		"purification interrupts both enemy attacks")

func run() -> void:
	if not open_candidate():
		quit(2)
		return
	await check_unlit_attack_and_retry()
	check_last_round_reload()
	await play()
	print(JSON.stringify({"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"gpu_capture": viewport != null, "shots": model.shots, "lives": model.resources.lives,
		"rescued": model.resources.rescued, "light_window_ticks": longest_light_window}))
	quit(0 if failures.is_empty() else 1)
