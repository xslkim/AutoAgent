extends SceneTree
## Shared player shell. Device coordinates and UI never access game-specific fields.
const Loader=preload("res://core/level_loader.gd")
const Session=preload("res://core/level_session.gd")
const Review=preload("res://tools/level_review.gd")
const Frame=preload("res://core/screen_frame.gd")
const Gun=preload("res://core/gun_input.gd")
const Http=preload("res://core/http_controls.gd")
const Audio=preload("res://core/level_audio.gd")
const Calibration=preload("res://core/calibration.gd")
const Metrics=preload("res://core/visible_metrics.gd")
const Codec=preload("res://core/pose_codec.gd")
const Opening=preload("res://tools/opening_cinematic.gd")
const DisplaySetup=preload("res://tools/display_setup.gd")

const GUN_PORT := 9000
const HTTP_PORT := 8080

class DesktopInput extends Node:
	var handle_key: Callable

	func _input(event: InputEvent) -> void:
		if event is InputEventKey and event.pressed and not event.echo:
			if handle_key.call(event.keycode):
				get_viewport().set_input_as_handled()

var session=Session.new()
var frame=Frame.new()
var gun=Gun.new()
var http=Http.new()
var discovered_http=Http.new()
var model
var preview
var status
var audio
var border
var dark
var network=false
var build_path=""
var assets=""
var quit_after=0.0
var elapsed=0.0
var completions={}
var calibration=Calibration.new()
var isolated_settings=false
var opening_directory := ""
var opening: Opening
var opening_pending := false
var transition: Opening
var transition_directory := ""
var transition_clips: Dictionary = {}
var previous_scene := ""
var show_paper_crosshair := true
var pressed_action := ""
var display_setup: DisplaySetup
var display_settings_path := "user://settings.cfg"
func _initialize():
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):build_path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):assets=arg.trim_prefix("--assets=")
		if arg.begins_with("--quit-after="):quit_after=float(arg.trim_prefix("--quit-after="))
		if arg=="--network":network=true
		if arg=="--isolated-settings":isolated_settings=true
		if arg.begins_with("--opening-dir="):opening_directory=arg.trim_prefix("--opening-dir=")
		if arg.begins_with("--transitions-dir="):transition_directory=arg.trim_prefix("--transitions-dir=")
	call_deferred("open")
func open():
	model=Loader.open(JSON.parse_string(FileAccess.get_file_as_string(build_path)),assets)
	if model==null:quit(2);return
	# The tracking frame fits the native window directly.
	root.content_scale_mode = Window.CONTENT_SCALE_MODE_DISABLED
	root.title="GunForge — "+model.level.id;root.size=Vector2i(1280,720)
	border=ColorRect.new();border.color=Color.WHITE;root.add_child(border)
	dark=ColorRect.new();dark.color=Color.BLACK;root.add_child(dark)
	preview=Review.Preview.new();preview.owner_tool=self;preview.model=model;preview.overlay=false;preview.clip_contents=true;root.add_child(preview)
	var desktop_input = DesktopInput.new()
	desktop_input.handle_key = handle_key
	root.add_child(desktop_input)
	if model.has_method("mount"):
		var viewport=SubViewport.new();viewport.size=Vector2i(model.level.layout.width,model.level.layout.height);viewport.disable_3d=true;root.add_child(viewport);model.mount(viewport);preview.native_viewport=viewport
	session.real_time_inputs=true
	session.setup(model)
	if not transition_directory.is_empty():
		var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(transition_directory.path_join("transitions.json")))
		if manifest is Dictionary:
			for clip in manifest.get("transitions", []):
				transition_clips[[clip.from, clip.to]] = clip.file.get_basename() + ".ogv"
	previous_scene = cinematic_scene()
	if not transition_clips.is_empty():
		session.tick_completed.connect(check_transition)
	session.set_pause("ready",true)
	session.input_consumed.connect(finish_input)
	status=Label.new();status.mouse_filter=Control.MOUSE_FILTER_IGNORE;root.add_child(status)
	status.visible=model.level.get("presentation",{}).get("debug_shell",true)
	var font=SystemFont.new();font.font_names=PackedStringArray(["Microsoft YaHei"]);status.add_theme_font_override("font",font)
	audio=Audio.new();root.add_child(audio);audio.setup(model,assets);audio.enabled=true
	if not opening_directory.is_empty():
		opening = Opening.new()
		if opening.configure(opening_directory):
			root.add_child(opening)
			opening_pending = true
			opening.completed.connect(start_gameplay)
		else:
			opening.free()
			opening = null
	display_setup = DisplaySetup.new()
	display_setup.configure(frame, calibration, "" if isolated_settings else display_settings_path)
	display_setup.frame_changed.connect(refresh_display_frame)
	display_setup.closed.connect(func(): session.set_pause("display_setup", false))
	root.add_child(display_setup)
	# The Android client uses the discovery reply's port for both aim and HTTP
	# controls. Saved HTTP clients search their previously configured port + 1.
	gun.open(GUN_PORT, [8001, HTTP_PORT + 1, GUN_PORT + 1])
	http.open(HTTP_PORT, handle_http)
	discovered_http.open(GUN_PORT, handle_http)
	root.size_changed.connect(layout);layout()
	print(JSON.stringify({"level_player_ready":true,"build_id":model.build.build_id,"udp_errors":gun.bind_errors,
		"http_error":http.bind_error,"discovered_http_error":discovered_http.bind_error}))

func close_player() -> void:
	gun.close()
	http.close()
	discovered_http.close()
	quit()

func layout():
	var box=frame.screen_rect(root.size);border.position=box.position;border.size=box.size
	var inset=frame.white*box.size.x/1920.0;dark.position=box.position+Vector2.ONE*inset;dark.size=box.size-Vector2.ONE*inset*2
	box=frame.content_rect(root.size);preview.position=box.position;preview.size=box.size;status.position=box.position+Vector2(8,8)
	if opening != null:
		opening.position = box.position
		opening.size = box.size
	if transition != null:
		transition.position = box.position
		transition.size = box.size
	display_setup.size = Vector2(root.size)
	display_setup.queue_redraw()

func refresh_display_frame() -> void:
	gun.last_frame_sent = -100
	layout()

func open_display_setup() -> void:
	session.set_pause("display_setup", true)
	for entry in session.queue.pending:
		finish_input(entry.order, {"ok": false, "reason": "display_setup"})
	session.queue.pending.clear()
	display_setup.begin()

func menu_action() -> String:
	if not model.level.get("presentation", {}).has("hud_art") or display_setup.visible:
		return ""
	if (opening != null and opening.visible) or transition != null:
		return ""
	if model.phase == "result":
		return "retry"
	return "start" if session.pause_reasons.has("ready") else ""

func handle_action_pointer(point: Vector2, pressed: bool) -> bool:
	var action := menu_action()
	var inside: bool = not network and not action.is_empty() and model.render_scene.paper_hud.action_rect(action == "retry").has_point(point)
	if pressed:
		if not inside:
			return false
		pressed_action = action
		return true
	if pressed_action.is_empty():
		return false
	var activate := inside and pressed_action == action
	pressed_action = ""
	if activate:
		enqueue_device({"event": "START"})
	return true

func queue_shot(point,_pose):
	if display_setup.visible:return
	if network or not in_playfield(point):return
	if opening != null and opening.visible:return
	if session.pause_reasons.has("ready") or model.phase=="result":
		enqueue_device({"event":"START"})
		return
	session.enqueue("SHOT",point)

func in_playfield(point: Vector2) -> bool:
	return Rect2(Vector2.ZERO,Vector2(model.level.layout.width,model.level.layout.height)).has_point(point)
func from_norm(point: Vector2) -> Vector2:
	return from_calibrated_norm(calibration.apply(point))

func from_calibrated_norm(point: Vector2) -> Vector2:
	# A resize can change the window before the preview has drawn its new scale.
	var content: Vector2 = frame.content_size()
	var canvas := Vector2(model.level.layout.width, model.level.layout.height)
	var scale := minf(content.x / canvas.x, content.y / canvas.y)
	var letterbox := (content - canvas * scale) * .5
	var inset: Vector2 = Vector2.ONE * (frame.white + frame.dark)
	return (point - inset - letterbox) / scale

func device_shot(raw: Vector2) -> Dictionary:
	var calibrated := calibration.apply(raw)
	if not calibrated.is_finite():
		return {}
	return {"event": "RELOAD" if frame.offscreen(calibrated) else "SHOT",
		"point": from_calibrated_norm(calibrated)}

func enqueue_device_shot(point: Vector2) -> bool:
	if in_playfield(point):
		return session.enqueue("SHOT", point)
	# The frame margins spend a round but cannot hit off-canvas geometry.
	# Enqueue copies the geometry immediately and keeps the rendered submission ID.
	var painted_pose: Array = session.submission
	session.submission = []
	var accepted: bool = session.enqueue("SHOT", point)
	session.submission = painted_pose
	return accepted

func enqueue_device(event):
	var command=event.event
	if display_setup.visible:
		match command:
			"SHOT": display_setup.sample(event.aim)
			"START": display_setup.handle_key(KEY_ENTER)
			"EXIT": display_setup.handle_key(KEY_ESCAPE)
		return
	if command=="AIM":return
	if command=="LOST":
		for entry in session.queue.pending:
			if entry.event.event=="SHOT":finish_input(entry.order,{"ok":false,"reason":"tracking_lost"})
		session.queue.pending=session.queue.pending.filter(func(entry):return entry.event.event!="SHOT");return
	if opening != null and opening.visible:
		if command in ["START", "EXIT"]:opening.finish()
		return
	if transition != null:
		if command in ["START", "EXIT"]:
			transition.finish()
		return
	if command in ["START", "EXIT"] and model.available_commands().has("SKIP"):
		session.enqueue("SKIP")
		return
	if command=="EXIT":session.set_pause("manual",not session.pause_reasons.has("manual"));return
	if command=="START":
		if opening_pending:
			opening_pending = false
			opening.begin()
		else:
			start_gameplay()
		return
	if command=="SHOT":
		var shot := device_shot(event.aim)
		if shot.is_empty():
			return
		var action := menu_action()
		if not action.is_empty():
			if model.render_scene.paper_hud.action_rect(action == "retry").has_point(shot.point):
				enqueue_device({"event": "START"})
			return
		if shot.event == "SHOT":
			enqueue_device_shot(shot.point)
		elif model.available_commands().has("RELOAD"):
			session.enqueue("RELOAD")
	else:session.enqueue(command)
func start_gameplay():
	if model.phase=="result":
		for order in completions.keys():finish_input(order,{"ok":false,"reason":"session_restarted"})
		session.start();audio.clear()
		previous_scene = cinematic_scene()
	session.set_pause("tracking",network and not gun.valid)
	session.set_pause("ready",false)
	session.set_pause("manual",false)

func cinematic_scene() -> String:
	if transition_clips.is_empty():
		return ""
	var section := String(model.get("current_section"))
	match section:
		"story.cinema_intro": return "cinema.ticket_office"
		"story.train_station_intro": return "waiting_room"
		"lantern_base.pullback": return "lantern_base.workbench"
	if section.begins_with("cinema.") or section.begins_with("lantern_base."):
		return section
	return section.get_slice(".", 0)

func check_transition() -> void:
	var next_scene := cinematic_scene()
	if transition != null or next_scene == previous_scene:
		return
	var file: String = transition_clips.get([previous_scene, next_scene], "")
	previous_scene = next_scene
	if file.is_empty():
		return
	var player := Opening.new()
	if not player.configure_video(transition_directory.path_join("game").path_join(file)):
		player.free()
		return
	transition = player
	session.set_pause("transition", true)
	# Discard inputs queued against the outgoing scene.
	for entry in session.queue.pending:
		finish_input(entry.order, {"ok": false, "reason": "transition"})
	session.queue.pending.clear()
	session.submission.clear()
	session.submission_id = ""
	root.add_child(player)
	root.move_child(player, display_setup.get_index())
	layout()
	player.completed.connect(func():
		transition = null
		session.set_pause("transition", false)
		player.queue_free()
	)
	player.begin()

func _process(delta):
	if model==null:return
	elapsed+=delta
	var events=gun.poll(elapsed,frame.white,frame.dark)
	session.set_pause("tracking",network and not gun.valid)
	if network or display_setup.visible:
		for event in events:enqueue_device(event)
	http.poll()
	discovered_http.poll()
	session.advance(delta)
	for order in completions.keys():
		if elapsed-completions[order].at>5:completions.erase(order)
	if session.closed:
		close_player()
		return
	var lifecycle: String = session.public_state().lifecycle
	if model.has_method("set_presentation_context"):model.set_presentation_context("player",lifecycle)
	if model.level.get("presentation", {}).has("hud_art"):
		var point := Vector2.INF
		if network and gun.valid:
			point = from_norm(gun.aim)
		elif not network:
			point = (preview.get_local_mouse_position() - preview.origin) / preview.scale_factor
		var hud = model.render_scene.paper_hud
		hud.aim = point if show_paper_crosshair and lifecycle == "running" else Vector2.INF
		hud.tracking_lost = (lifecycle == "paused" and model.phase == "running"
			and session.pause_reasons.has("tracking") and not session.pause_reasons.has("manual")
			and not display_setup.visible)
		var action := menu_action()
		if network or pressed_action != action:
			pressed_action = ""
		hud.action_hovered = not action.is_empty() and hud.action_rect(action == "retry").has_point(point)
		hud.action_pressed = hud.action_hovered and not pressed_action.is_empty()
	audio.sync()
	for player in audio.players.values():player.stream_paused=not session.pause_reasons.is_empty()
	var reload_hint = "　R 换弹" if model.available_commands().has("RELOAD") else ""
	status.text="%s  %s  %s\nEnter 开始 / 重试 / 恢复%s　Esc 暂停　G 光枪模式　Q 退出" % [lifecycle,JSON.stringify(model.resources),str(session.pause_reasons.keys()),reload_hint]
	preview.queue_redraw()
	if quit_after>0 and elapsed>=quit_after:close_player()
func handle_key(keycode: Key) -> bool:
	if keycode == KEY_F11:
		var fullscreen := DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_FULLSCREEN
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED if fullscreen else DisplayServer.WINDOW_MODE_FULLSCREEN)
		return true
	if display_setup.visible and keycode != KEY_Q:
		display_setup.handle_key(keycode)
		return true
	if keycode in [KEY_F2, KEY_C]:
		if (opening != null and opening.visible) or transition != null:return false
		open_display_setup()
		if keycode == KEY_C:display_setup.begin_calibration()
		return true
	match keycode:
		KEY_ENTER, KEY_KP_ENTER:enqueue_device({"event":"START"})
		KEY_ESCAPE:enqueue_device({"event":"EXIT"})
		KEY_R:
			if not model.available_commands().has("RELOAD"):return false
			session.enqueue("RELOAD")
		KEY_G:network=not network
		KEY_H:
			if not model.level.get("presentation", {}).has("hud_art"):return false
			show_paper_crosshair = not show_paper_crosshair
		KEY_Q:close_player()
		_:return false
	return true
func handle_http(command,payload,completion):
	if command=="STATE":
		var targets=[]
		var pose=Codec.decode(session.submission,model.geometry_assets())
		var visible=Metrics.sample(pose,model.resolver,Vector2(model.level.layout.width,model.level.layout.height),8)
		for id in visible.targets:
			var point=visible.targets[id].aim
			if point!=null:targets.append({"id":id,"point":[point.x,point.y]})
		var lifecycle = "opening" if opening != null and opening.visible else ("transition" if transition != null else session.public_state().lifecycle)
		var shot_input_enabled = lifecycle == "running" and (not ("input_enabled" in model) or model.input_enabled)
		var state = {"ok":true,"phase":model.phase,"lifecycle":lifecycle,"shot_input_enabled":shot_input_enabled,"resources":model.resources.duplicate(true),"score":model.resources.get("score",0),"build_id":model.build.build_id,"shots":model.shots,"hits":model.hits,"visible_targets":targets}
		if lifecycle == "opening":state["opening_seconds"] = opening.video.stream_position
		return state
	if command in ["START","EXIT"]:enqueue_device({"event":command});return {"ok":true}
	if display_setup.visible:
		if command == "SHOT":
			var raw := Vector2(payload.x, payload.y)
			if raw.is_finite() and display_setup.stage >= 0:
				display_setup.sample(raw)
				return {"ok":true, "hit":false, "score":model.resources.get("score", 0)}
		return {"ok":false,"reason":"display_setup"}
	var order = session.queue.next_order
	var accepted: bool
	if command == "SHOT":
		var shot := device_shot(Vector2(payload.get("x", 0), payload.get("y", 0)))
		if shot.is_empty():
			return {"ok": false, "reason": "invalid_coordinates"}
		if shot.event == "SHOT":
			accepted = enqueue_device_shot(shot.point)
		else:
			if not model.available_commands().has("RELOAD"):
				return {"ok": false, "reason": "outside_playfield"}
			accepted = session.enqueue("RELOAD")
	else:
		accepted = session.enqueue(command)
	if not accepted:
		return {"ok": false, "reason": "paused_or_no_submission"}
	completions[order]={"callback":completion,"at":elapsed}
	return {"deferred":true}
func finish_input(order,result):
	if not completions.has(order):return
	var response=result.duplicate(true);response.score=model.resources.get("score",0)
	completions[order].callback.call(response);completions.erase(order)
