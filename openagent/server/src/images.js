// Генерация изображений через UnoRouter (бесплатные :free модели). Первая — лучшая по качеству, остальные — запасные.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const BASE = 'https://api.unorouter.com/v1';
export const imageEnabled = () => !!process.env.UNOROUTER_API_KEY;
const models = () => (process.env.IMAGE_MODELS || 'flux-2-dev:free,flux-2-klein-9b:free,flux.1-schnell:free,phoenix-1.0:free,lucid-origin:free,agnes-image-2.5-flash:free').split(',').map((s) => s.trim()).filter(Boolean);
const SIZES = { square: '1024x1024', portrait: '832x1216', landscape: '1216x832' };

class ConsentError extends Error { constructor(m, detail) { super(m); this.detail = detail; } }
async function one(model, prompt, size, signal) {
  const r = await fetch(`${BASE}/images/generations`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${process.env.UNOROUTER_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, prompt, n: 1, size, response_format: 'b64_json' }),
    signal: AbortSignal.any([signal, AbortSignal.timeout(90000)].filter(Boolean)),
  });
  const txt = await r.text();
  if (!r.ok) {
    if (/consent_required/.test(txt)) { let msg = ''; try { msg = JSON.parse(txt).error?.message || ''; } catch {} throw new ConsentError(`${model}: нужно согласие`, msg); }
    throw new Error(`${model}: HTTP ${r.status}`);
  }
  let j; try { j = JSON.parse(txt); } catch { throw new Error(`${model}: некорректный ответ`); }
  const d = j.data?.[0];
  if (d?.b64_json) return Buffer.from(d.b64_json.replace(/^data:[^,]+,/, ''), 'base64');
  if (d?.url) {
    const img = await fetch(d.url, { signal: AbortSignal.timeout(60000) });
    if (!img.ok) throw new Error(`${model}: не скачалась картинка (${img.status})`);
    return Buffer.from(await img.arrayBuffer());
  }
  throw new Error(`${model}: в ответе нет изображения`);
}

/** Модель выбирает сервер (агент названия выдумывает). Возвращает { file, model }. */
export async function generateImage({ prompt, aspect = 'square' }, dir, signal) {
  if (!imageEnabled()) throw new Error('Генерация изображений не настроена (нет UNOROUTER_API_KEY)');
  const size = SIZES[aspect] || SIZES.square;
  const errs = []; let consent = 0, tried = 0, detail = '';
  for (const m of models()) {
    tried++;
    try {
      const buf = await one(m, String(prompt).slice(0, 1500), size, signal);
      if (buf.length < 500) throw new Error(`${m}: пустое изображение`);
      fs.mkdirSync(dir, { recursive: true });
      const isJpg = buf[0] === 0xff && buf[1] === 0xd8;
      const file = path.join(dir, `img_${Date.now().toString(36)}_${crypto.randomBytes(2).toString('hex')}.${isJpg ? 'jpg' : 'png'}`);
      fs.writeFileSync(file, buf);
      return { file, model: m };
    } catch (e) {
      if (signal?.aborted) throw e;
      if (e instanceof ConsentError) { consent++; detail ||= e.detail; } else errs.push(e.message);
      if (consent >= 2 && !errs.length) break;               // везде одно и то же — не мучаем остальные
    }
  }
  if (consent && !errs.length) throw new Error(`UnoRouter просит один раз дать согласие на использование моделей (${detail.slice(0, 200)}). Нужно подтвердить на https://unorouter.com (вход тем же аккаунтом, где получен ключ). Пользователю так и скажи, не повторяй вызов.`);
  throw new Error('Не удалось создать изображение: ' + errs.join(' | ').slice(0, 300) + '. Не повторяй вызов больше одного раза.');
}
