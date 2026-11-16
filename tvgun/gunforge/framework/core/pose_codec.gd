extends RefCounted
const Item = preload("raster_item.gd")

static func encode(items: Array, assets: Dictionary) -> Array:
	if items.is_empty():
		return []
	var ids_by_image := {}
	for candidate in assets:
		var image: Image = assets[candidate].image
		if not ids_by_image.has(image):
			ids_by_image[image] = candidate
	var out = []
	for item in items:
		assert(ids_by_image.has(item.image), "Pose references an unregistered image")
		var entry := {"asset":ids_by_image.get(item.image, ""),"source":item.source,"transform":item.transform,
			"size":item.size,"id":item.id,"kind":item.kind,"tint":item.tint,"generation":item.generation}
		if item.hit_image != null:
			assert(ids_by_image.has(item.hit_image), "Pose references an unregistered hit image")
			entry.hit_asset = ids_by_image.get(item.hit_image, "")
		out.append(entry)
	return out

static func decode(data: Array, assets: Dictionary) -> Array:
	var out = []
	for entry in data:
		assert(assets.has(entry.asset), "Snapshot requires missing asset")
		var item = Item.new()
		item.image = assets[entry.asset].image
		if entry.has("hit_asset"):
			item.hit_image = assets[entry.hit_asset].image
		item.texture = assets[entry.asset].texture
		item.source = entry.source
		item.transform = entry.transform
		item.size = entry.size
		item.id = entry.id
		item.kind = entry.kind
		item.tint = entry.tint
		item.generation=int(entry.get("generation",0))
		out.append(item)
	return out
