extends SceneTree
## Exercise the actual raster draw call and shot resolver against filled alpha edges.

const Loader = preload("res://core/level_loader.gd")
const Layer = preload("res://core/raster_layer.gd")
const Item = preload("res://core/raster_item.gd")
const SCALES := [0.625, 1.25]

func _initialize() -> void:
	run.call_deferred()

func sample_shots(model) -> Dictionary:
	model.start()
	while not model.input_enabled and model.tick < 600:
		model.step()
	if not model.input_enabled:
		return {}
	var pose: Array = model.geometry()
	var state: Dictionary = model.save_state()
	var output := {}
	for side in ["left", "right"]:
		var id: String = "layer." + model.current_section + ".near_" + side
		var layers: Array = pose.filter(func(item): return item.id == id and item.kind == "blocker")
		if layers.size() != 1:
			return {}
		var layer = layers[0]
		var bounds: Rect2 = layer.bounds().intersection(Rect2(0, 0, model.level.layout.width, model.level.layout.height))
		var points := {}
		for y in range(ceili(bounds.position.y) + 3, floori(bounds.end.y), 11):
			for x in range(ceili(bounds.position.x) + 3, floori(bounds.end.x), 11):
				var point := Vector2(x + .5, y + .5)
				var hit: Dictionary = model.resolver.exact(point, pose)
				if hit.get("id", "") == id and layer.sample(point).a >= .75 and not points.has("blocker"):
					points["blocker"] = point
				if hit.is_empty() and layer.sample(point).a < .25 and not points.has("miss"):
					points["miss"] = point
				if points.size() == 2:
					break
			if points.size() == 2:
				break
		if points.size() != 2:
			return {}
		var checks := {}
		for kind in ["blocker", "miss"]:
			model.restore_state(state)
			var point: Vector2 = points[kind]
			var result: Dictionary = model.command("SHOT", point, pose)
			if result.get("kind") != kind or not result.get("ok", false) or result.get("hit", true) \
				or model.resources.ammo != state.public.resources.ammo - 1 or model.hits != 0:
				return {}
			checks[kind] = {"point": [point.x, point.y], "alpha": layer.sample(point).a, "result": result}
		output[side] = checks
	return output

func run() -> void:
	var args := {}
	for argument in OS.get_cmdline_user_args():
		var pair := argument.split("=", true, 1)
		if pair.size() == 2:
			args[pair[0]] = pair[1]
	var out: String = args.get("--captures", "")
	if DisplayServer.get_name() == "headless" or out.is_empty() or DirAccess.make_dir_recursive_absolute(out) != OK:
		push_error("A graphics viewport and capture directory are required")
		quit(2)
		return
	var compiled = JSON.parse_string(FileAccess.get_file_as_string(args.get("--build", "")))
	var model = Loader.open(compiled, args.get("--assets", ""))
	var probes = JSON.parse_string(FileAccess.get_file_as_string(args.get("--probes", "")))
	if model == null or not probes is Array or probes.is_empty():
		quit(2)
		return
	var blockers := sample_shots(model)
	if blockers.size() != 2:
		push_error("Expected blocker and miss on both sides of the alley")
		quit(1)
		return

	var viewport := SubViewport.new()
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var background := ColorRect.new()
	background.color = Color("#c3b4a1")
	viewport.add_child(background)
	var raster := Layer.new()
	raster.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	viewport.add_child(raster)
	var captures := {}
	for probe in probes:
		var source: Image = model.images[probe.id]
		var box: Array = probe.rect
		var rect := Rect2(box[0], box[1], box[2], box[3])
		if not Rect2(Vector2.ZERO, source.get_size()).encloses(rect):
			push_error("Probe region outside raster: " + probe.id)
			quit(2)
			return
		var texture := ImageTexture.create_from_image(source)
		for index in SCALES.size():
			var factor: float = SCALES[index]
			var item := Item.new()
			item.texture = texture
			item.source = rect
			item.size = rect.size * factor
			item.transform.origin = Vector2(8.25, 8.625)
			viewport.size = Vector2i(ceili(item.size.x) + 18, ceili(item.size.y) + 18)
			background.size = Vector2(viewport.size)
			raster.refresh([item])
			await process_frame
			await RenderingServer.frame_post_draw
			var name: String = "%s-%d.png" % [probe.id, index]
			if viewport.get_texture().get_image().save_png(out.path_join(name)) != OK:
				push_error("Could not save raster comparison: " + name)
				quit(2)
				return
			captures[name] = {"id": probe.id, "scale": factor, "rect": box,
				"size": [viewport.size.x, viewport.size.y]}
	var receipt := FileAccess.open(out.path_join("checks.json"), FileAccess.WRITE)
	if receipt == null:
		quit(2)
		return
	receipt.store_string(JSON.stringify({"build_id": model.build.build_id, "blockers": blockers, "captures": captures}) + "\n")
	receipt.close()
	quit()
