# AUTOAGENT_ALLOW_VISUAL
extends RefCounted
## Executes wire-protocol actions (click / send_text / drag / scroll / key_press)
## on nodes located by their stable id.
##
## input_layer = "engine" (default): events via viewport.push_input.
## input_layer = "os": warps OS cursor via DisplayServer.cursor_set_position(),
##   then injects via Input.parse_input_event() for cross-window visibility.
##
## By default nodes are searched in the active scene; tests may set
## `search_root` to point the driver at an explicit subtree.

const PINNED_META := "autoagent_pinned_id"

var search_root: Node = null


func click(node_id, input_layer := "engine") -> bool:
	var node := _find(node_id)
	if node == null:
		return false
	if node is Control:
		var ctrl := node as Control
		if ctrl.mouse_filter == Control.MOUSE_FILTER_IGNORE:
			return false
	if node is BaseButton:
		(node as BaseButton).pressed.emit()
		return true
	if node is Control:
		var center := (node as Control).get_global_rect().get_center()
		if input_layer == "os":
			_os_warp_cursor(center)
		var vp := (node as Control).get_viewport()
		_viewport_click(vp, center)
		return true
	return false


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


func drag(from_id, to_id, input_layer := "engine") -> bool:
	var src := _find(from_id)
	var dst := _find(to_id)
	if src == null or dst == null or not (src is Control) or not (dst is Control):
		return false
	var a := (src as Control).get_global_rect().get_center()
	var b := (dst as Control).get_global_rect().get_center()
	if input_layer == "os":
		_os_warp_cursor(a)
	var vp := (src as Control).get_viewport()
	_viewport_drag(vp, a, b)
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


## Send a key-press event to a widget.
## Supported keys: Enter/Return/Submit, Escape/Esc/Cancel, Tab, Shift+Tab.
func key_press(node_id, key: String, input_layer := "engine") -> bool:
	var node := _find(node_id)
	if node == null:
		return false

	var k := key.to_lower().strip_edges()

	# Build an InputEventKey for the given keycode + pressed state.
	var _make_key := func(kc: Key, pressed: bool, shift := false) -> InputEventKey:
		var ev := InputEventKey.new()
		ev.keycode = kc
		ev.pressed = pressed
		ev.shift_pressed = shift
		return ev

	var events: Array[InputEventKey] = []
	match k:
		"enter", "return", "submit":
			events = [_make_key(KEY_ENTER, true), _make_key(KEY_ENTER, false)]
		"escape", "esc", "cancel":
			events = [_make_key(KEY_ESCAPE, true), _make_key(KEY_ESCAPE, false)]
		"tab":
			events = [_make_key(KEY_TAB, true), _make_key(KEY_TAB, false)]
		"shifttab", "shift+tab":
			events = [
				_make_key(KEY_SHIFT, true, true),
				_make_key(KEY_TAB, true, true),
				_make_key(KEY_TAB, false, true),
				_make_key(KEY_SHIFT, false, false),
			]
		_:
			return false

	if input_layer == "os":
		_os_warp_cursor((node as Control).get_global_rect().get_center() if node is Control else Vector2.ZERO)

	for ev in events:
		Input.parse_input_event(ev)
	return true


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


func _viewport_click(vp: Viewport, pos: Vector2) -> void:
	_mouse_button(vp, pos, true)
	_mouse_button(vp, pos, false)


func _viewport_drag(vp: Viewport, a: Vector2, b: Vector2) -> void:
	_mouse_button(vp, a, true)
	_mouse_motion(vp, a, b)
	_mouse_button(vp, b, false)


func _os_warp_cursor(pos: Vector2) -> void:
	DisplayServer.cursor_set_position(pos)


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
