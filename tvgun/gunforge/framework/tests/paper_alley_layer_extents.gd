extends SceneTree
## Capture each compiled alley layer independently on a transparent viewport.

const Loader = preload("res://core/level_loader.gd")
const RasterLayer = preload("res://core/raster_layer.gd")

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	var args := {}
	for arg in OS.get_cmdline_user_args():
		var pair := arg.split("=", true, 1)
		if pair.size() == 2:
			args[pair[0]] = pair[1]
	var build: String = args.get("--build", "")
	var output: String = args.get("--output", "")
	var compiled = JSON.parse_string(FileAccess.get_file_as_string(build))
	var model = Loader.open(compiled, args.get("--assets", ""))
	if model == null or DisplayServer.get_name() == "headless" or output.is_empty() \
		or DirAccess.make_dir_recursive_absolute(output) != OK:
		push_error("Expected a rendered viewport, compiled campaign and output directory")
		quit(2)
		return
	var view := SubViewport.new()
	view.size = Vector2i(model.level.layout.width, model.level.layout.height)
	view.transparent_bg = true
	view.disable_3d = true
	view.render_target_update_mode = SubViewport.UPDATE_DISABLED
	root.add_child(view)
	var plate := RasterLayer.new()
	view.add_child(plate)
	model.current_section = "alley.arrival"
	var rows := []
	var items: Array = model.ordered(model.layer_items())
	items.reverse()
	for item in items:
		item.texture = ImageTexture.create_from_image(item.image)
		plate.refresh([item])
		view.render_target_update_mode = SubViewport.UPDATE_ONCE
		await process_frame
		await RenderingServer.frame_post_draw
		var filename: String = item.id.get_file() + ".png"
		var path := output.path_join(filename)
		if view.get_texture().get_image().save_png(path) != OK:
			push_error("Could not save " + path)
			quit(2)
			return
		rows.append({"id": item.id, "file": filename, "sha256": FileAccess.get_sha256(path)})
	var report := FileAccess.open(output.path_join("captures.json"), FileAccess.WRITE)
	if report == null:
		quit(2)
		return
	report.store_string(JSON.stringify({"build_id": model.build.build_id, "compiled_sha256": FileAccess.get_sha256(build),
		"godot": Engine.get_version_info().string, "gpu": RenderingServer.get_video_adapter_name(), "layers": rows}, "\t"))
	quit()
