extends "train_stop_probe.gd"
## Play the continuous candidate with pose-bound queue input, retry and replay.

const Session = preload("res://core/level_session.gd")
const WAITING := "waiting_room.waiting_room"
const PLATFORM := "platform.platform"
const CAR := "green_car.green_car"
const BASE := "lantern_base.lantern_base"
const PULLBACK := "lantern_base.pullback"
const WORKBENCH := "lantern_base.workbench"

var session = Session.new()
var handoffs: Array[Dictionary] = []
var retry := {}
var replay := {}

func step_to(target: int) -> void:
	while model.tick < target and model.phase == "running":
		session.step()

func counters() -> Dictionary:
	return {"lives": int(model.resources.lives), "ammo": int(model.resources.ammo), "score": int(model.resources.score),
		"rescued": int(model.resources.rescued), "shots": model.shots}

func submitted_shot(point: Vector2, pose: Array) -> Dictionary:
	session.submit(pose)
	check(session.enqueue("SHOT", point), "submit a pose-bound shot")
	session.step()
	check(session.last_results.size() == 1, "one shot result")
	return session.last_results[0] if not session.last_results.is_empty() else {}

func shoot(target: String) -> Dictionary:
	step_to(model.next_shot)
	var pose: Array = model.geometry()
	var point = target_point(target, pose)
	if point == null:
		failures.append("cannot aim at " + target)
		return {}
	return submitted_shot(point, pose)

func hit(target: String) -> void:
	check(shoot(target).get("target") == target, "hit " + target)

func handoff(next: String, record := true) -> int:
	var from: String = model.current_section
	var state := counters()
	var deadline: int = model.tick + 240
	var cold := 0
	while model.current_section == from and model.phase == "running" and model.tick < deadline:
		check(not model.input_enabled, "no shooting between sections")
		session.step()
		if viewport != null:
			if model.current_section != from:
				cold = uncached_scene_textures()
			await process_frame
			await RenderingServer.frame_post_draw
	check(model.current_section == next and model.phase == "running", "transition to " + next)
	check(counters() == state, "preserve counters across " + next)
	if record:
		var entry := {"from": from, "to": next, "tick": model.tick, "resources": state}
		if viewport != null:
			entry["uncached_scene_textures"] = cold
			check(cold == 0, "cache all visible textures before " + next)
		handoffs.append(entry)
	return model.tick

func clear_waiting_room() -> void:
	check(model.current_section == WAITING, "start in the waiting room")
	step_to(335)
	check(model.resources.lives == 4, "one life is deliberately spent in the waiting room")
	hit(WAITING + ".lamp")
	hit(WAITING + ".umbrella")
	hit(WAITING + ".rescue")
	var crow := WAITING + ".crow"
	while model.effective_kind(model.entities[crow]) != "primary" and model.tick < 515 and model.phase == "running":
		session.step()
	hit(crow)
	check(not model.input_enabled, "waiting room clears")

func check_platform_failure_and_retry() -> void:
	clear_waiting_room()
	var old_pose: Array = model.geometry()
	var old_point = target_point(WAITING + ".lamp", old_pose)
	var entered: int = await handoff(PLATFORM, false)
	check(not model.entities[WAITING + ".lamp"].active and not model.entities["flow.waiting_room"].active,
		"the preceding stop is fully deactivated")
	check(old_point != null, "previous station lamp was in the submitted pose")
	if old_point != null:
		var stale := submitted_shot(old_point, old_pose)
		check(stale.get("reason") == "target_inactive" and not stale.get("hit", false), "old pose cannot activate a previous lamp")
	step_to(entered + 1100)
	check(model.result == "overrun" and model.current_section == PLATFORM and model.resources.lives == 0,
		"defeat occurs on the platform without advancing the level")
	var defeated := counters()
	var rejected := submitted_shot(Vector2(80, 180), model.geometry())
	check(rejected.get("reason") == "not_running" and counters() == defeated, "result rejects queued shots without spending ammo")
	session.start()
	check(model.current_section == WAITING and model.tick == 0 and model.resources == model.level.initial_resources and model.shots == 0,
		"retry restores the initial station and counters")
	retry = {"defeated_at": PLATFORM, "defeated_resources": defeated, "restart": counters()}

func clear_platform(entered: int) -> void:
	await capture("train_platform")
	hit(PLATFORM + ".crow")
	step_to(entered + 185)
	hit(PLATFORM + ".lamp")
	step_to(entered + 225)
	hit(PLATFORM + ".umbrella")
	hit(PLATFORM + ".rescue")

func clear_green_car(entered: int) -> void:
	hit(CAR + ".lamp")
	step_to(entered + 112)
	await capture("train_green_car")
	hit(CAR + ".crow")
	step_to(entered + 187)
	hit(CAR + ".umbrella")

func clear_base(entered: int) -> void:
	check(model.resources.ammo == 1, "one round remains after three stations")
	hit(BASE + ".lamp")
	check(model.resources.ammo == 0 and session.enqueue("RELOAD"), "last round lights the lamp and allows a queued reload")
	session.step()
	check(session.last_results.size() == 1 and session.last_results[0].get("ok", false), "reload is accepted at the fourth station")
	step_to(entered + 112)
	check(model.resources.ammo == 12, "reload restores a full magazine while the lamp is on")
	await capture("train_lantern_base")
	hit(BASE + ".crow")
	step_to(entered + 188)
	hit(BASE + ".umbrella")

func reach_workbench() -> int:
	await capture("train_waiting_room")
	clear_waiting_room()
	var entered: int = await handoff(PLATFORM)
	check(counters() == {"lives": 4, "ammo": 8, "score": 300, "rescued": 1, "shots": 4}, "first station carries earned resources")
	await clear_platform(entered)
	entered = await handoff(CAR)
	check(model.resources.rescued == 2 and model.resources.score == 600, "second rescue and score carry into the car")
	await clear_green_car(entered)
	entered = await handoff(BASE)
	await clear_base(entered)
	entered = await handoff(PULLBACK)
	var state := counters()
	check(submitted_shot(Vector2(888, 723), model.geometry()).get("reason") == "not_running" and counters() == state,
		"camera cut rejects queued shots")
	entered = await handoff(WORKBENCH)
	while not model.fired.has("lantern_base.pullback.settle") and model.tick < entered + 130 and model.phase == "running":
		session.step()
	await capture("train_workbench")
	return entered

func play_and_replay() -> void:
	var entered := await reach_workbench()
	step_to(entered + 190)
	check(model.result == "clear" and model.current_section == WORKBENCH and handoffs.size() == 5, "continuous preview ends at the workbench")
	var finished := counters()
	check(finished == {"lives": 4, "ammo": 10, "score": 1000, "rescued": 2, "shots": 14}, "final resources match the entire route")
	var record: Dictionary = session.recording()
	var trace: Array = model.trace.duplicate(true)
	await replay_recording(record)
	check(model.current_section == WORKBENCH and model.result == "clear" and counters() == finished and model.trace == trace,
		"replayed input reproduces the complete session")
	replay = {"inputs": record.tape.size(), "end_tick": record.end_tick, "final_resources": finished}

func replay_recording(record: Dictionary) -> void:
	session.load_recording(record)
	step_to(record.end_tick)

func run() -> void:
	if not open_candidate():
		quit(2)
		return
	if viewport != null:
		viewport.transparent_bg = true
	session.setup(model)
	await check_platform_failure_and_retry()
	await play_and_replay()
	print(JSON.stringify({"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"gpu_capture": viewport != null, "handoffs": handoffs, "retry": retry, "replay": replay}))
	quit(0 if failures.is_empty() else 1)
