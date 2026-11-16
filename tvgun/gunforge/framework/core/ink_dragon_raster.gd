extends RefCounted
## Shared raster composition for the full dragon in review and the playable level.

const Chain = preload("ink_dragon_chain.gd")
const Item = preload("raster_item.gd")
const BODY_ART = ["paper", "locked", "ink", "glow", "purified"]

var layout: Dictionary
var images: Dictionary
var pivots: Array = []
var chain = Chain.new()

static func point(values: Array) -> Vector2:
	return Vector2(values[0], values[1])

static func image_paths(data: Dictionary) -> Array[String]:
	var paths: Array[String] = []
	for node in data.body_nodes:
		for state in BODY_ART:
			paths.append(node.textures[state])
	paths.append_array([data.head.upper_jaw, data.head.lower_jaw, data.tail.file,
		data.mouth.core, data.mouth.glow, data.mouth.interior])
	return paths

func configure(data: Dictionary, source_images: Dictionary) -> bool:
	layout = data
	images = source_images
	pivots.clear()
	var ids: Array = []
	for node in layout.body_nodes:
		pivots.append([point(node.pivots[0]), point(node.pivots[1])])
		ids.append(node.id)
	var order: Array = []
	for id in layout.opening_order:
		order.append(ids.find(id))
	return chain.configure(pivots, order)

func body_pose(clock: float) -> Array[Transform2D]:
	var at := point(layout.origin) + point(layout.sway) * Vector2(sin(clock * 1.3), sin(clock * 1.9))
	return chain.pose(at, clock, float(layout.body_scale))

func attach(at: Vector2, angle: float, pivot: Vector2) -> Transform2D:
	var result := Transform2D(angle, at).scaled_local(Vector2.ONE * float(layout.body_scale))
	result.origin -= result.basis_xform(pivot)
	return result

func head_transform(body: Transform2D, swing: float = 0.0) -> Transform2D:
	return attach(body * pivots[0][0], body.get_rotation() + swing, point(layout.head.neck_pivot))

func mouth_pose(head: Transform2D) -> Transform2D:
	return attach(head * point(layout.mouth.anchor), head.get_rotation(), point(layout.mouth.center))

func raster(path: String, basis: Transform2D, id: String = "", kind: String = ""):
	var item = Item.new()
	item.image = images[path]
	item.size = Vector2(item.image.get_size())
	item.source = Rect2(Vector2.ZERO, item.size)
	item.transform = basis
	item.id = id
	item.kind = kind
	return item

func items(poses: Array[Transform2D], clock: float, states: Array, mouth_state: String,
		mouth_id: String = "mouth", swing: float = 0.0) -> Array:
	var last := poses.size() - 1
	var tail_angle := poses[last].get_rotation() + deg_to_rad(9 * sin(clock * 3 - 2))
	var scene := [raster(layout.tail.file, attach(poses[last] * pivots[last][1], tail_angle, point(layout.tail.pivot)))]
	for index in range(last, -1, -1):
		var node: Dictionary = layout.body_nodes[index]
		var art: Dictionary = node.textures
		var state: String = states[index]
		var transform := poses[index]
		if state == Chain.PURIFIED:
			var afterglow = raster(art.purified, transform)
			afterglow.tint.a = .24
			scene.append(afterglow)
		scene.append(raster(art.locked if state == Chain.LOCKED else art.paper, transform))
		if state == Chain.ACTIVE:
			var glow = raster(art.glow, transform)
			glow.tint.a = .65 + .25 * sin(clock * 9)
			scene.append(glow)
			scene.append(raster(art.ink, transform, node.id, "primary"))
	var head := head_transform(poses[0], swing)
	if mouth_state == Chain.ACTIVE:
		var mouth := mouth_pose(head)
		var interior := mouth
		interior.origin += interior.basis_xform(point(layout.mouth.center) - point(layout.mouth.interior_center))
		scene.append(raster(layout.mouth.interior, interior))
		var shine = raster(layout.mouth.glow, mouth)
		shine.tint.a = .65
		scene.append(shine)
		scene.append(raster(layout.mouth.core, mouth, mouth_id, "weak"))
	var jaw_angle := deg_to_rad(float(layout.head.open_degrees) if mouth_state == Chain.ACTIVE else 12 + 4 * sin(clock * 4))
	var jaw := attach(head * point(layout.head.hinge), head.get_rotation() - jaw_angle, point(layout.head.jaw_pivot))
	scene.append(raster(layout.head.lower_jaw, jaw, "lower_jaw", "blocker"))
	scene.append(raster(layout.head.upper_jaw, head, "upper_jaw", "blocker"))
	return scene
