extends SceneTree
## Exercise the bridge lanes, timed attacks and real submitted hit geometry.

const Loader = preload("res://core/level_loader.gd")
const Codec = preload("res://core/pose_codec.gd")
const LAMP := "footbridge.lamp"
const LIGHT := "footbridge.light"
const DROP := "bridge.drop"
const CART := "bridge.cyclist"
const DECK := "layer.footbridge.bridge"
var model
var failures: Array[String] = []
var viewport: SubViewport
var captures := ""
var soft_ticks := 0

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, label: String) -> void:
	if not value:
		failures.append(label)

func step_to(target: int) -> void:
	while model.tick < target and model.phase == "running":
		model.step()

func aim(id: String, pose: Array) -> Variant:
	for item in pose:
		if item.id != id:
			continue
		var area: Rect2 = item.bounds().intersection(Rect2(0, 0, 1776, 936))
		if model.resolver.exact(area.get_center(), pose).get("id") == id:
			return area.get_center()
		for y in range(ceili(area.position.y), floori(area.end.y), 4):
			for x in range(ceili(area.position.x), floori(area.end.x), 4):
				var point := Vector2(x, y)
				if model.resolver.exact(point, pose).get("id") == id:
					return point
	return null

func shoot(id: String) -> Dictionary:
	step_to(model.next_shot)
	var assets: Dictionary = model.geometry_assets()
	var pose := Codec.decode(Codec.encode(model.geometry(), assets), assets)
	var point = aim(id, pose)
	if point == null:
		failures.append("cannot aim at " + id)
		return {}
	var result: Dictionary = model.command("SHOT", point, pose)
	model.step()
	return result

func capture(name: String) -> void:
	if viewport == null:
		return
	await process_frame
	await RenderingServer.frame_post_draw
	check(viewport.get_texture().get_image().save_png(captures.path_join(name + ".png")) == OK, "capture " + name)

func bridge_covers_drop() -> bool:
	var pose: Array = model.geometry()
	for item in pose:
		if item.id != DROP:
			continue
		var area: Rect2 = item.bounds()
		for y in range(ceili(area.position.y), floori(area.end.y), 4):
			for x in range(ceili(area.position.x), floori(area.end.x), 4):
				var point := Vector2(x, y)
				if item.sample(point).a >= .5 and model.resolver.exact(point, pose).get("id") == DECK:
					return true
	return false

func probe_attacks_and_light() -> void:
	var saved: Dictionary = model.save_state()
	var opened: int = model.tick
	var streak := 0
	var saw_dark := false
	var covered := false
	for offset in 450:
		if model.effective_kind(model.entities[DROP]) == "primary":
			streak += 1
			soft_ticks = maxi(soft_ticks, streak)
		else:
			saw_dark = saw_dark or is_equal_approx(model.active_opacity(model.entities[LIGHT]), 1.0)
			streak = 0
		if offset % 12 == 0:
			check(aim(LAMP, model.geometry()) != null, "lantern stays aimable through the drop path")
		if model.tick == 130:
			check(model.active_cues.values().any(func(cue): return cue.cue == "bell") and model.entities[CART].x == 690,
				"cyclist stops and rings before throwing")
			await capture("bridge_bell")
		if model.tick >= 194 and model.tick < 227 and not covered:
			covered = bridge_covers_drop()
			if covered:
				await capture("bridge_fall")
		if model.tick == 205:
			check(model.active_effects.values().any(func(effect): return effect.effect == "cart_spit") and model.resources.lives == 5,
				"visible cyclist throw precedes damage")
			await capture("bridge_throw")
		model.step()
	check(covered and saw_dark and soft_ticks >= 72, "drop passes behind the deck and has a clear lit window")
	check(not model.entities[LIGHT].active and model.effective_kind(model.entities[DROP]) == "invalid", "lamp expiry hardens the drop")
	check(model.fired.has("bridge.fall1.hit") and model.fired.has("bridge.cart1.hit"), "uninterrupted attacks reach the player")
	check(shoot(LAMP).get("hit", false) and model.entities[LIGHT].active, "lantern can be relit after expiry")
	model.restore_state(saved)

func play() -> void:
	check(model.current_section == "footbridge", "opens at the footbridge")
	await capture("bridge_off")
	check(shoot(DROP).get("kind") == "invalid", "unlit drop cannot be damaged")
	check(model.effective_kind(model.entities[CART]) == "primary", "cyclist remains vulnerable with the lantern off")
	check(shoot(DECK).get("kind") == "blocker", "moving deck blocks a pose-bound shot")
	check(shoot(LAMP).get("target") == LAMP and model.entities[LIGHT].active, "covered lantern can be activated")
	await probe_attacks_and_light()
	step_to(100)
	await capture("bridge_lit")
	step_to(130)
	check(shoot(CART).get("target") == CART, "cyclist is vulnerable without lighting its lane")
	check(shoot(DROP).get("target") == DROP, "lit drop can be intercepted")
	step_to(260)
	check(model.result == "clear" and model.resources.lives == 5 and model.resources.score == 200,
		"both lanes clear without damage")
	check(not model.fired.has("bridge.cart1.release") and not model.fired.has("bridge.fall1.release"),
		"purification cancels both scheduled attacks")

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
	model.start()
	await play()
	print(JSON.stringify({"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"gpu_capture": viewport != null, "shots": model.shots, "lives": model.resources.lives, "light_window_ticks": soft_ticks}))
	quit(0 if failures.is_empty() else 1)
