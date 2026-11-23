// Тест голосового цикла: сервер OpenAgent + Deepgram Voice Agent (Haiku 4.5 + «Владимир»). Речь пользователя — синтезированная (реальный аудиопоток в микрофон).
import { spawn } from 'node:child_process';
import jwt from 'jsonwebtoken';
import { WebSocket } from 'ws';
import { mkUser } from './harness.mjs';
import { config } from '../src/config.js';

const PORT = 18787;
const user = mkUser('voice@example.com', 'owner');
const token = jwt.sign({ uid: user.id }, config.jwtSecret);

async function tts16k(text) {   // «голос пользователя»: линейный PCM 16 кГц
  const r = await fetch(`https://api.deepgram.com/v1/speak?model=aura-2-thalia-en&encoding=linear16&sample_rate=16000&container=none`, { method: 'POST', headers: { Authorization: `Token ${config.deepgram.apiKey}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
  if (!r.ok) throw new Error('tts ' + r.status + ' ' + (await r.text()).slice(0, 200));
  return Buffer.from(await r.arrayBuffer());
}
const base = { dataDir: process.env.DATA_DIR };
const srv = spawn('node', ['--env-file=' + process.env.ENVFILE, 'src/index.js'], { cwd: new URL('..', import.meta.url).pathname, env: { ...process.env, PORT: String(PORT) }, stdio: ['ignore', 'pipe', 'pipe'] });
srv.stdout.on('data', (d) => process.env.V && process.stdout.write('[srv] ' + d)); srv.stderr.on('data', (d) => process.stdout.write('[srv-err] ' + d));
await new Promise((r) => setTimeout(r, 1500));
const h = await (await fetch(`http://127.0.0.1:${PORT}/health`)).json();
console.log('health features include voice-agent:', h.features.includes('voice-agent'));

function session(label, script) {
  return new Promise((resolve) => {
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/api/voice-agent?token=${token}&lang=${script.lang || 'ru'}`);
    const ev = []; let audio = 0, firstAudio = 0, t0 = Date.now(), tSend = 0; const res = { label, user: '', agent: '', tools: [], errors: [], ready: 0, firstAudioMs: 0, audioBytes: 0 };
    ws.on('message', async (d, bin) => {
      if (bin) { if (!firstAudio && tSend) { firstAudio = Date.now(); res.firstAudioMs = firstAudio - tSend; } audio += d.length; res.audioBytes = audio; return; }
      const j = JSON.parse(d.toString()); ev.push(j.t);
      if (j.t === 'ready') { res.ready = Date.now() - t0; tSend = Date.now(); await script.start(ws); }
      else if (j.t === 'user') res.user += j.text + ' ';
      else if (j.t === 'agent') { res.agent += j.text + ' '; }
      else if (j.t === 'tool') res.tools.push(j.name);
      else if (j.t === 'error') res.errors.push(j.message);
      else if (j.t === 'phone') ws.send(JSON.stringify({ t: 'phone_result', id: j.id, text: 'готово: будильник на 7:00 установлен' }));
      else if (j.t === 'state' && j.state === 'listening' && res.agent && (script.until ? script.until(res) : true)) { setTimeout(() => { ws.close(); }, 300); }
    });
    ws.on('close', () => resolve(res));
    setTimeout(() => ws.close(), script.timeout || 40000);
  });
}
const feed = async (ws, pcm) => { for (let i = 0; i < pcm.length; i += 3200) { ws.send(pcm.subarray(i, i + 3200)); await new Promise((r) => setTimeout(r, 100)); } const sil = Buffer.alloc(3200); for (let i = 0; i < 20; i++) { ws.send(sil); await new Promise((r) => setTimeout(r, 100)); } };

const out = [];
out.push(await session('text-math', { start: (ws) => ws.send(JSON.stringify({ t: 'text', text: 'Сколько будет семнадцать умножить на три?' })) }));
out.push(await session('text-tool-weather', { timeout: 60000, start: (ws) => ws.send(JSON.stringify({ t: 'text', text: 'Какая сейчас погода в Берлине?' })) }));
out.push(await session('text-phone', { timeout: 40000, start: (ws) => ws.send(JSON.stringify({ t: 'text', text: 'Поставь будильник на семь утра' })) }));
out.push(await session('text-run_task', { timeout: 120000, start: (ws) => ws.send(JSON.stringify({ t: 'text', text: 'Найди в интернете, кто сейчас президент Франции, подробно проверь по источникам и скажи' })) }));
const pcm = await tts16k('What is the capital of France? Answer in one short sentence.');
out.push(await session('real-audio-en', { lang: 'en', timeout: 40000, start: (ws) => feed(ws, pcm) }));
for (const r of out) console.log(JSON.stringify(r));
const bad = out.filter((r) => r.errors.length || !r.agent || !r.audioBytes);
console.log(bad.length ? `ПРОВАЛ: ${bad.map((b) => b.label)}` : 'ВСЕ СЕССИИ ОК');
srv.kill(); process.exit(bad.length ? 1 : 0);
