extends RefCounted

var config: Dictionary
var phase = "title"
var lives = 5
var ammo = 6
var score = 0
var wave = 0
var clock = 0.0
var total = 0.0
var lamp_until = -1.0
var lamp_amount = 0.0
var reload_until = -1.0
var last_shot = -10.0
var state_clock = 0.0
var rescued_at = -1.0
var enemies = []
var pickup_taken = false
var hits = 0
var shots = 0
var feedback = ""
var feedback_until = 0.0
var events = []
var lost_seconds = 0.0
var resume = 0.0
var auto_paused = false
var user_paused = false
var last_result = {}

func setup(data: Dictionary):
	if data.get("format","") == "gunforge-compiled-level-v1":
		var params = data.level.ruleset_data
		config = params.native_level.duplicate(true)
		var ordered = []
		for wave_id in config.wave_order:
			var current = config.waves[wave_id].duplicate(true)
			var enemies_by_id = current.enemies
			current.enemies = []
			for enemy_id in current.enemy_order:
				var entry = enemies_by_id[enemy_id].duplicate(true)
				entry.id = enemy_id
				current.enemies.append(entry)
			ordered.append(current)
		config.waves = ordered
		config.presentation = params.presentation.duplicate(true)
	else:
		config = data.duplicate(true)
	if not config.has("presentation"):
		config.presentation = JSON.parse_string(FileAccess.get_file_as_string("res://runtime/presentation.json"))
	reset()
	phase = "title"

func reset():
	lives = int(config.rules.lives)
	score = 0
	total = 0
	shots = 0
	hits = 0
	wave = 0
	begin_wave()
	phase = "playing"
	auto_paused = false
	user_paused = false
	lost_seconds = 0
	resume = 0

func begin_wave():
	clock = 0
	ammo = int(config.rules.magazine)
	lamp_until = -1
	lamp_amount = 0
	reload_until = -1
	last_shot = -10
	rescued_at = -1
	pickup_taken = false
	enemies.clear()
	for entry in config.waves[wave].enemies:
		enemies.append({"at":entry.at,"deadline":entry.deadline,"status":"waiting","hit_at":-10.0,"warned":false})
	phase = "playing"
	state_clock = 0
	notify("wave", "第 %d 波" % (wave+1))

func notify(kind: String, message: String):
	feedback = message
	feedback_until = clock+1.1
	events.append({"event":kind,"wave":wave,"t":clock})

func resident_active() -> bool:
	return phase == "playing" and clock>=config.waves[wave].resident_at

func resident_time() -> float:
	return maxf(0,clock-config.waves[wave].resident_at)

func pickup_active() -> bool:
	return phase == "playing" and not pickup_taken and clock>=config.waves[wave].pickup_at

func exposure_at(center: Vector2, origin: Vector2, shift: Vector2, canvas: Vector2, spill_image: Image) -> float:
	var mask_pos = center+origin+shift*float(config.presentation.light_parallax)
	return preload("res://core/spatial_queries.gd").mask_red(spill_image,mask_pos,canvas)*lamp_amount

func light_active(exposure: float) -> bool:
	return exposure>=float(config.presentation.soft_exposure)

func tick(dt: float, locked: bool):
	dt = maxf(0,dt)
	if phase not in ["playing","gap","transition"]:
		state_clock += dt
		if phase=="continue" and state_clock>=config.rules.continue_seconds:
			phase = "title"
		return
	if not locked:
		lost_seconds += dt
		resume = config.rules.resume_countdown
		if lost_seconds>=2:
			auto_paused = true
	else:
		lost_seconds = 0
		if auto_paused:
			resume = maxf(0,resume-dt)
			if resume<=0:
				auto_paused = false
	if user_paused or auto_paused:
		return
	total += dt
	if phase=="gap":
		state_clock += dt
		if state_clock>=config.rules.wave_gap:
			wave += 1
			begin_wave()
		return
	if phase=="transition":
		state_clock += dt
		if state_clock>=3:
			phase = "complete"
			notify("complete","巷口已点亮")
		return
	clock += dt
	if reload_until>=0 and clock>=reload_until:
		ammo = int(config.rules.magazine)
		reload_until = -1
		notify("reload_done","光已装满")
	lamp_amount = move_toward(lamp_amount,1.0 if clock<lamp_until else 0.0,dt/config.rules.light_fade_seconds)
	for enemy in enemies:
		if enemy.status=="waiting" and clock>=enemy.at:
			enemy.status = "alive"
		if enemy.status=="alive" and not enemy.warned and clock>=enemy.deadline-config.rules.warning_seconds:
			enemy.warned = true
			notify("warning","墨鸦即将来袭")
		if enemy.status=="alive" and clock>=enemy.deadline:
			damage("墨鸦来袭")
			enemy.status = "gone"
	if phase=="playing" and clock>=config.waves[wave].duration:
		phase = "transition" if wave==config.waves.size()-1 else "gap"
		state_clock = 0
		notify("gap","准备下一波")

func damage(reason: String):
	lives = maxi(0,lives-1)
	notify("hurt",reason)
	if lives==0:
		phase = "continue"
		state_clock = 0

func reload():
	if phase!="playing" or auto_paused or user_paused or reload_until>=0 or ammo==config.rules.magazine:
		return
	reload_until = clock+config.rules.reload_seconds
	notify("reload","正在回光")

func command(event: String, hit: Dictionary = {}, offscreen = false, locked = true) -> bool:
	if event=="START":
		if phase in ["title","complete"]:
			reset()
			return true
		if user_paused:
			user_paused = false
			return true
	if event=="COIN" and phase=="continue":
		lives = int(config.rules.lives)
		score = 0
		begin_wave()
		notify("continue","从本波重新开始")
		return true
	if event=="RELOAD":
		reload()
		return true
	if event!="SHOT" or phase!="playing" or not locked or auto_paused or user_paused:
		return false
	if offscreen:
		reload()
		return true
	if reload_until>=0 or clock-last_shot<config.rules.shot_interval:
		return false
	last_shot = clock
	if ammo<=0:
		notify("empty","光已用尽 · 移出屏幕扣扳机或按 R")
		return false
	ammo -= 1
	shots += 1
	var kind = hit.get("kind","miss")
	var id = hit.get("id","")
	if id == "resident_ink" and rescued_at >= 0:
		hit = hit.duplicate(true)
		hit.kind = "miss"
		kind = "miss"
		id = ""
	last_result = hit
	if kind in ["primary","weak"]:
		hits += 1
		if id=="lamp":
			lamp_until = clock+config.rules.lamp_seconds
			score += int(config.presentation.scores.lamp)
			notify("lamp","灯亮了 · 墨已软化")
		elif id=="resident_ink":
			rescued_at = clock
			score += int(config.presentation.scores.rescue)
			notify("rescue","纸居民获救")
		elif enemy_ids().has(id):
			var index = enemy_ids().find(id)
			if index>=0 and index<enemies.size() and enemies[index].status=="alive":
				enemies[index].status = "defeated"
				enemies[index].hit_at = clock
				score += int(config.presentation.scores.weak if kind=="weak" else config.presentation.scores.primary)
				notify("hit","印迹命中" if kind=="weak" else "净化墨鸦")
		elif id=="pickup":
			pickup_taken = true
			if config.presentation.pickup.types[wave]=="light":
				ammo = int(config.rules.magazine)
			else:
				lives = mini(int(config.rules.lives),lives+1)
			score += int(config.presentation.scores.pickup)
			notify("pickup","收到了光" if config.presentation.pickup.types[wave]=="light" else "灯芯已补充")
	elif kind=="protected":
		score = maxi(0,score-int(config.presentation.scores.protected))
		notify("protected","请只净化胸口的墨")
	elif kind=="invalid":
		notify("blocked","墨已硬化 · 先点灯")
	elif kind=="blocker":
		notify("blocked","被前景纸层挡住")
	else:
		notify("miss","未命中")
	return true

func snapshot() -> Dictionary:
	return {"phase":phase,"wave":wave,"time":clock,"total":total,"ammo":ammo,"lives":lives,"score":score,
			"rescued":rescued_at>=0,"lamp":lamp_amount,"enemies":enemies.duplicate(true),
			"paused":auto_paused or user_paused,"lost":lost_seconds,"resume":resume,
			"shots":shots,"hits":hits,"feedback":feedback,"events":events.duplicate(true)}

const SAVED_FIELDS = ["config", "phase", "lives", "ammo", "score", "wave", "clock", "total", "lamp_until", "lamp_amount", "reload_until", "last_shot", "state_clock", "rescued_at", "enemies", "pickup_taken", "hits", "shots", "feedback", "feedback_until", "events", "lost_seconds", "resume", "auto_paused", "user_paused", "last_result"]

func save_state() -> Dictionary:
	var data = {"version":1}
	for key in SAVED_FIELDS:
		var value = get(key)
		data[key] = value.duplicate(true) if value is Dictionary or value is Array else value
	return data

func restore_state(data: Dictionary):
	assert(data.version == 1)
	for key in SAVED_FIELDS:
		assert(data.has(key), "Incomplete rules snapshot")
		var value = data[key]
		set(key, value.duplicate(true) if value is Dictionary or value is Array else value)

func enemy_ids() -> Array:
	var ids = []
	for i in range(config.waves[wave].enemies.size()):
		ids.append(str(config.waves[wave].enemies[i].get("id","crow_%d" % i)))
	return ids
