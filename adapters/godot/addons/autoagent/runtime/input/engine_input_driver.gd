extends RefCounted
## Executes the four wire-protocol actions (click / send_text / drag / scroll)
## on nodes located by their stable id.
##
## By default nodes are searched in the active scene; tests may set
## `search_root` to point the driver at an explicit subtree.

const PINNED_META := "autoagent_pinned_id"

var search_root: Node = null


func click(node_id) -> bool:
	var node := _find(node_id)
	if node == null or not (node is Control):
		return false
	var center := (node as Control).get_global_rect().get_center()
	var vp := (node as Control).get_viewport()
	_mouse_button(vp, center, true)
	_mouse_button(vp, center, false)
	return true


func send_text(node_id, text: String) -> bool:
	var node := _find(node_id)
	if node == null:
		return false
	if node is LineEdit:
		var le := node as LineEdit
		le.text = text
		le.text_submitted.emit(text)
		return true
	if node is TextEdit:
		(node as TextEdit).text = text
		return true
	return false


func drag(from_id, to_id) -> bool:
	var src := _find(from_id)
	var dst := _find(to_id)
	if src == null or dst == null or not (src is Control) or not (dst is Control):
		return false
	var vp := (src as Control).get_viewport()
	var a := (src as Control).get_global_rect().get_center()
	var b := (dst as Control).get_global_rect().get_center()
	_mouse_button(vp, a, true)
	_mouse_motion(vp, a, b)
	_mouse_button(vp, b, false)
	return true


func scroll(node_id, delta_x: float, delta_y: float) -> bool:
	var node := _find(node_id)
	if node == null:
		return false
	if node is ScrollContainer:
		var sc := node as ScrollContainer
		sc.scroll_horizontal += int(delta_x)
		sc.scroll_vertical += int(delta_y)
		return true
	return false


# --- helpers ---------------------------------------------------------------

func _find(node_id) -> Node:
	var root := search_root
	if root == null:
		var tree := Engine.get_main_loop() as SceneTree
		root = tree.current_scene if tree != null else null
	if root == null:
		return null
	return _find_recursive(root, str(node_id))


func _find_recursive(node: Node, target: String) -> Node:
	var id := str(node.get_meta(PINNED_META)) if node.has_meta(PINNED_META) else str(node.name)
	if id == target:
		return node
	for child in node.get_children():
		var found := _find_recursive(child, target)
		if found != null:
			return found
	return null


func _mouse_button(viewport: Viewport, pos: Vector2, pressed: bool) -> void:
	if viewport == null:
		return
	var ev := InputEventMouseButton.new()
	ev.button_index = MOUSE_BUTTON_LEFT
	ev.pressed = pressed
	ev.position = pos
	ev.global_position = pos
	viewport.push_input(ev)


func _mouse_motion(viewport: Viewport, from: Vector2, to: Vector2) -> void:
	if viewport == null:
		return
	var ev := InputEventMouseMotion.new()
	ev.position = to
	ev.global_position = to
	ev.relative = to - from
	viewport.push_input(ev)
