extends SceneTree
const Loader=preload("res://core/level_loader.gd")
const Session=preload("res://core/level_session.gd")
const Metrics=preload("res://core/visible_metrics.gd")
var path=""
var assets=""
var report=""
var idle=false
var expected_result=""
func _initialize():
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):assets=arg.trim_prefix("--assets=")
		if arg.begins_with("--report="):report=arg.trim_prefix("--report=")
		if arg=="--idle":idle=true
		if arg.begins_with("--expected="):expected_result=arg.trim_prefix("--expected=")
	call_deferred("run")
func run():
	var model=Loader.open(JSON.parse_string(FileAccess.get_file_as_string(path)),assets)
	if model==null:quit(2);return
	var viewport
	if model.has_method("mount"):
		viewport=SubViewport.new();viewport.size=Vector2i(model.level.layout.width,model.level.layout.height);root.add_child(viewport);model.mount(viewport)
	var session=Session.new();session.setup(model)
	var warnings=[];var observations=[]
	var began=Time.get_ticks_usec()
	for at in range(int(model.level.deadline_tick)+120):
		if not idle and at%12==0 and model.phase=="running":
			var pose=model.geometry()
			var visible=Metrics.sample(pose,model.resolver,Vector2(model.level.layout.width,model.level.layout.height),8)
			var candidates=[];var need_activation=false
			for target in visible.targets.values():
				if target.kinds.has("invalid"):need_activation=true
			for id in visible.targets:
				var target=visible.targets[id]
				if target.aim==null:continue
				var role=model.target_role(id)
				if role=="activation_source" and not need_activation:continue
				candidates.append({"id":id,"point":target.aim,"priority":0 if role=="activation_source" else 1})
			candidates.sort_custom(func(a,b):return a.id<b.id if a.priority==b.priority else a.priority<b.priority)
			if not candidates.is_empty():
				session.submit(pose);session.enqueue("SHOT",candidates[0].point)
			if at%60==0:
				observations.append({"tick":at,"visibility":visible})
				for warning in visible.warnings:
					warning.tick=at;warnings.append(warning)
			if model.resources.get("ammo",1)==0:session.enqueue("RELOAD")
		session.step()
		if model.phase=="result":break
	var elapsed=(Time.get_ticks_usec()-began)/1000000.0
	var output={"build_id":model.build.build_id,"source_revision":model.build.source_revision,"state":model.public_state(),"ticks":session.clock.tick,"elapsed_seconds":elapsed,"simulation_speed_ratio":session.clock.tick/60.0/maxf(elapsed,.000001),"observations":observations,"warnings":warnings,"input_count":session.tape.size(),"policy":"visible-alpha-only diagnostic bot; 200ms action interval, 8px grid; no human difficulty prediction","passed":model.phase=="result" and model.result in ["clear","convoy_safe","complete"]}
	if not expected_result.is_empty():output.passed=model.phase=="result" and model.result==expected_result
	output.trace=model.trace.duplicate(true)
	if not report.is_empty():
		FileAccess.open(report,FileAccess.WRITE).store_string(JSON.stringify(output,"\t"))
		FileAccess.open(report+".input.bin",FileAccess.WRITE).store_var(session.recording())
	print(JSON.stringify({"passed":output.passed,"result":model.result,"elapsed_seconds":elapsed,"inputs":session.tape.size()}))
	if viewport!=null:viewport.queue_free();await process_frame
	quit(0 if output.passed else 1)
