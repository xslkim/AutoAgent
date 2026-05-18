extends RefCounted
## Reflects the running scene's node tree into AutoAgent protocol nodes.
##
## Pinned ids and metadata are read from Godot node metadata authored in the
## .tscn (autoagent_pinned_id / autoagent_logical_role / autoagent_state_sprites).

const PINNED_META := "autoagent_pinned_id"
const ROLE_META := "autoagent_logical_role"
const SPRITES_META := "autoagent_state_sprites"


## Reflect the active scene. Returns a flat Array of protocol-node Dictionaries.
func reflect_scene() -> Array:
	var tree := Engine.get_main_loop() as SceneTree
	var root: Node = tree.current_scene if tree != null else null
	if root == null:
		return []
	return reflect_from(root)


## Reflect an explicit subtree root — used by unit tests.
func reflect_from(root: Node) -> Array:
	var nodes: Array = []
	_walk(root, null, nodes)
	return nodes


# Appends `node` and its descendants to `out`; returns this node's id.
func _walk(node: Node, parent_id, out: Array) -> String:
	var node_id := _resolve_id(node)
	var entry := {
		"id": node_id,
		"type": node.get_class(),
		"engine_type": node.get_class(),
		"parent_id": parent_id,
		"children_ids": [],
		"stable_id_source": ("pinned" if node.has_meta(PINNED_META) else "auto"),
		"visual": _build_visual(node),
	}
	var meta = _build_meta(node)
	if meta != null:
		entry["meta"] = meta
	out.append(entry)

	for child in node.get_children():
		entry["children_ids"].append(_walk(child, node_id, out))
	return node_id


func _resolve_id(node: Node) -> String:
	if node.has_meta(PINNED_META):
		return str(node.get_meta(PINNED_META))
	return str(node.name)


func _build_visual(node: Node) -> Dictionary:
	var v := {}
	if node is Control:
		var c := node as Control
		v["position"] = [c.position.x, c.position.y]
		v["size"] = [c.size.x, c.size.y]
		v["visible"] = c.is_visible_in_tree()
		var r := c.get_global_rect()
		v["world_bounds"] = [
			r.position.x, r.position.y,
			r.position.x + r.size.x, r.position.y + r.size.y,
		]
		v["alpha"] = c.modulate.a
		v["color"] = "#" + c.modulate.to_html(true)
		if c is TextureRect and (c as TextureRect).texture != null:
			v["sprite_ref"] = _resource_name((c as TextureRect).texture)
	elif node is CanvasLayer:
		v["position"] = [0.0, 0.0]
		v["size"] = [0.0, 0.0]
		v["visible"] = (node as CanvasLayer).visible
	else:
		v["position"] = [0.0, 0.0]
		v["size"] = [0.0, 0.0]
		v["visible"] = true
	return v


func _build_meta(node: Node):
	var meta := {}
	if node.has_meta(ROLE_META):
		meta["logical_role"] = str(node.get_meta(ROLE_META))
	if node.has_meta(SPRITES_META):
		var raw = node.get_meta(SPRITES_META)
		if typeof(raw) == TYPE_DICTIONARY:
			var sprites := {}
			for state in raw:
				sprites[str(state)] = _resource_name(raw[state])
			meta["state_sprites"] = sprites
	if meta.is_empty():
		return null
	return meta


func _resource_name(res) -> String:
	if res == null:
		return ""
	var path: String = res.resource_path
	if path.is_empty():
		return ""
	return path.get_file().get_basename()
