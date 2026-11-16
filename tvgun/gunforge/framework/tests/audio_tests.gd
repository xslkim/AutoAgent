extends SceneTree
const Loader=preload("res://core/level_loader.gd")
const Audio=preload("res://core/level_audio.gd")
var passed=[]
var failed=[]
func check(ok,label):
	(passed if ok else failed).append(label);print(("PASS " if ok else "FAIL ")+label)
func _initialize():call_deferred("run")
func run():
	var path="";var assets="";var report=""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):assets=arg.trim_prefix("--assets=")
		if arg.begins_with("--report="):report=arg.trim_prefix("--report=")
	var model=Loader.open(JSON.parse_string(FileAccess.get_file_as_string(path)),assets)
	if model==null:quit(2);return
	model.start()
	for i in range(110):model.step()
	check(model.active_cues.size()==1,"cue_envelope_starts_at_compiled_tick")
	var saved=model.save_state()
	var player=Audio.new();root.add_child(player);player.setup(model,assets);player.enabled=true;player.sync()
	await create_timer(.04).timeout
	check(player.players.size()==1,"wav_resource_decodes_and_plays")
	player.sync(true)
	check(player.players.is_empty(),"seeking_does_not_replay_historical_one_shots")
	# Explicit test-only loop fixture, never published or adopted as game content.
	model.level.cues.target_warning.loop=true;model.active_cues.values()[0].loop=true
	player.sync(true)
	check(player.players.size()==1,"loop_reconstructed_from_serialized_offset")
	await create_timer(.04).timeout
	model.restore_state(saved)
	for i in range(14):model.step()
	player.sync();check(model.active_cues.is_empty() and player.players.is_empty(),"expired_cue_stops_after_restore")
	var output={"passed":passed,"failed":failed,"build_id":model.build.build_id,"listening":"not performed; this checks state and decoder behavior"}
	if not report.is_empty():FileAccess.open(report,FileAccess.WRITE).store_string(JSON.stringify(output,"\t"))
	print(JSON.stringify(output));player.clear();player.queue_free();await process_frame;await create_timer(.05).timeout;quit(0 if failed.is_empty() else 1)
