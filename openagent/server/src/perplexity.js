// Perplexity: Search API (ранжированные результаты — вместо Exa) и Agent API (полноценный агент с веб-поиском и ответом с источниками).
// Ключ хранится в приложении: запросы идут через телефон (мост) — так же, как Groq; серверный PERPLEXITY_API_KEY необязателен.
import { bridgeHas, bridgeFetch } from './bridge.js';

const HOST = 'api.perplexity.ai';
const BASE = () => process.env.PPLX_BASE || `https://${HOST}`;   // PPLX_BASE — только для тестов
export const pplxUp = (user) => !!user && (bridgeHas(user.id, HOST) || !!process.env.PERPLEXITY_API_KEY);

export function pplxFetch(user, path, init = {}) {
  const url = `${BASE()}${path}`;
  const headers = { 'Content-Type': 'application/json', ...(init.headers || {}) };
  if (bridgeHas(user.id, HOST)) return bridgeFetch(user.id, url, { ...init, headers });          // ключ добавит приложение
  return fetch(url, { ...init, headers: { ...headers, Authorization: `Bearer ${process.env.PERPLEXITY_API_KEY}` } });
}

/** Search API → [{title,url,snippet,date}] */
export async function pplxSearch(user, query, n = 6, signal) {
  const r = await pplxFetch(user, '/search', { method: 'POST', body: JSON.stringify({ query, max_results: Math.min(Math.max(n, 1), 20) }), signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(25000)]) : AbortSignal.timeout(25000) });
  if (!r.ok) { const t = await r.text().catch(() => ''); throw new Error(`Perplexity ${r.status}: ${t.slice(0, 140)}`); }
  const j = await r.json();
  return (j.results || []).map((x) => ({ title: x.title || x.url, url: x.url, snippet: String(x.snippet || '').replace(/\s+/g, ' ').trim(), date: x.last_updated || x.date || '' }));
}

// agent-* — готовые уровни агента Perplexity; «провайдер/модель» — конкретная модель через Perplexity, с веб-поиском
export const PPLX_MODELS = ['agent-fast', 'agent-low', 'agent-medium', 'agent-high', 'openai/gpt-6-luna', 'anthropic/claude-haiku-5-5'];

/** Ответ целиком через Perplexity Agent API (stream). Возвращает { text, sources } и вызывает onDelta по ходу. */
export async function pplxAgent(user, { effort = 'low', model, input, signal, onDelta, onStatus }) {
  const body = model ? { model, input, stream: true, tools: [{ type: 'web_search' }] } : { effort, input, stream: true };
  const r = await pplxFetch(user, '/v1/agent', { method: 'POST', body: JSON.stringify(body), signal });
  if (!r.ok) {
    const t = await r.text().catch(() => '');
    throw new Error(r.status === 401 || r.status === 403 ? 'Perplexity: неверный ключ или нет доступа' : r.status === 429 ? 'Perplexity: лимит запросов — подождите минуту' : `Perplexity ${r.status}: ${t.slice(0, 160)}`);
  }
  let text = '', buf = '', sources = [];
  const dec = new TextDecoder();
  const addResults = (arr) => { for (const x of arr || []) if (x?.url && !sources.some((s) => s.url === x.url)) sources.push({ id: x.id, title: x.title || x.url, url: x.url }); };
  for await (const chunk of r.body) {
    buf += dec.decode(chunk, { stream: true });
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line.startsWith('data:')) continue;
      const data = line.slice(5).trim();
      if (!data || data === '[DONE]') continue;
      let e; try { e = JSON.parse(data); } catch { continue; }
      switch (e.type) {
        case 'response.output_text.delta': if (e.delta) { text += e.delta; onDelta?.(e.delta); } break;
        case 'response.output_item.done': if (e.item?.type === 'search_results') addResults(e.item.results); break;
        case 'response.completed': {
          for (const it of e.response?.output || []) if (it.type === 'search_results') addResults(it.results);
          if (!text) text = (e.response?.output || []).filter((it) => it.type === 'message').flatMap((it) => it.content || []).filter((c) => c.type === 'output_text').map((c) => c.text).join('');
          break;
        }
        case 'response.failed': case 'error': throw new Error('Perplexity: ' + String(e.error?.message || e.response?.error?.message || 'ошибка').slice(0, 200));
        default:
          if (/search|tool|reason/.test(e.type || '')) onStatus?.(e.type);
      }
    }
  }
  return { text, sources };
}
