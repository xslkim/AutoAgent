extends SceneTree
## Review the cinema boss with either its whitebox or production artwork.

const Shadow = preload("res://core/screen_shadow.gd")
const ORDERS = [[0,1,2], [0,2,1], [1,0,2], [1,2,0], [2,0,1], [2,1,0]]
const CONTENT := Vector2i(1776, 936)
const COOL := Color(44.0 / 255, 36.0 / 255, 84.0 / 255, .44)
const WARM := Color(233.0 / 255, 163.0 / 255, 105.0 / 255, .32)
var model = Shadow.new()
var boss: Dictionary
var art := {}
var beam_textures: Array[Texture2D] = []
var canvas: Node2D
var font := SystemFont.new()
var beam_mix := PackedFloat32Array([0, 0, 0])
const BEAM_SECONDS := .30

func _initialize() -> void:
	call_deferred("run")

func point(values: Array) -> Vector2:
	return Vector2(values[0], values[1])

func rect(values: Array) -> Rect2:
	return Rect2(values[0], values[1], values[2], values[3])

func alpha_image(path: String) -> Image:
	var mask := Image.load_from_file(path)
	if mask == null or mask.is_empty():
		return null
	var image := Image.create(mask.get_width(), mask.get_height(), false, Image.FORMAT_RGBA8)
	for y in mask.get_height():
		for x in mask.get_width():
			image.set_pixel(x, y, Color(1, 1, 1, mask.get_pixel(x, y).r))
	return image

func load_art(pack: Dictionary, folder: String) -> bool:
	boss = pack.layout
	var masks := {}
	for id in pack.assets:
		var image := Image.load_from_file(folder.path_join(pack.assets[id]))
		if image == null or image.is_empty():
			return false
		if id == "projector":
			masks[id] = image
		art[id] = ImageTexture.create_from_image(image)
	for id in pack.hit_masks:
		var image := alpha_image(folder.path_join(pack.hit_masks[id]))
		if image == null:
			return false
		masks[id] = image
	for file in pack.beam_textures:
		var image := Image.load_from_file(folder.path_join(file))
		if image == null or image.get_size() != CONTENT:
			return false
		beam_textures.append(ImageTexture.create_from_image(image))
	return beam_textures.size() == 3 and model.configure(boss, masks)

func probe() -> bool:
	var core := rect(boss.core.rect).get_center()
	var order_count := 0
	for order in ORDERS:
		model.reset()
		if model.shoot(core) != "miss" or model.core_exposed():
			return false
		var cleaned := []
		for index in order:
			var projector: Dictionary = boss.projectors[index]
			var reel_rect := rect(projector.reel.rect)
			var machine := point(projector.lens) if art.is_empty() else rect(projector.art_rect).get_center()
			if model.shoot(machine) != "invalid":
				return false
			if model.shoot(reel_rect.position + Vector2.ONE) != "miss":
				return false
			if model.shoot(reel_rect.get_center()) != "reel":
				return false
			cleaned.append(projector.id)
			if model.shoot(reel_rect.get_center()) != "miss":
				return false
			for item in boss.projectors:
				if model.beam_warm(item.id) != (item.id in cleaned):
					return false
			if model.core_exposed() != (cleaned.size() == 3):
				return false
			if cleaned.size() < 3 and model.shoot(core) != "miss":
				return false
		if model.shoot(core) != "clear" or not model.complete() or model.shoot(core) != "miss":
			return false
		order_count += 1
	print(JSON.stringify({"passed": true, "orders": order_count, "projector_shots_invalid": true,
		"independent_beams": true, "core_requires_all_reels": true, "duplicate_hits_ignored": true,
		"uses_art_masks": not art.is_empty()}))
	return true

func label(at: Vector2, text: String, size: int = 28) -> void:
	canvas.draw_string(font, at, text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, Color("#d9ceda"))

func draw_ellipse(region: Rect2, fill: Color, edge: Color) -> void:
	var points := PackedVector2Array()
	var center := region.get_center()
	for i in 64:
		points.append(center + Vector2.from_angle(i * TAU / 64) * region.size * .5)
	canvas.draw_colored_polygon(points, fill)
	points.append(points[0])
	canvas.draw_polyline(points, edge, 3, true)

func draw_sprite(id: String, region: Rect2) -> void:
	var texture: Texture2D = art[id]
	var size := texture.get_size()
	var fit := minf(region.size.x / size.x, region.size.y / size.y)
	var drawn := (size * fit).round()
	var position := region.position + ((region.size - drawn) * .5).floor()
	canvas.draw_texture_rect(texture, Rect2(position, drawn), false)

func draw_art() -> void:
	var view := Rect2(Vector2.ZERO, Vector2(CONTENT))
	canvas.draw_texture_rect(art.background, view, false)
	draw_sprite("shadow", rect(boss.shadow_rect))
	for i in beam_textures.size():
		canvas.draw_texture_rect(beam_textures[i], view, false, COOL.lerp(WARM, beam_mix[i]))
	canvas.draw_texture_rect(art.fixtures, view, false)
	for projector in boss.projectors:
		canvas.draw_texture_rect(art.projector, rect(projector.art_rect), false)
		var region := rect(projector.reel.rect)
		draw_sprite("clean_reel", region)
		if not model.beam_warm(projector.id):
			draw_sprite("reel_ink", region)
	if model.core_exposed():
		draw_sprite("core", rect(boss.core.rect))

func draw_whitebox() -> void:
	canvas.draw_rect(Rect2(0, 0, 1776, 936), Color("#262238"))
	var screen := rect(boss.screen)
	canvas.draw_rect(screen, Color("#4e4662"))
	canvas.draw_rect(screen, Color("#8b7d99"), false, 3)
	canvas.draw_circle(Vector2(888, 337), 176, Color("#333041"))
	for i in boss.projectors.size():
		var projector: Dictionary = boss.projectors[i]
		var warm: bool = model.beam_warm(projector.id)
		var points := PackedVector2Array([point(projector.lens),
			point(projector.screen_span[0]), point(projector.screen_span[1])])
		var beam_color := Color("#46456b").lerp(Color("#966b4b"), beam_mix[i])
		canvas.draw_colored_polygon(points, beam_color)
		var machine := rect(projector.rect)
		canvas.draw_rect(machine, Color("#3f3d52"))
		canvas.draw_rect(machine, Color("#888398"), false, 3)
		canvas.draw_circle(point(projector.lens), 7, beam_color.lightened(.2))
		label(machine.position + Vector2(12, 92), "放映机 %d" % (i + 1), 24)
		var reel := rect(projector.reel.rect)
		draw_ellipse(reel, Color("#93745e") if warm else Color("#191722"),
			Color("#a68b78") if warm else Color("#bc6f8b"))
	if model.core_exposed():
		var core := rect(boss.core.rect)
		draw_ellipse(core, Color("#a4383c"), Color("#c9706e"))

func draw_stage() -> void:
	if art.is_empty():
		draw_whitebox()
	else:
		draw_art()
	var status := "净化胶片盘墨渍，恢复放映机的光"
	if model.complete():
		status = "银幕影已净化"
	elif model.core_exposed():
		status = "三束光已恢复，银幕影核开放"
	label(Vector2(66, 88), status)

func _process(delta: float) -> bool:
	if canvas:
		for i in boss.projectors.size():
			var target := 1.0 if model.beam_warm(boss.projectors[i].id) else 0.0
			if not is_equal_approx(beam_mix[i], target):
				beam_mix[i] = move_toward(beam_mix[i], target, delta / BEAM_SECONDS)
				canvas.queue_redraw()
	return false

func on_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		model.shoot(event.position)
		canvas.queue_redraw()
	elif event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_R:
			model.reset()
			beam_mix.fill(0)
			canvas.queue_redraw()
		elif event.keycode == KEY_ESCAPE:
			quit()

func capture(folder: String) -> void:
	if DisplayServer.get_name() == "headless" or DirAccess.make_dir_recursive_absolute(folder) != OK:
		quit(2)
		return
	var viewport := SubViewport.new()
	viewport.size = CONTENT
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	viewport.add_child(canvas)
	canvas.draw.connect(draw_art)
	for cleared in [0, 1, 3]:
		for i in cleared:
			var projector: Dictionary = boss.projectors[i]
			if not model.beam_warm(projector.id):
				if model.shoot(rect(projector.reel.rect).get_center()) != "reel":
					quit(1)
					return
				beam_mix[i] = 1
		canvas.queue_redraw()
		await process_frame
		await RenderingServer.frame_post_draw
		var frame := viewport.get_texture().get_image()
		if frame.save_png(folder.path_join("screen_%d.png" % cleared)) != OK:
			quit(1)
			return
	print("Captured three art states")
	quit()

func run() -> void:
	var arguments := OS.get_cmdline_user_args()
	if arguments.is_empty():
		printerr("Usage: screen_shadow_review.gd -- <T12 layouts.json or screen_shadow/art.json> [--probe]")
		quit(2)
		return
	var data = JSON.parse_string(FileAccess.get_file_as_string(arguments[0]))
	var valid := false
	if data is Dictionary:
		if data.has("assets"):
			valid = load_art(data, arguments[0].get_base_dir())
		else:
			for stage in data.get("stations", []):
				if stage.id == "screen_stage":
					boss = stage.boss
					valid = model.configure(boss)
					break
	if not valid:
		printerr("Missing or invalid screen boss geometry")
		quit(2)
		return
	if "--probe" in arguments:
		quit(0 if probe() else 1)
		return
	canvas = Node2D.new()
	for arg in arguments:
		if arg.begins_with("--capture=") and not art.is_empty():
			await capture(arg.trim_prefix("--capture="))
			return
	root.title = "银幕影 · 左键净化，R 重置，Esc 关闭"
	root.content_scale_size = CONTENT
	root.content_scale_mode = Window.CONTENT_SCALE_MODE_CANVAS_ITEMS
	root.content_scale_aspect = Window.CONTENT_SCALE_ASPECT_KEEP
	font.font_names = PackedStringArray(["Microsoft YaHei", "Noto Sans CJK SC"])
	root.add_child(canvas)
	canvas.draw.connect(draw_stage)
	root.window_input.connect(on_input)
	canvas.queue_redraw()
