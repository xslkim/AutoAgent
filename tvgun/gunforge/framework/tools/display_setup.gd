extends Control
## Display settings and raw light-gun calibration for the shared player.
signal frame_changed
signal closed

const ScreenFrame = preload("res://core/screen_frame.gd")
const Calibration = preload("res://core/calibration.gd")
const FRAME_KEYS = ["white", "dark", "outer"]
const FIT_COUNT := 5
const POINTS = [Vector2(960, 540), Vector2(240, 200), Vector2(1680, 200),
	Vector2(1680, 880), Vector2(240, 880), Vector2(600, 360),
	Vector2(1320, 360), Vector2(1320, 720), Vector2(600, 720)]

var frame: ScreenFrame
var calibration: Calibration
var settings_path: String
var saved := ConfigFile.new()
var draft: ConfigFile
var stage := -1
var raw_points: Array[Vector2] = []
var max_error := 0.0
var candidate: Calibration
var feedback := ""
var font := SystemFont.new()

func configure(screen: ScreenFrame, gun_calibration: Calibration, path: String) -> void:
	frame = screen
	calibration = gun_calibration
	settings_path = path
	if not path.is_empty():
		saved.load(path)
	load_profile(saved, saved.get_value("display", "profile", "monitor"))
	font.font_names = PackedStringArray(["Microsoft YaHei", "Noto Sans CJK SC"])
	mouse_filter = Control.MOUSE_FILTER_STOP
	hide()

func load_profile(config: ConfigFile, profile: String) -> void:
	var defaults := ScreenFrame.new()
	defaults.configure(profile)
	frame.configure(profile)
	for key in FRAME_KEYS:
		frame.set(key, config.get_value(profile, key, defaults.get(key)))
	calibration.matrix = config.get_value(profile, "calibration", Calibration.new().matrix).duplicate()

func remember_profile() -> void:
	for key in FRAME_KEYS:
		draft.set_value(frame.profile, key, frame.get(key))
	draft.set_value(frame.profile, "calibration", calibration.matrix.duplicate())

func begin() -> void:
	draft = ConfigFile.new()
	draft.parse(saved.encode_to_text())
	stage = -1
	feedback = ""
	show()
	queue_redraw()

func switch_profile() -> void:
	remember_profile()
	load_profile(draft, "tv" if frame.profile == "monitor" else "monitor")
	feedback = ""
	frame_changed.emit()

func adjust_margin(delta: float) -> void:
	frame.outer = clampf(frame.outer + delta, 0.0, .12)
	frame_changed.emit()

func begin_calibration() -> void:
	stage = 0
	raw_points.clear()
	max_error = 0
	candidate = Calibration.new()
	queue_redraw()

func sample(raw: Vector2) -> void:
	if stage < 0 or not raw.is_finite():
		return
	if stage < FIT_COUNT:
		raw_points.append(raw)
	else:
		max_error = maxf(max_error, candidate.apply(raw).distance_to(POINTS[stage]))
	stage += 1
	if stage == FIT_COUNT and not candidate.fit(raw_points, POINTS.slice(0, FIT_COUNT)):
		end_calibration("未能拟合，请重新校准")
	elif stage == POINTS.size():
		if max_error < 10:
			calibration.matrix = candidate.matrix.duplicate()
			end_calibration("校准通过 · 最大误差 %.1f 像素 · Enter 保存" % max_error)
		else:
			end_calibration("独立检查未通过，请重新校准")
	queue_redraw()

func end_calibration(message: String) -> void:
	stage = -1
	candidate = null
	feedback = message
	queue_redraw()

func finish(save_changes: bool) -> void:
	if save_changes:
		remember_profile()
		draft.set_value("display", "profile", frame.profile)
		if not settings_path.is_empty():
			var path := ProjectSettings.globalize_path(settings_path)
			var pending := path + ".%d.tmp" % OS.get_process_id()
			var error := draft.save(pending)
			if error == OK:
				error = DirAccess.rename_absolute(pending, path)
			if error != OK:
				DirAccess.remove_absolute(pending)
				feedback = "无法保存显示设置 · 请重试"
				queue_redraw()
				return
		saved = draft
	else:
		load_profile(saved, saved.get_value("display", "profile", "monitor"))
	stage = -1
	candidate = null
	hide()
	frame_changed.emit()
	closed.emit()

func handle_key(keycode: Key) -> void:
	if keycode == KEY_ESCAPE or keycode == KEY_F2:
		if stage >= 0:
			end_calibration("校准已取消")
		else:
			finish(false)
		return
	if stage >= 0:
		return
	match keycode:
		KEY_ENTER, KEY_KP_ENTER: finish(true)
		KEY_F3: switch_profile()
		KEY_LEFT: adjust_margin(-.005)
		KEY_RIGHT: adjust_margin(.005)
		KEY_C: begin_calibration()

func caption(text: String, point: Vector2, font_size: int) -> void:
	var width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
	draw_string(font, point - Vector2(width * .5, 0), text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Color("#e9d5af"))

func _draw() -> void:
	if frame == null or not visible:
		return
	var content := frame.content_rect(size)
	var scale := content.size.x / 1776.0
	var center := content.get_center()
	var title_size := maxi(12, roundi(42 * scale))
	var text_size := maxi(10, roundi(32 * scale))
	draw_rect(content, Color("#182033"))
	if stage >= 0:
		var target := frame.norm_to_window(POINTS[stage], size)
		var ring := Color("#d7ad6d")
		draw_arc(target, 34 * scale, 0, TAU, 48, ring, 4 * scale, true)
		draw_arc(target, 15 * scale, 0, TAU, 32, ring, 3 * scale, true)
		draw_circle(target, 4 * scale, Color("#ecd3a0"), true, -1, true)
		var step := "校准 %d / 5" % (stage + 1) if stage < FIT_COUNT else "独立检查 %d / 4" % (stage - FIT_COUNT + 1)
		caption(step + " · 用光枪射击圆心", Vector2(center.x, content.position.y + 64 * scale), text_size)
		caption("Esc 返回显示设置", Vector2(center.x, content.end.y - 40 * scale), text_size)
		return
	for sx in [-1, 1]:
		for sy in [-1, 1]:
			var corner := center + Vector2(sx, sy) * (content.size * .5 - Vector2.ONE * 28 * scale)
			draw_line(corner, corner - Vector2(sx * 60 * scale, 0), Color("#cfa46b"), 5 * scale, true)
			draw_line(corner, corner - Vector2(0, sy * 60 * scale), Color("#cfa46b"), 5 * scale, true)
	var profile := "电视" if frame.profile == "tv" else "显示器"
	caption("显示设置 · " + profile, center - Vector2(0, 168 * scale), title_size)
	caption("确认白色追踪框和四角标记均完整可见", center - Vector2(0, 64 * scale), text_size)
	caption("← / → 调整边距 %.1f%%    F3 切换配置" % (frame.outer * 100), center, text_size)
	caption("C 光枪校准    Enter 保存    Esc 取消", center + Vector2(0, 84 * scale), text_size)
	caption(feedback, center + Vector2(0, 151 * scale), text_size)
