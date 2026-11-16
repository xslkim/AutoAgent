extends "train_stop_probe.gd"
## Play through the battle and sample the camera motion in the shared renderer.

const INSIDE := "pullback.interior"
const OUTSIDE := "pullback.exterior"
const VIEW := Rect2(0, 0, 1776, 936)
const ORIGINS := {INSIDE: Vector2(888, 723), OUTSIDE: Vector2(281, 827)}
const STILLS := {15: "pullback_approach", 51: "pullback_inside_rim", 63: "pullback_match_cut",
	70: "pullback_paper_lantern", 116: "pullback_widening", 155: "pullback_workbench"}

var cuts: Array[Dictionary] = []
var captured: Array[String] = []

func check_camera_plane(id: String) -> void:
	var plane: Dictionary = model.entities[id]
	if not plane.active or model.active_opacity(plane) <= 0.0:
		return
	var bounds: Rect2 = model.display_transform(plane) * Rect2(0, 0, plane.width, plane.height)
	check(bounds.grow(.02).encloses(VIEW), id + " does not expose the viewport during interpolation")

func check_match_anchor(id: String) -> void:
	var pose: Transform2D = model.display_transform(model.entities[id])
	check((pose * ORIGINS[id]).distance_to(VIEW.get_center()) < 1.0, id + " is centered on its paper rim")

func check_input_locked(ammo: int, shots: int) -> void:
	var response: Dictionary = model.command("SHOT", VIEW.get_center(), model.geometry())
	check(not response.get("ok", false) and response.get("reason") == "not_running", "shot is rejected during pullback")
	check(model.resources.ammo == ammo and model.shots == shots, "cut does not spend ammo or count a shot")

func play() -> void:
	step_to(1100)
	check(model.result == "overrun" and not model.fired.has("pullback.start"), "failed battle does not start the camera cut")
	model.start()
	check(shoot("lantern_base.lamp").get("target") == "lantern_base.lamp", "station lamp activates")
	step_to(184)
	check(shoot("lantern_base.crow").get("target") == "lantern_base.crow", "crow can be purified")
	check(shoot("lantern_base.umbrella").get("target") == "lantern_base.umbrella", "umbrella can be purified")
	check(not model.input_enabled and model.current_section == "lantern_base", "battle clears before the cut")
	await capture("pullback_combat_clear")
	var ammo: int = model.resources.ammo
	var shots: int = model.shots
	var start := -1
	while model.phase == "running" and model.tick < 530:
		var section: String = model.current_section
		model.step()
		var changed: bool = model.current_section != section
		var cold := 0
		if changed and viewport != null:
			cold = uncached_scene_textures()
		if viewport != null:
			await process_frame
			await RenderingServer.frame_post_draw
		if changed:
			var cut := {"section": model.current_section, "tick": model.tick}
			if viewport != null:
				cut["uncached_scene_textures"] = cold
				cut["frame_uploads_including_future_preloads"] = model.render_scene.upload_count
				cut["frame_upload_us"] = model.render_scene.upload_us
				check(cold == 0, "section textures are cached before " + model.current_section)
			cuts.append(cut)
			check_input_locked(ammo, shots)
			if model.current_section == "pullback":
				start = model.tick
		check(not model.input_enabled, "input stays disabled for the entire cut")
		check_camera_plane(INSIDE)
		check_camera_plane(OUTSIDE)
		if start < 0:
			continue
		var elapsed: int = model.tick - start
		if elapsed == 51:
			check_match_anchor(INSIDE)
		elif elapsed == 70:
			check_match_anchor(OUTSIDE)
		if STILLS.has(elapsed):
			var name: String = STILLS[elapsed]
			if viewport != null:
				check(viewport.get_texture().get_image().save_png(captures.path_join(name + ".png")) == OK, "capture " + name)
			captured.append(name)
	check(cuts.size() == 2 and cuts[0].section == "pullback" and cuts[1].section == "workbench", "camera reaches the workbench in order")
	check(captured.size() == STILLS.size(), "all planned camera samples ran")
	check(model.current_section == "workbench" and model.result == "clear", "the standalone preview ends at the workbench")
	check(not model.entities[INSIDE].active and not model.entities[OUTSIDE].active, "native workbench layers replace the camera planes")
	check(model.geometry().all(func(item): return item.kind.is_empty()), "workbench arrival contains no shot targets")
	model.start()
	check(model.current_section == "lantern_base" and model.input_enabled and model.shots == 0, "retry starts from combat without camera residue")

func run() -> void:
	if not open_candidate():
		quit(2)
		return
	if viewport != null:
		viewport.transparent_bg = true
		model.render_scene.measure_uploads = true
	await play()
	print(JSON.stringify({"passed": failures.is_empty(), "failures": failures, "build_id": model.build.build_id,
		"gpu_capture": viewport != null, "cuts": cuts, "camera_samples": captured}))
	quit(0 if failures.is_empty() else 1)
