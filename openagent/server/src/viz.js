// Генераторы SVG: графики, диаграммы, таблицы, графики функций, геометрия. Без зависимостей, тёмная/светлая тема.
import { spawnSync } from 'node:child_process';

const THEMES = {
  dark: { bg: '#101014', fg: '#ECE9F2', dim: '#9A96A6', grid: '#2A2833', axis: '#5A566A', pal: ['#B8A9FF', '#5FD38D', '#FFB86B', '#6BB8FF', '#FF7A90', '#E6D96B', '#7CE0D6', '#D58BFF'] },
  light: { bg: '#FFFFFF', fg: '#1B1A22', dim: '#6B6878', grid: '#E6E4EE', axis: '#9A96A6', pal: ['#5B45E0', '#1F9D55', '#E07B1F', '#1F6FD0', '#D6264A', '#B59B00', '#12958A', '#A23BD6'] },
};
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const f = (n) => (Math.round(n * 100) / 100).toString();
const FONT = "font-family=\"Roboto,Segoe UI,Arial,sans-serif\"";

function niceTicks(min, max, n = 6) {
  if (min === max) { min -= 1; max += 1; }
  const span = max - min, raw = span / n, mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || mag * 10;
  const start = Math.ceil(min / step - 1e-9) * step, ticks = [];
  for (let v = start; v <= max + step * 1e-9; v += step) ticks.push(Math.abs(v) < step * 1e-9 ? 0 : +v.toFixed(10));
  return { ticks, step };
}
const fmtTick = (v) => (Math.abs(v) >= 1e6 || (Math.abs(v) < 1e-3 && v !== 0) ? v.toExponential(1) : String(+v.toFixed(6)));

function wrap(W, H, body, T, title) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" ${FONT}><rect width="${W}" height="${H}" rx="18" fill="${T.bg}"/>${
    title ? `<text x="${W / 2}" y="34" text-anchor="middle" font-size="20" font-weight="600" fill="${T.fg}">${esc(title)}</text>` : ''}${body}</svg>`;
}

function legend(names, T, x, y) {
  return names.map((n, i) => `<g transform="translate(${x + i * 0},${y + i * 22})"><rect width="12" height="12" rx="3" fill="${T.pal[i % T.pal.length]}"/><text x="19" y="11" font-size="13" fill="${T.fg}">${esc(n)}</text></g>`).join('');
}

// ---------------- chart ----------------
export function chartSvg(o) {
  const T = THEMES[o.theme] || THEMES.dark;
  const W = 820, H = 520, type = o.type || 'bar';
  const title = o.title || '';
  if (type === 'table') return tableSvg(o, T);
  if (type === 'pie' || type === 'donut') return pieSvg(o, T, W, H);
  const labels = o.labels || [];
  let series = o.series || (o.values ? [{ name: o.title || '', data: o.values }] : []);
  if (type === 'histogram') {
    const vals = (o.values || series[0]?.data || []).map(Number).filter(Number.isFinite);
    const bins = Math.max(2, Math.min(60, o.bins || Math.ceil(Math.sqrt(vals.length)) || 8));
    const mn = Math.min(...vals), mx = Math.max(...vals), w = (mx - mn) / bins || 1;
    const counts = Array(bins).fill(0); vals.forEach((v) => counts[Math.min(bins - 1, Math.floor((v - mn) / w))]++);
    series = [{ name: 'Частота', data: counts }];
    o = { ...o, labels: counts.map((_, i) => `${fmtTick(mn + i * w)}`), type: 'bar' };
  }
  const L = o.labels || labels;
  const ml = 78, mr = o.legend === false || series.length < 2 ? 30 : 160, mt = title ? 60 : 30, mb = 78;
  const pw = W - ml - mr, ph = H - mt - mb;
  let body = '';

  if (type === 'scatter') {
    const pts = series.map((s) => (s.data || []).map((p) => (Array.isArray(p) ? { x: +p[0], y: +p[1] } : { x: +p.x, y: +p.y })));
    const xs = pts.flat().map((p) => p.x), ys = pts.flat().map((p) => p.y);
    const xt = niceTicks(Math.min(...xs), Math.max(...xs)), yt = niceTicks(Math.min(...ys), Math.max(...ys));
    const x0 = xt.ticks[0] - xt.step * 0.0, x1 = xt.ticks.at(-1), y0 = yt.ticks[0], y1 = yt.ticks.at(-1);
    const X = (v) => ml + ((v - x0) / (x1 - x0 || 1)) * pw, Y = (v) => mt + ph - ((v - y0) / (y1 - y0 || 1)) * ph;
    body += axes(T, ml, mt, pw, ph, xt.ticks.map((t) => [X(t), fmtTick(t)]), yt.ticks.map((t) => [Y(t), fmtTick(t)]), o);
    pts.forEach((arr, i) => { arr.forEach((p) => { body += `<circle cx="${f(X(p.x))}" cy="${f(Y(p.y))}" r="5" fill="${T.pal[i % 8]}" fill-opacity=".85"/>`; });
      if (o.trend) { const n = arr.length, sx = arr.reduce((a, p) => a + p.x, 0), sy = arr.reduce((a, p) => a + p.y, 0), sxy = arr.reduce((a, p) => a + p.x * p.y, 0), sxx = arr.reduce((a, p) => a + p.x * p.x, 0);
        const k = (n * sxy - sx * sy) / (n * sxx - sx * sx || 1), b = (sy - k * sx) / n; body += `<line x1="${f(X(x0))}" y1="${f(Y(k * x0 + b))}" x2="${f(X(x1))}" y2="${f(Y(k * x1 + b))}" stroke="${T.pal[i % 8]}" stroke-dasharray="6 5" stroke-width="2"/>`; } });
    if (series.length > 1 && o.legend !== false) body += legend(series.map((s) => s.name || ''), T, W - mr + 20, mt);
    return wrap(W, H, body, T, title);
  }

  const n = Math.max(...series.map((s) => (s.data || []).length), L.length);
  const all = series.flatMap((s) => (s.data || []).map(Number));
  const stacked = !!o.stacked && (type === 'bar' || type === 'area');
  let ymaxV = Math.max(0, ...all), yminV = Math.min(0, ...all);
  if (stacked) ymaxV = Math.max(...Array.from({ length: n }, (_, i) => series.reduce((a, s) => a + (+s.data?.[i] || 0), 0)));
  const horizontal = type === 'hbar';
  const yt = niceTicks(yminV, ymaxV);
  const y0 = yt.ticks[0] < yminV ? yt.ticks[0] : yminV, y1 = yt.ticks.at(-1);
  const Y = (v) => mt + ph - ((v - y0) / (y1 - y0 || 1)) * ph;
  const bandW = pw / n;
  const xl = (i) => ml + bandW * i + bandW / 2;

  if (horizontal) {
    const bh = ph / n, X = (v) => ml + ((v - y0) / (y1 - y0 || 1)) * pw;
    yt.ticks.forEach((t) => { body += `<line x1="${f(X(t))}" y1="${mt}" x2="${f(X(t))}" y2="${mt + ph}" stroke="${T.grid}"/><text x="${f(X(t))}" y="${mt + ph + 22}" text-anchor="middle" font-size="13" fill="${T.dim}">${fmtTick(t)}</text>`; });
    for (let i = 0; i < n; i++) {
      const gh = (bh * 0.7) / series.length;
      series.forEach((s, k) => { const v = +s.data?.[i] || 0; body += `<rect x="${f(X(Math.min(0, v)))}" y="${f(mt + bh * i + bh * 0.15 + gh * k)}" width="${f(Math.abs(X(v) - X(0)))}" height="${f(gh - 2)}" rx="4" fill="${T.pal[k % 8]}"/><text x="${f(X(v) + 6)}" y="${f(mt + bh * i + bh * 0.15 + gh * k + gh / 2 + 4)}" font-size="12" fill="${T.dim}">${fmtTick(v)}</text>`; });
      body += `<text x="${ml - 10}" y="${f(mt + bh * i + bh / 2 + 4)}" text-anchor="end" font-size="13" fill="${T.fg}">${esc(L[i] ?? i + 1)}</text>`;
    }
    body += `<line x1="${ml}" y1="${mt}" x2="${ml}" y2="${mt + ph}" stroke="${T.axis}"/>`;
    if (series.length > 1 && o.legend !== false) body += legend(series.map((s) => s.name || ''), T, W - mr + 20, mt);
    return wrap(W, H, body, T, title);
  }

  body += axes(T, ml, mt, pw, ph, Array.from({ length: n }, (_, i) => [xl(i), String(L[i] ?? i + 1)]), yt.ticks.map((t) => [Y(t), fmtTick(t)]), o, true);
  if (type === 'bar') {
    for (let i = 0; i < n; i++) {
      const gw = (bandW * 0.7) / (stacked ? 1 : series.length); let acc = 0;
      series.forEach((s, k) => {
        const v = +s.data?.[i] || 0;
        const x = stacked ? xl(i) - gw / 2 : xl(i) - (bandW * 0.7) / 2 + gw * k;
        const yTop = stacked ? Y(acc + v) : Y(Math.max(0, v)), hgt = stacked ? Y(acc) - Y(acc + v) : Math.abs(Y(v) - Y(0));
        body += `<rect x="${f(x)}" y="${f(yTop)}" width="${f(gw - 3)}" height="${f(Math.max(hgt, 0))}" rx="5" fill="${T.pal[k % 8]}"/>`;
        if (!stacked && n <= 14 && o.valueLabels !== false) body += `<text x="${f(x + (gw - 3) / 2)}" y="${f(v >= 0 ? yTop - 6 : yTop + hgt + 14)}" text-anchor="middle" font-size="12" fill="${T.dim}">${fmtTick(v)}</text>`;
        acc += v;
      });
    }
  } else { // line / area
    series.forEach((s, k) => {
      const pts = Array.from({ length: n }, (_, i) => [xl(i), Y(+s.data?.[i] || 0)]);
      const d = pts.map((p, i) => `${i ? 'L' : 'M'}${f(p[0])},${f(p[1])}`).join(' ');
      if (type === 'area') body += `<path d="${d} L${f(pts.at(-1)[0])},${f(Y(0))} L${f(pts[0][0])},${f(Y(0))} Z" fill="${T.pal[k % 8]}" fill-opacity=".22"/>`;
      body += `<path d="${d}" fill="none" stroke="${T.pal[k % 8]}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>`;
      if (n <= 40) pts.forEach((p) => { body += `<circle cx="${f(p[0])}" cy="${f(p[1])}" r="4" fill="${T.bg}" stroke="${T.pal[k % 8]}" stroke-width="2.5"/>`; });
    });
  }
  if (series.length > 1 && o.legend !== false) body += legend(series.map((s) => s.name || ''), T, W - mr + 20, mt);
  return wrap(W, H, body, T, title);
}

function axes(T, ml, mt, pw, ph, xticks, yticks, o, bandX = false) {
  let b = '';
  yticks.forEach(([y, t]) => { b += `<line x1="${ml}" y1="${f(y)}" x2="${ml + pw}" y2="${f(y)}" stroke="${T.grid}"/><text x="${ml - 10}" y="${f(y + 4)}" text-anchor="end" font-size="13" fill="${T.dim}">${esc(t)}</text>`; });
  if (!bandX) xticks.forEach(([x]) => { b += `<line x1="${f(x)}" y1="${mt}" x2="${f(x)}" y2="${mt + ph}" stroke="${T.grid}"/>`; });
  const skip = Math.ceil(xticks.length / 14);
  xticks.forEach(([x, t], i) => { if (i % skip === 0) b += `<text x="${f(x)}" y="${mt + ph + 24}" text-anchor="middle" font-size="13" fill="${T.dim}">${esc(String(t).slice(0, 14))}</text>`; });
  b += `<line x1="${ml}" y1="${mt + ph}" x2="${ml + pw}" y2="${mt + ph}" stroke="${T.axis}" stroke-width="1.5"/>`;
  if (o.xlabel) b += `<text x="${ml + pw / 2}" y="${mt + ph + 56}" text-anchor="middle" font-size="14" fill="${T.fg}">${esc(o.xlabel)}</text>`;
  if (o.ylabel) b += `<text transform="translate(22,${mt + ph / 2}) rotate(-90)" text-anchor="middle" font-size="14" fill="${T.fg}">${esc(o.ylabel)}</text>`;
  return b;
}

function pieSvg(o, T, W, H) {
  const labels = o.labels || []; const vals = (o.values || o.series?.[0]?.data || []).map(Number);
  const total = vals.reduce((a, b) => a + Math.max(b, 0), 0) || 1;
  const cx = 280, cy = H / 2 + 14, R = 170, r = o.type === 'donut' ? 90 : 0;
  let a = -Math.PI / 2, body = '';
  vals.forEach((v, i) => {
    const frac = Math.max(v, 0) / total, a2 = a + frac * 2 * Math.PI, big = frac > 0.5 ? 1 : 0;
    const p = (ang, rad) => `${f(cx + rad * Math.cos(ang))},${f(cy + rad * Math.sin(ang))}`;
    const d = frac >= 0.9999 ? `M${p(a, R)} A${R},${R} 0 1 1 ${p(a + Math.PI, R)} A${R},${R} 0 1 1 ${p(a, R)}` : r
      ? `M${p(a, R)} A${R},${R} 0 ${big} 1 ${p(a2, R)} L${p(a2, r)} A${r},${r} 0 ${big} 0 ${p(a, r)} Z` : `M${cx},${cy} L${p(a, R)} A${R},${R} 0 ${big} 1 ${p(a2, R)} Z`;
    body += `<path d="${d}" fill="${T.pal[i % 8]}" stroke="${T.bg}" stroke-width="3"/>`;
    if (frac > 0.04) { const m = (a + a2) / 2, rr = r ? (R + r) / 2 : R * 0.68; body += `<text x="${f(cx + rr * Math.cos(m))}" y="${f(cy + rr * Math.sin(m) + 5)}" text-anchor="middle" font-size="14" font-weight="600" fill="${o.theme === 'light' ? '#fff' : '#101014'}">${Math.round(frac * 100)}%</text>`; }
    a = a2;
    body += `<g transform="translate(520,${70 + i * 28})"><rect width="14" height="14" rx="4" fill="${T.pal[i % 8]}"/><text x="24" y="12" font-size="15" fill="${T.fg}">${esc(labels[i] ?? `#${i + 1}`)} — ${fmtTick(v)}</text></g>`;
  });
  return wrap(W, H, body, T, o.title);
}

function tableSvg(o, T) {
  const cols = o.columns || (o.rows?.[0] ? o.rows[0].map((_, i) => `Столбец ${i + 1}`) : []);
  const rows = o.rows || [];
  const cw = cols.map((c, i) => Math.min(280, Math.max(70, 16 + 9 * Math.max(String(c).length, ...rows.map((r) => String(r[i] ?? '').length)))));
  const W = cw.reduce((a, b) => a + b, 0) + 40, rh = 40, top = o.title ? 64 : 24, H = top + rh * (rows.length + 1) + 24;
  let b = '', x = 20;
  cols.forEach((c, i) => { b += `<text x="${x + 12}" y="${top + 26}" font-size="14" font-weight="700" fill="${T.pal[0]}">${esc(c)}</text>`; x += cw[i]; });
  b += `<line x1="20" y1="${top + rh}" x2="${W - 20}" y2="${top + rh}" stroke="${T.axis}" stroke-width="1.5"/>`;
  rows.forEach((r, j) => {
    if (j % 2) b += `<rect x="20" y="${top + rh * (j + 1)}" width="${W - 40}" height="${rh}" fill="${T.grid}" fill-opacity=".45"/>`;
    let xx = 20; cols.forEach((_, i) => { b += `<text x="${xx + 12}" y="${top + rh * (j + 1) + 26}" font-size="14" fill="${T.fg}">${esc(String(r[i] ?? '').slice(0, 36))}</text>`; xx += cw[i]; });
  });
  return wrap(W, H, b, T, o.title);
}

// ---------------- безопасный вычислитель выражений ----------------
const FN = { sin: Math.sin, cos: Math.cos, tan: Math.tan, asin: Math.asin, acos: Math.acos, atan: Math.atan, sinh: Math.sinh, cosh: Math.cosh, tanh: Math.tanh, sqrt: Math.sqrt, cbrt: Math.cbrt, abs: Math.abs, ln: Math.log, log: Math.log10, log2: Math.log2, exp: Math.exp, floor: Math.floor, ceil: Math.ceil, round: Math.round, sign: Math.sign };
export function compileExpr(src, vars = ['x']) {
  const s = String(src).replace(/\s+/g, '').replace(/\*\*/g, '^').replace(/π/g, 'pi').replace(/−/g, '-');
  let i = 0;
  const peek = () => s[i];
  function num() { const m = s.slice(i).match(/^(\d+\.?\d*|\.\d+)(e[+-]?\d+)?/i); if (!m) return null; i += m[0].length; return parseFloat(m[0]); }
  function ident() { const m = s.slice(i).match(/^[a-zA-Zα-ω_][a-zA-Z0-9_]*/); if (!m) return null; i += m[0].length; return m[0]; }
  function parseExpr() { let l = parseTerm(); while (peek() === '+' || peek() === '-') { const op = s[i++]; const r = parseTerm(); const a = l; l = op === '+' ? (v) => a(v) + r(v) : (v) => a(v) - r(v); } return l; }
  function parseTerm() {
    let l = parseUnary();
    for (;;) {
      const c = peek();
      if (c === '*' || c === '/') { i++; const r = parseUnary(); const a = l; l = c === '*' ? (v) => a(v) * r(v) : (v) => a(v) / r(v); }
      else if (c && (/[a-zA-Z(0-9.]/.test(c))) { const r = parseUnary(); const a = l; l = (v) => a(v) * r(v); } // неявное умножение: 2x, 3(x+1)
      else break;
    }
    return l;
  }
  function parseUnary() { if (peek() === '-') { i++; const a = parseUnary(); return (v) => -a(v); } if (peek() === '+') { i++; return parseUnary(); } return parsePow(); }
  function parsePow() { const b = parseAtom(); if (peek() === '^') { i++; const e = parseUnary(); return (v) => b(v) ** e(v); } return b; }
  function parseAtom() {
    if (peek() === '(') { i++; const e = parseExpr(); if (peek() !== ')') throw new Error('Ожидалась )'); i++; return e; }
    if (peek() === '|') { i++; const e = parseExpr(); if (peek() !== '|') throw new Error('Ожидалась |'); i++; return (v) => Math.abs(e(v)); }
    const n = num(); if (n !== null) return () => n;
    const id = ident(); if (!id) throw new Error(`Не понимаю выражение около «${s.slice(i, i + 6)}»`);
    if (FN[id] && peek() === '(') { i++; const e = parseExpr(); if (peek() !== ')') throw new Error('Ожидалась )'); i++; const fn = FN[id]; return (v) => fn(e(v)); }
    if (id === 'pi') return () => Math.PI; if (id === 'e') return () => Math.E;
    if (vars.includes(id)) return (v) => v[id];
    throw new Error(`Неизвестное имя «${id}»`);
  }
  const r = parseExpr(); if (i < s.length) throw new Error(`Лишнее «${s.slice(i, i + 6)}»`);
  return r;
}
export function calculate(expr) {
  const v = compileExpr(expr, [])({});
  return Number.isFinite(v) ? String(+v.toPrecision(14)) : String(v);
}

// ---------------- график функций ----------------
export function plotSvg(o) {
  const T = THEMES[o.theme] || THEMES.dark;
  const W = 820, H = 620, ml = 56, mr = 28, mt = o.title ? 62 : 28, mb = 48, pw = W - ml - mr, ph = H - mt - mb;
  const curves = [];
  for (const [i, fn] of (o.functions || []).entries()) {
    const expr = typeof fn === 'string' ? fn : fn.expr; const label = (typeof fn === 'string' ? null : fn.label) || `y = ${expr}`;
    const g = compileExpr(String(expr).replace(/^\s*y\s*=\s*/i, ''), ['x']);
    curves.push({ label, color: i, pts: [], sample: (xmin, xmax, N) => { const out = []; for (let k = 0; k <= N; k++) { const x = xmin + ((xmax - xmin) * k) / N; let y; try { y = g({ x }); } catch { y = NaN; } out.push([x, y]); } return out; } });
  }
  for (const [i, p] of (o.parametric || []).entries()) {
    const gx = compileExpr(p.x, ['t']), gy = compileExpr(p.y, ['t']); const t0 = p.tmin ?? 0, t1 = p.tmax ?? 2 * Math.PI;
    curves.push({ label: p.label || `(${p.x}, ${p.y})`, color: curves.length, parametric: true, pts: Array.from({ length: 721 }, (_, k) => { const t = t0 + ((t1 - t0) * k) / 720; return [gx({ t }), gy({ t })]; }) });
  }
  let xmin = o.xmin ?? -10, xmax = o.xmax ?? 10;
  const N = 800;
  curves.forEach((c) => { if (!c.parametric) c.pts = c.sample(xmin, xmax, N); });
  let ymin = o.ymin, ymax = o.ymax;
  if (ymin === undefined || ymax === undefined) {
    const ys = curves.flatMap((c) => c.pts.map((p) => p[1])).filter((y) => Number.isFinite(y) && Math.abs(y) < 1e6).sort((a, b) => a - b);
    const lo = ys[Math.floor(ys.length * 0.02)] ?? -5, hi = ys[Math.ceil(ys.length * 0.98) - 1] ?? 5;
    const pad = (hi - lo) * 0.1 || 1; ymin ??= lo - pad; ymax ??= hi + pad;
  }
  if (o.parametric?.length && !(o.functions || []).length && o.xmin === undefined) { const xs = curves.flatMap((c) => c.pts.map((p) => p[0])).filter(Number.isFinite); xmin = Math.min(...xs); xmax = Math.max(...xs); const pad = (xmax - xmin) * 0.1 || 1; xmin -= pad; xmax += pad; }
  if (o.equal) { const cx = (xmin + xmax) / 2, cy = (ymin + ymax) / 2, k = Math.max((xmax - xmin) / pw, (ymax - ymin) / ph) / 2; xmin = cx - k * pw; xmax = cx + k * pw; ymin = cy - k * ph; ymax = cy + k * ph; }
  const X = (v) => ml + ((v - xmin) / (xmax - xmin)) * pw, Y = (v) => mt + ph - ((v - ymin) / (ymax - ymin)) * ph;
  const xt = niceTicks(xmin, xmax, 10), yt = niceTicks(ymin, ymax, 8);
  let b = `<clipPath id="cp"><rect x="${ml}" y="${mt}" width="${pw}" height="${ph}"/></clipPath>`;
  xt.ticks.forEach((t) => { b += `<line x1="${f(X(t))}" y1="${mt}" x2="${f(X(t))}" y2="${mt + ph}" stroke="${T.grid}"/>`; });
  yt.ticks.forEach((t) => { b += `<line x1="${ml}" y1="${f(Y(t))}" x2="${ml + pw}" y2="${f(Y(t))}" stroke="${T.grid}"/>`; });
  const ax = Y(0) >= mt && Y(0) <= mt + ph ? Y(0) : mt + ph, ay = X(0) >= ml && X(0) <= ml + pw ? X(0) : ml;
  b += `<line x1="${ml}" y1="${f(ax)}" x2="${ml + pw}" y2="${f(ax)}" stroke="${T.axis}" stroke-width="1.6"/><line x1="${f(ay)}" y1="${mt}" x2="${f(ay)}" y2="${mt + ph}" stroke="${T.axis}" stroke-width="1.6"/>`;
  xt.ticks.forEach((t) => { if (t !== 0) b += `<text x="${f(X(t))}" y="${f(Math.min(ax + 18, mt + ph + 18))}" text-anchor="middle" font-size="12" fill="${T.dim}">${fmtTick(t)}</text>`; });
  yt.ticks.forEach((t) => { if (t !== 0) b += `<text x="${f(Math.max(ay - 8, ml - 6))}" y="${f(Y(t) + 4)}" text-anchor="end" font-size="12" fill="${T.dim}">${fmtTick(t)}</text>`; });
  b += '<g clip-path="url(#cp)">';
  curves.forEach((c) => {
    let d = '', pen = false;
    for (let k = 0; k < c.pts.length; k++) {
      const [x, y] = c.pts[k];
      if (!Number.isFinite(y) || !Number.isFinite(x) || Math.abs(y) > 1e7) { pen = false; continue; }
      if (pen && !c.parametric && k && Number.isFinite(c.pts[k - 1][1]) && Math.abs(y - c.pts[k - 1][1]) > (ymax - ymin) * 2) pen = false; // разрыв (tan, 1/x)
      d += `${pen ? 'L' : 'M'}${f(X(x))},${f(Y(y))} `; pen = true;
    }
    b += `<path d="${d}" fill="none" stroke="${T.pal[c.color % 8]}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>`;
  });
  for (const p of o.points || []) { b += `<circle cx="${f(X(p.x))}" cy="${f(Y(p.y))}" r="5.5" fill="${T.fg}" stroke="${T.bg}" stroke-width="2"/>${p.label ? `<text x="${f(X(p.x) + 9)}" y="${f(Y(p.y) - 9)}" font-size="14" fill="${T.fg}">${esc(p.label)}</text>` : ''}`; }
  b += '</g>';
  b += `<g transform="translate(${ml + 14},${mt + 14})">${curves.map((c, i) => `<g transform="translate(0,${i * 22})"><rect width="22" height="4" y="5" rx="2" fill="${T.pal[c.color % 8]}"/><text x="30" y="12" font-size="14" fill="${T.fg}">${esc(c.label)}</text></g>`).join('')}</g>`;
  return wrap(W, H, b, T, o.title);
}

// ---------------- геометрия ----------------
export function geometrySvg(o) {
  const T = THEMES[o.theme] || THEMES.dark;
  const W = 760, H = 640, m = 56, mt = o.title ? 70 : 40;
  const objs = o.objects || [];
  const P = {};
  objs.filter((x) => x.type === 'point').forEach((p) => { P[p.name] = [+p.x, +p.y]; });
  const pt = (v) => (typeof v === 'string' ? P[v] : [+v[0], +v[1]]);
  const xs = [], ys = [];
  const add = (p) => { if (p && Number.isFinite(p[0])) { xs.push(p[0]); ys.push(p[1]); } };
  for (const ob of objs) {
    try {
      if (ob.type === 'point') add([ob.x, ob.y]);
      else if (ob.type === 'segment' || ob.type === 'vector') { add(pt(ob.a)); add(pt(ob.b)); }
      else if (ob.type === 'polygon') ob.points.forEach((v) => add(pt(v)));
      else if (ob.type === 'circle' || ob.type === 'arc') { const c = pt(ob.center); add([c[0] - ob.r, c[1] - ob.r]); add([c[0] + ob.r, c[1] + ob.r]); }
      else if (ob.type === 'text') add([ob.x, ob.y]);
    } catch {}
  }
  let x0 = Math.min(...xs, 0), x1 = Math.max(...xs, 1), y0 = Math.min(...ys, 0), y1 = Math.max(...ys, 1);
  const padx = (x1 - x0) * 0.12 || 1, pady = (y1 - y0) * 0.12 || 1; x0 -= padx; x1 += padx; y0 -= pady; y1 += pady;
  const pw = W - 2 * m, ph = H - mt - m, k = Math.min(pw / (x1 - x0), ph / (y1 - y0));
  const ox = m + (pw - k * (x1 - x0)) / 2, oy = mt + (ph - k * (y1 - y0)) / 2 + k * (y1 - y0);
  const X = (v) => ox + (v - x0) * k, Y = (v) => oy - (v - y0) * k;
  let b = '';
  if (o.grid !== false) {
    const xt = niceTicks(x0, x1, 12), yt = niceTicks(y0, y1, 10);
    xt.ticks.forEach((t) => { b += `<line x1="${f(X(t))}" y1="${f(Y(y1))}" x2="${f(X(t))}" y2="${f(Y(y0))}" stroke="${T.grid}"/>`; });
    yt.ticks.forEach((t) => { b += `<line x1="${f(X(x0))}" y1="${f(Y(t))}" x2="${f(X(x1))}" y2="${f(Y(t))}" stroke="${T.grid}"/>`; });
    if (o.axes) { b += `<line x1="${f(X(x0))}" y1="${f(Y(0))}" x2="${f(X(x1))}" y2="${f(Y(0))}" stroke="${T.axis}" stroke-width="1.5"/><line x1="${f(X(0))}" y1="${f(Y(y0))}" x2="${f(X(0))}" y2="${f(Y(y1))}" stroke="${T.axis}" stroke-width="1.5"/>`;
      xt.ticks.forEach((t) => { if (t) b += `<text x="${f(X(t))}" y="${f(Y(0) + 16)}" text-anchor="middle" font-size="11" fill="${T.dim}">${fmtTick(t)}</text>`; });
      yt.ticks.forEach((t) => { if (t) b += `<text x="${f(X(0) - 6)}" y="${f(Y(t) + 4)}" text-anchor="end" font-size="11" fill="${T.dim}">${fmtTick(t)}</text>`; }); }
  }
  let ci = 0;
  const col = (ob) => ob.color || T.pal[(ci++) % 8];
  const lbl = (text, x, y, c, dx = 8, dy = -8) => (text ? `<text x="${f(X(x) + dx)}" y="${f(Y(y) + dy)}" font-size="16" font-weight="600" fill="${c || T.fg}">${esc(text)}</text>` : '');
  for (const ob of objs) {
    try {
      const c = col(ob);
      if (ob.type === 'polygon') { const pts = ob.points.map(pt); b += `<polygon points="${pts.map((p) => `${f(X(p[0]))},${f(Y(p[1]))}`).join(' ')}" fill="${ob.fill ? c : 'none'}" fill-opacity=".18" stroke="${c}" stroke-width="2.6" stroke-linejoin="round"/>`; }
      else if (ob.type === 'segment' || ob.type === 'vector') {
        const a = pt(ob.a), e = pt(ob.b); b += `<line x1="${f(X(a[0]))}" y1="${f(Y(a[1]))}" x2="${f(X(e[0]))}" y2="${f(Y(e[1]))}" stroke="${c}" stroke-width="2.6" ${ob.dashed ? 'stroke-dasharray="7 6"' : ''} stroke-linecap="round"/>`;
        if (ob.type === 'vector') { const ang = Math.atan2(Y(e[1]) - Y(a[1]), X(e[0]) - X(a[0])), sx = X(e[0]), sy = Y(e[1]); b += `<polygon points="${f(sx)},${f(sy)} ${f(sx - 14 * Math.cos(ang - 0.4))},${f(sy - 14 * Math.sin(ang - 0.4))} ${f(sx - 14 * Math.cos(ang + 0.4))},${f(sy - 14 * Math.sin(ang + 0.4))}" fill="${c}"/>`; }
        if (ob.label) b += `<text x="${f((X(a[0]) + X(e[0])) / 2 + 8)}" y="${f((Y(a[1]) + Y(e[1])) / 2 - 8)}" font-size="15" fill="${c}">${esc(ob.label)}</text>`;
      } else if (ob.type === 'line') {
        const a = pt(ob.a), e = pt(ob.b), dx = e[0] - a[0], dy = e[1] - a[1], L = 1e3; b += `<line x1="${f(X(a[0] - dx * L))}" y1="${f(Y(a[1] - dy * L))}" x2="${f(X(a[0] + dx * L))}" y2="${f(Y(a[1] + dy * L))}" stroke="${c}" stroke-width="2.2" ${ob.dashed ? 'stroke-dasharray="7 6"' : ''}/>`;
      } else if (ob.type === 'circle') { const cc = pt(ob.center); b += `<circle cx="${f(X(cc[0]))}" cy="${f(Y(cc[1]))}" r="${f(ob.r * k)}" fill="${ob.fill ? c : 'none'}" fill-opacity=".15" stroke="${c}" stroke-width="2.6" ${ob.dashed ? 'stroke-dasharray="7 6"' : ''}/>${ob.label ? lbl(ob.label, cc[0] + ob.r * 0.7, cc[1] + ob.r * 0.7, c) : ''}`; }
      else if (ob.type === 'arc') { const cc = pt(ob.center), a1 = (ob.from * Math.PI) / 180, a2 = (ob.to * Math.PI) / 180, r = ob.r * k; const sx = X(cc[0]) + r * Math.cos(a1), sy = Y(cc[1]) - r * Math.sin(a1), ex = X(cc[0]) + r * Math.cos(a2), ey = Y(cc[1]) - r * Math.sin(a2); b += `<path d="M${f(sx)},${f(sy)} A${f(r)},${f(r)} 0 ${((ob.to - ob.from + 360) % 360) > 180 ? 1 : 0} 0 ${f(ex)},${f(ey)}" fill="none" stroke="${c}" stroke-width="2.6"/>`; }
      else if (ob.type === 'angle') { // отметка угла в вершине между лучами p1 и p2
        const v = pt(ob.vertex), p1 = pt(ob.p1), p2 = pt(ob.p2), a1 = Math.atan2(p1[1] - v[1], p1[0] - v[0]), a2 = Math.atan2(p2[1] - v[1], p2[0] - v[0]); let d = a2 - a1; while (d <= -Math.PI) d += 2 * Math.PI; while (d > Math.PI) d -= 2 * Math.PI;
        const r = 30, sx = X(v[0]) + r * Math.cos(a1), sy = Y(v[1]) - r * Math.sin(a1), ex = X(v[0]) + r * Math.cos(a1 + d), ey = Y(v[1]) - r * Math.sin(a1 + d);
        if (ob.right) { const q = 16, u1 = [Math.cos(a1), -Math.sin(a1)], u2 = [Math.cos(a1 + d), -Math.sin(a1 + d)]; const vx = X(v[0]), vy = Y(v[1]); b += `<path d="M${f(vx + q * u1[0])},${f(vy + q * u1[1])} L${f(vx + q * (u1[0] + u2[0]))},${f(vy + q * (u1[1] + u2[1]))} L${f(vx + q * u2[0])},${f(vy + q * u2[1])}" fill="none" stroke="${c}" stroke-width="2"/>`; }
        else b += `<path d="M${f(sx)},${f(sy)} A${r},${r} 0 0 ${d > 0 ? 0 : 1} ${f(ex)},${f(ey)}" fill="none" stroke="${c}" stroke-width="2.2"/>`;
        if (ob.label) { const mid = a1 + d / 2; b += `<text x="${f(X(v[0]) + 48 * Math.cos(mid) - 8)}" y="${f(Y(v[1]) - 48 * Math.sin(mid) + 5)}" font-size="15" fill="${c}">${esc(ob.label)}</text>`; }
      } else if (ob.type === 'text') b += `<text x="${f(X(ob.x))}" y="${f(Y(ob.y))}" font-size="${ob.size || 16}" fill="${ob.color || T.fg}">${esc(ob.text)}</text>`;
    } catch {}
  }
  for (const ob of objs) if (ob.type === 'point') b += `<circle cx="${f(X(ob.x))}" cy="${f(Y(ob.y))}" r="5.5" fill="${T.fg}"/>${lbl(ob.label ?? ob.name, ob.x, ob.y, T.fg, 9, -9)}`;
  return wrap(W, H, b, T, o.title);
}

// ---------------- graphviz и произвольный SVG ----------------
export function graphviz(dot, theme = 'dark') {
  const T = THEMES[theme] || THEMES.dark;
  const src = String(dot).replace(/^\s*(strict\s+)?(di)?graph[^{]*\{/i, (m) => `${m}\n  bgcolor="${T.bg}"; node [color="${T.pal[0]}", fontcolor="${T.fg}", style="rounded", shape=box, fontname="Helvetica"]; edge [color="${T.dim}", fontcolor="${T.dim}", fontname="Helvetica"];\n`);
  const r = spawnSync('dot', ['-Tsvg'], { input: src, encoding: 'utf8', timeout: 20000 });
  if (r.error) throw new Error('graphviz (dot) не установлен на сервере: apt install graphviz');
  if (r.status !== 0) throw new Error('Ошибка DOT: ' + (r.stderr || '').slice(0, 300));
  return r.stdout;
}

export function sanitizeSvg(svg, theme = 'dark') {
  const T = THEMES[theme] || THEMES.dark;
  let s = String(svg).trim();
  if (!/<svg[\s>]/i.test(s)) throw new Error('Нужен корректный <svg>…</svg>');
  s = s.replace(/<\?xml[\s\S]*?\?>/g, '').replace(/<!DOCTYPE[\s\S]*?>/gi, '').replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<foreignObject[\s\S]*?<\/foreignObject>/gi, '')
    .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*')/gi, '').replace(/(xlink:)?href\s*=\s*("(?!#)[^"]*"|'(?!#)[^']*')/gi, '');
  if (!/xmlns=/.test(s)) s = s.replace(/<svg/i, '<svg xmlns="http://www.w3.org/2000/svg"');
  if (!/viewBox=/i.test(s)) { const w = s.match(/<svg[^>]*\swidth="(\d+)/i)?.[1] || 800, h = s.match(/<svg[^>]*\sheight="(\d+)/i)?.[1] || 600; s = s.replace(/<svg/i, `<svg viewBox="0 0 ${w} ${h}"`); }
  const vb = s.match(/viewBox="([\d.\-\s,]+)"/i)[1].split(/[\s,]+/).map(Number);
  if (!/data-nobg/.test(s)) s = s.replace(/(<svg[^>]*>)/i, `$1<rect x="${vb[0]}" y="${vb[1]}" width="${vb[2]}" height="${vb[3]}" fill="${T.bg}"/>`);
  if (s.length > 800000) throw new Error('SVG слишком большой');
  return s;
}
