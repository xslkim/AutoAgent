shader_type canvas_item;
render_mode unshaded;
uniform float progress = 0.0;
void fragment() {
	vec4 c = texture(TEXTURE, UV);
	float noise = fract(sin(dot(floor(UV * 48.0), vec2(12.9898,78.233))) * 43758.5453);
	c.a *= smoothstep(progress - 0.05, progress + 0.05, noise);
	COLOR = c * COLOR;
}
