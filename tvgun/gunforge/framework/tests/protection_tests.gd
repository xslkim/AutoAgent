extends SceneTree
const Loader=preload("res://core/level_loader.gd")
var passed=[]
var failed=[]
func check(ok,label):
	(passed if ok else failed).append(label);print(("PASS " if ok else "FAIL ")+label)
func center(model,id):
	var e=model.entities[id];return Vector2(e.x+e.width*.5,e.y+e.height*.5)
func _initialize():
	var path="";var assets="";var report=""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):assets=arg.trim_prefix("--assets=")
		if arg.begins_with("--report="):report=arg.trim_prefix("--report=")
	var model=Loader.open(JSON.parse_string(FileAccess.get_file_as_string(path)),assets)
	if model==null:quit(2);return
	model.start()
	check(not model.resources.has("ammo") and not model.resources.has("lives"),"independent_hull_merit_resources")
	var blocked=model.command("SHOT",center(model,"drone"))
	check(not blocked.hit and model.entities.drone.health==2,"shield_blocks_damage")
	for i in range(120):model.step()
	model.command("SHOT",center(model,"drone"));model.command("SHOT",center(model,"drone"));model.step()
	check(not model.entities.drone.active and model.resources.merit==200,"open_window_two_hit_target_reward_once")
	var saved=bytes_to_var(var_to_bytes(model.save_state()))
	model.command("SHOT",center(model,"bolt_a"));model.step()
	for i in range(240):model.step()
	model.command("SHOT",center(model,"bolt_b"));model.step()
	while model.tick<720:model.step()
	check(model.result=="convoy_safe" and model.resources.hull==2 and model.resources.merit==900,"intercept_both_and_protect_success")
	var expected=var_to_bytes(model.save_state())
	model.restore_state(saved);model.command("SHOT",center(model,"bolt_a"));model.step()
	for i in range(240):model.step()
	model.command("SHOT",center(model,"bolt_b"));model.step()
	while model.tick<720:model.step()
	check(expected==var_to_bytes(model.save_state()),"branch_checkpoint_bit_exact_replay")
	model.start()
	for i in range(720):model.step()
	check(model.result=="convoy_lost" and model.resources.hull==0,"unintercepted_projectiles_fail_objective")
	model.start();model.command("SHOT",center(model,"shield"));model.step()
	check(model.entities.drone.kind=="weak","activation_overrides_shield_window")
	model.start();model.command("SHOT",center(model,"convoy"));model.step()
	check(model.resources.merit==-100 and model.resources.hull==2,"protected_object_hit_policy")
	model.start()
	for i in range(300):model.step()
	check(model.entities.drone.kind=="invalid","shield_closes_at_declared_time")
	var output={"passed":passed,"failed":failed,"build_id":model.build.build_id}
	if not report.is_empty():FileAccess.open(report,FileAccess.WRITE).store_string(JSON.stringify(output,"\t"))
	print(JSON.stringify(output));quit(0 if failed.is_empty() else 1)
