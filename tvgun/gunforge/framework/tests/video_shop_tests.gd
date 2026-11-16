extends SceneTree
## Verify the playable video shop, including the signed light mask and protected owner.

const Loader = preload("res://core/level_loader.gd")
const Codec = preload("res://core/pose_codec.gd")
const LAMP := "video_shop.lamp"
const LIGHT := "video_shop.light"
const SIGN := "shop.sign"
const DROP := "shop.drop"
const OWNER := "shop.owner"
const RESCUE := "shop.rescue"
var model
var failures: Array[String] = []
var viewport: SubViewport
var captures := ""
var window_ticks := 0

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

func drop_probe() -> void:
	var saved: Dictionary = model.save_state()
	step_to(40)
	var before: float = model.entities[DROP].y
	check(model.fired.has(DROP + ".warn") and model.resources.lives == 5, "drop warns under the eaves")
	step_to(145)
	check(model.fired.has(DROP + ".fall") and model.entities[DROP].y > before + 120 and model.resources.lives == 5,
		"drop is visible in flight before contact")
	await capture("shop_falling")
	step_to(171)
	check(model.resources.lives == 4, "uninterrupted drop deals damage after the fall")
	model.restore_state(saved)
	step_to(145)
	check(shoot(DROP).get("target") == DROP, "drop is interceptable in flight")
	step_to(171)
	check(model.resources.lives == 5 and not model.fired.has(DROP + ".damage"), "interception cancels contact")

func light_probe() -> void:
	var saved: Dictionary = model.save_state()
	var opened: int = model.tick
	var streak := 0
	var dark_in_light := false
	for offset in 450:
		if model.effective_kind(model.entities[SIGN]) == "primary":
			streak += 1
			window_ticks = maxi(window_ticks, streak)
		else:
			dark_in_light = dark_in_light or is_equal_approx(model.active_opacity(model.entities[LIGHT]), 1.0)
			streak = 0
		if offset % 12 == 0:
			check(aim(LAMP, model.geometry()) != null, "neon stays aimable during patrol")
		if model.tick == 355:
			check(model.active_effects.values().any(func(e): return e.effect == "sign_spit") and model.resources.lives == 5,
				"sign spit has a visible release before damage")
			await capture("shop_spit")
		model.step()
	check(model.tick == opened + 450 and not model.entities[LIGHT].active and model.effective_kind(model.entities[SIGN]) == "invalid",
		"neon expires and restores hardening")
	check(window_ticks >= 72 and dark_in_light, "patrol crosses both lit and unlit areas with an aimable window")
	check(model.resources.lives == 4, "uninterrupted sign attack lands once")
	check(shoot(LAMP).get("hit", false) and model.entities[LIGHT].active, "neon can be relit")
	model.restore_state(saved)

func play() -> void:
	check(model.current_section == "video_shop", "opens at the video shop")
	await capture("shop_off")
	check(shoot(SIGN).get("kind") == "invalid", "dark sign is hardened")
	check(shoot(OWNER).get("kind") == "protected" and model.entities[RESCUE].health == 1, "owner is protected")
	check(shoot("layer.video_shop.left_wall").get("kind") == "blocker", "moving foreground blocks shots")
	await drop_probe()
	check(shoot(LAMP).get("target") == LAMP and model.entities[LIGHT].active, "covered neon can be activated")
	await light_probe()
	var deadline: int = model.tick + 270
	while model.tick < deadline and model.effective_kind(model.entities[SIGN]) != "primary":
		model.step()
	check(model.effective_kind(model.entities[SIGN]) == "primary", "sign softens inside the lit mask")
	await capture("shop_lit")
	check(shoot(SIGN).get("target") == SIGN, "softened sign can be purified")
	check(shoot(RESCUE).get("target") == RESCUE and model.resources.rescued == 1, "chest ink rescues the owner")
	var solved: int = model.tick
	step_to(solved + 90)
	check(aim(RESCUE, model.geometry()) == null and aim(OWNER, model.geometry()) != null, "rescued paper owner remains protected")
	await capture("shop_rescued")
	step_to(solved + 161)
	await capture("shop_thanks")
	step_to(solved + 188)
	check(model.result == "clear" and model.resources.lives == 5 and not model.fired.has("shop.spit1.release"),
		"station clears after all three targets and the interrupted spit does not fire")

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
		"gpu_capture": viewport != null, "shots": model.shots, "rescued": model.resources.rescued, "light_window_ticks": window_ticks}))
	quit(0 if failures.is_empty() else 1)
