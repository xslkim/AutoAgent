extends SceneTree
const Loader=preload("res://core/level_loader.gd")
const Session=preload("res://core/level_session.gd")
var passed=[]
var failed=[]
func check(ok,label):
	(passed if ok else failed).append(label);print(("PASS " if ok else "FAIL ")+label)
func _initialize():
	var path="";var assets="";var report=""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):assets=arg.trim_prefix("--assets=")
		if arg.begins_with("--report="):report=arg.trim_prefix("--report=")
	var model=Loader.open(JSON.parse_string(FileAccess.get_file_as_string(path)),assets)
	if model==null:quit(2);return
	var session=Session.new();session.setup(model)
	check(not session.enqueue("SHOT",Vector2(220,230)),"shot_requires_render_submission")
	session.submit(model.geometry());session.enqueue("SHOT",Vector2(220,230))
	var pending=bytes_to_var(var_to_bytes(session.snapshot()))
	session.step();session.step()
	var expected=var_to_bytes(model.save_state())
	check(model.resources.score==100 and model.shots==1,"queued_shot_binds_submitted_geometry")
	session.restore(pending);session.step();session.step()
	check(expected==var_to_bytes(model.save_state()) and model.shots==1,"pending_queue_snapshot_restores_without_duplicate_consumption")
	var reference={}
	while session.clock.tick<660:
		session.step()
		if session.clock.tick in [119,120,239,400,659,660]:reference[session.clock.tick]=var_to_bytes(model.save_state())
	check(session.checkpoints[660].tape.is_empty() and session.snapshot().tape.size()==1,
		"seek_checkpoints_skip_input_tape_public_snapshots_keep_it")
	var trace_checkpoint: Array = session.checkpoints[660].model.trace
	var trace_bytes := var_to_bytes(trace_checkpoint)
	var timings=[]
	for at in [400,119,659,120,239,660]:
		var began=Time.get_ticks_usec();session.seek(at);timings.append((Time.get_ticks_usec()-began)/1000.0)
		check(reference[at]==var_to_bytes(model.save_state()),"seek_exact_tick_"+str(at))
	session.seek(120);session.submit(model.geometry());session.enqueue("RELOAD");session.step()
	check(session.tape.size()==2 and session.tape[-1].tick==121,"branch_retains_past_replaces_future")
	var recording=session.recording();session.load_recording(recording)
	for i in range(121):session.step()
	check(model.shots==1 and session.clock.tick==121,"recording_replays_same_build")
	check(var_to_bytes(trace_checkpoint)==trace_bytes,"checkpoint_trace_survives_seek_branch_and_restart")
	var at=session.clock.tick;session.set_pause("settings",true);session.set_pause("tracking",true);session.step();session.set_pause("settings",false);session.advance(1)
	check(session.clock.tick==at,"clearing_settings_does_not_clear_tracking_pause")
	session.set_pause("tracking",false);session.step();check(session.clock.tick==at+1,"resume_after_all_reasons_clear")
	session.enqueue("EXIT");session.step();at=session.clock.tick;session.step();check(session.closed and at==session.clock.tick,"closed_session_stops_simulation")
	var frame_states=[]
	for fps in [30,60,144]:
		session.start()
		for i in range(fps*10):session.advance(1.0/fps)
		frame_states.append(var_to_bytes(model.save_state()))
	check(frame_states[0]==frame_states[1] and frame_states[1]==frame_states[2],"30_60_144hz_identical_logical_state")
	session.start();session.real_time_inputs=true;session.submit(model.geometry());session.enqueue("SHOT",Vector2(220,230));session.queue.pending[0].received_ms-=300;session.step()
	check(model.shots==0 and session.queue.rejected[-1].reason=="expired_shot","live_stale_shot_rejected_after_wall_clock_stall")
	var output={"passed":passed,"failed":failed,"seek_ms":timings,"build_id":model.build.build_id,"seek_scope":"gallery 12s; warm in-process CPU, native binary checkpoints; not a 90s hardware benchmark"}
	if not report.is_empty():FileAccess.open(report,FileAccess.WRITE).store_string(JSON.stringify(output,"\t"))
	print(JSON.stringify(output));quit(0 if failed.is_empty() else 1)
