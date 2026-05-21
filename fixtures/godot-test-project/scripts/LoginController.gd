# AUTOAGENT_ALLOW_VISUAL
extends CanvasLayer
## LoginController — wires the login form to MockApi.
##
## Mirrors Unity LoginController.cs and UE ULoginController:
##   • admin / password  → hide login_panel, show welcome_panel + welcome_text
##   • anything else     → show error_label, keep login form visible
##
## Attach to the LoginScene root node (CanvasLayer).

const MockApiClass := preload("res://scripts/MockApi.gd")

@onready var _login_panel: Panel = $login_panel
@onready var _account_input: LineEdit = $login_panel/account_input_bg
@onready var _password_input: LineEdit = $login_panel/password_input_bg
@onready var _login_button: Button = $login_panel/login_button_bg
@onready var _error_label: Label = $login_panel/error_label
@onready var _welcome_panel: Panel = $welcome_panel
@onready var _welcome_text: Label = $welcome_panel/welcome_text

var _api: MockApiClass


func _ready() -> void:
	_api = MockApiClass.new()
	_error_label.text = ""
	_login_button.pressed.connect(_on_login_pressed)


func _on_login_pressed() -> void:
	var username := _account_input.text.strip_edges()
	var password := _password_input.text.strip_edges()
	var result := _api.login(username, password)
	if result == "ok":
		_login_panel.visible = false
		_welcome_panel.visible = true
		_welcome_text.visible = true
	else:
		_error_label.text = "Invalid credentials"
