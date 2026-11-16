extends Node2D

const Pose = preload("res://runtime/game_pose.gd")
const Item = preload("res://core/raster_item.gd")
const Painter = preload("res://core/raster_layer.gd")
const Puppet = preload("res://core/puppet.gd")
var model
var images = {}
var textures = {}
var background
var lighting
var actors
var foreground
var purification
var font: SystemFont
var puppet = Puppet.new()
var station: Dictionary
var crow_model: Dictionary
var hit_items = []
var drawn_hit_items = []
var logical_pose = {}
var pose_revision = 0
var drawn_pose_revision = 0
var aim_points = {}
var cursor = Vector2(-100,-100)
var locked = true
var debug = false
var flash_time = -10.0
var flash_point = Vector2.ZERO
var last_kind = ""
var view_clock = 0.0
var network_mode = false
var profile = "monitor"
var extras = ""
var calibration_ui = {}
var light_exposure = 0.0
var draw_time_ms = 0.0
var overlay: Node2D

func load_image(path: String):
	if images.has(path):
		return
	var loaded = load("res://runtime/"+path)
	var image = loaded.get_image()
	if image.is_empty():
		push_error("Missing runtime texture "+path)
		return
	images[path] = image
	textures[path] = loaded

func _ready():
	font = SystemFont.new()
	font.font_names = PackedStringArray(["Microsoft YaHei","Noto Sans CJK SC"])
	station = JSON.parse_string(FileAccess.get_file_as_string("res://runtime/station/station.json"))
	crow_model = JSON.parse_string(FileAccess.get_file_as_string("res://runtime/crow/enemy.json"))
	puppet.open("res://runtime/vendor")
	for layer in station.layers:
		load_image("station/"+layer.file)
	for light in station.lights:
		load_image("station/"+light.spill)
		load_image("station/"+light.glow)
	for key in ["body","core","core_hardened"]:
		load_image("crow/"+crow_model.files[key].file)
	load_image("crow/defeated.png")
	var hard = images["crow/core_hardened.png"].duplicate()
	var tint = Color("#dbc49a")
	for y in range(hard.get_height()):
		for x in range(hard.get_width()):
			tint.a = hard.get_pixel(x,y).a
			hard.set_pixel(x,y,tint)
	images["crow/core_hardened.png"] = hard
	textures["crow/core_hardened.png"] = ImageTexture.create_from_image(hard)
	for key in ["life_wick","life_wick_empty","ammo_light","ammo_light_empty","score_seal","prompt_bar","crosshair","continue_panel"]:
		load_image("ui/"+key+".png")
	for key in ["light","wick"]:
		load_image("pickups/pickup_"+key+".png")
	for i in range(3):
		load_image("ink_on_lamp/cover_%02d.png" % i)
	background = Painter.new()
	add_child(background)
	lighting = Painter.new()
	var add_material = ShaderMaterial.new()
	add_material.shader = load("res://shaders/additive.gdshader")
	lighting.material = add_material
	add_child(lighting)
	actors = Painter.new()
	add_child(actors)
	purification = Painter.new()
	var dissolve = ShaderMaterial.new()
	dissolve.shader = load("res://shaders/dissolve.gdshader")
	purification.material = dissolve
	add_child(purification)
	foreground = Painter.new()
	add_child(foreground)
	overlay = Node2D.new()
	overlay.draw.connect(_draw_hud)
	add_child(overlay)
	build_pose()

func build_pose():
	pose_revision += 1
	var composer = Pose.new()
	composer.model = model
	composer.station = station
	composer.crow_model = crow_model
	composer.images = images
	composer.textures = textures
	composer.puppet = puppet
	logical_pose = composer.compose(view_clock)
	hit_items = logical_pose.hit_items
	aim_points = logical_pose.aim_points
	light_exposure = logical_pose.light_exposure

func update_frame():
	if not is_instance_valid(background) or logical_pose.is_empty():
		return
	var began = Time.get_ticks_usec()
	var pose = logical_pose
	drawn_hit_items = pose.hit_items.duplicate()
	drawn_pose_revision = pose_revision
	background.refresh(pose.background)
	lighting.refresh(pose.lighting)
	actors.refresh(pose.actors)
	purification.refresh(pose.purification)
	purification.material.set_shader_parameter("progress",pose.dissolve_progress)
	foreground.refresh(pose.foreground)
	overlay.queue_redraw()
	draw_time_ms = (Time.get_ticks_usec()-began)/1000.0

func label(text: String, point: Vector2, size = 30, color = Color("#e4c7a5")):
	var width = font.get_string_size(text,HORIZONTAL_ALIGNMENT_LEFT,-1,size).x
	overlay.draw_string(font,point-Vector2(width/2,0),text,HORIZONTAL_ALIGNMENT_LEFT,-1,size,color)

func _draw_hud():
	if not font or not model:
		return
	var hud=model.config.presentation.hud
	for i in range(int(model.config.rules.lives)):
		var key = "life_wick" if i<model.lives else "life_wick_empty"
		overlay.draw_texture_rect(textures["ui/"+key+".png"],Rect2(hud.life_origin[0]+i*hud.life_stride,hud.life_origin[1],hud.life_size[0],hud.life_size[1]),false)
	for i in range(int(model.config.rules.magazine)):
		var key = "ammo_light" if i<model.ammo else "ammo_light_empty"
		overlay.draw_texture_rect(textures["ui/"+key+".png"],Rect2(hud.ammo_origin[0]+i*hud.ammo_stride,hud.ammo_origin[1],hud.ammo_size[0],hud.ammo_size[1]),false)
	overlay.draw_texture_rect(textures["ui/score_seal.png"],Rect2(hud.score_rect[0],hud.score_rect[1],hud.score_rect[2],hud.score_rect[3]),false)
	label(str(model.score),Vector2(hud.score_rect[0]+hud.score_rect[2]*.5,hud.score_rect[1]+hud.score_rect[3]*4.0/7.0),32)
	var text = ""
	if model.phase=="title":
		overlay.draw_rect(Rect2(0,0,1776,936),Color(0.02,.03,.06,.68))
		label("纸 灯 城",Vector2(888,340),76)
		label("夜市巷口",Vector2(888,407),32)
		label("点灯驱墨 · 只净化居民胸口的墨",Vector2(888,475),30)
		label("按 Enter 或 START 开始",Vector2(888,560),36)
		label("鼠标射击 · R 换弹 · F11 全屏 · G 光枪 · C 校准 · F2 显示设置",Vector2(888,650),25)
	elif model.phase=="continue":
		overlay.draw_rect(Rect2(0,0,1776,936),Color(.02,.03,.06,.68))
		overlay.draw_texture_rect(textures["ui/continue_panel.png"],Rect2(558,258,660,420),false)
		label("灯芯已熄灭",Vector2(888,390),42)
		label("按 5 / COIN 续关",Vector2(888,478),34)
		label("重来本波 · 分数清零",Vector2(888,540),28)
	elif model.phase=="complete":
		overlay.draw_rect(Rect2(0,0,1776,936),Color(.02,.03,.06,.66))
		label("巷口已点亮",Vector2(888,365),62)
		label("得分 %d · 命中 %d / %d" % [model.score,model.hits,model.shots],Vector2(888,466),34)
		label("Enter 再玩一次",Vector2(888,568),34)
	elif model.phase=="transition":
		overlay.draw_rect(Rect2(0,0,1776*clampf(model.state_clock/2,0,1),936),Color("#292d42"))
	elif model.auto_paused or model.user_paused:
		overlay.draw_rect(Rect2(0,0,1776,936),Color(.02,.03,.06,.65))
		label("已暂停" if model.user_paused else ("请对准屏幕" if not locked else "恢复中 %d"%ceil(model.resume)),Vector2(888,455),46)
	else:
		if not locked:
			text = "请对准屏幕"
		elif model.reload_until>=0:
			text = "回光中…"
		elif model.clock<model.feedback_until:
			text = model.feedback
		elif model.phase=="gap":
			text = "下一波 · 可以换弹"
		elif model.wave==0 and model.clock<12:
			text = "射灯 → 墨软化 → 净墨救人"
	if text!="":
		overlay.draw_texture_rect(textures["ui/prompt_bar.png"],Rect2(588,24,600,72),false)
		label(text,Vector2(888,70),28)
	if locked and model.phase=="playing":
		overlay.draw_texture_rect(textures["ui/crosshair.png"],Rect2(cursor-Vector2(20,20),Vector2(40,40)),false,Color(1,1,1,.65))
	if view_clock-flash_time<.3:
		var elapsed = view_clock-flash_time
		var color = Color("#d9a066")
		color.a = 1-elapsed/.3
		overlay.draw_arc(flash_point,12+elapsed*95,0,TAU,32,color,3)
		for i in range(8):
			var v = Vector2.from_angle(i*TAU/8)
			overlay.draw_line(flash_point+v*(18+elapsed*80),flash_point+v*(34+elapsed*90),color,3)
	for i in range(model.enemies.size()):
		var enemy = model.enemies[i]
		var id = model.enemy_ids()[i]
		if enemy.status=="alive" and enemy.get("warned",false) and aim_points.has(id):
			var pulse = .5+.5*sin(view_clock*TAU*float(model.config.presentation.warning.pulse_hz))
			overlay.draw_arc(aim_points[id],float(model.config.presentation.warning.radius[0])+(float(model.config.presentation.warning.radius[1])-float(model.config.presentation.warning.radius[0]))*pulse,0,TAU,40,Color(.85,.63,.4,.45+.4*pulse),3)
	if not extras.is_empty():
		overlay.draw_rect(Rect2(260,210,1256,450),Color(.04,.05,.09,.94))
		var lines = extras.split("\n")
		for i in range(lines.size()):
			label(lines[i],Vector2(888,265+i*48),27)
	if not calibration_ui.is_empty():
		overlay.draw_rect(Rect2(0,0,1776,936),Color(.03,.04,.07,.9))
		var p = calibration_ui.get("target",Vector2(888,468))
		overlay.draw_circle(p,22,Color("#d9a066"))
		overlay.draw_circle(p,5,Color("#2a1e3d"))
		label(calibration_ui.get("text",""),Vector2(888,130),28)
	if debug:
		for item in hit_items:
			if item.kind=="":
				continue
			overlay.draw_rect(item.bounds(),Color("#93c7a5") if item.kind=="protected" else Color("#cd7667"),false,1)
		label("%s | 波 %d | %.1fs | light %.2f | %s" % [profile,model.wave+1,model.clock,light_exposure,"UDP" if network_mode else "mouse"],Vector2(888,815),22)

func geometry_assets() -> Dictionary:
	var out = {}
	for key in images:
		out[key] = {"image":images[key],"texture":textures[key]}
	out["vendor_atlas"] = {"image":puppet.image,"texture":puppet.texture}
	return out
