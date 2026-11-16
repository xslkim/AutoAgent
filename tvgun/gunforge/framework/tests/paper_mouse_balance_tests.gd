extends "res://tools/level_player.gd"
## Exercise the revised campaign through the desktop input path at fixed simulation ticks.

const CROW := "alley.w1_crow_1"
const LAMP := "alley.lamp"
const RESCUE := "alley.resident_ink"
var failures: Array[String] = []

func check(condition: bool, description: String) -> void:
	if not condition:
		failures.append(description)

func _process(_delta):
	super._process(0.0)

func paint_pose() -> void:
	preview.queue_redraw()
	await process_frame
	await RenderingServer.frame_post_draw

func click(point: Vector2) -> Dictionary:
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_LEFT
	event.position = preview.position + preview.origin + point * preview.scale_factor
	event.global_position = event.position
	event.pressed = true
	root.push_input(event, true)
	event = event.duplicate()
	event.pressed = false
	root.push_input(event, true)
	session.step()
	return session.last_results[0] if not session.last_results.is_empty() else {}

func advance_until(at: int) -> void:
	while session.clock.tick < at:
		session.step()

func point_for(id: String, also_on: String = "") -> Vector2:
	var pose: Array = model.geometry()
	for item in pose:
		if item.id != id:
			continue
		var box: Rect2 = item.bounds().intersection(Rect2(0, 0, 1776, 936))
		for y in range(ceili(box.position.y), ceili(box.end.y), 3):
			for x in range(ceili(box.position.x), ceili(box.end.x), 3):
				var point := Vector2(x, y)
				if model.resolver.exact(point, pose).get("id") != id:
					continue
				if also_on.is_empty() or pose.any(func(piece):
					return piece.id == also_on and piece.bounds().has_point(point) and piece.sample(point).a >= .5
				):
					return point
	return Vector2.INF

func find_empty_point() -> Vector2:
	for point in [Vector2(800, 210), Vector2(500, 180), Vector2(900, 280)]:
		if model.resolver.exact(point, model.geometry()).is_empty():
			return point
	return Vector2.INF

func open():
	isolated_settings = true
	super.open()
	if model == null:
		return
	if DisplayServer.get_name() == "headless" or not model.level.controls.get("auto_reload", false):
		quit(2)
		return
	var magazine: int = model.level.controls.magazine
	var reload_ticks := ceili(float(model.level.controls.reload_ms) * model.level.tick_hz / 1000)
	await paint_pose()
	var start: Vector2 = model.render_scene.paper_hud.action_rect(false).get_center()
	click(start)
	check(not session.pause_reasons.has("ready") and model.shots == 0, "mouse start without firing")
	var lesson: int = int(model.level.events["alley.lesson.lamp"].at_tick)
	advance_until(lesson)
	await paint_pose()
	var empty := find_empty_point()
	if empty.is_finite():
		for index in magazine:
			var result := click(empty)
			check(result.get("ok") and not result.get("hit"), "mouse round %d spends one shot" % index)
			if index < magazine - 1:
				advance_until(model.next_shot)
	else:
		check(false, "empty content point is available")
	check(magazine == 8 and model.shots == magazine and model.resources.ammo == 0, "8 usable starting rounds")
	var reload_due: int = model.reload_at
	check(reload_due - model.tick == reload_ticks - 1, "last round starts automatic reload")
	var busy := click(empty) if empty.is_finite() else {}
	check(busy.get("reason") == "weapon_busy", "extra click does not consume another round")
	if reload_due > model.tick:
		advance_until(reload_due - 1)
		check(model.resources.ammo == 0, "rounds stay empty until reload ends")
		advance_until(reload_due)
	check(reload_ticks == 36 and model.resources.ammo == magazine and model.reload_at == -1,
		"automatic reload restores all rounds after 600 ms")
	if empty.is_finite():
		click(empty)
		handle_key(KEY_R)
		session.step()
		check(model.reload_at > model.tick, "R still starts a partial reload")
		advance_until(model.reload_at)
		check(model.resources.ammo == magazine, "manual reload refills the magazine")

	session.start()
	advance_until(int(model.level.events[CROW + ".spawn"].at_tick))
	var crow: Dictionary = model.entities[CROW]
	var warning_tick: int = model.tick + ceili(float(model.level.events[CROW + ".warning"].trigger.value) * .06)
	advance_until(warning_tick)
	check(crow.motion_phase == "windup" and model.fired.has(CROW + ".warning"), "crow displays windup")
	var release_ms: int = int(model.level.events[CROW + ".release"].trigger.value)
	var warning_ms: int = int(model.level.events[CROW + ".warning"].trigger.value)
	var contact_ms: int = int(model.level.events[CROW + ".attack"].trigger.value)
	check(release_ms - warning_ms == 1650 and contact_ms - release_ms == 520, "crow reaction and dive windows")
	advance_until(warning_tick + 90)
	check(crow.motion_phase == "windup" and not model.fired.has(CROW + ".release"), "crow still winds up after 1.5 s")
	await paint_pose()
	var target := point_for(CROW)
	if target.is_finite():
		check(click(target).get("target") == CROW, "mouse interrupts crow after 1.5 s")
	else:
		check(false, "winding crow is visible and shootable")
	advance_until(warning_tick + 132)
	check(not model.fired.has(CROW + ".release") and model.resources.lives == 5, "interrupted crow never releases or damages player")

	session.start()
	advance_until(int(model.level.events[CROW + ".spawn"].at_tick))
	while not model.fired.has(CROW + ".release") and model.tick < warning_tick + 110:
		session.step()
	check(model.fired.has(CROW + ".release") and not model.fired.has(CROW + ".attack"), "a missed warning starts the dive")
	advance_until(model.tick + 12)
	await paint_pose()
	target = point_for(CROW)
	if target.is_finite():
		check(click(target).get("target") == CROW, "mouse can still interrupt the dive")
	else:
		check(false, "diving crow is visible and shootable")
	advance_until(warning_tick + 132)
	check(not model.fired.has(CROW + ".attack") and model.resources.lives == 5, "diving crow is stopped before contact")

	# Place an active crow across the lamp to exercise the same pixel in both masks.
	session.start()
	advance_until(int(model.level.events[CROW + ".spawn"].at_tick))
	crow = model.entities[CROW]
	var lamp: Dictionary = model.entities[LAMP]
	crow.x = lamp.x - 70
	crow.y = lamp.y - 65
	await paint_pose()
	var overlap := point_for(CROW, LAMP)
	check(overlap.is_finite(), "crow and lamp share a shootable pixel")
	if overlap.is_finite():
		check(click(overlap).get("target") == CROW and lamp.value == 0, "overlap mouse shot hits crow, not lamp")
		advance_until(model.next_shot)
		await paint_pose()
		check(click(overlap).get("target") == LAMP and lamp.value == 1, "same pixel lights exposed lamp")
		check(model.resources.ammo == magazine, "first lamp supply caps at magazine capacity")

	session.start()
	advance_until(lesson)
	await paint_pose()
	var lamp_point := point_for(LAMP)
	check(lamp_point.is_finite(), "alley lamp is shootable")
	if lamp_point.is_finite():
		model.resources.ammo = 1
		check(click(lamp_point).get("target") == LAMP and model.resources.ammo == 4 and model.reload_at == -1,
			"last shot gets four lamp rounds and ends automatic reload")
		var second_light: int = model.entities[LAMP].next_activation
		advance_until(second_light)
		await paint_pose()
		lamp_point = point_for(LAMP)
		check(lamp_point.is_finite(), "lamp is shootable again after its cooldown")
		if lamp_point.is_finite():
			check(click(lamp_point).get("target") == LAMP and model.resources.ammo == 3,
				"relighting never grants a second ammo supply")

	for lives in [3, 5]:
		session.start()
		var rescue_tick: int = int(model.level.events["alley.resident.arrives"].at_tick)
		while model.tick < rescue_tick and model.phase == "running":
			# Preserve the rescue branch without taking all preceding wave attacks.
			for entity in model.entities:
				if entity.begins_with("alley.w") and model.entities[entity].active:
					model.entities[entity].active = false
			session.step()
		model.resources.lives = lives
		await paint_pose()
		var ink_point := point_for(RESCUE)
		check(ink_point.is_finite(), "resident ink is shootable")
		if ink_point.is_finite():
			check(click(ink_point).get("target") == RESCUE and model.resources.rescued == 1
				and model.resources.lives == mini(5, lives + 1), "rescue restores at most one life")
	print(JSON.stringify({"build_id": model.build.build_id, "passed": failures.is_empty(), "failures": failures,
		"magazine": magazine, "reload_ticks": reload_ticks, "warning_ms": release_ms - warning_ms,
		"lunge_ms": contact_ms - release_ms, "overlap_pixel": [overlap.x, overlap.y]}))
	quit(0 if failures.is_empty() else 1)
