extends "res://tests/paper_gallery_capture.gd"
## Capture the same scene with its authored red weak-point and HUD stamp images hidden.

const SAMPLES := ["station_5_plaza", "subject_dragon", "subject_bridge_warning", "ending_wide_full"]

func transparent_like(source: Image) -> Image:
	return Image.create_empty(source.get_width(), source.get_height(), false, Image.FORMAT_RGBA8)

func capture(name: String) -> void:
	await super.capture(name)
	if name not in SAMPLES:
		return
	var hud = model.render_scene.paper_hud
	var score: Texture2D = hud.textures.score_seal
	hud.textures.score_seal = ImageTexture.create_from_image(transparent_like(score.get_image()))

	var dragon_images := {}
	if name == "subject_dragon":
		var mouth: Dictionary = model.dragon.layout.mouth
		for path in [mouth.core, mouth.glow]:
			var original: Image = model.dragon.images[path]
			dragon_images[path] = original
			model.dragon.images[path] = transparent_like(original)

	var weak_images := {}
	for entity in model.entities.values():
		if not entity.active or not entity.visible:
			continue
		for part in entity.get("parts", {}).values():
			if part.get("kind") == "weak" and not weak_images.has(part.resource):
				var original: Image = model.images[part.resource]
				weak_images[part.resource] = original
				model.images[part.resource] = transparent_like(original)

	await super.capture(name + "_without_stamps")

	model.dragon.images.merge(dragon_images, true)
	model.images.merge(weak_images, true)
	hud.textures.score_seal = score
