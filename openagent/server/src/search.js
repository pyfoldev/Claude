import { config } from './config.js';

const UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36';
const decode = (s) => s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#0?39;/g, "'").replace(/&nbsp;/g, ' ')
  .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(+n));
const strip = (h) => decode(h.replace(/<[^>]+>/g, ' ')).replace(/\s+/g, ' ').trim();

function timeout(ms, signal) {
  const ac = new AbortController();
  const t = setTimeout(() => ac.abort(), ms);
  signal?.addEventListener('abort', () => ac.abort());
  return { signal: ac.signal, done: () => clearTimeout(t) };
}

async function get(url, ms = 9000, signal, headers = {}) {
  const t = timeout(ms, signal);
  try {
    const r = await fetch(url, { signal: t.signal, headers: { 'User-Agent': UA, 'Accept-Language': 'ru,en;q=0.8', ...headers }, redirect: 'follow' });
    return { ok: r.ok, status: r.status, type: r.headers.get('content-type') || '', text: await r.text() };
  } finally { t.done(); }
}

function bingUrl(u) {
  try {
    const x = new URL(u);
    if (x.hostname.endsWith('bing.com') && x.pathname.startsWith('/ck/')) {
      const p = x.searchParams.get('u');
      if (p?.startsWith('a1')) return Buffer.from(p.slice(2).replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8');
    }
  } catch {}
  return u;
}

async function bing(q, n, signal) {
  const lang = /[а-яё]/i.test(q) ? 'setlang=ru&mkt=ru-RU' : 'setlang=en&mkt=en-US&cc=US';
  const r = await get(`https://www.bing.com/search?q=${encodeURIComponent(q)}&${lang}&count=${n}`, 9000, signal);
  const out = [];
  for (const m of r.text.matchAll(/<li class="b_algo"[\s\S]*?<\/li>/g)) {
    const a = m[0].match(/<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/);
    if (!a) continue;
    const snip = m[0].match(/<p[^>]*>([\s\S]*?)<\/p>/) || m[0].match(/class="b_lineclamp\d*"[^>]*>([\s\S]*?)<\/div>/);
    out.push({ title: strip(a[2]), url: bingUrl(decode(a[1])), snippet: snip ? strip(snip[1]) : '' });
  }
  return out;
}

async function ddg(q, n, signal) {
  const t = timeout(9000, signal);
  try {
    const r = await fetch('https://html.duckduckgo.com/html/', { method: 'POST', signal: t.signal, headers: { 'User-Agent': UA, 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ q }) });
    const html = await r.text();
    const out = [];
    for (const m of html.matchAll(/<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>[\s\S]*?class="result__snippet"[^>]*>([\s\S]*?)<\/a>/g)) {
      let u = decode(m[1]); const uddg = u.match(/uddg=([^&]+)/); if (uddg) u = decodeURIComponent(uddg[1]);
      out.push({ title: strip(m[2]), url: u.startsWith('//') ? 'https:' + u : u, snippet: strip(m[3]) });
    }
    return out.slice(0, n);
  } finally { t.done(); }
}

async function tavily(q, n, signal) {
  const r = await fetch('https://api.tavily.com/search', { method: 'POST', signal, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${process.env.TAVILY_API_KEY}` },
    body: JSON.stringify({ query: q, max_results: n, include_raw_content: false }) });
  const j = await r.json();
  return (j.results || []).map((x) => ({ title: x.title, url: x.url, snippet: x.content }));
}

async function brave(q, n, signal) {
  const r = await fetch(`https://api.search.brave.com/res/v1/web/search?q=${encodeURIComponent(q)}&count=${n}`, { signal, headers: { 'X-Subscription-Token': process.env.BRAVE_API_KEY, Accept: 'application/json' } });
  const j = await r.json();
  return (j.web?.results || []).map((x) => ({ title: x.title, url: x.url, snippet: strip(x.description || '') }));
}

/** Читаемый текст страницы: <article>/<main>, без навигации и скриптов. */
export function readable(html) {
  const title = strip((html.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [])[1] || '');
  let body = html.replace(/<(script|style|noscript|svg|iframe|form|nav|footer|header|aside)[\s\S]*?<\/\1>/gi, ' ').replace(/<!--[\s\S]*?-->/g, '');
  const main = body.match(/<(article|main)[\s\S]*?<\/\1>/i);
  if (main && strip(main[0]).length > 500) body = main[0];
  const text = decode(body.replace(/<\/(p|div|li|h\d|tr|section|br)>|<br\s*\/?>/gi, '\n').replace(/<[^>]+>/g, ''))
    .replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim();
  return { title, text };
}

export async function fetchPage(url, { signal, max = 12000 } = {}) {
  const r = await get(url, 10000, signal);
  if (!r.ok) return { url, error: `HTTP ${r.status}` };
  if (!/html|text|json|xml/.test(r.type)) return { url, error: `Тип ${r.type} — скачай через bash` };
  if (!/html/.test(r.type)) return { url, title: '', text: r.text.slice(0, max) };
  const { title, text } = readable(r.text);
  return { url, title, text: text.slice(0, max) };
}

/** Exa: нейро-поиск, сразу отдаёт текст страниц и ключевые фрагменты — без отдельных загрузок страниц (быстрее и дешевле по токенам). */
async function exa(query, n, signal, o = {}) {
  const body = { query, type: 'auto', numResults: n, contents: { text: { maxCharacters: 1500 }, highlights: { maxCharacters: 700 } } };
  if (o.category) body.category = o.category;
  if (o.days) body.startPublishedDate = new Date(Date.now() - o.days * 864e5).toISOString();
  if (o.domains?.length) body.includeDomains = o.domains;
  const r = await fetch((process.env.EXA_BASE_URL || 'https://api.exa.ai') + '/search', { method: 'POST', signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20000)]) : AbortSignal.timeout(20000),
    headers: { 'x-api-key': process.env.EXA_API_KEY, 'Content-Type': 'application/json', 'User-Agent': 'OpenAgent' }, body: JSON.stringify(body) });
  if (!r.ok) { const t = await r.text().catch(() => ''); throw new Error(`Exa ${r.status}: ${t.slice(0, 160)}`); }
  const j = await r.json();
  return (j.results || []).map((x) => ({
    title: x.title || x.url, url: x.url, date: (x.publishedDate || '').slice(0, 10), author: x.author || '',
    snippet: (x.highlights || []).join(' … ').replace(/\s+/g, ' ').slice(0, 600), text: (x.text || '').replace(/\s+/g, ' ').trim(),
  }));
}
export const exaEnabled = () => !!process.env.EXA_API_KEY;

const fmtPplx = (query, results, read) => {
  let out = `Результаты поиска «${query}» (Perplexity):\n\n`;
  results.forEach((r, i) => {
    out += `${i + 1}. ${r.title}${r.date ? ` [${r.date}]` : ''}\n   ${r.url}\n`;
    if (r.snippet) out += `   ${r.snippet.slice(0, i < Math.max(read, 2) ? 900 : 350)}\n`;
    out += '\n';
  });
  return out;
};

/** provider: 'exa' | 'pplx' | 'auto' (Exa → Perplexity → запасные). pplx(query, n, signal) — функция поиска Perplexity (через телефон/ключ сервера) или null. */
export async function webSearch(query, { signal, count = 6, read = 2, category, days, domains, provider = 'auto', pplx = null } = {}) {
  const note = [];
  const tryPplx = async () => {
    if (!pplx) return null;
    try { const res = (await pplx(query, Math.min(count, 10), signal)).filter((r) => r.url?.startsWith('http')); if (res.length) return fmtPplx(query, res, read); }
    catch (e) { note.push(`Perplexity недоступен (${e.message}) — использован запасной поиск`); }
    return null;
  };
  if (provider === 'pplx') { const o = await tryPplx(); if (o) return o; }
  if (provider !== 'pplx' && exaEnabled()) {
    try {
      const results = (await exa(query, Math.min(count, 8), signal, { category, days, domains })).filter((r) => r.url?.startsWith('http'));
      if (results.length) {
        let out = `Результаты поиска «${query}» (Exa):\n\n`;
        results.forEach((r, i) => {
          out += `${i + 1}. ${r.title}${r.date ? ` [${r.date}]` : ''}\n   ${r.url}\n`;
          if (r.snippet) out += `   ${r.snippet}\n`;
          if (i < Math.max(read, 2) && r.text) out += `   --- текст ---\n   ${r.text.slice(0, 900)}\n`;
          out += '\n';
        });
        return out;
      }
    } catch (e) { note.push(`Exa недоступен (${e.message}) — использован запасной поиск`); }
  }
  if (provider === 'auto' && !exaEnabled()) { const o = await tryPplx(); if (o) return o; }
  const providers = [];
  if (process.env.TAVILY_API_KEY) providers.push(['tavily', tavily]);
  if (process.env.BRAVE_API_KEY) providers.push(['brave', brave]);
  providers.push(['bing', bing], ['duckduckgo', ddg]);
  let results = [], used = '';
  for (const [name, fn] of providers) {
    try { results = (await fn(query, count, signal)).filter((r) => r.url?.startsWith('http')); } catch { results = []; }
    if (results.length) { used = name; break; }
  }
  if (!results.length) return 'Поиск не дал результатов (или заблокирован). Попробуй другой запрос или web_fetch по известному адресу.';
  const pages = read > 0 ? await Promise.all(results.slice(0, Math.min(read, 3)).map((r) => fetchPage(r.url, { signal, max: 1800 }).catch(() => null))) : [];
  let out = `Результаты поиска «${query}» (${used}):\n\n`;
  results.forEach((r, i) => {
    out += `${i + 1}. ${r.title}\n   ${r.url}\n   ${r.snippet}\n`;
    const p = pages[i];
    if (p?.text) out += `   --- страница ---\n   ${p.text.replace(/\n+/g, '\n   ').slice(0, 1200)}\n`;
    out += '\n';
  });
  return note.length ? `${note.join('; ')}\n\n${out}` : out;
}
