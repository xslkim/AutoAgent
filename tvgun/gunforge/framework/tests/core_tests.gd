extends SceneTree

const Frame = preload("res://core/screen_frame.gd")
const Hit = preload("res://core/hit_resolver.gd")
const Item = preload("res://core/raster_item.gd")
const Link = preload("res://core/gun_input.gd")
const Cal = preload("res://core/calibration.gd")
var passed = []
var failed = []

func check(ok: bool, name: String):
	(passed if ok else failed).append(name)
	print(("PASS " if ok else "FAIL ")+name)

func square(at: Vector2, size: Vector2, kind: String, id: String):
	var item = Item.new()
	item.image = Image.create(int(size.x),int(size.y),false,Image.FORMAT_RGBA8)
	item.image.fill(Color.WHITE)
	item.size = size
	item.source = Rect2(Vector2.ZERO,size)
	item.transform = Transform2D(0,at)
	item.kind = kind
	item.id = id
	return item

func _initialize():
	var frame = Frame.new()
	for profile in ["monitor","tv"]:
		frame.configure(profile)
		for window in [Vector2(1280,720),Vector2(1920,1200),Vector2(3840,2160)]:
			var p = Vector2(320,840)
			check(frame.window_to_norm(frame.norm_to_window(p,window),window).distance_to(p)<.001,
				  "coordinate_roundtrip_%s_%s"%[profile,window])
	check(frame.offscreen(Vector2(-1,500)) and not frame.offscreen(Vector2(10,500)),"offscreen_excludes_white_border")
	var resolver = Hit.new()
	var paper = square(Vector2(80,80),Vector2(100,100),"protected","human")
	var ink = square(Vector2(110,110),Vector2(40,40),"primary","ink")
	check(resolver.resolve(Vector2(125,125),[paper,ink]).id=="ink","ink_over_paper_exact")
	check(resolver.resolve(Vector2(100,125),[paper,ink]).kind=="protected","paper_never_assisted_to_ink")
	check(resolver.resolve(Vector2(71,90),[paper,ink]).kind=="miss","outside_paper_has_no_penalty")
	var block = square(Vector2(100,100),Vector2(80,80),"blocker","cover")
	check(resolver.resolve(Vector2(125,125),[paper,ink,block]).kind=="blocker","front_cover_precedes_ink")
	var target = square(Vector2(200,100),Vector2(80,80),"primary","target")
	check(resolver.resolve(Vector2(192,130),[target]).assisted,"unique_visible_primary_assist")
	var second = square(Vector2(175,100),Vector2(8,80),"primary","second")
	check(resolver.resolve(Vector2(192,130),[target,second]).kind=="miss","ambiguous_primary_not_assisted")
	var guard = square(Vector2(196,100),Vector2(3,80),"protected","guard")
	check(resolver.resolve(Vector2(192,130),[target,guard]).kind=="miss","assist_cannot_cross_protected_paper")
	var link = Link.new()
	check(link.decode("100,200",0).size()==1,"legacy_aim")
	check(link.decode("SHOT",.05).size()==1 and link.decode("SHOT",.2).is_empty(),"legacy_shot_100ms_expiry")
	link = Link.new()
	check(link.decode("300,400,4,10",0).size()==1,"sequenced_aim")
	check(link.decode("LOST,12",.1).size()==1 and not link.valid,"LOST_immediate")
	check(link.decode("300,400,4,11",.2).is_empty() and not link.valid,"late_aim_cannot_restore_lock")
	check(link.decode("SHOT 300,400,13",.3).is_empty(),"SHOT_rejected_during_loss")
	link.decode("300,400,4,15",.4)
	check(link.decode("SHOT 300,400,14",.41).size()==1,"late_independent_shot_supported")
	check(link.decode("SHOT 300,400,14",.42).is_empty(),"duplicate_shot_rejected")
	check(link.decode("SHOT 300,400,11",.425).is_empty(),"pre_loss_shot_rejected_after_relock")
	check(link.decode("NaN,400,4,16",.43).is_empty(),"nonfinite_packet_rejected")
	check(link.decode("300,400,4,1",3).size()==1,"session_restarts_after_two_second_gap")
	link.decode("HELLO session-12345678",3.1)
	check(not link.valid and link.largest_aim==-1,"explicit_new_session_clears_state")
	link.decode("300,400,4,0",3.2)
	link.decode("HELLO session-12345678",3.3)
	check(link.valid,"repeated_HELLO_does_not_erase_lock")
	var cal = Cal.new()
	var to = [Vector2(960,540),Vector2(240,200),Vector2(1680,200),Vector2(1680,880),Vector2(240,880)]
	var from = []
	for p in to:
		from.append(Vector2(p.x*1.07+16,p.y*.96-20))
	check(cal.fit(from,to),"five_point_homography")
	var maximum = 0.0
	for p in [Vector2(600,360),Vector2(1320,360),Vector2(1320,720),Vector2(600,720)]:
		maximum = maxf(maximum,cal.apply(Vector2(p.x*1.07+16,p.y*.96-20)).distance_to(p))
	check(maximum<.001,"four_independent_checkpoints")
	check(not cal.fit([Vector2.ONE,Vector2.ONE,Vector2.ONE,Vector2.ONE,Vector2.ONE],to),"degenerate_calibration_rejected")
	var rules = load("res://runtime/game_rules.gd").new()
	var config = JSON.parse_string(FileAccess.get_file_as_string("res://runtime/level.json"))
	rules.setup(config)
	check(not rules.command("SHOT",{},false,true) and rules.ammo==6,"title_shot_consumed")
	rules.command("START")
	rules.command("SHOT",{"id":"lamp","kind":"primary"})
	check(rules.ammo==5 and rules.lamp_until>0,"lamp_uses_one_round")
	rules.tick(.2,true)
	rules.command("SHOT",{"id":"resident_ink","kind":"primary"})
	check(rules.rescued_at>=0,"resident_rescue")
	rules.tick(2.1,false)
	var before = rules.clock
	rules.tick(1,false)
	check(rules.auto_paused and rules.clock==before,"lost_pause_freezes_clock")
	rules.tick(.5,true)
	check(rules.auto_paused and rules.clock==before,"relock_countdown")
	rules.tick(.6,true)
	check(not rules.auto_paused,"relock_resumes_after_countdown")
	rules.ammo = 0
	rules.command("SHOT",{},true,true)
	rules.tick(.51,true)
	check(rules.ammo==6,"offscreen_reload")
	var prior_wave = rules.wave
	rules.lives = 1
	rules.damage("test")
	rules.command("COIN")
	check(rules.lives==5 and rules.ammo==6 and rules.score==0 and rules.wave==prior_wave and rules.clock==0,"continue_restores_wave_start")
	check(not rules.command("SHOT",{},false,false),"invalid_lock_cannot_hit")
	var report = {"passed":passed,"failed":failed,"total":passed.size()+failed.size()}
	var dest = ProjectSettings.globalize_path("res://../games/g01/reports/0B")
	DirAccess.make_dir_recursive_absolute(dest)
	var report_path = dest.path_join("core_tests.json")
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--report="):
			report_path = arg.trim_prefix("--report=")
	var file = FileAccess.open(report_path,FileAccess.WRITE)
	file.store_string(JSON.stringify(report,"\t"))
	quit(0 if failed.is_empty() else 1)
