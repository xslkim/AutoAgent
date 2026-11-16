extends RefCounted
## Deterministic CPU alpha sampling. These are sampled estimates, not exact area proofs.
static func sample(pose, resolver, canvas, stride=8):
	var targets={}
	var pixels={}
	for item in pose:
		if item.kind not in ["primary","weak","protected","invalid"]:continue
		var key=item.id
		if not targets.has(key):targets[key]={"alpha_samples":0,"visible_samples":0,"kinds":[],"aim":null}
		if not targets[key].kinds.has(item.kind):targets[key].kinds.append(item.kind)
		var box=item.bounds().intersection(Rect2(Vector2.ZERO,canvas))
		for y in range(int(floor(box.position.y/stride))*stride,int(ceil(box.end.y)),stride):
			for x in range(int(floor(box.position.x/stride))*stride,int(ceil(box.end.x)),stride):
				var point=Vector2(x+.5,y+.5)
				if item.sample(point).a<.5:continue
				var pixel_key=key+":"+str(x)+":"+str(y)
				if pixels.has(pixel_key):continue
				pixels[pixel_key]=true;targets[key].alpha_samples+=1
				var top=resolver.exact(point,pose)
				if top.get("id","")==key:
					targets[key].visible_samples+=1
					if top.get("kind","") in ["primary","weak"]:targets[key].aim=point
	var warnings=[]
	for id in targets:
		var target=targets[id]
		target.visible_ratio=target.visible_samples/float(maxi(1,target.alpha_samples))
		if target.kinds.has("primary") or target.kinds.has("weak"):
			if target.visible_samples==0:warnings.append({"code":"NO_VISIBLE_ALPHA_SAMPLES","entity":id,"message":"No hittable samples at this grid spacing; review clipping, alpha, overlap and occlusion.","state":"open"})
			elif target.visible_ratio<.2:warnings.append({"code":"LOW_SAMPLED_VISIBILITY","entity":id,"ratio":target.visible_ratio,"threshold":.2,"threshold_source":"unvalidated review heuristic; not a rule proof","state":"open"})
	return {"algorithm":"cpu-alpha-grid-v1","stride_content_px":stride,"targets":targets,"warnings":warnings,"scope":"sampled visible alpha; sub-grid features may be missed; no human success-rate prediction"}
