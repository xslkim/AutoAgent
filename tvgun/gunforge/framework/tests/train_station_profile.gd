extends "train_station_tests.gd"
## Measure the same recorded route, drawing once for every fixed simulation tick.

var profile_path := ""

func texture_costs() -> Dictionary:
	var presentation: Dictionary = model.level.presentation
	var stage_resources := {}
	for layer in presentation.layers.values():
		stage_resources[layer.resource] = true
	var wipes: Dictionary = presentation.bottom_wipes
	for id in model.level.entities:
		var entity: Dictionary = model.level.entities[id]
		if entity.template == "activation_source" or wipes.has(id) or id in wipes.values() or id.begins_with("lantern_base.pullback."):
			stage_resources[entity.resource] = true
	var costs := {}
	for resource in model.images:
		var raster: Image = model.images[resource]
		var size := raster.get_size()
		var bytes := 0
		while true:
			bytes += size.x * size.y * 4
			if not raster.has_mipmaps() or size == Vector2i.ONE:
				break
			size = Vector2i(maxi(size.x / 2, 1), maxi(size.y / 2, 1))
		costs[raster.get_instance_id()] = Vector2i(bytes, 0) if stage_resources.has(resource) else Vector2i(0, bytes)
	return costs

func replay_recording(record: Dictionary) -> void:
	session.load_recording(record)
	var scene = model.render_scene
	scene.measure_uploads = true
	var costs := texture_costs()
	root.size = Vector2i(1280, 720)
	var preview := TextureRect.new()
	preview.texture = viewport.get_texture()
	preview.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	preview.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	preview.size = Vector2(root.size)
	root.add_child(preview)
	await process_frame
	await RenderingServer.frame_post_draw
	var previous := Time.get_ticks_usec()
	var samples: Array[Dictionary] = []
	var activations: Array[Dictionary] = []
	var glow_ids: Array = model.level.presentation.bottom_wipes.values()
	while model.tick < record.end_tick and model.phase == "running":
		var section: String = model.current_section
		var trace_start: int = model.trace.size()
		session.step()
		var changed: bool = section != model.current_section
		var cold := uncached_scene_textures() if changed else 0
		var lit: Array[String] = []
		for index in range(trace_start, model.trace.size()):
			var entry: Dictionary = model.trace[index]
			if entry.topic == "entity.spawned" and entry.entity in glow_ids:
				var glow: Image = model.images[model.level.entities[entry.entity].resource]
				check(scene.textures.has(glow.get_instance_id()), "light is resident before activation: " + entry.entity)
				lit.append(entry.entity)
		await process_frame
		await RenderingServer.frame_post_draw
		var current := Time.get_ticks_usec()
		if not lit.is_empty():
			check(scene.upload_count == 0, "activating a light performs no texture uploads: " + model.current_section)
			activations.append({"tick": model.tick, "section": model.current_section, "glows": lit,
				"frame_us": current - previous, "upload_count": scene.upload_count})
		var resident := Vector2i.ZERO
		for id in scene.textures:
			resident += costs[id]
		var upcoming := Vector2i.ZERO
		for id in scene.preloaded_textures:
			if not scene.textures.has(id):
				upcoming += costs[id]
		samples.append({"tick": model.tick, "section": model.current_section, "cut": changed,
			"frame_us": current - previous, "stage_bytes": resident.x, "actor_prop_bytes": resident.y,
			"preloaded_stage_bytes": upcoming.x, "preloaded_actor_prop_bytes": upcoming.y,
			"engine_texture_bytes": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED),
			"engine_video_bytes": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED),
			"upload_count": scene.upload_count, "upload_us": scene.upload_us, "uncached_scene_textures": cold})
		previous = current
	check(activations.size() == 4, "recording exercises one light in each combat station")
	var output := FileAccess.open(profile_path, FileAccess.WRITE)
	check(output != null, "write texture and frame timing profile")
	if output != null:
		output.store_string(JSON.stringify({"build_id": model.build.build_id, "gpu": RenderingServer.get_video_adapter_name(),
			"rendering_method": RenderingServer.get_current_rendering_method(),
			"viewport": [viewport.size.x, viewport.size.y], "window": [root.size.x, root.size.y],
			"light_activations": activations, "samples": samples}) + "\n")

func run() -> void:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--profile="):
			profile_path = argument.trim_prefix("--profile=")
	var has_captures := Array(OS.get_cmdline_user_args()).any(func(arg): return arg.begins_with("--captures=") and arg.length() > 11)
	if profile_path.is_empty() or not has_captures or DisplayServer.get_name() == "headless":
		printerr("Train station profiling needs a graphics display, --captures and --profile.")
		quit(2)
		return
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	await super.run()
