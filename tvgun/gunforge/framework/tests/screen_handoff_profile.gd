extends SceneTree
## Measure a fixed-tick campaign frame in the actual Compatibility renderer.

const Loader = preload("res://core/level_loader.gd")

class MeasuredSession extends "res://core/level_session.gd":
	var checkpoint_us := 0

	func cache_checkpoint():
		var began := Time.get_ticks_usec()
		super.cache_checkpoint()
		checkpoint_us = Time.get_ticks_usec() - began

class MeasuredScene extends "res://core/art_level_scene.gd":
	var scene_process_us := 0
	var raster_update_us := 0
	var canvas_commands_us := 0
	var hud_us := 0

	func _process(delta):
		var began := Time.get_ticks_usec()
		super._process(delta)
		scene_process_us = Time.get_ticks_usec() - began

	func update_rasters():
		var began := Time.get_ticks_usec()
		super.update_rasters()
		raster_update_us = Time.get_ticks_usec() - began

	func _draw():
		var began := Time.get_ticks_usec()
		super._draw()
		canvas_commands_us = Time.get_ticks_usec() - began

	func draw_hud():
		var began := Time.get_ticks_usec()
		super.draw_hud()
		hud_us = Time.get_ticks_usec() - began

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	var args := {}
	for argument in OS.get_cmdline_user_args():
		var pair := argument.split("=", true, 1)
		if pair.size() == 2:
			args[pair[0]] = pair[1]
	var build = JSON.parse_string(FileAccess.get_file_as_string(args.get("--build", "")))
	var model = Loader.open(build, args.get("--assets", ""))
	var file := FileAccess.open(args.get("--recording", ""), FileAccess.READ)
	var fixture = file.get_var() if file != null else null
	var interval := int(args.get("--checkpoint-interval", 60))
	var output: String = args.get("--output", "")
	if DisplayServer.get_name() == "headless" or model == null or not fixture is Dictionary \
		or fixture.recording.build_id != model.build.build_id or interval <= 0 or output.is_empty():
		push_error("Expected a GPU viewport, a matching campaign recording and an output path")
		quit(2)
		return
	var target_tick := int(args.get("--tick", 0))
	var target_section: String = args.get("--section", "cinema.screen_stage")
	var expect_cut := target_tick == 0
	if expect_cut:
		var handoffs: Array = fixture.handoffs.filter(func(row): return row.station == "screen_stage")
		if handoffs.size() == 1:
			target_tick = int(handoffs[0].tick)
	if target_tick < 180 or target_tick + 24 > int(fixture.recording.end_tick):
		push_error("Expected a target tick with a complete capture window")
		quit(2)
		return
	var session := MeasuredSession.new()
	session.checkpoint_interval = interval
	session.setup(model)
	session.load_recording(fixture.recording)
	session.seek(target_tick - 180)
	var viewport := SubViewport.new()
	viewport.size = Vector2i(model.level.layout.width, model.level.layout.height)
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var scene := MeasuredScene.new()
	scene.model = model
	scene.measure_uploads = true
	model.render_scene = scene
	viewport.add_child(scene)
	root.size = Vector2i(1280, 720)
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	var preview := TextureRect.new()
	preview.texture = viewport.get_texture()
	preview.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	preview.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	preview.size = Vector2(root.size)
	root.add_child(preview)
	await process_frame
	await RenderingServer.frame_post_draw
	var previous := Time.get_ticks_usec()
	var rows := []
	while model.tick < target_tick + 24:
		session.checkpoint_us = 0
		var began := Time.get_ticks_usec()
		session.step()
		var stepped := Time.get_ticks_usec()
		await process_frame
		var processing := Time.get_ticks_usec()
		await RenderingServer.frame_pre_draw
		var rendering := Time.get_ticks_usec()
		await RenderingServer.frame_post_draw
		var done := Time.get_ticks_usec()
		rows.append({"tick": model.tick, "section": model.current_section, "wall_us": done - previous,
			"harness_us": began - previous, "simulation_us": stepped - began - session.checkpoint_us,
			"checkpoint_us": session.checkpoint_us, "frame_wait_us": processing - stepped,
			"process_to_draw_us": rendering - processing, "draw_wall_us": done - rendering,
			"scene_process_us": scene.scene_process_us, "raster_update_us": scene.raster_update_us,
			"canvas_commands_us": scene.canvas_commands_us, "hud_us": scene.hud_us,
			"texture_upload_count": scene.upload_count, "texture_upload_us": scene.upload_us,
			"draw_calls": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
			"preloaded_section": scene.preloaded_section, "cached_textures": scene.textures.size(),
			"preloaded_caption_count": scene.get("preloaded_caption_count"), "trace_entries": model.trace.size()})
		previous = done
	if rows[179].tick != target_tick or rows[179].section != target_section \
		or (expect_cut and rows[178].section == target_section):
		push_error("Capture did not reproduce the requested frame")
		quit(1)
		return
	if args.get("--expect-deferred", "") == "true" and (rows[178].preloaded_caption_count != 2 \
		or rows[179].checkpoint_us != 0 or rows[180].checkpoint_us <= 0):
		push_error("Expected two warmed captions and the checkpoint on the tick after the cut")
		quit(1)
		return
	var report := FileAccess.open(output, FileAccess.WRITE)
	if report == null:
		quit(2)
		return
	var evidence := {"build_id": model.build.build_id, "checkpoint_interval": interval,
		"gpu": RenderingServer.get_video_adapter_name(), "renderer": RenderingServer.get_current_rendering_method(),
		"cut_tick": target_tick, "cut_frame": rows[179], "samples": rows}
	report.store_string(JSON.stringify(evidence) + "\n")
	report.close()
	print(JSON.stringify(rows[179]))
	quit()
