extends Node
## GUT-free headless self-test for engine_input_driver.gd.
##
## Verifies the four wire-protocol input actions (click / send_text / scroll /
## drag) against real Godot widgets. No third-party test framework — works on
## any Godot build and is CI-friendly.
##
## Run from the editor: open headless_input_test.tscn and press F6.
## Run headless (CI):
##   godot --headless --path fixtures/godot-test-project \
##       res://addons/autoagent/tests/headless_input_test.tscn

const EngineInputDriver := preload(
	"res://addons/autoagent/runtime/input/engine_input_driver.gd")

var _passed := 0
var _failed := 0


func _ready() -> void:
	print("AutoAgent — Godot input driver headless self-test")
	await _run_tests()
	print("\n%d passed, %d failed" % [_passed, _failed])
	if _failed == 0:
		print("ALL CHECKS PASSED")
	get_tree().quit(0 if _failed == 0 else 1)


func _run_tests() -> void:
	var root := Control.new()
	root.name = "test_root"
	root.size = Vector2(1000, 700)
	add_child(root)

	var driver := EngineInputDriver.new()
	driver.search_root = root

	# Let the layout settle so global rects are valid.
	await get_tree().process_frame
	await get_tree().process_frame

	await _test_click(root, driver)
	await _test_send_text(root, driver)
	await _test_scroll(root, driver)
	await _test_drag(root, driver)


func _test_click(root: Control, driver) -> void:
	var button := Button.new()
	button.name = "test_button"
	button.position = Vector2(100, 100)
	button.size = Vector2(200, 60)
	root.add_child(button)
	var fired := [false]
	button.pressed.connect(func() -> void: fired[0] = true)
	await get_tree().process_frame

	var ok: bool = driver.click("test_button")
	await get_tree().process_frame

	_check("click returns true", ok)
	_check("click triggers pressed signal", fired[0])
	_check("click on missing node returns false", not driver.click("no_such_node"))


func _test_send_text(_root: Control, driver) -> void:
	var line_edit := LineEdit.new()
	line_edit.name = "test_input"
	_root.add_child(line_edit)
	await get_tree().process_frame

	var ok: bool = driver.send_text("test_input", "hello@test.com")
	_check("send_text returns true", ok)
	_check("send_text sets LineEdit.text", line_edit.text == "hello@test.com")


func _test_scroll(_root: Control, driver) -> void:
	var scroller := ScrollContainer.new()
	scroller.name = "test_scroller"
	scroller.position = Vector2(0, 300)
	scroller.size = Vector2(300, 200)
	_root.add_child(scroller)
	var content := Control.new()
	content.custom_minimum_size = Vector2(280, 2000)
	scroller.add_child(content)
	await get_tree().process_frame

	var ok: bool = driver.scroll("test_scroller", 0.0, 80.0)
	_check("scroll returns true", ok)
	_check("scroll changes scroll_vertical", scroller.scroll_vertical == 80)


func _test_drag(_root: Control, driver) -> void:
	var a := Control.new()
	a.name = "drag_a"
	a.position = Vector2(400, 100)
	a.size = Vector2(80, 80)
	var b := Control.new()
	b.name = "drag_b"
	b.position = Vector2(600, 100)
	b.size = Vector2(80, 80)
	_root.add_child(a)
	_root.add_child(b)
	await get_tree().process_frame

	_check("drag between two controls returns true", driver.drag("drag_a", "drag_b"))
	_check("drag with missing target returns false", not driver.drag("drag_a", "no_such"))


func _check(label: String, condition: bool) -> void:
	if condition:
		_passed += 1
		print("  [PASS] " + label)
	else:
		_failed += 1
		print("  [FAIL] " + label)
