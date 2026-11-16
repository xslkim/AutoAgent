extends RefCounted
## Common bounded event evaluation for neutral and registered rule packages.
static func run(host, incoming: Array):
	for id in host.level.event_order:
		if host.phase != "running":
			break
		var event = host.level.events[id]
		if int(host.fired.get(id, 0)) >= int(event.max_firings):
			continue
		var trigger = event.trigger
		var due = false
		var intent_num = host.tick * 1000
		if event.has("at_tick"):
			due = host.tick >= int(event.at_tick)
			intent_num = int(host.build.source_map[id].declared_absolute_ms) * int(host.level.tick_hz)
		elif trigger.has("after") and host.fired_time.has(trigger.after):
			intent_num = int(host.fired_time[trigger.after]) + int(trigger.delay_ms) * int(host.level.tick_hz)
			due = host.tick * 1000 >= intent_num
		elif trigger.has("on"):
			for topic in incoming:
				if topic.topic == trigger.on or topic.topic + ":" + topic.entity == trigger.on:
					due = true
		elif trigger.has("query"):
			due = host.compare(float(host.queries[trigger.query].value), trigger.compare, float(trigger.value))
		if not due:
			continue
		var allowed=true
		for guard in event.get("guards",[]):
			var value=host.entities[guard.entity][guard.field] if guard.has("entity") else (host.resources[guard.resource] if guard.has("resource") else host.queries[guard.query].value)
			if not host.compare(float(value),guard.compare,float(guard.value)):allowed=false;break
		if not allowed:continue
		host.fired[id] = int(host.fired.get(id, 0)) + 1
		host.fired_time[id] = intent_num
		host.trace.append({"tick":host.tick,"event_id":id,"topic":"event.fired"})
		for action_id in event.order:
			host.apply_action(event.actions[action_id])

