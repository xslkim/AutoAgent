extends SceneTree
## Native read-only review prototype; simulation and hit geometry share LevelRuntime.
const Loader = preload("res://core/level_loader.gd")
const Session = preload("res://core/level_session.gd")
const Codec = preload("res://core/pose_codec.gd")
const CuePlayer=preload("res://core/level_audio.gd")
const Timeline=preload("res://tools/review_timeline.gd")
const SpatialView = preload("res://tools/review_spatial.gd")
const ReviewTheme = preload("res://tools/review_theme.gd")
class Preview:
	extends Control
	var model
	var owner_tool
	var shown = []
	var textures = {}
	var scale_factor = 1.0
	var origin = Vector2.ZERO
	var overlay = true
	var native_viewport
	func contour(item):
		var image=item.image
		var key="edge:"+str(image.get_instance_id())+":"+str(item.source)+":"+str(item.tint.a)
		if textures.has(key):return textures[key]
		var edge=Image.create(image.get_width(),image.get_height(),false,Image.FORMAT_RGBA8)
		edge.fill(Color.TRANSPARENT)
		for y in range(maxi(0,int(item.source.position.y)),mini(image.get_height(),int(ceil(item.source.end.y)))):
			for x in range(maxi(0,int(item.source.position.x)),mini(image.get_width(),int(ceil(item.source.end.x)))):
				if image.get_pixel(x,y).a*item.tint.a<.5:continue
				for offset in [Vector2i(-1,0),Vector2i(1,0),Vector2i(0,-1),Vector2i(0,1)]:
					var q=Vector2i(x,y)+offset
					if not item.source.has_point(Vector2(q)) or q.x<0 or q.y<0 or q.x>=image.get_width() or q.y>=image.get_height() or image.get_pixel(q.x,q.y).a*item.tint.a<.5:
						edge.set_pixel(x,y,Color.WHITE);break
		textures[key]=ImageTexture.create_from_image(edge)
		return textures[key]
	func _gui_input(event):
		if model==null or not event is InputEventMouseButton or event.button_index!=MOUSE_BUTTON_LEFT:
			return
		var point = (event.position-origin)/scale_factor
		if owner_tool.has_method("handle_action_pointer") and owner_tool.handle_action_pointer(point, event.pressed):
			accept_event()
			return
		if not event.pressed:return
		var canvas = Vector2(model.level.layout.width,model.level.layout.height)
		if Rect2(Vector2.ZERO,canvas).has_point(point):
			owner_tool.queue_shot(point,shown)
	func _draw():
		draw_rect(Rect2(Vector2.ZERO,size),Color("#111827"))
		if model == null:return
		var canvas = Vector2(model.level.layout.width,model.level.layout.height)
		scale_factor = minf(size.x/canvas.x,size.y/canvas.y)
		origin = (size-canvas*scale_factor)*.5
		shown = model.geometry()
		owner_tool.session.submit(shown)
		draw_scene(self, Rect2(origin, canvas * scale_factor), shown, overlay)

	func draw_reference(target: Control, region: Rect2, geometry: Array) -> Rect2:
		var canvas = Vector2(model.level.layout.width, model.level.layout.height)
		var fitted = canvas * minf(region.size.x / canvas.x, region.size.y / canvas.y)
		var destination = Rect2(region.position + (region.size - fitted) * 0.5, fitted)
		draw_scene(target, destination, geometry, false)
		return destination

	func draw_scene(target: Control, destination: Rect2, geometry: Array, show_contours: bool) -> void:
		var base = Transform2D(0, destination.position).scaled_local(Vector2.ONE * destination.size.x / model.level.layout.width)
		if native_viewport!=null:
			target.draw_texture_rect(native_viewport.get_texture(), destination, false)
			if not show_contours:
				return
		for item in geometry:
			target.draw_set_transform_matrix(base*item.transform)
			var color = Color("#59b8aa")
			if item.kind=="protected":color=Color("#d9ad6b")
			if item.kind=="invalid":color=Color("#556071")
			if item.kind=="blocker":color=Color("#293141")
			if native_viewport == null:
				var key = item.image.get_instance_id()
				if not textures.has(key):textures[key]=ImageTexture.create_from_image(item.image)
				target.draw_texture_rect_region(textures[key],Rect2(Vector2.ZERO,item.size),item.source,color)
			if show_contours and not item.kind.is_empty():target.draw_texture_rect_region(contour(item),Rect2(Vector2.ZERO,item.size),item.source,Color("#e2e8f0"))
		target.draw_set_transform_matrix(Transform2D.IDENTITY)
var model
var session=Session.new()
var clock
var preview
var spatial_view
var info
var event_tree
var slider
var note
var status
var source_label
var phase_label
var play_button
var sound_button
var alpha_button
var view_buttons: Array[Button] = []
var running = false
var adjusting = false
var build_path = ""
var asset_root = ""
var review_dir = ""
var capture_path = ""
var quit_capture = false
var evidence_dir=""
var audio
var speed=1.0
var previous_build={}
var loaded_path=""
var previous_path=""
var comparison_path=""
var initial_tick=-1
var smoke=false
var capture_tick=150
var recording_path=""
var timeline
var catalog_tree
var graph
var loop_enabled=false
var loop_a=0
var loop_b=0
var reload_button
var coin_button
func _initialize():
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):build_path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):asset_root=arg.trim_prefix("--assets=")
		if arg.begins_with("--reviews="):review_dir=arg.trim_prefix("--reviews=")
		if arg.begins_with("--capture="):capture_path=arg.trim_prefix("--capture=")
		if arg=="--quit-after-capture":quit_capture=true
		if arg.begins_with("--evidence="):evidence_dir=arg.trim_prefix("--evidence=")
		if arg=="--review-smoke":smoke=true
		if arg.begins_with("--capture-tick="):capture_tick=int(arg.trim_prefix("--capture-tick="))
		if arg.begins_with("--recording="):recording_path=arg.trim_prefix("--recording=" )
		if arg.begins_with("--compare="):comparison_path=arg.trim_prefix("--compare=")
		if arg.begins_with("--at-tick="):initial_tick=int(arg.trim_prefix("--at-tick="))
	call_deferred("open")
func button(parent,text,action):
	var node=Button.new()
	node.text=text
	node.custom_minimum_size.y=34
	node.pressed.connect(action)
	parent.add_child(node)
	return node

func tool_menu(parent: Control, title: String, actions: Dictionary) -> void:
	var menu = MenuButton.new()
	menu.text = title + "  ▾"
	menu.flat = false
	menu.custom_minimum_size.y = 34
	parent.add_child(menu)
	var popup = menu.get_popup()
	popup.theme = review_theme
	var callbacks = actions.values()
	for label in actions:
		popup.add_item(label)
	popup.id_pressed.connect(func(id): callbacks[id].call())

func label(parent: Control, caption: String, font_size: int = 15, color: Color = ReviewTheme.INK) -> Label:
	var node = Label.new()
	node.text = caption
	node.add_theme_font_size_override("font_size", font_size)
	node.add_theme_color_override("font_color", color)
	parent.add_child(node)
	return node

var review_theme: Theme

func open():
	if build_path.is_empty() or asset_root.is_empty():
		push_error("Use start_level_review.ps1 or supply --build and --assets")
		quit(2);return
	root.title="GunForge · 关卡查看器"
	root.size=Vector2i(1440,900)
	var content=Control.new();content.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT);root.add_child(content)
	var backdrop = ColorRect.new()
	backdrop.color = Color("#0c1525")
	backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	content.add_child(backdrop)
	backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var font=SystemFont.new();font.font_names=PackedStringArray(["Microsoft YaHei","Noto Sans CJK SC"])
	review_theme = ReviewTheme.make(font)
	content.theme = review_theme
	var margin=MarginContainer.new();margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["margin_left","margin_right","margin_top","margin_bottom"]:margin.add_theme_constant_override(side,16)
	content.add_child(margin)
	var column=VBoxContainer.new();margin.add_child(column)
	var header = HBoxContainer.new()
	column.add_child(header)
	var identity = VBoxContainer.new()
	identity.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	identity.add_theme_constant_override("separation", 1)
	header.add_child(identity)
	label(identity, "关卡查看器", 23)
	source_label = label(identity, "", 13, ReviewTheme.MUTED)
	button(header, "打开构建", choose_build)
	tool_menu(header, "版本", {"查看版本差异": show_diff, "切换上一版本": switch_previous, "采用当前候选": confirm_adopt})
	tool_menu(header, "回放", {"打开回放": choose_recording, "保存回放": save_recording, "最近输入判定": show_last_input})
	var toolbar_panel = PanelContainer.new()
	column.add_child(toolbar_panel)
	var toolbar = HBoxContainer.new()
	toolbar_panel.add_child(toolbar)
	play_button = button(toolbar, "▶ 播放", toggle_playback)
	play_button.theme_type_variation = "ReviewPrimary"
	play_button.custom_minimum_size.x = 88
	button(toolbar, "新一局", func():reset();running=true;refresh()).tooltip_text = "从头开始新的试玩"
	button(toolbar, "单帧", func():running=false;advance_once();refresh()).tooltip_text = "前进一帧"
	var speed_select = OptionButton.new()
	for text in ["0.5 倍速","1 倍速","2 倍速","4 倍速"]:speed_select.add_item(text)
	speed_select.select(1);speed_select.item_selected.connect(func(i):speed=[.5,1.0,2.0,4.0][i]);toolbar.add_child(speed_select)
	toolbar.add_child(VSeparator.new())
	label(toolbar, "视角", 13, ReviewTheme.MUTED)
	var views = ButtonGroup.new()
	for caption in ["玩家正面", "侧视", "俯视"]:
		var index = view_buttons.size()
		var option = button(toolbar, caption, func():select_view(index))
		option.toggle_mode = true
		option.button_group = views
		view_buttons.append(option)
	view_buttons[0].button_pressed = true
	toolbar.add_spacer(false)
	reload_button = button(toolbar, "换弹", func():queue_command("RELOAD"))
	coin_button = button(toolbar, "续关", func():queue_command("COIN"))
	alpha_button = button(toolbar, "命中轮廓", func():
		preview.overlay = alpha_button.button_pressed
		preview.queue_redraw())
	alpha_button.toggle_mode = true
	alpha_button.tooltip_text = "在玩家正面显示 Alpha 命中轮廓"
	sound_button = button(toolbar, "声音", func():
		audio.enabled = sound_button.button_pressed
		audio.sync(true))
	sound_button.toggle_mode = true
	var readout = HBoxContainer.new()
	column.add_child(readout)
	phase_label = label(readout, "", 14, ReviewTheme.ACCENT)
	status = label(readout, "", 14, ReviewTheme.MUTED)
	status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	status.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	var split=HSplitContainer.new();split.size_flags_vertical=Control.SIZE_EXPAND_FILL;column.add_child(split)
	var left=VBoxContainer.new();left.size_flags_horizontal=Control.SIZE_EXPAND_FILL;split.add_child(left)
	left.add_theme_constant_override("separation", 5)
	preview=Preview.new();preview.custom_minimum_size=Vector2(650,345);preview.size_flags_vertical=Control.SIZE_EXPAND_FILL;preview.owner_tool=self;left.add_child(preview)
	preview.clip_contents=true
	spatial_view = SpatialView.new()
	spatial_view.label_font = font
	spatial_view.front_reference = preview.draw_reference
	spatial_view.mouse_filter = Control.MOUSE_FILTER_STOP
	spatial_view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	spatial_view.entity_selected.connect(inspect_spatial_entity)
	preview.add_child(spatial_view)
	spatial_view.hide()
	var timeline_header = HBoxContainer.new()
	left.add_child(timeline_header)
	label(timeline_header, "时间轴", 15)
	label(timeline_header, "点击跳转", 12, ReviewTheme.MUTED)
	timeline_header.add_spacer(false)
	button(timeline_header, "标记 A", func():loop_a=clock.tick)
	button(timeline_header, "标记 B", func():loop_b=clock.tick)
	var loop = button(timeline_header, "循环 A–B", func():loop_enabled=not loop_enabled)
	loop.toggle_mode = true
	timeline=Timeline.new();timeline.owner_tool=self;timeline.custom_minimum_size=Vector2(650,102);left.add_child(timeline)
	timeline.font=font
	slider=HSlider.new();slider.step=1;slider.value_changed.connect(func(v):
		if not adjusting:jump(int(v)))
	left.add_child(slider)
	var right=VBoxContainer.new();right.custom_minimum_size=Vector2(340,0);split.add_child(right)
	var tabs=TabContainer.new();tabs.custom_minimum_size.y=186;right.add_child(tabs)
	event_tree=Tree.new();event_tree.name="事件";event_tree.columns=2;event_tree.column_titles_visible=true;event_tree.set_column_title(0,"时间 / 条件");event_tree.set_column_title(1,"事件");event_tree.item_selected.connect(select_event);tabs.add_child(event_tree)
	catalog_tree=Tree.new();catalog_tree.name="关卡树";catalog_tree.item_selected.connect(select_catalog);tabs.add_child(catalog_tree)
	graph=GraphEdit.new();graph.name="依赖图";graph.minimap_enabled=false;tabs.add_child(graph)
	label(right, "选中项详情", 14, ReviewTheme.MUTED)
	info=TextEdit.new();info.editable=false;info.wrap_mode=TextEdit.LINE_WRAPPING_BOUNDARY;info.size_flags_vertical=Control.SIZE_EXPAND_FILL;right.add_child(info)
	label(right, "关卡批注", 14)
	note=TextEdit.new();note.wrap_mode=TextEdit.LINE_WRAPPING_BOUNDARY;note.placeholder_text="期望怎样调整？哪些内容需要保留？";note.custom_minimum_size.y=78;right.add_child(note)
	button(right,"保存当前帧的批注",save_note).theme_type_variation = "ReviewPrimary"
	if not comparison_path.is_empty():
		var candidate_path = build_path
		build_path = comparison_path
		load_build()
		if model==null:return
		build_path = candidate_path
	load_build()
	if model==null:return
	if loaded_path!=build_path:
		quit(2)
		return
	if not recording_path.is_empty():
		var file=FileAccess.open(recording_path,FileAccess.READ)
		var record=file.get_var(false) if file!=null else null
		if not record is Dictionary or record.get("build_id","")!=model.build.build_id:
			push_error("Recording build mismatch");quit(2);return
		session.load_recording(record)
	if initial_tick>=0:jump(mini(initial_tick,session.max_tick))
	if smoke:
		await smoke_test();return
	if not capture_path.is_empty():
		if recording_path.is_empty():session.start()
		for i in range(capture_tick):session.step()
		refresh()
		await process_frame
		await RenderingServer.frame_post_draw
		var error=root.get_texture().get_image().save_png(capture_path)
		print(JSON.stringify({"capture":capture_path,"error":error}))
		if quit_capture:quit(0 if error==OK else 1)
func load_build():
	var compiled=JSON.parse_string(FileAccess.get_file_as_string(build_path))
	var next_model=Loader.open(compiled,asset_root)
	if next_model==null:
		if model==null:quit(2)
		else:status.text="构建校验失败；保留当前版本，请重新编译"
		return
	if model!=null:previous_build=model.build.duplicate(true);previous_path=loaded_path
	model=next_model;loaded_path=build_path;running=false
	preview.textures.clear()
	if preview.native_viewport!=null:preview.native_viewport.queue_free();preview.native_viewport=null
	if model.has_method("mount"):
		var native=SubViewport.new();native.size=Vector2i(model.level.layout.width,model.level.layout.height);native.disable_3d=true;native.render_target_update_mode=SubViewport.UPDATE_ALWAYS
		root.add_child(native);model.mount(native);preview.native_viewport=native
	session.setup(model);clock=session.clock
	if audio!=null:audio.queue_free()
	audio=CuePlayer.new();root.add_child(audio);audio.setup(model,asset_root)
	audio.enabled=model.level.get("presentation",{}).get("default_sound",false)
	preview.model=model
	spatial_view.model=model
	timeline.model=model
	update_version_label()
	slider.max_value=session.max_tick
	event_tree.clear();var tree_root=event_tree.create_item();tree_root.set_text(0,"事件依赖");event_tree.hide_root=true
	for id in model.level.event_order:
		var item=event_tree.create_item(tree_root);item.set_text(0,("%.3f 秒" % (float(model.build.source_map[id].tick)/60.0)) if model.build.source_map[id].has("tick") else "条件触发");item.set_text(1,id);item.set_metadata(0,id)
	if model.has_method("review_events"):
		for entry in model.review_events():
			var item=event_tree.create_item(tree_root);item.set_text(0,entry.when);item.set_text(1,entry.id);item.set_metadata(0,entry)
	populate_catalog();populate_graph()
	spatial_view.selected_id = ""
	info.text = "选择事件、关卡树中的项目，或点击画面上的对象以查看详情。"
	refresh()
func reset():
	running=false;session.start();clock=session.clock;refresh()
	audio.clear()

func switch_previous():
	if previous_path.is_empty():return
	var at = clock.tick
	build_path = previous_path
	load_build()
	if loaded_path==build_path:jump(mini(at,session.max_tick))
func asset_map():
	return model.geometry_assets()

func select_view(index: int) -> void:
	for i in range(view_buttons.size()):
		view_buttons[i].set_pressed_no_signal(i == index)
	spatial_view.mode = SpatialView.Mode.TOP if index == 2 else SpatialView.Mode.SIDE
	spatial_view.visible = index != 0
	alpha_button.disabled = spatial_view.visible
	spatial_view.queue_redraw()

func inspect_spatial_entity(id: String, center: Vector2, pose_scale: float) -> void:
	info.text = "对象  %s\n选取时刻  %.2f 秒\n正面位置  (%d, %d) 像素\n画面缩放  %.2f×\n\n%s" % [
		id, clock.tick / 60.0, roundi(center.x), roundi(center.y), pose_scale,
		JSON.stringify(model.entities.get(id, {}), "  "),
	]

func toggle_playback() -> void:
	if model.phase == "result":
		jump(0)
	running = not running
	refresh()

func queue_shot(point,pose):
	if spatial_view.visible:return
	if not running:
		var hit=model.resolver.exact(point,pose)
		var id=hit.get("id","")
		info.text=JSON.stringify({"selected_entity":id,"geometry_hit":hit,"parameters":model.entities.get(id,{}),"queries":model.queries},"  ")
		return
	if model.phase!="running":return
	session.enqueue("SHOT",point)
func queue_command(event):
	session.enqueue(event)
	if not running:session.step();refresh()
func advance_once():
	session.step()
func _process(delta):
	if preview==null:return
	if audio!=null:
		for player in audio.players.values():player.stream_paused=not running
	if running and model.phase=="running":
		session.advance(delta*speed)
		if loop_enabled and loop_b>loop_a and clock.tick>=loop_b:session.seek(loop_a);audio.sync(true)
		refresh()
func refresh():
	var playing = running and model.phase == "running"
	if model.has_method("set_presentation_context"):model.set_presentation_context("review","playing" if playing else "paused")
	reload_button.visible=model.available_commands().has("RELOAD");coin_button.visible=model.available_commands().has("COIN")
	play_button.text = "Ⅱ 暂停" if playing else ("▶ 重播" if model.phase == "result" else "▶ 播放")
	sound_button.set_pressed_no_signal(audio.enabled)
	alpha_button.set_pressed_no_signal(preview.overlay)
	phase_label.text = {"ready": "待开始", "result": "已结束"}.get(model.phase, "播放中" if playing else "已暂停")
	var fields=[]
	for field in model.level.get("hud",[]):fields.append(field.label+" "+str(model.resources[field.resource]))
	var hud=" · ".join(fields) if not fields.is_empty() else JSON.stringify(model.resources)
	status.text="%.2f / %.2f 秒     %s     命中 %d / %d" % [clock.tick/60.0,session.max_tick/60.0,hud,model.hits,model.shots]
	if not model.result.is_empty():
		status.text += "     结果 " + model.result
	adjusting=true;slider.max_value=session.max_tick;slider.value=clock.tick;adjusting=false
	preview.queue_redraw()
	if spatial_view.visible:spatial_view.queue_redraw()
	timeline.queue_redraw()
	if audio!=null:audio.sync()
func jump(at):
	running=false;session.seek(at);audio.sync(true);refresh()
func select_event():
	var item=event_tree.get_selected()
	if item==null:return
	var id=item.get_metadata(0)
	if id is Dictionary:
		info.text=JSON.stringify(id,"  ");return
	info.text=JSON.stringify({"event_id":id,"design":model.level.events[id],"source":model.build.source_map[id],"fired":model.fired.get(id,0),"state":model.public_state()},"  ")
func save_note(author="user"):
	if review_dir.is_empty() or note.text.strip_edges().is_empty():return
	var text=note.text
	running=false
	DirAccess.make_dir_recursive_absolute(review_dir)
	var id="note-"+str(Time.get_unix_time_from_system()).replace(".","-")+"-"+str(Time.get_ticks_usec())
	var file=review_dir.path_join(id+".json")
	var selected=event_tree.get_selected()
	var entry={"comment_id":id,"package":model.level.id,"source_revision":model.build.source_revision,"build_id":model.build.build_id,"tick":clock.tick,"time_ms":clock.tick*1000.0/60,"anchor":selected.get_metadata(0) if selected else null,"text":text,"status":"open","author":author,"state":model.public_state(),"submission_id":session.submission_id}
	if spatial_view.visible:
		entry["view"] = "top" if spatial_view.mode == SpatialView.Mode.TOP else "side"
	root.gui_disable_input=true
	var saved=await capture_evidence(id)
	root.gui_disable_input=false
	if saved.is_empty():status.text="证据保存失败；批注未登记";return
	entry.evidence=saved
	var pending = FileAccess.open(file+".pending",FileAccess.WRITE)
	if pending==null:status.text="无法写入批注";return
	pending.store_string(JSON.stringify(entry,"\t"))
	pending.close()
	if DirAccess.rename_absolute(file+".pending",file)!=OK:
		status.text="无法发布批注"
		return
	note.text="";refresh();status.text="批注已保存："+file
func evidence_root():
	if evidence_dir.is_empty():evidence_dir=asset_root.get_base_dir().path_join("gunforge_cache/level_design/review-evidence")
	DirAccess.make_dir_recursive_absolute(evidence_dir)
	return evidence_dir
func save_recording():
	var path=evidence_root().path_join("replay-"+str(Time.get_unix_time_from_system()).replace(".","-")+".bin")
	var file=FileAccess.open(path,FileAccess.WRITE)
	if file==null:status.text="无法保存回放";return
	file.store_var(session.recording());file.close();status.text="已保存回放："+path
func capture_evidence(id):
	var directory=evidence_root().path_join(id)
	if DirAccess.make_dir_recursive_absolute(directory)!=OK:return {}
	var previous=preview.overlay
	var files={}
	var spatial_visible = spatial_view.visible
	if spatial_visible:
		spatial_view.queue_redraw()
		await process_frame;await RenderingServer.frame_post_draw
		files["spatial"] = capture_preview_image(directory.path_join("spatial.png"), Rect2(Vector2.ZERO, preview.size))
		if files["spatial"].is_empty():return {}
		spatial_view.hide()
	for mode in ["player","alpha"]:
		preview.overlay=mode=="alpha";preview.queue_redraw()
		await process_frame;await RenderingServer.frame_post_draw
		var canvas = Vector2(model.level.layout.width,model.level.layout.height)
		files[mode] = capture_preview_image(directory.path_join(mode+".png"), Rect2(preview.origin,canvas*preview.scale_factor))
		if files[mode].is_empty():
			preview.overlay=previous
			preview.queue_redraw()
			spatial_view.visible=spatial_visible
			return {}
	preview.overlay=previous;preview.queue_redraw()
	spatial_view.visible=spatial_visible
	var record=directory.path_join("input.bin");var file=FileAccess.open(record,FileAccess.WRITE)
	if file==null:return {}
	file.store_var(session.recording());file.close()
	files.recording={"path":record,"sha256":FileAccess.get_sha256(record)}
	return files

func capture_preview_image(path: String, region: Rect2) -> Dictionary:
	# The viewport texture includes content scaling and excludes the outer window bars.
	var transform = root.get_stretch_transform()*preview.get_global_transform_with_canvas()
	var rect = transform*region
	var box = Rect2i(rect.position.round(),rect.end.round()-rect.position.round())
	var frame = root.get_texture().get_image()
	if not Rect2i(Vector2i.ZERO,frame.get_size()).encloses(box) or frame.get_region(box).save_png(path)!=OK:
		return {}
	return {"path":path,"sha256":FileAccess.get_sha256(path)}
func choose_build():
	running=false
	var dialog=FileDialog.new();dialog.access=FileDialog.ACCESS_FILESYSTEM;dialog.file_mode=FileDialog.FILE_MODE_OPEN_FILE;dialog.filters=PackedStringArray(["*.json ; 编译后的关卡 JSON"]);dialog.size=Vector2i(900,600)
	root.add_child(dialog);dialog.file_selected.connect(func(path):build_path=path;load_build();dialog.queue_free());dialog.canceled.connect(dialog.queue_free);dialog.popup_centered()
func adopted_pointer():
	var path=asset_root.path_join("gunforge/level_design/adopted/"+model.level.id+".json")
	return JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else {}
func update_version_label():
	var adopted=adopted_pointer()
	var label="已采用构建" if adopted.get("build_id","")==model.build.build_id else "候选预览，未采用"
	source_label.text=model.level.id+"    ·    "+label+"    ·    构建 "+model.build.build_id.substr(0,12)
	source_label.tooltip_text = "源版本 " + model.build.source_revision + "\n随机种子 " + str(model.level.seed)
func diff_values(a,b,path=""):
	var out=[]
	if a is Dictionary and b is Dictionary:
		var keys=a.keys()
		for key in b:
			if not keys.has(key):keys.append(key)
		keys.sort()
		for key in keys:
			var at=path+"/"+str(key)
			if not a.has(key):out.append({"path":at,"added":b[key]})
			elif not b.has(key):out.append({"path":at,"removed":a[key]})
			else:out.append_array(diff_values(a[key],b[key],at))
	elif var_to_str(a)!=var_to_str(b):out.append({"path":path,"before":a,"after":b})
	return out
func show_diff():
	if previous_build.is_empty():info.text="请先打开另一个构建；这里将按稳定 ID 显示两个版本的字段差异。";return
	info.text=JSON.stringify({"base_build":previous_build.build_id,"new_build":model.build.build_id,"changes":diff_values(previous_build.level,model.level)},"  ")
func confirm_adopt():
	running=false
	var current=adopted_pointer()
	var output=[]
	var source=asset_root.path_join("gunforge/level_design/packages/"+model.level.id+"/revisions/"+model.build.source_revision+"/level.json")
	var result=OS.execute(asset_root.path_join(".venv/Scripts/python.exe"),PackedStringArray([asset_root.path_join("gunforge/pipeline/level_design/checks.py"),source]),output,true)
	var report=JSON.parse_string("\n".join(output))
	if result!=0 or not report is Dictionary:
		status.text="无法采用：源版本或检查报告不完整";return null
	var dialog=ConfirmationDialog.new();dialog.title="采用已预览的关卡版本";dialog.dialog_text="";dialog.dialog_hide_on_ok=false
	var column=VBoxContainer.new();column.custom_minimum_size=Vector2(710,0);dialog.add_child(column)
	column.add_theme_font_override("font",info.get_theme_font("font"))
	var label=Label.new();label.text="关卡："+model.level.id+"\n源："+model.build.source_revision+"\n构建："+model.build.build_id+"\n采用会切换本地指针并保留回退记录。";column.add_child(label)
	var reason=LineEdit.new();reason.placeholder_text="采用理由（必填）";column.add_child(reason);dialog.register_text_enter(reason)
	var boxes=[]
	var titles={"HUD_UNDECLARED":"未声明通用 HUD；当前可能由原画面渲染器提供", "DISPLAY_PROFILE_UNTESTED":"此画布比例还需要真实光枪和显示设备验证", "HUMAN_DIFFICULTY_UNCALIBRATED":"功能机器人尚不能代表真人难度", "LEGACY_RULE_POLICY":"点灯奖励、续灯和续关计分保留旧版策略"}
	for warning in report.warnings:
		var box=CheckBox.new();box.text="已核对："+titles.get(warning.code,warning.message);box.set_meta("code",warning.code);column.add_child(box);boxes.append(box)
	root.add_child(dialog);dialog.confirmed.connect(func():
		if reason.text.strip_edges().is_empty():status.text="未采用：请填写理由";return
		for box in boxes:
			if not box.button_pressed:status.text="未采用：请核对仍开放的警告";return
		var response=[]
		var arguments=PackedStringArray([asset_root.path_join("gunforge/pipeline/level_design/versions.py"),"adopt",model.level.id,model.build.source_revision,"--expected",current.get("source_revision","none"),"--reason",reason.text,"--actor","user","--build-id",model.build.build_id])
		for box in boxes:arguments.append("--ack-warning");arguments.append(box.get_meta("code"))
		var adopted=OS.execute(asset_root.path_join(".venv/Scripts/python.exe"),arguments,response,true)
		status.text="采用完成；旧版可通过版本指针记录回退" if adopted==0 else "采用失败："+"\n".join(response)
		update_version_label();dialog.queue_free())
	dialog.canceled.connect(dialog.queue_free);dialog.popup_centered(Vector2i(760,360))
	return dialog
func smoke_test():
	running=false
	for i in range(150):session.step()
	refresh();await process_frame;await RenderingServer.frame_post_draw
	var before=model.public_state()
	jump(20);jump(150)
	var exact=var_to_bytes(before)==var_to_bytes(model.public_state())
	# Letterbox pixels can show off-canvas debug contours but cannot accept shots.
	await process_frame;await RenderingServer.frame_post_draw
	var outside = InputEventMouseButton.new()
	outside.button_index = MOUSE_BUTTON_LEFT
	outside.pressed = true
	outside.position = preview.origin - Vector2(0,1)
	running = true
	preview._gui_input(outside)
	running = false
	var outside_ignored = session.queue.pending.is_empty()
	note.text="Automated UI/evidence probe; not a user annotation or acceptance."
	await save_note("test_harness")
	var saved=note.text.is_empty()
	save_recording()
	var before_pointer=adopted_pointer()
	var confirmation=confirm_adopt()
	var dialog_ok=confirmation!=null
	if confirmation!=null:
		await process_frame;await RenderingServer.frame_post_draw
		dialog_ok=confirmation.get_texture().get_image().save_png(evidence_root().path_join("adoption-dialog.png"))==OK
		confirmation.queue_free()
	dialog_ok=dialog_ok and before_pointer==adopted_pointer()
	var inspected = []
	var event_sources_ok = true
	var item = event_tree.get_root().get_first_child()
	while item != null:
		var id = item.get_metadata(0)
		if id is String:
			for action in model.level.events[id].actions.values():
				if action.op in ["spawn", "launch", "cue", "vfx", "section"] and action.op not in inspected:
					item.select(0)
					select_event()
					var details = JSON.parse_string(info.text)
					event_sources_ok = event_sources_ok and details is Dictionary and details.get("event_id") == id and details.get("source", {}).has("pointer")
					inspected.append(action.op)
		item = item.get_next()
	var output={"passed":exact and saved and dialog_ok and outside_ignored and event_sources_ok,"seek_exact":exact,"evidence_saved":saved,"off_canvas_input_ignored":outside_ignored,"adoption_dialog_without_adoption":dialog_ok,"event_sources_ok":event_sources_ok,"inspected_ops":inspected,"build_id":model.build.build_id,"author":"test_harness"}
	print(JSON.stringify(output));quit(0 if output.passed else 1)
func populate_catalog():
	catalog_tree.clear();var top=catalog_tree.create_item();top.set_text(0,model.level.id);catalog_tree.hide_root=false
	for section in ["entities","queries","cues","resources","ruleset_data","controls","effects","sections","presentation"]:
		var branch=catalog_tree.create_item(top);branch.set_text(0,section);branch.collapsed=true
		for id in model.level.get(section,{}):
			var item=catalog_tree.create_item(branch);item.set_text(0,str(id));item.set_metadata(0,{"section":section,"id":id,"pointer":"/"+section+"/"+str(id)})
func select_catalog():
	var item=catalog_tree.get_selected();var entry=item.get_metadata(0)
	if item == catalog_tree.get_root():
		info.text = JSON.stringify({"level":model.level.id,"build_id":model.build.build_id,"layout":model.level.layout,"controls":model.level.get("controls",{}),"events":model.level.events,"ruleset_data":model.level.get("ruleset_data",{})}, "  ")
		return
	if not entry is Dictionary:return
	info.text=JSON.stringify({"source":entry.pointer,"design":model.level[entry.section][entry.id],"runtime":model.queries.get(entry.id,model.entities.get(entry.id,{}))},"  ")
func populate_graph():
	for child in graph.get_children():
		if child is GraphNode:graph.remove_child(child);child.queue_free()
	graph.clear_connections()
	var nodes={};var index=0
	for id in model.level.event_order:
		var node=GraphNode.new();node.name="event_"+str(index);node.title=id;node.draggable=false;node.position_offset=Vector2((index%3)*260,int(index/3)*115)
		var label=Label.new();label.text=JSON.stringify(model.level.events[id].trigger);label.custom_minimum_size=Vector2(210,30);node.add_child(label)
		node.set_slot(0,true,0,Color("#59b8aa"),true,0,Color("#d9ad6b"));graph.add_child(node);nodes[id]=node.name;index+=1
	for id in model.level.event_order:
		var trigger=model.level.events[id].trigger
		if trigger.has("after") and nodes.has(trigger.after):graph.connect_node(nodes[trigger.after],0,nodes[id],0)
func choose_recording():
	running=false
	var dialog=FileDialog.new();dialog.access=FileDialog.ACCESS_FILESYSTEM;dialog.file_mode=FileDialog.FILE_MODE_OPEN_FILE;dialog.filters=PackedStringArray(["*.bin ; 同构建输入回放"]);root.add_child(dialog)
	dialog.file_selected.connect(func(path):
		var file=FileAccess.open(path,FileAccess.READ)
		var record=file.get_var(false) if file!=null else null
		if not record is Dictionary or record.get("build_id","")!=model.build.build_id:status.text="回放版本不匹配；未载入"
		else:session.load_recording(record);audio.clear();refresh();status.text="已载入回放："+path
		dialog.queue_free())
	dialog.canceled.connect(dialog.queue_free);dialog.popup_centered(Vector2i(900,600))
func show_last_input():
	if session.tape.is_empty():info.text="当前路径尚无已消费输入。";return
	var entry=session.tape[-1].duplicate(true)
	if entry.input.has("geometry"):entry.input.geometry=entry.input.geometry.map(func(item):return {"asset":item.asset,"id":item.id,"kind":item.kind,"source":item.source,"transform":item.transform,"size":item.size,"alpha_multiplier":item.tint.a})
	info.text=JSON.stringify(entry,"  ")
