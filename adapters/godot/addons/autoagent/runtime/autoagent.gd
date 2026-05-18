extends Node
## AutoAgent runtime entry point (autoload singleton).
##
## Starts the WebSocket wire-protocol server on startup and polls it every
## frame. Godot's WebSocketPeer is non-blocking, so the whole adapter runs on
## the main thread — no background threads or cross-thread queues needed.

const WebSocketServer := preload("server/websocket_server.gd")

var _server


func _ready() -> void:
	_server = WebSocketServer.new()
	_server.start()


func _process(_delta: float) -> void:
	if _server != null:
		_server.poll()


func _exit_tree() -> void:
	if _server != null:
		_server.stop()
		_server = null
