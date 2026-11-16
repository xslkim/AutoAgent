extends "res://tests/footbridge_tests.gd"
## Verify the bicycle and its owner through player submissions as well as the existing bridge route.

const Session = preload("res://core/level_session.gd")
const RESIDENT := "bridge.cyclist_resident"
const REACTION := "bridge.cyclist_reaction"
const BICYCLE := "bridge.bicycle"
const SCENERY := [RESIDENT, REACTION, BICYCLE]
const SAFE_FIELD := Rect2(60, 60, 1656, 816)
var session = Session.new()

func exposed_decoration(id: String, pose: Array) -> Variant:
	var sprites := pose.filter(func(sprite): return sprite.id == id)
	if sprites.size() != 1:
		return null
	var item = sprites[0]
	var bounds: Rect2 = item.bounds()
	for y in range(ceili(bounds.position.y), floori(bounds.end.y), 3):
		for x in range(ceili(bounds.position.x), floori(bounds.end.x), 3):
			var at := Vector2(x + .5, y + .5)
			if item.sample(at).a >= .5 and model.resolver.exact(at, pose).is_empty():
				return at
	return null

func safe_shot(id: String) -> Variant:
	while model.tick < model.next_shot:
		session.step()
	var pose: Array = model.geometry()
	var point = exposed_decoration(id, pose)
	if point == null:
		failures.append("no exposed decoration for " + id)
		return null
	session.submit(pose)
	check(session.enqueue("SHOT", point), "submit shot at visible decoration")
	session.step()
	check(session.last_results.size() == 1 and session.last_results[0].get("kind") == "miss",
		"visible decoration does not receive or block a shot")
	return [point.x, point.y]

func verify_cyclist() -> void:
	session.setup(model)
	check(model.level.sections.footbridge.targets == [DROP, CART], "only the existing ink enemies count toward progress")
	check(not model.level.initial_resources.has("rescued"), "safe resident requires no rescue counter")
	for id in SCENERY:
		check(model.entities[id].kind == "decoration" and model.entities[id].active, "scenery is noninteractive: " + id)
	check(model.entities[RESIDENT].visible and not model.entities[REACTION].visible, "cyclist starts with the idle pose")
	await capture("cyclist_idle")
	var resident_point = safe_shot(RESIDENT)
	var bicycle_point = safe_shot(BICYCLE)
	while model.tick < 130:
		session.step()
	check(model.entities[REACTION].visible and not model.entities[RESIDENT].visible, "only the startled pose appears on the cart bell")
	var pose: Array = model.geometry()
	var upper: Rect2 = pose.filter(func(item): return item.id == REACTION)[0].bounds()
	var lower: Rect2 = pose.filter(func(item): return item.id == CART)[0].bounds()
	check(SAFE_FIELD.encloses(upper) and upper.end.y < lower.position.y, "the resident and the hostile cart occupy separate bridge decks")
	check(aim(CART, pose) != null, "the hostile cart remains hittable during the reaction")
	await capture("cyclist_and_cart")
	var reaction_point = safe_shot(REACTION)
	while model.tick < 173:
		session.step()
	check(model.entities[RESIDENT].visible and not model.entities[REACTION].visible, "cyclist returns to idle after the bell")
	check(model.resources.lives == 5 and model.resources.ammo == 9 and model.resources.score == 0 and model.hits == 0,
		"three scenery shots only spend light rounds")
	var trace: Array = model.trace.duplicate(true)
	check(not trace.any(func(entry): return entry.topic.begins_with("target.") and entry.get("entity") in SCENERY),
		"no scenery registers as a shot target")
	var recorded: Dictionary = session.recording()
	session.load_recording(recorded)
	while session.clock.tick < recorded.end_tick:
		session.step()
	check(model.trace == trace and model.resources.ammo == 9 and model.entities[RESIDENT].visible, "pose and resources replay exactly")
	print(JSON.stringify({"build_id": model.build.build_id, "scenery_shots": [resident_point, bicycle_point, reaction_point],
		"vertical_lane_gap_px": lower.position.y - upper.end.y, "replayed_inputs": recorded.tape.size(),
		"resident_returned_to_idle": model.entities[RESIDENT].visible and not model.entities[REACTION].visible}))

func play() -> void:
	await super.play()
	var cleared: Dictionary = model.save_state()
	await verify_cyclist()
	model.restore_state(cleared)
