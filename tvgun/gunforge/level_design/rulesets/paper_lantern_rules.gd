extends "res://runtime/game_rules.gd"
## Versioned rules plugin: continuous legacy envelopes and typed effects only.
## Spawn/warning/deadline/wave flow execute through the common scheduler.
const Scheduler=preload("res://core/event_scheduler.gd")
class ScheduleHost:
	extends RefCounted
	var build={}
	var level={}
	var phase="running"
	var tick=0
	var entities={}
	var resources={}
	var queries={}
	var fired={}
	var fired_time={}
	var trace=[]
	var owner_rule
	func compare(a,op,b):
		match op:
			"gte":return a>=b
			"gt":return a>b
			"eq":return a==b
			"lte":return a<=b
			"lt":return a<b
		return false
	func apply_action(action):owner_rule.get_ref().apply_effect(action.effect,action.params)
var schedule
var compiled={}
var schedule_tick=0
func setup(data):
	assert(data.get("format","")=="gunforge-compiled-level-v1")
	compiled=data;schedule=ScheduleHost.new();schedule.owner_rule=weakref(self);schedule.build=data;schedule.level=data.level
	super.setup(data)
func reset():
	schedule_tick=0
	if schedule!=null:schedule.trace.clear()
	super.reset()
func begin_wave():
	super.begin_wave()
	if schedule!=null:schedule.fired.clear();schedule.fired_time.clear()
func run_schedule():
	schedule.phase="running";schedule.tick=schedule_tick;schedule.queries.clear()
	for id in schedule.level.queries:
		var query=schedule.level.queries[id]
		var value=0.0
		match query.name:
			"local_clock":value=clock
			"state_clock":value=state_clock
			"wave":value=wave
			"playing","gap","transition","continue":value=1 if phase==query.name else 0
			"reload_due":value=1 if reload_until>=0 and clock>=reload_until else 0
			"enemy_waiting","enemy_alive","enemy_unwarned":
				var index=enemy_ids().find(query.subject)
				if index>=0:
					var enemy=enemies[index]
					value=(1 if not enemy.warned else 0) if query.name=="enemy_unwarned" else (1 if enemy.status==query.name.trim_prefix("enemy_") else 0)
		schedule.queries[id]={"value":value,"tick":schedule_tick,"space":"scalar","algorithm":"legacy-float60-v1"}
	Scheduler.run(schedule,[])
func apply_effect(effect,params):
	var index=enemy_ids().find(params.get("enemy",""))
	match effect:
		"reload_done":
			ammo=int(config.rules.magazine);reload_until=-1;notify("reload_done","光已装满")
		"enemy_spawn":enemies[index].status="alive"
		"enemy_warning":enemies[index].warned=true;notify("warning","墨鸦即将来袭")
		"enemy_expire":damage("墨鸦来袭");enemies[index].status="gone"
		"wave_end":
			phase="transition" if wave==config.waves.size()-1 else "gap";state_clock=0;notify("gap","准备下一波")
		"next_wave":wave+=1;begin_wave();schedule.phase="halted"
		"level_complete":phase="complete";notify("complete","巷口已点亮")
		"return_title":phase="title"
func tick(dt,locked):
	dt=maxf(0,dt);schedule_tick+=1
	if phase not in ["playing","gap","transition"]:
		state_clock+=dt;run_schedule();return
	if not locked:
		lost_seconds+=dt;resume=config.rules.resume_countdown
		if lost_seconds>=2:auto_paused=true
	else:
		lost_seconds=0
		if auto_paused:
			resume=maxf(0,resume-dt)
			if resume<=0:auto_paused=false
	if user_paused or auto_paused:return
	total+=dt
	if phase in ["gap","transition"]:state_clock+=dt;run_schedule();return
	clock+=dt
	lamp_amount=move_toward(lamp_amount,1.0 if clock<lamp_until else 0.0,dt/config.rules.light_fade_seconds)
	run_schedule()
func save_state():
	var saved=super.save_state()
	saved.scheduler={"tick":schedule_tick,"fired":schedule.fired.duplicate(true),"fired_time":schedule.fired_time.duplicate(true),"trace":schedule.trace.duplicate(true),"queries":schedule.queries.duplicate(true),"phase":schedule.phase}
	return saved
func restore_state(saved):
	super.restore_state(saved)
	schedule_tick=int(saved.scheduler.tick);schedule.tick=schedule_tick
	for key in ["fired","fired_time","trace","queries"]:schedule.set(key,saved.scheduler[key].duplicate(true))
	schedule.phase=saved.scheduler.phase
