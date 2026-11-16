extends RefCounted
## Fixed-step clock. Catch-up is bounded per rendered frame; debt is retained.
var hz: int = 60
var max_steps: int = 120
var tick: int = 0
var debt: float = 0.0

func setup(rate: int = 60, budget: int = 120):
	assert(rate > 0 and budget > 0)
	hz = rate
	max_steps = budget
	tick = 0
	debt = 0.0

func advance_frame(seconds: float, callback: Callable, interrupted := Callable()) -> int:
	assert(is_finite(seconds) and seconds >= 0)
	debt += seconds
	var count = mini(max_steps, int(floor((debt + 1e-10) * hz)))
	for i in range(count):
		tick += 1
		debt -= 1.0 / hz
		callback.call(tick, 1.0 / hz)
		if interrupted.is_valid() and interrupted.call():
			debt = 0.0
			return i + 1
	if absf(debt) < 1e-10:
		debt = 0.0
	return count

func step(callback: Callable):
	tick += 1
	callback.call(tick, 1.0 / hz)

func snapshot() -> Dictionary:
	return {"version":1,"hz":hz,"max_steps":max_steps,"tick":tick,"debt":debt}

func restore(data: Dictionary):
	assert(data.version == 1 and data.hz > 0 and data.max_steps > 0)
	assert(data.tick >= 0 and is_finite(float(data.debt)) and data.debt >= 0)
	hz = int(data.hz)
	max_steps = int(data.max_steps)
	tick = int(data.tick)
	debt = float(data.debt)
