extends SceneTree
## Drive a train-station candidate with the same pose snapshots submitted by the player.

const Loader = preload("res://core/level_loader.gd")
const Codec = preload("res://core/pose_codec.gd")

var model
var failures: Array[String] = []
var viewport: SubViewport
var captures := ""

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, label: String) -> void:
	if not value:
		failures.append(label)

func step_to(target: int) -> void:
	while model.tick < target and model.phase == "running":
		model.step()

func target_point(target: String, pose: Array) -> Variant:
	for item in pose:
		if item.id != target:
			continue
		var area: Rect2 = item.bounds().intersection(Rect2(0, 0, 1776, 936))
		if model.resolver.exact(area.get_center(), pose).get("id") == target:
			return area.get_center()
		for y in range(ceili(area.position.y), floori(area.end.y), 4):
			for x in range(ceili(area.position.x), floori(area.end.x), 4):
				var point := Vector2(x, y)
				if model.resolver.exact(point, pose).get("id") == target:
					return point
	return null

func shoot(target: String) -> Dictionary:
	step_to(model.next_shot)
	var assets: Dictionary = model.geometry_assets()
	var pose := Codec.decode(Codec.encode(model.geometry(), assets), assets)
	var point = target_point(target, pose)
	if point == null:
		failures.append("cannot aim at " + target)
		return {}
	var result: Dictionary = model.command("SHOT", point, pose)
	model.step()
	return result

func capture(name: String) -> void:
	if viewport == null:
		return
	await process_frame
	await RenderingServer.frame_post_draw
	check(viewport.get_texture().get_image().save_png(captures.path_join(name + ".png")) == OK, "capture " + name)

func uncached_scene_textures() -> int:
	var scene = model.render_scene
	var missing := {}
	for item in model.visual_items():
		var id: int = item.image.get_instance_id()
		if not scene.textures.has(id) and not (scene.preloaded_section == model.current_section and scene.preloaded_textures.has(id)):
			missing[id] = true
	return missing.size()

func open_candidate() -> bool:
	var args := {}
	for argument in OS.get_cmdline_user_args():
		var pair := argument.split("=", true, 1)
		if pair.size() == 2:
			args[pair[0]] = pair[1]
	var compiled = JSON.parse_string(FileAccess.get_file_as_string(args.get("--build", "")))
	model = Loader.open(compiled, args.get("--assets", ""))
	if model == null:
		return false
	captures = args.get("--captures", "")
	if not captures.is_empty() and DisplayServer.get_name() != "headless":
		if DirAccess.make_dir_recursive_absolute(captures) != OK:
			return false
		viewport = SubViewport.new()
		viewport.size = Vector2i(1776, 936)
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		root.add_child(viewport)
		model.mount(viewport)
	model.start()
	return true
