extends Node
## Presentation follows serialized cue envelopes; seek suppresses past one-shots.
var model
var root_path=""
var players={}
var heard={}
var enabled=false
func setup(runtime,assets):model=runtime;root_path=assets
func clear():
	for player in players.values():player.stop();player.stream=null;player.queue_free()
	players.clear();heard.clear()
func sync(seeking=false):
	if model==null or not "active_cues" in model:return
	if seeking:clear()
	for id in players.keys():
		if not enabled or not model.active_cues.has(id):players[id].stop();players[id].stream=null;players[id].queue_free();players.erase(id)
	if not enabled:return
	for id in model.active_cues:
		var instance=model.active_cues[id]
		if seeking and not instance.loop:heard[id]=true;continue
		if heard.has(id) or players.has(id):continue
		var cue=model.level.cues[instance.cue]
		var resource=model.level.resources[cue.resource]
		var stream=AudioStreamWAV.load_from_file(root_path.path_join(resource.path))
		if stream==null:push_error("Audio asset cannot be decoded: "+resource.path);continue
		if instance.loop:
			stream.loop_mode=AudioStreamWAV.LOOP_FORWARD;stream.loop_end=stream.data.size()/(2 if stream.format==AudioStreamWAV.FORMAT_16_BITS else 1)/(2 if stream.stereo else 1)
		var player=AudioStreamPlayer.new();add_child(player);player.stream=stream;player.volume_db=cue.get("volume_db",-17)
		var seconds=(model.tick-instance.start_tick)/float(model.level.tick_hz)
		player.play(fmod(seconds,stream.get_length()) if instance.loop else seconds)
		players[id]=player;heard[id]=true
