extends Node2D

var items = []

func _draw():
	for item in items:
		draw_set_transform_matrix(item.transform)
		draw_texture_rect_region(item.texture, Rect2(Vector2.ZERO,item.size), item.source, item.tint)
	draw_set_transform_matrix(Transform2D.IDENTITY)

func refresh(value: Array):
	items = value
	queue_redraw()
