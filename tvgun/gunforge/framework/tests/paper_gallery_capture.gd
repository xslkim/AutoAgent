extends "res://tests/night_market_tests.gd"
## Capture named characters and bosses at poses from the deterministic campaign route.

const SUBJECTS := {
	"vendor": [1, "alley.resident"],
	"video_owner": [3, "video_shop.shop.owner"],
	"ticket_clerk": [6, "cinema.ticket_office.resident"],
	"passerby_b": [8, "cinema.auditorium.resident"],
	"projectionist": [9, "cinema.projection_booth.resident"],
	"passerby_c": [11, "waiting_room.waiting_room.resident"],
	"platform_clerk": [12, "platform.platform.resident"],
	"ink_crow": [1, "alley.w1_crow_1"],
	"ink_drop": [3, "video_shop.shop.drop"],
	"ink_sign": [3, "video_shop.shop.sign"],
	"ink_cart": [4, "footbridge.bridge.cyclist"],
	"ink_tape": [6, "cinema.ticket_office.tape"],
	"umbrella_open": [6, "cinema.ticket_office.canopy"],
	"umbrella_closed": [6, "cinema.ticket_office.umbrella", "primary"],
	"dragon": [5, "dragon.mouth", "weak"],
	"screen_shadow": [10, "cinema.shadow_core", "primary"],
	"forget": [15, "lantern_base.forget.stroke_1", "weak"],
}
const CAST := "paper.lantern_city_cast"
const CAST_SUBJECTS := {
	"cyclist": [4, "footbridge.bridge.cyclist_resident"],
	"passerby_a": [12, "platform.platform.resident", "protected"],
	"passerby_a_saved": [12, "platform.platform.resident", "decoration"],
	"tadpole": [1, ["puddle.puddle.tadpole1", "puddle.puddle.tadpole2", "puddle.puddle.tadpole3"]],
}
const BRIDGE_WARNING := ["footbridge.bridge.cyclist_reaction", "footbridge.bridge.cyclist"]

var subject_frames: Dictionary = {}
var subjects: Dictionary = {}

func queue_action(index: int) -> bool:
	for name in subjects:
		var subject: Array = subjects[name]
		if index != subject[0] or subject_frames.has(name) or not model.input_enabled:
			continue
		var ids: Array = subject[1] if subject[1] is Array else [subject[1]]
		if not ids.all(func(id): return model.entities[id].active and model.entities[id].visible):
			continue
		if subject.size() == 3 and model.effective_kind(model.entities[ids[0]]) != subject[2]:
			continue
		if name == "passerby_a_saved" and model.tick < model.entities["platform.platform.rescue"].defeated_at + 38:
			continue
		var box := visible_bounds(ids)
		var canvas := Rect2(0, 0, model.level.layout.width, model.level.layout.height)
		if box.size.x >= 28 and box.size.y >= 28 and canvas.encloses(box):
			subject_frames[name] = sample(ids, index, box)
	return super.queue_action(index)

func sample(ids: Array, index: int, box: Rect2) -> Dictionary:
	var result := {"tick": model.tick, "station": index, "section": model.current_section,
		"bounds": [box.position.x, box.position.y, box.size.x, box.size.y]}
	if ids.size() == 1:
		result["entity"] = ids[0]
	else:
		result["entities"] = ids
	return result

func visible_bounds(ids: Array) -> Rect2:
	var box := Rect2()
	for item in model.visual_items():
		if item.id in ids and item.tint.a >= .65:
			box = box.merge(item.bounds()) if box.has_area() else item.bounds()
	return box

func capture_bridge_warning() -> void:
	var bridge: Array = handoffs.filter(func(row): return row.station == "footbridge")
	if bridge.is_empty():
		check(false, "route exposes the bridge")
		return
	var entered: int = bridge[0].tick
	session.seek(entered)
	check(session.enqueue("RELOAD"), "branch without firing at the cart before its bell")
	while model.tick < entered + 130 and model.phase == "running":
		session.step()
	check(BRIDGE_WARNING.all(func(id): return visible_bounds([id]).has_area())
		and model.active_cues.values().any(func(cue): return cue.cue == "footbridge.bell"),
		"cyclist reaction and hostile cart share the bell frame")
	var frame := sample(BRIDGE_WARNING, 4, visible_bounds(BRIDGE_WARNING))
	frame["branch"] = "bridge_entry_with_no_combat_shots"
	subject_frames["bridge_warning"] = frame
	await capture("subject_bridge_warning")

func play() -> void:
	if viewport == null or captures.is_empty():
		check(false, "gallery capture requires a GPU viewport and output directory")
		return
	subjects = SUBJECTS.duplicate()
	if model.level.id == CAST:
		subjects.erase("platform_clerk")
		subjects.merge(CAST_SUBJECTS)
	await super.play()
	var completed: Dictionary = session.snapshot()
	var checkpoints: Dictionary = session.checkpoints.duplicate()
	for name in subjects:
		check(subject_frames.has(name), "route exposes gallery subject " + name)
		if not subject_frames.has(name):
			continue
		var frame: Dictionary = subject_frames[name]
		session.seek(frame.tick)
		var ids: Array = frame.entities if frame.has("entities") else [frame.entity]
		check(model.current_section == frame.section and ids.all(func(id): return visible_bounds([id]).has_area()),
			"replay reproduces " + name)
		await capture("subject_" + name)
	if model.level.id == CAST:
		await capture_bridge_warning()
	session.restore(completed)
	session.checkpoints = checkpoints
	print(JSON.stringify({"gallery_subjects": subject_frames, "build_id": model.build.build_id}))
