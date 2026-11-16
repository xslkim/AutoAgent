extends RefCounted

var aim = Vector2.ZERO
var valid = false
var grade = 0
var last_aim = -100.0
var last_packet = -100.0
var largest_aim = -1
var shot_sequences = {}
var session = 0
var source = ""
var rejected = 0
var transport: PacketPeerUDP
var discovery: Array[PacketPeerUDP] = []
var peer_ip = ""
var peer_port = 0
var last_frame_sent = -100.0
var bind_errors = []
var port = 9000
var session_token = ""
var last_loss_sequence = -1
var retired_sessions = []

func open(game_port = 9000, discovery_ports: Array[int] = [8001]):
	port = game_port
	transport = PacketPeerUDP.new()
	bind(transport, game_port)
	for discovery_port in discovery_ports:
		var socket := PacketPeerUDP.new()
		if bind(socket, discovery_port):
			discovery.append(socket)

func bind(socket: PacketPeerUDP, local_port: int) -> bool:
	var error := socket.bind(local_port, "0.0.0.0")
	if error != OK:
		bind_errors.append({"port":local_port,"error":error})
	return error == OK

func close():
	if transport:
		transport.close()
	for socket in discovery:
		socket.close()
	discovery.clear()

func reset_session():
	largest_aim = -1
	shot_sequences.clear()
	valid = false
	last_aim = -100
	last_loss_sequence = -1
	session += 1

func decode(text: String, now: float, sender = "test") -> Array:
	var out = []
	if text.length() > 160:
		rejected += 1
		return out
	if sender != source or now-last_packet >= 2.0:
		reset_session()
		source = sender
	last_packet = now
	text = text.strip_edges()
	if text.begins_with("HELLO "):
		var token = text.substr(6)
		if token.length()<8 or retired_sessions.has(token):
			return []
		if token!=session_token:
			if not session_token.is_empty():
				retired_sessions.append(session_token)
				if retired_sessions.size()>16:
					retired_sessions.pop_front()
			reset_session()
			session_token = token
			last_frame_sent = -100
		return []
	if text in ["START", "COIN", "RELOAD", "EXIT"]:
		return [{"event":text}]
	var shot = text.begins_with("SHOT ")
	var lost = text.begins_with("LOST,")
	var tokens = (text.substr(5) if shot else text).split(",")
	if text == "SHOT":
		if valid and now-last_aim <= .100:
			return [{"event":"SHOT","aim":aim,"grade":grade}]
		return []
	if lost:
		if tokens.size() != 2 or not tokens[1].is_valid_int():
			return []
		var seq = int(tokens[1])
		if seq <= largest_aim:
			return []
		largest_aim = seq
		last_loss_sequence = seq
		valid = false
		grade = 0
		return [{"event":"LOST"}]
	if tokens.size() not in [2,3,4] or (shot and tokens.size()!=3):
		rejected += 1
		return []
	if not tokens[0].is_valid_float() or not tokens[1].is_valid_float():
		return []
	var point = Vector2(float(tokens[0]),float(tokens[1]))
	if not is_finite(point.x) or not is_finite(point.y) or point.length()>100000:
		return []
	var seq = -1
	if tokens.size()>=3:
		var last = tokens[-1]
		if not last.is_valid_int() or int(last)<0:
			return []
		seq = int(last)
	if shot:
		if not valid or now-last_aim > .6 or shot_sequences.has(seq) or seq<=last_loss_sequence:
			return []
		shot_sequences[seq] = true
		if shot_sequences.size()>512:
			shot_sequences.erase(shot_sequences.keys()[0])
		return [{"event":"SHOT","aim":point,"grade":grade}]
	if tokens.size()==3 or seq!=-1 and seq<=largest_aim:
		return []
	var new_grade = 4
	if tokens.size()==4:
		if not tokens[2].is_valid_int() or int(tokens[2]) not in [1,2,3,4]:
			return []
		new_grade = int(tokens[2])
	if seq!=-1:
		largest_aim = seq
	aim = point
	grade = new_grade
	valid = true
	last_aim = now
	return [{"event":"AIM","aim":aim,"grade":grade}]

func poll(now: float, white: float, dark: float) -> Array:
	var events = []
	while transport and transport.get_available_packet_count()>0:
		var bytes = transport.get_packet()
		peer_ip = transport.get_packet_ip()
		peer_port = transport.get_packet_port()
		events.append_array(decode(bytes.get_string_from_ascii(), now, peer_ip))
	for socket in discovery:
		while socket.get_available_packet_count()>0:
			var text := socket.get_packet().get_string_from_ascii()
			if text == "TVGUN_DISCOVER":
				socket.set_dest_address(socket.get_packet_ip(),socket.get_packet_port())
				socket.put_packet(("TVGUN_HERE %d" % port).to_ascii_buffer())
	if peer_port and now-last_frame_sent>=2:
		transport.set_dest_address(peer_ip,peer_port)
		transport.put_packet(("FRAME %d,%d" % [white,dark]).to_ascii_buffer())
		last_frame_sent = now
	if valid and now-last_aim>.6:
		valid = false
		last_loss_sequence = largest_aim
		events.append({"event":"LOST"})
	return events
