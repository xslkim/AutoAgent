extends "res://tests/tadpole_campaign_tests.gd"
## Replay the full campaign and check the bridge scenery through the plaza handoff.

const BRIDGE_SCENERY := ["footbridge.bridge.cyclist_resident", "footbridge.bridge.cyclist_reaction", "footbridge.bridge.bicycle"]

func play() -> void:
	await super.play()
	if not handoffs.any(func(entry): return entry.station == "plaza"):
		check(false, "full route reaches the plaza")
		return
	var completed: Dictionary = session.snapshot()
	var bridge: Dictionary = handoffs.filter(func(entry): return entry.station == "footbridge")[0]
	var plaza: Dictionary = handoffs.filter(func(entry): return entry.station == "plaza")[0]
	session.seek(bridge.tick)
	check(model.current_section == "footbridge.footbridge" and BRIDGE_SCENERY.all(func(id): return model.entities[id].active),
		"the bridge cut spawns the resident, reaction pose and bike")
	check(carried() == bridge.counters, "safe scenery keeps the incoming counters")
	await capture("cyclist_bridge_entry")
	session.seek(plaza.tick - 1)
	var before := carried()
	check(model.entities[BRIDGE_SCENERY[0]].active and model.entities[BRIDGE_SCENERY[2]].visible,
		"the safe cyclist waits on the bridge until the plaza cut")
	session.step()
	check(station() == 5 and carried() == before and carried().rescued == bridge.counters.rescued,
		"bridge completion carries resources with no added rescue")
	check(BRIDGE_SCENERY.all(func(id): return not model.entities[id].active and not model.entities[id].visible)
		and not model.visual_items().any(func(item): return item.id in BRIDGE_SCENERY), "all bridge scenery leaves the model and scene")
	await capture("cyclist_plaza_handoff")
	session.restore(completed)
	print(JSON.stringify({"build_id": model.build.build_id, "bridge": bridge, "plaza": plaza,
		"scenery_removed_after_handoff": BRIDGE_SCENERY}))
