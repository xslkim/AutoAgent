@tool
extends EditorPlugin
## Registers the AutoAgent runtime as an autoload singleton when the plugin is
## enabled, so the wire-protocol server starts whenever the project runs.
##
## Also adds an "AutoAgent" menu in the editor toolbar with:
##   • "Scan for Unpinned Nodes" — lists all Control nodes in the current scene
##     that have no autoagent_pinned_id metadata (mirrors TASK-0205 UE editor tool).

const AUTOLOAD_NAME := "AutoAgent"
const AUTOLOAD_PATH := "res://addons/autoagent/runtime/autoagent.gd"
const PINNED_META := "autoagent_pinned_id"


func _enter_tree() -> void:
	add_autoload_singleton(AUTOLOAD_NAME, AUTOLOAD_PATH)
	add_tool_menu_item("AutoAgent: Scan Unpinned Nodes", _scan_unpinned)


func _exit_tree() -> void:
	remove_tool_menu_item("AutoAgent: Scan Unpinned Nodes")
	remove_autoload_singleton(AUTOLOAD_NAME)


## Scans the current edited scene for Control nodes without a pinned stable ID.
## Results are printed to the Godot Output panel and the OS terminal.
func _scan_unpinned() -> void:
	var scene_root := EditorInterface.get_edited_scene_root()
	if scene_root == null:
		push_warning("[AutoAgent] No scene open — open a scene before scanning.")
		print("[AutoAgent] No scene open.")
		return

	var unpinned: Array[String] = []
	_collect_unpinned(scene_root, unpinned)

	if unpinned.is_empty():
		print("[AutoAgent] All Control nodes are pinned. ✓")
	else:
		print("[AutoAgent] %d unpinned Control node(s) found:" % unpinned.size())
		for path in unpinned:
			print("  • %s" % path)
		print(
			"[AutoAgent] Add metadata/autoagent_pinned_id to each node "
			"or call StableIdManager.pin(node, 'my_id') at runtime."
		)


func _collect_unpinned(node: Node, out: Array[String]) -> void:
	if node is Control and not node.has_meta(PINNED_META):
		out.append(str(node.get_path()))
	for child in node.get_children():
		_collect_unpinned(child, out)
