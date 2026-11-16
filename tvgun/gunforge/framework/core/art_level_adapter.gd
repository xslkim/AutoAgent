extends "level_runtime.gd"
## Generic layered 2D adapter. All gameplay remains in the shared runtime.
const Puppet=preload("puppet.gd")
const Scene=preload("art_level_scene.gd")
const Dragon=preload("ink_dragon_raster.gd")
const Chain=preload("ink_dragon_chain.gd")
var puppets={}
var dragon: RefCounted
var dragon_binding: Dictionary = {}
var camera_amplitude := Vector2.ZERO
var presentation_context={"mode":"review","lifecycle":"paused"}
var render_scene
func setup(compiled,asset_root):
	var camera: Dictionary = compiled.level.get("presentation", {}).get("camera", {})
	camera_amplitude = Vector2(camera.get("amplitude_x", 0), camera.get("amplitude_y", 0))
	super.setup(compiled,asset_root)
	dragon = null
	dragon_binding = level.get("presentation", {}).get("dragon", {})
	if not dragon_binding.is_empty():
		var path: String = level.resources[dragon_binding.layout].path
		var layout: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(root_path.path_join(path)))
		var art: Dictionary = {}
		for file in dragon_binding.images:
			art[file] = images[dragon_binding.images[file]]
		dragon = Dragon.new()
		assert(dragon.configure(layout, art), "Invalid dragon chain")
	puppets.clear()
	for id in level.get("presentation",{}).get("puppets",{}):
		var definition=level.presentation.puppets[id];var animations={}
		for clip in definition.clips:animations[clip]=JSON.parse_string(FileAccess.get_file_as_string(root_path.path_join(level.resources[definition.clips[clip]].path)))
		var puppet=Puppet.new()
		puppet.open_registered(JSON.parse_string(FileAccess.get_file_as_string(root_path.path_join(level.resources[definition.character].path))),animations,images[definition.atlas]);puppets[id]=puppet
func mount(parent):
	render_scene=Scene.new();render_scene.model=self;parent.add_child(render_scene)
func set_presentation_context(mode,lifecycle):presentation_context={"mode":mode,"lifecycle":lifecycle}
func camera_shift() -> Vector2:
	var seconds := float(tick) / float(level.tick_hz)
	return camera_amplitude * Vector2(sin(seconds * .85), sin(seconds * 1.1))

func display_center(entity) -> Vector2:
	if dragon != null and is_same(entity, entities[dragon_binding.mouth]) and entities[dragon_binding.anchor].active:
		var posed: Array[Transform2D] = dragon.body_pose(dragon_clock())
		var head: Transform2D = dragon.head_transform(posed[0], dragon_swing())
		return head * Dragon.point(dragon.layout.mouth.anchor)
	return center(entity) + camera_shift() * float(entity.get("parallax", 0))

func dragon_clock() -> float:
	return float(entities[dragon_binding.anchor].age_ticks) / float(level.tick_hz)

func dragon_swing() -> float:
	for effect in active_effects.values():
		if effect.effect == dragon_binding.get("warning_effect", "") and effect.entity == dragon_binding.mouth:
			var seconds := float(tick - effect.start_tick) / float(level.tick_hz)
			var progress := clampf(seconds * 1000 / float(level.effects[effect.effect].duration_ms), 0, 1)
			return deg_to_rad(8 * sin(seconds * TAU * 3) * sin(progress * PI))
	return 0.0

func dragon_state(id: String) -> String:
	var entity: Dictionary = entities[id]
	if entity.health <= 0:
		return Chain.PURIFIED
	return Chain.ACTIVE if entity.active and entity.kind in ["primary", "weak"] else Chain.LOCKED

func dragon_items(hit_only := false) -> Array:
	if dragon == null or not entities[dragon_binding.anchor].active:
		return []
	var clock := dragon_clock()
	var states: Array = []
	for node in dragon.layout.body_nodes:
		states.append(dragon_state(node.id))
	var out: Array = dragon.items(dragon.body_pose(clock), clock, states, dragon_state(dragon_binding.mouth),
		dragon_binding.mouth, dragon_swing())
	for index in out.size():
		var item = out[index]
		item.z = 42.0 + index * .001
		if entities.has(item.id):
			item.generation = entities[item.id].generation
	return out.filter(func(item): return item.kind != "") if hit_only else out

func display_transform(entity) -> Transform2D:
	var transform := super.display_transform(entity)
	transform.origin += camera_shift() * float(entity.get("parallax", 0))
	return transform

func layer_items(blockers_only=false):
	var out=[]
	var shift := camera_shift()
	for id in level.get("presentation",{}).get("layers",{}):
		var layer=level.presentation.layers[id]
		if layer.has("section") and layer.section != current_section:continue
		if blockers_only and not layer.get("blocker",false):continue
		var item=Item.new();item.image=images[layer.resource];item.source=Rect2(Vector2.ZERO,item.image.get_size())
		if layer.has("source"):item.source=Rect2(layer.source[0],layer.source[1],layer.source[2],layer.source[3])
		var origin := Vector2(layer.x, layer.y) + shift * float(layer.get("parallax", 0))
		item.transform=Transform2D(0,origin);item.size=Vector2(layer.width,layer.height);item.z=layer.z
		item.kind="blocker" if layer.get("blocker",false) else "";item.id="layer."+id;item.tint=Color(layer.get("tint","#ffffff"));out.append(item)
	return out
func puppet_items():
	var out=[]
	for id in entities:
		var entity=entities[id]
		if not entity.active or not entity.visible or not entity.has("puppet"):continue
		var binding=entity.puppet;var puppet=puppets[binding.rig];var target=entities[binding.target]
		var solved=target.health<=0
		var elapsed=maxf(0,(tick-target.defeated_at)/float(level.tick_hz)) if solved else float(entity.age_ticks)/level.tick_hz
		var clip=binding.idle
		if solved:
			clip=binding.success if elapsed<float(puppet.clips[binding.success].duration) else binding.rest
			if clip==binding.rest:elapsed-=float(puppet.clips[binding.success].duration)
		var pieces=puppet.items(clip,elapsed,Vector2.ZERO,entity.kind=="protected",not solved,binding.target_part,binding.target,id)
		var scale=float(entity.height)/float(puppet.rig.height)
		var base=Transform2D(0,Vector2(entity.x+entity.width*.5,entity.y+entity.height)).scaled_local(Vector2.ONE*scale)
		for item in pieces:
			item.transform=base*item.transform;item.z=float(entity.properties.get("z",20))+out.size()*.001
			if item.id==binding.target:item.id=binding.target;item.kind="primary" if target.active and not solved else "";item.generation=target.generation
			else:item.id=id;item.kind="" if entity.kind=="decoration" else entity.kind;item.generation=entity.generation
			out.append(item)
	return out
func ordered(items):
	items.sort_custom(func(a,b):return a.id<b.id if a.z==b.z else a.z<b.z)
	return items
func shift_entities(items: Array) -> Array:
	if camera_amplitude == Vector2.ZERO:
		return items
	var shift := camera_shift()
	for item in items:
		item.transform.origin += shift * float(entities[item.id].get("parallax", 0))
	return items

func geometry():return ordered(shift_entities(super.geometry()+puppet_items())+layer_items(true)+dragon_items(true))
func visual_items():
	var out=shift_entities(entity_geometry(true)+puppet_items())+layer_items()
	var presentation: Dictionary = level.get("presentation", {})
	var entity_tints: Dictionary = presentation.get("entity_tints", {})
	var wipes: Dictionary = presentation.get("bottom_wipes", {})
	for item in out:
		if entity_tints.has(item.id) and not item.state_visual:
			var tints: Dictionary = entity_tints[item.id]
			var kind: String = effective_kind(entities[item.id]) if entities.has(item.id) else item.kind
			item.tint *= Color(tints.get(kind, "#ffffff"))
		if wipes.has(item.id):
			item.tint.a = 1.0 - active_opacity(entities[wipes[item.id]])
	var faded: Array = []
	for id in entities:
		var entity=entities[id]
		var ended=int(entity.defeated_at) if entity.defeated_at>=0 else int(entity.removed_at)
		if entity.active or not entity.visible or ended<0 or entity.properties.get("virtual",false) or not entity.has("parts"):continue
		var age=(tick-ended)/float(level.tick_hz)
		if age>.42:continue
		for item in Motion.parts(entity,id,images,level.tick_hz):
			item.kind="";item.tint.a*=maxf(0,1-age/.42);item.transform.origin+=Vector2(0,age*32);faded.append(item)
	return ordered(out+shift_entities(faded)+dragon_items())
func section_stats():
	var all_targets=[]
	var combat_sections = 0
	for section in level.get("sections",{}).values():
		if not section.targets.is_empty():
			all_targets.append_array(section.targets)
			combat_sections += 1
	var cleared=0
	for id in all_targets:
		if entities[id].health<=0:cleared+=1
	var section=level.get("sections",{}).get(current_section,{})
	var here=0
	for id in section.get("targets",[]):
		if entities[id].health<=0:here+=1
	return {"cleared":cleared,"total":all_targets.size(),"section_cleared":here,"section_total":section.get("targets",[]).size(),"section":section,"section_count":combat_sections}
