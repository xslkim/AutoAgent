extends RefCounted
signal input_consumed(order,result)
signal tick_completed
## Shared shell: input binding, recording, pause ownership, checkpoints and seek.
const Clock=preload("fixed_clock.gd")
const Queue=preload("tick_input_queue.gd")
const Codec=preload("pose_codec.gd")
var model
var clock=Clock.new()
var queue=Queue.new()
var tape=[]
var checkpoints={}
var submission=[]
var submission_id=""
var submission_serial=0
var pause_reasons={}
var closed=false
var checkpoint_interval=60
var last_results=[]
var real_time_inputs=false
var max_tick=0
func setup(runtime):
	model=runtime;start()
func start():
	clock.setup();queue=Queue.new();tape.clear();checkpoints.clear();pause_reasons.clear();closed=false
	submission=[];submission_id="";submission_serial=0;model.start();cache_checkpoint()
	max_tick=int(model.level.get("review_end_tick",model.level.deadline_tick))
func submit(pose):
	submission=Codec.encode(pose,model.geometry_assets());submission_serial+=1
	submission_id="submission:%d:tick:%d" % [submission_serial,clock.tick]
func enqueue(event,point=Vector2.ZERO):
	if closed or not pause_reasons.is_empty():return false
	if event=="SHOT" and submission_id.is_empty():return false
	# A new command after seeking starts an explicit branch; future records survive only in saved files.
	tape=tape.filter(func(entry):return entry.tick<=clock.tick)
	for at in checkpoints.keys():
		if at>clock.tick:checkpoints.erase(at)
	var payload={"event":event,"point":point}
	if event=="SHOT":payload.geometry=submission.duplicate(true)
	return queue.enqueue(payload,clock.tick+1,input_ms(),submission_id,"pose:"+submission_id)
func virtual_ms():return int(clock.tick*1000/60)
func input_ms():return Time.get_ticks_msec() if real_time_inputs else virtual_ms()
func apply(entry):
	if entry.event=="EXIT":closed=true;return {"ok":true,"closed":true}
	if entry.event=="SHOT":return model.command("SHOT",entry.point,Codec.decode(entry.geometry,model.geometry_assets()))
	return model.command(entry.event)
func consume(at,_dt):
	var scheduled_checkpoint: bool = at % checkpoint_interval == 0
	var delayed_checkpoint: bool = at > 1 and (at - 1) % checkpoint_interval == 0 and not checkpoints.has(at - 1)
	var previous_section = model.get("current_section") if scheduled_checkpoint else null
	max_tick=maxi(max_tick,at)
	last_results.clear()
	for entry in tape:
		if int(entry.tick)==at:last_results.append(apply(entry.input))
	var now=input_ms()
	for entry in queue.pending:
		if entry.target_tick<=at and entry.event.event=="SHOT" and now-entry.received_ms>queue.max_shot_age_ms:input_consumed.emit(entry.order,{"ok":false,"reason":"expired_shot"})
	for entry in queue.consume(at,now):
		var result=apply(entry.event)
		last_results.append(result);tape.append({"tick":at,"input":entry.event.duplicate(true),"binding":{"submission":entry.submission_id,"pose":entry.pose_id,"order":entry.order},"result":result.duplicate(true)})
		input_consumed.emit(entry.order,result)
	if not closed:model.step()
	# A section cut already rebuilds the displayed scene. Save its due checkpoint one tick later.
	if delayed_checkpoint or (scheduled_checkpoint and previous_section == model.get("current_section")):
		cache_checkpoint()
	if tick_completed.has_connections():
		tick_completed.emit()
func step():
	if not closed and pause_reasons.is_empty():clock.step(consume)
func advance(delta):
	if not closed and pause_reasons.is_empty():
		clock.advance_frame(delta, consume, func(): return pause_reasons.has("transition"))
func set_pause(reason,enabled):
	if enabled:pause_reasons[reason]=true
	else:pause_reasons.erase(reason)
func snapshot(include_tape := true):
	return _snapshot(model.save_state(), include_tape)
func _snapshot(model_state: Dictionary, include_tape: bool):
	return {"version":1,"build_id":model.build.build_id,"clock":clock.snapshot(),"queue":queue.snapshot(),"model":model_state,"tape":tape.duplicate(true) if include_tape else [],"submission":submission.duplicate(true),"submission_id":submission_id,"submission_serial":submission_serial,"closed":closed,"pause_reasons":pause_reasons.duplicate(true),"real_time_inputs":real_time_inputs,"wall_at":Time.get_ticks_msec() if real_time_inputs else 0}
func restore(saved):
	assert(saved.version==1 and saved.build_id==model.build.build_id)
	clock.restore(saved.clock);queue.restore(saved.queue);model.restore_state(saved.model)
	tape=saved.tape.duplicate(true)
	real_time_inputs=saved.get("real_time_inputs",false)
	if real_time_inputs:
		var offset=Time.get_ticks_msec()-int(saved.wall_at)
		for entry in queue.pending:entry.received_ms+=offset
	submission=saved.submission.duplicate(true);submission_id=saved.submission_id;submission_serial=int(saved.submission_serial);closed=saved.closed;pause_reasons=saved.pause_reasons.duplicate(true)
func cache_checkpoint():
	# Seeking restores the session's current input tape after loading a checkpoint.
	var model_state: Dictionary = model.save_checkpoint() if model.has_method("save_checkpoint") else model.save_state()
	checkpoints[clock.tick] = _snapshot(model_state, false)
func seek(at):
	assert(at>=0 and at<=max_tick)
	var nearest=0
	for key in checkpoints:
		if key<=at and key>nearest:nearest=key
	var full_tape=tape.duplicate(true)
	restore(checkpoints[nearest]);tape=full_tape;queue.pending.clear();pause_reasons.clear();closed=false
	while clock.tick<at:clock.step(consume)
	# A seek does not constitute a new RenderSubmission. Wait for the viewport to paint.
	submission=[];submission_id=""
func recording():
	return {"version":1,"build_id":model.build.build_id,"source_revision":model.build.source_revision,"seed":model.level.seed,"tape":tape.duplicate(true),"rejections":queue.rejected.duplicate(true),"end_tick":clock.tick,"submission_policy":"bound actual viewport pose; serialized alpha geometry and asset IDs"}
func load_recording(record):
	assert(record.version==1 and record.build_id==model.build.build_id and record.seed==model.level.seed)
	start();tape=record.tape.duplicate(true)
	max_tick=maxi(max_tick,int(record.end_tick))
func public_state():
	var lifecycle="closed" if closed else ("ready" if pause_reasons.has("ready") or model.phase=="ready" else ("paused" if not pause_reasons.is_empty() else ("result" if model.phase=="result" else "running")))
	return {"lifecycle":lifecycle,"pause_reasons":pause_reasons.keys(),"build_id":model.build.build_id,"tick":clock.tick,"game":model.public_state()}
