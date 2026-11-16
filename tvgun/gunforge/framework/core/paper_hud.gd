extends RefCounted
## Paint the paper interface over the scene without adding hit geometry.

var model
var textures: Dictionary = {}
var elements: Dictionary = {}
var panel := StyleBoxTexture.new()
var action_style := StyleBoxTexture.new()
var action_hovered := false
var action_pressed := false
var crosshair: Dictionary
var aim := Vector2.INF
var tracking_lost := false
var lettering: Dictionary = {}
var title_sprite: Sprite2D
var chapter_sprite: Sprite2D
var lettering_key := ""
const TITLE_BOUNDS := Vector2(625, 210)
const FIRST_CHAPTER_BOUNDS := Vector2(212, 96)
const CHAPTER_BOUNDS := Vector2(536, 188)
const TRACKING_PROMPT := "请对准屏幕"
const STATION_CAPTION_COUNT := 2

func setup(runtime, binding: Dictionary, surface: Node2D) -> void:
	model = runtime
	var layout: Dictionary = read_metadata(binding.layout)
	var style: Dictionary = read_metadata(binding.style)
	for element in layout.elements:
		elements[element.id] = element
	for key in binding.images:
		textures[key] = ImageTexture.create_from_image(model.images[binding.images[key]])
	panel.texture = textures.continue_panel
	var margins: Array = style.continue_panel.slice_insets_ltrb
	for side in range(4):
		panel.set_texture_margin(side, margins[side])
	var button_art: Image = model.images[binding.images.continue_panel].duplicate()
	button_art.resize(roundi(button_art.get_width() * .25), roundi(button_art.get_height() * .25), Image.INTERPOLATE_LANCZOS)
	action_style.texture = ImageTexture.create_from_image(button_art)
	for side in range(4):
		action_style.set_texture_margin(side, float(margins[side]) / 4)
	crosshair = style.crosshair
	if binding.has("lettering"):
		var art: Dictionary = binding.lettering
		lettering = {"title": lettering_texture(art.title, TITLE_BOUNDS),
			"first_chapter": lettering_texture(art.first_chapter, FIRST_CHAPTER_BOUNDS), "chapters": {}}
		for section in art.chapters:
			lettering.chapters[section] = lettering_texture(art.chapters[section], CHAPTER_BOUNDS)
		var matte := ShaderMaterial.new()
		matte.shader = preload("lettering_matte.gdshader")
		title_sprite = Sprite2D.new()
		chapter_sprite = Sprite2D.new()
		for sprite in [title_sprite, chapter_sprite]:
			sprite.material = matte
			sprite.hide()
			surface.add_child(sprite)

func lettering_texture(id: String, bounds: Vector2) -> ImageTexture:
	var source: Image = model.images[id]
	var size := source.get_size()
	var ratio := minf(bounds.x * 2 / size.x, bounds.y * 2 / size.y)
	if ratio >= 1:
		return ImageTexture.create_from_image(source)
	var sampled: Image = source.duplicate()
	sampled.resize(roundi(size.x * ratio), roundi(size.y * ratio), Image.INTERPOLATE_LANCZOS)
	return ImageTexture.create_from_image(sampled)

func lettering_screen() -> String:
	if lettering.is_empty() or model.phase == "result":
		return ""
	var context: Dictionary = model.presentation_context
	if context.mode == "player" and context.lifecycle == "ready":
		return "title"
	if (context.mode != "player" or context.lifecycle == "running") and lettering.chapters.has(model.current_section):
		return "chapter"
	return ""

func place_lettering(sprite: Sprite2D, texture: Texture2D, center: Vector2, bounds: Vector2) -> void:
	var size := texture.get_size()
	sprite.texture = texture
	sprite.position = center
	sprite.scale = Vector2.ONE * minf(bounds.x / size.x, bounds.y / size.y)

func update_lettering() -> void:
	if lettering.is_empty():
		return
	var screen := lettering_screen()
	var key: String = model.current_section if screen == "chapter" else screen
	if key == lettering_key:
		return
	lettering_key = key
	title_sprite.visible = screen == "title"
	chapter_sprite.visible = not screen.is_empty()
	var canvas := Vector2(model.level.layout.width, model.level.layout.height)
	if screen == "title":
		place_lettering(title_sprite, lettering.title, canvas * Vector2(.5, .283), TITLE_BOUNDS)
		place_lettering(chapter_sprite, lettering.first_chapter, canvas * Vector2(.5, .46), FIRST_CHAPTER_BOUNDS)
	elif screen == "chapter":
		place_lettering(chapter_sprite, lettering.chapters[model.current_section], canvas * Vector2(.5, .48), CHAPTER_BOUNDS)

func draw_lettering_card(surface, screen: String, section: Dictionary) -> void:
	var canvas := Vector2(model.level.layout.width, model.level.layout.height)
	var center := canvas.x * .5
	surface.draw_rect(Rect2(Vector2.ZERO, canvas), Color(.015, .02, .04, .72 if screen == "title" else .62))
	if screen == "title":
		surface.label(model.level.presentation.instructions, Vector2(center, canvas.y * .61), 29, Color("#dfd0b4"), true)
		draw_action(surface, false)
		surface.label("Enter / 光枪开始键 · R 换弹", Vector2(center, canvas.y * .81), 24, Color("#e3bd76"), true)
	else:
		var chapter: String = section.title.split(" · ", false, 1)[0]
		surface.label(chapter, Vector2(center, canvas.y * .33), 28, Color("#dec69e"), true)
		surface.label(section.get("hint", ""), Vector2(center, canvas.y * .75), 30, Color("#e9d5af"), true)

func read_metadata(id: String) -> Dictionary:
	var path: String = model.root_path.path_join(model.level.resources[id].path)
	return JSON.parse_string(FileAccess.get_file_as_string(path))

func rect(element: Dictionary) -> Rect2:
	return Rect2(Vector2(element.pos[0], element.pos[1]), Vector2(element.size[0], element.size[1]))

func fit(surface, text: String, width: float, size: int) -> int:
	var measured: float = surface.font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	return mini(size, floori(size * width / maxf(width, measured)))

func action_rect(retry: bool) -> Rect2:
	var canvas := Vector2(model.level.layout.width, model.level.layout.height)
	var center := Vector2(canvas.x * .5, canvas.y * .5 + 109 if retry else canvas.y * .72)
	var size := Vector2(268, 70)
	return Rect2(center - size * .5, size)

func draw_action(surface, retry: bool) -> void:
	var box := action_rect(retry)
	action_style.modulate_color = Color("#d5b58b")
	if action_pressed:
		action_style.modulate_color = Color("#ae815f")
	elif action_hovered:
		action_style.modulate_color = Color("#f4d9a0")
	surface.draw_style_box(action_style, box)
	surface.label("重试" if retry else "开始", box.get_center() + Vector2(0, 12), 34, Color("#f1d5a1"), true)

func draw_prompt(surface, prompt: String, progress := "") -> void:
	var box := rect(elements.prompt)
	var center := box.get_center()
	surface.draw_texture_rect(textures.prompt_bar, box, false)
	if not progress.is_empty():
		surface.label(progress, center + Vector2(0, -6), 19, Color("#dec69e"), true)
	var baseline := 9 if progress.is_empty() else 19
	surface.label(prompt, center + Vector2(0, baseline), fit(surface, prompt, 546, 25), Color("#f1d8ad"), true)

func station_heading(section: Dictionary) -> String:
	var stations: Array = model.level.presentation.stations
	return "第 %d / %d 站 · %s" % [section.station, stations.size(), stations[int(section.station) - 1]]

func preload_station_caption(surface, section: Dictionary, index: int) -> void:
	if not section.has("station") or section.get("skippable", false):
		return
	if index == 0:
		surface.warm_label(station_heading(section), 24)
	else:
		var prompt: String = section.get("hint", "")
		surface.warm_label(prompt, fit(surface, prompt, 546, 25))

func draw_playing(surface, section: Dictionary, stats: Dictionary) -> void:
	var life: Dictionary = elements.life
	var life_rect := rect(life)
	var lives: int = model.resources.lives
	var life_size := Vector2(life.cell[0], life.cell[1]) * (44.0 / float(life.cell[1]))
	var life_color := Color("#ffc4a3") if lives <= 2 else Color("#ffedca")
	var life_panel := Rect2(life_rect.position - Vector2(10, 12), life_rect.size + Vector2(20, 24))
	surface.draw_rect(life_panel, Color("#21192bea"))
	surface.draw_rect(life_panel, Color("#b88e60"), false, 2)
	surface.label("生命 %d / %d" % [lives, life.count],
		Vector2(life_rect.get_center().x, life_rect.position.y + 18), 27, life_color, true)
	for index in range(life.count):
		var slot_x := index * (float(life.cell[0]) + float(life.gap))
		var point := life_rect.position + Vector2(slot_x + (float(life.cell[0]) - life_size.x) * .5, 28)
		var icon: Texture2D = textures.life_wick if index < lives else textures.life_wick_empty
		surface.draw_texture_rect(icon, Rect2(point, life_size), false)

	var ammo_rect := rect(elements.ammo)
	var magazine: int = model.level.controls.magazine
	var ammo: int = model.resources[model.level.controls.ammo_resource]
	var stride := ammo_rect.size.x / magazine
	var cell := Vector2(minf(stride - 3, elements.ammo.cell[0]), 0)
	cell.y = cell.x * 1.5
	for index in range(magazine):
		var point := ammo_rect.position + Vector2(index * stride + (stride - cell.x) * .5, ammo_rect.size.y - cell.y)
		var icon: Texture2D = textures.ammo_light if index < ammo else textures.ammo_light_empty
		surface.draw_texture_rect(icon, Rect2(point, cell), false)
	surface.label("光弹 %d / %d" % [ammo, magazine], ammo_rect.get_center() + Vector2(0, -4), 20, Color("#ead6ae"), true)

	var score_rect := rect(elements.score)
	var score := str(int(model.resources.score))
	surface.draw_texture_rect(textures.score_seal, score_rect, false)
	surface.label(score, score_rect.get_center() + Vector2(0, 10), fit(surface, score, 81, 32), Color("#eed5b0"), true)
	surface.label(station_heading(section), Vector2(24, 48), 24)

	var prompt: String = section.get("hint", "")
	if tracking_lost:
		prompt = TRACKING_PROMPT
	elif model.reload_at >= 0:
		prompt = "自动回光中…" if ammo == 0 and model.level.controls.get("auto_reload", false) else "回光中…"
	elif ammo == 0:
		prompt = "光弹用尽 · R 或向屏外射击换弹"
	var progress := "净化 %d / %d · 获救 %d" % [stats.section_cleared, stats.section_total, int(model.resources.rescued)]
	draw_prompt(surface, prompt, progress)

	var canvas := Vector2(model.level.layout.width, model.level.layout.height)
	if model.input_enabled and Rect2(Vector2.ZERO, canvas).has_point(aim):
		var size := Vector2(crosshair.display_size[0], crosshair.display_size[1])
		var anchor := Vector2(crosshair.center[0], crosshair.center[1])
		surface.draw_texture_rect(textures.crosshair, Rect2(aim - size * anchor, size), false, Color(1, 1, 1, crosshair.opacity))

func draw_result(surface, section: Dictionary, stats: Dictionary) -> void:
	var canvas := Vector2(model.level.layout.width, model.level.layout.height)
	var center := canvas * .5
	var labels: Dictionary = model.level.presentation.labels
	var clear: bool = model.result == "clear"
	var title: String = labels.get("result_success", "完成") if clear else labels.get("result_failure", "失败")
	surface.draw_rect(Rect2(Vector2.ZERO, canvas), Color(.02, .025, .045, .57))
	surface.draw_style_box(panel, Rect2(center - Vector2(346, 189), Vector2(692, 414)))
	surface.label(title, center + Vector2(0, -76), fit(surface, title, 572, 49), Color("#f1d5a1"), true)
	if clear and stats.section_total == 0 and section.has("hint"):
		surface.label(section.hint, center + Vector2(0, -25), 28, Color("#e8cda3"), true)
	var summary := "净化 %d / %d　获救 %d　印记 %d" % [stats.cleared, stats.total, int(model.resources.rescued), int(model.resources.score)]
	surface.label(summary, center + Vector2(0, 33), fit(surface, summary, 570, 30), Color("#ebd4ae"), true)
	draw_action(surface, true)
	surface.label("Enter / 光枪开始键", center + Vector2(0, 167), 22, Color("#e2bb7a"), true)
