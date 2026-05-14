#!/usr/bin/env python3
"""Generate fixtures/godot-test-project/scenes/poc_playground.tscn."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "fixtures/godot-test-project/scenes/poc_playground.tscn"

HEAD = '''[gd_scene load_steps=5 format=3]

[ext_resource type="Texture2D" path="res://assets/ui/slot_bg.png" id="slot_bg"]
[ext_resource type="Texture2D" path="res://assets/ui/input_bg_normal.png" id="input_normal"]
[ext_resource type="Texture2D" path="res://assets/ui/input_bg_focused.png" id="input_focused"]
[ext_resource type="Texture2D" path="res://assets/ui/panel_bg.png" id="panel_bg"]

[node name="PocPlaygroundScene" type="CanvasLayer"]
'''


def click_node(name: str, x: int, y: int) -> str:
    return f'''
[node name="{name}" type="TextureRect" parent="."]
offset_left = {float(x)}
offset_top = {float(y)}
offset_right = {float(x + 120)}
offset_bottom = {float(y + 80)}
texture = ExtResource("slot_bg")
expand_mode = 1
stretch_mode = 6
metadata/autoagent_pinned_id = "{name}"
metadata/autoagent_logical_role = "button"
'''


def text_target() -> str:
    return '''
[node name="text_target" type="TextureRect" parent="."]
offset_left = 100.0
offset_top = 220.0
offset_right = 460.0
offset_bottom = 276.0
texture = ExtResource("input_normal")
expand_mode = 1
stretch_mode = 6
metadata/autoagent_pinned_id = "text_target"
metadata/autoagent_logical_role = "input"
metadata/autoagent_state_sprites = {
"normal": ExtResource("input_normal"),
"focused": ExtResource("input_focused")
}

[node name="text_target_text" type="Label" parent="text_target"]
offset_left = 12.0
offset_top = 16.0
offset_right = 348.0
offset_bottom = 40.0
text = ""
vertical_alignment = 1
metadata/autoagent_pinned_id = "text_target_text"
metadata/autoagent_logical_role = "text_display"
'''


def drag_pair() -> str:
    return '''
[node name="drag_source" type="TextureRect" parent="."]
offset_left = 100.0
offset_top = 320.0
offset_right = 200.0
offset_bottom = 420.0
texture = ExtResource("slot_bg")
expand_mode = 1
stretch_mode = 6
metadata/autoagent_pinned_id = "drag_source"
metadata/autoagent_logical_role = "drag_source"

[node name="drag_target" type="TextureRect" parent="."]
offset_left = 260.0
offset_top = 320.0
offset_right = 360.0
offset_bottom = 420.0
texture = ExtResource("slot_bg")
expand_mode = 1
stretch_mode = 6
metadata/autoagent_pinned_id = "drag_target"
metadata/autoagent_logical_role = "drop_target"
'''


def scroll_block(item_count: int) -> str:
    item_h = 72
    spacing = 8
    content_h = item_count * (item_h + spacing)
    out = [f'''
[node name="scroll_container" type="TextureRect" parent="."]
offset_left = 100.0
offset_top = 460.0
offset_right = 740.0
offset_bottom = 960.0
texture = ExtResource("panel_bg")
expand_mode = 1
stretch_mode = 6
clip_contents = true
metadata/autoagent_pinned_id = "scroll_container"
metadata/autoagent_logical_role = "scroll_container"

[node name="scroll_content" type="Control" parent="scroll_container"]
offset_left = 10.0
offset_top = 10.0
offset_right = 630.0
offset_bottom = {float(10 + content_h)}
metadata/autoagent_pinned_id = "scroll_content"
metadata/autoagent_logical_role = "image_only"
''']
    for i in range(1, item_count + 1):
        y = (i - 1) * (item_h + spacing)
        out.append(f'''
[node name="scroll_item_{i:03d}" type="TextureRect" parent="scroll_container/scroll_content"]
offset_left = 0.0
offset_top = {float(y)}
offset_right = 620.0
offset_bottom = {float(y + item_h)}
texture = ExtResource("slot_bg")
expand_mode = 1
stretch_mode = 6
metadata/autoagent_pinned_id = "scroll_item_{i:03d}"
metadata/autoagent_logical_role = "image_only"
''')
    return "".join(out)


def main() -> None:
    parts = [HEAD]
    parts.append(click_node("click_target", 100, 100))
    for i in range(1, 6):
        parts.append(click_node(f"click_target_variant_{i}", 100 + i * 140, 100))
    parts.append(text_target())
    parts.append(drag_pair())
    parts.append(scroll_block(30))
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
