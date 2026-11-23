// Клиент MCP (Model Context Protocol) по HTTP (Streamable HTTP): подключение к удалённым MCP-серверам и вызов их инструментов агентом.
import { db } from './db.js';

const PROTO = '2025-03-26';
const sessions = new Map();     // serverId -> { sid, tools, at }
const TTL = 10 * 60e3;

/** Каталог готовых подключений (удалённые MCP-серверы; токен вводится пользователем). */
export const MCP_PRESETS = [
  { id: 'context7', name: 'Context7', desc: 'Актуальная документация библиотек и фреймворков', url: 'https://mcp.context7.com/mcp', auth: 'none' },
  { id: 'deepwiki', name: 'DeepWiki', desc: 'Разбор любых GitHub-репозиториев: структура, вопросы по коду', url: 'https://mcp.deepwiki.com/mcp', auth: 'none' },
  { id: 'github', name: 'GitHub', desc: 'Репозитории, issues, pull request, код, Actions', url: 'https://api.githubcopilot.com/mcp/', auth: 'bearer', hint: 'Personal Access Token (github.com/settings/tokens)' },
  { id: 'huggingface', name: 'Hugging Face', desc: 'Поиск моделей, датасетов, Spaces и статей', url: 'https://huggingface.co/mcp', auth: 'bearer', hint: 'Токен hf_… (huggingface.co/settings/tokens)' },
  { id: 'linear', name: 'Linear', desc: 'Задачи, проекты и циклы Linear', url: 'https://mcp.linear.app/mcp', auth: 'bearer', hint: 'API-ключ Linear (Settings → API)' },
  { id: 'stripe', name: 'Stripe', desc: 'Платежи, клиенты, счета, подписки', url: 'https://mcp.stripe.com', auth: 'bearer', hint: 'Restricted key rk_… или sk_…' },
  { id: 'supabase', name: 'Supabase', desc: 'Базы данных, SQL, проекты Supabase', url: 'https://mcp.supabase.com/mcp', auth: 'bearer', hint: 'Personal access token (supabase.com/dashboard/account/tokens)' },
  { id: 'cloudflare-docs', name: 'Cloudflare Docs', desc: 'Документация Cloudflare', url: 'https://docs.mcp.cloudflare.com/mcp', auth: 'none' },
  { id: 'exa', name: 'Exa Search', desc: 'Нейропоиск Exa как MCP', url: 'https://mcp.exa.ai/mcp', auth: 'none', hint: 'Можно без ключа (лимит); с ключом: …/mcp?exaApiKey=КЛЮЧ' },
  { id: 'tavily', name: 'Tavily', desc: 'Поиск и извлечение страниц', url: 'https://mcp.tavily.com/mcp/?tavilyApiKey=', auth: 'url', hint: 'Допишите ключ в конец адреса' },
  { id: 'firecrawl', name: 'Firecrawl', desc: 'Скрейпинг и обход сайтов', url: 'https://mcp.firecrawl.dev/КЛЮЧ/v2/mcp', auth: 'url', hint: 'Замените КЛЮЧ на свой API-ключ' },
  { id: 'zapier', name: 'Zapier', desc: '7000+ приложений через Zapier MCP', url: 'https://mcp.zapier.com/api/mcp/mcp', auth: 'bearer', hint: 'Ключ Zapier MCP (mcp.zapier.com)' },
  { id: 'custom', name: 'Свой сервер', desc: 'Любой удалённый MCP-сервер (Streamable HTTP)', url: '', auth: 'bearer', hint: 'Адрес и, если нужен, токен' },
];

const hdrs = (s) => { try { return JSON.parse(s.headers || '{}'); } catch { return {}; } };

async function readRpc(r, id) {
  const ct = r.headers.get('content-type') || '';
  if (!ct.includes('text/event-stream')) { const j = await r.json().catch(() => null); return Array.isArray(j) ? j.find((x) => x.id === id) : j; }
  let buf = '', data = [];
  const dec = new TextDecoder();
  for await (const chunk of r.body) {
    buf += dec.decode(chunk, { stream: true });
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).replace(/\r$/, ''); buf = buf.slice(i + 1);
      if (line.startsWith('data:')) data.push(line.slice(5).trim());
      else if (line === '' && data.length) {
        try { const m = JSON.parse(data.join('\n')); if (m.id === id) return m; } catch {}
        data = [];
      }
    }
  }
  return null;
}

async function rpc(server, state, method, params, { notify = false, signal } = {}) {
  const id = notify ? undefined : Math.floor(Math.random() * 1e9);
  const body = { jsonrpc: '2.0', method, ...(params ? { params } : {}), ...(notify ? {} : { id }) };
  const headers = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream', 'MCP-Protocol-Version': PROTO, ...hdrs(server) };
  if (state.sid) headers['Mcp-Session-Id'] = state.sid;
  const sig = signal ? AbortSignal.any([signal, AbortSignal.timeout(30000)]) : AbortSignal.timeout(30000);
  const r = await fetch(server.url, { method: 'POST', headers, body: JSON.stringify(body), signal: sig });
  const sid = r.headers.get('mcp-session-id'); if (sid) state.sid = sid;
  if (notify) { await r.arrayBuffer().catch(() => {}); return null; }
  if (r.status === 404 && state.sid) { const e = new Error('session'); e.expired = true; throw e; }
  if (r.status === 401 || r.status === 403) throw new Error(`${server.name}: нужна авторизация (проверьте токен) — HTTP ${r.status}`);
  if (!r.ok) throw new Error(`${server.name}: HTTP ${r.status} ${(await r.text().catch(() => '')).slice(0, 120)}`);
  const msg = await readRpc(r, id);
  if (!msg) throw new Error(`${server.name}: пустой ответ`);
  if (msg.error) throw new Error(`${server.name}: ${msg.error.message || 'ошибка MCP'}`);
  return msg.result;
}

async function connect(server, signal) {
  const state = { sid: null, tools: null, at: 0 };
  await rpc(server, state, 'initialize', { protocolVersion: PROTO, capabilities: {}, clientInfo: { name: 'OpenAgent', version: '1.0' } }, { signal });
  await rpc(server, state, 'notifications/initialized', null, { notify: true, signal }).catch(() => {});
  sessions.set(server.id, state);
  return state;
}

export async function mcpTools(server, { force = false, signal } = {}) {
  let st = sessions.get(server.id);
  if (st?.tools && !force && Date.now() - st.at < TTL) return st.tools;
  if (!st) st = await connect(server, signal);
  const all = []; let cursor;
  for (let i = 0; i < 5; i++) {
    let res;
    try { res = await rpc(server, st, 'tools/list', cursor ? { cursor } : {}, { signal }); }
    catch (e) { if (e.expired) { st = await connect(server, signal); res = await rpc(server, st, 'tools/list', {}, { signal }); } else throw e; }
    all.push(...(res.tools || [])); cursor = res.nextCursor; if (!cursor) break;
  }
  st.tools = all; st.at = Date.now();
  return all;
}

export async function mcpCallTool(server, tool, args, signal) {
  let st = sessions.get(server.id) || await connect(server, signal);
  let res;
  try { res = await rpc(server, st, 'tools/call', { name: tool, arguments: args || {} }, { signal }); }
  catch (e) { if (e.expired) { st = await connect(server, signal); res = await rpc(server, st, 'tools/call', { name: tool, arguments: args || {} }, { signal }); } else throw e; }
  const parts = (res.content || []).map((c) => c.type === 'text' ? c.text : c.type === 'image' ? '[изображение]' : c.type === 'resource' ? (c.resource?.text || `[ресурс ${c.resource?.uri || ''}]`) : `[${c.type}]`);
  const text = parts.join('\n') || (res.structuredContent ? JSON.stringify(res.structuredContent) : '(пусто)');
  return (res.isError ? 'Ошибка инструмента: ' : '') + text;
}

// ---- интеграция с агентом ----
const safe = (s) => String(s).replace(/[^a-zA-Z0-9_-]+/g, '_').slice(0, 24);
export const mcpServers = (uid) => db.prepare('SELECT * FROM mcp_servers WHERE user_id=? AND enabled=1 ORDER BY id').all(uid);
export const mcpAllServers = (uid) => db.prepare('SELECT * FROM mcp_servers WHERE user_id=? ORDER BY id').all(uid);

/** Перед запуском агента: обновляет кэш инструментов включённых серверов (с ограничением по времени). */
export async function prepareMcp(uid) {
  const list = mcpServers(uid);
  if (!list.length) return;
  await Promise.race([Promise.allSettled(list.map((s) => mcpTools(s).catch(() => null))), new Promise((r) => setTimeout(r, 6000))]);
}

/** Определения инструментов для модели (из кэша, синхронно). */
export function mcpToolDefs(uid) {
  const out = [];
  for (const s of mcpServers(uid)) {
    const tools = sessions.get(s.id)?.tools; if (!tools) continue;
    for (const t of tools) {
      if (out.length >= 48) break;
      const params = t.inputSchema && t.inputSchema.type === 'object' ? t.inputSchema : { type: 'object', properties: {} };
      out.push({ type: 'function', function: { name: `mcp_${s.id}_${safe(t.name)}`, description: `[${s.name}] ${String(t.description || t.name).slice(0, 380)}`, parameters: params } });
    }
  }
  return out;
}

/** Выполнение вызова mcp_<id>_<tool> (имя сопоставляется со списком инструментов сервера). */
export async function mcpCall(uid, fname, args, signal) {
  const m = /^mcp_(\d+)_(.+)$/.exec(fname);
  if (!m) return 'Ошибка: неизвестный MCP-инструмент';
  const server = db.prepare('SELECT * FROM mcp_servers WHERE id=? AND user_id=? AND enabled=1').get(+m[1], uid);
  if (!server) return 'Ошибка: подключение отключено или удалено';
  const tools = sessions.get(server.id)?.tools || await mcpTools(server, { signal });
  const tool = tools.find((t) => safe(t.name) === m[2]);
  if (!tool) return 'Ошибка: у сервера нет такого инструмента';
  try { return String(await mcpCallTool(server, tool.name, args, signal)).slice(0, 8000); } catch (e) { return `Ошибка MCP: ${e.message}`; }
}
export const forgetMcp = (id) => sessions.delete(id);
