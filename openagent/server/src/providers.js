import crypto from 'node:crypto';
import { config } from './config.js';
import { db, now } from './db.js';
import { riverProv } from './llm.js';
import { bridgeHas, bridgeFetch } from './bridge.js';
import { kieFetcher, kieModels } from './kie.js';
import { pplxUp, pplxFetch, PPLX_MODELS } from './perplexity.js';
export const groqUp = (user) => !!user && (bridgeHas(user.id, 'api.groq.com') || !!process.env.GROQ_API_KEY);

const key = crypto.createHash('sha256').update(config.jwtSecret).digest();
const enc = (t) => { const iv = crypto.randomBytes(12); const c = crypto.createCipheriv('aes-256-gcm', key, iv); const b = Buffer.concat([c.update(t, 'utf8'), c.final()]); return Buffer.concat([iv, c.getAuthTag(), b]).toString('base64'); };
const dec = (t) => { const b = Buffer.from(t, 'base64'); const d = crypto.createDecipheriv('aes-256-gcm', key, b.subarray(0, 12)); d.setAuthTag(b.subarray(12, 28)); return Buffer.concat([d.update(b.subarray(28)), d.final()]).toString('utf8'); };

export const encSecret = enc;
export const decSecret = dec;
const cache = new Map();
const COARENA = { id: 'coarena', name: 'Coarena', baseUrl: 'https://coarena.ai/api/v1' };
const GROQ = { id: 'groq', name: 'Groq', baseUrl: 'https://api.groq.com/openai/v1' };
const groqModels = () => (process.env.GROQ_MODELS || 'openai/gpt-oss-120b').split(',').map((x) => x.trim()).filter(Boolean);
// Puter (puter.js): OpenAI-совместимый шлюз к десяткам моделей (GPT, Claude, Gemini, Llama, Mistral…). Ключ — токен Puter (puter.com → Dashboard → API token), PUTER_AUTH_TOKEN.
const PUTER = { id: 'puter', name: 'Puter', baseUrl: 'https://api.puter.com/puterai/openai/v1' };
const putersModels = () => (process.env.PUTER_MODELS || 'gpt-5-nano,gpt-5-mini,claude-sonnet-4-5,claude-haiku-4-5,gemini-2.5-flash,deepseek-chat').split(',').map((x) => x.trim()).filter(Boolean);
// Простые OpenAI-совместимые провайдеры: ключ в .env → провайдер появляется у всех без ввода ключа в приложении.
const SIMPLE = [
  { id: 'dahl', name: 'Dahl Inference', baseUrl: 'https://inference.dahl.global/v1', env: 'DAHL_API_KEY', models: 'DAHL_MODELS', dflt: 'deepseek-ai/DeepSeek-V4-Flash-0731', minTokens: 3000, firstTokenMs: 30000, fixed: true },   // MiniMax убран: холодный старт ~80 с и «мысли» в тексте
  { id: 'cohere', name: 'Cohere', baseUrl: 'https://api.cohere.ai/compatibility/v1', env: 'COHERE_API_KEY', models: 'COHERE_MODELS', dflt: 'command-a-03-2025,command-r-plus-08-2024,command-r7b-12-2024' },
  { id: 'vyce', name: 'Vyce AI', baseUrl: 'https://vyceai.com/v1', env: 'VYCE_API_KEY', models: 'VYCE_MODELS', dflt: '' },
];
const simpleModels = (x) => (process.env[x.models] || x.dflt).split(',').map((m) => m.trim()).filter(Boolean);
const KIE = { id: 'kie', name: 'kie.ai', baseUrl: 'https://api.kie.ai' };   // у моделей разные протоколы: адаптер kie.js
const UNO = { id: 'unorouter', name: 'UnoRouter', baseUrl: 'https://api.unorouter.com/v1' };
const UNO_DEFAULT = 'kimi-k3.1-pro:free,claude-haiku-5-5:free,gemini-3.6-flash:free,deepseek-v4.1-flash:free,gpt-oss-120b:free,glm-5.3-flash:free,qwen3.5-397b-a17b:free,nemotron-3-ultra-550b-a55b:free,minimax-m3.1-flash:free';
const unoModels = () => (process.env.UNOROUTER_MODELS || UNO_DEFAULT).split(',').map((x) => x.trim()).filter(Boolean);
const coarenaModels = () => (process.env.COARENA_MODELS || 'gpt-6-luna,claude-haiku-5-5,gemini-3-8-flash,deepseek-v4-1-flash-1017').split(',').map((x) => x.trim()).filter(Boolean);

/** Список моделей провайдера + текст ошибки, если не получилось (нужно, чтобы пользователь видел причину). */
export async function fetchModels(prov) {
  try {
    const r = await fetch(`${prov.baseUrl}/models`, { headers: { Authorization: `Bearer ${prov.apiKey}`, ...(prov.headers || {}) }, signal: AbortSignal.timeout(12000) });
    if (!r.ok) return { models: [], error: r.status === 401 || r.status === 403 ? 'Неверный API-ключ' : `HTTP ${r.status}` };
    const j = await r.json();
    return { models: (j.data || j.models || []).map((m) => m.id || m.name).filter(Boolean).sort() };
  } catch (e) { return { models: [], error: e.name === 'TimeoutError' ? 'Нет ответа от сервера провайдера' : `Не удалось подключиться: ${e.message}` }; }
}
export async function listModels(prov, id) {
  const hit = cache.get(id);
  if (hit && now() - hit.t < 600e3) return hit.models;
  const { models } = await fetchModels(prov);
  if (models.length) cache.set(id, { t: now(), models });
  return models.length ? models : hit?.models || [];
}

export const cachedModels = (id) => cache.get(id)?.models || [];

export function resolveProvider(user, id) {
  if (!id || id === 'river') return { id: 'river', ...riverProv(), name: 'river.ai' };
  { const x = SIMPLE.find((y) => y.id === id); if (x && process.env[x.env]) return { id: x.id, name: x.name, baseUrl: x.baseUrl, apiKey: process.env[x.env], effort: false, ...(x.minTokens ? { minTokens: x.minTokens } : {}), ...(x.firstTokenMs ? { firstTokenMs: x.firstTokenMs } : {}) }; }
  if (id === 'kie' && process.env.KIE_API_KEY) return { ...KIE, apiKey: process.env.KIE_API_KEY, effort: false, fetcher: kieFetcher(process.env.KIE_API_KEY), maxConc: 3, firstTokenMs: 45000 };
  if (id === 'puter' && process.env.PUTER_AUTH_TOKEN) return { ...PUTER, apiKey: process.env.PUTER_AUTH_TOKEN, effort: false };
  if (id === 'unorouter' && process.env.UNOROUTER_API_KEY) return { ...UNO, apiKey: process.env.UNOROUTER_API_KEY, effort: false };
  if (id === 'perplexity' && pplxUp(user)) return { id: 'perplexity', name: 'Perplexity Agent', baseUrl: 'https://api.perplexity.ai', apiKey: '', effort: false };
  if (id === 'groq' && bridgeHas(user.id, 'api.groq.com')) return { ...GROQ, apiKey: '', effort: true, fetcher: (url, init) => bridgeFetch(user.id, url, init) };   // запросы выполняет приложение (ключ Groq только на телефоне)
  if (id === 'groq' && process.env.GROQ_API_KEY) return { ...GROQ, apiKey: process.env.GROQ_API_KEY, effort: true };
  if (id === 'coarena' && process.env.COARENA_API_KEY) return { ...COARENA, apiKey: process.env.COARENA_API_KEY, effort: false };
  const r = db.prepare('SELECT * FROM providers WHERE id=? AND user_id=?').get(+id, user.id);
  if (!r) return { id: 'river', ...riverProv(), name: 'river.ai' };
  return { id: String(r.id), name: r.name, baseUrl: r.base_url, apiKey: dec(r.api_key), effort: !!r.effort_param };
}

// Если модели указаны вручную — показываем только их (чистый список), иначе всё, что вернул провайдер
const mergeModels = (a, extra) => { const e = extra ? extra.split(',').map((x) => x.trim()).filter(Boolean) : []; return e.length ? e : a; };

export async function providersFor(user) {
  const out = [];
  const rp = riverProv();
  const rm = await listModels(rp, 'river');
  out.push({ id: 'river', name: 'river.ai', builtin: true, baseUrl: rp.baseUrl, effort: true, models: rm.filter((m) => config.river.allowed.includes(m)) });
  if (process.env.KIE_API_KEY) out.push({ id: 'kie', name: KIE.name, builtin: true, baseUrl: KIE.baseUrl, effort: false, models: kieModels() });
  for (const x of SIMPLE) if (process.env[x.env]) {
    const all = await listModels({ id: x.id, baseUrl: x.baseUrl, apiKey: process.env[x.env] }, x.id);
    const want = simpleModels(x);
    out.push({ id: x.id, name: x.name, builtin: true, baseUrl: x.baseUrl, effort: false, models: process.env[x.models] || x.fixed ? want : all.length ? all : want });
  }
  if (process.env.PUTER_AUTH_TOKEN) {
    const all = await listModels({ ...PUTER, apiKey: process.env.PUTER_AUTH_TOKEN }, 'puter');
    out.push({ id: 'puter', name: PUTER.name, builtin: true, baseUrl: PUTER.baseUrl, effort: false, models: all.length ? all : putersModels() });
  }
  if (process.env.COARENA_API_KEY) {
    const all = await listModels({ ...COARENA, apiKey: process.env.COARENA_API_KEY }, 'coarena');
    const want = coarenaModels();
    out.push({ id: 'coarena', name: 'Coarena', builtin: true, baseUrl: COARENA.baseUrl, effort: false, models: want.filter((m) => !all.length || all.includes(m)) });
  }
  if (process.env.UNOROUTER_API_KEY) {
    const all = await listModels({ ...UNO, apiKey: process.env.UNOROUTER_API_KEY }, 'unorouter');
    out.push({ id: 'unorouter', name: 'UnoRouter (free)', builtin: true, baseUrl: UNO.baseUrl, effort: false, models: unoModels().filter((m) => !all.length || all.includes(m)) });
  }
  if (groqUp(user)) out.push({ id: 'groq', name: bridgeHas(user.id, 'api.groq.com') ? 'Groq (через телефон)' : 'Groq', builtin: true, baseUrl: GROQ.baseUrl, effort: true, models: groqModels() });
  if (pplxUp(user)) out.push({ id: 'perplexity', name: 'Perplexity Agent', builtin: true, baseUrl: 'https://api.perplexity.ai', effort: false, models: PPLX_MODELS });
  for (const r of db.prepare('SELECT * FROM providers WHERE user_id=? ORDER BY id').all(user.id)) {
    const p = resolveProvider(user, r.id);
    out.push({ id: String(r.id), name: r.name, builtin: false, baseUrl: r.base_url, effort: !!r.effort_param, keyHint: '…' + p.apiKey.slice(-4), models: mergeModels(await listModels(p, String(r.id)), r.extra_models) });
  }
  return out;
}

export const PRESETS = [
  { name: 'Dahl Inference', baseUrl: 'https://inference.dahl.global/v1', models: '', keyUrl: 'https://inference.dahl.global', note: 'OpenAI-совместимый; список моделей подтягивается сам' },
  { name: 'Cohere', baseUrl: 'https://api.cohere.ai/compatibility/v1', models: 'command-a-03-2025,command-r-plus-08-2024,command-r7b-12-2024', keyUrl: 'https://dashboard.cohere.com/api-keys', note: 'Command-модели; бесплатный пробный ключ на dashboard.cohere.com' },
  { name: 'Vyce AI', baseUrl: 'https://vyceai.com/v1', models: '', keyUrl: 'https://vyceai.com', note: 'Прокси к Claude, GPT, DeepSeek и др.; ключ в личном кабинете' },
  { name: 'Puter', baseUrl: PUTER.baseUrl, models: '', keyUrl: 'https://puter.com/dashboard', note: 'Токен Puter (Dashboard → API token). Модели GPT, Claude, Gemini и др. через один ключ' },
  { name: 'UnoRouter', baseUrl: UNO.baseUrl, models: UNO_DEFAULT, keyUrl: 'https://unorouter.com', note: 'Модели :free — бесплатные; для части нужно один раз дать согласие на сайте' },
  { name: 'Coarena', baseUrl: COARENA.baseUrl, models: 'gpt-6-luna,gemini-3-8-flash,deepseek-v4-1-flash-1017', keyUrl: 'https://coarena.ai/api', note: 'Бесплатный ключ на coarena.ai/api (30 запросов/мин)' },
  { name: 'OpenRouter', baseUrl: 'https://openrouter.ai/api/v1', models: '', keyUrl: 'https://openrouter.ai/keys' },
  { name: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1', models: 'deepseek-chat', keyUrl: 'https://platform.deepseek.com/api_keys' },
  { name: 'OpenAI', baseUrl: 'https://api.openai.com/v1', models: '', keyUrl: 'https://platform.openai.com/api-keys' },
];

/** Добавляет провайдера и сразу проверяет подключение: возвращает список моделей или причину ошибки. */
export async function addProvider(user, { name, baseUrl, apiKey, effort, models }) {
  baseUrl = String(baseUrl || '').trim().replace(/\/+$/, '');
  if (!/^https?:\/\//.test(baseUrl)) throw new Error('Адрес должен начинаться с http:// или https://');
  const extra = String(models || '').split(/[\s,;]+/).filter(Boolean).join(',');
  const key = String(apiKey || '').trim();
  const check = await fetchModels({ baseUrl, apiKey: key || 'none' });
  if (check.error && /ключ/.test(check.error) && !extra) throw new Error(check.error + ' — проверьте ключ');
  const id = db.prepare('INSERT INTO providers(user_id,name,base_url,api_key,effort_param,extra_models,created_at) VALUES (?,?,?,?,?,?,?)')
    .run(user.id, String(name || baseUrl.replace(/^https?:\/\//, '').split('/')[0]).slice(0, 40), baseUrl, enc(key || 'none'), effort ? 1 : 0, extra, now()).lastInsertRowid;
  cache.delete(String(id));
  const list = mergeModels(check.models, extra);
  return { id: String(id), models: list, warning: check.error && !list.length ? check.error : check.error ? `${check.error} (используются указанные вручную модели)` : null };
}
export const removeProvider = (user, id) => db.prepare('DELETE FROM providers WHERE id=? AND user_id=?').run(+id, user.id).changes > 0;
export const refreshModels = (id) => cache.delete(String(id));
