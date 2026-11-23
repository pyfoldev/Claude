// Описание изображения vision-моделью (для «посмотри на экран»): сначала быстрые модели Coarena/Groq, запасная — river.
import fs from 'node:fs';
import { config } from './config.js';
import { chatOnce } from './llm.js';
import { resolveProvider } from './providers.js';

export async function describeImage(user, file, prompt, signal) {
  const b64 = fs.readFileSync(file).toString('base64');
  const messages = [{ role: 'user', content: [{ type: 'text', text: prompt }, { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${b64}` } }] }];
  const tries = [];
  if (process.env.COARENA_API_KEY) tries.push(['coarena', 'gemini-3-8-flash'], ['coarena', 'gpt-6-luna']);
  tries.push(['river', config.river.visionModel]);
  let lastErr = '';
  for (const [pid, model] of tries) {
    try {
      const prov = resolveProvider(user, pid);
      const t = await chatOnce(messages, { prov, model, maxTokens: 600, signal: AbortSignal.any([signal, AbortSignal.timeout(25000)].filter(Boolean)), failFast: true });
      if (t.trim()) return t.trim();
    } catch (e) { lastErr = e.message; }
  }
  throw new Error(lastErr || 'vision-модели не ответили');
}
