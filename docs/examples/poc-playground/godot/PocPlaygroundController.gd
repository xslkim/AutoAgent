# AUTOAGENT_ALLOW_VISUAL: highlight modulates color, Button wrapper repositions child,
# and show/hide toggles visible. These are test/reference fixtures — not product changes.
extends CanvasLayer
## Interactive card-panel controller for the poc_playground scene.
##
## AI-written by Claude Code during autonomous loop (TASK POC-PLAYGROUND-001).

# ------------------------------------------------------------------ nodes
@onready var _click_targets: Array = []
@onready var _text_target: TextureRect = $text_target
@onready var _text_label: Label = $text_target/text_target_text
@onready var _line_edit: LineEdit = null
@onready var _api: Node = null

# ------------------------------------------------------------------ state
var _selected_index: int = -1
var _default_modulate: Color = Color.WHITE
var _highlight_modulate: Color = Color(1.0, 0.85, 0.3, 1.0)

# ------------------------------------------------------------------ lifecycle

func _ready() -> void:
	_find_click_targets()
	_attach_buttons()
	_attach_input_field()

# ------------------------------------------------------------------ click targets

func _find_click_targets() -> void:
	var ids := ["click_target",
		"click_target_variant_1", "click_target_variant_2",
		"click_target_variant_3", "click_target_variant_4",
		"click_target_variant_5"]
	for id in ids:
		var node := get_node_or_null(str("/root/PocPlaygroundScene/", id))
		if node and node is TextureRect:
			_click_targets.append(node)
			if _default_modulate == Color.WHITE:
				_default_modulate = node.modulate

func _attach_buttons() -> void:
	for i in _click_targets.size():
		var rect := _click_targets[i] as TextureRect
		rect.mouse_filter = Control.MOUSE_FILTER_STOP
		# Wrap in a Button so the framework can inject clicks via pressed signal.
		var btn := Button.new()
		btn.name = rect.name + "_btn"
		btn.flat = true
		btn.size = rect.size
		btn.position = rect.position
		rect.replace_by(btn)
		rect.position = Vector2.ZERO
		btn.add_child(rect)
		_click_targets[i] = rect

		var idx := i
		btn.pressed.connect(func(): _on_click_target(idx))

func _on_click_target(index: int) -> void:
	if _selected_index >= 0 and _selected_index < _click_targets.size():
		(_click_targets[_selected_index] as TextureRect).modulate = _default_modulate
	_selected_index = index
	if index >= 0 and index < _click_targets.size():
		(_click_targets[index] as TextureRect).modulate = _highlight_modulate

# ------------------------------------------------------------------ text input + filter

func _attach_input_field() -> void:
	if not _text_target:
		return
	_line_edit = LineEdit.new()
	_line_edit.name = "text_input"
	_line_edit.size = _text_target.size
	_line_edit.position = Vector2.ZERO
	_text_target.add_child(_line_edit)
	_line_edit.text_changed.connect(_on_filter_text_changed)

func _on_filter_text_changed(text: String) -> void:
	var lower := text.to_lower()
	for i in _click_targets.size():
		var rect := _click_targets[i] as TextureRect
		var btn := rect.get_parent()
		if btn is Button:
			var match := lower.is_empty() or rect.name.to_lower().contains(lower)
			btn.visible = match
