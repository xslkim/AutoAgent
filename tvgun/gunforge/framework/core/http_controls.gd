extends RefCounted

# Compatibility for the Android client's saved HTTP event mode.
var server = TCPServer.new()
var clients = []
var callback: Callable
var bind_error = OK

func open(port: int, handler: Callable):
	callback = handler
	bind_error = server.listen(port,"0.0.0.0")

func close():
	for client in clients:
		client.peer.disconnect_from_host()
	clients.clear()
	server.stop()

func respond(client: Dictionary, code: int, result: Dictionary):
	var body = JSON.stringify(result).to_utf8_buffer()
	var title = "OK" if code==200 else "Bad Request" if code==400 else "Not Found"
	var header = "HTTP/1.1 %d %s\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: %d\r\nConnection: close\r\nCache-Control: no-store\r\n\r\n" % [code,title,body.size()]
	client.peer.put_data(header.to_utf8_buffer())
	client.peer.put_data(body)
	clients.erase(client)

func poll():
	while server.is_connection_available():
		var peer = server.take_connection()
		if clients.size()>=16:
			peer.disconnect_from_host()
		else:
			clients.append({"peer":peer,"buffer":PackedByteArray(),"at":Time.get_ticks_msec()})
	for client in clients.duplicate():
		var peer = client.peer
		peer.poll()
		if peer.get_status()!=StreamPeerTCP.STATUS_CONNECTED or Time.get_ticks_msec()-client.at>5000:
			peer.disconnect_from_host()
			clients.erase(client)
			continue
		if client.get("pending",false):
			continue
		if peer.get_available_bytes()>0:
			var received = peer.get_data(peer.get_available_bytes())
			if received[0]!=OK:
				clients.erase(client)
				continue
			client.buffer.append_array(received[1])
		if client.buffer.size()>16384:
			respond(client,400,{"ok":false})
			continue
		var text = client.buffer.get_string_from_utf8()
		var boundary = text.find("\r\n\r\n")
		if boundary<0:
			continue
		var lines = text.substr(0,boundary).split("\r\n")
		var first = lines[0].split(" ")
		var size = 0
		var invalid = first.size()!=3
		for line in lines:
			if line.to_lower().begins_with("content-length:"):
				var value = line.substr(line.find(":")+1).strip_edges()
				invalid = invalid or not value.is_valid_int()
				size = int(value)
			if line.to_lower().begins_with("transfer-encoding:"):
				invalid = true
		if invalid or size<0 or size>4096:
			respond(client,400,{"ok":false})
			continue
		if client.buffer.size()<boundary+4+size:
			continue
		var payload = {}
		if size>0:
			payload = JSON.parse_string(client.buffer.slice(boundary+4,boundary+4+size).get_string_from_utf8())
			if not payload is Dictionary:
				respond(client,400,{"ok":false})
				continue
		if first[0]=="GET" and first[1]=="/state":
			respond(client,200,callback.call("STATE",payload,Callable()))
		elif first[0]=="POST" and first[1] in ["/start","/coin","/reload","/exit","/shot"]:
			if first[1]=="/shot" and (not payload.has("x") or not payload.has("y") or
					not (payload.x is float or payload.x is int) or not (payload.y is float or payload.y is int)):
				respond(client,400,{"ok":false})
			else:
				client.pending = true
				var finish = func(result):
					if clients.has(client):
						respond(client,200,result)
				var result = callback.call(first[1].substr(1).to_upper(),payload,finish)
				if not result.get("deferred",false) and clients.has(client):
					respond(client,200,result)
		else:
			respond(client,404,{"ok":false})
