extends Control

# Godot sample with several visual-write violations.

func _ready():
    $LoginPanel.modulate = Color.RED          # violation: modulate_write
    $LoginPanel.self_modulate = Color.WHITE   # violation: self_modulate_write
    $LoginPanel.position = Vector2(100, 200)  # violation: position_write
    $LoginPanel.size = Vector2(640, 480)      # violation: size_write
    $LoginPanel.visible = false               # violation: visible_write
    $Bg.texture = preload("res://foo.png")    # violation: texture_write
    $LoginPanel.show()                        # violation: show_call
    $WelcomePanel.hide()                      # violation: hide_call
