shader_type canvas_item;
uniform sampler2D screen_tex : hint_screen_texture, filter_linear;
uniform float insanity = 0.0;
uniform float vignette = 0.55;
uniform float grain = 0.04;
uniform float flash = 0.0;
uniform vec3 tint = vec3(0.5, 0.0, 0.0);
uniform float tint_amt = 0.0;
uniform float ps1 = 0.0;
uniform float t = 0.0;
uniform float glitch = 0.0;

float h(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void fragment() {
	vec2 uv = SCREEN_UV;
	float g = glitch * step(0.7, h(vec2(floor(uv.y * 24.0), floor(t * 12.0))));
	uv.x += g * 0.06 * (h(vec2(floor(t * 20.0), uv.y)) - 0.5);
	float wob = insanity * 0.003 * sin(uv.y * 40.0 + t * 3.0);
	vec2 off = vec2(wob + insanity * 0.005 + glitch * 0.01, 0.0);
	vec3 c;
	c.r = texture(screen_tex, uv + off).r;
	c.g = texture(screen_tex, uv).g;
	c.b = texture(screen_tex, uv - off).b;
	if (ps1 > 0.5) {
		float d = h(floor(FRAGCOORD.xy / 2.0)) * 0.05;
		c = floor((c + d) * 20.0) / 20.0;
	}
	float l = dot(c, vec3(0.3, 0.59, 0.11));
	c = mix(c, vec3(l), insanity * 0.45);
	float d2 = length(uv - 0.5) * 1.414;
	c *= 1.0 - smoothstep(0.35, 1.05, d2) * vignette;
	c += (h(uv * vec2(1280.0, 720.0) + fract(t)) - 0.5) * (grain + insanity * 0.12);
	c = mix(c, tint, tint_amt);
	c += vec3(flash);
	COLOR = vec4(c, 1.0);
}
