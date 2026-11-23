// GigaAM Multilingual 600M (ai-sage, MIT) — распознавание речи на CPU сервера через локальный сервис server/py/stt_service.py.
// Включение: STT_ENGINE=gigaam (все распознавания) или режим приложения «GigaAM + Flux» (запрашивает engine=gigaam на потоке). Нет сервиса → Deepgram.
import { spawn } from 'node:child_process';
import { config } from './config.js';

const URL_ = () => config.stt.gigaamUrl;
let _up = false, _at = 0;
/** Сервис GigaAM жив? (кэш 15 с, обновляется в фоне, вызов не блокирует). */
export function gigaamUp() {
  if (!URL_() || process.env.GIGAAM === '0') return false;
  if (Date.now() - _at > 15000) {
    _at = Date.now();
    fetch(URL_() + '/', { signal: AbortSignal.timeout(2500) }).then((r) => { _up = r.ok; }).catch(() => { _up = false; });
  }
  return _up;
}

/** GigaAM выдаёт строчные слова без знаков: делаем читаемый текст (заглавная и точка в конце). */
export function prettify(t) {
  const s = String(t || '').trim(); if (!s) return '';
  const c = s[0].toUpperCase() + s.slice(1);
  return /[.!?…]$/.test(c) ? c : c + '.';
}

/** Текст отдаём клиенту ОДИН раз — в `done` (после turn_end клиент шлёт «end», результат к этому моменту уже считается). */
/** PCM 16 кГц / 16 бит / моно → текст. */
export async function gigaamPcm(pcm, { raw = false } = {}) {
  const r = await fetch(URL_() + '/transcribe', { method: 'POST', headers: { 'content-type': 'application/octet-stream' }, body: pcm, signal: AbortSignal.timeout(180000) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `GigaAM ${r.status}`);
  return raw ? j.text || '' : prettify(j.text);
}

/** Любой аудиофайл → PCM 16 кГц моно через ffmpeg. */
export function toPcm16k(buf) {
  return new Promise((resolve, reject) => {
    const p = spawn('ffmpeg', ['-loglevel', 'error', '-i', 'pipe:0', '-f', 's16le', '-ar', '16000', '-ac', '1', 'pipe:1']);
    const out = []; let err = '';
    p.stdout.on('data', (d) => out.push(d)); p.stderr.on('data', (d) => { err += d; });
    p.on('error', reject); p.on('close', (c) => (c === 0 ? resolve(Buffer.concat(out)) : reject(new Error('ffmpeg: ' + err.slice(0, 160)))));
    p.stdin.on('error', () => {}); p.stdin.end(buf);
  });
}
export const gigaamFile = async (buf) => gigaamPcm(await toPcm16k(buf));

/**
 * Поток распознавания для приложения (тот же протокол, что у Deepgram-моста): ready / delta / turn_end / done / closed.
 * Конец фразы ищем по тишине на сервере: уже на ~300 мс тишины запускаем распознавание заранее, а если фраза продолжилась — результат отбрасываем.
 */
export function gigaamBridge(ws, params, { WebSocket }) {
  const send = (o) => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(o)); };
  const silence = Math.min(Math.max(parseInt(params.get('silence')) || 550, 250), 2000);
  const chunks = []; let bytes = 0, spoke = false, quiet = 0, noise = 300, spec = null, specBytes = -1, turnSent = false, ended = false, closed = false;
  send({ t: 'model', model: 'GigaAM-Multilingual 600M' }); send({ t: 'ready' });
  const all = () => Buffer.concat(chunks);
  const rms = (b) => { let s = 0; const n = b.length >> 1; for (let i = 0; i < n; i++) { const v = b.readInt16LE(i * 2); s += v * v; } return Math.sqrt(s / Math.max(1, n)); };
  const run = () => { const buf = all(); specBytes = buf.length; spec = gigaamPcm(buf, { raw: true }).catch((e) => { send({ t: 'error', message: `GigaAM: ${e.message}`.slice(0, 200) }); return ''; }); return spec; };
  const finish = async () => {
    if (closed) return; closed = true;
    let text = '';
    try { text = bytes < 3200 ? '' : (spec && specBytes === bytes ? await spec : await run()); } catch {}
    text = prettify(text);
    if (text) send({ t: 'delta', text: text + ' ' });
    send({ t: 'done', text }); send({ t: 'closed' }); try { ws.close(); } catch {}
  };
  ws.on('message', (data, isBinary) => {
    if (closed) return;
    if (isBinary) {
      const b = Buffer.isBuffer(data) ? data : Buffer.from(data); chunks.push(b); bytes += b.length;
      const e = rms(b); const voiced = e > Math.max(500, noise * 2.2);
      if (!voiced) noise = noise * 0.95 + e * 0.05;
      if (voiced) { spoke = true; quiet = 0; if (spec && specBytes !== bytes) { spec = null; specBytes = -1; } turnSent = false; }
      else if (spoke) { quiet += (b.length >> 1) / 16; if (quiet >= 300 && !spec && bytes > 16000) run(); if (quiet >= silence && !turnSent) { turnSent = true; send({ t: 'turn_end' }); } }
      if (bytes > 16000 * 2 * 120) finish();   // страховка: не больше 2 минут за раз
      return;
    }
    let m; try { m = JSON.parse(data.toString()); } catch { return; }
    if (m.t === 'end') { ended = true; finish(); }
  });
  const kill = () => { closed = true; };
  ws.on('close', kill); ws.on('error', kill);
  setTimeout(() => { if (!closed) finish(); }, 5 * 60 * 1000).unref?.();
}
