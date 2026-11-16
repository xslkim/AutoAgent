extends SceneTree
## Compare the bound input and station handoffs of two complete campaign recordings.

func read_fixture(path: String) -> Variant:
	var file := FileAccess.open(path, FileAccess.READ)
	return file.get_var() if file != null else null

func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 2 or args.size() > 3:
		push_error("Expected two campaign recordings and an optional review recording output")
		quit(2)
		return
	var left = read_fixture(args[0])
	var right = read_fixture(args[1])
	if not left is Dictionary or not right is Dictionary \
		or not left.get("recording") is Dictionary or not right.get("recording") is Dictionary:
		push_error("Expected valid campaign recording files")
		quit(2)
		return
	var identical := var_to_bytes(left.recording.tape) == var_to_bytes(right.recording.tape)
	var handoffs_equal: bool = left.handoffs == right.handoffs
	var passed: bool = identical and handoffs_equal and not right.recording.tape.is_empty()
	if passed and args.size() == 3:
		var output := FileAccess.open(args[2], FileAccess.WRITE)
		if output == null or not output.store_var(right.recording):
			push_error("Could not save the review recording")
			quit(2)
			return
	print(JSON.stringify({"reference_build_id": left.recording.build_id, "build_id": right.recording.build_id,
		"inputs": right.recording.tape.size(), "serialized_input_tape_identical": identical,
		"handoffs_identical": handoffs_equal}))
	quit(0 if passed else 1)
