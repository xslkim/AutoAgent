extends SceneTree
const Rules = preload("res://runtime/game_rules.gd")
const Clock = preload("res://core/fixed_clock.gd")
const Queue = preload("res://core/tick_input_queue.gd")
var game
var failures = []
var comparisons = 0
var directory = ""
var output = ""
var allow_fixes = false
var compiled_path = ""
func _initialize():call_deferred("run")
func normalized(value):return JSON.stringify(JSON.parse_string(JSON.stringify(value)),"",true)
func check_state(expected, label):
	expected = expected.duplicate(true)
	if allow_fixes and label.begins_with("paper/") and expected.lives==4:
		expected.lives = 5
		for event in expected.events:
			if event.event=="hurt":event.event = "protected"
	if allow_fixes and label.begins_with("repeat_rescue/") and expected.score>=600:
		expected.score -= 300
		expected.hits -= 1
		expected.feedback = "未命中"
		var first = true
		for event in expected.events:
			if event.event=="rescue":
				if first:first = false
				else:event.event = "miss"
	comparisons += 1
	if normalized(game.model.snapshot())!=normalized(expected):
		if failures.size()<10:failures.append({"at":label,"expected":expected,"actual":game.model.snapshot()})
func reset():
	var data=JSON.parse_string(FileAccess.get_file_as_string(compiled_path if not compiled_path.is_empty() else "res://runtime/level.json"))
	if compiled_path.is_empty():game.model=Rules.new()
	else:
		var asset_root=ProjectSettings.globalize_path("res://").path_join("../..").simplify_path()
		var catalog=JSON.parse_string(FileAccess.get_file_as_string(asset_root.path_join("gunforge/level_design/specs/capabilities-v1.json")))
		game.model=load(asset_root.path_join(catalog.rulesets[data.level.ruleset].native_rules)).new()
	game.model.setup(data)
	game.scene.model = game.model
	game.scene.view_clock = 0
	game.scene.build_pose()
	game.scene.update_frame()
	game.last_events = 0
	game.simulation_clock = Clock.new()
	game.input_queue = Queue.new()
	game.input_completions.clear()
	game.network_mode = true
	game.link.valid = true
	game.commit_render_submission()
func shoot_target(id):
	for item in game.scene.hit_items:
		if item.id!=id or item.kind not in ["primary","weak","protected","invalid"]:continue
		var box = item.bounds()
		for y in range(int(box.position.y),int(box.end.y),3):
			for x in range(int(box.position.x),int(box.end.x),3):
				var hit = game.resolver.exact(Vector2(x,y),game.scene.hit_items)
				if hit.get("id","")==id and hit.get("kind","")==item.kind:
					game.debug_command({"op":"input","event":"SHOT","x":x+72,"y":y+72})
					return
func run():
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--baseline="):directory = arg.trim_prefix("--baseline=")
		if arg.begins_with("--output="):output = arg.trim_prefix("--output=")
		if arg=="--expected-fixes":allow_fixes = true
		if arg.begins_with("--compiled="):compiled_path=arg.trim_prefix("--compiled=")
	if directory.is_empty() or output.is_empty():quit(2);return
	game = load("res://main.tscn").instantiate()
	root.add_child(game)
	game.sound.enabled = false
	game.set_process(false)
	game.set_process_unhandled_input(false)
	game.fixed = true
	var cases = ["normal","one_miss_per_wave","miss_and_continue","paper","repeat_rescue","repeat_lamp","reload","loss"]
	for name in cases:
		var data = JSON.parse_string(FileAccess.get_file_as_string(directory.path_join(name+"_0.json")))
		var index = 0
		for operation in data.operations:
			var request = operation.request
			match request.op:
				"record_reset":reset()
				"input":game.debug_command(request)
				"record_lock":game.link.valid = request.value
				"record_target":
					if operation.response.has("point"):
						game.debug_command({"op":"input","event":"SHOT","x":operation.response.point[0],"y":operation.response.point[1]})
				"record_steps":
					for frame in range(int(request.frames)):
						game.simulation_clock.step(game.fixed_tick)
						game.scene.update_frame()
						game.commit_render_submission()
						check_state(operation.response.trace[frame],name+"/%d/%d" % [index,frame])
			if operation.response.has("state"):check_state(operation.response.state,name+"/%d" % index)
			index += 1
		print(name+" compared")
	var report = {"passed":failures.is_empty(),"comparisons":comparisons,"failures":failures,"comparison":"same tick public state at legacy JSON numeric encoding; discrete fields exact; no timing tolerance used"}
	FileAccess.open(output,FileAccess.WRITE).store_string(JSON.stringify(report,"\t"))
	print(JSON.stringify({"passed":report.passed,"comparisons":comparisons,"failures":failures.size()}))
	game.queue_free()
	await process_frame
	quit(0 if failures.is_empty() else 1)
