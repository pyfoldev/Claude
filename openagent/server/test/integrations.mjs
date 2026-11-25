// Проверка коннекторов без сети: подменяем fetch и смотрим, какие запросы формируются (адрес, метод, заголовки авторизации, тело).
import { CONNECTORS } from '../src/integrations.js';
const calls = [];
globalThis.fetch = async (url, o = {}) => { calls.push({ url: String(url), method: o.method || 'GET', h: o.headers || {}, body: o.body }); return new Response(JSON.stringify({ ok: true, results: [], items: [], data: [], records: [], issues: [], messages: [], channels: [], result: [], projects: [], deployments: [] }), { status: 200, headers: { 'content-type': 'application/json' } }); };
const sample = (p) => { const o = {}; for (const [k, v] of Object.entries(p.properties || {})) o[k] = v.enum ? v.enum[0] : v.type === 'array' ? ['x@y.z'] : v.type === 'integer' ? 2 : v.type === 'object' ? { a: 1 } : v.type === 'boolean' ? true : 'x'; return o; };
let bad = 0;
for (const c of CONNECTORS) {
  const cr = Object.fromEntries(c.fields.map((f) => [f.k, f.k === 'url' ? 'https://example.test/cal.ics' : f.k === 'domain' ? 'acme.atlassian.net' : f.k === 'webhook_url' ? 'https://discord.test/api/webhooks/1/x' : 'SECRET_' + f.k]));
  for (const a of c.actions) {
    calls.length = 0; let err = '';
    try { await a.run(cr, sample(a.params)); } catch (e) { err = e.message; }
    const r = calls[0];
    const okShape = r && /^https?:\/\//.test(r.url) && !/undefined|\[object/.test(r.url);
    if (!okShape) bad++;
    console.log(`${okShape ? 'ok ' : 'BAD'} ${c.id}.${a.name}${a.write ? ' [write]' : ''}  ${r ? r.method + ' ' + r.url.slice(0, 90) : 'нет запроса'}${err && !/Cannot read|is not a function|not iterable|undefined/.test(err) ? '  ⚠ ' + err.slice(0, 80) : ''}`);
  }
}
console.log(`\nконнекторов ${CONNECTORS.length}, действий ${CONNECTORS.reduce((n, c) => n + c.actions.length, 0)}, проблем ${bad}`);
process.exit(bad ? 1 : 0);
