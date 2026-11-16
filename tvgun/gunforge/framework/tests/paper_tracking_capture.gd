extends "res://tools/level_player.gd"
## Put the verified gallery poses inside the player's actual display frame for C13.

var captures := ""
var destination := ""
var gallery_path := ""
var failures: Array[String] = []
var samples: Array[Dictionary] = []

func capture_frame(id: String, provenance: Dictionary) -> void:
	await process_frame
	await RenderingServer.frame_post_draw
	var image: Image = root.get_texture().get_image()
	var file := id + ".png"
	var target := destination.path_join(file)
	if image.save_png(target) != OK:
		failures.append("cannot save " + file)
		return
	var bounds: Rect2 = frame.screen_rect(root.size)
	samples.append({"id": id, "file": file, "sha256": FileAccess.get_sha256(target), "profile": frame.profile,
		"white_norm_px": frame.white, "dark_norm_px": frame.dark, "outer": frame.outer,
		"window": [image.get_width(), image.get_height()],
		"white_outer_rect": [bounds.position.x, bounds.position.y, bounds.size.x, bounds.size.y],
		"provenance": provenance})

func open() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--gallery-checks="):
			gallery_path = arg.trim_prefix("--gallery-checks=")
		elif arg.begins_with("--gallery-captures="):
			captures = arg.trim_prefix("--gallery-captures=")
		elif arg.begins_with("--tracking-output="):
			destination = arg.trim_prefix("--tracking-output=")
	isolated_settings = true
	super.open()
	if model == null:
		return
	var gallery = JSON.parse_string(FileAccess.get_file_as_string(gallery_path))
	if DisplayServer.get_name() == "headless" or not gallery is Dictionary or gallery.get("build_id") != model.build.build_id \
			or DirAccess.make_dir_recursive_absolute(destination) != OK:
		push_error("C13 capture requires the matching gallery, GPU display and writable output directory")
		quit(2)
		return
	if http.bind_error != OK or not gun.bind_errors.is_empty():
		failures.append("player port unavailable")
	var content := TextureRect.new()
	content.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	content.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	content.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(content)
	preview.hide()
	for profile in ["monitor", "tv"]:
		frame.configure(profile)
		layout()
		content.position = preview.position
		content.size = preview.size
		for name in gallery.frames:
			var source: Dictionary = gallery.frames[name]
			if source.capture.begins_with("display/"):
				continue
			var path := captures.path_join(source.capture + ".png")
			if FileAccess.get_sha256(path) != source.source_png_sha256:
				failures.append("gallery source changed: " + name)
				continue
			var image := Image.load_from_file(path)
			if image == null or image.get_size() != Vector2i(1776, 936):
				failures.append("invalid content frame: " + name)
				continue
			content.texture = ImageTexture.create_from_image(image)
			await capture_frame(profile + "_" + name, {"capture": source.capture, "sha256": source.source_png_sha256})
	content.queue_free()
	preview.show()
	frame.configure("monitor")
	layout()
	open_display_setup()
	await capture_frame("monitor_display_setup", {"ui": "overscan"})
	display_setup.switch_profile()
	await capture_frame("tv_display_setup", {"ui": "overscan"})
	display_setup.begin_calibration()
	await capture_frame("tv_calibration_target", {"ui": "calibration"})
	display_setup.finish(false)
	if opening != null:
		enqueue_device({"event": "START"})
		var timeout := Time.get_ticks_msec() + 5000
		while opening.subtitle.text.is_empty() and Time.get_ticks_msec() < timeout:
			await process_frame
		if opening.visible and not opening.subtitle.text.is_empty():
			for profile in ["monitor", "tv"]:
				frame.configure(profile)
				layout()
				await capture_frame(profile + "_opening", {"cinematic": "opening", "subtitle": opening.subtitle.text})
		else:
			failures.append("opening never displayed its first caption")
	else:
		failures.append("opening media unavailable")
	var evidence := {"build_id": model.build.build_id, "gallery_checks_sha256": FileAccess.get_sha256(gallery_path),
		"passed": failures.is_empty(), "failures": failures, "samples": samples}
	var manifest := FileAccess.open(destination.path_join("frames.json"), FileAccess.WRITE)
	if manifest == null:
		quit(2)
		return
	manifest.store_string(JSON.stringify(evidence) + "\n")
	print(JSON.stringify({"build_id": model.build.build_id, "samples": samples.size(),
		"passed": failures.is_empty(), "failures": failures}))
	gun.close()
	http.close()
	quit(0 if failures.is_empty() else 1)
