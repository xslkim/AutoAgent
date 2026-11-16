extends SceneTree
const Loader=preload("res://core/level_loader.gd")
const Session=preload("res://core/level_session.gd")
func _initialize():
	var path="";var assets="";var report=""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):assets=arg.trim_prefix("--assets=")
		if arg.begins_with("--report="):report=arg.trim_prefix("--report=")
	var model=Loader.open(JSON.parse_string(FileAccess.get_file_as_string(path)),assets)
	if model==null:quit(2);return
	var session=Session.new();session.setup(model)
	var reference={};var checkpoints={};var began=Time.get_ticks_usec()
	for at in range(5400):
		session.step()
		if at%47==0:reference[at+1]=var_to_bytes(model.save_state())
	var seconds=(Time.get_ticks_usec()-began)/1000000.0
	var times=[];var failures=0
	for at in reference:
		began=Time.get_ticks_usec();session.seek(at);times.append((Time.get_ticks_usec()-began)/1000.0)
		if reference[at]!=var_to_bytes(model.save_state()):failures+=1
	times.sort()
	var p95=times[int(ceil(times.size()*.95))-1]
	var output={"build_id":model.build.build_id,"duration_seconds":90,"samples":times.size(),"seek_p95_ms":p95,"seek_max_ms":times[-1],"simulation_seconds":seconds,"simulation_speed_ratio":90/maxf(seconds,.000001),"checkpoint_bytes":var_to_bytes(session.checkpoints).size(),"comparison_failures":failures,"passed":failures==0 and p95<=300 and seconds<=9,"scope":"warm CPU fixture on this host; no GPU/phone latency claim"}
	if not report.is_empty():FileAccess.open(report,FileAccess.WRITE).store_string(JSON.stringify(output,"\t"))
	print(JSON.stringify(output));quit(0 if output.passed else 1)
