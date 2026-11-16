extends SceneTree
const Runtime = preload("res://core/level_runtime.gd")
var passed = []
var failures = []
func check(value, label):
	(passed if value else failures).append(label)
	print(("PASS " if value else "FAIL ")+label)
func center(model, id):
	var e = model.entities[id]
	return Vector2(e.x+e.width*.5,e.y+e.height*.5)
func _initialize():
	var path = ""
	var asset_root = ""
	var report = ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):asset_root=arg.trim_prefix("--assets=")
		if arg.begins_with("--report="):report=arg.trim_prefix("--report=")
	if path.is_empty() or asset_root.is_empty():quit(2);return
	var build = JSON.parse_string(FileAccess.get_file_as_string(path))
	var model = Runtime.new()
	model.setup(build,asset_root)
	check(model.phase=="ready","neutral_ready_without_lives")
	model.start()
	check(model.entities.target_a.active and not model.entities.target_b.active,"time_zero_spawn")
	var r = model.command("SHOT",center(model,"target_a"))
	check(r.hit and not model.entities.target_a.active,"visible_alpha_target_neutralized")
	model.step()
	check(model.resources.score==100,"semantic_event_awards_score")
	for i in range(119):model.step()
	check(model.tick==120 and model.entities.target_b.active,"timed_spawn_at_2000ms")
	var x = model.entities.target_b.x
	for i in range(10):model.step()
	check(model.entities.target_b.x>x,"data_driven_motion")
	var saved = bytes_to_var(var_to_bytes(model.save_state()))
	model.command("SHOT",center(model,"target_b"))
	model.step()
	var expected = var_to_bytes(model.save_state())
	check(model.phase=="result" and model.result=="clear" and model.resources.score==200,"success_branch")
	model.restore_state(saved)
	model.command("SHOT",center(model,"target_b"))
	model.step()
	check(var_to_bytes(model.save_state())==expected,"snapshot_restores_events_resources_and_motion")
	model.start()
	model.command("SHOT",center(model,"protected_a"))
	model.step()
	check(model.result=="wrong_target" and model.resources.score==-50,"protected_target_failure_branch")
	model.start()
	for i in range(720):model.step()
	check(model.result=="timeout","timeout_branch")
	model.start()
	model.command("SHOT",center(model,"target_a"))
	for i in range(10):model.step()
	model.command("RELOAD")
	for i in range(30):model.step()
	check(model.resources.ammo==4 and model.reload_at==-1,"configured_reload")
	model.paused_reasons["manual"]=true
	model.paused_reasons["tracking"]=true
	var at=model.tick
	model.step()
	model.paused_reasons.erase("manual")
	model.step()
	check(model.tick==at,"pause_reasons_independent")
	model.paused_reasons.clear()
	model.start()
	var miss=model.command("SHOT",center(model,"target_a"),[])
	check(not miss.hit and model.entities.target_a.active,"empty_bound_pose_never_retargets_current_geometry")
	model.start()
	for i in range(170):model.step()
	check(not model.fired.has("zone_entry"),"movement_before_region_entry_does_not_start_timer")
	for i in range(60):model.step()
	check(model.fired.get("zone_entry",0)==1,"moving_target_region_entry_starts_timer_once")
	var result={"passed":passed,"failed":failures,"build_id":build.build_id}
	if not report.is_empty():FileAccess.open(report,FileAccess.WRITE).store_string(JSON.stringify(result,"\t"))
	print(JSON.stringify(result))
	quit(0 if failures.is_empty() else 1)
