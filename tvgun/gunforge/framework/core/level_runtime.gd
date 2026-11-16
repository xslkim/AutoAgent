extends RefCounted
## Neutral fixed-tick runtime. Content cannot name scripts or execute expressions.
const Item = preload("raster_item.gd")
const Resolver = preload("hit_resolver.gd")
const Motion=preload("motion_pose.gd")
var build: Dictionary
var level: Dictionary
var entities: Dictionary = {}
var resources: Dictionary = {}
var queries: Dictionary = {}
var tick: int = 0
var phase = "ready"
var result = ""
var paused_reasons: Dictionary = {}
var fired: Dictionary = {}
var fired_time: Dictionary = {}
var topics: Array = []
var trace: Array = []
var shots: int = 0
var hits: int = 0
var reload_at: int = -1
var next_shot: int = 0
var images: Dictionary = {}
var resolver = Resolver.new()
var root_path: String
var active_cues = {}
var cue_serial = 0
var active_effects={}
var effect_serial=0
var current_section=""
var input_enabled=true

func setup(compiled: Dictionary, asset_root: String):
	assert(compiled.format == "gunforge-compiled-level-v1")
	build = compiled.duplicate(true)
	level = build.level
	root_path = asset_root
	images.clear()
	for id in level.resources:
		var resource = level.resources[id]
		if resource.kind == "image":
			var path = asset_root.path_join(resource.path)
			assert(FileAccess.get_sha256(path) == resource.sha256, "Asset version mismatch")
			var image = Image.load_from_file(path)
			assert(image != null and not image.is_empty())
			images[id] = image
	reset()
	phase = "ready"

func reset():
	tick = 0
	phase = "running"
	result = ""
	entities = level.entities.duplicate(true)
	resources = level.initial_resources.duplicate(true)
	queries.clear()
	fired.clear()
	fired_time.clear()
	topics.clear()
	trace.clear()
	paused_reasons.clear()
	shots = 0
	hits = 0
	reload_at = -1
	next_shot = 0
	active_cues.clear();cue_serial=0
	active_effects.clear();effect_serial=0;current_section="";input_enabled=true
	for id in entities:
		var entity = entities[id]
		entity.properties = entity.get("properties", {})
		entity.active = bool(entity.properties.get("active", false))
		entity.visible = bool(entity.properties.get("visible", true))
		entity.kind = "protected" if entity.template == "protected" else ("decoration" if entity.template == "decoration" else "primary")
		entity.health = int(entity.properties.get("hits", 1))
		entity.value = float(entity.properties.get("value", 0))
		entity.age_ticks=0;entity.generation=0;entity.stun_until=-1;entity.pause_motion_until=-1;entity.stunned=false;entity.next_activation=-1
		entity.last_hit_tick=-1000;entity.hit_direction=1;entity.defeated_at=-1;entity.removed_at=-1;entity.view_tick=0
		Motion.update(entity,level.tick_hz)
	update_queries()
	process_events([])

func start():
	reset()

func emit(topic: String, entity: String = "", data:Dictionary={}):
	var entry = {"tick":tick,"topic":topic,"entity":entity}
	if not data.is_empty():entry.data=data.duplicate(true)
	topics.append(entry)
	trace.append(entry.duplicate(true))
	var bindings=level.get("presentation",{}).get("sound_bindings",{})
	var cue=bindings.get(topic+":"+entity,bindings.get(topic,""))
	if not cue.is_empty():play_cue(cue)

func play_cue(id):
	var cue=level.cues[id];cue_serial+=1
	active_cues[str(cue_serial)]={"cue":id,"start_tick":tick,"end_tick":tick+int(ceil(cue.duration_ms*level.tick_hz/1000.0)),"loop":cue.get("loop",false)}
	var entry={"tick":tick,"topic":"cue.started","entity":id};topics.append(entry);trace.append(entry.duplicate(true))

func start_effect(id,point,entity="",source=""):
	if id.is_empty():return
	effect_serial+=1
	var effect = {"effect":id,"start_tick":tick,"position":[point.x,point.y],"entity":entity}
	if not source.is_empty():effect["source"] = source
	active_effects[str(effect_serial)] = effect
	emit("effect.started",id)

func feedback(name,point,entity=""):
	start_effect(level.get("presentation",{}).get("feedback",{}).get(name,""),point,entity)

func center(entity):return Vector2(entity.x+entity.width*.5,entity.y+entity.height*.5)
func display_center(entity) -> Vector2:return center(entity)
func display_transform(entity) -> Transform2D:return Motion.transform(entity)
func active_opacity(entity) -> float:
	return float(entity.get("pose_opacity", 1)) if entity.active and entity.visible else 0.0

func effective_kind(entity) -> String:
	if not entity.has("mask_permission") or entity.kind not in ["primary", "weak"]:
		return entity.kind
	var gate: Dictionary = entity.mask_permission
	var anchor: Dictionary = entities[gate.source]
	var opacity := active_opacity(anchor)
	if opacity <= 0:
		return "invalid"
	var center_point := display_transform(entity) * (Vector2(entity.width, entity.height) * .5)
	var local := display_transform(anchor).affine_inverse() * center_point
	var size := Vector2(anchor.width, anchor.height)
	if not Rect2(Vector2.ZERO, size).has_point(local):
		return "invalid"
	var weight := preload("spatial_queries.gd").mask_red(images[gate.resource], local, size)
	var influence := weight * opacity
	return entity.kind if influence >= gate.threshold else "invalid"

func step():
	if phase != "running" or not paused_reasons.is_empty():
		return
	tick += 1
	for id in active_effects.keys():
		if (tick-active_effects[id].start_tick)*1000>=level.effects[active_effects[id].effect].duration_ms*level.tick_hz:active_effects.erase(id)
	for id in active_cues.keys():
		var cue=active_cues[id]
		if not cue.loop and tick>=cue.end_tick:active_cues.erase(id)
	if reload_at >= 0 and tick >= reload_at:
		resources[level.controls.ammo_resource] = level.controls.magazine
		reload_at = -1
		emit("weapon.reloaded")
	for id in entities:
		var entity = entities[id]
		entity.view_tick=tick
		entity.stunned=tick<int(entity.stun_until)
		if entity.active:
			if tick-1>=int(entity.stun_until) and tick-1>=int(entity.pause_motion_until):
				entity.age_ticks+=1
				entity.x += float(entity.get("vx",entity.properties.get("vx", 0))) / level.tick_hz
				entity.y += float(entity.get("vy",entity.properties.get("vy", 0))) / level.tick_hz
			Motion.update(entity,level.tick_hz)
	var incoming = topics.duplicate(true)
	topics.clear()
	update_queries()
	process_events(incoming)
	if phase == "running" and tick >= level.deadline_tick:
		phase = "result"
		result = "timeout"
		emit("session.timeout")

func compare(a: float, op: String, b: float) -> bool:
	match op:
		"gte": return a >= b
		"gt": return a > b
		"eq": return a == b
		"lte": return a <= b
		"lt": return a < b
	return false

func update_queries():
	for id in level.queries:
		var query = level.queries[id]
		var entity = entities[query.entity]
		if query.op=="entity_age_ms":
			queries[id]={"value":Motion.age_ms(entity,level.tick_hz),"tick":tick,"algorithm":query.algorithm,"space":query.space};continue
		var point = Vector2(entity.x, entity.y)
		if query.get("sample", "center") == "center":
			point += Vector2(entity.width, entity.height) * .5
		var value = 0.0
		match query.op:
			"region_contains":
				var r = query.region
				value = 1.0 if Rect2(r[0], r[1], r[2], r[3]).has_point(point) else 0.0
			"distance":
				var other = entities[query.other]
				value = point.distance_to(Vector2(other.x + other.width * .5, other.y + other.height * .5))
			"mask_sample":
				var image = images[query.resource]
				value=preload("spatial_queries.gd").mask_red(image,point,Vector2(level.layout.width,level.layout.height))
				if query.has("other"):
					value *= float(entities[query.other].value)
		queries[id] = {"value":value,"tick":tick,"algorithm":query.algorithm,"space":query.space}

func process_events(incoming: Array):
	preload("event_scheduler.gd").run(self,incoming)

func apply_action(action: Dictionary):
	match action.op:
		"spawn": spawn(action.entity)
		"remove": entities[action.entity].active = false;entities[action.entity].removed_at=tick
		"set": entities[action.entity][action.field] = action.value
		"permission": entities[action.entity].kind = action.kind
		"resource_add":
			var previous: int = int(resources[action.resource])
			var bounds = level.get("resource_bounds", {}).get(action.resource, {})
			resources[action.resource] = clampi(previous + int(action.amount), bounds.get("min", -2147483648), bounds.get("max", 2147483647))
			# A supply on the last shot can refill before the automatic reload completes.
			var controls: Dictionary = level.get("controls", {})
			if reload_at >= 0 and previous == 0 and resources[action.resource] > 0 \
				and controls.get("auto_reload", false) and action.resource == controls.ammo_resource:
				reload_at = -1
		"emit": emit(action.event)
		"cue":
			if action.get("replace_existing", false):active_cues.clear()
			play_cue(action.cue)
		"stun":
			var entity=entities[action.entity]
			entity.stun_until=maxi(entity.stun_until,tick+int(ceil(action.duration_ms*level.tick_hz/1000.0)));entity.stunned=true
			emit("target.stunned",action.entity)
		"launch":
			spawn(action.entity)
			var projectile=entities[action.entity];var origin=center(entities[action.source])-Vector2(projectile.width,projectile.height)*.5
			projectile.motion_override={"easing":"linear","frames":[{"at_ms":0,"x":origin.x,"y":origin.y},{"at_ms":action.duration_ms,"x":action.x-projectile.width*.5,"y":action.y-projectile.height*.5}]}
			Motion.update(projectile,level.tick_hz);emit("attack.launched",action.source)
		"vfx":start_effect(action.effect,display_center(entities[action.entity]),action.entity,action.get("source",""))
		"section":current_section=action.section;emit("section.started",action.section)
		"input":input_enabled=action.enabled
		"complete", "fail":
			phase = "result"
			result = action.result
			emit("session." + action.op)

func spawn(id):
	var entity=entities[id];entity.active=true;entity.age_ticks=0;entity.generation+=1;entity.health=int(entity.properties.get("hits",1));entity.defeated_at=-1;entity.removed_at=-1
	entity.stun_until=-1;entity.pause_motion_until=-1;entity.stunned=false;entity.erase("motion_override");Motion.update(entity,level.tick_hz)
	emit("entity.spawned",id)

func image_for(entity: Dictionary) -> Image:
	if entity.has("resource"):
		return images[entity.resource]
	var shape = entity.properties.get("shape", "rect")
	var key = "@" + shape
	if not images.has(key):
		var image = Image.create(32, 32, false, Image.FORMAT_RGBA8)
		image.fill(Color.WHITE if shape == "rect" else Color.TRANSPARENT)
		if shape == "circle":
			for y in range(32):
				for x in range(32):
					if Vector2(x + .5, y + .5).distance_to(Vector2(16, 16)) <= 16:
						image.set_pixel(x, y, Color.WHITE)
		images[key] = image
	return images[key]

func geometry() -> Array:
	return entity_geometry()

func entity_geometry(visuals := false) -> Array:
	var out = []
	var keys = entities.keys()
	keys.sort_custom(func(a, b):
		var za = int(entities[a].properties.get("z", 0))
		var zb = int(entities[b].properties.get("z", 0))
		return a < b if za == zb else za < zb)
	for id in keys:
		var entity = entities[id]
		if not entity.active or not entity.visible or entity.properties.get("virtual",false) or entity.has("puppet"):
			continue
		var kind := effective_kind(entity)
		if entity.has("parts"):
			var parts: Array = Motion.parts(entity,id,images,level.tick_hz,kind if visuals else "")
			if kind != entity.kind:
				for part in parts:
					part.kind = kind
			out.append_array(parts)
			continue
		var item = Item.new()
		item.id = id
		item.kind = "" if kind == "decoration" else kind
		item.image = image_for(entity)
		if entity.has("hit_resource"):
			item.hit_image = images[entity.hit_resource]
		item.source = Rect2(Vector2.ZERO, item.image.get_size())
		item.size = Vector2(entity.width, entity.height)
		item.transform = Motion.transform(entity);item.generation=int(entity.generation);item.z=int(entity.properties.get("z",0))
		item.tint.a = float(entity.get("pose_opacity",1))
		out.append(item)
	return out

func geometry_assets() -> Dictionary:
	for entity in entities.values():image_for(entity)
	var out = {}
	for id in images:out[id]={"image":images[id],"texture":null}
	return out

func target_role(id):return entities[id].template if entities.has(id) else "unknown"
func available_commands():
	var commands = ["START","EXIT"]
	if phase == "running" and level.get("sections", {}).get(current_section, {}).get("skippable", false):
		commands.append("SKIP")
	var controls = level.get("controls",{})
	if controls.has("ammo_resource") and controls.has("magazine"):
		commands.append("RELOAD")
	return commands

func begin_reload():
	var reload_ms := float(level.controls.get("reload_ms", 500))
	reload_at = tick + maxi(1, ceili(reload_ms * level.tick_hz / 1000))

func command(event: String, point: Vector2 = Vector2.ZERO, bound_geometry: Variant = null) -> Dictionary:
	if event == "START":
		start()
		return {"ok":true}
	if phase != "running" or not paused_reasons.is_empty():
		return {"ok":false,"reason":"not_running"}
	if event == "SKIP":
		if not available_commands().has("SKIP"):
			return {"ok":false,"reason":"skip_unavailable"}
		active_cues.clear()
		emit("section.skipped", current_section)
		return {"ok":true}
	if not input_enabled:
		return {"ok":false,"reason":"not_running"}
	var controls = level.get("controls", {})
	if event == "RELOAD":
		if available_commands().has("RELOAD") and reload_at < 0:
			begin_reload()
			return {"ok":true}
		return {"ok":false,"reason":"reload_unavailable"}
	if event != "SHOT":
		return {"ok":false,"reason":"unsupported_command"}
	if tick < next_shot or reload_at >= 0:
		return {"ok":false,"reason":"weapon_busy"}
	if controls.has("ammo_resource"):
		if resources[controls.ammo_resource] <= 0:
			emit("weapon.empty")
			feedback("empty",point)
			return {"ok":false,"reason":"empty"}
		resources[controls.ammo_resource] -= 1
		if resources[controls.ammo_resource] == 0 and controls.get("auto_reload", false):
			begin_reload()
	next_shot = tick + int(ceil(float(controls.get("shot_interval_ms", 0)) * level.tick_hz / 1000))
	shots += 1
	emit("weapon.fired");feedback("shot",point)
	var pose = geometry() if bound_geometry == null else bound_geometry
	var hit = resolver.resolve(point, pose, float(controls.get("assist_px", 0)))
	var id = hit.get("id", "")
	if entities.has(id):
		var entity = entities[id]
		if not entity.active or entity.kind == "decoration":
			return {"ok":true,"hit":false,"reason":"target_inactive"}
		if int(hit.get("generation",entity.generation))!=int(entity.generation):return {"ok":true,"hit":false,"reason":"target_generation_changed"}
		# Spatial permission is part of the submitted pose. Explicit entity permission still gates queued hits.
		if hit.kind in ["primary", "weak"] and entity.kind in ["primary", "weak"]:
			if entity.template == "activation_source":
				if tick<int(entity.next_activation):emit("interaction.cooldown",id);return {"ok":true,"hit":false,"reason":"interaction_cooldown"}
				hits+=1;entity.next_activation=tick+int(ceil(entity.properties.get("activation_cooldown_ms",0)*level.tick_hz/1000.0))
				entity.value = 1.0
				emit("interaction.activated", id)
			else:
				hits+=1;entity.last_hit_tick=tick;entity.hit_direction=1 if display_center(entity).x>=point.x else -1
				entity.pause_motion_until=tick+int(ceil(entity.properties.get("hitstop_ms",0)*level.tick_hz/1000.0))
				entity.health -= int(entity.properties.get("weak_damage",1)) if hit.kind=="weak" else 1
				emit("target.weak_hit" if hit.kind=="weak" else "target.hit",id)
				feedback("weak" if hit.kind=="weak" else "hit",hit.get("point",point),id)
				if entity.health <= 0:
					entity.active = false
					entity.defeated_at=tick
					feedback("neutralized",hit.get("point",point),id)
					emit("target.neutralized", id)
			return {"ok":true,"hit":true,"target":id,"kind":hit.kind}
		if hit.kind == "protected" and entity.kind == "protected":
			emit("target.protected_hit", id)
		else:
			emit("target.blocked", id)
	return {"ok":true,"hit":false,"kind":hit.get("kind", "miss")}

func public_state() -> Dictionary:
	return {"tick":tick,"phase":phase,"result":result,"resources":resources.duplicate(true),
		"entities":entities.duplicate(true),"queries":queries.duplicate(true),"shots":shots,"hits":hits,
		"reload_at":reload_at,"next_shot":next_shot,"pause_reasons":paused_reasons.keys(),"active_cues":active_cues.duplicate(true),"cue_serial":cue_serial,"active_effects":active_effects.duplicate(true),"effect_serial":effect_serial,"current_section":current_section,"input_enabled":input_enabled}

func save_state() -> Dictionary:
	return _save_state(true)

func save_checkpoint() -> Dictionary:
	# The runtime only appends trace entries. Keep each checkpoint's own array
	# so advancing or clearing the live trace cannot change the saved history.
	return _save_state(false)

func _save_state(copy_trace_entries: bool) -> Dictionary:
	return {"version":1,"build_id":build.build_id,"public":public_state(),"fired":fired.duplicate(true),
		"fired_time":fired_time.duplicate(true),"topics":topics.duplicate(true),"trace":trace.duplicate(copy_trace_entries)}

func restore_state(saved: Dictionary):
	assert(saved.version == 1 and saved.build_id == build.build_id)
	var state = saved.public
	tick = int(state.tick)
	phase = state.phase
	result = state.result
	resources = state.resources.duplicate(true)
	entities = state.entities.duplicate(true)
	queries = state.queries.duplicate(true)
	shots = int(state.shots)
	hits = int(state.hits)
	reload_at = int(state.reload_at)
	next_shot = int(state.next_shot)
	active_cues=state.active_cues.duplicate(true);cue_serial=int(state.cue_serial)
	active_effects=state.get("active_effects",{}).duplicate(true);effect_serial=int(state.get("effect_serial",0));current_section=state.get("current_section","");input_enabled=state.get("input_enabled",true)
	paused_reasons.clear()
	for reason in state.pause_reasons:
		paused_reasons[reason] = true
	fired = saved.fired.duplicate(true)
	fired_time = saved.fired_time.duplicate(true)
	topics = saved.topics.duplicate(true)
	trace = saved.trace.duplicate(true)
