extends SceneTree
const Clock = preload("res://core/fixed_clock.gd")
const Queue = preload("res://core/tick_input_queue.gd")
var failures = []
var passed = []

func check(ok: bool, label: String):
	if ok:
		passed.append(label)
	else:
		failures.append(label)
	print(("PASS " if ok else "FAIL ") + label)

func _initialize():
	for fps in [30,60,144]:
		var c = Clock.new()
		var events = []
		var callback = func(t, _dt):
			if t % 60 == 0:
				events.append(t)
		for frame in range(fps * 78):
			c.advance_frame(1.0 / fps, callback)
		check(c.tick == 4680 and events.size() == 78, "78_second_clock_%dhz" % fps)
	var c = Clock.new()
	c.setup(60,2)
	c.advance_frame(1.0,func(_t,_dt): pass)
	check(c.tick == 2 and c.debt > 0.96,"catchup_retains_time_debt")
	var saved = c.snapshot()
	var restored = Clock.new()
	restored.restore(saved)
	for i in range(30):
		c.advance_frame(0,func(_t,_dt): pass)
		restored.advance_frame(0,func(_t,_dt): pass)
	check(c.tick == 60 and c.snapshot() == restored.snapshot(),"clock_restore_and_debt_drain")
	var q = Queue.new()
	check(not q.enqueue({"event":"SHOT"},1,0),"no_pose_shot_rejected")
	var event = {"event":"SHOT","aim":[100,200],"session":"phone1"}
	q.enqueue(event,1,0,"render_0","pose_0")
	event.aim[0] = 900
	q.enqueue({"event":"RELOAD"},1,1)
	var record = q.snapshot()
	var q2 = Queue.new()
	q2.restore(record)
	var entries = q.consume(1,100)
	check(entries == q2.consume(1,100),"input_restore_preserves_order")
	check(entries[0].event.aim[0] == 100 and entries[0].pose_id == "pose_0", "input_geometry_binding_and_data_frozen")
	check(entries[0].order < entries[1].order,"same_tick_input_order")
	q.enqueue({"event":"SHOT"},2,0,"render_1","pose_1")
	check(q.consume(2,251).is_empty() and q.rejected[-1].reason == "expired_shot","stale_shot_not_delayed_fire")
	q.capacity = 1
	q.enqueue({"event":"START"},3,300)
	check(not q.enqueue({"event":"RELOAD"},3,300),"queue_overflow_explicit")
	q.consume(3,300)
	q.enqueue({"event":"START"},5,300)
	check(not q.enqueue({"event":"EXIT"},4,300),"nonmonotonic_tick_rejected")
	print(JSON.stringify({"passed":passed,"failed":failures}))
	quit(0 if failures.is_empty() else 1)
