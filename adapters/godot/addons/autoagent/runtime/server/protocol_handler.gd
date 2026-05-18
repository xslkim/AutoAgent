extends RefCounted
## JSON-RPC 2.0 dispatcher for the AutoAgent wire protocol.
##
## Runs synchronously on the main thread — Godot's JSON class handles parsing
## and serialisation natively, so no hand-rolled JSON code is needed.

const ControlReflector := preload("../reflection/control_reflector.gd")
const EngineInputDriver := preload("../input/engine_input_driver.gd")

const SERVER_VERSION := "0.1"

var _reflector
var _input


func _init() -> void:
	_reflector = ControlReflector.new()
	_input = EngineInputDriver.new()


func dispatch(json_text: String) -> String:
	var parsed = JSON.parse_string(json_text)
	if typeof(parsed) != TYPE_DICTIONARY:
		return _error(null, -32700, "parse error")

	var method = parsed.get("method", "")
	var id = parsed.get("id", null)
	var params = parsed.get("params", {})
	if typeof(params) != TYPE_DICTIONARY:
		params = {}

	match method:
		"negotiate_version":
			return _ok(id, {"server_version": SERVER_VERSION, "accepted": true})
		"dump_tree":
			return _ok(id, _reflector.reflect_scene())
		"find_widget":
			return _ok(id, _find_widget(params))
		"get_widget":
			return _get_widget(id, params)
		"click":
			return _action(id, _input.click(params.get("id", "")))
		"send_text":
			return _action(id, _input.send_text(
				params.get("id", ""), str(params.get("text", ""))))
		"drag":
			return _action(id, _input.drag(
				params.get("from_id", ""), params.get("to_id", "")))
		"scroll":
			return _action(id, _input.scroll(
				params.get("id", ""),
				float(params.get("delta_x", 0.0)),
				float(params.get("delta_y", 0.0))))
		"take_screenshot":
			return _take_screenshot(id, params)
		_:
			return _error(id, -32601, "method not found: " + str(method))


# --- handlers --------------------------------------------------------------

func _find_widget(params: Dictionary) -> Array:
	var role = params.get("logical_role", null)
	var matches: Array = []
	for node in _reflector.reflect_scene():
		if role != null:
			var meta = node.get("meta", {})
			if meta.get("logical_role", "") != role:
				continue
		matches.append(node["id"])
	return matches


func _get_widget(id, params: Dictionary) -> String:
	var node_id = str(params.get("id", ""))
	for node in _reflector.reflect_scene():
		if node["id"] == node_id:
			return _ok(id, node)
	return _error(id, -32001, "widget not found: " + node_id)


func _action(id, ok: bool) -> String:
	if ok:
		return _ok(id, null)
	return _error(id, -32001, "widget not found or action failed")


func _take_screenshot(id, params: Dictionary) -> String:
	var path := str(params.get("path", ""))
	if path.is_empty():
		return _error(id, -32602, "missing param: path")
	var tree := Engine.get_main_loop() as SceneTree
	if tree == null or tree.root == null:
		return _error(id, -32603, "no active viewport")
	var image := tree.root.get_texture().get_image()
	if image == null:
		return _error(id, -32603, "could not capture viewport image")
	var err := image.save_png(path)
	if err != OK:
		return _error(id, -32603, "save_png failed (error %d)" % err)
	return _ok(id, {"path": path})


# --- JSON-RPC envelope -----------------------------------------------------

func _ok(id, result) -> String:
	return JSON.stringify({"jsonrpc": "2.0", "id": id, "result": result})


func _error(id, code: int, message: String) -> String:
	return JSON.stringify({
		"jsonrpc": "2.0", "id": id,
		"error": {"code": code, "message": message},
	})
