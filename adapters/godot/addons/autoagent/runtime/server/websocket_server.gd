extends RefCounted
## Minimal multi-client WebSocket server for the AutoAgent wire protocol.
##
## Non-blocking: poll() must be called every frame (from the autoload). Godot's
## WebSocketPeer handles the HTTP upgrade + subprotocol handshake internally.

const ProtocolHandler := preload("protocol_handler.gd")

const PORT := 27842
const BIND_ADDRESS := "127.0.0.1"
const SUBPROTOCOL := "autoagent.v1"

var _tcp: TCPServer
var _peers: Array[WebSocketPeer] = []
var _handler


func start() -> void:
	_handler = ProtocolHandler.new()
	_tcp = TCPServer.new()
	var err := _tcp.listen(PORT, BIND_ADDRESS)
	if err != OK:
		push_error("[AutoAgent] cannot listen on %s:%d (error %d)" % [BIND_ADDRESS, PORT, err])
		_tcp = null
		return
	print("[AutoAgent] WebSocket server listening on ws://%s:%d" % [BIND_ADDRESS, PORT])


func stop() -> void:
	for ws in _peers:
		ws.close()
	_peers.clear()
	if _tcp != null:
		_tcp.stop()
		_tcp = null


func poll() -> void:
	if _tcp == null:
		return

	# Accept any pending TCP connections and start their WebSocket handshake.
	while _tcp.is_connection_available():
		var conn := _tcp.take_connection()
		var ws := WebSocketPeer.new()
		ws.supported_protocols = PackedStringArray([SUBPROTOCOL])
		ws.accept_stream(conn)
		_peers.append(ws)

	# Service connected peers.
	var keep: Array[WebSocketPeer] = []
	for ws in _peers:
		ws.poll()
		var state := ws.get_ready_state()
		if state == WebSocketPeer.STATE_CONNECTING:
			keep.append(ws)
		elif state == WebSocketPeer.STATE_OPEN:
			# Reject any client that did not negotiate the required subprotocol.
			if ws.get_selected_protocol() != SUBPROTOCOL:
				ws.close(1002, "subprotocol required: " + SUBPROTOCOL)
				continue
			while ws.get_available_packet_count() > 0:
				var msg := ws.get_packet().get_string_from_utf8()
				ws.send_text(_handler.dispatch(msg))
			keep.append(ws)
		# STATE_CLOSING / STATE_CLOSED → drop the peer.
	_peers = keep
