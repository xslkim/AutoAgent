shader_type canvas_item;
render_mode unshaded;
uniform float maximum_y = 0.75;
void fragment() {
	vec4 c = texture(TEXTURE, UV);
	float y = dot(c.rgb, vec3(0.299, 0.587, 0.114));
	float ceiling = max(0.0, maximum_y - 1.0 / 255.0);
	COLOR = vec4(c.rgb * min(1.0, ceiling / max(y, 0.00001)), c.a);
}
