// Движок режима Чат: Vercel AI SDK (`ai`, Apache-2.0) — цикл «модель → инструменты → модель», потоковый разбор tool-calls, повторы.
// Инструменты и их выполнение (поиск, графики, файлы, телефон, память…) остаются нашими: SDK лишь ведёт диалог с моделью.
import { streamText, tool, jsonSchema, stepCountIs } from 'ai';
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

export const chatEngineOn = () => process.env.CHAT_ENGINE !== 'legacy';

/** OpenAI-сообщения (как их строит buildMessages) → ModelMessage[] для AI SDK. */
export function toModelMessages(msgs) {
  const out = []; const names = new Map();
  for (const m of msgs) {
    if (m.role === 'system') continue;
    if (m.role === 'user') {
      if (typeof m.content === 'string') out.push({ role: 'user', content: m.content });
      else out.push({ role: 'user', content: (m.content || []).map((p) => p.type === 'image_url' ? { type: 'image', image: p.image_url.url } : { type: 'text', text: p.text || '' }) });
    } else if (m.role === 'assistant') {
      const parts = [];
      if (m.content) parts.push({ type: 'text', text: m.content });
      for (const c of m.tool_calls || []) {
        let input = {}; try { input = JSON.parse(c.function.arguments || '{}'); } catch {}
        names.set(c.id, c.function.name); parts.push({ type: 'tool-call', toolCallId: c.id, toolName: c.function.name, input });
      }
      out.push({ role: 'assistant', content: parts.length ? parts : '' });
    } else if (m.role === 'tool') {
      out.push({ role: 'tool', content: [{ type: 'tool-result', toolCallId: m.tool_call_id, toolName: names.get(m.tool_call_id) || 'tool', output: { type: 'text', value: String(m.content ?? '') } }] });
    }
  }
  return out;
}

const PAR = new Set(['web_search', 'web_fetch', 'read_file', 'list_dir', 'memory_search', 'grep', 'glob', 'http_request', 'delegate']);

/**
 * cb: { delta(text), assistant(content, calls[{id,name,arguments}]), tool(id,name,content,files), usage(u) }
 * execTool(call{id,function:{name,arguments}}) → Promise<{result, files}>;  shouldStop() → bool (ask_user завершил ход)
 */
export async function runChatAI({ prov, model, system, messages, toolDefs, execTool, shouldStop, signal, maxSteps, maxTokens, effort, cb }) {
  const doFetch = prov.fetcher || fetch;
  const withEffort = prov.effort && ['low', 'high', 'max'].includes(effort);
  const provider = createOpenAICompatible({
    name: prov.id || 'provider', baseURL: prov.baseUrl, apiKey: prov.apiKey || 'none', headers: prov.headers, includeUsage: true,
    fetch: withEffort ? (url, init) => { try { const b = JSON.parse(init.body); b.reasoning_effort = effort; init = { ...init, body: JSON.stringify(b) }; } catch {} return doFetch(url, init); } : doFetch,
  });
  let chain = Promise.resolve(); const files = new Map();
  const tools = {};
  for (const d of toolDefs) {
    const f = d.function;
    tools[f.name] = tool({
      description: f.description, inputSchema: jsonSchema(f.parameters || { type: 'object', properties: {} }),
      execute: async (input, { toolCallId }) => {
        const run = async () => { const r = await execTool({ id: toolCallId, function: { name: f.name, arguments: JSON.stringify(input ?? {}) } }); files.set(toolCallId, r.files || []); return String(r.result ?? ''); };
        if (PAR.has(f.name)) return run();
        const p = chain.then(run, run); chain = p.catch(() => {}); return p;   // изменяющие инструменты — строго по очереди
      },
    });
  }
  const result = streamText({
    model: provider.chatModel(model), system, messages: toModelMessages(messages), tools, maxOutputTokens: maxTokens, abortSignal: signal, maxRetries: 3,
    stopWhen: [stepCountIs(maxSteps), () => !!shouldStop?.()],
    experimental_repairToolCall: undefined,
  });
  let text = '', calls = [], results = new Map(), failed = null;
  for await (const part of result.fullStream) {
    switch (part.type) {
      case 'text-delta': text += part.text; cb.delta(part.text); break;
      case 'tool-call': calls.push({ id: part.toolCallId, name: part.toolName, arguments: JSON.stringify(part.input ?? {}) }); break;
      case 'tool-result': results.set(part.toolCallId, String(part.output ?? '')); break;
      case 'tool-error': results.set(part.toolCallId, `Ошибка: ${part.error?.message || part.error || 'сбой инструмента'}`); break;
      case 'finish-step': {
        const u = part.usage || {};
        cb.usage({ prompt_tokens: u.inputTokens ?? 0, completion_tokens: u.outputTokens ?? 0, prompt_tokens_details: { cached_tokens: u.inputTokenDetails?.cacheReadTokens ?? u.cachedInputTokens ?? 0 } });
        if (text.trim() || calls.length) {
          cb.assistant(text.trim(), calls);
          for (const c of calls) cb.tool(c.id, c.name, results.get(c.id) ?? '(нет результата)', files.get(c.id) || []);
        }
        text = ''; calls = []; results = new Map(); break;
      }
      case 'error': failed = part.error; break;
      default: break;
    }
  }
  if (failed) throw (failed instanceof Error ? failed : new Error(String(failed?.message || failed)));
}
