extends RefCounted
## Frozen nearest-neighbour red-channel query in explicitly supplied canvas pixels.
static func mask_red(image:Image,point:Vector2,canvas:Vector2)->float:
	var uv=point/canvas
	var pixel=(uv*Vector2(image.get_size())).clamp(Vector2.ZERO,Vector2(image.get_size())-Vector2.ONE)
	return image.get_pixel(int(pixel.x),int(pixel.y)).r
