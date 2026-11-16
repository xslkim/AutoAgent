extends RefCounted
## Segment poses and ordered purification for the Ink Dragon encounter.

const LOCKED := "locked"
const ACTIVE := "active"
const PURIFIED := "purified"
const MOUTH := "mouth"

var _pivots: Array = []
var _order: Array = []
var _cursor := 0
var _mouth_cleared := false

func configure(pivots: Array, order: Array) -> bool:
	if pivots.is_empty() or order.size() != pivots.size():
		return false
	for index in pivots.size():
		if not pivots[index] is Array:
			return false
		var pair: Array = pivots[index]
		if pair.size() != 2 or not (pair[0] is Vector2 and pair[1] is Vector2):
			return false
		if not pair[0].is_finite() or not pair[1].is_finite() or pair[0].is_equal_approx(pair[1]):
			return false
		if order[index] != pivots.size() - 1 - index:
			return false
	_pivots = pivots.duplicate(true)
	_order = order.duplicate()
	reset()
	return true

func reset() -> void:
	_cursor = 0
	_mouth_cleared = false

func segment_state(index: int) -> String:
	var position := _order.find(index)
	if position < 0 or position > _cursor:
		return LOCKED
	return ACTIVE if position == _cursor else PURIFIED

func mouth_state() -> String:
	if _mouth_cleared:
		return PURIFIED
	return ACTIVE if not _order.is_empty() and _cursor == _order.size() else LOCKED

func apply_hit(id: String) -> bool:
	if id == MOUTH:
		if mouth_state() != ACTIVE:
			return false
		_mouth_cleared = true
		return true
	if _cursor >= _order.size() or id != "body_%02d" % (_order[_cursor] + 1):
		return false
	_cursor += 1
	return true

func complete() -> bool:
	return _mouth_cleared

func pose(origin: Vector2, clock: float, scale: float) -> Array[Transform2D]:
	var result: Array[Transform2D] = []
	var anchor := origin
	for index in _pivots.size():
		var pair: Array = _pivots[index]
		var angle := deg_to_rad(14 * sin(clock * 2.3 - index * 1.16))
		var transform := Transform2D(angle, anchor).scaled_local(Vector2.ONE * scale)
		transform.origin -= transform.basis_xform(pair[0])
		result.append(transform)
		anchor = transform * pair[1]
	return result
