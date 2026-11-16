extends SceneTree
## Drive the compiled cinema candidate through the shared player model.

const Loader = preload("res://core/level_loader.gd")
const Codec = preload("res://core/pose_codec.gd")
const NORMAL = ["ticket_office", "poster_hall", "auditorium", "projection_booth"]
var model
var failures: Array[String] = []
var viewport: SubViewport
var captures := ""
var light_windows := {}
var fold_windows := {}
var fade_windows := {}

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, name: String) -> void:
	if not value:
		failures.append(name)

func step_to(tick: int) -> void:
	while model.tick < tick and model.phase == "running":
		model.step()

func ready_shot() -> void:
	step_to(model.next_shot)
	if model.resources.ammo == 0:
		check(model.command("RELOAD").ok, "reload accepted")
		step_to(model.reload_at)

func target_point(target: String, pose: Array) -> Variant:
	for item in pose:
		if item.id != target:
			continue
		var area: Rect2 = item.bounds()
		var center := area.get_center()
		if model.resolver.exact(center, pose).get("id") == target:
			return center
		for y in range(ceili(area.position.y), floori(area.end.y), 5):
			for x in range(ceili(area.position.x), floori(area.end.x), 5):
				var point := Vector2(x, y)
				if model.resolver.exact(point, pose).get("id") == target:
					return point
	return null

func shoot(target: String) -> Dictionary:
	ready_shot()
	var pose: Array = model.geometry()
	var point = target_point(target, pose)
	if point == null:
		failures.append("cannot aim at " + target)
		return {}
	var result: Dictionary = model.command("SHOT", point, pose)
	model.step()
	return result

func find_item(items: Array, id: String) -> Variant:
	for item in items:
		if item.id == id:
			return item
	return null

func wait_for_soft_tape(tape: String) -> bool:
	ready_shot()
	var deadline: int = model.tick + patrol_ticks(tape)
	while model.tick < deadline and model.phase == "running":
		if model.effective_kind(model.entities[tape]) == "primary":
			return true
		model.step()
	return false

func patrol_ticks(tape: String) -> int:
	return ceili(float(model.entities[tape].bob.period_ms) * model.level.tick_hz / 1000.0)

func changed_ink_pixels(frame: Image, reference: Image, area: Rect2i) -> int:
	var count := 0
	for y in range(area.position.y, area.end.y, 2):
		for x in range(area.position.x, area.end.x, 2):
			if absi(frame.get_pixel(x, y).r8 - reference.get_pixel(x, y).r8) > 4:
				count += 1
	return count

func verify_light_pixels(lamp: String, light: Dictionary, ink: Dictionary, tape: Dictionary) -> void:
	if viewport == null:
		return
	var point := Vector2i(model.display_center(model.entities[lamp]))
	var ink_position := Vector2i(model.display_transform(ink).origin)
	var band := Vector2i(int(ink.width), floori(ink.height / 3.0))
	var upper := Rect2i(ink_position, band)
	var lower := Rect2i(ink_position + Vector2i(0, int(ink.height) - band.y), band)
	var screenshot: Image = await rendered_frame()
	tape.visible = false
	var retreating: Image = await rendered_frame()
	ink.visible = false
	var dim: Image = await rendered_frame()
	light.pose_opacity = 1.0
	var full: Image = await rendered_frame()
	light.pose_opacity = 0.0
	var off: Image = await rendered_frame()
	ink.visible = true
	var covered: Image = await rendered_frame()
	light.pose_opacity = 1.0
	var clear: Image = await rendered_frame()
	light.pose_opacity = .5
	tape.visible = true
	var full_delta := full.get_pixelv(point).r8 - off.get_pixelv(point).r8
	var dim_delta := dim.get_pixelv(point).r8 - off.get_pixelv(point).r8
	check(full_delta >= 10 and absf(dim_delta - full_delta * .5) <= 2,
		"GPU lamp pixels use the same half-brightness as the light permission")
	var covered_top := changed_ink_pixels(covered, off, upper)
	var retreat_top := changed_ink_pixels(retreating, dim, upper)
	var retreat_bottom := changed_ink_pixels(retreating, dim, lower)
	check(covered_top > 30 and retreat_top * 10 < covered_top and retreat_bottom > maxi(30, retreat_top * 4),
		"GPU ink retracts into the bottom of the shade (%d/%d/%d)" % [covered_top, retreat_top, retreat_bottom])
	check(changed_ink_pixels(clear, full, upper) == 0 and changed_ink_pixels(clear, full, lower) == 0,
		"GPU ink clears at full brightness")
	check(screenshot.save_png(captures.path_join("ticket_fade_in.png")) == OK, "fade-in capture")

func verify_light_fade(stage: String, first: bool) -> void:
	var tape: Dictionary = model.entities[stage + ".tape"]
	var light_id := stage + ".light"
	var light: Dictionary = model.entities[light_id]
	var lamp := stage + ".lamp"
	var ink_id := stage + ".lamp_ink"
	var ink: Dictionary = model.entities[ink_id]
	var saved: Dictionary = model.save_state()
	var opened: int = model.tick
	# Hold the patrol at its authored lit endpoint to isolate the brightness curve.
	tape.x = tape.motion.frames[0].x + tape.bob.amplitude_x
	tape.y = tape.motion.frames[0].y
	tape.erase("motion")
	tape.erase("bob")
	model.active_effects.clear()
	var low := smoothstep(0.0, 18.0, 4.0)
	var tail := smoothstep(0.0, 18.0, 1.0)
	for sample in [[0, 0.0, "invalid"], [4, low, "invalid"], [9, .5, ""], [18, 1.0, "primary"],
			[372, 1.0, "primary"], [381, .68, ""], [393, 1.0, "primary"], [414, .42, "invalid"],
			[432, 1.0, "primary"], [441, .5, ""], [446, low, "invalid"], [449, tail, "invalid"]]:
		step_to(opened + int(sample[0]))
		var visuals: Array = model.visual_items()
		var visual = find_item(visuals, light_id)
		var overlay = find_item(visuals, ink_id)
		var opacity: float = visual.tint.a if visual != null else -1.0
		check(is_equal_approx(opacity, sample[1]),
			"%s light opacity %.4f differs from %.4f at tick %d" % [stage, opacity, sample[1], sample[0]])
		check(overlay != null and overlay.kind == "" and is_equal_approx(overlay.tint.a, 1.0 - opacity),
			"%s ink coverage follows the light without changing the hit mask at tick %d" % [stage, sample[0]])
		if not str(sample[2]).is_empty():
			check(model.effective_kind(tape) == sample[2], "%s permission follows brightness at tick %d" % [stage, sample[0]])
		if first and sample[0] == 9:
			await verify_light_pixels(lamp, light, ink, tape)
		if first and sample[0] == 414:
			await capture("ticket_lamp_flicker")
		if first and sample[0] == 441:
			await capture("ticket_fade_out")
	var ending: Dictionary = model.save_state()
	step_to(opened + 450)
	check(not model.entities[light_id].active and model.effective_kind(tape) == "invalid",
		stage + " expires at 7.5 seconds with no residual illumination")
	var returned = find_item(model.visual_items(), ink_id)
	check(returned != null and is_equal_approx(returned.tint.a, 1.0), stage + " ink fully returns on expiry")
	if first:
		await capture("ticket_ink_returned")
		model.restore_state(ending)
		check(model.tick == model.entities[lamp].next_activation and shoot(lamp).get("hit", false)
			and model.entities[light_id].active and model.entities[light_id].age_ticks == 0
			and is_zero_approx(model.entities[light_id].pose_opacity),
			"earliest valid relight restarts its fade without the old expiry removing the glow")
	fade_windows[stage] = 18
	model.restore_state(saved)

func verify_light_patrol(stage: String) -> void:
	var tape := stage + ".tape"
	var lamp := stage + ".lamp"
	var light := stage + ".light"
	var saved: Dictionary = model.save_state()
	var run_length := 0
	var longest := 0
	var cold_ticks := 0
	var lamps_visible := true
	var saw_cold_after_soft := false
	for offset in range(patrol_ticks(tape) + 144):
		if model.effective_kind(model.entities[tape]) == "primary":
			run_length += 1
			longest = maxi(longest, run_length)
		else:
			cold_ticks += 1
			saw_cold_after_soft = saw_cold_after_soft or longest > 0
			run_length = 0
		if offset % 12 == 0:
			var pose: Array = model.geometry()
			lamps_visible = lamps_visible and target_point(lamp, pose) != null
			check(model.entities[light].active and target_point(tape, pose) != null,
				stage + " patrol remains visible while the lamp is active")
		model.step()
	light_windows[stage] = longest
	check(longest >= 72 and cold_ticks > 0 and saw_cold_after_soft,
		stage + " offers at least 1.2 seconds of vulnerability and hardens on exit")
	check(lamps_visible, stage + " lamp remains aimable through the patrol")
	model.restore_state(saved)

func verify_bound_permissions(tape: String) -> void:
	var saved: Dictionary = model.save_state()
	var assets: Dictionary = model.geometry_assets()
	var dark := Codec.decode(Codec.encode(model.geometry(), assets), assets)
	var dark_point = target_point(tape, dark)
	if not wait_for_soft_tape(tape) or dark_point == null:
		check(false, "dark and soft snapshots are available")
		model.restore_state(saved)
		return
	var soft := Codec.decode(Codec.encode(model.geometry(), assets), assets)
	var soft_point = target_point(tape, soft)
	var result: Dictionary = model.command("SHOT", dark_point, dark)
	check(not result.get("hit", false) and result.get("kind") == "invalid", "submitted dark pose blocks after entry into light")
	ready_shot()
	var deadline: int = model.tick + patrol_ticks(tape)
	while model.tick < deadline and model.effective_kind(model.entities[tape]) == "primary":
		model.step()
	check(model.effective_kind(model.entities[tape]) == "invalid", "tape re-hardens outside warm light")
	check(soft_point != null and model.command("SHOT", soft_point, soft).get("hit", false),
		"submitted soft pose accepts a queued shot across the light boundary")
	model.restore_state(saved)

func verify_parallax(stage: String) -> void:
	var lamp := stage + ".lamp"
	var initial = find_item(model.geometry(), lamp)
	var initial_shift: Vector2 = model.camera_shift()
	step_to(model.tick + 60)
	var pose: Array = model.geometry()
	var moved = find_item(pose, lamp)
	var expected: Vector2 = (model.camera_shift() - initial_shift) * model.entities[lamp].parallax
	check(expected.length() > 5 and (moved.transform.origin - initial.transform.origin).is_equal_approx(expected),
		"lamp hit mask shifts with the camera")
	var assets: Dictionary = model.geometry_assets()
	var restored := Codec.decode(Codec.encode(pose, assets), assets)
	var has_blocker := false
	for item in restored:
		if item.kind != "blocker":
			continue
		has_blocker = true
		var visual = find_item(model.visual_items(), item.id)
		check(visual.transform == item.transform, item.id + " moved hit mask matches visible foreground")
		var point = target_point(item.id, restored)
		check(point != null and model.resolver.exact(point, restored).get("kind") == "blocker",
			item.id + " still blocks a shot after snapshot encoding")
	check(has_blocker, "station has at least one foreground blocker")

func verify_umbrella_fold(stage: String, capture_first: bool) -> void:
	var saved: Dictionary = model.save_state()
	var canopy := stage + ".canopy"
	var paper := stage + ".fold_body"
	var umbrella := stage + ".umbrella"
	var start: int = int(model.fired_time[stage + ".start"] / 1000)
	var fold_start := start + ceili(float(model.level.events[stage + ".fold.start"].trigger.delay_ms) * model.level.tick_hz / 1000.0)
	var duration := ceili(float(model.level.events[stage + ".fold"].trigger.delay_ms) * model.level.tick_hz / 1000.0)
	ready_shot()
	step_to(fold_start - 1)
	var open = find_item(model.geometry(), canopy)
	check(open != null and open.kind == "invalid" and not model.entities[paper].active,
		stage + " fully open canopy has no damageable body")
	if capture_first:
		await capture("umbrella_open")
	step_to(fold_start + floori(duration * .5))
	var assets: Dictionary = model.geometry_assets()
	var moving := Codec.decode(Codec.encode(model.geometry(), assets), assets)
	var shield = find_item(moving, canopy)
	var reveal = find_item(moving, paper)
	check(shield != null and shield.kind == "blocker" and shield.transform.x.length() < .8,
		stage + " moving canopy keeps its transformed blocker mask")
	check(reveal != null and reveal.kind == "invalid" and reveal.tint.a > .5 and reveal.tint.a < 1,
		stage + " partial ink reveal is visibly present and protected from damage")
	if capture_first:
		await capture("umbrella_folding")
	var point = target_point(canopy, moving)
	check(point != null and model.command("SHOT", point, moving).get("kind") == "blocker",
		stage + " moving canopy actually blocks a shot")
	step_to(fold_start + duration - 1)
	var before: Array = model.geometry()
	var last_reveal = find_item(before, paper)
	check(last_reveal != null and last_reveal.kind == "invalid" and find_item(before, umbrella) == null,
		stage + " no premature ink or weak point one tick before the end")
	step_to(fold_start + duration)
	var closed: Array = model.geometry()
	var pieces := closed.filter(func(item): return item.id == umbrella)
	check(find_item(closed, canopy) == null and find_item(closed, paper) == null and pieces.size() == 2
		and pieces[0].kind == "primary" and pieces[1].kind == "weak", stage + " unlocks both hit zones on the final tick")
	if capture_first:
		await capture("umbrella_closed")
	ready_shot()
	var queued: Dictionary = model.command("SHOT", point, moving) if point != null else {}
	check(queued.get("reason") == "target_inactive" and model.entities[umbrella].health == 1,
		stage + " queued shot at an old canopy cannot hit the new body")
	fold_windows[stage] = duration
	model.restore_state(saved)

func verify_resident(stage: String, resident: String) -> void:
	var rescue := stage + ".rescue"
	var ink = find_item(model.puppet_items(), rescue)
	var before = find_item(model.puppet_items(), resident)
	step_to(model.tick + 19)
	var moved = find_item(model.puppet_items(), rescue)
	check(ink != null and moved != null and moved.transform != ink.transform,
		stage + " chest ink follows the moving puppet")
	if stage == "ticket_office":
		await capture("resident_struggle")
	var count: int = model.resources.rescued
	check(shoot(resident).get("kind") == "protected", stage + " paper resident is protected")
	check(shoot(rescue).get("hit", false) and model.resources.rescued == count + 1,
		stage + " resident rescued by cleaning separate ink")
	var cleared: int = model.tick
	step_to(cleared + 18)
	var bounced = find_item(model.puppet_items(), resident)
	check(bounced != null and bounced.transform != before.transform and find_item(model.geometry(), rescue) == null,
		stage + " rescued pose remains while the chest ink disappears")
	check(find_item(model.visual_items(), stage + ".lamp") != null, stage + " lamp stays visible during station hold")
	if stage == "ticket_office":
		await capture("resident_rescued")
	step_to(cleared + 55)
	var thanked = find_item(model.puppet_items(), resident)
	check(thanked != null and thanked.transform != bounced.transform, stage + " resident transitions to thanks")
	if stage == "ticket_office":
		await capture("resident_thanks")
	step_to(cleared + 80)

func verify_separate_hit_area(target: String) -> void:
	var pose: Array = model.geometry()
	var assets: Dictionary = model.geometry_assets()
	var restored := Codec.decode(Codec.encode(pose, assets), assets)
	for item in restored:
		if item.id != target or item.hit_image == null:
			continue
		var area: Rect2 = item.bounds()
		for y in range(ceili(area.position.y), floori(area.end.y), 7):
			for x in range(ceili(area.position.x), floori(area.end.x), 7):
				var point := Vector2(x, y)
				var uv: Vector2 = (item.transform.affine_inverse() * point) / item.size
				var pixel: Vector2i = Vector2i(uv * Vector2(item.image.get_size()))
				if item.image.get_pixelv(pixel).a > .8 and item.sample(point).a < .1:
					check(model.resolver.exact(point, restored).get("id", "") != target,
						"solid prop pixels remain outside the hit mask after snapshot encoding")
					return
	failures.append("no visible decoration outside tape ink mask")

func rendered_frame() -> Image:
	await process_frame
	await RenderingServer.frame_post_draw
	return viewport.get_texture().get_image()

func capture(label: String) -> void:
	if viewport == null:
		return
	var frame := await rendered_frame()
	check(frame.save_png(captures.path_join(label + ".png")) == OK, label + " capture")

func check_station(stage: String, first: bool) -> void:
	var lamp := stage + ".lamp"
	var tape := stage + ".tape"
	var canopy := stage + ".canopy"
	check(model.current_section == stage, stage + " section")
	check(model.layer_items().all(func(item): return item.id.begins_with("layer." + stage + ".")), stage + " layer isolation")
	await verify_umbrella_fold(stage, first)
	if first:
		verify_separate_hit_area(tape)
		check(shoot(tape).get("kind") == "invalid", "unlit tape is hardened")
		check(shoot(canopy).get("kind") == "invalid", "open umbrella is not damageable")
		verify_parallax(stage)
		await capture("ticket_off")
	check(shoot(lamp).get("hit", false) and model.entities[stage + ".light"].active,
		stage + " lamp illuminates")
	await verify_light_fade(stage, first)
	verify_light_patrol(stage)
	if first:
		var visual_lamp = find_item(model.visual_items(), lamp)
		var visual_light = find_item(model.visual_items(), stage + ".light")
		var expected_offset: Vector2 = model.center(model.entities[stage + ".light"]) - model.center(model.entities[lamp])
		check((visual_light.bounds().get_center() - visual_lamp.bounds().get_center()).is_equal_approx(expected_offset),
			"lamp light and prop share the same parallax")
		step_to(model.tick + 9)
		check(model.effective_kind(model.entities[tape]) == "invalid", "lighting the lamp does not soften tape outside spill")
		await capture("ticket_lit_outside")
		verify_bound_permissions(tape)
		check(wait_for_soft_tape(tape), "tape enters the light")
		await capture("ticket_lit")
		var opened := int(model.fired_time[lamp + ".open"] / 1000)
		step_to(opened + 450)
		check(not model.entities[stage + ".light"].active and model.effective_kind(model.entities[tape]) == "invalid",
			"lamp expires after 7500ms")
		check(shoot(lamp).get("hit", false), "expired lamp can be relit")
	check(wait_for_soft_tape(tape), stage + " has an available soft shot")
	if not first:
		await capture(stage)
	check(shoot(tape).get("target") == tape, stage + " tape purified")
	step_to(model.tick + 160)
	check(not model.entities[canopy].active, stage + " umbrella folds")
	check(shoot(stage + ".umbrella").get("hit", false), stage + " folded umbrella purified")
	var resident := stage + ".resident"
	if model.entities.has(resident):
		await verify_resident(stage, resident)
	else:
		step_to(model.tick + 53)

func check_boss() -> void:
	check(model.current_section == "screen_stage", "screen stage reached")
	var start := int(model.fired_time.get("screen_stage.start", 0) / 1000)
	check(not model.entities.shadow_core.active, "core locked at boss start")
	await capture("screen_dark")
	check(shoot("projector_left").get("kind") == "invalid", "projector body cannot be damaged")
	check(shoot("reel_left").get("hit", false), "left reel purified")
	check(model.entities["projector_left.warm"].active and not model.entities["projector_right.warm"].active,
		"only the corresponding beam turns warm")
	step_to(start + 200)
	check(not model.entities.sweep_tape_1.active, "cleansed projector skips its sweep")
	check(model.fired.has("projector_center.sweep") and not model.entities.sweep_tape_2.active,
		"uncleansed projector sweeps before spawning")
	await capture("screen_sweep")
	step_to(start + 214)
	check(model.entities.sweep_tape_2.active, "enemy enters when the sweep reaches its lane")
	await capture("screen_spawn")
	check(shoot("sweep_tape_2").get("hit", false), "sweep enemy has a live ink mask")
	check(shoot("reel_center").get("hit", false) and not model.entities.shadow_core.active,
		"core still locked after two reels")
	check(shoot("reel_right").get("hit", false) and model.entities.shadow_core.active,
		"all reels reveal the core")
	await capture("screen_core")
	check(shoot("shadow_core").get("hit", false) and model.result == "clear", "core completes level")

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
	for index in NORMAL.size():
		await check_station(NORMAL[index], index == 0)
	await check_boss()
	check(model.resources.rescued == 3, "three residents rescued")
	var report := {"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"gpu_capture": viewport != null, "shots": model.shots, "rescued": model.resources.rescued,
		"longest_light_window_ticks": light_windows, "umbrella_fold_ticks": fold_windows, "light_fade_ticks": fade_windows}
	print(JSON.stringify(report))
	quit(0 if failures.is_empty() else 1)
