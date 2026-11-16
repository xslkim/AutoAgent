extends RefCounted
## Input order and original pose binding survive delayed consumption/replay.
var capacity: int = 512
var max_shot_age_ms: int = 250
var next_order: int = 0
var pending: Array = []
var rejected: Array = []
var rejection_count: int = 0

func enqueue(event: Dictionary, target_tick: int, received_ms: int,
		submission_id: String = "", pose_id: String = "") -> bool:
	var reason = ""
	if not event.has("event") or target_tick < 0 or received_ms < 0:
		reason = "invalid_input"
	elif pending.size() >= capacity:
		reason = "queue_full"
	elif event.event == "SHOT" and (submission_id.is_empty() or pose_id.is_empty()):
		reason = "no_submitted_pose"
	elif not pending.is_empty() and target_tick < pending[-1].target_tick:
		reason = "nonmonotonic_target_tick"
	if not reason.is_empty():
		remember_rejection({"reason":reason,"order":next_order,"event":event.duplicate(true)})
		next_order += 1
		return false
	pending.append({"event":event.duplicate(true),"target_tick":target_tick,
		"received_ms":received_ms,"order":next_order,
		"submission_id":submission_id,"pose_id":pose_id})
	next_order += 1
	return true

func consume(at_tick: int, now_ms: int) -> Array:
	var result = []
	while not pending.is_empty() and pending[0].target_tick <= at_tick:
		var entry = pending.pop_front()
		if entry.event.event == "SHOT" and now_ms - entry.received_ms > max_shot_age_ms:
			remember_rejection({"reason":"expired_shot","order":entry.order,"event":entry.event})
		else:
			result.append(entry)
	return result

func snapshot() -> Dictionary:
	return {"version":1,"capacity":capacity,"max_shot_age_ms":max_shot_age_ms,
		"rejection_count":rejection_count,"next_order":next_order,"pending":pending.duplicate(true),"rejected":rejected.duplicate(true)}

func restore(data: Dictionary):
	assert(data.version == 1 and data.capacity > 0 and data.max_shot_age_ms >= 0)
	assert(data.pending.size() <= data.capacity)
	capacity = int(data.capacity)
	max_shot_age_ms = int(data.max_shot_age_ms)
	rejection_count = int(data.get("rejection_count",data.rejected.size()))
	next_order = int(data.next_order)
	pending = data.pending.duplicate(true)
	rejected = data.rejected.duplicate(true)

func remember_rejection(entry: Dictionary):
	rejection_count += 1
	rejected.append(entry)
	if rejected.size() > capacity:
		rejected.pop_front()
