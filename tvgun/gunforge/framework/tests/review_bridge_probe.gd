extends "res://tools/level_review.gd"
## Comparison harness. The browser reads frames and metadata produced by the native reviewer.

func smoke_test() -> void:
	var timer = Timer.new()
	timer.wait_time = 0.025
	timer.timeout.connect(func(): poll_bridge(timer))
	root.add_child(timer)
	timer.start()

func poll_bridge(timer: Timer) -> void:
	var request_path = evidence_dir.path_join("request.json")
	if not FileAccess.file_exists(request_path):
		return
	timer.stop()
	var request = JSON.parse_string(FileAccess.get_file_as_string(request_path))
	DirAccess.remove_absolute(request_path)
	var result = await run_command(request)
	var response = evidence_dir.path_join("response-" + request.request_id + ".json")
	var file = FileAccess.open(response + ".pending", FileAccess.WRITE)
	file.store_string(JSON.stringify(result))
	file.close()
	DirAccess.rename_absolute(response + ".pending", response)
	timer.start()

func run_command(request: Dictionary) -> Dictionary:
	match request.op:
		"seek":
			jump(clampi(int(request.tick), 0, session.max_tick))
		"inspect":
			var row = event_tree.get_root().get_first_child()
			while row != null and row.get_metadata(0) != request.id:
				row = row.get_next()
			if row == null:
				return {"error": "找不到该事件"}
			row.select(0)
			select_event()
			return {"details": JSON.parse_string(info.text), "tick": clock.tick, "build_id": model.build.build_id}
		"switch":
			switch_previous()
		"note":
			note.text = request.text
			await save_note("bridge_prototype")
			if not note.text.is_empty():
				return {"error": "批注保存失败"}
			return {"saved": true, "tick": clock.tick, "build_id": model.build.build_id}
	var snapshot = await capture_evidence("bridge-frame")
	if snapshot.is_empty():
		return {"error": "画面保存失败"}
	var hash_context = HashingContext.new()
	hash_context.start(HashingContext.HASH_SHA256)
	hash_context.update(var_to_bytes(Codec.encode(preview.shown, model.geometry_assets())))
	return {
		"tick": clock.tick, "build_id": model.build.build_id,
		"event_ids": model.level.event_order, "state": model.public_state(),
		"pose_sha256": hash_context.finish().hex_encode(), "frame_sha256": snapshot.player.sha256,
	}
