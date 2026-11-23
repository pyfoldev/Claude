// Разбор сохранённых ответов API (phone-data/*.json) без написания кода: показать структуру, найти записи, ближайшие точки по координатам.
import fs from 'node:fs';
import path from 'node:path';
import { workspaceOf } from './workspace.js';

const LAT = ['lat', 'latitude', 'y', 'la', 'lt'], LON = ['lon', 'lng', 'long', 'longitude', 'x', 'lo', 'ln'];
function coordsOf(o) {
  if (!o || typeof o !== 'object') return null;
  const low = Object.fromEntries(Object.keys(o).map((k) => [k.toLowerCase(), o[k]]));
  const num = (v) => (typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' && !isNaN(+v) ? +v : null);
  let la = null, lo = null;
  for (const k of LAT) if (la === null && num(low[k]) !== null) la = num(low[k]);
  for (const k of LON) if (lo === null && num(low[k]) !== null) lo = num(low[k]);
  if (la === null || lo === null) {
    const arr = o.coordinates || o.coords || o.position || o.location || o.geometry?.coordinates || low.pos;
    if (Array.isArray(arr) && arr.length >= 2 && typeof arr[0] === 'number') { [lo, la] = arr[0] > 90 || Math.abs(arr[0]) > Math.abs(arr[1]) ? [arr[0], arr[1]] : [arr[1], arr[0]]; }
    else if (arr && typeof arr === 'object' && !Array.isArray(arr)) { const c = coordsOf(arr); if (c) return c; }
  }
  return la !== null && lo !== null && Math.abs(la) <= 90 && Math.abs(lo) <= 180 ? { la, lo } : null;
}
/** Все «записи» (объекты) внутри JSON, в т.ч. вложенные в массивы/GeoJSON; для GeoJSON поля берём из properties. */
function records(j, out = [], depth = 0) {
  if (depth > 6 || out.length > 50000) return out;
  if (Array.isArray(j)) { for (const x of j) { if (x && typeof x === 'object' && !Array.isArray(x)) out.push(x); records(x, out, depth + 1); } }
  else if (j && typeof j === 'object') for (const v of Object.values(j)) if (v && typeof v === 'object') records(v, out, depth + 1);
  return out;
}
const flat = (o) => (o?.properties && o.type === 'Feature' ? { ...o.properties, geometry: o.geometry } : o);
const hay = (o) => JSON.stringify(o).toLowerCase();
const hav = (a, b, c, d) => { const r = Math.PI / 180, dx = (d - b) * r * Math.cos(((a + c) / 2) * r), dy = (c - a) * r; return Math.round(6371000 * Math.hypot(dx, dy)); };
const brief = (o) => { const f = { ...flat(o) }; delete f.geometry; const s = JSON.stringify(f); return s.length > 320 ? s.slice(0, 320) + '…' : s; };

export function dataQuery(user, a) {
  const name = path.basename(String(a.file || '')); if (!name) return 'Нужен file (имя из phone-data)';
  const dir = path.join(workspaceOf(user.id), 'phone-data');
  if (a.op === 'list' || !fs.existsSync(path.join(dir, name))) {
    const l = fs.existsSync(dir) ? fs.readdirSync(dir) : [];
    return a.op === 'list' ? (l.join(', ') || 'Файлов нет') : `Файл ${name} не найден. Есть: ${l.join(', ') || 'ничего'}`;
  }
  let j; try { j = JSON.parse(fs.readFileSync(path.join(dir, name), 'utf8')); } catch { return 'Файл не JSON'; }
  const recs = records(j).map(flat);
  const filt = String(a.filter || a.query || '').toLowerCase();
  const n = Math.min(Math.max(+a.n || 5, 1), 20);
  if (a.op === 'find') {
    const hit = recs.filter((o) => !filt || hay(o).includes(filt)).slice(0, 20);
    return hit.length ? `Найдено ${hit.length}${hit.length === 20 ? '+' : ''}:\n` + hit.map(brief).join('\n') : `Ничего не найдено по «${a.query}» среди ${recs.length} записей`;
  }
  if (a.op === 'nearest') {
    const la = +a.lat, lo = +a.lon; if (!isFinite(la) || !isFinite(lo)) return 'Нужны lat и lon';
    const withC = recs.map((o) => ({ o, c: coordsOf(o) })).filter((x) => x.c && (!filt || hay(x.o).includes(filt)));
    if (!withC.length) return `Нет записей с координатами${filt ? ` по фильтру «${filt}»` : ''} (всего записей: ${recs.length}). Структура: ${brief(recs[0] || {})}`;
    const best = withC.map((x) => ({ ...x, d: hav(la, lo, x.c.la, x.c.lo) })).sort((p, q) => p.d - q.d).slice(0, n);
    return `Ближайшие (из ${withC.length}):\n` + best.map((x) => `${x.d} м · (${x.c.la.toFixed(5)}, ${x.c.lo.toFixed(5)}) · ${brief(x.o)}`).join('\n');
  }
  return `Записей: ${recs.length}. Первые:\n` + recs.slice(0, 3).map(brief).join('\n') + '\nОперации: show | find{query} | nearest{lat,lon,n,filter?} | list';
}
