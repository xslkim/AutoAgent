extends SceneTree
## Play the campaign through the shared input queue without resetting the session.

const Loader = preload("res://core/level_loader.gd")
const Session = preload("res://core/level_session.gd")
const STAGES = ["alley", "stall", "video_shop", "footbridge", "plaza"]
const CINEMA_STAGES = ["ticket_office", "poster_hall", "auditorium", "projection_booth", "screen_stage"]
const TRAIN_STAGES = ["waiting_room", "platform", "green_car", "lantern_base", "workbench"]
const ENDING_LIGHT := "lantern_base.ending_light"
const ENDING_CITY := "lantern_base.ending_city"
const ENDING_CITY_VIEW := "lantern_base.ending.city_view"
const ENDING_WIDE := "lantern_base.ending_wide"
const ENDING_WIDE_VIEW := "lantern_base.ending.wide_view"
const ENDING_TAPE := "lantern_base.ending.tape"
const ENDING_QUOTE := "lantern_base.ending_quote"
const ENDING_PAPER := "lantern_base.ending.paper"
var model
var stages: Array = []
var combined := false
var full_campaign := false
var session = Session.new()
var failures: Array[String] = []
var reached: Array[int] = []
var handoffs: Array = []
var viewport: SubViewport
var captures := ""
var profile_path := ""
var recording_path := ""
var profile_last_frame_us := 0
var profile_open_us := 0
var profile_samples: Array[Dictionary] = []
var profile_texture_sizes: Dictionary = {}
var profile_ui_texture_bytes := 0
var profile_last_texture_ids: Array = []
var profile_last_section := ""
var screen_entry_tick := -1
var failure_retries: Array[Dictionary] = []
var previous_pose: Array = []
var previous_point: Variant
var checked_old_shot := false
var chapter_pose: Array = []
var chapter_point: Variant
var checked_chapter_shot := false
var chapter_tick := -1
var cinema_pose: Array = []
var cinema_point: Variant
var checked_cinema_shot := false
var train_chapter_tick := -1
var pullback_tick := -1
var ending_tick := -1
var city_tick := -1
var wide_tick := -1
var quote_tick := -1
var ending_counters := {}
var city_pan_start := Vector2.ZERO
var city_texture_preloaded := false
var wide_texture_preloaded := false
var campaign_replay := {}
var reloads := 0

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, label: String) -> void:
	if not value:
		failures.append(label)

func station() -> int:
	return int(model.level.sections.get(model.current_section, {}).get("station", 0))

func carried() -> Dictionary:
	return {"lives": model.resources.lives, "ammo": model.resources.ammo, "score": model.resources.score,
		"rescued": model.resources.rescued, "shots": model.shots}

func aim(item, pose: Array) -> Variant:
	var area: Rect2 = item.bounds().intersection(Rect2(0, 0, 1776, 936))
	var middle := area.get_center()
	if model.resolver.exact(middle, pose).get("id") == item.id:
		return middle
	for y in range(ceili(area.position.y), floori(area.end.y), 7):
		for x in range(ceili(area.position.x), floori(area.end.x), 7):
			var point := Vector2(x, y)
			if model.resolver.exact(point, pose).get("id") == item.id:
				return point
	return null

func capture(name: String) -> void:
	if captures.is_empty() or viewport == null:
		return
	await process_frame
	await RenderingServer.frame_post_draw
	check(viewport.get_texture().get_image().save_png(captures.path_join(name + ".png")) == OK, "capture " + name)

func rgba8_bytes(image: Image) -> int:
	var width := image.get_width()
	var height := image.get_height()
	var bytes := width * height * 4
	if image.has_mipmaps():
		while width > 1 or height > 1:
			width = maxi(1, width >> 1)
			height = maxi(1, height >> 1)
			bytes += width * height * 4
	return bytes

func prepare_texture_accounting() -> void:
	var presentation: Dictionary = model.level.presentation
	var stage_resources: Dictionary = {}
	for layer in presentation.layers.values():
		stage_resources[layer.resource] = true
	var lamp_wipes: Dictionary = presentation.get("bottom_wipes", {})
	var light_sources := {}
	for entity in model.level.entities.values():
		if entity.has("mask_permission"):
			light_sources[entity.mask_permission.source] = true
	for id in lamp_wipes.values():
		light_sources[id] = true
	for id in model.level.entities:
		var entity: Dictionary = model.level.entities[id]
		var beam: bool = id.begins_with("cinema.projector_") and (id.ends_with(".dark") or id.ends_with(".warm"))
		if entity.template != "activation_source" and not lamp_wipes.has(id) and not light_sources.has(id) \
				and not beam and id not in [ENDING_CITY_VIEW, ENDING_WIDE_VIEW]:
			continue
		stage_resources[entity.get("resource", "")] = true
		for part in entity.get("parts", {}).values():
			stage_resources[part.resource] = true
	for id in model.images:
		var image: Image = model.images[id]
		var bytes := rgba8_bytes(image)
		profile_texture_sizes[image.get_instance_id()] = Vector2i(bytes, 0) if stage_resources.has(id) else Vector2i(0, bytes)
	var hud = model.render_scene.paper_hud
	if hud != null:
		var textures: Array = hud.textures.values() + [hud.action_style.texture]
		if not hud.lettering.is_empty():
			textures += [hud.lettering.title, hud.lettering.first_chapter] + hud.lettering.chapters.values()
		var seen := {}
		for texture in textures:
			var id: int = texture.get_instance_id()
			if not seen.has(id):
				profile_ui_texture_bytes += rgba8_bytes(texture.get_image())
				seen[id] = true

func sample_rendered_frame() -> void:
	await process_frame
	await RenderingServer.frame_post_draw
	var frame_us := Time.get_ticks_usec()
	var scene = model.render_scene
	var resident_ids: Array = scene.textures.keys()
	var current_ids: Array = resident_ids.duplicate()
	for id in scene.preloaded_textures:
		if not scene.textures.has(id):
			current_ids.append(id)
	if profile_last_frame_us > 0:
		var resident := Vector2i.ZERO
		for id in resident_ids:
			resident += profile_texture_sizes[id]
		var preloaded := Vector2i.ZERO
		for id in scene.preloaded_textures:
			if not scene.textures.has(id):
				preloaded += profile_texture_sizes[id]
		var handoff_bytes := 0
		if profile_last_section != model.current_section:
			handoff_bytes = resident.x + resident.y + preloaded.x + preloaded.y + profile_ui_texture_bytes
			for id in profile_last_texture_ids:
				if not current_ids.has(id):
					var bytes: Vector2i = profile_texture_sizes[id]
					handoff_bytes += bytes.x + bytes.y
		profile_samples.append({
			"tick": model.tick,
			"section": model.current_section,
			"station": station(),
			"frame_us": frame_us - profile_last_frame_us,
			"process_us": roundi(Performance.get_monitor(Performance.TIME_PROCESS) * 1000000),
			"texture_bytes": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED),
			"video_bytes": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_VIDEO_MEM_USED),
			"draw_calls": RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
			"cached_textures": scene.textures.size(),
			"stage_texture_bytes": resident.x,
			"actor_prop_texture_bytes": resident.y,
			"preloaded_section": scene.preloaded_section,
			"preloaded_textures": scene.preloaded_textures.size(),
			"preloaded_stage_texture_bytes": preloaded.x,
			"preloaded_actor_prop_texture_bytes": preloaded.y,
			"handoff_asset_upper_bound_bytes": handoff_bytes,
			"texture_upload_count": scene.upload_count,
			"texture_upload_us": scene.upload_us,
		})
	profile_last_frame_us = frame_us
	profile_last_texture_ids = current_ids
	profile_last_section = model.current_section

func write_profile() -> void:
	var report := FileAccess.open(profile_path, FileAccess.WRITE)
	check(report != null, "write frame profile")
	if report == null:
		return
	var sweep_spawns: Array = model.trace.filter(func(entry):
		return entry.topic == "entity.spawned" and entry.entity.begins_with("cinema.sweep_tape_"))
	check(not combined or sweep_spawns.size() == 3, "profile exercises all three projector spawns")
	report.store_string(JSON.stringify({
		"build_id": model.build.build_id,
		"gpu": RenderingServer.get_video_adapter_name(),
		"rendering_method": RenderingServer.get_current_rendering_method(),
		"viewport": [viewport.size.x, viewport.size.y],
		"window": [root.size.x, root.size.y],
		"open_us": profile_open_us,
		"asset_accounting": "rgba8_with_mipmaps",
		"effects_ui_texture_bytes": profile_ui_texture_bytes,
		"screen_sweep_spawns": sweep_spawns,
		"samples": profile_samples,
	}) + "\n")

func check_texture_restart() -> void:
	if combined:
		session.seek(screen_entry_tick - 20)
		await process_frame
		await RenderingServer.frame_post_draw
		check(station() == 9 and model.render_scene.preloaded_section == "cinema.screen_stage"
			and not model.render_scene.preloaded_textures.is_empty(), "seeking into the handoff preloads the screen")
		session.seek(screen_entry_tick - 120)
		await process_frame
		await RenderingServer.frame_post_draw
		check(station() == 9 and model.render_scene.preloaded_textures.is_empty(),
			"seeking back before the hold releases the pending screen textures")
		session.seek(screen_entry_tick - 20)
		await process_frame
		await RenderingServer.frame_post_draw
	session.start()
	await process_frame
	await RenderingServer.frame_post_draw
	check(station() == 1 and model.resources.lives == 5, "restart resets to the alley")
	var visible: Dictionary = {}
	for item in model.visual_items():
		visible[item.image.get_instance_id()] = true
	var cached: Dictionary = model.render_scene.textures
	check(cached.size() == visible.size() and cached.keys().all(func(id): return visible.has(id)),
		"restart retains only textures used by the alley opening")
	check(model.render_scene.preloaded_textures.is_empty(), "restart clears pending textures")

func retry_from_defeat(expected_station: int) -> void:
	var defeated := carried()
	var defeat_tick: int = model.tick
	check(station() == expected_station and model.phase == "result" and model.result == "overrun"
		and model.resources.lives == 0, "station %d reaches the defeated result" % expected_station)
	if model.phase != "result":
		return
	session.submit(model.geometry())
	check(session.enqueue("SHOT", Vector2(2, 2)) and session.enqueue("RELOAD"), "submit controls at result")
	session.step()
	check(session.last_results.size() == 2 and session.last_results.all(func(reply): return reply.get("reason") == "not_running")
		and carried() == defeated, "result rejects shooting and reload without changing counters")
	session.start()
	var restarted := carried()
	check(station() == 1 and model.phase == "running" and model.tick == 0
		and model.resources == model.level.initial_resources and model.shots == 0,
		"retry returns to the alley with initial player and station counters")
	check(not model.entities["flow.cinema"].active and session.submission.is_empty()
		and session.queue.pending.is_empty() and session.tape.is_empty(), "retry clears prior station and input state")
	if full_campaign:
		check(not model.entities["flow.lantern_base"].active and not model.entities["lantern_base.forget.stroke_1"].active,
			"retry clears the workbench and its active phase")
	while model.phase == "running" and not model.input_enabled and model.tick < 300:
		session.step()
	session.submit(model.geometry())
	check(session.enqueue("SHOT", Vector2(2, 2)), "retry accepts a freshly submitted shot")
	session.step()
	check(model.shots == 1 and model.resources.ammo == restarted.ammo - 1, "fresh shot consumes exactly one round")
	failure_retries.append({"station": expected_station, "defeat_tick": defeat_tick, "before_retry": defeated,
		"after_retry": restarted, "first_shot": carried()})

func check_failure_retries() -> void:
	if full_campaign:
		var workbench: Dictionary = handoffs.back()
		session.seek(workbench.tick)
		check(station() == 15 and not model.input_enabled, "reuse the played route just before the final boss")
		check(session.enqueue("RELOAD"), "branch the recorded playthrough before the ink rises")
		while model.phase == "running" and model.tick < workbench.tick + 1600:
			session.step()
		retry_from_defeat(15)
		return
	var ticket: Dictionary = handoffs[4]
	session.seek(ticket.tick)
	check(station() == 6 and model.resources.lives == 4, "reuse the played route into the cinema")
	# An actual command branches from the saved route so the prior winning shots are no longer replayed.
	check(session.enqueue("RELOAD"), "branch the recorded playthrough at the ticket office")
	while model.phase == "running" and model.resources.lives > 2 and model.tick < ticket.tick + 1000:
		session.step()
	check(station() == 6 and model.resources.lives == 2, "take both ticket-office attacks")
	while station() == 6 and model.phase == "running" and model.tick < ticket.tick + 1600:
		queue_action(6)
		session.step()
	var poster_end: int = model.tick + 1000
	while model.phase == "running" and model.tick < poster_end:
		session.step()
	retry_from_defeat(7)
	session.start()
	while model.phase == "running" and model.tick < 6000:
		session.step()
	retry_from_defeat(1)

func handle_entry(index: int, previous: int, before: Dictionary) -> void:
	reached.append(index)
	var name: String = stages[index - 1]
	var marker := "flow." + name
	if index >= 6 and index <= 10:
		marker = "flow.cinema"
	elif name == "workbench":
		marker = "flow.lantern_base"
	check(model.entities[marker].active, "current station is active")
	if previous > 0:
		var old: String = stages[previous - 1]
		var prefix := old + "."
		if previous >= 6 and previous <= 10:
			prefix = "cinema." + old + "."
		elif name == "workbench":
			prefix = "lantern_base.lantern_base."
		check(carried() == before, "%s preserves player counters across the handoff" % name)
		if previous <= 5:
			check(not model.entities["flow." + old].active, "prior stage events are deactivated")
		check(not model.visual_items().any(func(item): return item.id.begins_with(prefix) or item.id.begins_with("layer." + prefix)),
			"prior targets and layers are removed at the cut")
		handoffs.append({"station": name, "tick": model.tick, "counters": carried()})
	if index == 2:
		check(model.resources["alley.purified"] > 0 and model.resources["stall.purified"] == 0, "stall starts with its own wave counter")
	if index == 6:
		check(chapter_tick >= 0 and model.tick - chapter_tick == 90 and not model.entities["dragon.anchor"].active,
			"chapter transition removes the dragon and opens the ticket office after 1.5 seconds")
	if index == 10:
		screen_entry_tick = model.tick
	if index == 11:
		check(train_chapter_tick >= 0 and model.tick - train_chapter_tick == 90 and not model.entities["flow.cinema"].active,
			"cinema transition opens the waiting room after 1.5 seconds")
	await capture("station_%d_%s" % [index, name])

func queue_action(index: int) -> bool:
	if not model.input_enabled or model.tick < model.next_shot or model.reload_at >= 0:
		return false
	if index == 1 and model.resources.lives == 5 and model.tick < 1260:
		return false # Leave the first attack live so the handoff has a spent life to carry.
	if not profile_path.is_empty() and index == 10 and model.tick - screen_entry_tick < 315:
		return false # Let all three projectors sweep and spawn before clearing the screen.
	if model.resources.ammo == 0:
		if session.enqueue("RELOAD"):
			reloads += 1
		return false
	if index == 2 and not checked_old_shot and previous_point != null:
		session.submit(previous_pose)
		return session.enqueue("SHOT", previous_point)
	if index == 6 and not checked_chapter_shot and chapter_point != null:
		session.submit(chapter_pose)
		return session.enqueue("SHOT", chapter_point)
	if index == 11 and not checked_cinema_shot and cinema_point != null:
		session.submit(cinema_pose)
		return session.enqueue("SHOT", cinema_point)
	var pose: Array = model.geometry()
	var lamp_item = null
	for item in pose:
		if item.kind not in ["primary", "weak"]:
			continue
		if model.entities[item.id].template == "activation_source":
			if index > 1 and model.tick >= model.entities[item.id].next_activation:
				lamp_item = item
			continue
		var point = aim(item, pose)
		if point != null:
			if combined and item.id == "dragon.mouth":
				chapter_pose = pose
				chapter_point = point
			if full_campaign and item.id == "cinema.shadow_core":
				cinema_pose = pose
				cinema_point = point
			session.submit(pose)
			session.enqueue("SHOT", point)
			return false
	if lamp_item != null:
		var point = aim(lamp_item, pose)
		if point != null:
			session.submit(pose)
			session.enqueue("SHOT", point)
	return false

func play() -> void:
	var current := station()
	check(current == 1, "campaign begins at the alley")
	if current != 1:
		return
	if model.level.sections.has(ENDING_LIGHT):
		check(model.command("SKIP").get("reason") == "skip_unavailable", "combat sections cannot be skipped")
	await handle_entry(current, 0, {})
	if not profile_path.is_empty():
		await sample_rendered_frame()
	var showed_dragon := false
	var capture_reload: bool = viewport != null and not captures.is_empty() and model.level.presentation.has("hud_art")
	while model.phase == "running" and model.tick < 16000:
		if current == 1 and model.tick == 5500:
			previous_pose = model.geometry()
			for item in previous_pose:
				if item.id == "alley.lamp":
					previous_point = aim(item, previous_pose)
					break
		if current == 5 and not showed_dragon and model.entities["dragon.anchor"].active:
			showed_dragon = true
			await capture("station_5_dragon")
		var before := carried()
		var stale := queue_action(current)
		session.step()
		if model.level.controls.get("auto_reload", false) and before.ammo > 0 and model.resources.ammo == 0 and model.reload_at >= 0:
			reloads += 1
		if capture_reload and model.reload_at >= 0:
			capture_reload = false
			await capture("hud_reload")
		if stale:
			if current == 2:
				checked_old_shot = true
			elif current == 6:
				checked_chapter_shot = true
			else:
				checked_cinema_shot = true
			check(not session.last_results.is_empty() and session.last_results[0].get("reason") == "target_inactive",
				"a submitted shot from the previous station cannot hit after the handoff")
		var next := station()
		if combined and next == 0 and current == 5 and chapter_tick < 0:
			chapter_tick = model.tick
			check(model.current_section == "story.cinema_intro" and model.phase == "running" and not model.input_enabled,
				"dragon clear shows the cinema transition without ending the session")
			check(model.entities["dragon.anchor"].active and not model.entities["flow.cinema"].active,
				"chapter transition keeps the purified dragon visible until the cut")
			await capture("cinema_transition")
		if full_campaign and next == 0 and current == 10 and train_chapter_tick < 0:
			train_chapter_tick = model.tick
			check(model.current_section == "story.train_station_intro" and model.phase == "running" and not model.input_enabled,
				"cinema clear shows the train transition without ending the session")
			await capture("train_station_transition")
		if full_campaign and next == 0 and current == 14 and pullback_tick < 0:
			pullback_tick = model.tick
			check(model.current_section == "lantern_base.pullback" and not model.input_enabled,
				"the lantern pullback locks shooting before the workbench")
			await capture("lantern_pullback")
		if model.current_section == ENDING_LIGHT and ending_tick < 0:
			ending_tick = model.tick
			ending_counters = carried()
			check(model.phase == "running" and not model.input_enabled and model.available_commands().has("SKIP"),
				"the seventh stroke starts the skippable ending with weapon input locked")
			check(model.active_opacity(model.entities[ENDING_PAPER]) == 0, "the lantern starts unlit")
			if model.level.cues.has(ENDING_TAPE):
				check(ending_tape_active(), "the tape starts with the workbench shot")
				if model.level.sections.has(ENDING_WIDE):
					check(model.active_cues.size() == 1, "the epilogue mix replaces earlier ambience")
			model.set_presentation_context("player", "running")
			await capture("ending_unlit")
		if model.level.sections.has(ENDING_CITY) and model.tick == ending_tick + 216 and ending_tick >= 0:
			check(lantern_is_lit(), "the workbench lantern reaches full light before the city cut")
			await capture("ending_relit")
			if viewport != null:
				var scene = model.render_scene
				var image: Image = model.images[model.entities[ENDING_CITY_VIEW].resource]
				city_texture_preloaded = scene.preloaded_section == ENDING_CITY and scene.preloaded_textures.has(image.get_instance_id())
				check(city_texture_preloaded, "city art is preloaded during the workbench shot")
		if model.current_section == ENDING_CITY:
			if city_tick < 0:
				city_tick = model.tick
				check(city_tick - ending_tick == ending_delay_ticks("ending.city_prepare")
					and not model.input_enabled and carried() == ending_counters,
					"the city shot follows relighting and keeps combat locked")
			var city: Dictionary = model.entities[ENDING_CITY_VIEW]
			if model.tick == city_tick + 72:
				city_pan_start = Vector2(city.x, city.y)
				check(model.active_opacity(city) == 1 and city.kind == "decoration", "city art is opaque and noninteractive")
				await capture("ending_city_start")
			var street_tail := ending_delay_ticks("ending.wide_prepare") - 12 if model.level.sections.has(ENDING_WIDE) else 486
			if model.tick == city_tick + street_tail:
				check(model.active_opacity(city) == 1 and Vector2(city.x, city.y).distance_to(city_pan_start) > 60,
					"city camera traverses the lane before dissolving back")
				await capture("ending_city_end")
				if viewport != null and model.level.sections.has(ENDING_WIDE):
					var scene = model.render_scene
					var image: Image = model.images[model.entities[ENDING_WIDE_VIEW].resource]
					wide_texture_preloaded = scene.preloaded_section == ENDING_WIDE and scene.preloaded_textures.has(image.get_instance_id())
					check(wide_texture_preloaded, "panorama texture is preloaded during the street shot")
		if model.current_section == ENDING_WIDE:
			await sample_panorama()
		if model.current_section == ENDING_QUOTE and quote_tick < 0:
			quote_tick = model.tick
			if model.level.sections.has(ENDING_WIDE):
				check(wide_tick >= 0 and quote_tick - wide_tick == ending_delay_ticks("ending.quote")
					and not model.entities[ENDING_WIDE_VIEW].active, "panorama dissolves back to the workbench")
			elif model.level.sections.has(ENDING_CITY):
				check(city_tick >= 0 and quote_tick - city_tick == ending_delay_ticks("ending.quote")
					and not model.entities[ENDING_CITY_VIEW].active,
					"the city shot returns to the lit workbench before the last line")
			else:
				check(quote_tick - ending_tick == 276, "the quote follows the lantern lighting")
			check(not model.input_enabled, "the last line keeps combat locked")
			check(lantern_is_lit() and carried() == ending_counters,
				"lighting the lantern preserves the campaign result")
			await capture("ending_quote")
		if next > 0 and next != current:
			await handle_entry(next, current, before)
			current = next
		if not profile_path.is_empty():
			await sample_rendered_frame()
	check(reached == range(1, stages.size() + 1), "all stations reached in order")
	var final_target := "cinema.shadow_core" if combined else "dragon.mouth"
	if full_campaign:
		final_target = "lantern_base.forget.stroke_7"
	check(model.result == "clear" and model.entities[final_target].health <= 0, "final boss ends the campaign")
	var rescues := 7 if full_campaign else (5 if combined else 2)
	check(model.resources.rescued == rescues and model.resources["stall.purified"] == 6
		and model.trace.any(func(entry): return entry.topic == "player.damaged"),
		"the full run exercises rescues, local stall progress and damage")
	check(checked_old_shot and reloads > 0, "old pose and shared magazine were exercised")
	if combined:
		check(checked_chapter_shot, "chapter handoff rejects the stale dragon pose")
	if full_campaign:
		check(checked_cinema_shot, "train handoff rejects the stale screen pose")
		var final_section := ENDING_QUOTE if model.level.sections.has(ENDING_LIGHT) else "lantern_base.workbench"
		check(pullback_tick >= 0 and model.current_section == final_section, "final result is shown at the workbench")
		if final_section == ENDING_QUOTE:
			check(ending_tick >= 0 and quote_tick >= 0 and model.tick - quote_tick == ending_delay_ticks("lantern_base.complete"),
				"natural playback holds the quote before showing the summary")
			check(carried() == ending_counters, "ending does not change the final counters")
			check(not ending_tape_active(), "the tape expires at natural completion")
		await capture("campaign_clear")
		check_campaign_replay()
		return
	await capture("lantern_city_clear" if combined else "night_market_clear")

func check_campaign_replay() -> void:
	var record: Dictionary = session.recording()
	var trace: Array = model.trace.duplicate(true)
	var counters := carried()
	session.load_recording(record)
	while session.clock.tick < record.end_tick:
		session.step()
	check(model.result == "clear" and carried() == counters and model.trace == trace,
		"replaying the full route reproduces the result, counters and event trace")
	campaign_replay = {"inputs": record.tape.size(), "end_tick": record.end_tick, "counters": counters}
	if not recording_path.is_empty():
		var file := FileAccess.open(recording_path, FileAccess.WRITE)
		check(file != null, "open campaign recording output")
		if file != null:
			check(file.store_var({"recording": record, "handoffs": handoffs}), "write campaign recording")

func lantern_is_lit() -> bool:
	var image: Image = model.images[model.entities[ENDING_PAPER].resource]
	return model.visual_items().any(func(item): return item.image == image and item.tint.a == 1)

func ending_tape_active() -> bool:
	return model.active_cues.values().any(func(cue): return cue.cue == ENDING_TAPE)

func ending_delay_ticks(event: String) -> int:
	return ceili(model.level.events["lantern_base." + event].trigger.delay_ms * model.level.tick_hz / 1000.0)

func sample_panorama() -> void:
	var wide: Dictionary = model.entities[ENDING_WIDE_VIEW]
	if wide_tick < 0:
		wide_tick = model.tick
		check(wide_tick - city_tick == ending_delay_ticks("ending.wide_prepare") and not model.input_enabled,
			"panorama follows the street without enabling combat")
		check(model.active_opacity(wide) == 0 and model.entities[ENDING_CITY_VIEW].active,
			"panorama begins over the visible street")
	if model.tick == wide_tick + 108:
		check(model.active_opacity(wide) == 1 and not model.entities[ENDING_CITY_VIEW].active,
			"the panorama replaces the street after the dissolve")
		await capture("ending_wide_near")
	if model.tick == wide_tick + 1368:
		check(wide.pose_scale == 1 and model.active_opacity(wide) == 1,
			"the camera settles on the full town before returning to the workbench")
		await capture("ending_wide_full")

func check_ending_skip(from_tick: int, section: String) -> Dictionary:
	session.seek(from_tick)
	check(model.current_section == section and model.result.is_empty(), "skip branches from " + section)
	if model.level.cues.has(ENDING_TAPE):
		check(ending_tape_active(), "skip starts with a live tape cue")
	session.submit(model.geometry())
	check(session.enqueue("SHOT", Vector2(250, 700)) and session.enqueue("RELOAD") and session.enqueue("SKIP"),
		"submit weapon inputs and skip during the ending")
	session.step()
	var replies: Array = session.last_results
	check(replies.size() == 3 and replies[0].get("reason") == "not_running" and replies[1].get("reason") == "not_running"
		and replies[2].get("ok", false), "the ending accepts skip and rejects weapon inputs")
	check(model.phase == "result" and model.result == "clear" and model.current_section == ENDING_QUOTE,
		"skip reaches the same successful result and caption")
	check(carried() == ending_counters and lantern_is_lit(),
		"skip preserves counters and shows the lit lantern")
	check(not model.entities.has(ENDING_CITY_VIEW) or not model.entities[ENDING_CITY_VIEW].active,
		"skip clears the city overlay")
	check(not model.entities.has(ENDING_WIDE_VIEW) or not model.entities[ENDING_WIDE_VIEW].active,
		"skip clears the panorama overlay")
	check(not ending_tape_active(), "skip cancels the tape cue")
	return {"start_tick": from_tick, "result_tick": model.tick, "counters": carried(), "result": model.result}

func run() -> void:
	var args := {}
	for arg in OS.get_cmdline_user_args():
		var pair := arg.split("=", true, 1)
		if pair.size() == 2:
			args[pair[0]] = pair[1]
	profile_path = args.get("--profile", "")
	recording_path = args.get("--recording", "")
	if not profile_path.is_empty() and DisplayServer.get_name() == "headless":
		push_error("Frame profiling needs a graphics display")
		quit(2)
		return
	var open_started := Time.get_ticks_usec()
	var compiled = JSON.parse_string(FileAccess.get_file_as_string(args.get("--build", "")))
	model = Loader.open(compiled, args.get("--assets", ""))
	profile_open_us = Time.get_ticks_usec() - open_started
	if model == null:
		quit(2)
		return
	full_campaign = model.level.id in ["paper.lantern_city_campaign", "paper.lantern_city_ui", "paper.lantern_city_epilogue",
		"paper.lantern_city_tadpole", "paper.lantern_city_rescue", "paper.lantern_city_cast"]
	combined = full_campaign or model.level.id == "paper.lantern_city"
	stages = STAGES + CINEMA_STAGES if combined else STAGES
	if full_campaign:
		stages += TRAIN_STAGES
	captures = args.get("--captures", "")
	if not profile_path.is_empty() or (not captures.is_empty() and DisplayServer.get_name() != "headless"):
		if not captures.is_empty() and DirAccess.make_dir_recursive_absolute(captures) != OK:
			quit(2)
			return
		viewport = SubViewport.new()
		viewport.size = Vector2i(1776, 936)
		viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		root.add_child(viewport)
		model.mount(viewport)
		if not profile_path.is_empty():
			model.render_scene.measure_uploads = true
			prepare_texture_accounting()
			root.size = Vector2i(1280, 720)
			DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
			var preview := TextureRect.new()
			preview.texture = viewport.get_texture()
			preview.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			preview.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			preview.size = Vector2(root.size)
			root.add_child(preview)
	session.setup(model)
	if viewport != null and model.level.presentation.get("hud_art", {}).has("lettering"):
		model.set_presentation_context("player", "ready")
		await capture("title_screen")
		model.set_presentation_context("review", "paused")
	await play()
	var outcome := {"build_id": model.build.build_id,
		"gpu_capture": viewport != null and not captures.is_empty(), "reached": reached, "handoffs": handoffs, "reloads": reloads,
		"end_tick": model.tick, "counters": carried(), "result": model.result, "chapter_transition_tick": chapter_tick}
	if full_campaign:
		outcome["train_transition_tick"] = train_chapter_tick
		outcome["pullback_tick"] = pullback_tick
		outcome["replay"] = campaign_replay
		outcome["old_chapter_poses_rejected"] = checked_chapter_shot and checked_cinema_shot
	if not profile_path.is_empty():
		write_profile()
		await check_texture_restart()
		outcome["texture_restart_checked"] = true
	if ending_tick >= 0:
		outcome["ending"] = {"light_tick": ending_tick, "quote_tick": quote_tick, "natural_result_tick": outcome.end_tick}
		if city_tick >= 0:
			outcome.ending["city_tick"] = city_tick
			outcome.ending["city_texture_preloaded"] = city_texture_preloaded
		if wide_tick >= 0:
			outcome.ending["wide_tick"] = wide_tick
			outcome.ending["wide_texture_preloaded"] = wide_texture_preloaded
		if profile_path.is_empty():
			if city_tick >= 0:
				outcome.ending["skip_from_quote"] = check_ending_skip(quote_tick, ENDING_QUOTE)
				if wide_tick >= 0:
					outcome.ending["skip_from_wide"] = check_ending_skip(wide_tick + 120, ENDING_WIDE)
				outcome.ending["skip_from_city"] = check_ending_skip(city_tick + 120, ENDING_CITY)
			outcome.ending["skip"] = check_ending_skip(ending_tick, ENDING_LIGHT)
	if args.get("--failure-retry", "") == "true":
		check(combined and reached.size() == stages.size(), "failure and retry fixture requires a completed combined route")
		if combined and reached.size() == stages.size():
			check_failure_retries()
			outcome["failure_retries"] = failure_retries
	outcome["passed"] = failures.is_empty()
	outcome["failures"] = failures
	print(JSON.stringify(outcome))
	quit(0 if failures.is_empty() else 1)
