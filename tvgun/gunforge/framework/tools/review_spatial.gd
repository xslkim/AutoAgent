extends Control
## The shared frontal pose anchors the approximate inspection diagrams.
signal entity_selected(id: String, center: Vector2, pose_scale: float)

enum Mode { SIDE, TOP }

const PAPER = Color("#142135")
const LINE = Color("#3d536e")
const INK = Color("#eaf1fa")
const MUTED = Color("#aabbd0")
const PLAYER = Color("#80b9ff")
const TARGET = Color("#8ce3d2")
const PROTECTED = Color("#f4ca87")
const PROJECTILE = Color("#ff9e91")
const INTERACTIVE = Color("#c1affc")

var mode = Mode.SIDE
var model
var label_font: Font
var front_reference: Callable
var selected_id := ""
var markers: Array[Dictionary] = []

func project(center: Vector2, pose_scale: float, canvas: Vector2, plot: Rect2) -> Vector2:
	var near = clampf(0.5 + log(maxf(pose_scale, 0.01)) / log(2.0) * 0.26, 0.07, 0.93)
	var screen = (center / canvas).clamp(Vector2(0.04, 0.05), Vector2(0.96, 0.95))
	var coordinates = Vector2(screen.x, near) if mode == Mode.TOP else Vector2(1.0 - near, screen.y)
	return plot.position + coordinates * plot.size

func caption(at: Vector2, value: String, font_size: int = 14, color: Color = INK, width: float = -1.0) -> void:
	draw_string(label_font, at, value, HORIZONTAL_ALIGNMENT_LEFT, width, font_size, color)

func arrow(at: Vector2, direction: Vector2, color: Color, length: float) -> void:
	var back = at - direction * length
	var edge = direction.orthogonal() * length * 0.42
	draw_colored_polygon(PackedVector2Array([at, back + edge, back - edge]), color)

func badge(at: Vector2, number: int, color: Color, radius: float = 10.0, filled: bool = true) -> void:
	draw_circle(at, radius + 2.0, Color("#0b1423"), true, -1.0, true)
	draw_circle(at, radius, color if filled else PAPER, true, -1.0, true)
	if not filled:
		draw_arc(at, radius, 0.0, TAU, 20, color, 1.8, true)
	var value = str(number)
	var half_width = label_font.get_string_size(value, HORIZONTAL_ALIGNMENT_LEFT, -1, 12).x * 0.5
	caption(at + Vector2(-half_width, 4.0), value, 12, Color("#0b1423") if filled else color)

func draw_diagram(plot: Rect2, top: bool) -> void:
	draw_rect(plot, Color("#101e30"))
	for band in range(4):
		var zone = Rect2(plot.position, plot.size)
		if top:
			zone.position.y += band * plot.size.y * 0.25
			zone.size.y *= 0.25
		else:
			zone.position.x += band * plot.size.x * 0.25
			zone.size.x *= 0.25
		draw_rect(zone, Color(PLAYER, 0.03 + (band if top else 3 - band) * 0.027))
	draw_rect(plot, LINE, false)
	var middle = plot.get_center()
	var eye: Vector2
	var forward: Vector2
	var far_a: Vector2
	var far_b: Vector2
	if top:
		eye = Vector2(middle.x, plot.end.y + 12)
		forward = Vector2.UP
		far_a = plot.position
		far_b = Vector2(plot.end.x, plot.position.y)
		caption(plot.position + Vector2(6, -8), "远处", 13, MUTED)
		caption(Vector2(plot.position.x, plot.end.y + 24), "画面左侧", 13, MUTED)
		caption(plot.end + Vector2(-56, 24), "画面右侧", 13, MUTED)
		caption(eye + Vector2(-38, 31), "玩家 / 镜头", 14, PLAYER)
		draw_dashed_line(Vector2(plot.position.x, middle.y), Vector2(plot.end.x, middle.y), LINE, 1.0, 6.0)
	else:
		eye = Vector2(plot.position.x - 14, middle.y)
		forward = Vector2.RIGHT
		far_a = Vector2(plot.end.x, plot.position.y)
		far_b = plot.end
		caption(plot.position + Vector2(6, -8), "画面上方", 13, MUTED)
		caption(Vector2(plot.position.x + 6, plot.end.y + 23), "画面下方", 13, MUTED)
		caption(plot.end + Vector2(-27, 23), "远处", 13, MUTED)
		caption(eye + Vector2(-20, 32), "玩家", 14, PLAYER)
		draw_dashed_line(Vector2(middle.x, plot.position.y), Vector2(middle.x, plot.end.y), LINE, 1.0, 6.0)
	draw_line(eye, far_a, Color(PLAYER, 0.17), 1.0, true)
	draw_line(eye, far_b, Color(PLAYER, 0.17), 1.0, true)
	draw_circle(eye, 11.0, Color("#203d5d"), true, -1.0, true)
	draw_arc(eye, 11.0, 0.0, TAU, 24, PLAYER, 1.5, true)
	draw_line(eye, eye + forward * 27, PLAYER, 2.0, true)
	arrow(eye + forward * 28, forward, PLAYER, 8.0)

func collect_markers(geometry: Array, canvas: Vector2, plot: Rect2) -> void:
	var targets = {}
	for item in geometry:
		if item.id.is_empty() or item.kind in ["", "blocker", "decoration"]:
			continue
		var bounds: Rect2 = item.bounds()
		if not Rect2(Vector2.ZERO, canvas).intersects(bounds):
			continue
		if targets.has(item.id):
			targets[item.id].bounds = targets[item.id].bounds.merge(bounds)
		else:
			targets[item.id] = {"bounds": bounds, "kind": item.kind}
	var ids = targets.keys()
	ids.sort()
	for id in ids:
		var entity: Dictionary = model.entities.get(id, {})
		var pose_scale: float = entity.get("pose_scale", 1.0)
		var center: Vector2 = targets[id].bounds.get_center()
		var color = TARGET
		var role = "目标"
		if targets[id].kind == "protected":
			color = PROTECTED
			role = "保护对象"
		elif entity.get("template") == "projectile":
			color = PROJECTILE
			role = "弹体"
		elif entity.get("template") == "activation_source":
			color = INTERACTIVE
			role = "可射击机关"
		var frames: Array = entity.get("motion_override", entity.get("motion", {})).get("frames", [])
		var has_depth = frames.any(func(frame): return frame.has("scale"))
		if frames.size() >= 2:
			var path = PackedVector2Array()
			var half_size = Vector2(entity.width, entity.height) * 0.5
			for frame in frames:
				path.append(project(Vector2(frame.x, frame.y) + half_size, frame.get("scale", 1.0), canvas, plot))
			var selected = id == selected_id
			var trail = Color(color, 0.94 if selected else 0.55)
			draw_polyline(path, trail, 3.5 if selected else 2.0, true)
			for i in range(1, path.size()):
				var delta = path[i] - path[i - 1]
				if delta.length() > 22.0:
					arrow(path[i - 1].lerp(path[i], 0.68), delta.normalized(), trail, 10.0)
		markers.append({
			"id": id, "point": project(center, pose_scale, canvas, plot),
			"center": center, "scale": pose_scale, "color": color, "role": role,
			"number": markers.size() + 1, "has_depth": has_depth,
		})

func draw_context(region: Rect2, geometry: Array, canvas: Vector2) -> void:
	draw_rect(region, PAPER)
	draw_rect(region, LINE, false)
	var origin = region.position + Vector2(12, 0)
	caption(origin + Vector2(0, 23), "同帧 · 玩家正面", 15)
	var inset = Rect2(origin + Vector2(0, 34), Vector2(region.size.x - 24, (region.size.x - 24) * 0.5625))
	draw_rect(inset, Color("#0c1525"))
	var frame: Rect2 = front_reference.call(self, inset, geometry)
	for marker in markers:
		var normalized = (marker.center / canvas).clamp(Vector2(0.04, 0.06), Vector2(0.96, 0.94))
		marker["front"] = frame.position + normalized * frame.size
		badge(marker.front, marker.number, marker.color, 8.0)
	var y = inset.end.y + 26.0
	caption(Vector2(origin.x, y), "本帧对象  %d" % markers.size(), 14)
	if markers.is_empty():
		caption(Vector2(origin.x, y + 24), "此刻没有可标记的对象", 13, MUTED)
		caption(Vector2(origin.x, y + 45), "拖动下方时间轴查看", 13, MUTED)
		return
	var list_end = region.end.y
	if model.phase == "result":
		list_end -= 26.0
		caption(Vector2(origin.x, region.end.y - 12), "本局已结束，可往前拖时间轴", 12, MUTED, region.size.x - 24)
	var rows = maxi(0, floori((list_end - y - 14.0) / 24.0))
	for i in range(mini(rows, markers.size())):
		var marker = markers[i]
		var at = Vector2(origin.x + 9, y + 22.0 + i * 24.0)
		var row = Rect2(at - Vector2(9, 10), Vector2(region.size.x - 24, 22))
		if i == rows - 1 and markers.size() > rows:
			caption(at + Vector2(-8, 5), "另有 %d 项，点图中编号查看" % (markers.size() - i), 12, MUTED, row.size.x)
			break
		if marker.id == selected_id:
			draw_rect(row.grow(1), Color("#284358"))
		marker["row"] = row
		badge(at, marker.number, marker.color, 8.0)
		caption(at + Vector2(17, 5), "%s · %s" % [marker.role, marker.id], 13, INK, row.size.x - 17)

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color("#0e192b"))
	draw_rect(Rect2(Vector2.ZERO, size), LINE, false)
	markers.clear()
	if model == null or label_font == null or not front_reference.is_valid():
		return
	var top = mode == Mode.TOP
	var context_width = clampf(size.x * 0.27, 177, 242)
	var plot = Rect2(64 if top else 57, 98, size.x - context_width - 107, size.y - 192)
	var context = Rect2(size.x - context_width - 14, 16, context_width, size.y - 32)
	caption(Vector2(18, 30), "俯视  /  从上往下看" if top else "侧视  /  从侧面看", 21)
	caption(Vector2(18, 56), "蓝色箭头从玩家位置指向画面深处。", 14, MUTED)
	draw_diagram(plot, top)
	var canvas = Vector2(model.level.layout.width, model.level.layout.height)
	var geometry: Array = model.geometry()
	collect_markers(geometry, canvas, plot)
	for marker in markers:
		if marker.id == selected_id:
			draw_arc(marker.point, 16.0, 0.0, TAU, 24, PLAYER, 2.0, true)
		badge(marker.point, marker.number, marker.color, 10.0, marker.has_depth)
	draw_context(context, geometry, canvas)
	caption(Vector2(18, size.y - 30), "编号对应正面小窗    ·    线和箭头表示配置的路线", 13)
	caption(Vector2(18, size.y - 10), "远近按缩放估算，空心编号放在中线作为参考。", 12, MUTED)

func _gui_input(event: InputEvent) -> void:
	if not event is InputEventMouseButton or not event.pressed or event.button_index != MOUSE_BUTTON_LEFT:
		return
	var nearest = {}
	var best = 18.0
	for marker in markers:
		if marker.has("row") and marker.row.has_point(event.position):
			nearest = marker
			break
		var distance = minf(marker.point.distance_to(event.position), marker.front.distance_to(event.position))
		if distance < best:
			best = distance
			nearest = marker
	if not nearest.is_empty():
		selected_id = nearest.id
		entity_selected.emit(nearest.id, nearest.center, nearest.scale)
		queue_redraw()
	accept_event()
