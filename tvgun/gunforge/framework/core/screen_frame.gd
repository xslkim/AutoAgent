extends RefCounted

const NORM = Vector2(1920, 1080)
var white: float = 24
var dark: float = 48
var outer: float = 0.022
var profile = "monitor"
var calibration = Transform2D.IDENTITY

func configure(name: String):
	profile = name
	outer = 0.045 if name == "tv" else 0.022

func screen_rect(window: Vector2) -> Rect2:
	var fit = minf(window.x / NORM.x, window.y / NORM.y) * (1 - 2 * outer)
	var size = NORM * fit
	return Rect2((window - size) / 2, size)

func content_rect(window: Vector2) -> Rect2:
	var frame = screen_rect(window)
	var scale = frame.size.x / NORM.x
	var inset = (white + dark) * scale
	return Rect2(frame.position + Vector2.ONE * inset, frame.size - Vector2.ONE * inset * 2)

func window_to_norm(point: Vector2, window: Vector2) -> Vector2:
	var rect = screen_rect(window)
	return (point - rect.position) / rect.size * NORM

func norm_to_window(point: Vector2, window: Vector2) -> Vector2:
	var rect = screen_rect(window)
	return rect.position + point / NORM * rect.size

func content_size() -> Vector2:
	return NORM - Vector2.ONE * 2 * (white + dark)

func to_content(point: Vector2) -> Vector2:
	return calibration * point - Vector2.ONE * (white + dark)

func offscreen(point: Vector2) -> bool:
	return not Rect2(Vector2.ZERO, NORM).has_point(calibration * point)
