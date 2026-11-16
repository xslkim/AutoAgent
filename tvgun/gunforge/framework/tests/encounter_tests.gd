extends SceneTree

const Loader = preload("res://core/level_loader.gd")
var model
var passed = []
var failed = []

func _initialize():
	call_deferred("run")

func check(ok: bool, name: String):
	(passed if ok else failed).append(name)

func step_to(tick: int):
	while model.tick < tick and model.phase == "running":
		model.step()

func shoot(entity: String):
	var point = model.center(model.entities[entity])
	return model.command("SHOT",point)

func run():
	var path = ""
	var assets = ""
	var report = ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):path = arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):assets = arg.trim_prefix("--assets=")
		if arg.begins_with("--report="):report = arg.trim_prefix("--report=")
	model = Loader.open(JSON.parse_string(FileAccess.get_file_as_string(path)),assets)
	if model == null:
		quit(2)
		return

	model.start()
	step_to(78)
	check(model.current_section == "approach" and model.entities.rammer.motion_phase == "windup", "wave_and_visible_windup")
	var shot = shoot("jammer")
	model.step()
	var attack_age = model.entities.rammer.age_ticks
	check(shot.get("hit",false) and model.resources.cells == 11 and not model.available_commands().has("RELOAD"), "finite_cells_and_real_support_hit")
	check(model.active_effects.values().any(func(e):return e.effect == "signal" and e.get("source") == "jammer"), "support_effect_uses_bound_emitter")
	step_to(132)
	check(model.entities.rammer.age_ticks == attack_age and not model.fired.has("rammer.release"), "support_delays_the_same_local_attack_clock")
	step_to(196)
	check(model.resources.reactor == 2 and model.fired.get("rammer.attack") == 1, "delayed_contact_damages_custom_resource_once")

	model.start()
	step_to(85)
	check(shoot("rammer").get("hit",false), "rammer_can_be_neutralized_during_windup")
	step_to(150)
	check(model.resources.reactor == 3 and not model.fired.has("rammer.attack"), "neutralized_attacker_cannot_deal_contact_damage")
	step_to(205)
	check(model.entities.slug.active and shoot("slug").get("hit",false), "real_flight_geometry_is_interceptable")
	step_to(290)
	check(model.resources.credits == 75 and model.resources.reactor == 3 and not model.fired.has("slug.impact"), "intercept_awards_credit_and_cancels_impact")
	step_to(410)
	check(model.current_section == "sweep" and model.entities.sweeper.active, "second_wave_uses_own_start_and_offset")
	step_to(720)
	check(model.result == "clear" and model.resources.reactor == 2, "interception_route_completes")

	model.start()
	step_to(300)
	check(model.result == "reactor_lost" and model.resources.reactor == 0 and model.fired.get("slug.impact") == 1, "unintercepted_attack_reaches_failure")

	var result = {"passed":passed,"failed":failed,"build_id":model.build.build_id}
	if not report.is_empty():
		FileAccess.open(report,FileAccess.WRITE).store_string(JSON.stringify(result,"\t"))
	print(JSON.stringify(result))
	quit(0 if failed.is_empty() else 1)
