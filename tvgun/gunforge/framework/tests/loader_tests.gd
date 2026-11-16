extends SceneTree
const Loader=preload("res://core/level_loader.gd")
var checks=[]
var failures=[]
func check(ok,label):
	(checks if ok else failures).append(label)
func _initialize():
	var path="";var assets="";var report=""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):assets=arg.trim_prefix("--assets=")
		if arg.begins_with("--report="):report=arg.trim_prefix("--report=")
	var build=JSON.parse_string(FileAccess.get_file_as_string(path))
	check(Loader.open(build,assets)!=null,"valid_cross_language_payload_and_build_digest")
	var broken=build.duplicate(true);broken.level.entities.target_a.x+=1
	check(Loader.open(broken,assets)==null and Loader.last_error=="Compiled payload checksum mismatch","mutated_compiled_design_rejected_by_payload_hash")
	broken=build.duplicate(true);broken.build_id="0".repeat(64)
	check(Loader.open(broken,assets)==null and Loader.last_error=="Build identity checksum mismatch","changed_build_identity_rejected")
	check(Loader.open({"format":"gunforge-compiled-level-v1","level":{},"tool_lock":{}},assets)==null and Loader.last_error=="Missing compiled-payload integrity contract; rebuild","partial_envelope_rejected_with_reason")
	var output={"passed":checks,"failed":failures,"build_id":build.build_id,"expected_failures":"see matching rejection reasons in this run log"}
	if not report.is_empty():FileAccess.open(report,FileAccess.WRITE).store_string(JSON.stringify(output,"\t"))
	print(JSON.stringify(output));quit(0 if failures.is_empty() else 1)
