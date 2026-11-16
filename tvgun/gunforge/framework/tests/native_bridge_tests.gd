extends SceneTree
const Loader=preload("res://core/level_loader.gd")
const Session=preload("res://core/level_session.gd")
const Codec=preload("res://core/pose_codec.gd")
var failed=[]
var comparisons=0
var path=""
var assets=""
var report=""
func _initialize():
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):assets=arg.trim_prefix("--assets=")
		if arg.begins_with("--report="):report=arg.trim_prefix("--report=")
	call_deferred("run")
func same(a,b,label):
	comparisons+=1
	if var_to_bytes(a)!=var_to_bytes(b) and failed.size()<10:failed.append(label)
func run():
	var model=Loader.open(JSON.parse_string(FileAccess.get_file_as_string(path)),assets)
	if model==null:quit(2);return
	var viewport=SubViewport.new();viewport.size=Vector2i(1776,936);root.add_child(viewport);model.mount(viewport)
	var session=Session.new();session.setup(model)
	var reference=load("res://runtime/game_rules.gd").new();reference.setup(JSON.parse_string(FileAccess.get_file_as_string("res://runtime/level.json")));reference.command("START")
	var scene=load("res://runtime/game_scene.gd").new();scene.model=reference;viewport.add_child(scene)
	var at_states={}
	for i in range(4700):
		session.step();reference.tick(1.0/60.0,true)
		same(model.rules.snapshot(),reference.snapshot(),"native_state_"+str(i))
		if i%60==0:
			scene.view_clock=reference.total;scene.build_pose()
			same(Codec.encode(model.geometry(),model.geometry_assets()),Codec.encode(scene.hit_items,scene.geometry_assets()),"native_pose_"+str(i))
		if session.clock.tick in [60,170,1850,3000,4600]:at_states[session.clock.tick]=var_to_bytes(model.save_state())
	for at in [3000,60,4600,170,1850]:
		session.seek(at);same(var_to_bytes(model.save_state()),at_states[at],"native_seek_"+str(at))
	session.start();var first=var_to_bytes(model.save_state());session.start();same(first,var_to_bytes(model.save_state()),"retry_initial_state_stable")
	var output={"comparisons":comparisons,"failed":failed,"passed":failed.is_empty(),"build_id":model.build.build_id,"scope":"shared scheduler and registered rules plugin: timeout/death path, same-tick public state and CPU geometry, seek"}
	if not report.is_empty():FileAccess.open(report,FileAccess.WRITE).store_string(JSON.stringify(output,"\t"))
	print(JSON.stringify(output));viewport.queue_free();await process_frame;quit(0 if failed.is_empty() else 1)
