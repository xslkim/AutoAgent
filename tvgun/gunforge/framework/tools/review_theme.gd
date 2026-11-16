extends RefCounted

const INK = Color("#eaf1fa")
const MUTED = Color("#aabbd0")
const ACCENT = Color("#92e2d2")

static func box(fill: Color, border: Color, radius: int = 8, padding: int = 0) -> StyleBoxFlat:
	var style = StyleBoxFlat.new()
	style.bg_color = fill
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(radius)
	style.content_margin_left = padding
	style.content_margin_right = padding
	style.content_margin_top = padding
	style.content_margin_bottom = padding
	return style

static func make(font: Font) -> Theme:
	var theme = Theme.new()
	theme.default_font = font
	theme.default_font_size = 15
	theme.set_constant("separation", "HBoxContainer", 8)
	theme.set_constant("separation", "VBoxContainer", 8)
	for type in ["Button", "OptionButton", "MenuButton", "TabContainer"]:
		theme.set_color("font_color", type, INK)
		theme.set_color("font_hover_color", type, Color.WHITE)
		theme.set_color("font_pressed_color", type, Color("#091e25"))
		theme.set_color("font_disabled_color", type, Color("#7d8da3"))
		theme.set_stylebox("normal", type, box(Color("#22344b"), Color("#47617c"), 7, 8))
		theme.set_stylebox("hover", type, box(Color("#324d68"), Color("#7a9db9"), 7, 8))
		theme.set_stylebox("pressed", type, box(ACCENT, Color("#b5f4e7"), 7, 8))
		theme.set_stylebox("hover_pressed", type, box(Color("#b5f4e7"), Color("#dcfff7"), 7, 8))
		theme.set_stylebox("disabled", type, box(Color("#192538"), Color("#2d3d53"), 7, 8))
		var focus = box(Color.TRANSPARENT, Color("#c6f5ff"), 7)
		focus.set_border_width_all(2)
		focus.draw_center = false
		theme.set_stylebox("focus", type, focus)
	theme.set_type_variation("ReviewPrimary", "Button")
	theme.set_stylebox("normal", "ReviewPrimary", box(Color("#16655d"), Color("#68cebb"), 7, 8))
	theme.set_stylebox("hover", "ReviewPrimary", box(Color("#247f74"), ACCENT, 7, 8))
	theme.set_stylebox("panel", "PanelContainer", box(Color("#152237"), Color("#31435c"), 10, 8))
	theme.set_color("font_color", "Label", INK)
	for type in ["TextEdit", "Tree", "GraphEdit", "PopupMenu"]:
		theme.set_stylebox("panel" if type in ["GraphEdit", "PopupMenu"] else "normal", type,
			box(Color("#142135"), Color("#3d536e"), 8, 8))
		theme.set_color("font_color", type, INK)
	theme.set_color("font_readonly_color", "TextEdit", Color("#c6d8eb"))
	theme.set_color("font_placeholder_color", "TextEdit", MUTED)
	theme.set_stylebox("read_only", "TextEdit", box(Color("#142135"), Color("#3d536e"), 8, 8))
	theme.set_color("font_selected_color", "TabContainer", ACCENT)
	theme.set_color("font_unselected_color", "TabContainer", MUTED)
	theme.set_stylebox("tab_selected", "TabContainer", box(Color("#253e52"), Color("#5fafa7"), 7, 8))
	theme.set_stylebox("tab_unselected", "TabContainer", box(Color("#18283e"), Color("#3d536e"), 7, 8))
	theme.set_stylebox("panel", "TabContainer", box(Color("#142135"), Color("#3d536e"), 8, 3))
	return theme
