extends SceneTree
## Drive the plaza through the same pose-bound input session as the player.

const Loader = preload("res://core/level_loader.gd")
const Session = preload("res://core/level_session.gd")
const MOUTH := "dragon.mouth"
var model
var session = Session.new()
var failures: Array[String] = []
var cleared: Array[String] = []
var viewport: SubViewport
var captures := ""

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, label: String) -> void:
	if not value:
		failures.append(label)

func step_to(target: int) -> void:
	while model.tick < target and model.phase == "running":
		session.step()

func aim(id: String, pose: Array) -> Variant:
	for item in pose:
		if item.id != id:
			continue
		var area: Rect2 = item.bounds()
		var middle := area.get_center()
		if model.resolver.exact(middle, pose).get("id") == id:
			return middle
		for y in range(ceili(area.position.y), floori(area.end.y), 4):
			for x in range(ceili(area.position.x), floori(area.end.x), 4):
				var point := Vector2(x, y)
				if model.resolver.exact(point, pose).get("id") == id:
					return point
	return null

func send(event: String, point := Vector2.ZERO) -> Dictionary:
	if not session.enqueue(event, point):
		failures.append("input rejected: " + event)
		return {}
	session.step()
	return session.last_results[0] if not session.last_results.is_empty() else {}

func ready_weapon() -> void:
	step_to(model.next_shot)
	if model.resources.ammo == 0:
		check(send("RELOAD").get("ok", false), "reload accepted")
		step_to(model.reload_at)

func shoot(id: String) -> Dictionary:
	ready_weapon()
	var pose: Array = model.geometry()
	var point = aim(id, pose)
	if point == null:
		failures.append("no visible hit zone: " + id)
		return {}
	session.submit(pose)
	return send("SHOT", point)

func damageable(pose: Array) -> Array:
	return pose.filter(func(item): return item.kind in ["primary", "weak"]).map(func(item): return item.id)

func active_effect(id: String) -> bool:
	return model.active_effects.values().any(func(effect): return effect.effect == id)

func fired_tick(id: String) -> int:
	return int(float(model.fired_time.get(id, 0)) / 1000.0)

func capture(name: String) -> void:
	if viewport == null:
		return
	await process_frame
	await RenderingServer.frame_post_draw
	check(viewport.get_texture().get_image().save_png(captures.path_join(name + ".png")) == OK, "capture " + name)

func verify_entry() -> void:
	check(model.current_section == "square_watch" and model.dragon_items().is_empty(), "plaza wave precedes the boss")
	await capture("plaza_wave")
	check(shoot("square.sign").get("target") == "square.sign", "plaza sign purified")
	check(not model.entities["dragon.anchor"].active, "one remaining plaza target holds the boss")
	check(shoot("square.ink").get("target") == "square.ink" and not model.input_enabled, "second target clears the wave")
	step_to(fired_tick("square.clear") + 52)
	check(model.current_section == "ink_dragon" and model.input_enabled and model.entities["dragon.anchor"].active,
		"boss enters after the wave clears")
	await capture("dragon_entry")

func verify_body() -> void:
	var order: Array = model.dragon.layout.opening_order
	for index in order.size():
		var id: String = order[index]
		ready_weapon()
		var pose: Array = model.geometry()
		check(damageable(pose) == [id] and not model.entities[MOUTH].active,
			"only %s is exposed before the mouth" % id)
		var point = aim(id, pose)
		if point == null:
			failures.append("no visible ink on " + id)
			return
		session.submit(pose)
		if index == 0:
			step_to(model.tick + 35)
			var moved = aim(id, model.geometry())
			check(moved != null and moved.distance_to(point) > 4, "visible tail moves after a frame is submitted")
		check(send("SHOT", point).get("target") == id, "submitted ink shot purifies " + id)
		cleared.append(id)
		if index == 0:
			ready_weapon()
			check(send("SHOT", point).get("reason") == "target_inactive", "stale tail shot cannot harm the next segment")
		if index == 3:
			await capture("dragon_mid")

func verify_mouth() -> void:
	check(damageable(model.geometry()) == [MOUTH] and model.entities[MOUTH].active, "core alone opens after eight segments")
	await capture("dragon_mouth")
	check(shoot("upper_jaw").get("kind") == "blocker" and model.entities[MOUTH].health == 1,
		"paper jaw still blocks while the core is exposed")
	var opened := fired_tick("dragon.mouth_open")
	step_to(opened + 164)
	check(active_effect("dragon_windup") and absf(model.dragon_swing()) > .01, "mouth attack warns with a visible head swing")
	await capture("dragon_warning")
	step_to(opened + 237)
	check(active_effect("dragon_breath") and model.resources.lives == 5, "ink release precedes contact")
	await capture("dragon_breath")
	step_to(opened + 251)
	check(model.resources.lives == 4 and active_effect("hurt_fx"), "an uninterrupted breath deals one damage")
	step_to(opened + 421)
	check(active_effect("dragon_windup"), "next breath starts with another warning")
	check(shoot(MOUTH).get("kind") == "weak" and not model.input_enabled, "the exposed core accepts the finishing shot")
	await capture("dragon_cleansed")
	step_to(model.tick + 52)
	check(model.result == "clear" and model.resources.lives == 4 and not model.fired.has("dragon.breath2.release"),
		"finishing shot cancels the second breath and completes the plaza")
	check(damageable(model.geometry()).is_empty() and model.resources.score == 1100, "purified dragon retains no hit zone")
	var end_tick: int = model.tick
	var expected: PackedByteArray = var_to_bytes(model.save_state())
	session.seek(opened)
	session.seek(end_tick)
	check(var_to_bytes(model.save_state()) == expected, "checkpoint replay preserves the dragon encounter")

func run() -> void:
	var args := {}
	for arg in OS.get_cmdline_user_args():
		var pair := arg.split("=", true, 1)
		if pair.size() == 2:
			args[pair[0]] = pair[1]
	var compiled = JSON.parse_string(FileAccess.get_file_as_string(args.get("--build", "")))
	model = Loader.open(compiled, args.get("--assets", ""))
	if model == null:
		quit(2)
		return
	captures = args.get("--captures", "")
	if not captures.is_empty() and DisplayServer.get_name() != "headless":
		if DirAccess.make_dir_recursive_absolute(captures) != OK:
			quit(2)
			return
		viewport = SubViewport.new()
		viewport.size = Vector2i(1776, 936)
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		root.add_child(viewport)
		model.mount(viewport)
	session.setup(model)
	await verify_entry()
	if failures.is_empty():
		await verify_body()
	if failures.is_empty():
		await verify_mouth()
	var report := {"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"gpu_capture": viewport != null, "body_order": cleared, "shots": model.shots, "lives": model.resources.lives}
	print(JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
