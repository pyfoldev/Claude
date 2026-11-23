// Потоковое распознавание речи: Deepgram (nova-3). Приложение шлёт PCM (16 кГц, 16 бит, моно) на наш WebSocket,
// сервер пересылает его в Deepgram и возвращает текст по мере речи + события конца фразы. Ключ Deepgram остаётся на сервере.
// Протокол к приложению прежний: ready / delta (закреплённый текст) / interim (текущий черновик фразы) / turn_end / done / error / closed.
import { WebSocketServer, WebSocket } from 'ws';
import jwt from 'jsonwebtoken';
import { config, isOwnerEmail } from './config.js';
import { db } from './db.js';
import { registerBridge } from './bridge.js';
import { voiceAgentSession } from './voiceAgent.js';

const DG_HTTP = 'https://api.deepgram.com/v1/listen';
const DG_WS = 'wss://api.deepgram.com/v1/listen';
const langOf = (l) => { const x = String(l || '').trim().toLowerCase(); return !x || x === 'auto' ? 'multi' : x.slice(0, 5); };

function userFrom(req, u) {
  const h = req.headers.authorization || '';
  const token = h.startsWith('Bearer ') ? h.slice(7) : u.searchParams.get('token');
  try { const { uid } = jwt.verify(token, config.jwtSecret); return db.prepare('SELECT id FROM users WHERE id=?').get(uid) || null; } catch { return null; }
}

function bridge(ws, params) {
  const send = (o) => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(o)); };
  if (!config.deepgram.apiKey) { send({ t: 'error', message: 'DEEPGRAM_API_KEY не задан' }); return ws.close(); }
  const silence = Math.min(Math.max(parseInt(params.get('silence')) || 550, 250), 2000);
  const q = new URLSearchParams({
    model: config.deepgram.streamModel, language: langOf(params.get('lang')), encoding: 'linear16', sample_rate: '16000', channels: '1',
    interim_results: 'true', smart_format: 'true', punctuate: 'true', endpointing: String(silence), utterance_end_ms: '1000', vad_events: 'true',
  });
  let ready = false, ended = false, finished = false, turnSent = false; const queue = []; let full = '';
  const up = new WebSocket(`${DG_WS}?${q}`, { headers: { Authorization: `Token ${config.deepgram.apiKey}` }, handshakeTimeout: 8000 });
  const upSend = (o) => { if (up.readyState === WebSocket.OPEN) up.send(JSON.stringify(o)); };
  const finish = () => { if (finished) return; finished = true; send({ t: 'done', text: full.trim() }); send({ t: 'closed' }); try { ws.close(); } catch {} };

  up.on('open', () => { ready = true; send({ t: 'model', model: config.deepgram.streamModel }); send({ t: 'ready' }); for (const b of queue.splice(0)) up.send(b); if (ended) upSend({ type: 'CloseStream' }); });
  up.on('unexpected-response', (_req, res) => {
    res.resume();
    const msg = res.statusCode === 401 || res.statusCode === 403 ? 'Deepgram: неверный ключ или нет доступа' : res.statusCode === 402 ? 'Deepgram: закончился баланс' : res.statusCode === 429 ? 'Deepgram: превышен лимит запросов' : `Deepgram не принял подключение (HTTP ${res.statusCode})`;
    send({ t: 'error', message: msg }); try { ws.close(); } catch {}
  });
  up.on('message', (data) => {
    let j; try { j = JSON.parse(data.toString()); } catch { return; }
    if (j.type === 'Results') {
      const text = (j.channel?.alternatives?.[0]?.transcript || '').trim();
      if (j.is_final) {
        if (text) { turnSent = false; full += (full ? ' ' : '') + text; send({ t: 'delta', text: text + ' ' }); }
        send({ t: 'interim', text: '' });
        if (j.speech_final && !turnSent) { turnSent = true; send({ t: 'eager' }); send({ t: 'turn_end' }); }
      } else if (text) send({ t: 'interim', text });
    } else if (j.type === 'UtteranceEnd') { if (!turnSent && full) { turnSent = true; send({ t: 'turn_end' }); } }
    else if (j.type === 'Error' || j.err_code) send({ t: 'error', message: String(j.description || j.err_msg || 'ошибка распознавания').slice(0, 200) });
  });
  up.on('error', (e) => { if (!ready) { send({ t: 'error', message: `Нет связи с Deepgram: ${e.message}` }); try { ws.close(); } catch {} } });
  up.on('close', () => finish());

  ws.on('message', (data, isBinary) => {
    if (isBinary) { const b = Buffer.isBuffer(data) ? data : Buffer.from(data); if (ready) { if (up.readyState === WebSocket.OPEN) up.send(b); } else if (queue.length < 400) queue.push(b); return; }
    let m; try { m = JSON.parse(data.toString()); } catch { return; }
    if (m.t === 'end') { ended = true; if (ready) { upSend({ type: 'Finalize' }); upSend({ type: 'CloseStream' }); } }
    else if (m.t === 'flush') upSend({ type: 'Finalize' });
  });
  const kill = () => { try { up.close(); } catch {} };
  ws.on('close', kill); ws.on('error', kill);
  const keep = setInterval(() => upSend({ type: 'KeepAlive' }), 8000); keep.unref?.();
  up.on('close', () => clearInterval(keep));
  setTimeout(() => { kill(); try { ws.close(); } catch {} }, 5 * 60 * 1000).unref?.();   // страховка: одна сессия не дольше 5 минут
}

const sttWss = new WebSocketServer({ noServer: true, maxPayload: 1 << 20 });
const bridgeWss = new WebSocketServer({ noServer: true, maxPayload: 16 << 20 });
const vaWss = new WebSocketServer({ noServer: true, maxPayload: 1 << 20 });
/** Единственный обработчик upgrade: /api/stt-stream (распознавание) и /api/llm-bridge (мост Groq через телефон). */
export function attachWs(server) {
  server.on('upgrade', (req, socket, head) => {
    let u; try { u = new URL(req.url, 'http://x'); } catch { return socket.destroy(); }
    if (!['/api/stt-stream', '/api/llm-bridge', '/api/voice-agent'].includes(u.pathname)) return socket.destroy();
    const user = userFrom(req, u);
    if (!user) { socket.write('HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n'); return socket.destroy(); }
    if (u.pathname === '/api/voice-agent') vaWss.handleUpgrade(req, socket, head, (ws) => voiceAgentSession(ws, (() => { const x = db.prepare('SELECT * FROM users WHERE id=?').get(user.id); x.role = isOwnerEmail(x.email) ? 'owner' : 'user'; return x; })(), u.searchParams));
    else if (u.pathname === '/api/stt-stream') sttWss.handleUpgrade(req, socket, head, (ws) => bridge(ws, u.searchParams));
    else bridgeWss.handleUpgrade(req, socket, head, (ws) => registerBridge(user.id, ws));
  });
}
export const attachSttStream = attachWs;

/** Файловое распознавание Deepgram (prerecorded). Язык — "ru"/"en"/…; пусто или "auto" → мультиязычный режим. */
export async function deepgramTranscribe(buf, _name, mime, language) {
  if (!config.deepgram.apiKey) throw new Error('DEEPGRAM_API_KEY не задан');
  const q = new URLSearchParams({ model: config.deepgram.model, language: langOf(language), smart_format: 'true', punctuate: 'true' });
  const r = await fetch(`${DG_HTTP}?${q}`, { method: 'POST', headers: { Authorization: `Token ${config.deepgram.apiKey}`, 'Content-Type': mime && mime !== 'application/octet-stream' ? mime : 'audio/*' }, body: buf, signal: AbortSignal.timeout(120000) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.err_msg || j.reason || `Deepgram ${r.status}`);
  return (j.results?.channels?.[0]?.alternatives?.[0]?.transcript || '').trim();
}
export const mistralTranscribe = deepgramTranscribe;   // старое имя (на случай внешних импортов)
