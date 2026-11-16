extends SceneTree
## Runs a station art pack through the runtime raster painter and hit resolver.

const Painter = preload("res://core/raster_layer.gd")
const Item = preload("res://core/raster_item.gd")
const Resolver = preload("res://core/hit_resolver.gd")
const STATIONS = ["stall", "video_shop", "footbridge", "square"]
const CAMERAS = [Vector2(-60,-30), Vector2(60,-30), Vector2(60,30), Vector2(-60,30)]

var resolver = Resolver.new()
var viewport: SubViewport
var painter: Node2D
var lighting: Node2D
var origin: Vector2
var content: Vector2
var resources: Dictionary

func _initialize() -> void:
	call_deferred("run")

func point(values: Array) -> Vector2:
	return Vector2(values[0], values[1])

func item(path: String, position: Vector2, id: String, kind: String = ""):
	if not resources.has(path):
		var image := Image.load_from_file(path)
		if image.get_format() == Image.FORMAT_L8:
			# A grayscale hit mask is coverage, not an opaque gray surface.
			var rgba := Image.create(image.get_width(), image.get_height(), false, Image.FORMAT_RGBA8)
			for y in image.get_height():
				for x in image.get_width():
					rgba.set_pixel(x,y,Color(1,1,1,image.get_pixel(x,y).r))
			image = rgba
		resources[path] = [image, ImageTexture.create_from_image(image)]
	var result = Item.new()
	result.image = resources[path][0]
	result.texture = resources[path][1]
	result.source = Rect2(Vector2.ZERO, result.image.get_size())
	result.size = Vector2(result.image.get_size())
	result.transform.origin = position
	result.id = id
	result.kind = kind
	return result

func cover_probe(blocker, hits: Array) -> bool:
	var available: Rect2 = blocker.bounds().intersection(Rect2(Vector2(10,10), content - Vector2(20,20)))
	for y in range(ceili(available.position.y), floori(available.end.y), 11):
		for x in range(ceili(available.position.x), floori(available.end.x), 11):
			var test := Vector2(x,y)
			if blocker.sample(test).a < .5:
				continue
			var actor = Item.new()
			actor.image = blocker.image
			actor.size = blocker.size
			actor.source = blocker.source
			actor.transform = blocker.transform
			actor.kind = "primary"
			actor.id = "covered_actor"
			var hidden: Dictionary = resolver.resolve(test, [actor] + hits, 0.0)
			return resolver.resolve(test, [actor], 0.0).id == actor.id and hidden.kind == "blocker"
	return false

func compose(pack: Dictionary, folder: String, shift: Vector2, amount: float) -> Dictionary:
	var visual: Array = []
	var blockers: Array = []
	var anchors: Dictionary = pack.get("anchors", {})
	var anchor_samples := {}
	var lamp_shift := Vector2.ZERO
	for layer in pack.layers:
		var offset := shift * float(layer.parallax)
		var position := point(layer.pos) - origin - offset
		var raster = item(folder.path_join(layer.file), position, layer.id)
		visual.append(raster)
		for id in anchors:
			var anchor: Dictionary = anchors[id]
			if anchor.layer == layer.id:
				var screen_point := point(anchor.point) - offset
				var visible: bool = Rect2(Vector2.ZERO, content).has_point(screen_point) and raster.sample(screen_point).a >= .5
				anchor_samples[id] = {"position": [screen_point.x, screen_point.y], "visible": visible}
		if layer.has("block_mask"):
			blockers.append(item(folder.path_join(layer.block_mask), position, layer.id, "blocker"))
		if layer.id == "lamp":
			lamp_shift = offset
	var hits: Array = blockers.duplicate()
	var light: Dictionary = pack.lights[0] if not pack.lights.is_empty() else {}
	var aim := Vector2.ZERO
	var lamp_hit := false
	var lamp_shape := false
	if not light.is_empty():
		var lamp = item(folder.path_join(light.hit_mask), point(light.hit_pos) - origin - lamp_shift, "lamp", "primary")
		hits.push_front(lamp)
		aim = point(light.aim) - origin - lamp_shift
		lamp_hit = resolver.resolve(aim, hits, 0.0).id == "lamp"
		for corner in [Vector2(.5,.5), Vector2(lamp.size.x-.5,.5),
				Vector2(.5,lamp.size.y-.5), lamp.size-Vector2(.5,.5)]:
			var probe: Vector2 = lamp.transform * corner
			if lamp.sample(probe).a < .5 and resolver.resolve(probe, hits, 0.0).id != "lamp":
				lamp_shape = true
				break
	var blocked := 0
	for blocker in blockers:
		if cover_probe(blocker, hits):
			blocked += 1
	var base_covers: bool = visual[0].bounds().encloses(Rect2(Vector2.ZERO, content))
	if viewport:
		painter.refresh(visual)
		var light_items: Array = []
		if amount > 0 and not light.is_empty():
			for key in ["spill","glow"]:
				var overlay = item(folder.path_join(light[key]), point(light.pos) - origin - lamp_shift, key)
				overlay.tint.a = amount
				light_items.append(overlay)
		lighting.refresh(light_items)
	var result := {"lamp_present": not light.is_empty(), "lamp_hit": lamp_hit, "outside_lamp": lamp_shape, "covers_blocked": blocked,
		"cover_count": blockers.size(), "base_covers": base_covers, "aim": [aim.x, aim.y]}
	if pack.has("anchors"):
		result["anchors"] = anchor_samples
	return result

func capture(path: String) -> bool:
	await process_frame
	await RenderingServer.frame_post_draw
	return viewport.get_texture().get_image().save_png(path) == OK

func run() -> void:
	var arguments := OS.get_cmdline_user_args()
	if arguments.size() < 2:
		printerr("usage: station_parallax_probe.gd -- <parallax packs> <output> [station ids...]")
		quit(2)
		return
	var output := arguments[1]
	if DirAccess.make_dir_recursive_absolute(output) != OK:
		quit(2)
		return
	if DisplayServer.get_name() != "headless":
		viewport = SubViewport.new()
		viewport.transparent_bg = true
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		root.add_child(viewport)
		painter = Painter.new()
		viewport.add_child(painter)
		lighting = Painter.new()
		var material := CanvasItemMaterial.new()
		material.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
		lighting.material = material
		viewport.add_child(lighting)
	var results := {}
	var passed := true
	var stations := PackedStringArray(STATIONS) if arguments.size() == 2 else arguments.slice(2)
	for stage in stations:
		resources = {}
		var folder := arguments[0].path_join(stage)
		var decoded = JSON.parse_string(FileAccess.get_file_as_string(folder.path_join("station.json")))
		if not decoded is Dictionary:
			printerr("Invalid station pack: " + folder)
			quit(2)
			return
		var pack: Dictionary = decoded
		origin = point(pack.content_origin)
		content = point(pack.content_size)
		if viewport:
			viewport.size = Vector2i(content)
		var samples := {}
		samples.rest = compose(pack, folder, Vector2.ZERO, 0)
		if viewport:
			passed = await capture(output.path_join(stage + "_rest.png")) and passed
			if samples.rest.lamp_present:
				compose(pack, folder, Vector2.ZERO, 1)
				passed = await capture(output.path_join(stage + "_lit.png")) and passed
		for index in CAMERAS.size():
			var camera: Vector2 = CAMERAS[index]
			var breath := camera.sign() * Vector2(8,4)
			var id := "corner_%d" % index
			samples[id] = compose(pack, folder, camera + breath, 1)
			if viewport:
				passed = await capture(output.path_join(stage + "_" + id + ".png")) and passed
			samples[id + "_against"] = compose(pack, folder, camera - breath, 1)
			if viewport:
				passed = await capture(output.path_join(stage + "_" + id + "_against.png")) and passed
		for sample in samples.values():
			var lamp_ok: bool = not sample.lamp_present or (sample.lamp_hit and sample.outside_lamp)
			passed = passed and lamp_ok and sample.base_covers and sample.covers_blocked == sample.cover_count
			if pack.has("anchors"):
				passed = passed and sample.anchors.size() == pack.anchors.size()
				for anchor in sample.anchors.values():
					passed = passed and anchor.visible
		results[stage] = samples
	var evidence := {"passed": passed, "godot": Engine.get_version_info().string,
		"gpu_capture": viewport != null, "samples": results}
	var file := FileAccess.open(output.path_join("engine_checks.json"), FileAccess.WRITE)
	if file == null:
		quit(2)
		return
	file.store_string(JSON.stringify(evidence, "  ") + "\n")
	file.close()
	print(JSON.stringify({"passed": passed, "stations": results.size(), "gpu_capture": viewport != null}))
	quit(0 if passed else 1)
