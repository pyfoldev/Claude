// Быстрый путь управления телефоном: маленькая модель (Qwen3-0.6B + LoRA, GGUF) на CPU сервера превращает фразу в действия `phone` за доли секунды.
// Всё непонятное она отдаёт большой модели (пустой список). Выполнение — тем же инструментом `phone` (с теми же проверками подтверждений).
import fs from 'node:fs';
import path from 'node:path';
import { config } from './config.js';
import { slotsOk } from './slotCheck.js';

const SCHEMA = {
  open_app: { app: 's!' }, close_app: { app: 's!' }, alarm: { hour: 'i!', minute: 'i', label: 's' }, timer: { seconds: 'i!', label: 's' }, stopwatch: { op: 's' }, flashlight: { on: 'b' },
  toggle: { target: 's!', on: 'b' }, volume: { level: 'i!', target: 's' }, brightness: { level: 'i!' }, system: { op: 's!' }, media: { op: 's!' }, music_play: { query: 's!', app: 's' },
  call: { to: 's!' }, message: { app: 's!', to: 's!', text: 's!' }, remind: { text: 's!', minutes: 'i!' },
};
const ENUM = {
  toggle: { target: ['wifi', 'bluetooth', 'airplane', 'dnd', 'autorotate', 'nfc', 'hotspot', 'location', 'battery_saver'] },
  system: { op: ['home', 'back', 'recents', 'notifications', 'quick_settings', 'lock'] },
  media: { op: ['play', 'pause', 'toggle', 'next', 'prev', 'stop', 'forward', 'rewind', 'volume_up', 'volume_down'] },
  stopwatch: { op: ['start', 'stop', 'status'] }, volume: { target: ['media', 'ring', 'alarm'] }, message: { app: ['whatsapp', 'telegram'] },
};
/** Проверка действия по схеме (зеркало phone-model/sim.py). Возвращает null, если всё верно, иначе текст ошибки. */
export function validateAction(a) {
  if (!a || typeof a !== 'object' || !SCHEMA[a.action]) return 'неизвестное действие';
  const spec = SCHEMA[a.action];
  for (const [k, v] of Object.entries(a)) {
    if (k === 'action') continue;
    const t = spec[k]; if (!t) return `лишнее поле ${k}`;
    const ty = t[0];
    if (ty === 'i' && !Number.isInteger(v)) return `${k}: нужен int`;
    if (ty === 'b' && typeof v !== 'boolean') return `${k}: нужен bool`;
    if (ty === 's' && (typeof v !== 'string' || !v.trim())) return `${k}: нужна строка`;
    if (ENUM[a.action]?.[k] && !ENUM[a.action][k].includes(v)) return `${k}: недопустимое значение`;
  }
  for (const [k, t] of Object.entries(spec)) if (t.endsWith('!') && !(k in a)) return `нет поля ${k}`;
  if (a.action === 'alarm' && !(a.hour >= 0 && a.hour <= 23 && (a.minute ?? 0) >= 0 && (a.minute ?? 0) <= 59)) return 'время вне диапазона';
  if (a.action === 'timer' && !(a.seconds >= 1 && a.seconds <= 86400)) return 'длительность вне диапазона';
  if ((a.action === 'volume' || a.action === 'brightness') && !(a.level >= 0 && a.level <= 100)) return 'уровень вне 0..100';
  if (a.action === 'remind' && !(a.minutes >= 1 && a.minutes <= 43200)) return 'minutes вне диапазона';
  return null;
}

const PROMPT = (t) => `<|im_start|>user\n${t}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n`;
const modelPath = () => process.env.PHONE_MODEL_PATH || path.resolve(config.dataDir, 'models', 'phone.gguf');
export const phoneModelEnabled = () => process.env.PHONE_MODEL !== '0' && fs.existsSync(modelPath());

let ready = null, llama = null, model = null, ctx = null, seq = null, grammar = null, chain = Promise.resolve();
async function load() {
  const { getLlama, LlamaCompletion } = await import('node-llama-cpp');
  llama = await getLlama({ build: 'never', progressLogs: false });
  model = await llama.loadModel({ modelPath: modelPath() });
  ctx = await model.createContext({ contextSize: 512, threads: +process.env.PHONE_MODEL_THREADS || undefined });
  const schema = { type: 'array', maxItems: 4, items: { type: 'object', properties: { action: { enum: Object.keys(SCHEMA) } }, required: ['action'], additionalProperties: true } };
  grammar = await llama.createGrammarForJsonSchema(schema);
  seq = ctx.getSequence();
  return LlamaCompletion;
}

/** Фраза → { actions, ms } | null (null — пусть решает большая модель). Запросы идут по очереди. */
export function phoneFast(text) {
  const run = async () => {
    const t0 = Date.now();
    const C = await (ready ||= load());
    const comp = new C({ contextSequence: seq });
    seq.clearHistory?.();
    const out = await comp.generateCompletion(PROMPT(String(text).slice(0, 300)), { maxTokens: 120, temperature: 0, grammar, stopOnAbortSignal: false });
    let acts; try { acts = JSON.parse(out.trim()); } catch { return null; }
    if (!Array.isArray(acts) || !acts.length) return null;
    for (const a of acts) { const e = validateAction(a); if (e) return null; }
    if (!slotsOk(acts, String(text))) return null;   // числа сверяем независимым разбором фразы; сомнение → большая модель
    return { actions: acts, ms: Date.now() - t0 };
  };
  const p = chain.then(run, run); chain = p.catch(() => {});
  return p.catch((e) => { console.error('phoneFast:', e.message); return null; });
}
