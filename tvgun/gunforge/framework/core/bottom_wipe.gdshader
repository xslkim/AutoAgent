shader_type canvas_item;
render_mode unshaded;

varying vec4 item_color;

void vertex() {
	item_color = COLOR;
}

void fragment() {
	vec4 ink = texture(TEXTURE, UV);
	float distance_from_base = (1.0 - UV.y) * 0.8 + abs(UV.x - 0.5) * 0.34 + sin(UV.x * 23.0) * 0.02;
	float edge = mix(-0.10, 1.10, item_color.a);
	float coverage = 1.0 - smoothstep(edge - 0.06, edge + 0.06, distance_from_base);
	COLOR = vec4(ink.rgb * item_color.rgb, ink.a * coverage);
}
