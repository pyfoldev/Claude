// kie.ai: одна платформа, но у моделей РАЗНЫЕ протоколы — chat/completions (Gemini, GPT-5.2), OpenAI Responses (GPT-6.x, Grok, DeepSeek, Kimi) и Claude Messages.
// Адаптер принимает обычный запрос chat/completions (как шлёт остальной код: llm.js и AI SDK) и отдаёт обычный ответ chat/completions (поток SSE или JSON),
// а внутри ходит в нужный протокол. Подключается как `fetcher` провайдера. Ключ — KIE_API_KEY (kie.ai → API Key). Маршруты — по документации docs.kie.ai.
const BASE = process.env.KIE_BASE_URL || 'https://api.kie.ai';
const gemini = (id, path = `/${id}-openai/v1/chat/completions`) => [id, { kind: 'chat', path }];
export const KIE_ROUTES = Object.fromEntries([
  ['gpt-5-2', { kind: 'chat', path: '/gpt-5-2/v1/chat/completions' }],
  gemini('gemini-3-pro', '/gemini-3-pro/v1/chat/completions'), gemini('gemini-3.1-pro', '/gemini-3.1-pro/v1/chat/completions'),
  gemini('gemini-3-6-flash'), gemini('gemini-3-8-flash'), gemini('gemini-4-argon'), gemini('gemini-4-carbon'), gemini('gemini-4-hydrogen'), gemini('gemini-4-neon'),
  ...['gpt-5-6-luna', 'gpt-5-6-terra', 'gpt-5-6-sol', 'gpt-6-astra', 'gpt-6-sol', 'gpt-6-1-terra', 'gpt-6-1-sol', 'gpt-6-2-sol', 'gpt-6-2-astra'].map((m) => [m, { kind: 'responses', path: '/codex/v1/responses' }]),
  ...['grok-4-3', 'grok-4-5', 'grok-4-6', 'grok-4-7'].map((m) => [m, { kind: 'responses', path: '/grok/v1/responses' }]),
  ...['deepseek-v4-1-flash', 'kimi-k3', 'kimi-k3-1-pro'].map((m) => [m, { kind: 'responses', path: '/openai/v1/responses' }]),
  ...['claude-opus-4-5', 'claude-opus-4-6', 'claude-opus-4-7', 'claude-opus-4-8', 'claude-opus-5', 'claude-opus-5-5', 'claude-sonnet-4-5', 'claude-sonnet-4-6', 'claude-sonnet-5', 'claude-sonnet-5-5', 'claude-haiku-4-5', 'claude-haiku-5-5', 'claude-fable-5'].map((m) => [m, { kind: 'claude', path: '/claude/v1/messages' }]),
]);
// Быстрые модели (по замерам: 1–4 с до первого слова) — первыми; Claude (12–15 с, иногда не отвечает) и Grok (долго «думает») — в конце.
const SLOW = /^(claude|grok)/;
export const kieModels = () => (process.env.KIE_MODELS ? process.env.KIE_MODELS.split(',').map((x) => x.trim()).filter(Boolean) : [...Object.keys(KIE_ROUTES).filter((m) => !SLOW.test(m)).sort((a, b) => (b === 'deepseek-v4-1-flash') - (a === 'deepseek-v4-1-flash')), ...Object.keys(KIE_ROUTES).filter((m) => SLOW.test(m))]);

const textOf = (c) => (typeof c === 'string' ? c : (c || []).filter((p) => p.type === 'text').map((p) => p.text).join(''));
const dataUrl = (u) => { const m = /^data:([^;]+);base64,(.*)$/s.exec(u || ''); return m ? { media: m[1], data: m[2] } : null; };
const args = (s) => { try { return JSON.parse(s || '{}'); } catch { return {}; } };

/** chat/completions → тело Responses API */
export function toResponses(b) {
  const input = []; const sys = [];
  for (const m of b.messages || []) {
    if (m.role === 'system') { sys.push(textOf(m.content)); continue; }
    if (m.role === 'user') input.push({ role: 'user', content: typeof m.content === 'string' ? [{ type: 'input_text', text: m.content }] : m.content.map((p) => (p.type === 'image_url' ? { type: 'input_image', image_url: p.image_url.url } : { type: 'input_text', text: p.text || '' })) });
    else if (m.role === 'assistant') {
      if (textOf(m.content)) input.push({ role: 'assistant', content: [{ type: 'output_text', text: textOf(m.content) }] });
      for (const c of m.tool_calls || []) input.push({ type: 'function_call', call_id: c.id, name: c.function.name, arguments: c.function.arguments || '{}' });
    } else if (m.role === 'tool') input.push({ type: 'function_call_output', call_id: m.tool_call_id, output: textOf(m.content) });
  }
  const o = { model: b.model, input, stream: true };
  if (sys.length) o.instructions = sys.join('\n\n');
  if (b.tools?.length) o.tools = b.tools.map((t) => ({ type: 'function', name: t.function.name, description: t.function.description, parameters: t.function.parameters }));
  if (b.max_tokens) o.max_output_tokens = b.max_tokens;
  o.reasoning = { effort: b.reasoning_effort || process.env.KIE_EFFORT || 'low' };   // по умолчанию — быстро: иначе модели тратят сотни токенов на «размышления» даже для простого вопроса
  return o;
}

/** chat/completions → тело Claude Messages */
export function toClaude(b) {
  const sys = []; const msgs = [];
  const push = (role, blocks) => { const last = msgs[msgs.length - 1]; if (last && last.role === role) last.content.push(...blocks); else msgs.push({ role, content: blocks }); };
  for (const m of b.messages || []) {
    if (m.role === 'system') { sys.push(textOf(m.content)); continue; }
    if (m.role === 'user') push('user', typeof m.content === 'string' ? [{ type: 'text', text: m.content }] : m.content.map((p) => { const d = p.type === 'image_url' ? dataUrl(p.image_url.url) : null; return d ? { type: 'image', source: { type: 'base64', media_type: d.media, data: d.data } } : { type: 'text', text: p.text || '' }; }));
    else if (m.role === 'assistant') { const bl = []; if (textOf(m.content)) bl.push({ type: 'text', text: textOf(m.content) }); for (const c of m.tool_calls || []) bl.push({ type: 'tool_use', id: c.id, name: c.function.name, input: args(c.function.arguments) }); if (bl.length) push('assistant', bl); }
    else if (m.role === 'tool') push('user', [{ type: 'tool_result', tool_use_id: m.tool_call_id, content: textOf(m.content) || '(пусто)' }]);
  }
  const o = { model: b.model, max_tokens: b.max_tokens || 4096, messages: msgs, stream: true };
  if (sys.length) o.system = sys.join('\n\n');
  if (b.tools?.length) o.tools = b.tools.map((t) => ({ name: t.function.name, description: t.function.description, input_schema: t.function.parameters || { type: 'object', properties: {} } }));
  return o;
}

async function* sse(res) {   // события SSE: {event, data}
  let buf = ''; const dec = new TextDecoder();
  for await (const chunk of res.body) {
    buf += dec.decode(chunk, { stream: true }); let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, i); buf = buf.slice(i + 2);
      const ev = /^event:\s*(.*)$/m.exec(block)?.[1]?.trim(); const data = block.split('\n').filter((l) => l.startsWith('data:')).map((l) => l.slice(5).trim()).join('');
      if (!data || data === '[DONE]') continue;
      try { yield { event: ev, data: JSON.parse(data) }; } catch {}
    }
  }
}

/** Responses-поток → куски chat/completions: {text}|{tool:{index,id,name,args}}|{usage}|{error} */
export async function* fromResponses(res) {
  const idx = new Map(); let n = 0;
  for await (const { event, data } of sse(res)) {
    const t = data.type || event;
    if (t === 'response.output_text.delta' && data.delta) yield { text: data.delta };
    else if (t === 'response.output_item.added' && data.item?.type === 'function_call') { idx.set(data.item.id, n); yield { tool: { index: n++, id: data.item.call_id || data.item.id, name: data.item.name, args: '' } }; }
    else if (t === 'response.function_call_arguments.delta') yield { tool: { index: idx.get(data.item_id) ?? 0, args: data.delta } };
    else if (t === 'response.completed') { const u = data.response?.usage; if (u) yield { usage: { prompt_tokens: u.input_tokens || 0, completion_tokens: u.output_tokens || 0, prompt_tokens_details: { cached_tokens: u.input_tokens_details?.cached_tokens || 0 } } }; }
    else if (t === 'response.failed' || t === 'error') yield { error: data.response?.error?.message || data.message || 'ошибка kie.ai' };
  }
}
/** Claude-поток → те же куски */
export async function* fromClaude(res) {
  let inTok = 0, cached = 0; const idx = new Map(); let n = 0;
  for await (const { event, data } of sse(res)) {
    const t = data.type || event;
    if (t === 'message_start') { const u = data.message?.usage || {}; inTok = (u.input_tokens || 0) + (u.cache_read_input_tokens || 0); cached = u.cache_read_input_tokens || 0; }
    else if (t === 'content_block_start' && data.content_block?.type === 'tool_use') { idx.set(data.index, n); yield { tool: { index: n++, id: data.content_block.id, name: data.content_block.name, args: '' } }; }
    else if (t === 'content_block_delta') { const d = data.delta || {}; if (d.type === 'text_delta') yield { text: d.text }; else if (d.type === 'input_json_delta') yield { tool: { index: idx.get(data.index) ?? 0, args: d.partial_json } }; }
    else if (t === 'message_delta') yield { usage: { prompt_tokens: inTok, completion_tokens: data.usage?.output_tokens || 0, prompt_tokens_details: { cached_tokens: cached } } };
    else if (t === 'error') yield { error: data.error?.message || 'ошибка kie.ai' };
  }
}

const jerr = (status, message) => new Response(JSON.stringify({ error: { message } }), { status, headers: { 'content-type': 'application/json' } });
const KIE_CODE = { 401: 401, 402: 402, 403: 403, 404: 404, 410: 404, 422: 400, 429: 429, 455: 503, 500: 502, 501: 502, 505: 503 };

/** fetcher провайдера: принимает запрос chat/completions, возвращает ответ chat/completions */
export function kieFetcher(apiKey) {
  return async (_url, init) => {
    const b = JSON.parse(init.body); const route = KIE_ROUTES[b.model];
    if (!route) return jerr(404, `kie.ai: модель ${b.model} не подключена (список: KIE_MODELS)`);
    const wantStream = !!b.stream;
    const body = route.kind === 'responses' ? toResponses(b) : route.kind === 'claude' ? toClaude(b) : b;
    // kie.ai иногда «зависает» без ответа (Claude Sonnet — 100+ с): ждём заголовки не дольше 60 с и говорим об этом прямо
    const hang = new AbortController(); const timer = setTimeout(() => hang.abort(), +process.env.KIE_HEADERS_TIMEOUT_MS || 60000);
    let up;
    try { up = await fetch(BASE + route.path, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` }, body: JSON.stringify(body), signal: init.signal ? AbortSignal.any([init.signal, hang.signal]) : hang.signal }); }
    catch (e) { clearTimeout(timer); if (init.signal?.aborted) throw e; return jerr(504, hang.signal.aborted ? `kie.ai: модель ${b.model} не ответила за 60 с (перегружена) — выберите другую` : `kie.ai: нет связи (${e.message})`); }
    clearTimeout(timer);
    const ct = up.headers.get('content-type') || '';
    if (!up.ok || !/event-stream/.test(ct)) {                           // ошибки kie.ai приходят и как HTTP-статус, и как JSON {code,msg} с кодом 200
      const txt = await up.text().catch(() => ''); let j = null; try { j = JSON.parse(txt); } catch {}
      const code = +(j?.code ?? j?.error?.code) || up.status;
      if (up.ok && wantStream === false && route.kind === 'chat' && j?.choices) return new Response(txt, { status: 200, headers: { 'content-type': 'application/json' } });
      if (code !== 200 || !up.ok) return jerr(KIE_CODE[code] || (up.ok ? 502 : up.status), `kie.ai ${code}: ${j?.msg || j?.error?.message || j?.message || txt.slice(0, 200)}`);
      return jerr(502, `kie.ai: неожиданный ответ ${txt.slice(0, 200)}`);
    }
    if (route.kind === 'chat') return up;                                // уже chat/completions (поток) — отдаём как есть (для stream:false kie отвечает JSON, см. выше)
    const gen = route.kind === 'responses' ? fromResponses(up) : fromClaude(up);
    const enc = new TextEncoder(); const id = `kie-${Date.now()}`;
    const chunk = (delta, extra = {}) => `data: ${JSON.stringify({ id, object: 'chat.completion.chunk', model: b.model, choices: [{ index: 0, delta, finish_reason: null }], ...extra })}\n\n`;
    if (wantStream) {
      return new Response(new ReadableStream({
        async start(ctrl) {
          try {
            let sawTool = false;
            for await (const p of gen) {
              if (p.text) ctrl.enqueue(enc.encode(chunk({ content: p.text })));
              else if (p.tool) { sawTool = true; ctrl.enqueue(enc.encode(chunk({ tool_calls: [{ index: p.tool.index, ...(p.tool.id ? { id: p.tool.id, type: 'function' } : {}), function: { ...(p.tool.name ? { name: p.tool.name } : {}), arguments: p.tool.args || '' } }] }))); }
              else if (p.usage) ctrl.enqueue(enc.encode(`data: ${JSON.stringify({ id, object: 'chat.completion.chunk', model: b.model, choices: [], usage: p.usage })}\n\n`));
              else if (p.error) ctrl.enqueue(enc.encode(`data: ${JSON.stringify({ error: { message: p.error } })}\n\n`));
            }
            ctrl.enqueue(enc.encode(`data: ${JSON.stringify({ id, object: 'chat.completion.chunk', model: b.model, choices: [{ index: 0, delta: {}, finish_reason: sawTool ? 'tool_calls' : 'stop' }] })}\n\ndata: [DONE]\n\n`));
          } catch (e) { ctrl.enqueue(enc.encode(`data: ${JSON.stringify({ error: { message: e.message } })}\n\n`)); }
          ctrl.close();
        },
      }), { status: 200, headers: { 'content-type': 'text/event-stream' } });
    }
    // без потока: собираем ответ целиком
    let content = ''; const calls = []; let usage;
    for await (const p of gen) {
      if (p.error) return jerr(502, p.error);
      if (p.text) content += p.text; else if (p.usage) usage = p.usage;
      else if (p.tool) { const c = (calls[p.tool.index] ||= { id: '', type: 'function', function: { name: '', arguments: '' } }); if (p.tool.id) c.id = p.tool.id; if (p.tool.name) c.function.name = p.tool.name; c.function.arguments += p.tool.args || ''; }
    }
    const message = { role: 'assistant', content, ...(calls.length ? { tool_calls: calls.filter(Boolean) } : {}) };
    return new Response(JSON.stringify({ id, object: 'chat.completion', model: b.model, choices: [{ index: 0, message, finish_reason: calls.length ? 'tool_calls' : 'stop' }], usage }), { status: 200, headers: { 'content-type': 'application/json' } });
  };
}
