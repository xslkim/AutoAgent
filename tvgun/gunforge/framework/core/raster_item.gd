extends RefCounted

var image: Image
var hit_image: Image
var texture: Texture2D
var source = Rect2()
var transform = Transform2D.IDENTITY
var size = Vector2.ZERO
var id = ""
var kind = ""
var z=0
var generation=0
var tint = Color.WHITE
var state_visual := false
var state_images: Array[Image] = []

func sample(point: Vector2) -> Color:
	var p = transform.affine_inverse() * point
	if not Rect2(Vector2.ZERO, size).has_point(p):
		return Color.TRANSPARENT
	var uv = p / size
	var xy = source.position + uv * source.size
	var x = clampi(int(xy.x), 0, image.get_width()-1)
	var y = clampi(int(xy.y), 0, image.get_height()-1)
	var color: Color = image.get_pixel(x, y) * tint
	if hit_image != null:
		color.a = hit_image.get_pixel(x, y).a * tint.a
	return color

func bounds() -> Rect2:
	return transform * Rect2(Vector2.ZERO, size)
