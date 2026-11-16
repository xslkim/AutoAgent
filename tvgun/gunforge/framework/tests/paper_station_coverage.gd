extends SceneTree
## Check station raster opacity in a transparent Godot viewport, with no clear color to hide holes.

const Loader = preload("res://core/level_loader.gd")
const RasterLayer = preload("res://core/raster_layer.gd")
const RasterItem = preload("res://core/raster_item.gd")
const Session = preload("res://core/level_session.gd")
const SIZE := Vector2i(1776, 936)

var model
var session = Session.new()
var plate_view: SubViewport
var full_view: SubViewport
var plate
var textures := {}
var diagnostics := {}
var output := ""

func _initialize() -> void:
	run.call_deferred()

func make_viewport() -> SubViewport:
	var view := SubViewport.new()
	view.size = SIZE
	view.transparent_bg = true
	view.render_target_update_mode = SubViewport.UPDATE_DISABLED
	root.add_child(view)
	return view

func inspect(image: Image, key: String) -> Dictionary:
	if image.detect_alpha() == Image.ALPHA_NONE:
		return {"opaque": true, "missing_pixels": 0}
	var result := {"opaque": false}
	if diagnostics.has(key):
		return result
	var raw := image.get_data()
	var low := SIZE
	var high := Vector2i.ZERO
	var count := 0
	for index in range(3, raw.size(), 4):
		if raw[index] == 255:
			continue
		var point := Vector2i((index >> 2) % SIZE.x, int((index >> 2) / SIZE.x))
		low = low.min(point)
		high = high.max(point)
		count += 1
	var filename := key.replace(":", "_").replace("/", "_") + ".png"
	var saved := image.save_png(output.path_join(filename)) == OK
	result.merge({"missing_pixels": count, "missing_bounds_xyxy": [low.x, low.y, high.x + 1, high.y + 1],
		"image": filename if saved else ""})
	diagnostics[key] = result
	return result

func draw_plate() -> Array:
	var items: Array = model.layer_items()
	var identifiers := []
	for item in items:
		var id: int = item.image.get_instance_id()
		if not textures.has(id):
			textures[id] = ImageTexture.create_from_image(item.image)
		item.texture = textures[id]
		identifiers.append(item.id)
	plate.refresh(model.ordered(items))
	return identifiers

func rendered(include_full := false) -> Dictionary:
	var ids := draw_plate()
	plate_view.render_target_update_mode = SubViewport.UPDATE_ONCE
	if include_full:
		full_view.render_target_update_mode = SubViewport.UPDATE_ONCE
	await process_frame
	await RenderingServer.frame_post_draw
	var result := {"section": model.current_section, "tick": model.tick,
		"station": int(model.level.sections.get(model.current_section, {}).get("station", 0)),
		"shift": [model.camera_shift().x, model.camera_shift().y], "layers": ids,
		"plate": inspect(plate_view.get_texture().get_image(), "plate:" + model.current_section)}
	if include_full:
		result["scene"] = inspect(full_view.get_texture().get_image(), "scene:" + model.current_section)
	return result

func check_controls() -> Dictionary:
	var sample := Image.create_empty(SIZE.x, SIZE.y, false, Image.FORMAT_RGBA8)
	sample.fill(Color("#1b223a"))
	var item := RasterItem.new()
	item.size = Vector2(SIZE)
	item.source = Rect2(Vector2.ZERO, item.size)
	item.texture = ImageTexture.create_from_image(sample)
	plate.refresh([item])
	plate_view.render_target_update_mode = SubViewport.UPDATE_ONCE
	await process_frame
	await RenderingServer.frame_post_draw
	var positive := inspect(plate_view.get_texture().get_image(), "control_opaque")
	sample.fill_rect(Rect2i(71, 93, 16, 9), Color.TRANSPARENT)
	item.texture.update(sample)
	plate.refresh([item])
	plate_view.render_target_update_mode = SubViewport.UPDATE_ONCE
	await process_frame
	await RenderingServer.frame_post_draw
	var negative := inspect(plate_view.get_texture().get_image(), "control_hole")
	return {"opaque_control": positive, "hole_control": negative,
		"passed": positive.opaque and not negative.opaque and negative.get("missing_pixels") == 144
			and negative.get("missing_bounds_xyxy") == [71, 93, 87, 102]}

func stress() -> Array:
	var amplitude: Vector2 = model.camera_amplitude
	var shifts := [Vector2.ZERO, Vector2(-amplitude.x, -amplitude.y), Vector2(amplitude.x, -amplitude.y),
		Vector2(-amplitude.x, amplitude.y), amplitude]
	var rows := []
	var tick: int = model.tick
	var section: String = model.current_section
	model.tick = int(model.level.tick_hz)
	for name in model.level.sections:
		model.current_section = name
		for shift in shifts:
			model.camera_amplitude = Vector2(shift.x / sin(.85), shift.y / sin(1.1))
			rows.append(await rendered())
	model.camera_amplitude = amplitude
	model.tick = tick
	model.current_section = section
	return rows

func replay(record: Dictionary) -> Array:
	session.setup(model)
	session.load_recording(record)
	var intervals := []
	var start := 0
	var section: String = model.current_section
	while model.tick < int(record.end_tick):
		session.step()
		if model.phase != "running" and model.tick < int(record.end_tick):
			push_error("Campaign recording ended before the expected tick")
			return []
		if model.current_section != section:
			intervals.append({"start": start, "end": model.tick - 1, "section": section})
			start = model.tick
			section = model.current_section
	intervals.append({"start": start, "end": model.tick, "section": section})
	var pullback_id := "lantern_base.pullback.interior"
	var pullback_at := -1
	var pullback_samples := {}
	for span in intervals:
		if span.section == "lantern_base.pullback":
			pullback_at = span.start
			break
	if pullback_at >= 0:
		for entity_id in [pullback_id, "lantern_base.pullback.exterior"]:
			for frame in model.level.entities[entity_id].motion.frames:
				var offset := ceili(float(frame.at_ms) * model.level.tick_hz / 1000.0)
				for adjacent in [-1, 0, 1]:
					pullback_samples[pullback_at + offset + adjacent] = true
	var rows := []
	for span in intervals:
		var targets := {}
		for quarter in range(5):
			targets[roundi(lerpf(span.start, span.end, quarter / 4.0))] = true
		for at in range(span.start, span.end + 1, int(model.level.tick_hz)):
			targets[at] = true
		if span.section in ["lantern_base.ending_city", "lantern_base.ending_wide"]:
			var fade_ticks := 72 if span.section == "lantern_base.ending_city" else 108
			for quarter in range(5):
				targets[span.start + roundi(fade_ticks * quarter / 4.0)] = true
		for at in pullback_samples:
			if at >= span.start and at <= span.end:
				targets[at] = true
		var ordered: Array = targets.keys()
		ordered.sort()
		for at in ordered:
			session.seek(int(at))
			rows.append(await rendered(true))
	return rows

func run() -> void:
	var args := {}
	for arg in OS.get_cmdline_user_args():
		var pair := arg.split("=", true, 1)
		if pair.size() == 2:
			args[pair[0]] = pair[1]
	output = args.get("--output", "")
	var compiled = JSON.parse_string(FileAccess.get_file_as_string(args.get("--build", "")))
	model = Loader.open(compiled, args.get("--assets", ""))
	if model == null or DisplayServer.get_name() == "headless" or output.is_empty() \
		or DirAccess.make_dir_recursive_absolute(output) != OK:
		push_error("Expected a GPU viewport, verified campaign and output directory")
		quit(2)
		return
	plate_view = make_viewport()
	plate = RasterLayer.new()
	plate_view.add_child(plate)
	var controls := await check_controls()
	if not controls.passed:
		push_error("The opaque and deliberate-hole controls did not reproduce")
		quit(2)
		return
	var replay_rows := []
	if args.has("--recording"):
		var file := FileAccess.open(args["--recording"], FileAccess.READ)
		var fixture = file.get_var() if file != null else null
		if not fixture is Dictionary or fixture.recording.build_id != model.build.build_id:
			push_error("Expected a campaign recording for the selected build")
			quit(2)
			return
		full_view = make_viewport()
		model.mount(full_view)
		replay_rows = await replay(fixture.recording)
		var stations := {}
		for row in replay_rows:
			if row.station > 0:
				stations[row.station] = true
		if stations.size() != 15 or model.result != "clear":
			push_error("Expected the full 15-station campaign replay and clear result")
			quit(2)
			return
		model.render_scene.process_mode = Node.PROCESS_MODE_DISABLED
	var extremes := await stress()
	var extreme_failures := extremes.filter(func(row): return not row.plate.opaque).size()
	var replay_failures := replay_rows.filter(func(row): return not row.plate.opaque or not row.scene.opaque).size()
	var report := FileAccess.open(output.path_join("checks.json"), FileAccess.WRITE)
	if report == null:
		quit(2)
		return
	var totals := {"build_id": model.build.build_id, "camera_samples": extremes.size(), "camera_failures": extreme_failures,
		"replay_samples": replay_rows.size(), "replay_failures": replay_failures}
	report.store_string(JSON.stringify({"totals": totals, "controls": controls, "extremes": extremes, "replay": replay_rows,
		"gpu": RenderingServer.get_video_adapter_name(), "viewport": [SIZE.x, SIZE.y], "diagnostics": diagnostics}, "\t"))
	print(JSON.stringify(totals))
	quit(1 if extreme_failures + replay_failures > 0 else 0)
