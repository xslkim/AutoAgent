extends RefCounted
## Shared data-driven motion and composite alpha geometry, no rendering side effects.
const Item=preload("raster_item.gd")
static func age_ms(entity,hz):return float(entity.age_ticks)*1000.0/hz
static func update(entity,hz):
	var motion=entity.get("motion_override",entity.get("motion",{}))
	var at=age_ms(entity,hz)
	if not motion.is_empty():
		var frames=motion.frames
		var a=frames[0];var b=frames[-1]
		for i in range(frames.size()-1):
			if at<=frames[i+1].at_ms:a=frames[i];b=frames[i+1];break
		var t=clampf((at-a.at_ms)/maxf(1,b.at_ms-a.at_ms),0,1)
		if motion.get("easing","smoothstep")=="smoothstep":t=t*t*(3-2*t)
		entity.x=lerpf(float(a.x),float(b.x),t);entity.y=lerpf(float(a.y),float(b.y),t)
		entity.pose_scale=lerpf(float(a.get("scale",1)),float(b.get("scale",1)),t)
		entity.pose_scale_x=lerpf(float(a.get("scale_x",1)),float(b.get("scale_x",1)),t)
		entity.pose_scale_y=lerpf(float(a.get("scale_y",1)),float(b.get("scale_y",1)),t)
		entity.pose_opacity=lerpf(float(a.get("opacity",1)),float(b.get("opacity",1)),t)
		entity.pose_rotation=lerpf(float(a.get("rotation_rad",0)),float(b.get("rotation_rad",0)),t)
		if entity.has("bob"):
			var bob=entity.bob;var phase=at*TAU/bob.period_ms+bob.get("phase_rad",0)
			entity.x+=bob.amplitude_x*sin(phase);entity.y+=bob.amplitude_y*sin(phase*1.23)
	entity.motion_phase=""
	for phase in entity.get("phases",[]):
		if at>=phase.start_ms and at<phase.end_ms:entity.motion_phase=phase.id;break
static func transform(entity):
	var scale=float(entity.get("pose_scale",1));var angle=float(entity.get("pose_rotation",0))
	var center=Vector2(entity.width,entity.height)*.5
	var stretch := Vector2(entity.get("pose_scale_x",1),entity.get("pose_scale_y",1))
	var basis=Transform2D(angle,Vector2.ZERO).scaled_local(stretch*scale)
	basis.origin=Vector2(entity.x,entity.y)+center-basis.basis_xform(center)
	var hit_age=float(entity.get("view_tick",0)-entity.get("last_hit_tick",-1000))/60.0
	if hit_age>=0 and hit_age<.22:basis.origin+=Vector2(entity.get("hit_direction",1)*18,-5)*exp(-hit_age*18)
	return basis
static func parts(entity,id,images,hz,visual_kind: String = ""):
	var out=[];var base=transform(entity)
	for key in entity.part_order:
		var part=entity.parts[key];var item=Item.new()
		item.id=id;item.kind=part.get("kind",entity.kind) if entity.kind in ["primary","weak"] else entity.kind
		if entity.kind=="decoration":item.kind=""
		if not visual_kind.is_empty() and part.has("hardened_visual"):
			item.state_images.assign([images[part.resource], images[part.hardened_visual.resource]])
			if visual_kind == "invalid":
				part = part.hardened_visual
				item.state_visual = true
		item.image=images[part.resource];item.source=Rect2(Vector2.ZERO,item.image.get_size())
		if part.has("hit_resource"):item.hit_image=images[part.hit_resource]
		if part.has("source"):item.source=Rect2(part.source[0],part.source[1],part.source[2],part.source[3])
		item.size=Vector2(entity.width*part.width,entity.height*part.height)
		var offset=Vector2(entity.width*part.x,entity.height*part.y)
		var local=Transform2D(0,offset)
		if part.has("flap"):
			var pivot=item.size*Vector2(part.flap.pivot[0],part.flap.pivot[1])
			var angle=part.flap.amplitude_rad*sin(float(entity.age_ticks)/hz*part.flap.hz*TAU+part.flap.get("phase_rad",0))
			local=Transform2D(angle,offset+pivot);local.origin-=local.basis_xform(pivot)
		item.transform=base*local;item.tint=Color(part.get("tint","#ffffff"));item.z=float(entity.properties.get("z",0))+out.size()*.001;item.generation=int(entity.generation)
		item.tint.a *= float(entity.get("pose_opacity",1))
		out.append(item)
	return out
