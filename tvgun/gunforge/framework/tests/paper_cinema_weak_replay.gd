extends SceneTree
## Branch from live cinema poses and fire directly at both paper seals.

const Loader = preload("res://core/level_loader.gd")
const Session = preload("res://core/level_session.gd")
const PoseCodec = preload("res://core/pose_codec.gd")
const TARGETS := ["cinema.ticket_office.tape", "cinema.poster_hall.umbrella"]

func _initialize() -> void:
	run.call_deferred()

func weak_point(model, pose: Array, target: String) -> Variant:
	var canvas := Rect2(0, 0, model.level.layout.width, model.level.layout.height)
	for item in pose:
		if item.id != target or item.kind != "weak":
			continue
		var region: Rect2 = item.bounds().intersection(canvas)
		for y in range(ceili(region.position.y), floori(region.end.y)):
			for x in range(ceili(region.position.x), floori(region.end.x)):
				var point := Vector2(x + .5, y + .5)
				if item.sample(point).a >= .75:
					var hit: Dictionary = model.resolver.exact(point, pose)
					if hit.get("id") == target and hit.get("kind") == "weak":
						return point
	return null

func run() -> void:
	var args := {}
	for argument in OS.get_cmdline_user_args():
		var pair := argument.split("=", true, 1)
		if pair.size() == 2:
			args[pair[0]] = pair[1]
	var compiled = JSON.parse_string(FileAccess.get_file_as_string(args.get("--build", "")))
	var model = Loader.open(compiled, args.get("--assets", ""))
	var file := FileAccess.open(args.get("--recording", ""), FileAccess.READ)
	var fixture = file.get_var() if file != null else null
	if model == null or not fixture is Dictionary or fixture.recording.build_id != model.build.build_id:
		push_error("Expected a recording for the exact candidate")
		quit(2)
		return
	var session := Session.new()
	session.setup(model)
	var samples := []
	for target in TARGETS:
		var recorded: Array = fixture.recording.tape.filter(func(entry): return entry.result.get("target") == target)
		if recorded.is_empty():
			push_error("Recording did not reach " + target)
			quit(1)
			return
		var shot: Dictionary = recorded[0]
		session.load_recording(fixture.recording)
		session.seek(shot.tick - 1)
		var pose: Array = PoseCodec.decode(shot.input.geometry, model.geometry_assets())
		var point = weak_point(model, pose, target)
		if point == null:
			push_error("Could not resolve a visible weak point for " + target)
			quit(1)
			return
		var ammo: int = model.resources.ammo
		var reply: Dictionary = model.command("SHOT", point, pose)
		if reply.get("target") != target or reply.get("kind") != "weak" or not reply.get("hit", false) \
			or model.resources.ammo != ammo - 1 or model.entities[target].active:
			push_error("Weak shot did not consume one round and purify " + target)
			quit(1)
			return
		samples.append({"target": target, "tick": model.tick, "point": [point.x, point.y], "reply": reply})
	print(JSON.stringify({"passed": true, "build_id": model.build.build_id, "shots": samples}))
	quit()
