extends RefCounted
const Runtime = preload("level_runtime.gd")
static var last_error=""
static func refuse(message):
	last_error=message
	push_error(message)
	return null
static func local_path(root,path):
	root=root.replace("\\","/");path=path.replace("\\","/")
	var candidate=root.path_join(path).simplify_path()
	var prefix=root.simplify_path().trim_suffix("/")+"/"
	return candidate if candidate.to_lower().begins_with(prefix.to_lower()) else ""
static func open(compiled, asset_root):
	last_error=""
	asset_root=asset_root.replace("\\","/")
	if not compiled is Dictionary or compiled.get("format","")!="gunforge-compiled-level-v1":return refuse("Not a compiled level")
	if not compiled.has("tool_lock") or not compiled.has("level"):return refuse("Missing level lock")
	if compiled.get("payload_algorithm","")!="numeric-f64le-v1":return refuse("Missing compiled-payload integrity contract; rebuild")
	var payload={"level":compiled.level,"source_map":compiled.source_map,"source_manifest":compiled.source_manifest}
	if preload("level_integrity.gd").digest(payload)!=compiled.payload_sha256:return refuse("Compiled payload checksum mismatch")
	if JSON.stringify(compiled.source_manifest,"",true).sha256_text()!=compiled.source_revision:return refuse("Source manifest identity mismatch")
	var identity={"source_revision":compiled.source_revision,"tool_lock":compiled.tool_lock,"payload_sha256":compiled.payload_sha256}
	if JSON.stringify(identity,"",true).sha256_text()!=compiled.build_id:return refuse("Build identity checksum mismatch")
	if not Engine.get_version_info().string.begins_with(compiled.tool_lock.godot+"-"):return refuse("Engine version differs from locked build")
	var catalog_path=asset_root.path_join("gunforge/level_design/specs/capabilities-v1.json")
	if FileAccess.get_sha256(catalog_path)!=compiled.tool_lock.get("capability_catalog_sha256",""):return refuse("Capability catalog changed; rebuild candidate")
	if FileAccess.get_sha256(asset_root.path_join("gunforge/framework/core/level_runtime.gd"))!=compiled.tool_lock.get("runtime_sha256",""):return refuse("Runtime changed; rebuild candidate")
	for section in ["profile_files","core_files"]:
		if not compiled.tool_lock.has(section):return refuse("Incomplete implementation lock")
		for path in compiled.tool_lock[section]:
			var target=local_path(asset_root,path)
			if target.is_empty() or FileAccess.get_sha256(target)!=compiled.tool_lock[section][path]:return refuse("Implementation changed: "+path)
	for resource in compiled.level.resources.values():
		var target=local_path(asset_root,resource.path)
		if target.is_empty() or FileAccess.get_sha256(target)!=resource.sha256:return refuse("Resource changed: "+resource.path)
	var catalog=JSON.parse_string(FileAccess.get_file_as_string(catalog_path))
	if not catalog.rulesets.has(compiled.level.ruleset):return refuse("Unregistered ruleset")
	var profile=catalog.rulesets[compiled.level.ruleset]
	var model=load(asset_root.path_join(profile.adapter_source)).new() if profile.has("adapter_source") else Runtime.new()
	model.setup(compiled,asset_root)
	return model
