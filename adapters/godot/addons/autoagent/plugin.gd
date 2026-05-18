@tool
extends EditorPlugin
## Registers the AutoAgent runtime as an autoload singleton when the plugin is
## enabled, so the wire-protocol server starts whenever the project runs.

const AUTOLOAD_NAME := "AutoAgent"
const AUTOLOAD_PATH := "res://addons/autoagent/runtime/autoagent.gd"


func _enter_tree() -> void:
	add_autoload_singleton(AUTOLOAD_NAME, AUTOLOAD_PATH)


func _exit_tree() -> void:
	remove_autoload_singleton(AUTOLOAD_NAME)
