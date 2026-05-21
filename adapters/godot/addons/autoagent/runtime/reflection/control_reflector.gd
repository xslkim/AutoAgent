extends RefCounted
## Reflects the running scene's node tree into AutoAgent protocol nodes.
##
## Pinned ids and metadata are read from Godot node metadata authored in the
## .tscn (autoagent_pinned_id / autoagent_logical_role / autoagent_state_sprites).
##
## stable_id_source priority (mirrors UE FStableIdResolver):
##   1. "pinned"  — node has metadata/autoagent_pinned_id set in .tscn / at runtime
##   2. "auto"    — node.name is a clean identifier (no "@" suffix, non-empty)
##   3. "hash"    — auto-generated name (e.g. "Button@2"); hash of class::path used

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
	var id_source := _resolve_id_and_source(node)
	var node_id: String = id_source[0]
	var source: String = id_source[1]

	var entry := {
		"id": node_id,
		"type": node.get_class(),
		"engine_type": node.get_class(),
		"parent_id": parent_id,
		"children_ids": [],
		"stable_id_source": source,
		"visual": _build_visual(node),
	}

	var behavior := _build_behavior(node)
	if not behavior.is_empty():
		entry["behavior"] = behavior

	var meta = _build_meta(node)
	if meta != null:
		entry["meta"] = meta

	var extras := _build_engine_extras(node)
	if not extras.is_empty():
		entry["engine_extras"] = extras

	out.append(entry)

	for child in node.get_children():
		entry["children_ids"].append(_walk(child, node_id, out))
	return node_id


## Returns [id: String, stable_id_source: String].
## "pinned" → explicit meta; "auto" → clean node.name; "hash" → generated name.
func _resolve_id_and_source(node: Node) -> Array:
	if node.has_meta(PINNED_META):
		return [str(node.get_meta(PINNED_META)), "pinned"]
	var name_str := str(node.name)
	# Godot auto-names duplicates with "@" (e.g. "Button@2") — not stable.
	if name_str.is_empty() or "@" in name_str:
		var path_str := str(node.get_path()) if node.is_inside_tree() else name_str
		var h: int = abs((node.get_class() + "::" + path_str).hash())
		return ["h_%08x" % h, "hash"]
	return [name_str, "auto"]


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


func _build_behavior(node: Node) -> Dictionary:
	if not (node is Control):
		return {}
	var ctrl := node as Control
	# A node is interactable only if mouse events reach it.
	var interactable: bool = ctrl.mouse_filter != Control.MOUSE_FILTER_IGNORE
	if node is BaseButton:
		# Disabled buttons cannot be clicked.
		interactable = interactable and not (node as BaseButton).disabled
	return {
		"interactable": interactable,
		"raycast_target": ctrl.mouse_filter == Control.MOUSE_FILTER_STOP,
	}


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


func _build_engine_extras(node: Node) -> Dictionary:
	## Returns {"godot": {...}} with engine-specific fields not in the core schema.
	## Currently: text content for Label / Button / LineEdit / TextEdit.
	var g := {}
	if node is LineEdit:
		g["text"] = (node as LineEdit).text
		g["placeholder"] = (node as LineEdit).placeholder_text
	elif node is TextEdit:
		g["text"] = (node as TextEdit).text
	elif node is Label:
		g["text"] = (node as Label).text
	elif node is Button:
		g["text"] = (node as Button).text
	if g.is_empty():
		return {}
	return {"godot": g}


func _resource_name(res) -> String:
	if res == null:
		return ""
	var path: String = res.resource_path
	if path.is_empty():
		return ""
	return path.get_file().get_basename()
