extends SceneTree
const Item=preload("res://core/raster_item.gd")
const Resolver=preload("res://core/hit_resolver.gd")
const Metrics=preload("res://core/visible_metrics.gd")
func item(id,kind,image):
	var result=Item.new();result.id=id;result.kind=kind;result.image=image;result.source=Rect2(0,0,32,32);result.size=Vector2(32,32);return result
func _initialize():
	var image=Image.create(32,32,false,Image.FORMAT_RGBA8);image.fill(Color.WHITE)
	var target=item("target","primary",image);var protected=item("protected","protected",image);var resolver=Resolver.new()
	var covered=Metrics.sample([target,protected],resolver,Vector2(64,64),4)
	var uncovered=Metrics.sample([protected,target],resolver,Vector2(64,64),4)
	var faded=item("faded","primary",image);faded.tint.a=.4
	var transparent=Metrics.sample([faded],resolver,Vector2(64,64),4)
	var passed=covered.targets.target.visible_samples==0 and covered.warnings[0].code=="NO_VISIBLE_ALPHA_SAMPLES" and uncovered.targets.target.visible_ratio==1 and uncovered.warnings.is_empty() and transparent.targets.faded.alpha_samples==0
	print(JSON.stringify({"passed":passed,"covered_warning":covered.warnings,"scope":"deterministic sampled alpha and draw-order semantics; no human visibility proof"}))
	quit(0 if passed else 1)
