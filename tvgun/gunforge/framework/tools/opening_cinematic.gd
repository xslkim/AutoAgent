extends Control
## Plays a local opening in the game's content rectangle.
signal completed

var video: VideoStreamPlayer
var subtitle: Label
var captions: Array = []
var caption_index := 0

func configure(directory: String) -> bool:
	return configure_video(directory.path_join("paper_lantern_city_opening_game.ogv"),
		directory.path_join("opening_subtitles.json"))

func configure_video(path: String, subtitle_path := "") -> bool:
	if not FileAccess.file_exists(path):
		push_warning("Opening video missing: " + path)
		return false
	if not subtitle_path.is_empty():
		var track: Variant = JSON.parse_string(FileAccess.get_file_as_string(subtitle_path))
		if track is Array:
			captions = track
		else:
			push_warning("Opening subtitle track unavailable")

	mouse_filter = MOUSE_FILTER_IGNORE
	clip_contents = true
	hide()
	set_process(false)
	var backdrop := ColorRect.new()
	backdrop.color = Color.BLACK
	backdrop.mouse_filter = MOUSE_FILTER_IGNORE
	add_child(backdrop)
	backdrop.set_anchors_and_offsets_preset(PRESET_FULL_RECT)

	var stream := VideoStreamTheora.new()
	stream.file = path
	video = VideoStreamPlayer.new()
	video.stream = stream
	video.expand = true
	video.mouse_filter = MOUSE_FILTER_IGNORE
	add_child(video)
	video.set_anchors_and_offsets_preset(PRESET_FULL_RECT)
	video.finished.connect(finish)

	subtitle = make_label()
	subtitle.set_anchors_and_offsets_preset(PRESET_BOTTOM_WIDE)
	subtitle.offset_top = -88
	subtitle.offset_bottom = -22
	subtitle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	subtitle.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	subtitle.add_theme_font_size_override("font_size", 25)

	var hint := make_label()
	hint.text = "Enter / Esc / 开始键  跳过"
	hint.set_anchors_and_offsets_preset(PRESET_TOP_WIDE)
	hint.offset_top = 12
	hint.offset_right = -18
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	return true

func make_label() -> Label:
	var result := Label.new()
	result.mouse_filter = MOUSE_FILTER_IGNORE
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["Microsoft YaHei", "Noto Sans CJK SC"])
	result.add_theme_font_override("font", font)
	result.add_theme_color_override("font_color", Color("#e8d3ad"))
	result.add_theme_color_override("font_outline_color", Color.BLACK)
	result.add_theme_constant_override("outline_size", 5)
	add_child(result)
	return result

func begin() -> void:
	show()
	video.play()
	set_process(true)

func _process(_delta: float) -> void:
	if not video.is_playing():
		finish()
		return
	var position := video.stream_position
	while caption_index < captions.size() and position >= float(captions[caption_index].end):
		caption_index += 1
	var line: Dictionary = captions[caption_index] if caption_index < captions.size() else {}
	subtitle.text = line.text if not line.is_empty() and position >= float(line.start) else ""

func finish() -> void:
	if not visible:
		return
	hide()
	set_process(false)
	video.stop()
	completed.emit()
