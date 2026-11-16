extends RefCounted
## CPU pose composition: no scene-tree, draw, material, clock or GPU readback.
const Item = preload("res://core/raster_item.gd")
var model
var station: Dictionary
var crow_model: Dictionary
var images: Dictionary
var textures: Dictionary
var puppet
var hit_items = []
var aim_points = {}
var light_exposure = 0.0
var dissolve_progress = 0.0

func image_item(path: String, pos: Vector2, size: Vector2, kind = "", id = ""):
	var item = Item.new()
	item.image = images[path]
	item.texture = textures[path]
	item.source = Rect2(Vector2.ZERO,item.image.get_size())
	item.transform = Transform2D(0,pos)
	item.size = size
	item.id = id
	item.kind = kind
	return item

func compose(view_clock: float) -> Dictionary:
	var cfg = model.config.presentation
	var camera = Vector2(cfg.camera.amplitude[0]*sin(view_clock*cfg.camera.rate[0]),cfg.camera.amplitude[1]*sin(view_clock*cfg.camera.rate[1]))
	var breath = Vector2(cfg.breath.amplitude[0]*sin(view_clock*cfg.breath.rate[0]),cfg.breath.amplitude[1]*sin(view_clock*cfg.breath.rate[1]))
	var shift = camera+breath
	var bg = []
	var fg = []
	var body = []
	var lights = []
	var evaporating = []
	hit_items = []
	aim_points.clear()
	var origin = Vector2(station.content_origin[0],station.content_origin[1])
	var lamp_pos = Vector2.ZERO
	for layer in station.layers:
		var pos = Vector2(layer.pos[0],layer.pos[1])-origin-shift*layer.parallax
		var item = image_item("station/"+layer.file,pos,Vector2(layer.draw_size[0],layer.draw_size[1]))
		if layer.get("blocks_shots",false):
			item.kind = "blocker"
			item.id = layer.id
			fg.append(item)
		else:
			bg.append(item)
		if layer.id=="lamp":
			lamp_pos = pos
			var lamp = Item.new()
			lamp.image = item.image
			lamp.texture = item.texture
			lamp.source = Rect2(cfg.lamp.hit_rect[0],cfg.lamp.hit_rect[1],cfg.lamp.hit_rect[2],cfg.lamp.hit_rect[3])
			lamp.transform = Transform2D(0,pos+Vector2(cfg.lamp.hit_rect[0],cfg.lamp.hit_rect[1]))
			lamp.size = Vector2(cfg.lamp.hit_rect[2],cfg.lamp.hit_rect[3])
			lamp.id = "lamp"
			lamp.kind = "primary"
			hit_items.append(lamp)
			aim_points.lamp = pos+Vector2(cfg.lamp.aim[0],cfg.lamp.aim[1])
	var cover = image_item("ink_on_lamp/cover_%02d.png" % int(cfg.lamp.cover_order[model.wave]),lamp_pos+Vector2(cfg.lamp.cover_origin[0],cfg.lamp.cover_origin[1]),Vector2(cfg.lamp.cover_size[0],cfg.lamp.cover_size[1]))
	cover.tint.a = 1-model.lamp_amount
	body.append(cover)
	for light in station.lights:
		var pos = -origin-shift*float(cfg.light_parallax)
		var spill = image_item("station/"+light.spill,pos,Vector2(station.canvas[0],station.canvas[1]))
		spill.tint = Color(.85,.63,.40,model.lamp_amount*.7)
		lights.append(spill)
		var glow = image_item("station/"+light.glow,pos,Vector2(station.canvas[0],station.canvas[1]))
		glow.tint.a = model.lamp_amount
		lights.append(glow)
	if model.resident_active():
		var rescued = model.rescued_at>=0
		var time = model.clock-model.rescued_at if rescued else model.resident_time()
		var rescue_duration = float(puppet.clips["rescued_bounce"].duration)
		var clip = "rescued_bounce" if rescued and time<rescue_duration else ("thank" if rescued else "struggle")
		var person = puppet.items(clip,maxf(0,time-(rescue_duration if clip=="thank" else 0)),Vector2(cfg.resident_origin[0],cfg.resident_origin[1])-shift*float(cfg.actor_parallax),not rescued,not rescued)
		body.append_array(person)
		hit_items.append_array(person)
		for item in person:
			if item.id=="resident_ink":
				aim_points.resident_ink = item.transform * (item.size * Vector2(.5,.5))
	for i in range(model.enemies.size()):
		var enemy = model.enemies[i]
		if enemy.status not in ["alive","defeated"]:
			continue
		var fade = clampf((model.clock-enemy.hit_at)/float(cfg.crow.dissolve_seconds),0,1) if enemy.status=="defeated" else 0.0
		if fade>=1:
			continue
		var center = Vector2(cfg.crow.origin[0]+cfg.crow.amplitude[0]*sin(view_clock*cfg.crow.rate[0]),cfg.crow.origin[1]+cfg.crow.amplitude[1]*sin(view_clock*cfg.crow.rate[1]))-shift*float(cfg.actor_parallax)
		light_exposure = model.exposure_at(center,origin,shift,Vector2(station.canvas[0],station.canvas[1]),images["station/"+station.lights[0].spill])
		var soft = model.light_active(light_exposure)
		var scale = float(cfg.crow.draw_size)/cfg.crow.canvas_size
		var recoil = float(cfg.crow.recoil)*exp(-float(cfg.crow.recoil_decay)*maxf(0,model.clock-enemy.hit_at)) if enemy.status=="defeated" else 0.0
		center.x += recoil
		if enemy.status=="defeated":
			var gone = image_item("crow/defeated.png",center-Vector2.ONE*float(cfg.crow.draw_size)*.5,Vector2.ONE*float(cfg.crow.draw_size))
			evaporating.append(gone)
			dissolve_progress = fade
			continue
		for key in ["body","core" if soft else "core_hardened"]:
			var info = crow_model.files[key]
			var pos = center+(Vector2(info.crop_origin[0],info.crop_origin[1])-Vector2.ONE*float(cfg.crow.canvas_size)*.5)*scale
			var sprite = image_item("crow/"+info.file,pos,Vector2(info.size[0],info.size[1])*scale,
					("primary" if soft else "invalid") if key=="body" else ("weak" if soft else "invalid"),model.enemy_ids()[i])
			sprite.tint.a = 1-fade
			body.append(sprite)
			if enemy.status=="alive":
				hit_items.append(sprite)
		aim_points[model.enemy_ids()[i]] = center+Vector2(0,20)
	if model.pickup_active():
		var key = cfg.pickup.types[model.wave]
		var at = Vector2(cfg.pickup.origin[0],cfg.pickup.origin[1])-shift*float(cfg.actor_parallax)+Vector2(0,cfg.pickup.amplitude_y*sin(view_clock*cfg.pickup.rate))
		var pickup = image_item("pickups/pickup_"+key+".png",at-Vector2.ONE*float(cfg.pickup.size)*.5,Vector2.ONE*float(cfg.pickup.size),"primary","pickup")
		body.append(pickup)
		hit_items.append(pickup)
		aim_points.pickup = at
	hit_items.append_array(fg)
	return {"background":bg,"lighting":lights,"actors":body,"purification":evaporating,
		"foreground":fg,"hit_items":hit_items,"aim_points":aim_points.duplicate(true),
		"light_exposure":light_exposure,"dissolve_progress":dissolve_progress}
