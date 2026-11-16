extends SceneTree
## Local review harness for the Ink Dragon. Shares runtime raster picking.

const Chain = preload("res://core/ink_dragon_chain.gd")
const Dragon = preload("res://core/ink_dragon_raster.gd")
const Item = preload("res://core/raster_item.gd")
const Painter = preload("res://core/raster_layer.gd")
const Resolver = preload("res://core/hit_resolver.gd")
const SAMPLE_TEXTURES = {"paper":"base", "locked":"locked", "glow":"active_glow",
	"purified":"purified_glow", "ink":"ink"}

var chain = Chain.new()
var resolver = Resolver.new()
var painter: Node2D
var resources := {}
var layout: Dictionary
var pivots: Array = []
var order: Array = []
var view_size: Vector2
var ink_centers: Array[Vector2] = []
var hits: Array = []
var jaw_cover: Array = []
var full_art := false
var dragon = Dragon.new()
var dragon_textures: Dictionary = {}
var clock := 0.0

func _initialize() -> void:
	call_deferred("run")

func point(values: Array) -> Vector2:
	return Vector2(values[0], values[1])

func read_json(path: String) -> Dictionary:
	var decoded = JSON.parse_string(FileAccess.get_file_as_string(path))
	return decoded if decoded is Dictionary else {}

func register_texture(id: String, image: Image) -> bool:
	if image == null or image.is_empty():
		printerr("Missing prototype texture: " + id)
		return false
	resources[id] = [image, ImageTexture.create_from_image(image)]
	return true

func raster(key: String, basis: Transform2D, id: String = "", kind: String = ""):
	var item = Item.new()
	item.image = resources[key][0]
	item.texture = resources[key][1]
	item.size = Vector2(item.image.get_size())
	item.source = Rect2(Vector2.ZERO, item.size)
	item.transform = basis
	item.id = id
	item.kind = kind
	return item

func load_prototype(path: String) -> bool:
	layout = read_json(path)
	if layout.is_empty() or layout.max_active != 1 or layout.body_nodes.size() != 8 or float(layout.body_scale) <= 0:
		return false
	var root_dir := path.get_base_dir()
	full_art = not layout.has("sample")
	var sample := {}
	if not full_art:
		var sample_path := root_dir.path_join(layout.sample)
		sample = read_json(sample_path)
		if sample.is_empty():
			return false
		for entry in SAMPLE_TEXTURES:
			var texture_path := sample_path.get_base_dir().path_join(sample[SAMPLE_TEXTURES[entry]])
			if not register_texture(entry, Image.load_from_file(texture_path)):
				return false
		if not register_texture("mouth", mouth_texture(float(layout.mouth.radius))):
			return false
	var parent := "head"
	var ids := []
	for node in layout.body_nodes:
		if node.parent != parent or node.id != "body_%02d" % (ids.size() + 1):
			return false
		parent = node.id
		ids.append(node.id)
		if full_art:
			pivots.append([point(node.pivots[0]), point(node.pivots[1])])
			ink_centers.append(point(node.aim) + Vector2(.5, .5))
		else:
			pivots.append([point(sample.pivots[0]), point(sample.pivots[1])])
			ink_centers.append(ink_center_for(resources.ink[0]))
	for id in layout.opening_order:
		order.append(ids.find(id))
	if not chain.configure(pivots, order):
		return false
	view_size = point(layout.content_size)
	if not register_texture("background", Image.load_from_file(root_dir.path_join(layout.background))):
		return false
	if full_art:
		var images := {}
		for file in Dragon.image_paths(layout):
			if not register_texture(file, Image.load_from_file(root_dir.path_join(file))):
				return false
			images[file] = resources[file][0]
			dragon_textures[images[file].get_instance_id()] = resources[file][1]
		return dragon.configure(layout, images)
	return true

func ink_center_for(ink: Image) -> Vector2:
	var bounds := ink.get_used_rect()
	var best := INF
	var center := Vector2.ZERO
	for y in range(bounds.position.y, bounds.end.y):
		for x in range(bounds.position.x, bounds.end.x):
			var candidate := Vector2(x + .5, y + .5)
			var distance := candidate.distance_squared_to(bounds.get_center())
			if distance < best and ink.get_pixel(x, y).a >= .9:
				center = candidate
				best = distance
	return center

func mouth_texture(radius: float) -> Image:
	var size := ceili(radius * 2)
	var image := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var center := Vector2.ONE * radius
	for y in size:
		for x in size:
			var distance := (Vector2(x + .5, y + .5) - center).length()
			if distance < radius:
				image.set_pixel(x, y, Color("#ce5346"))
	return image

func body_pose() -> Array[Transform2D]:
	if full_art:
		return dragon.body_pose(clock)
	var origin := point(layout.get("origin", [420, 420]))
	var sway := point(layout.get("sway", [58, 48]))
	var at := origin + sway * Vector2(sin(clock * 1.3), sin(clock * 1.9))
	return chain.pose(at, clock, float(layout.body_scale))

func mouth_pose(head_pose: Transform2D) -> Transform2D:
	if full_art:
		return dragon.mouth_pose(dragon.head_transform(head_pose))
	var center: Vector2 = head_pose * pivots[0][0]
	var offset := point(layout.mouth.offset_from_body_anchor).rotated(head_pose.get_rotation())
	return Transform2D(0, center + offset - Vector2.ONE * float(layout.mouth.radius))

func compose(poses: Array[Transform2D]) -> void:
	var background = raster("background", Transform2D.IDENTITY)
	background.size = view_size
	var scene := [background]
	hits.clear()
	jaw_cover.clear()
	if full_art:
		var states: Array = []
		for index in poses.size():
			states.append(chain.segment_state(index))
		for item in dragon.items(poses, clock, states, chain.mouth_state()):
			if item.kind == "blocker":
				jaw_cover.append(item)
			elif item.kind != "":
				hits.append(item)
			item.texture = dragon_textures[item.image.get_instance_id()]
			scene.append(item)
		if painter:
			painter.refresh(scene)
		return
	for index in range(poses.size() - 1, -1, -1):
		var id: String = layout.body_nodes[index].id
		var state := chain.segment_state(index)
		var transform := poses[index]
		if state == Chain.PURIFIED:
			var afterglow = raster("purified", transform)
			afterglow.tint.a = .24
			scene.append(afterglow)
		scene.append(raster("locked" if state == Chain.LOCKED else "paper", transform))
		if state == Chain.ACTIVE:
			var glow = raster("glow", transform)
			glow.tint.a = .65 + .25 * sin(clock * 9)
			scene.append(glow)
			var ink = raster("ink", transform, id, "primary")
			scene.append(ink)
			hits.append(ink)
	if chain.mouth_state() == Chain.ACTIVE:
		var mouth = raster("mouth", mouth_pose(poses[0]), Chain.MOUTH, "weak")
		scene.append(mouth)
		hits.append(mouth)
	if painter:
		painter.refresh(scene)

func shoot(at: Vector2) -> bool:
	var target: Dictionary = resolver.exact(at, hits + jaw_cover)
	return not target.is_empty() and chain.apply_hit(target.id)

func probe() -> bool:
	var shots := []
	var maximum_joint_gap := 0.0
	for frame in 120:
		clock = frame / 30.0
		var posed := body_pose()
		for index in range(posed.size() - 1):
			var a: Vector2 = posed[index] * pivots[index][1]
			var b: Vector2 = posed[index + 1] * pivots[index + 1][0]
			var gap := a.distance_to(b)
			maximum_joint_gap = maxf(maximum_joint_gap, gap)
	if maximum_joint_gap > .001:
		return false
	for index in order:
		var posed := body_pose()
		compose(posed)
		if hits.size() != 1 or chain.apply_hit(Chain.MOUTH):
			return false
		for other in posed.size():
			if other != index and shoot(posed[other] * ink_centers[other]):
				return false
		var point_on_ink: Vector2 = posed[index] * ink_centers[index]
		if not shoot(point_on_ink):
			return false
		shots.append(layout.body_nodes[index].id)
		compose(posed)
		if shoot(point_on_ink):
			return false
	var last_pose := body_pose()
	compose(last_pose)
	if hits.size() != 1 or hits[0].id != Chain.MOUTH:
		return false
	var mouth := mouth_pose(last_pose[0])
	var center := point(layout.mouth.center) if full_art else Vector2.ONE * float(layout.mouth.radius)
	if shoot(mouth.origin + Vector2.ONE) or not shoot(mouth * center):
		return false
	compose(last_pose)
	var passed := chain.complete() and hits.is_empty() and not chain.apply_hit(Chain.MOUTH)
	print(JSON.stringify({"passed": passed, "body_order": shots, "mouth_last": chain.complete(),
		"motion_frames": 120, "max_joint_gap_px": maximum_joint_gap}))
	return passed

func run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.is_empty() or not load_prototype(args[0]):
		printerr("Usage: ink_dragon_review.gd -- <boss.json or boss_draft.json> [--probe]")
		quit(2)
		return
	if "--probe" in args:
		quit(0 if probe() else 1)
		return
	root.title = "墨舞龙 · 左键净化，R 重置，Esc 关闭"
	root.content_scale_size = Vector2i(view_size)
	root.content_scale_mode = Window.CONTENT_SCALE_MODE_CANVAS_ITEMS
	root.content_scale_aspect = Window.CONTENT_SCALE_ASPECT_KEEP
	painter = Painter.new()
	root.add_child(painter)
	root.window_input.connect(on_input)

func _process(delta: float) -> bool:
	if painter:
		clock += delta
		compose(body_pose())
	return false

func on_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		shoot(event.position)
	elif event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_R:
			chain.reset()
		elif event.keycode == KEY_ESCAPE:
			quit()
