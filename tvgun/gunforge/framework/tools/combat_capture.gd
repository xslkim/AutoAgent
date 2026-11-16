extends SceneTree
## Scripted software demonstration of the actual shared runtime, not human play.
const Loader=preload("res://core/level_loader.gd")
const Session=preload("res://core/level_session.gd")
const Audio=preload("res://core/level_audio.gd")
const Metrics=preload("res://core/visible_metrics.gd")
var model
var session=Session.new()
var audio
var output=""
var running=false
var last_action=-1
var captured={}
var lamp_sent=false
var next_target_shot=450
func _initialize():call_deferred("open")
func open():
	var build="";var assets=""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):build=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):assets=arg.trim_prefix("--assets=")
		if arg.begins_with("--output="):output=arg.trim_prefix("--output=")
	DirAccess.make_dir_recursive_absolute(output)
	model=Loader.open(JSON.parse_string(FileAccess.get_file_as_string(build)),assets)
	if model==null:quit(2);return
	root.size=Vector2i(1280,760);root.content_scale_size=Vector2i(1280,760);root.content_scale_mode=Window.CONTENT_SCALE_MODE_CANVAS_ITEMS
	var stage=Node2D.new();stage.scale=Vector2.ONE*(1280.0/1776);stage.position=Vector2(0,(760-936*stage.scale.x)*.5);root.add_child(stage)
	model.mount(stage);model.set_presentation_context("review","playing")
	session.setup(model);audio=Audio.new();root.add_child(audio);audio.setup(model,assets);audio.enabled=true;running=true
func _process(delta):
	if not running:return
	var at=session.clock.tick
	if at>=720:
		running=false
		FileAccess.open(output.path_join("input.bin"),FileAccess.WRITE).store_var(session.recording())
		FileAccess.open(output.path_join("state.json"),FileAccess.WRITE).store_string(JSON.stringify({"state":model.public_state(),"trace":model.trace,"build_id":model.build.build_id,"policy":"scripted diagnostic demonstration; first attack deliberately allowed, then support and shots"},"\t"))
		audio.clear();audio.queue_free();model.render_scene.queue_free()
		await process_frame
		model.render_scene=null;session.model=null;model=null;session=null
		for i in range(3):await process_frame
		quit();return
	if at!=last_action:
		var pose=model.geometry()
		if at>=322 and not lamp_sent:
			lamp_sent=true
			var sample=Metrics.sample(pose,model.resolver,Vector2(1776,936),8)
			if sample.targets.has("lamp"):
				session.submit(pose);session.enqueue("SHOT",sample.targets.lamp.aim)
		elif at>=next_target_shot:
			next_target_shot=at+12
			var sample=Metrics.sample(pose,model.resolver,Vector2(1776,936),8)
			for id in sample.targets:
				if model.target_role(id) not in ["target","projectile"] or sample.targets[id].aim==null:continue
				session.submit(pose);session.enqueue("SHOT",sample.targets[id].aim);break
			if model.resources.ammo==0:session.enqueue("RELOAD")
		last_action=at
	session.advance(delta);audio.sync()
	for mark in [260,314,336,462]:
		if session.clock.tick>=mark and not captured.has(mark):
			captured[mark]=true;capture_frame(mark)
func capture_frame(mark):
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(output.path_join("frame-%d.png" % mark))
