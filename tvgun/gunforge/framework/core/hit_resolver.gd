extends RefCounted

func exact(point: Vector2, items: Array) -> Dictionary:
	for index in range(items.size()-1, -1, -1):
		var item = items[index]
		if item.kind != "" and item.bounds().has_point(point) and item.sample(point).a >= 0.5:
			return {"id": item.id, "kind": item.kind, "point": point, "assisted": false,"generation":item.generation}
	return {}

func resolve(point: Vector2, items: Array, assist = 15.0) -> Dictionary:
	var precise = exact(point, items)
	if not precise.is_empty():
		return precise
	var candidates = {}
	for dy in range(-int(assist), int(assist)+1):
		for dx in range(-int(assist), int(assist)+1):
			var offset = Vector2(dx, dy)
			if offset.length_squared() > assist * assist:
				continue
			var candidate = exact(point + offset, items)
			if candidate.get("kind", "") not in ["primary", "weak"]:
				continue
			var safe = true
			for step in range(1, int(ceil(offset.length()))+1):
				var probe = point + offset * float(step) / maxf(1, ceil(offset.length()))
				if exact(probe, items).get("kind", "") in ["protected", "blocker", "invalid"]:
					safe = false
					break
			if safe:
				candidates[candidate.id] = candidate
	if candidates.size() == 1:
		var result = candidates.values()[0]
		result.kind = "primary"
		result.assisted = true
		return result
	return {"kind": "miss", "id": "", "point": point, "assisted": false}
