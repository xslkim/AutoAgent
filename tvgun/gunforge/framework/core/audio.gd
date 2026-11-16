extends Node

var sounds = {}
var players = []
var enabled = true

func _ready():
	for i in range(6):
		var player = AudioStreamPlayer.new()
		player.volume_db = -17
		add_child(player)
		players.append(player)
	for name in ["shot","hit","lamp","rescue","reload","hurt","warning"]:
		var data = PackedByteArray()
		var hz = {"shot":150.0,"hit":490.0,"lamp":660.0,"rescue":880.0,"reload":320.0,"hurt":100.0,"warning":230.0}[name]
		var duration = .10 if name=="shot" else .22
		for i in range(int(22050*duration)):
			var t = i/22050.0
			var envelope = exp(-t*20)
			var sample = sin(t*hz*TAU)*envelope*.4
			if name=="shot":
				sample += sin(t*8713)*sin(t*5209)*envelope*.3
			var value = int(clampf(sample,-1,1)*32767)
			data.append(value & 255)
			data.append((value>>8)&255)
		var stream = AudioStreamWAV.new()
		stream.format = AudioStreamWAV.FORMAT_16_BITS
		stream.mix_rate = 22050
		stream.data = data
		sounds[name] = stream

func cue(name: String):
	if not enabled or not sounds.has(name):
		return
	var player = players.filter(func(p): return not p.playing)
	var chosen = player[0] if not player.is_empty() else players[0]
	chosen.stream = sounds[name]
	chosen.play()
