extends SceneTree
const Rules = preload("res://runtime/game_rules.gd")
const Scene = preload("res://runtime/game_scene.gd")
var passed = []
var failed = []
func check(ok, label):
	(passed if ok else failed).append(label)
	print(("PASS " if ok else "FAIL ")+label)
func _initialize():call_deferred("run")
func run():
	var rules = Rules.new()
	rules.setup(JSON.parse_string(FileAccess.get_file_as_string("res://runtime/level.json")))
	rules.command("START")
	for i in range(210):rules.tick(1.0/60,true)
	var scene = Scene.new()
	scene.model = rules
	root.add_child(scene)
	rules.command("SHOT",{"kind":"primary","id":"resident_ink"})
	var at = rules.rescued_at
	var score = rules.score
	var hits = rules.hits
	scene.view_clock = rules.total
	scene.build_pose()
	var ink_target = false
	var paper_target = false
	for item in scene.hit_items:
		ink_target = ink_target or item.id=="resident_ink" and item.kind!=""
		paper_target = paper_target or item.id=="resident" and item.kind=="protected"
	check(not ink_target and not paper_target,"rescued_actor_and_residual_ink_not_targets")
	for i in range(10):rules.tick(1.0/60,true)
	rules.command("SHOT",{"kind":"primary","id":"resident_ink"})
	check(rules.score==score and rules.hits==hits and rules.rescued_at==at,"D02_stale_ink_hit_cannot_repeat_reward_or_restart_animation")
	for i in range(10):rules.tick(1.0/60,true)
	var lives = rules.lives
	rules.command("SHOT",{"kind":"protected","id":"resident"})
	check(rules.lives==lives and rules.score==maxi(0,score-100),"D08_paper_mistake_penalizes_score_only")
	rules.damage("real threat")
	check(rules.lives==lives-1,"independent_enemy_damage_still_applies")
	check(rules.ammo==3,"shots_still_spend_ammunition")
	print(JSON.stringify({"passed":passed,"failed":failed}))
	scene.queue_free()
	await process_frame
	quit(0 if failed.is_empty() else 1)
