extends SceneTree
const Loader=preload("res://core/level_loader.gd")
const Codec=preload("res://core/pose_codec.gd")
var passed=[]
var failed=[]
var model
func check(value,label):
	(passed if value else failed).append(label)
	print(("PASS " if value else "FAIL ")+label)
func step_to(at):
	while model.tick<at and model.phase=="running":model.step()
func reset_at(at):model.start();step_to(at)
func point_for(id,kind=""):
	var items=model.geometry()
	for item in items:
		if item.id!=id or (not kind.is_empty() and item.kind!=kind):continue
		var box=item.bounds()
		for y in range(int(box.position.y),int(box.end.y),3):
			for x in range(int(box.position.x),int(box.end.x),3):
				var point=Vector2(x+.5,y+.5)
				var hit=model.resolver.exact(point,items)
				if hit.get("id","")==id and (kind.is_empty() or hit.kind==kind):return point
	return null
func _initialize():call_deferred("run")
func run():
	var path="";var assets="";var report=""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):assets=arg.trim_prefix("--assets=")
		if arg.begins_with("--report="):report=arg.trim_prefix("--report=")
	model=Loader.open(JSON.parse_string(FileAccess.get_file_as_string(path)),assets)
	if model==null:quit(2);return
	reset_at(200)
	check(model.level.sections.size()==6 and model.section_stats().total==29,"six_sections_and_29_attackers")
	check(model.resources.ammo==80 and not model.available_commands().has("RELOAD"),"finite_ammo_without_magazine")
	var id="w1_crow_1";var before=model.entities[id].x
	step_to(215)
	check(abs(model.entities[id].x-before)>1,"continuous_entry_changes_bound_pose")
	var life=model.resources.lives;step_to(305)
	check(model.entities[id].motion_phase=="windup" and model.resources.lives==life,"readable_windup_precedes_damage")
	check(model.entities[id].pose_scale>2.4 and model.active_effects.values().any(func(e):return e.effect=="lunge_release"),"committed_lunge_visible_before_damage")
	step_to(306)
	check(model.resources.lives==life-1 and not model.active_effects.is_empty() and model.active_cues.values().any(func(c):return c.cue=="hurt"),"actual_attack_damages_with_effect_and_sound")
	reset_at(270)
	var age=model.entities[id].age_ticks
	var lamp=point_for("lamp")
	check(lamp!=null,"support_lamp_has_visible_alpha_target")
	model.command("SHOT",lamp);model.step()
	check(model.resources.ammo==79 and model.active_effects.values().any(func(e):return e.effect=="shot_spark"),"shot_consumes_one_round_and_emits_visible_trace")
	check(model.entities[id].stunned and model.entities.lamp.next_activation>model.tick,"lamp_stuns_visible_enemy_and_enters_cooldown")
	var stunned_age=model.entities[id].age_ticks
	for i in range(89):model.step()
	check(model.entities[id].age_ticks==stunned_age and model.resources.lives==5,"stun_freezes_motion_and_attack_clock_for_1500ms")
	model.step();check(model.entities[id].age_ticks==stunned_age,"stun_holds_all_90_following_intervals")
	model.step();check(model.entities[id].age_ticks==stunned_age+1,"local_clock_resumes_after_exact_stun_interval")
	model.next_shot=0;var cooldown=model.command("SHOT",lamp)
	check(cooldown.get("reason","")=="interaction_cooldown","support_cannot_be_spammed")
	reset_at(240)
	var old_pose=Codec.decode(Codec.encode(model.geometry(),model.geometry_assets()),model.geometry_assets())
	var old_point=point_for(id);model.spawn(id);model.next_shot=0
	var stale=model.command("SHOT",old_point,old_pose)
	check(stale.get("reason","")=="target_generation_changed" and model.entities[id].active,"frozen_old_generation_cannot_hit_respawn")
	# Isolate a real heavy actor; use its actual transformed alpha, not synthetic rectangles.
	model.start();model.spawn("w4_crow_1");model.entities.w4_crow_1.age_ticks=70
	preload("res://core/motion_pose.gd").update(model.entities.w4_crow_1,60)
	model.entities.w4_crow_1.x=650;model.entities.w4_crow_1.y=250
	var weak=point_for("w4_crow_1","weak");var primary=point_for("w4_crow_1","primary")
	check(weak!=null and primary!=null,"composite_body_and_weak_stamp_are_separately_hittable")
	model.command("SHOT",primary);model.step()
	check(model.entities.w4_crow_1.health==1 and model.entities.w4_crow_1.active,"heavy_body_requires_second_hit")
	model.next_shot=0;model.entities.w4_crow_1.x=650;model.entities.w4_crow_1.y=250
	weak=point_for("w4_crow_1","weak");model.command("SHOT",weak);model.step()
	var score=model.resources.score;model.next_shot=0;model.command("SHOT",weak);model.step()
	check(score==150 and model.resources.score==score,"one_purification_reward_for_composite_actor")
	model.start();model.spawn("w2_crow_3")
	var bolt="w2_crow_3.ink"
	model.apply_action({"op":"launch","entity":bolt,"source":"w2_crow_3","x":900,"y":800,"duration_ms":1250})
	for i in range(40):model.step()
	var saved=bytes_to_var(var_to_bytes(model.save_state()))
	var aim=point_for(bolt);check(aim!=null,"moving_ink_projectile_has_interceptable_alpha")
	model.command("SHOT",aim);model.step()
	var expected=var_to_bytes(model.save_state())
	check(model.resources.score==25 and not model.entities[bolt].active,"intercept_awards_score_and_removes_projectile")
	model.restore_state(saved);model.command("SHOT",aim);model.step()
	check(var_to_bytes(model.save_state())==expected,"snapshot_restores_projectile_effects_sound_and_award_exactly")
	model.start();model.apply_action({"op":"launch","entity":bolt,"source":"w2_crow_3","x":900,"y":800,"duration_ms":1250})
	for i in range(75):model.step()
	check(model.resources.lives==4 and not model.entities[bolt].active,"unintercepted_projectile_causes_real_damage")
	reset_at(2500)
	# Survive to the rescue scene using restoration of lives, solely for isolated geometry testing.
	model.start()
	for i in range(2500):model.resources.lives=5;model.step()
	var rescue=point_for("resident_ink");check(rescue!=null,"rescue_ink_bound_to_animated_resident_pose")
	model.command("SHOT",rescue);model.step()
	check(model.resources.rescued==1 and not model.entities.resident_ink.active,"rescue_is_a_real_distinct_target")
	model.start()
	model.resources.ammo=1
	var empty_space=Vector2(890,110)
	model.command("SHOT",empty_space)
	step_to(60)
	check(model.command("RELOAD").get("reason")=="reload_unavailable" and model.resources.ammo==0,"reload_cannot_refill_finite_ammo")
	check(model.command("SHOT",empty_space).get("reason")=="empty" and model.shots==1 and model.resources.ammo==0,"empty_ammo_blocks_firing")
	var output={"passed":passed,"failed":failed,"build_id":model.build.build_id,"scope":"software mechanics, not human difficulty or real lightgun feel"}
	if not report.is_empty():FileAccess.open(report,FileAccess.WRITE).store_string(JSON.stringify(output,"\t"))
	print(JSON.stringify(output));quit(0 if failed.is_empty() else 1)
