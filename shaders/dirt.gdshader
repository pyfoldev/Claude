shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled, shadows_disabled, specular_disabled;

uniform float amount : hint_range(0.0, 1.0) = 1.0;
uniform vec4 dirt_color : source_color = vec4(0.2, 0.15, 0.1, 1.0);
uniform float seed = 0.0;
uniform float opacity = 0.85;
uniform float emit_amount = 0.0;
uniform sampler2D noise_tex : repeat_enable, filter_linear;

void fragment() {
	vec2 uv = UV;
	float n = texture(noise_tex, uv * 1.3 + vec2(seed, seed * 0.7)).r;
	float n2 = texture(noise_tex, uv * 3.1 + vec2(seed * 1.7, 0.3)).r;
	float blot = n * 0.7 + n2 * 0.3;
	vec2 c = uv - 0.5;
	float rad = length(c) * 2.0;
	float edge = 1.0 - smoothstep(0.55, 1.0, rad + (n - 0.5) * 0.5);
	// чем меньше amount, тем выше порог — пятно «съедается»
	float thr = mix(1.05, 0.25, amount);
	float a = smoothstep(thr - 0.12, thr + 0.02, blot + edge * 0.35 - 0.25) * edge;
	a *= smoothstep(0.0, 0.08, amount);
	ALBEDO = dirt_color.rgb * (0.7 + 0.5 * n2);
	ROUGHNESS = 0.9;
	EMISSION = dirt_color.rgb * emit_amount;
	ALPHA = a * opacity;
}
