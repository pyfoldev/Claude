// Диагностика скорости и настроек: какие ключи заданы, какая модель отвечает в звонке, задержки LLM / озвучки / распознавания.
import { WebSocket } from 'ws';
import { config, SERVER_V } from './config.js';
import { chatOnce } from './llm.js';
import { resolveProvider, groqUp } from './providers.js';
import { bridgeUp } from './bridge.js';
import { pplxUp } from './perplexity.js';

const timed = async (fn) => { const t = Date.now(); try { const r = await fn(); return { ms: Date.now() - t, ...(r || {}) }; } catch (e) { return { ms: Date.now() - t, error: String(e.message || e).slice(0, 140) }; } };

export async function runDiag(user) {
  const keys = { groq: groqUp(user), mistral: !!config.mistral.apiKey, deepgram: !!config.deepgram.apiKey, fish: !!config.fish.apiKey, river: !!config.river.apiKey, coarena: !!process.env.COARENA_API_KEY, exa: !!process.env.EXA_API_KEY, perplexity: pplxUp(user), unorouter: !!process.env.UNOROUTER_API_KEY };
  const voiceProv = keys.groq ? 'groq' : 'river';
  const voiceModel = keys.groq ? 'openai/gpt-oss-120b' : config.river.fastModel;
  const [llm, tts, stt] = await Promise.all([
    timed(async () => { await chatOnce([{ role: 'user', content: 'Ответь одним словом: ок' }], { prov: resolveProvider(user, voiceProv), model: voiceModel, maxTokens: 12, failFast: true, signal: AbortSignal.timeout(15000) }); return { model: `${voiceProv}:${voiceModel}` }; }),
    keys.fish ? timed(async () => {
      const r = await fetch(`${process.env.FISH_BASE || 'https://api.fish.audio'}/v1/tts`, { method: 'POST', headers: { Authorization: `Bearer ${config.fish.apiKey}`, 'Content-Type': 'application/json', model: config.fish.model }, body: JSON.stringify({ text: 'Привет, как дела?', reference_id: config.fish.referenceId || '2a1036d645634680b3cc69aeeb60375b', format: 'mp3', mp3_bitrate: 64, latency: 'balanced' }), signal: AbortSignal.timeout(15000) });
      if (!r.ok) throw new Error(`Fish ${r.status}`);
      await r.body.getReader().read();                      // первые байты
      return {};
    }) : Promise.resolve({ error: 'нет FISH_API_KEY' }),
    keys.deepgram ? timed(async () => {
      const r = await fetch('https://api.deepgram.com/v1/projects', { headers: { Authorization: `Token ${config.deepgram.apiKey}` }, signal: AbortSignal.timeout(10000) });
      if (!r.ok) throw new Error(`Deepgram HTTP ${r.status}`);
      return { model: config.deepgram.model };
    }) : Promise.resolve({ error: 'нет DEEPGRAM_API_KEY' }),
  ]);
  const hints = [];
  if (!keys.groq) hints.push('Groq не подключён: укажите ключ Groq в Настройках приложения (запросы к Groq идут с телефона, сервер к нему не обращается). Пока звонок и «Авто» идут на более медленных моделях.');
  else if (bridgeUp(user.id)) hints.push('Groq работает через телефон: держите приложение открытым.');
  if (!keys.deepgram) hints.push('Нет DEEPGRAM_API_KEY: распознавание речи не работает.');
  if (!keys.mistral) hints.push('Нет MISTRAL_API_KEY: не работает память (эмбеддинги).');
  if (!keys.fish) hints.push('Нет FISH_API_KEY: нет озвучки.');
  if (llm.ms > 2500) hints.push('Ответ модели медленный (>2,5 с на «ок») — проверьте ключи/лимиты провайдера.');
  if (tts.ms > 2000) hints.push('Озвучка медленная: первый звук позже 2 с.');
  return { v: SERVER_V, keys, llm, tts, stt, hints };
}
