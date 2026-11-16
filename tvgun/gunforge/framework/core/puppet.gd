extends RefCounted

const Item = preload("raster_item.gd")
var rig: Dictionary
var clips = {}
var image: Image
var texture: Texture2D
var folder: String

func open_registered(data:Dictionary,animations:Dictionary,atlas:Image):
	rig = data.rig.duplicate(true)
	clips = animations.duplicate(true)
	image = atlas
	texture = null # The level scene uploads registered atlases when they are visible.

func open(path: String):
	folder = path
	var data = JSON.parse_string(FileAccess.get_file_as_string(path.path_join("character.json")))
	rig = data.rig
	for name in data.clips:
		clips[name] = JSON.parse_string(FileAccess.get_file_as_string(path.path_join(data.clips[name])))
	texture = load(path.path_join("atlas.png"))
	image = texture.get_image()

func pose(name: String, seconds: float) -> Dictionary:
	var clip = clips[name]
	var t = fposmod(seconds, clip.duration) if clip.meta.loop else clampf(seconds, 0, clip.duration)
	var f = t / clip.duration * (clip.frames.size()-1)
	var a = clip.frames[int(f)]
	var b = clip.frames[mini(int(f)+1, clip.frames.size()-1)]
	var world = {}
	for bone in rig.bones:
		var v = []
		for i in range(5):
			var default = 1.0 if i >= 3 else 0.0
			var left = a.get(bone.id, [])
			var right = b.get(bone.id, [])
			v.append(lerpf(left[i] if i < left.size() else default, right[i] if i < right.size() else default, f-floor(f)))
		var parent = world.get(bone.parent, {})
		var xy = Vector2(bone.x + v[0], bone.y + v[1])
		if not parent.is_empty():
			xy = (xy * Vector2(parent.sx, parent.sy)).rotated(deg_to_rad(parent.a)) + parent.xy
		world[bone.id] = {"xy": xy, "a": parent.get("a", 0)+bone.a+v[2], "sx": v[3], "sy": v[4]}
	var slots = []
	for original in rig.attachments:
		var slot = original.duplicate(true)
		var visible = not slot.get("hidden", false)
		for key in clip.meta.get("attachment_keys", {}).get(slot.part, []):
			if key.time > t:
				break
			visible = key.get("visible", visible)
			var variant = key.get("variant", "")
			if slot.get("variants", {}).has(variant):
				slot.merge(slot.variants[variant], true)
		if visible:
			slots.append(slot)
	return {"world": world, "slots": slots, "time": t}

func items(name: String, seconds: float, origin: Vector2, protected: bool, targetable_ink: bool = true, primary_part: String = "rescue_ink", primary_id: String = "resident_ink", body_id: String = "resident") -> Array:
	var state = pose(name, seconds)
	var result = []
	for slot in state.slots:
		var bone = state.world[slot.bone]
		var item = Item.new()
		item.image = image
		item.texture = texture
		item.source = Rect2(slot.rect[0], slot.rect[1], slot.rect[2], slot.rect[3])
		item.size = Vector2(slot.size[0], slot.size[1])
		var angle = -deg_to_rad(bone.a + slot.a)
		var basis = Transform2D(angle, Vector2.ZERO).scaled_local(Vector2(bone.sx, bone.sy))
		basis.origin = origin + Vector2(bone.xy.x, -bone.xy.y) - basis.basis_xform(Vector2(slot.pivot[0], slot.pivot[1]) * item.size)
		item.transform = basis
		item.kind = "primary" if slot.part == primary_part and targetable_ink else ("protected" if protected else "")
		item.id = primary_id if slot.part == primary_part else body_id
		result.append(item)
	return result
