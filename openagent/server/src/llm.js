import { config } from './config.js';

export const riverProv = () => ({ baseUrl: config.river.baseUrl, apiKey: config.river.apiKey, effort: true });
const hdr = (p) => ({ 'Content-Type': 'application/json', Authorization: `Bearer ${p.apiKey}`, ...(p.headers || {}) });

const sleep = (ms, signal) => new Promise((res, rej) => {
  const t = setTimeout(res, ms);
  signal?.addEventListener('abort', () => { clearTimeout(t); rej(new Error('aborted')); }, { once: true });
});

// Ограничение параллельных запросов на провайдера: очередь вместо лавины 429
const sems = new Map();
async function withSlot(key, max, fn) {
  const s = sems.get(key) || sems.set(key, { n: 0, q: [] }).get(key);
  if (s.n >= max) await new Promise((res) => s.q.push(res));
  s.n++;
  try { return await fn(); } finally { s.n--; s.q.shift()?.(); }
}
const maxConc = (prov) => prov.maxConc || (prov.id === 'coarena' ? 2 : 4);

// ---- Упреждающий ограничитель (токен-бакет на провайдера+модель) ----
// Замеры River: устойчиво ~0.4–0.5 запроса/с на модель, всплеск ~6; отклонённые запросы тоже засчитываются, поэтому слепые повторы только ухудшают.
// Лимит считается ПО МОДЕЛИ → нагрузку раскидываем по нескольким дешёвым моделям, а не бьёмся в одну.
const RATES = { river: { rate: 1.5, burst: 10 }, coarena: { rate: 0.45, burst: 3 }, unorouter: { rate: 1 / 60, burst: 1 }, groq: { rate: 0.5, burst: 5 }, other: { rate: 1, burst: 6 } };
const buckets = new Map();
const rateCfg = (prov) => RATES[prov.id] || (prov.baseUrl?.includes('river.ai') ? RATES.river : RATES.other);
function bucketFor(prov, model) {
  const k = `${prov.id || prov.baseUrl}|${model}`;
  const cfg = rateCfg(prov);
  let b = buckets.get(k);
  if (!b) { b = { tokens: cfg.burst, last: Date.now(), cool: 0, ...cfg }; buckets.set(k, b); }
  const t = Date.now();
  b.tokens = Math.min(b.burst, b.tokens + ((t - b.last) / 1000) * b.rate); b.last = t;
  return b;
}
const waitOf = (b) => Math.max(b.cool - Date.now(), b.tokens >= 1 ? 0 : Math.ceil(((1 - b.tokens) / b.rate) * 1000));
/** Сколько мс до готовности модели (0 — можно слать сразу). Нужен «Авто», чтобы сразу выбирать свободного провайдера. */
export const busyMs = (prov, model) => (process.env.RATE_LIMITER === '0' ? 0 : waitOf(bucketFor(prov, model)));
export const limiterStats = () => [...buckets.entries()].map(([k, b]) => ({ k, tokens: +b.tokens.toFixed(2), cool: Math.max(0, b.cool - Date.now()) }));

/** Выбирает модель, у которой сейчас есть «токен»; если все пусты — ждёт ближайший, не отправляя заведомо отклоняемый запрос. */
async function pickModel(prov, candidates, signal, onWait) {
  if (process.env.RATE_LIMITER === '0') return candidates[0];
  for (;;) {
    let best = null;
    for (const m of candidates) {
      const w = waitOf(bucketFor(prov, m));
      if (!best || w < best.w) best = { m, w };
      if (w === 0) break;
    }
    if (best.w <= 0) { bucketFor(prov, best.m).tokens -= 1; return best.m; }
    if (best.w > 1500) onWait?.(best.w);
    await sleep(best.w + Math.floor(Math.random() * 250), signal);
  }
}
function coolDown(prov, model, ms) { const b = bucketFor(prov, model); b.cool = Date.now() + ms; b.tokens = Math.min(b.tokens, 0); }

const RETRY_STATUS = new Set([408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524]);
const QUOTA = /insufficient_quota|exceeded your current quota|billing|daily (request )?limit|free usage is used up/i;
const BACKOFF = [1500, 3000, 6000, 10000, 15000, 20000];
const MAX_RETRIES = 6;

function retryAfterMs(res) {
  const h = res?.headers?.get('retry-after');
  if (!h) return 0;
  const n = Number(h);
  if (Number.isFinite(n)) return Math.min(n * 1000, 30000);
  const d = Date.parse(h);
  return Number.isFinite(d) ? Math.min(Math.max(d - Date.now(), 0), 30000) : 0;
}

function friendly(prov, status, text) {
  const name = prov.name || 'Провайдер';
  if (status === 429 && QUOTA.test(text)) return `${name}: исчерпан лимит/квота. ${text.slice(0, 160)}`;
  if (status === 429) return `${name}: слишком много запросов — лимит не снялся после нескольких повторов. Подождите минуту или выберите другую модель.`;
  if (status === 401 || status === 403) return `${name}: неверный или неактивный API-ключ`;
  if (status >= 500) return `${name}: сервис временно недоступен (${status}). Попробуйте ещё раз.`;
  return `${name} ${status}: ${text.slice(0, 300)}`;
}

async function post1(prov, body, signal, effort) {
  const withEffort = effort && prov.effort && (effort === 'low' || effort === 'high' || effort === 'max') ? { ...body, reasoning_effort: effort } : body;
  const doFetch = prov.fetcher || fetch;
  const go = (b) => doFetch(`${prov.baseUrl}/chat/completions`, { method: 'POST', headers: hdr(prov), body: JSON.stringify(b), signal });
  let res = await go(withEffort);
  if (!res.ok && res.status === 400 && body.stream_options) { // провайдер не знает stream_options
    const b2 = { ...withEffort }; delete b2.stream_options; res = await go(b2);
  }
  if (!res.ok && withEffort !== body && res.status === 400) res = await go(body); // модель не знает такой effort
  return res;
}

/**
 * Запрос с повторами: 429/5xx/сетевые сбои → экспоненциальная пауза (с Retry-After), после 2-й неудачи — переключение на запасную модель.
 * onRetry({attempt, delay, status, model, switched}) — чтобы показать пользователю статус.
 */
async function requestWithRetry(prov, baseBody, { signal, effort, onRetry, fallbacks = [], failFast = false } = {}) {
  const candidates = [baseBody.model, ...fallbacks.filter((m) => m !== baseBody.model)];
  let model = baseBody.model;
  for (let attempt = 0; ; attempt++) {
    if (failFast && candidates.every((m) => waitOf(bucketFor(prov, m)) > 700)) throw new Error(`${prov.name || 'Провайдер'}: занят`);   // «Авто» не ждёт — идёт к следующему провайдеру
    model = await pickModel(prov, candidates, signal, (w) => onRetry?.({ attempt: 0, delay: w, status: -1, model: candidates[0], switched: false }));
    let res = null, text = '', netErr = null;
    try { res = await withSlot(prov.id || prov.baseUrl, maxConc(prov), () => post1(prov, { ...baseBody, model }, signal, effort)); }
    catch (e) { if (signal?.aborted) throw e; netErr = e; }
    if (res?.ok) return { res, model };
    if (res) text = await res.text().catch(() => '');
    const status = res?.status || 0;
    const retryable = netErr ? true : RETRY_STATUS.has(status) && !(status === 429 && QUOTA.test(text));
    if (failFast) {                                       // без повторов: охлаждаем модель и сразу отдаём ошибку — вызывающий переключится
      coolDown(prov, model, status === 401 || status === 403 || status === 404 ? 300000 : status === 429 ? Math.max(retryAfterMs(res), 20000) : 30000);
      throw new Error(netErr ? `${prov.name || 'Провайдер'}: нет связи` : friendly(prov, status, text));
    }
    if (!retryable || attempt >= MAX_RETRIES) throw new Error(netErr ? `${prov.name || 'Провайдер'}: нет связи (${netErr.cause?.code || netErr.message})` : friendly(prov, status, text));
    const ra = retryAfterMs(res);
    if (status === 429) coolDown(prov, model, Math.max(ra, 3000));          // эта модель «остывает» — следующий запрос уйдёт на другую или подождёт
    const delay = status === 429 ? Math.max(ra, 800) + Math.floor(Math.random() * 400) : BACKOFF[Math.min(attempt, BACKOFF.length - 1)] + Math.floor(Math.random() * 600);
    onRetry?.({ attempt: attempt + 1, delay, status, model, switched: candidates.length > 1 });
    await sleep(delay, signal);
  }
}

// DeepSeek иногда выдаёт вызов инструмента своей текстовой разметкой («<｜DSML｜ invoke name=…>») вместо настоящего tool_calls — разбираем её сами и не показываем пользователю.
const DSML_START = /<\s*[|｜]\s*DSML/;
const DSML_PREFIXES = ['<｜DSML｜', '<|DSML|', '< | DSML', '<｜ DSML'];
export function parseDsml(text) {
  const calls = [];
  const inv = /<\s*[|｜]\s*DSML\s*[|｜]\s*invoke\s+name\s*=\s*"([^"]+)"\s*>([\s\S]*?)<\s*\/\s*[|｜]\s*DSML\s*[|｜]\s*invoke\s*>/g;
  let m;
  while ((m = inv.exec(text))) {
    const args = {}; const par = /<\s*[|｜]\s*DSML\s*[|｜]\s*parameter\s+name\s*=\s*"([^"]+)"([^>]*)>([\s\S]*?)<\s*\/\s*[|｜]\s*DSML\s*[|｜]\s*parameter\s*>/g;
    let p;
    while ((p = par.exec(m[2]))) {
      const isStr = /string\s*=\s*"true"/.test(p[2]); const raw = p[3].trim();
      let v = raw; if (!isStr) { try { v = JSON.parse(raw); } catch {} }
      args[p[1]] = v;
    }
    calls.push({ id: '', type: 'function', function: { name: m[1], arguments: JSON.stringify(args) } });
  }
  return calls;
}

/** Стриминговый чат (OpenAI-совместимый). onText(delta) вызывается на каждый кусок текста. */
export async function chatStream({ prov = riverProv(), messages, tools, signal, onText, model, effort, maxTokens, onUsage, onRetry, fallbacks, failFast }) {
  const body = { model: model || config.river.model, messages, stream: true, stream_options: { include_usage: true } };
  if (maxTokens) body.max_tokens = maxTokens;
  if (tools?.length) { body.tools = tools; body.tool_choice = 'auto'; }

  for (let tries = 0; ; tries++) {
    const { res } = await requestWithRetry(prov, body, { signal, effort, onRetry, fallbacks, failFast });
    let content = '';
    const calls = [];
    let sent = 0, dsml = false;       // sent — сколько символов content уже показано; dsml — начался текстовый вызов инструмента
    const flush = (final = false) => {
      if (dsml) return;
      const at = content.search(DSML_START);
      if (at >= 0) { dsml = true; if (at > sent) { onText?.(content.slice(sent, at)); } sent = content.length; return; }
      let hold = content.length;
      if (!final) { const lt = content.lastIndexOf('<'); if (lt >= 0 && content.length - lt <= 12 && DSML_PREFIXES.some((p) => p.startsWith(content.slice(lt)))) hold = lt; }   // хвост может оказаться началом разметки — придерживаем
      if (hold > sent) { onText?.(content.slice(sent, hold)); sent = hold; }
    };
    try {
      let buf = '';
      const dec = new TextDecoder();
      for await (const chunk of res.body) {
        buf += dec.decode(chunk, { stream: true });
        let i;
        while ((i = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, i).trim();
          buf = buf.slice(i + 1);
          if (!line.startsWith('data:')) continue;
          const data = line.slice(5).trim();
          if (!data || data === '[DONE]') continue;
          let j;
          try { j = JSON.parse(data); } catch { continue; }
          if (j.error) throw new Error(j.error.message || 'stream error');
          if (j.usage) onUsage?.(j.usage);
          const d = j.choices?.[0]?.delta;
          if (!d) continue;
          if (d.content) { content += d.content; flush(); }
          for (const tc of d.tool_calls || []) {
            const k = tc.index ?? 0;
            calls[k] ||= { id: '', type: 'function', function: { name: '', arguments: '' } };
            if (tc.id) calls[k].id = tc.id;
            if (tc.function?.name) calls[k].function.name += tc.function.name;
            if (tc.function?.arguments) calls[k].function.arguments += tc.function.arguments;
          }
        }
      }
    } catch (e) {
      // обрыв потока до первых данных — повторяем запрос целиком; если уже что-то пришло — отдаём как есть
      if (signal?.aborted) throw e;
      if (!content && !calls.length && tries < 2) { onRetry?.({ attempt: tries + 1, delay: 1500, status: 0, model: body.model, switched: false }); await sleep(1500, signal); continue; }
      if (!content && !calls.length) throw new Error(`${prov.name || 'Провайдер'}: поток оборвался (${e.message})`);
    }
    flush(true);
    let nat = calls.filter(Boolean);
    if (dsml) {
      if (!nat.length) nat = parseDsml(content);
      content = content.slice(0, content.search(DSML_START)).trim();
    }
    const tool_calls = nat.map((c, n) => ({ ...c, id: c.id || `call_${Date.now()}_${n}` }));
    return { content, tool_calls };
  }
}

/** Простой нестриминговый вызов для служебных задач (память, суммаризация) — тоже с повторами. */
export async function chatOnce(messages, { prov = riverProv(), signal, json = false, model, maxTokens, fallbacks, failFast } = {}) {
  const body = { model: model || config.river.fastModel, messages, stream: false, max_tokens: maxTokens || 700 };
  if (json) body.response_format = { type: 'json_object' };
  let r;
  try { r = await requestWithRetry(prov, body, { signal, fallbacks, failFast }); }
  catch (e) { if (!json || failFast) throw e; delete body.response_format; r = await requestWithRetry(prov, body, { signal, fallbacks }); }
  const j = await r.res.json();
  return j.choices?.[0]?.message?.content || '';
}

export function parseJson(text) {
  try { return JSON.parse(text); } catch {}
  const m = text.match(/[\[{][\s\S]*[\]}]/);
  if (m) { try { return JSON.parse(m[0]); } catch {} }
  return null;
}

/** Эмбеддинги Mistral. Возвращает массив Float32Array либо null, если ключа нет. */
export async function embed(texts) {
  if (!config.mistral.apiKey || !texts.length) return null;
  try {
    const res = await fetch('https://api.mistral.ai/v1/embeddings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${config.mistral.apiKey}` },
      body: JSON.stringify({ model: config.mistral.embedModel, input: texts.map((t) => t.slice(0, 6000)) }),
    });
    if (!res.ok) return null;
    const j = await res.json();
    return j.data.map((d) => Float32Array.from(d.embedding));
  } catch { return null; }
}
