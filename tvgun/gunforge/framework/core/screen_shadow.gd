extends RefCounted
## A projector is scenery. Only reel ink and the exposed screen core can be cleared.

const Item = preload("res://core/raster_item.gd")
const Resolver = preload("res://core/hit_resolver.gd")

var _resolver = Resolver.new()
var _projectors: Array = []
var _reels: Array = []
var _reel_by_projector := {}
var _cleaned := {}
var _core
var _cleared := false

func configure(spec: Dictionary, masks: Dictionary = {}) -> bool:
	var projectors: Array = spec.get("projectors", [])
	if projectors.size() != 3 or not spec.has("core"):
		return false
	_projectors.clear()
	_reels.clear()
	_reel_by_projector.clear()
	var ids := {}
	for projector in projectors:
		var reel: Dictionary = projector.reel
		if ids.has(projector.id) or ids.has(reel.id) or projector.id == reel.id:
			return false
		ids[projector.id] = true
		ids[reel.id] = true
		_projectors.append(make_item(projector, "invalid", false, masks.get("projector")))
		_reels.append(make_item(reel, "primary", true, masks.get("reel_ink")))
		_reel_by_projector[projector.id] = reel.id
	if ids.has(spec.core.id):
		return false
	_core = make_item(spec.core, "primary", true, masks.get("core"))
	reset()
	return true

func make_item(definition: Dictionary, kind: String, ellipse: bool = false, mask: Image = null):
	var rect: Array = definition.get("art_rect", definition.rect) if mask else definition.rect
	var size := Vector2i(int(rect[2]), int(rect[3]))
	var image := mask
	if not image:
		image = Image.create(size.x, size.y, false, Image.FORMAT_RGBA8)
		if ellipse:
			var radius := Vector2(size) * .5
			for y in size.y:
				for x in size.x:
					var unit := (Vector2(x + .5, y + .5) - radius) / radius
					if unit.length_squared() <= 1:
						image.set_pixel(x, y, Color.WHITE)
		else:
			image.fill(Color.WHITE)
	var item = Item.new()
	item.id = definition.id
	item.kind = kind
	item.image = image
	item.source = Rect2(Vector2.ZERO, Vector2(image.get_size()))
	item.size = Vector2(size)
	item.transform.origin = Vector2(rect[0], rect[1])
	return item

func reset() -> void:
	_cleaned.clear()
	_cleared = false

func beam_warm(projector: String) -> bool:
	return _cleaned.has(_reel_by_projector.get(projector, ""))

func core_exposed() -> bool:
	return _reels.size() == 3 and _cleaned.size() == 3 and not _cleared

func complete() -> bool:
	return _cleared

func shoot(at: Vector2) -> String:
	var geometry: Array = _projectors.duplicate()
	for reel in _reels:
		if not _cleaned.has(reel.id):
			geometry.append(reel)
	if core_exposed():
		geometry.append(_core)
	var hit: Dictionary = _resolver.exact(at, geometry)
	if hit.is_empty():
		return "miss"
	if hit.kind == "invalid":
		return "invalid"
	if hit.id == _core.id:
		_cleared = true
		return "clear"
	_cleaned[hit.id] = true
	return "reel"
