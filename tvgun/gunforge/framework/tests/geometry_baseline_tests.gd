extends SceneTree
const Rules = preload("res://runtime/game_rules.gd")
const Scene = preload("res://runtime/game_scene.gd")
const Hit = preload("res://core/hit_resolver.gd")
var model
var scene
var resolver = Hit.new()
var mismatches = []
var count = 0
var golden = []
var row = 0
func _initialize():
	call_deferred("run")
func advance(n):
	for i in range(n):
		model.tick(1.0/60,true)
		scene.view_clock = model.total
		scene.build_pose()
func fire(id):
	for item in scene.hit_items:
		if item.id != id or item.kind not in ["primary","weak","protected","invalid"]:
			continue
		var box = item.bounds()
		for y in range(int(box.position.y),int(box.end.y),3):
			for x in range(int(box.position.x),int(box.end.x),3):
				var point = Vector2(x,y)
				var hit = resolver.exact(point,scene.hit_items)
				if hit.get("id","")==id and hit.get("kind","")==item.kind:
					model.command("SHOT",resolver.resolve(point,scene.hit_items))
					scene.build_pose()
					return
	mismatches.append("target unavailable: "+id)
func sample():
	for entry in golden[row].samples:
		var point = Vector2(entry.point[0],entry.point[1])
		var hit = resolver.resolve(point,scene.hit_items)
		if hit.get("id","")!=entry.id or hit.get("kind","miss")!=entry.kind or hit.get("assisted",false)!=entry.assisted:
			mismatches.append({"row":row,"point":entry.point,"expected":entry,"actual":hit})
		count += 1
	if JSON.stringify(JSON.parse_string(JSON.stringify(model.snapshot())),"",true)!=JSON.stringify(golden[row].state,"",true):
		mismatches.append({"row":row,"state_mismatch":true,"actual":model.snapshot(),"expected":golden[row].state})
	row += 1
func run():
	var path = ""
	var output = ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--baseline="):path = arg.trim_prefix("--baseline=")
		if arg.begins_with("--output="):output = arg.trim_prefix("--output=")
	if path.is_empty() or output.is_empty():
		push_error("Pass --baseline=<geometry_0.json> --output=<report.json>")
		quit(2)
		return
	golden = JSON.parse_string(FileAccess.get_file_as_string(path))
	model = Rules.new()
	model.setup(JSON.parse_string(FileAccess.get_file_as_string("res://runtime/level.json")))
	scene = Scene.new()
	scene.model = model
	root.add_child(scene)
	model.command("START")
	advance(210)
	sample()
	fire("lamp")
	advance(40)
	sample()
	fire("resident_ink")
	sample()
	advance(10)
	sample()
	advance(3)
	sample()
	model = Rules.new()
	model.setup(JSON.parse_string(FileAccess.get_file_as_string("res://runtime/level.json")))
	scene.model = model
	model.command("START")
	advance(1110)
	sample()
	var report = {"passed":mismatches.is_empty(),"samples":count,"mismatches":mismatches,"method":"CPU composition and original-resolver samples vs pinned pre-migration baseline"}
	FileAccess.open(output,FileAccess.WRITE).store_string(JSON.stringify(report,"\t"))
	print(JSON.stringify({"passed":report.passed,"samples":count,"mismatch_count":mismatches.size()}))
	scene.queue_free()
	quit(0 if mismatches.is_empty() else 1)
