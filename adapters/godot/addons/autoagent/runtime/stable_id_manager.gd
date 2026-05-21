extends RefCounted
## Runtime API for pinning and unpinning stable AutoAgent IDs on Godot nodes.
##
## Stable IDs authored at design time (metadata/autoagent_pinned_id in .tscn) are
## read automatically by ControlReflector and have stable_id_source = "pinned".
## This class lets runtime code (e.g. a LoginController) register additional IDs
## without touching .tscn files — useful for programmatically created nodes.
##
## Usage:
##   # In an autoload or controller script:
##   StableIdManager.pin(my_button, "login_button_bg")
##   StableIdManager.get_id(my_button)   # → "login_button_bg"
##   StableIdManager.is_pinned(my_button) # → true
##   StableIdManager.unpin(my_button)

const PINNED_META := "autoagent_pinned_id"


## Assign a stable ID to `node`.  Overwrites any previously assigned ID.
static func pin(node: Node, id: String) -> void:
	if id.is_empty():
		push_warning("[AutoAgent] StableIdManager.pin() called with empty id on %s" % node.name)
		return
	node.set_meta(PINNED_META, id)


## Remove the pinned ID from `node`.  No-op if the node has no pinned ID.
static func unpin(node: Node) -> void:
	if node.has_meta(PINNED_META):
		node.remove_meta(PINNED_META)


## Return the pinned ID of `node`, or an empty string if not pinned.
static func get_id(node: Node) -> String:
	if node.has_meta(PINNED_META):
		return str(node.get_meta(PINNED_META))
	return ""


## Return true if `node` has a pinned stable ID.
static func is_pinned(node: Node) -> bool:
	return node.has_meta(PINNED_META)


## Bulk-pin a Dictionary {node: id} in one call.
## Useful for a controller's _ready() to register all managed widgets at once.
static func pin_all(mapping: Dictionary) -> void:
	for node in mapping:
		if node is Node:
			pin(node, str(mapping[node]))
