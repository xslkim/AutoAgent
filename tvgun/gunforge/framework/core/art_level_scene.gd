extends Node2D
## Layered 2D art and deterministic presentation; owns no combat simulation.
const RasterLayer = preload("raster_layer.gd")
const PaperHud = preload("paper_hud.gd")
const LABEL_OUTLINE := 4
var model
var textures={}
var texture_group := ""
var section_layers := false
var texture_preloads: Array[Dictionary] = []
var preloaded_section := ""
var preloaded_textures: Dictionary = {}
var preloaded_caption_count := 0
var measure_uploads := false
var upload_count := 0
var upload_us := 0
var font=SystemFont.new()
var background: Node2D
var additive: Node2D
var bottom_wipe: Node2D
var wipes: Dictionary = {}
var additive_z: int
var foreground: Array = []
var paper_hud: PaperHud

func _ready():
	font.font_names=PackedStringArray(["Microsoft YaHei","Noto Sans CJK SC"])
	var presentation: Dictionary = model.level.get("presentation", {})
	if presentation.has("hud_art"):
		paper_hud = PaperHud.new()
		paper_hud.setup(model, presentation.hud_art, self)
	wipes = presentation.get("bottom_wipes", {})
	section_layers = presentation.get("layers", {}).values().any(func(layer): return layer.has("section"))
	if section_layers:
		index_texture_preloads(presentation)
	if presentation.has("additive_z"):
		additive_z = presentation.additive_z
		background = RasterLayer.new()
		background.show_behind_parent = true
		add_child(background)
		additive = RasterLayer.new()
		additive.show_behind_parent = true
		var blend := CanvasItemMaterial.new()
		blend.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
		additive.material = blend
		add_child(additive)
		if not wipes.is_empty():
			bottom_wipe = RasterLayer.new()
			bottom_wipe.show_behind_parent = true
			var material := ShaderMaterial.new()
			material.shader = preload("bottom_wipe.gdshader")
			bottom_wipe.material = material
			add_child(bottom_wipe)
	update_rasters()

func _process(_delta):
	upload_count = 0
	upload_us = 0
	update_rasters()
	preload_next_section()
	if paper_hud != null:
		paper_hud.update_lettering()
	queue_redraw()

func index_texture_preloads(presentation: Dictionary) -> void:
	var events: Dictionary = model.level.events
	for id in model.level.event_order:
		var event: Dictionary = events[id]
		var enter: Dictionary = event.trigger
		if not enter.has("after") or enter.delay_ms != 0 or event.max_firings != 1:
			continue
		var wait_event: Dictionary = events[enter.after]
		var wait: Dictionary = wait_event.trigger
		if not wait.has("after") or wait.delay_ms <= 0 or wait_event.max_firings != 1:
			continue
		var clear: Dictionary = events[wait.after]
		if clear.max_firings != 1 or not clear.actions.values().any(func(action): return action.op == "input" and not action.enabled):
			continue
		var section := ""
		for action in event.actions.values():
			if action.op == "section":
				section = action.section
		if section.is_empty():
			continue
		var resources: Dictionary = {}
		for layer in presentation.layers.values():
			if layer.get("section", "") == section:
				resources[layer.resource] = true
		for action_id in event.order:
			var action: Dictionary = event.actions[action_id]
			if action.op == "spawn":
				collect_spawn_textures(model.level.entities[action.entity], presentation, resources)
				if wipes.has(action.entity):
					resources[model.level.entities[wipes[action.entity]].resource] = true
		if not resources.is_empty():
			texture_preloads.append({"enter": id, "clear": wait.after, "section": section,
				"delay_ms": wait.delay_ms, "resources": resources.keys()})

func collect_spawn_textures(entity: Dictionary, presentation: Dictionary, resources: Dictionary) -> void:
	if entity.get("properties", {}).get("virtual", false):
		return
	if entity.has("puppet"):
		resources[presentation.puppets[entity.puppet.rig].atlas] = true
	elif entity.has("parts"):
		for part in entity.parts.values():
			resources[part.resource] = true
			if part.has("hardened_visual"):
				resources[part.hardened_visual.resource] = true
	elif entity.has("resource"):
		resources[entity.resource] = true

func preload_next_section() -> void:
	if model.phase == "running" and not model.input_enabled:
		for plan in texture_preloads:
			if plan.section == model.current_section or model.fired.has(plan.enter) or not model.fired_time.has(plan.clear):
				continue
			var due: int = int(model.fired_time[plan.clear]) + int(plan.delay_ms) * int(model.level.tick_hz)
			if model.tick * 1000 >= due:
				continue
			if preloaded_section != plan.section:
				preloaded_section = plan.section
				preloaded_textures.clear()
				preloaded_caption_count = 0
			for resource in plan.resources:
				var image: Image = model.images[resource]
				var id := image.get_instance_id()
				if not textures.has(id) and not preloaded_textures.has(id):
					preloaded_textures[id] = upload(image)
					return
			if paper_hud != null and preloaded_caption_count < PaperHud.STATION_CAPTION_COUNT:
				paper_hud.preload_station_caption(self, model.level.sections[plan.section], preloaded_caption_count)
				preloaded_caption_count += 1
			return
	preloaded_section = ""
	preloaded_textures.clear()

func update_rasters():
	var items: Array = model.visual_items()
	var section: Dictionary = model.level.get("sections", {}).get(model.current_section, {})
	var group := ""
	if section.has("station"):
		group = "station:%d" % int(section.station)
	elif section_layers:
		group = "section:" + str(model.current_section)
	if group != texture_group:
		texture_group = group
		var section_images: Dictionary = {}
		for item in items:
			section_images[item.image.get_instance_id()] = true
			for image in item.state_images:
				section_images[image.get_instance_id()] = true
			if wipes.has(item.id):
				section_images[light_image(item.id).get_instance_id()] = true
		for id in textures.keys():
			if not section_images.has(id):
				textures.erase(id)
		if preloaded_section == model.current_section:
			for id in preloaded_textures:
				if section_images.has(id):
					textures[id] = preloaded_textures[id]
		preloaded_section = ""
		preloaded_textures.clear()
	for item in items:
		for image in item.state_images:
			texture(image)
	if additive == null:
		foreground = items
		return
	var behind: Array = []
	var lights: Array = []
	var overlays: Array = []
	foreground = []
	for item in items:
		if wipes.has(item.id):
			# The dormant glow belongs to the same station as the visible ink cover.
			texture(light_image(item.id))
			overlays.append(item)
			continue
		if item.z > additive_z:
			foreground.append(item)
			continue
		if item.z == additive_z:
			lights.append(item)
		else:
			behind.append(item)
	background.refresh(behind)
	additive.refresh(lights)
	if bottom_wipe != null:
		bottom_wipe.refresh(overlays)
	for item in items:
		item.texture = texture(item.image)

func light_image(cover_id: String) -> Image:
	return model.images[model.level.entities[wipes[cover_id]].resource]

func label(text,point,size=28,color=Color("#e8d3ad"),centered=false):
	var at=point
	if centered:at.x-=font.get_string_size(str(text),HORIZONTAL_ALIGNMENT_LEFT,-1,size).x*.5
	draw_string_outline(font,at,str(text),HORIZONTAL_ALIGNMENT_LEFT,-1,size,LABEL_OUTLINE,Color(.015,.02,.03,.9*color.a))
	draw_string(font,at,str(text),HORIZONTAL_ALIGNMENT_LEFT,-1,size,color)

func warm_label(text: String, size: int) -> void:
	if text.is_empty():
		return
	# An unattached item warms the same shaped line and glyph caches used by label().
	var item := RenderingServer.canvas_item_create()
	font.draw_string_outline(item, Vector2.ZERO, text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, LABEL_OUTLINE)
	font.draw_string(item, Vector2.ZERO, text, HORIZONTAL_ALIGNMENT_LEFT, -1, size)
	RenderingServer.free_rid(item)
func texture(image):
	var id=image.get_instance_id()
	if not textures.has(id):
		if preloaded_textures.has(id):
			textures[id] = preloaded_textures[id]
			preloaded_textures.erase(id)
		else:
			textures[id] = upload(image)
	return textures[id]
func upload(image: Image) -> ImageTexture:
	if not measure_uploads:
		return ImageTexture.create_from_image(image)
	var started := Time.get_ticks_usec()
	var uploaded := ImageTexture.create_from_image(image)
	upload_count += 1
	upload_us += Time.get_ticks_usec() - started
	return uploaded
func _draw():
	if model==null:return
	for item in foreground:
		draw_set_transform_matrix(item.transform)
		draw_texture_rect_region(item.texture if additive != null else texture(item.image),Rect2(Vector2.ZERO,item.size),item.source,item.tint)
	draw_set_transform_matrix(Transform2D.IDENTITY)
	if paper_hud == null or paper_hud.lettering_screen().is_empty():
		draw_intents()
		draw_effects()
	draw_hud()
func draw_intents():
	var presentation: Dictionary = model.level.get("presentation", {})
	var glows: Dictionary = presentation.get("activation_glows", {})
	var state_labels: Dictionary = presentation.get("entity_state_labels", {})
	for id in model.entities:
		var entity=model.entities[id]
		if not entity.active or not entity.visible or entity.properties.get("virtual",false):continue
		var at=model.display_center(entity)
		if state_labels.has(id):
			var caption: String = state_labels[id].get(model.effective_kind(entity), "")
			if not caption.is_empty():
				var color := Color("#f4ddb0")
				color.a = float(entity.get("pose_opacity", 1))
				label(caption, at + Vector2(0, entity.height * .33), 23, color, true)
		var glow: Dictionary = glows.get(id, {})
		if not glow.is_empty() and entity.value > 0:
			var warm := Color(glow.color)
			var radius := float(glow.radius)
			for band in range(6, 0, -1):
				draw_circle(at, radius * band / 6.0, Color(warm, .07), true, -1.0, true)
			draw_arc(at, radius * .53, 0, TAU, 48, Color(warm, .92), 4, true)
			var seconds := maxf(0, (entity.next_activation - model.tick) / float(model.level.tick_hz))
			label("%s · %.1f 秒" % [glow.label, seconds], at + Vector2(0, radius * .65), 28, warm, true)
		if entity.stunned:
			draw_arc(at,maxf(entity.width,entity.height)*.48,0,TAU,40,Color("#dab969"),4,true)
			label(model.level.get("presentation",{}).get("labels",{}).get("stunned","停顿"),at+Vector2(0,-entity.height*.45),23,Color("#e6c17a"),true)
		for phase in entity.get("phases",[]):
			if phase.id!=entity.motion_phase or entity.stunned:continue
			var progress=clampf((float(entity.age_ticks)*1000/model.level.tick_hz-phase.start_ms)/float(phase.end_ms-phase.start_ms),0,1)
			var color = Color(phase.get("color","#c9654b"))
			var radius = maxf(entity.width,entity.height) * .55 * float(entity.get("pose_scale",1))
			draw_arc(at,radius,0,TAU,48,Color("#321e24"),12,true)
			draw_arc(at,radius,0,TAU,48,Color(color,.55),4,true)
			if progress>0.0:
				draw_arc(at,radius,-PI*.5,-PI*.5+TAU*progress,48,color,8,true)
			var caption = str(phase.get("label",""))
			if not caption.is_empty():
				label(caption,Vector2(at.x,maxf(118.0,at.y-radius-14.0)),32,color,true)
	var support=model.level.get("presentation",{}).get("support",{})
	if not support.is_empty() and model.input_enabled and model.entities[support.entity].active:
		var entity=model.entities[support.entity]
		var remaining=maxf(0,(entity.next_activation-model.tick)/float(model.level.tick_hz))
		var at=model.display_center(entity)
		label(support.label+(" · 就绪" if remaining<=0 else " · %.1f 秒" % remaining),at+Vector2(-110,entity.height*.5+30),23,Color("#e1bd76"))
func draw_effects():
	var canvas = Vector2(model.level.layout.width,model.level.layout.height)
	for serial in model.active_effects:
		var instance=model.active_effects[serial];var definition=model.level.effects[instance.effect]
		var age=(model.tick-instance.start_tick)/float(model.level.tick_hz)
		var t=clampf(age*1000/definition.duration_ms,0,1)
		var at=Vector2(instance.position[0],instance.position[1]);var color=Color(definition.color);color.a*=1-t
		var radius=float(definition.get("radius",80))
		var anchor_uv = definition.get("anchor_uv",[])
		match definition.kind:
			"beam_sweep":
				if not instance.get("source", "").is_empty():
					var emitter = model.display_center(model.entities[instance.source])
					var normal = (at-emitter).normalized().orthogonal()
					var tip = at + normal * radius * (2*t-1)
					var beam = PackedVector2Array([emitter, tip-normal*52, tip+normal*52])
					draw_colored_polygon(beam, Color(color, .34 * sin(PI*t)))
					draw_line(emitter, tip, Color(color, .56 * sin(PI*t)), 4, true)
			"shot_trace":
				var muzzle = Vector2(canvas.x*.5,canvas.y-30)
				if not anchor_uv.is_empty():muzzle = canvas*Vector2(anchor_uv[0],anchor_uv[1])
				draw_shot_trace(at,muzzle,radius,color,t)
			"attack_release":
				var destination = Vector2(canvas.x*.5,canvas.y*.86)
				if not anchor_uv.is_empty():destination = canvas*Vector2(anchor_uv[0],anchor_uv[1])
				draw_attack_release(at,destination,radius,color,t)
			"spark","burst":
				for i in range(12 if definition.kind=="burst" else 7):
					var angle=i*TAU/(12 if definition.kind=="burst" else 7)+int(serial)*.37
					var direction=Vector2.from_angle(angle)
					var distance=radius*(.08+t*.8)
					draw_line(at+direction*distance*.4,at+direction*distance,color,maxf(1,5*(1-t)),true)
					if definition.kind=="burst":draw_circle(at+direction*distance+Vector2(0,t*t*25),maxf(1,6*(1-t)),Color(.025,.03,.04,1-t))
				draw_arc(at,radius*t*.6,0,TAU,32,color,3,true)
			"pulse":
				draw_arc(at,maxf(1,radius*t),0,TAU,96,color,5*(1-t)+1,true)
			"link":
				var support=model.level.get("presentation",{}).get("support",{})
				var source = instance.get("source",support.get("entity",""))
				if not source.is_empty():draw_line(model.display_center(model.entities[source]),at,color,2,true)
				draw_arc(at,35+60*t,0,TAU,32,color,3,true)
			"warning":draw_arc(at,radius*(1-.5*t),0,TAU,32,color,4,true)
			"player_hit":
				draw_player_hit(canvas,Color(definition.color),t,int(serial),definition.get("label",""))
		if definition.kind!="player_hit" and definition.has("label"):label(definition.label,at+Vector2(0,-20-t*40),26,color,true)

func draw_shot_trace(at: Vector2, muzzle: Vector2, radius: float, color: Color, age: float) -> void:
	var direction = (muzzle-at).normalized()
	var normal = direction.orthogonal()
	var tail = muzzle.lerp(at,age)
	draw_line(tail,at,color,maxf(1.0,18.0*(1.0-age)),true)
	draw_line(tail,at,Color(1.0,.98,.84,color.a),maxf(1.0,5.0*(1.0-age)),true)
	draw_circle(muzzle,35.0*(1.0-age),Color(color,color.a*.65))
	draw_circle(at,maxf(3.0,radius*.28*(1.0-age)),Color(1.0,.98,.84,color.a))
	draw_arc(at,radius*(.55+age),0,TAU,32,color,5,true)
	for offset in [direction,-direction,normal,-normal]:
		draw_line(at+offset*radius*.5,at+offset*radius*1.18,color,5,true)

func draw_attack_release(at: Vector2, destination: Vector2, radius: float, color: Color, age: float) -> void:
	var direction = (destination-at).normalized()
	var normal = direction.orthogonal()
	var tip = at.lerp(destination,minf(1.0,age*2.6))
	for offset in [-.65,0.0,.65]:
		var start = at + normal*radius*offset
		var end = tip + normal*radius*offset*.3
		draw_line(start,end,Color(.16,.025,.045,color.a),22,true)
		draw_line(start,end,color,9,true)
	draw_arc(at,radius*(.65+age),0,TAU,36,color,7,true)

func draw_player_hit(canvas: Vector2, color: Color, age: float, serial: int, caption: String) -> void:
	var strength = 1.0 - age
	draw_rect(Rect2(Vector2.ZERO,canvas),Color(color,.32*strength))
	for i in range(8):
		var inset = float(i)*9.0
		draw_rect(Rect2(Vector2.ONE*inset,canvas-Vector2.ONE*inset*2.0),Color(color,.88*strength*(1.0-i/9.0)),false,10)
	for i in range(16):
		var x = float((i*137+serial*43)%int(canvas.x))
		draw_circle(Vector2(x,canvas.y-(i%3)*19),float(28+(i%4)*13),Color(.24,.025,.05,.8*strength))
	var message_y = canvas.y*.77
	var message_alpha = minf(1.0,strength*2.6)
	draw_rect(Rect2(canvas.x*.5-225,message_y-58,450,78),Color(.17,.035,.05,.9*message_alpha))
	label(caption,Vector2(canvas.x*.5,message_y),46,Color(1.0,.86,.8,message_alpha),true)

func draw_hud():
	var presentation=model.level.get("presentation",{})
	var canvas=Vector2(model.level.layout.width,model.level.layout.height)
	var stats=model.section_stats();var section=stats.section
	var context=model.presentation_context
	if model.phase == "running" and section.get("skippable", false):
		if context.mode == "player":
			var hint := "Enter / Esc / 开始键  跳过"
			var hint_width := font.get_string_size(hint, HORIZONTAL_ALIGNMENT_LEFT, -1, 24).x
			label(hint, Vector2(canvas.x - hint_width - 26, 42), 24, Color("#dbc8a8"), true)
		if section.has("hint"):
			draw_rect(Rect2(0, canvas.y - 85, canvas.x, 85), Color(.018, .025, .045, .82))
			label(section.hint, Vector2(canvas.x * .5, canvas.y - 32), 32, Color("#efd5a4"), true)
		if paper_hud != null and paper_hud.tracking_lost:
			paper_hud.draw_prompt(self, PaperHud.TRACKING_PROMPT)
		return
	if paper_hud != null:
		var lettering_screen := paper_hud.lettering_screen()
		if not lettering_screen.is_empty():
			paper_hud.draw_lettering_card(self, lettering_screen, section)
			return
		if model.phase == "result":
			paper_hud.draw_result(self, section, stats)
			return
		if section.has("station") and (context.mode != "player" or context.lifecycle == "running" or paper_hud.tracking_lost):
			paper_hud.draw_playing(self, section, stats)
			return
		if paper_hud.tracking_lost:
			paper_hud.draw_prompt(self, PaperHud.TRACKING_PROMPT)
			return
	draw_rect(Rect2(0,0,canvas.x,80),Color(.018,.025,.045,.8))
	label(presentation.get("title",""),Vector2(25,36),30)
	if not section.is_empty():
		var stations: Array = presentation.get("stations", [])
		if section.has("station"):
			var station_title: String = stations[int(section.station) - 1]
			var detail := "" if station_title == section.title else " · " + str(section.title)
			label("第 %d / %d 站 · %s%s" % [section.station, stations.size(), station_title, detail],Vector2(25,67),25)
		elif stats.section_total > 0:
			label("第 %d / %d %s · %s" % [section.index,stats.section_count,presentation.get("labels",{}).get("section_unit","段"),section.title],Vector2(25,67),25)
		else:
			label(section.title,Vector2(25,67),25)
		if stats.section_total > 0:
			label("本段 %d / %d · %s %d / %d" % [stats.section_cleared,stats.section_total,presentation.get("labels",{}).get("progress","完成"),stats.cleared,stats.total],Vector2(canvas.x*.47,48),27,Color("#dfbc77"),true)
	var resources=[]
	for field in model.level.get("hud",[]):resources.append(field.label+" "+str(int(model.resources[field.resource])))
	# Right-align resource text without depending on game-specific counter names.
	var resource_text="  ".join(resources)
	var width=font.get_string_size(resource_text,HORIZONTAL_ALIGNMENT_LEFT,-1,26).x
	label(resource_text,Vector2(canvas.x-width-25,45),26)
	if not section.is_empty() and model.phase != "result":
		if stats.section_total == 0:
			draw_rect(Rect2(0,canvas.y-85,canvas.x,85),Color(.018,.025,.045,.82))
			label(section.get("hint",""),Vector2(canvas.x*.5,canvas.y-32),32,Color("#efd5a4"),true)
		else:
			label(section.get("hint",""),Vector2(canvas.x*.5,canvas.y-22),25,Color("#dbc8a8"),true)
	if context.mode=="player" and context.lifecycle=="ready":
		draw_rect(Rect2(Vector2.ZERO,canvas),Color(.015,.02,.04,.72))
		label(presentation.get("title",""),Vector2(canvas.x*.5,canvas.y*.34),68,Color("#ebd8b0"),true)
		label(presentation.get("subtitle",""),Vector2(canvas.x*.5,canvas.y*.43),34,Color("#cfa773"),true)
		label(presentation.get("instructions",""),Vector2(canvas.x*.5,canvas.y*.58),29,Color("#dfd0b4"),true)
		var controls = "Enter 或点击开始 · 鼠标 / 光枪射击"
		if model.available_commands().has("RELOAD"):controls += " · R 换弹"
		if paper_hud != null:
			paper_hud.draw_action(self, false)
			label("Enter / 光枪开始键 · R 换弹", Vector2(canvas.x * .5, canvas.y * .81), 24, Color("#e3bd76"), true)
		else:
			label(controls,Vector2(canvas.x*.5,canvas.y*.72),30,Color("#e3bd76"),true)
	elif model.phase=="result":
		draw_rect(Rect2(Vector2.ZERO,canvas),Color(.02,.025,.045,.65))
		label(presentation.get("labels",{}).get("result_success","完成") if model.result=="clear" else presentation.get("labels",{}).get("result_failure","失败"),Vector2(canvas.x*.5,canvas.y*.4),62,Color("#e7c994"),true)
		label("%s %d / %d · Enter 或点击重试" % [presentation.get("labels",{}).get("progress","完成"),stats.cleared,stats.total],Vector2(canvas.x*.5,canvas.y*.54),32,Color("#e0c59e"),true)
		if model.result == "clear" and not section.is_empty() and stats.section_total == 0:
			label(section.get("hint",""),Vector2(canvas.x*.5,canvas.y*.48),29,Color("#e0c59e"),true)
	elif context.mode=="player" and context.lifecycle=="paused":
		draw_rect(Rect2(Vector2.ZERO,canvas),Color(.02,.025,.045,.5))
		label("已暂停",Vector2(canvas.x*.5,canvas.y*.44),56,Color("#e7c994"),true)
		label("Enter / Esc 继续",Vector2(canvas.x*.5,canvas.y*.54),30,Color("#e0c59e"),true)
