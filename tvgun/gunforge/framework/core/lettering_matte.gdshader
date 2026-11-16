shader_type canvas_item;
render_mode unshaded;

// Keep the warm paper and indigo depth from the reviewed RGB artwork.
void fragment() {
	vec4 ink = texture(TEXTURE, UV);
	float warm = smoothstep(0.035, 0.15, ink.r - ink.b);
	float indigo = smoothstep(0.025, 0.09, ink.b - max(ink.r, ink.g));
	COLOR = vec4(ink.rgb, ink.a * max(warm, indigo * 0.92));
}
