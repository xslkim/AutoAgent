extends RefCounted
## Explicit migration bridge for registered native rules; never selected by game ID.
const Resolver = preload("hit_resolver.gd")
var build = {}
var level = {}
var rules
var scene
var tick = 0
var phase = "ready"
var result = ""
var resources = {}
var entities = {}
var queries = {}
var fired = {}
var trace=[]
var images = {}
var paused_reasons = {}
var shots = 0
var hits = 0
var profile = {}
var resolver = Resolver.new()
var active_cues={}
var cue_serial=0
var event_cursor=0
func setup(compiled, asset_root):
	build = compiled.duplicate(true);level=build.level
	var catalog=JSON.parse_string(FileAccess.get_file_as_string(asset_root.path_join("gunforge/level_design/specs/capabilities-v1.json")))
	profile=catalog.rulesets[level.ruleset]
	rules=load(asset_root.path_join(profile.native_rules)).new()
	rules.setup(build)
	scene=load(asset_root.path_join(profile.native_scene)).new()
	scene.model=rules
	sync_state()
func mount(parent):
	parent.add_child(scene)
	scene.update_frame()
func sync_state():
	phase="ready" if rules.phase=="title" else ("running" if rules.phase in ["playing","gap","transition"] else "result")
	result=rules.phase if phase=="result" else ""
	resources.clear()
	for id in profile.resources_map:resources[id]=rules.get(profile.resources_map[id])
	shots=rules.shots;hits=rules.hits
	if "schedule" in rules:
		queries=rules.schedule.queries.duplicate(true);fired=rules.schedule.fired.duplicate(true);trace=rules.schedule.trace.duplicate(true)
	entities={}
	for id in rules.enemy_ids():entities[id]={"native":true,"wave":rules.wave}
	while event_cursor<rules.events.size():
		var event=rules.events[event_cursor]
		cue(event.event);event_cursor+=1
func start():
	tick=0;paused_reasons.clear();rules=rules.get_script().new();rules.setup(build);rules.reset();scene.model=rules;event_cursor=0;active_cues.clear();cue_serial=0
	scene.flash_time=-10.0;scene.flash_point=Vector2.ZERO;scene.last_kind=""
	sync_state();refresh_pose()
func refresh_pose():
	if scene.is_inside_tree():
		scene.view_clock=rules.get(profile.view_clock_field);scene.build_pose();scene.update_frame()
func step():
	if not paused_reasons.is_empty():return
	tick+=1
	for id in active_cues.keys():
		if tick>=active_cues[id].end_tick:active_cues.erase(id)
	rules.tick(1.0/60.0,true);sync_state();refresh_pose()
func geometry():return scene.hit_items
func geometry_assets():return scene.geometry_assets()
func target_role(id):return profile.get("target_roles",{}).get(id,"target")
func available_commands():return ["START","EXIT","RELOAD","COIN"] if rules.phase=="continue" else ["START","EXIT","RELOAD"]
func command(event, point=Vector2.ZERO, bound_geometry=null):
	if not paused_reasons.is_empty():return {"ok":false,"reason":"paused"}
	var pose=geometry() if bound_geometry==null else bound_geometry
	var hit=resolver.resolve(point,pose,15) if event=="SHOT" else {}
	# Frozen geometry is not authority to hit an actor already cleared in live state.
	if event=="SHOT":
		var current=geometry().filter(func(item):return item.id==hit.get("id","") and item.kind==hit.get("kind",""))
		if current.is_empty():hit={}
	var before_hits=rules.hits
	var ok=rules.command(event,hit,false,true)
	if event=="SHOT" and ok:
		cue("shot");scene.flash_time=rules.total;scene.flash_point=point;scene.last_kind=hit.get("kind","miss")
	sync_state();refresh_pose()
	return {"ok":ok,"hit":rules.hits>before_hits,"native":rules.last_result.duplicate(true)}
func public_state():
	return {"tick":tick,"phase":phase,"result":result,"resources":resources.duplicate(true),"shots":shots,"hits":hits,"native":rules.snapshot(),"pause_reasons":paused_reasons.keys()}
func save_state():
	return {"version":1,"build_id":build.build_id,"tick":tick,"native":rules.save_state(),"pause_reasons":paused_reasons.duplicate(true),"active_cues":active_cues.duplicate(true),"cue_serial":cue_serial,"event_cursor":event_cursor,"flash_time":scene.flash_time,"flash_point":scene.flash_point,"last_kind":scene.last_kind}
func restore_state(saved):
	assert(saved.version==1 and saved.build_id==build.build_id)
	tick=int(saved.tick);paused_reasons=saved.pause_reasons.duplicate(true);rules.restore_state(saved.native)
	active_cues=saved.active_cues.duplicate(true);cue_serial=int(saved.cue_serial);event_cursor=int(saved.event_cursor)
	scene.flash_time=saved.flash_time;scene.flash_point=saved.flash_point;scene.last_kind=saved.last_kind
	sync_state();refresh_pose()
func cue(event):
	var id=level.ruleset_data.presentation.cue_bindings.get(event,"")
	if not level.cues.has(id):return
	cue_serial+=1
	var definition=level.cues[id]
	active_cues[str(cue_serial)]={"cue":id,"start_tick":tick,"end_tick":tick+int(ceil(definition.duration_ms*60/1000.0)),"loop":false}
func review_events():
	var entries=[]
	var native=level.ruleset_data.native_level
	for wid in native.wave_order:
		var wave=native.waves[wid]
		for eid in wave.enemy_order:
			entries.append({"id":wid+"/"+eid,"when":"波内 %.2f–%.2f 秒" % [wave.enemies[eid].at,wave.enemies[eid].deadline],"source":"/ruleset_data/native_level/waves/"+wid+"/enemies/"+eid,"design":wave.enemies[eid]})
		for key in ["resident_at","pickup_at"]:
			entries.append({"id":wid+"/"+key,"when":"波内 %.2f 秒" % wave[key],"source":"/ruleset_data/native_level/waves/"+wid+"/"+key,"design":wave[key]})
	return entries
