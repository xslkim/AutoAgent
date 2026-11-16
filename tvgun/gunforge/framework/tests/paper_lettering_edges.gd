extends SceneTree
## Read the actual HUD shader output for all four pieces of lettering.

const Loader = preload("res://core/level_loader.gd")
const Hud = preload("res://core/paper_hud.gd")

func _initialize() -> void:
	run.call_deferred()

func run() -> void:
	var args := {}
	for argument in OS.get_cmdline_user_args():
		var pair := argument.split("=", true, 1)
		if pair.size() == 2:
			args[pair[0]] = pair[1]
	var out: String = args.get("--captures", "")
	if DisplayServer.get_name() == "headless" or out.is_empty() or DirAccess.make_dir_recursive_absolute(out) != OK:
		push_error("Lettering needs a graphics viewport and capture directory")
		quit(2)
		return
	var compiled = JSON.parse_string(FileAccess.get_file_as_string(args.get("--build", "")))
	var model = Loader.open(compiled, args.get("--assets", ""))
	if model == null:
		quit(2)
		return
	var viewport := SubViewport.new()
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var background := ColorRect.new()
	viewport.add_child(background)
	var surface := Node2D.new()
	viewport.add_child(surface)
	var hud := Hud.new()
	var binding: Dictionary = model.level.presentation.hud_art
	hud.setup(model, binding, surface)
	var names: Dictionary = binding.lettering
	var textures: Dictionary = {names.title: hud.lettering.title, names.first_chapter: hud.lettering.first_chapter}
	for section in names.chapters:
		textures[names.chapters[section]] = hud.lettering.chapters[section]
	var sprite := hud.title_sprite
	sprite.centered = false
	sprite.position = Vector2(8, 8)
	sprite.show()
	var sizes := {}
	for identifier in textures:
		sprite.texture = textures[identifier]
		viewport.size = Vector2i(sprite.texture.get_size()) + Vector2i(16, 16)
		background.size = Vector2(viewport.size)
		sizes[identifier] = [viewport.size.x, viewport.size.y]
		for tone in ["black", "white"]:
			background.color = Color.BLACK if tone == "black" else Color.WHITE
			await process_frame
			await RenderingServer.frame_post_draw
			if viewport.get_texture().get_image().save_png(out.path_join(identifier + "-" + tone + ".png")) != OK:
				push_error("Could not save lettering composite: " + identifier)
				quit(2)
				return
	var receipt := FileAccess.open(out.path_join("captures.json"), FileAccess.WRITE)
	if receipt == null:
		quit(2)
		return
	receipt.store_string(JSON.stringify({"build_id": model.build.build_id, "sizes": sizes}) + "\n")
	receipt.close()
	quit()
