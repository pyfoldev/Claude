import fs from 'node:fs';
import { execFile } from 'node:child_process';
import path from 'node:path';
import crypto from 'node:crypto';
import { Router } from 'express';
import { deepgramTranscribe } from './sttStream.js';
import multer from 'multer';
import { config } from './config.js';
import { db, now } from './db.js';
import { requireAuth } from './auth.js';
import { runs, startRun, publicMessage, phoneResult } from './agent.js';
import { workspaceOf } from './workspace.js';
import mime from './mime.js';
import { listMemories, forgetMemory, saveMemory } from './memory.js';
import { providersFor, addProvider, removeProvider, refreshModels, PRESETS } from './providers.js';
import { listSchedules, deleteSchedule, runScheduleNow } from './scheduler.js';
import { listCheckpoints, checkpointFiles, restore as restoreCp, snapshot } from './checkpoints.js';
import { cwdFor } from './agent.js';
import { ensureSkills } from './agent.js';
import { searchRepos, installFromGithub } from './skills.js';
import { resolvePath } from './workspace.js';
import { spawn } from 'node:child_process';
import { listSites, deleteSite } from './sites.js';

export const api = Router();
api.use(requireAuth);

const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 500 * 1024 * 1024 } });
const diskUpload = multer({ dest: path.resolve(config.dataDir, 'tmp'), limits: { fileSize: 2 * 1024 * 1024 * 1024 } });

api.get('/me', (req, res) => {
  const u = req.user;
  res.json({ id: u.id, email: u.email, name: u.name, role: u.role, github: u.github_login || null });
});

// ---------- чаты ----------
const ownConv = (req) => db.prepare('SELECT * FROM conversations WHERE id=? AND user_id=?').get(+req.params.id, req.user.id);

api.get('/conversations', (req, res) => {
  const rows = db.prepare('SELECT id,title,mode,pinned,persona,project_id,updated_at FROM conversations WHERE user_id=? ORDER BY pinned DESC, updated_at DESC LIMIT 300').all(req.user.id);
  res.json(rows.map((r) => ({ id: r.id, title: r.title, mode: r.mode, pinned: !!r.pinned, persona: r.persona || '', projectId: r.project_id || null, updatedAt: r.updated_at, running: runs.has(r.id) })));
});
api.post('/conversations', (req, res) => {
  const t = now();
  const mode = req.body?.mode === 'code' ? 'code' : 'chat';
  const id = db.prepare('INSERT INTO conversations(user_id,mode,created_at,updated_at) VALUES (?,?,?,?)').run(req.user.id, mode, t, t).lastInsertRowid;
  res.json({ id: Number(id), title: 'Новый чат', mode, updatedAt: t, running: false });
});
api.patch('/conversations/:id', (req, res) => {
  if (!ownConv(req)) return res.sendStatus(404);
  if (typeof req.body.title === 'string') db.prepare('UPDATE conversations SET title=? WHERE id=?').run(req.body.title.slice(0, 80), +req.params.id);
  if ('projectId' in req.body) { const pid = req.body.projectId ? +req.body.projectId : null; if (pid && !db.prepare('SELECT 1 FROM projects WHERE id=? AND user_id=?').get(pid, req.user.id)) return res.status(404).json({ error: 'Проект не найден' }); db.prepare('UPDATE conversations SET project_id=? WHERE id=?').run(pid, +req.params.id); }
  if (typeof req.body.persona === 'string') db.prepare('UPDATE conversations SET persona=? WHERE id=?').run(req.body.persona.slice(0, 20), +req.params.id);
  if (typeof req.body.pinned === 'boolean') db.prepare('UPDATE conversations SET pinned=? WHERE id=?').run(req.body.pinned ? 1 : 0, +req.params.id);
  res.json({ ok: true });
});
api.delete('/conversations/:id', (req, res) => {
  if (!ownConv(req)) return res.sendStatus(404);
  runs.get(+req.params.id)?.ac.abort();
  db.prepare('DELETE FROM conversations WHERE id=?').run(+req.params.id);
  res.json({ ok: true });
});
api.get('/conversations/search', (req, res) => {
  const q = String(req.query.q || '').trim().slice(0, 80);
  if (q.length < 2) return res.json([]);
  const like = `%${q.replace(/[%_\\]/g, (c) => '\\' + c)}%`;
  const rows = db.prepare(`SELECT c.id, c.title, c.mode, m.content FROM messages m JOIN conversations c ON c.id=m.conv_id
    WHERE c.user_id=? AND m.role IN ('user','assistant') AND m.content LIKE ? ESCAPE '\\' GROUP BY c.id ORDER BY MAX(m.id) DESC LIMIT 30`).all(req.user.id, like);
  res.json(rows.map((r) => { const i = r.content.toLowerCase().indexOf(q.toLowerCase()); return { id: r.id, title: r.title, mode: r.mode, snippet: r.content.slice(Math.max(0, i - 40), i + 90).replace(/\s+/g, ' ') }; }));
});
api.get('/conversations/:id/messages', (req, res) => {
  const conv = ownConv(req); if (!conv) return res.sendStatus(404);
  const after = +req.query.after || 0;
  // для быстрой загрузки: последние 120 сообщений, тяжёлый вывод инструментов режем (полный — только на сервере)
  const before = +req.query.before || 0, PAGE = 120;
  const rows = after
    ? db.prepare('SELECT * FROM messages WHERE conv_id=? AND id>? ORDER BY id').all(conv.id, after)
    : before
      ? db.prepare('SELECT * FROM (SELECT * FROM messages WHERE conv_id=? AND id<? ORDER BY id DESC LIMIT ?) ORDER BY id').all(conv.id, before, PAGE)
      : db.prepare('SELECT * FROM (SELECT * FROM messages WHERE conv_id=? ORDER BY id DESC LIMIT ?) ORDER BY id').all(conv.id, PAGE);
  // есть ли ещё более старые сообщения (приложение подгружает их при прокрутке вверх)
  const hasMore = !after && rows.length > 0 && !!db.prepare('SELECT 1 FROM messages WHERE conv_id=? AND id<? LIMIT 1').get(conv.id, rows[0].id);
  const run = runs.get(conv.id);
  res.json({ messages: rows.map((r) => publicMessage(r.role === 'tool' && r.content.length > 5000 ? { ...r, content: r.content.slice(0, 5000) + '\n[… вывод сокращён]' } : r)), running: !!run, partial: run?.partial || '', mode: conv.mode, persona: conv.persona || '', incremental: !!after, hasMore });
});
api.get('/conversations/:id/export', (req, res) => {
  const conv = ownConv(req); if (!conv) return res.sendStatus(404);
  const rows = db.prepare("SELECT role, content, tool_calls FROM messages WHERE conv_id=? AND role IN ('user','assistant') ORDER BY id").all(conv.id);
  let md = `# ${conv.title}\n\n_OpenAgent · ${new Date(conv.created_at).toISOString().slice(0, 10)} · режим ${conv.mode}_\n\n`;
  for (const r of rows) {
    if (r.role === 'user') md += `## Вы\n\n${r.content}\n\n`;
    else if (r.content || r.tool_calls) md += `## Агент\n\n${r.content || ''}${r.tool_calls ? `\n\n_инструменты: ${JSON.parse(r.tool_calls).map((c) => c.function.name).join(', ')}_` : ''}\n\n`;
  }
  res.json({ name: `${conv.title.replace(/[^\p{L}\p{N} _-]+/gu, '').slice(0, 40).trim() || 'chat'}.md`, markdown: md });
});

function rerun(req, res, fromRow) {
  const conv = ownConv(req);
  if (runs.has(conv.id)) return res.status(409).json({ error: 'Агент ещё работает' });
  const atts = fromRow.attachments ? JSON.parse(fromRow.attachments) : null;
  const text = req.body.text !== undefined ? String(req.body.text).slice(0, 100000) : fromRow.content;
  db.prepare('DELETE FROM messages WHERE conv_id=? AND id>=?').run(conv.id, fromRow.id);
  if (conv.summarized_upto >= fromRow.id) db.prepare("UPDATE conversations SET summary='', summarized_upto=0 WHERE id=?").run(conv.id);
  try { startRun(req.user, db.prepare('SELECT * FROM conversations WHERE id=?').get(conv.id), text, atts, { model: req.body.model, provider: req.body.provider, effort: req.body.effort, autonomy: req.body.autonomy, search: req.body.search }); res.json({ ok: true }); }
  catch (e) { res.status(409).json({ error: e.message }); }
}
api.post('/conversations/:id/regenerate', (req, res) => {
  if (!ownConv(req)) return res.sendStatus(404);
  const last = db.prepare("SELECT * FROM messages WHERE conv_id=? AND role='user' ORDER BY id DESC LIMIT 1").get(+req.params.id);
  if (!last) return res.status(400).json({ error: 'Нет сообщений' });
  rerun(req, res, last);
});
api.post('/conversations/:id/edit', (req, res) => {
  if (!ownConv(req)) return res.sendStatus(404);
  const row = db.prepare("SELECT * FROM messages WHERE id=? AND conv_id=? AND role='user'").get(+req.body.messageId, +req.params.id);
  if (!row) return res.status(404).json({ error: 'Сообщение не найдено' });
  rerun(req, res, row);
});

api.post('/conversations/:id/send', (req, res) => {
  const conv = ownConv(req);
  if (!conv) return res.sendStatus(404);
  const text = String(req.body.text || '').slice(0, 100000);
  const ids = Array.isArray(req.body.files) ? req.body.files.slice(0, 20) : [];
  const atts = ids.map((id) => db.prepare('SELECT * FROM files WHERE id=? AND user_id=?').get(String(id), req.user.id))
    .filter(Boolean).map((f) => ({ id: f.id, name: f.name, mime: f.mime, size: f.size, path: f.path }));
  if (!text.trim() && !atts.length) return res.status(400).json({ error: 'Пустое сообщение' });
  // защита от двойной отправки (повтор запроса сетью/двойной тап): то же сообщение в последние 6 с без ответа — не дублируем
  const lastRow = db.prepare('SELECT role, content, created_at FROM messages WHERE conv_id=? ORDER BY id DESC LIMIT 1').get(conv.id);
  if (lastRow && lastRow.role === 'user' && lastRow.content === text && Date.now() - lastRow.created_at < 6000 && !atts.length) return res.json({ ok: true, duplicate: true });
  try { startRun(req.user, conv, text, atts.length ? atts : null, { voice: !!req.body.voice, model: req.body.model, provider: req.body.provider, effort: req.body.effort, autonomy: req.body.autonomy, search: req.body.search }); res.json({ ok: true }); }
  catch (e) { res.status(409).json({ error: e.message }); }
});

api.post('/conversations/:id/stop', (req, res) => {
  if (!ownConv(req)) return res.sendStatus(404);
  runs.get(+req.params.id)?.ac.abort();
  res.json({ ok: true });
});

api.get('/conversations/:id/stream', async (req, res) => {
  if (!ownConv(req)) return res.sendStatus(404);
  let run = runs.get(+req.params.id);
  // wait=1: приложение открывает поток одновременно с отправкой сообщения — ждём, пока запуск появится (до 2,5 с)
  if (!run && req.query.wait) for (let i = 0; i < 50 && !run; i++) { await new Promise((r) => setTimeout(r, 50)); run = runs.get(+req.params.id); }
  res.set({ 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive', 'X-Accel-Buffering': 'no' });
  res.flushHeaders();
  const send = (e) => res.write(`data: ${JSON.stringify(e)}\n\n`);
  if (!run) { send({ type: 'done' }); return res.end(); }
  send({ type: 'snapshot', partial: run.partial });
  if (run.userMsg) send({ type: 'message', message: run.userMsg });      // поток открыт чуть позже старта — не теряем событие с сообщением пользователя
  const onEv = (e) => { send(e); if (e.type === 'done' || e.type === 'error') res.end(); };
  run.emitter.on('event', onEv);
  const ping = setInterval(() => res.write(': ping\n\n'), 15000);
  req.on('close', () => { clearInterval(ping); run.emitter.off('event', onEv); });
});

// ---------- файлы ----------
api.post('/files', diskUpload.array('file', 20), (req, res) => {
  const ws = workspaceOf(req.user.id);
  const out = [];
  for (const f of req.files || []) {
    const id = crypto.randomBytes(12).toString('hex');
    const name = path.basename(Buffer.from(f.originalname, 'latin1').toString('utf8')).replace(/[^\p{L}\p{N}._ ()-]/gu, '_') || 'file';
    const dest = path.join(ws, 'uploads', `${id.slice(0, 6)}_${name}`);
    fs.renameSync(f.path, dest);
    const m = f.mimetype && f.mimetype !== 'application/octet-stream' ? f.mimetype : mime(name);
    db.prepare('INSERT INTO files(id,user_id,name,mime,size,path,created_at) VALUES (?,?,?,?,?,?,?)').run(id, req.user.id, name, m, f.size, dest, now());
    out.push({ id, name, mime: m, size: f.size });
  }
  res.json(out);
});
const thumbJobs = new Map();
/** Миниатюра картинки (кэшируется рядом с файлом): в чате не тянем оригиналы по несколько МБ. */
function thumbOf(f, w) {
  const out = `${f.path}.w${w}.jpg`;
  if (fs.existsSync(out)) return Promise.resolve(out);
  if (thumbJobs.has(out)) return thumbJobs.get(out);
  const py = 'import sys\nfrom PIL import Image, ImageOps\nim=Image.open(sys.argv[1]); im=ImageOps.exif_transpose(im); im.thumbnail((int(sys.argv[3]),int(sys.argv[3]))); im.convert("RGB").save(sys.argv[2],"JPEG",quality=82,optimize=True)';
  const p = new Promise((resolve) => {
    execFile('python3', ['-c', py, f.path, out, String(w)], { timeout: 20000 }, (err) => { thumbJobs.delete(out); resolve(!err && fs.existsSync(out) ? out : null); });
  });
  thumbJobs.set(out, p); return p;
}
api.get('/files/:id', async (req, res) => {
  const f = db.prepare('SELECT * FROM files WHERE id=? AND user_id=?').get(req.params.id, req.user.id);
  if (!f || !fs.existsSync(f.path)) return res.sendStatus(404);
  res.set('Cache-Control', 'private, max-age=31536000, immutable');   // id уникален → клиент не перекачивает
  const w = Math.min(Math.max(parseInt(req.query.w) || 0, 0), 1600);
  if (w && /^image\/(png|jpe?g|webp|bmp)/.test(f.mime) && f.size > 60000) {
    const t = await thumbOf(f, w);
    if (t) { res.set('Content-Type', 'image/jpeg'); return res.sendFile(t); }
  }
  res.set('Content-Type', f.mime);
  res.download(f.path, f.name);
});

// ---------- голос ----------
import { runDiag } from './diag.js';
api.get('/diag', async (req, res) => { try { res.json(await runDiag(req.user)); } catch (e) { res.status(500).json({ error: e.message }); } });
api.post('/phone/result', (req, res) => res.json({ ok: phoneResult(req.user.id, String(req.body.id || ''), req.body.text) }));

api.post('/stt', upload.single('audio'), async (req, res) => {
  if (!config.deepgram.apiKey) return res.status(503).json({ error: 'DEEPGRAM_API_KEY не задан' });
  if (!req.file) return res.status(400).json({ error: 'нет аудио' });
  try { res.json({ text: await deepgramTranscribe(req.file.buffer, req.file.originalname, req.file.mimetype, req.body.language) }); }
  catch (e) { res.status(502).json({ error: e.message }); }
});

const DEFAULT_VOICE = '2a1036d645634680b3cc69aeeb60375b'; // «Спокойный женский голос»
const speakable = (t) => t
  .replace(/```[\s\S]*?```/g, ' ')
  .replace(/`([^`]+)`/g, '$1')
  .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
  .replace(/https?:\/\/\S+/g, '')
  .replace(/[*_#>~|\\]+/g, '')
  .replace(/^\s*(?:[-•*·▪●○◦►▶]|\d+[.)])\s+/gm, '')
  .replace(/[•·▪●○◦►▶■□→←↑↓✓✔✗✘★☆]/g, ' ')
  .replace(/[«»"“”„]/g, '')
  .replace(/\s*[—–]\s*/g, ', ')          // тире → запятая: без длинных пауз и «сбоев» тембра
  .replace(/[:;]\s+/g, ', ')
  .replace(/[()\[\]{}]/g, ', ')
  .replace(/\.{2,}|…/g, '.')
  .replace(/([!?.,])\s*(?:[!?.,]\s*)+/g, '$1 ')
  .replace(/\s*,\s*,/g, ',')
  .replace(/\s+/g, ' ').replace(/^[\s.,!?:;-]+/, '').trim();

const voiceOf = (u) => u.voice_id || config.fish.referenceId || DEFAULT_VOICE;

const FISH = () => process.env.FISH_BASE || 'https://api.fish.audio';
/** Потоковая озвучка (GET): отдаёт аудио по мере синтеза, плеер начинает играть с первых байтов. */
let dgTtsBadUntil = 0;   // Deepgram TTS не отвечает (нет доступа/лимит) — на 5 минут уходим на Fish, чтобы не терять время на каждой фразе
const DG_TTS = () => config.ttsProvider === 'deepgram' && !!config.deepgram.apiKey && Date.now() > dgTtsBadUntil;
const dgFail = (status) => { if (config.fish.apiKey && [400, 401, 402, 403, 404, 429, 500, 502, 503].includes(status)) { dgTtsBadUntil = Date.now() + 5 * 60 * 1000; return true; } return false; };
/** Deepgram Aura-2: потоковый синтез. pcm → 24 кГц/16 бит/моно, иначе mp3. */
function dgSpeak(text, pcm, voice, signal) {
  const model = /^(aura-|flux-)/.test(String(voice || '')) ? voice : config.deepgram.ttsVoice;
  const q = new URLSearchParams({ model, ...(pcm ? { encoding: 'linear16', sample_rate: '24000', container: 'none' } : { encoding: 'mp3', bit_rate: '48000' }) });
  if (/^flux-/.test(model)) q.set('expressivity', String(config.deepgram.ttsExpressivity));
  const ver = /^flux-/.test(model) ? 'v2' : 'v1';     // Flux TTS (напр. flux-vladimir-ru) живёт на /v2/speak
  return fetch(`https://api.deepgram.com/${ver}/speak?${q}`, { method: 'POST', headers: { Authorization: `Token ${config.deepgram.apiKey}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ text }), signal });
}
api.get('/tts-stream', async (req, res) => {
  if (DG_TTS() && await dgTtsStream(req, res)) return;
  if (!config.fish.apiKey) return res.status(503).json({ error: 'FISH_API_KEY не задан' });
  const text = speakable(String(req.query.text || '')).slice(0, 1200);
  if (!text || !/[\p{L}\p{N}]/u.test(text)) return res.status(204).end();
  const ac = new AbortController(); res.on('close', () => ac.abort());
  try {
    const pcm = req.query.fmt === 'pcm';      // сырой звук 24 кГц/16 бит/моно: приложение играет его сразу, без буферизации плеера
    const body = { text, reference_id: String(req.query.voice || voiceOf(req.user)), ...(pcm ? { format: 'pcm', sample_rate: 24000 } : { format: 'mp3', mp3_bitrate: 64 }), normalize: false, latency: 'low', chunk_length: 100 };
    const r = await fetch(`${FISH()}/v1/tts`, { method: 'POST', headers: { Authorization: `Bearer ${config.fish.apiKey}`, 'Content-Type': 'application/json', model: config.fish.model }, body: JSON.stringify(body), signal: ac.signal });
    if (!r.ok) return res.status(502).json({ error: `Fish Audio ${r.status}: ${(await r.text()).slice(0, 200)}` });
    res.set({ 'Content-Type': pcm ? 'audio/pcm' : 'audio/mpeg', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no' });
    res.flushHeaders?.();
    const { Readable } = await import('node:stream');
    Readable.fromWeb(r.body).on('error', () => res.end()).pipe(res);
  } catch (e) { if (!res.headersSent) res.status(502).json({ error: e.message }); else res.end(); }
});

async function dgTtsStream(req, res) {
  const text = speakable(String(req.query.text || '')).slice(0, 1900);
  if (!text || !/[\p{L}\p{N}]/u.test(text)) { res.status(204).end(); return true; }
  const ac = new AbortController(); res.on('close', () => ac.abort());
  try {
    const pcm = req.query.fmt === 'pcm';
    const r = await dgSpeak(text, pcm, req.query.voice, ac.signal);
    if (!r.ok) { if (dgFail(r.status)) return false; res.status(502).json({ error: `Deepgram TTS ${r.status}: ${(await r.text()).slice(0, 200)}` }); return true; }
    res.set({ 'Content-Type': pcm ? 'audio/pcm' : 'audio/mpeg', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no' });
    res.flushHeaders?.();
    const { Readable } = await import('node:stream');
    Readable.fromWeb(r.body).on('error', () => res.end()).pipe(res);
    return true;
  } catch (e) { if (!res.headersSent) { if (config.fish.apiKey) { dgTtsBadUntil = Date.now() + 60 * 1000; return false; } res.status(502).json({ error: e.message }); } else res.end(); return true; }
}

api.post('/tts', async (req, res) => {
  const dg = DG_TTS();
  if (!dg && !config.fish.apiKey) return res.status(503).json({ error: 'Нет ключа озвучки (DEEPGRAM_API_KEY / FISH_API_KEY)' });
  const text = speakable(String(req.body.text || '')).slice(0, dg ? 1900 : 4000);
  if (!text || !/[\p{L}\p{N}]/u.test(text)) return res.status(204).end(); // нечего озвучивать (только знаки) — не мешаем очереди
  if (dg) {
    try {
      const r = await dgSpeak(text, false, req.body.voice);
      if (r.ok) { res.set('Content-Type', 'audio/mpeg'); return res.send(Buffer.from(await r.arrayBuffer())); }
      if (!dgFail(r.status)) return res.status(502).json({ error: `Deepgram TTS ${r.status}: ${(await r.text()).slice(0, 200)}` });
    } catch (e) { if (!config.fish.apiKey) return res.status(502).json({ error: e.message }); dgTtsBadUntil = Date.now() + 60 * 1000; }
  }                                                       // сюда попадаем, если Deepgram недоступен — озвучивает Fish
  try {
    // ВСЕГДА фиксированный reference_id — иначе модель выбирает случайный тембр на каждый запрос
    const body = { text, reference_id: String(req.body.voice || voiceOf(req.user)), format: 'mp3', mp3_bitrate: 64, normalize: false, latency: 'balanced', chunk_length: 200 };
    const r = await fetch(`${FISH()}/v1/tts`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${config.fish.apiKey}`, 'Content-Type': 'application/json', model: config.fish.model },
      body: JSON.stringify(body),
    });
    if (!r.ok) return res.status(502).json({ error: `Fish Audio ${r.status}: ${(await r.text()).slice(0, 200)}` });
    res.set('Content-Type', 'audio/mpeg');
    res.send(Buffer.from(await r.arrayBuffer()));
  } catch (e) { res.status(502).json({ error: e.message }); }
});

api.get('/voice', (req, res) => res.json({ id: voiceOf(req.user), name: req.user.voice_name || (voiceOf(req.user) === DEFAULT_VOICE ? 'Спокойный женский голос' : 'Свой голос') }));
api.post('/voice', (req, res) => {
  const id = String(req.body.id || '').trim();
  if (!/^[0-9a-f]{32}$/.test(id)) return res.status(400).json({ error: 'Некорректный id голоса' });
  db.prepare('UPDATE users SET voice_id=?, voice_name=? WHERE id=?').run(id, String(req.body.name || '').slice(0, 80), req.user.id);
  res.json({ ok: true });
});
api.get('/voices', async (req, res) => {
  if (!config.fish.apiKey) return res.status(503).json({ error: 'FISH_API_KEY не задан' });
  try {
    const q = new URLSearchParams({ page_size: '20', page_number: String(+req.query.page || 1), sort_by: req.query.sort === 'score' ? 'score' : 'task_count' });
    if (req.query.lang !== 'any') q.set('language', String(req.query.lang || 'ru'));
    if (req.query.q) q.set('title', String(req.query.q).slice(0, 60));
    if (req.query.self === '1') q.set('self', 'true');
    const r = await fetch(`https://api.fish.audio/model?${q}`, { headers: { Authorization: `Bearer ${config.fish.apiKey}` } });
    const j = await r.json();
    res.json((j.items || []).map((m) => ({ id: m._id, title: m.title, description: (m.description || '').replace(/\s+/g, ' ').slice(0, 140), languages: m.languages || [], sample: m.samples?.[0]?.audio || null, uses: m.task_count || 0 })));
  } catch (e) { res.status(502).json({ error: e.message }); }
});

// ---------- GitHub ----------
async function ghLogin(token) {
  const r = await fetch('https://api.github.com/user', { headers: { Authorization: `Bearer ${token}`, 'User-Agent': 'OpenAgent' } });
  return r.ok ? (await r.json()).login : null;
}
const saveGh = (uid, token, login) => db.prepare('UPDATE users SET github_token=?, github_login=? WHERE id=?').run(token, login, uid);

api.post('/github/device/start', async (req, res) => {
  if (!config.githubClientId) return res.status(503).json({ error: 'GITHUB_CLIENT_ID не задан — используй токен (PAT)' });
  const r = await fetch('https://github.com/login/device/code', {
    method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ client_id: config.githubClientId, scope: 'repo workflow read:org gist' }),
  });
  res.json(await r.json());
});
api.post('/github/device/poll', async (req, res) => {
  const r = await fetch('https://github.com/login/oauth/access_token', {
    method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify({ client_id: config.githubClientId, device_code: req.body.deviceCode, grant_type: 'urn:ietf:params:oauth:grant-type:device_code' }),
  });
  const j = await r.json();
  if (j.access_token) {
    const login = await ghLogin(j.access_token);
    saveGh(req.user.id, j.access_token, login);
    return res.json({ status: 'ok', login });
  }
  res.json({ status: j.error === 'authorization_pending' || j.error === 'slow_down' ? 'pending' : 'error', error: j.error });
});
api.post('/github/token', async (req, res) => {
  const token = String(req.body.token || '').trim();
  const login = await ghLogin(token);
  if (!login) return res.status(400).json({ error: 'Токен недействителен' });
  saveGh(req.user.id, token, login);
  res.json({ login });
});
api.delete('/github', (req, res) => { saveGh(req.user.id, null, null); res.json({ ok: true }); });

// ---------- память ----------
api.get('/memories', (req, res) => res.json(listMemories(req.user.id)));
api.post('/memories', async (req, res) => {
  const id = await saveMemory(req.user.id, { content: req.body.content, kind: req.body.kind || 'fact', importance: req.body.importance ?? 0.7 });
  res.json({ id });
});
api.delete('/memories', (req, res) => { for (const m of listMemories(req.user.id)) forgetMemory(req.user.id, m.id); res.json({ ok: true }); });
api.delete('/memories/:id', (req, res) => res.json({ ok: forgetMemory(req.user.id, +req.params.id) }));

// ---------- провайдеры и модели ----------
api.get('/providers', async (req, res) => res.json(await providersFor(req.user)));
api.get('/provider-presets', (_req, res) => res.json(PRESETS));
api.post('/providers', async (req, res) => {
  try { res.json(await addProvider(req.user, req.body)); } catch (e) { res.status(400).json({ error: e.message }); }
});
api.delete('/providers/:id', (req, res) => res.json({ ok: removeProvider(req.user, req.params.id) }));
api.post('/providers/:id/refresh', (req, res) => { refreshModels(req.params.id); res.json({ ok: true }); });

// ---------- автоматизации ----------
api.get('/schedules', (req, res) => res.json(listSchedules(req.user.id).map((s) => ({ id: s.id, name: s.name, prompt: s.prompt, mode: s.mode, everyMin: s.every_min, nextRun: s.next_run, enabled: !!s.enabled, lastRun: s.last_run, runs: s.runs, watchUrl: s.watch_url || null, hookUrl: s.hook_token ? `${config.publicUrl}/hooks/${s.hook_token}` : null }))));
api.post('/schedules', (req, res) => {
  const b = req.body; const t = now();
  let every = b.everyMin ? Math.max(5, +b.everyMin) : null;
  let firstRun = every ? t + every * 60e3 : null;
  if (/^\d{1,2}:\d{2}$/.test(b.atTime || '')) {       // «каждый день в HH:MM» по часовому поясу телефона (tzOffsetMin — минуты к UTC)
    const [h, m] = b.atTime.split(':').map(Number), off = +b.tzOffsetMin || 0;
    const loc = new Date(t + off * 60e3);
    let target = Date.UTC(loc.getUTCFullYear(), loc.getUTCMonth(), loc.getUTCDate(), h, m) - off * 60e3;
    if (target <= t) target += 86400e3;
    every = 1440; firstRun = target;
  }
  const watch = /^https?:\/\//.test(b.watchUrl || '') ? String(b.watchUrl).slice(0, 500) : null;
  if (!b.name || !b.prompt || (!every && !b.webhook)) return res.status(400).json({ error: 'Нужны название, задача и период (мин. 5 мин) или вебхук' });
  const token = b.webhook ? crypto.randomBytes(18).toString('hex') : null;
  const id = db.prepare('INSERT INTO schedules(user_id,name,prompt,mode,every_min,next_run,created_at,hook_token,watch_url,watch_text) VALUES (?,?,?,?,?,?,?,?,?,?)').run(req.user.id, String(b.name).slice(0, 60), String(b.prompt).slice(0, 8000), b.mode === 'chat' ? 'chat' : 'code', every, firstRun, t, token, watch, watch ? String(b.watchText || '').slice(0, 200) || null : null).lastInsertRowid;
  res.json({ id: Number(id), hookUrl: token ? `${config.publicUrl}/hooks/${token}` : null });
});
api.patch('/schedules/:id', (req, res) => {
  const s = db.prepare('SELECT * FROM schedules WHERE id=? AND user_id=?').get(+req.params.id, req.user.id);
  if (!s) return res.sendStatus(404);
  if (typeof req.body.enabled === 'boolean') db.prepare('UPDATE schedules SET enabled=?, next_run=? WHERE id=?').run(req.body.enabled ? 1 : 0, req.body.enabled && s.every_min ? now() + s.every_min * 60e3 : s.next_run, s.id);
  res.json({ ok: true });
});
api.post('/schedules/:id/run', (req, res) => {
  const s = db.prepare('SELECT * FROM schedules WHERE id=? AND user_id=?').get(+req.params.id, req.user.id);
  if (!s) return res.sendStatus(404);
  runScheduleNow(s); res.json({ ok: true });
});
api.delete('/schedules/:id', (req, res) => res.json({ ok: deleteSchedule(req.user.id, +req.params.id) }));

// ---------- агенты и коннекторы ----------
import { listAgents, saveAgent, deleteAgent, getAgent, publicAgent, runAgentNow, TEMPLATES, ensureMain } from './agents.js';
import { catalog as connCatalog, saveCreds, removeCreds, testConnector } from './integrations.js';
api.get('/agents', (req, res) => res.json({ agents: listAgents(req.user.id).map(publicAgent), templates: TEMPLATES, connectors: connCatalog(req.user.id).map((c) => ({ id: c.id, name: c.name, icon: c.icon, connected: c.connected })) }));
api.post('/agents', (req, res) => { try { res.json(publicAgent(saveAgent(req.user.id, req.body || {}))); } catch (e) { res.status(400).json({ error: e.message }); } });
api.patch('/agents/:id', (req, res) => { try { res.json(publicAgent(saveAgent(req.user.id, req.body || {}, +req.params.id))); } catch (e) { res.status(e.message === 'Агент не найден' ? 404 : 400).json({ error: e.message }); } });
api.delete('/agents/:id', (req, res) => res.json({ ok: deleteAgent(req.user.id, +req.params.id) }));
api.post('/agents/:id/run', (req, res) => {
  const a = getAgent(req.user.id, +req.params.id); if (!a) return res.sendStatus(404);
  const id = runAgentNow(a, String(req.body?.prompt || '').slice(0, 4000)); res.json({ ok: !!id, convId: id });
});
api.post('/agents/:id/chat', (req, res) => {          // обычный чат с агентом: его задача и коннекторы, подтверждения как всегда
  const a = getAgent(req.user.id, +req.params.id); if (!a) return res.sendStatus(404);
  const t = now();
  const id = db.prepare('INSERT INTO conversations(user_id,title,mode,created_at,updated_at,agent_id) VALUES (?,?,?,?,?,?)').run(req.user.id, `${a.emoji} ${a.name}`, 'chat', t, t, a.id).lastInsertRowid;
  res.json({ id: Number(id), title: `${a.emoji} ${a.name}`, mode: 'chat', updatedAt: t, running: false });
});
api.get('/integrations', (req, res) => res.json(connCatalog(req.user.id)));
api.put('/integrations/:id', (req, res) => { try { saveCreds(req.user.id, req.params.id, req.body?.fields || {}); res.json({ ok: true }); } catch (e) { res.status(400).json({ error: e.message }); } });
api.delete('/integrations/:id', (req, res) => { removeCreds(req.user.id, req.params.id); res.json({ ok: true }); });
api.post('/integrations/:id/test', async (req, res) => res.json({ result: await testConnector(req.user.id, req.params.id) }));

// ---------- навыки ----------
api.get('/skills', (req, res) => { ensureSkills(req.user.id); res.json(db.prepare('SELECT id,name,description,content,source FROM skills WHERE user_id=? ORDER BY name').all(req.user.id)); });
api.post('/skills', (req, res) => {
  const { name, description = '', content } = req.body;
  if (!name || !content) return res.status(400).json({ error: 'Нужны название и текст' });
  db.prepare('INSERT INTO skills(user_id,name,description,content) VALUES (?,?,?,?) ON CONFLICT(user_id,name) DO UPDATE SET description=excluded.description, content=excluded.content')
    .run(req.user.id, String(name).slice(0, 60), String(description).slice(0, 200), String(content).slice(0, 20000));
  res.json({ ok: true });
});
const ghToken = (uid) => db.prepare('SELECT github_token FROM users WHERE id=?').get(uid)?.github_token;
api.get('/skills/search', async (req, res) => {
  try { res.json(await searchRepos(req.query.q, ghToken(req.user.id))); } catch (e) { res.status(502).json({ error: e.message }); }
});
api.post('/skills/install', async (req, res) => {
  try { res.json(await installFromGithub(req.user, req.body.repo, ghToken(req.user.id))); } catch (e) { res.status(400).json({ error: e.message }); }
});
api.delete('/skills/:id', (req, res) => res.json({ ok: db.prepare('DELETE FROM skills WHERE id=? AND user_id=?').run(+req.params.id, req.user.id).changes > 0 }));

// ---------- файловый менеджер ----------
api.get('/fs', (req, res) => {
  try {
    const p = resolvePath(req.user, req.query.path || '.');
    const items = fs.readdirSync(p, { withFileTypes: true }).map((e) => {
      let size = 0, mtime = 0; try { const st = fs.statSync(path.join(p, e.name)); size = st.size; mtime = st.mtimeMs; } catch {}
      return { name: e.name, dir: e.isDirectory(), size, mtime };
    }).sort((a, b) => (b.dir - a.dir) || a.name.localeCompare(b.name));
    res.json({ path: p, parent: path.dirname(p), items });
  } catch (e) { res.status(400).json({ error: e.message }); }
});
api.get('/fs/file', (req, res) => {
  try {
    const p = resolvePath(req.user, req.query.path);
    const st = fs.statSync(p);
    if (req.query.download) return res.download(p);
    if (st.size > 600 * 1024) return res.status(413).json({ error: 'Файл слишком большой для просмотра — скачайте его' });
    res.json({ path: p, text: fs.readFileSync(p, 'utf8') });
  } catch (e) { res.status(400).json({ error: e.message }); }
});
api.put('/fs/file', (req, res) => {
  try { const p = resolvePath(req.user, req.body.path); fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, String(req.body.text ?? '')); res.json({ ok: true }); }
  catch (e) { res.status(400).json({ error: e.message }); }
});
api.delete('/fs', (req, res) => {
  try { const p = resolvePath(req.user, req.query.path); if (p === workspaceOf(req.user.id)) throw new Error('Нельзя удалить корень'); fs.rmSync(p, { recursive: true, force: true }); res.json({ ok: true }); }
  catch (e) { res.status(400).json({ error: e.message }); }
});

// ---------- терминал (только владелец) ----------
api.post('/exec', (req, res) => {
  if (req.user.role !== 'owner') return res.status(403).json({ error: 'Терминал доступен только владельцу' });
  const cwd = resolvePath(req.user, req.body.cwd || '.');
  const env = { ...process.env, TERM: 'dumb', GIT_TERMINAL_PROMPT: '0' };
  for (const k of ['JWT_SECRET', 'SMTP_PASS', 'RIVER_API_KEY', 'MISTRAL_API_KEY', 'DEEPGRAM_API_KEY', 'FISH_API_KEY', 'TURNSTILE_SECRET']) delete env[k];
  const gh = db.prepare('SELECT github_token FROM users WHERE id=?').get(req.user.id);
  if (gh?.github_token) { env.GITHUB_TOKEN = gh.github_token; env.GH_TOKEN = gh.github_token; }
  const script = `cd ${JSON.stringify(cwd)} 2>/dev/null\n${req.body.command}\n__rc=$?\necho\necho "__OA_CWD__$(pwd) $__rc"`;
  const p = spawn('bash', ['-lc', script], { env, detached: true });
  res.set({ 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no' });
  p.stdout.on('data', (d) => res.write(d)); p.stderr.on('data', (d) => res.write(d));
  const timer = setTimeout(() => { try { process.kill(-p.pid, 'SIGKILL'); } catch {} }, 600e3);
  p.on('close', () => { clearTimeout(timer); res.end(); });
  res.on('close', () => { try { process.kill(-p.pid, 'SIGKILL'); } catch {} });
});

// ---------- сайты ----------
api.get('/sites', (req, res) => res.json(listSites(req.user.id)));
api.delete('/sites/:slug', (req, res) => res.json({ ok: deleteSite(req.user.id, req.params.slug) }));

// ---------- расход токенов (информационно) ----------
api.get('/usage', (req, res) => {
  const day = new Date().toISOString().slice(0, 10);
  const today = db.prepare('SELECT prompt, completion, calls, cached FROM usage WHERE user_id=? AND day=?').get(req.user.id, day) || { prompt: 0, completion: 0, calls: 0, cached: 0 };
  const week = db.prepare("SELECT COALESCE(SUM(prompt),0) p, COALESCE(SUM(completion),0) c FROM usage WHERE user_id=? AND day>=date('now','-6 day')").get(req.user.id);
  res.json({ today, week: { prompt: week.p, completion: week.c } });
});

// ---------- инструкции пользователя ----------
api.get('/instructions', (req, res) => res.json({ text: req.user.instructions || '' }));
api.post('/instructions', (req, res) => { db.prepare('UPDATE users SET instructions=? WHERE id=?').run(String(req.body.text || '').slice(0, 700), req.user.id); res.json({ ok: true }); });

// ---------- запуск фрагмента кода из чата (только владелец) ----------
api.post('/run', (req, res) => {
  if (req.user.role !== 'owner') return res.status(403).json({ error: 'Запуск кода доступен только владельцу' });
  const lang = String(req.body.lang || 'python').toLowerCase();
  const cmd = { python: ['python3', '-u'], py: ['python3', '-u'], python3: ['python3', '-u'], js: ['node'], javascript: ['node'], node: ['node'], bash: ['bash'], sh: ['bash'], shell: ['bash'] }[lang];
  if (!cmd) return res.status(400).json({ error: `Язык «${lang}» не поддерживается (python, js, bash)` });
  const dir = path.join(workspaceOf(req.user.id), 'snippets'); fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, `run_${Date.now()}${cmd[0] === 'node' ? '.js' : cmd[0] === 'bash' ? '.sh' : '.py'}`);
  fs.writeFileSync(file, String(req.body.code || '').slice(0, 100000));
  const env = { ...process.env, MPLBACKEND: 'Agg', TERM: 'dumb' };
  for (const k of ['JWT_SECRET', 'SMTP_PASS', 'RIVER_API_KEY', 'MISTRAL_API_KEY', 'DEEPGRAM_API_KEY', 'FISH_API_KEY', 'TURNSTILE_SECRET', 'COARENA_API_KEY']) delete env[k];
  const p = spawn(cmd[0], [...cmd.slice(1), file], { cwd: dir, env, detached: true });
  let out = ''; const push = (d) => { out += d; if (out.length > 60000) out = out.slice(-40000); };
  p.stdout.on('data', push); p.stderr.on('data', push);
  const kill = () => { try { process.kill(-p.pid, 'SIGKILL'); } catch {} };
  const timer = setTimeout(() => { kill(); out += '\n[таймаут 30 с]'; }, 30000);
  p.on('close', (code) => { clearTimeout(timer); try { fs.unlinkSync(file); } catch {} res.json({ output: out.slice(-12000), exit: code }); });
  p.on('error', (e) => { clearTimeout(timer); res.json({ output: `Ошибка запуска: ${e.message}`, exit: -1 }); });
  res.on('close', kill);
});

// ---------- монитор сервера (только владелец) ----------
import os from 'node:os';
import { spawnSync } from 'node:child_process';
const sh = (cmd, args = []) => { const p = spawnSync(cmd, args, { encoding: 'utf8', timeout: 4000 }); return p.status === 0 ? p.stdout : ''; };
let lastCpu = null;
function cpuPercent() {
  try {
    const l = fs.readFileSync('/proc/stat', 'utf8').split('\n')[0].trim().split(/\s+/).slice(1).map(Number);
    const idle = l[3] + (l[4] || 0), total = l.reduce((a, b) => a + b, 0);
    const prev = lastCpu; lastCpu = { idle, total };
    if (!prev) return null;
    const dt = total - prev.total; return dt > 0 ? Math.round((1 - (idle - prev.idle) / dt) * 100) : null;
  } catch { return null; }
}
api.get('/system', (req, res) => {
  if (req.user.role !== 'owner') return res.status(403).json({ error: 'Только для владельца' });
  const mem = (() => { try { const m = Object.fromEntries(fs.readFileSync('/proc/meminfo', 'utf8').split('\n').filter(Boolean).map((l) => { const [k, v] = l.split(':'); return [k, parseInt(v) * 1024]; })); return { total: m.MemTotal, used: m.MemTotal - (m.MemAvailable ?? m.MemFree), swapTotal: m.SwapTotal || 0, swapUsed: (m.SwapTotal || 0) - (m.SwapFree || 0) }; } catch { return { total: os.totalmem(), used: os.totalmem() - os.freemem(), swapTotal: 0, swapUsed: 0 }; } })();
  const df = sh('df', ['-kP', '/']).split('\n')[1]?.trim().split(/\s+/) || [];
  const disk = df.length > 4 ? { total: +df[1] * 1024, used: +df[2] * 1024, percent: parseInt(df[4]) } : null;
  const procs = sh('ps', ['-eo', 'pid,comm,pcpu,pmem', '--sort=-pcpu']).split('\n').slice(1, 7).map((l) => l.trim().split(/\s+/)).filter((x) => x.length >= 4).map(([pid, name, cpu, m]) => ({ pid: +pid, name, cpu: +cpu, mem: +m }));
  const ports = sh('ss', ['-tlnH']).split('\n').map((l) => l.trim().split(/\s+/)[3]).filter(Boolean).map((a) => a.split(':').pop()).filter((p, i, arr) => /^\d+$/.test(p) && arr.indexOf(p) === i).slice(0, 12);
  const services = ['openagent', 'caddy', 'docker', 'nginx', 'ssh'].map((n) => ({ name: n, active: sh('systemctl', ['is-active', n]).trim() })).filter((s) => s.active && s.active !== 'unknown');
  res.json({ host: os.hostname(), uptime: os.uptime(), load: os.loadavg(), cores: os.cpus().length, cpu: cpuPercent(), mem, disk, procs, ports, services, node: process.version });
});

// ---------- git-панель (только владелец) ----------
const gitIn = (p, args) => { const r = spawnSync('git', args, { cwd: p, encoding: 'utf8', timeout: 20000, env: { ...process.env, GIT_TERMINAL_PROMPT: '0' } }); return { ok: r.status === 0, out: (r.stdout || '') + (r.stderr || '') }; };
api.get('/git', (req, res) => {
  if (req.user.role !== 'owner') return res.status(403).json({ error: 'Только для владельца' });
  try {
    const p = resolvePath(req.user, req.query.path || '.');
    if (!gitIn(p, ['rev-parse', '--is-inside-work-tree']).ok) return res.json({ repo: false, path: p });
    const branch = gitIn(p, ['rev-parse', '--abbrev-ref', 'HEAD']).out.trim();
    const status = gitIn(p, ['status', '--porcelain']).out.split('\n').filter(Boolean).slice(0, 80).map((l) => ({ code: l.slice(0, 2).trim() || '?', file: l.slice(3) }));
    const log = gitIn(p, ['log', '-12', '--pretty=format:%h\x1f%s\x1f%an\x1f%ar']).out.split('\n').filter(Boolean).map((l) => { const [hash, subject, author, when] = l.split('\x1f'); return { hash, subject, author, when }; });
    const rem = gitIn(p, ['remote', 'get-url', 'origin']); const remote = rem.ok ? rem.out.trim().replace(/\/\/[^@/]*@/, '//') : '';
    const ab = gitIn(p, ['rev-list', '--left-right', '--count', '@{u}...HEAD']);
    const [behind, ahead] = ab.ok ? ab.out.trim().split(/\s+/).map(Number) : [0, 0];
    res.json({ repo: true, path: p, branch, status, log, remote, ahead, behind, diffstat: gitIn(p, ['diff', '--stat']).out.split('\n').slice(-2).join(' ').trim() });
  } catch (e) { res.status(400).json({ error: e.message }); }
});
api.get('/git/repos', (req, res) => {
  if (req.user.role !== 'owner') return res.status(403).json({ error: 'Только для владельца' });
  const root = workspaceOf(req.user.id), out = [];
  const walk = (d, depth) => {
    if (depth > 4 || out.length >= 40) return;
    let ents; try { ents = fs.readdirSync(d, { withFileTypes: true }); } catch { return; }
    if (ents.some((e) => e.name === '.git')) { out.push({ path: path.relative(root, d) || '.', name: path.basename(d) }); return; }
    for (const e of ents) if (e.isDirectory() && !['node_modules', '.gradle', 'build', 'uploads', 'charts', 'skills'].includes(e.name)) walk(path.join(d, e.name), depth + 1);
  };
  walk(root, 0);
  res.json(out);
});
api.post('/git/:action', (req, res) => {
  if (req.user.role !== 'owner') return res.status(403).json({ error: 'Только для владельца' });
  try {
    const p = resolvePath(req.user, req.body.path || '.');
    const env = {};
    const tok = db.prepare('SELECT github_token FROM users WHERE id=?').get(req.user.id)?.github_token;
    let r;
    if (req.params.action === 'commit') { gitIn(p, ['add', '-A']); r = gitIn(p, ['-c', 'user.name=OpenAgent', '-c', 'user.email=agent@openagent.local', 'commit', '-m', String(req.body.message || 'Update').slice(0, 200)]); }
    else if (req.params.action === 'pull') r = gitIn(p, ['pull', '--ff-only']);
    else if (req.params.action === 'push') {
      const askpass = path.resolve(config.dataDir, 'git-askpass.sh');
      const x = spawnSync('git', ['push'], { cwd: p, encoding: 'utf8', timeout: 60000, env: { ...process.env, GIT_TERMINAL_PROMPT: '0', GIT_ASKPASS: askpass, GITHUB_TOKEN: tok || '' } });
      r = { ok: x.status === 0, out: (x.stdout || '') + (x.stderr || '') };
    } else return res.status(400).json({ error: 'Неизвестное действие' });
    res.json({ ok: r.ok, output: r.out.slice(-1500) });
  } catch (e) { res.status(400).json({ error: e.message }); }
});

// ---------- обновления автоматизаций (для фоновых уведомлений) ----------
api.get('/updates', (req, res) => {
  const since = +req.query.since || 0;
  const rows = db.prepare("SELECT id, title, updated_at FROM conversations WHERE user_id=? AND (title LIKE '◷%' OR title LIKE '⏱%') AND updated_at>? ORDER BY updated_at DESC LIMIT 10").all(req.user.id, since);
  res.json(rows.filter((r) => !runs.has(r.id)).map((r) => ({ id: r.id, title: r.title, updatedAt: r.updated_at, preview: (db.prepare("SELECT content FROM messages WHERE conv_id=? AND role='assistant' AND content!='' ORDER BY id DESC LIMIT 1").get(r.id)?.content || '').replace(/\s+/g, ' ').slice(0, 160) })));
});

// ---------- контрольные точки (откат изменений агента) ----------
function cwdOfConv(req) {
  const conv = db.prepare('SELECT * FROM conversations WHERE id=? AND user_id=?').get(+req.params.id, req.user.id);
  if (!conv || conv.mode !== 'code') return null;
  return cwdFor(req.user, conv, conv.project_id ? db.prepare('SELECT * FROM projects WHERE id=?').get(conv.project_id) : null);
}
api.get('/conversations/:id/checkpoints', (req, res) => { const d = cwdOfConv(req); if (!d) return res.json([]); res.json(listCheckpoints(d)); });
api.get('/conversations/:id/checkpoints/:hash', (req, res) => { const d = cwdOfConv(req); if (!d) return res.json([]); res.json(checkpointFiles(d, req.params.hash)); });
api.post('/conversations/:id/restore', (req, res) => {
  const d = cwdOfConv(req); if (!d) return res.status(404).json({ error: 'Только для Code-чатов' });
  if (runs.has(+req.params.id)) return res.status(409).json({ error: 'Дождитесь окончания работы агента' });
  try { res.json(restoreCp(d, String(req.body.hash))); } catch (e) { res.status(400).json({ error: e.message }); }
});
api.post('/conversations/:id/checkpoint', (req, res) => { const d = cwdOfConv(req); if (!d) return res.status(404).json({ error: 'Только для Code-чатов' }); res.json(snapshot(d, String(req.body.message || 'Вручную').slice(0, 100)) || { hash: null }); });

// ---------- проекты ----------
const slugP = (s) => String(s).toLowerCase().replace(/[^a-z0-9а-яё]+/gi, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'project';
api.get('/projects', (req, res) => res.json(db.prepare('SELECT id,name,slug,repo,created_at FROM projects WHERE user_id=? ORDER BY id DESC').all(req.user.id).map((p) => ({ id: p.id, name: p.name, slug: p.slug, repo: p.repo, createdAt: p.created_at, chats: db.prepare('SELECT COUNT(*) c FROM conversations WHERE project_id=?').get(p.id).c, files: (() => { try { return fs.readdirSync(path.join(workspaceOf(req.user.id), 'projects', p.slug)).filter((x) => !x.startsWith('.')).length; } catch { return 0; } })() }))));
api.post('/projects', async (req, res) => {
  const name = String(req.body.name || '').trim().slice(0, 60);
  if (!name) return res.status(400).json({ error: 'Нужно название' });
  let slug = slugP(name); const base = slug; let n = 1;
  while (db.prepare('SELECT 1 FROM projects WHERE user_id=? AND slug=?').get(req.user.id, slug)) slug = `${base}-${++n}`;
  const dir = path.join(workspaceOf(req.user.id), 'projects', slug); fs.mkdirSync(dir, { recursive: true });
  const repo = String(req.body.repo || '').trim();
  let note = '';
  if (repo) {
    if (req.user.role !== 'owner') return res.status(403).json({ error: 'Клонирование доступно только владельцу' });
    const tok = db.prepare('SELECT github_token FROM users WHERE id=?').get(req.user.id)?.github_token;
    const url = /^[\w.-]+\/[\w.-]+$/.test(repo) ? `https://github.com/${repo}.git` : repo;
    const askpass = path.resolve(config.dataDir, 'git-askpass.sh');
    const r2 = spawnSync('git', ['clone', '--depth', '50', url, '.'], { cwd: dir, encoding: 'utf8', timeout: 180000, env: { ...process.env, GIT_TERMINAL_PROMPT: '0', GIT_ASKPASS: askpass, GITHUB_TOKEN: tok || '' } });
    if (r2.status !== 0) { fs.rmSync(dir, { recursive: true, force: true }); return res.status(400).json({ error: `Не удалось клонировать: ${(r2.stderr || '').slice(-200)}` }); }
    note = 'клонирован';
  }
  const id = db.prepare('INSERT INTO projects(user_id,name,slug,repo,created_at) VALUES (?,?,?,?,?)').run(req.user.id, name, slug, repo || null, now()).lastInsertRowid;
  res.json({ id: Number(id), slug, note });
});
api.delete('/projects/:id', (req, res) => {
  const p = db.prepare('SELECT * FROM projects WHERE id=? AND user_id=?').get(+req.params.id, req.user.id);
  if (!p) return res.sendStatus(404);
  db.prepare('UPDATE conversations SET project_id=NULL WHERE project_id=?').run(p.id);
  db.prepare('DELETE FROM projects WHERE id=?').run(p.id);
  if (req.query.files === '1') fs.rmSync(path.join(workspaceOf(req.user.id), 'projects', p.slug), { recursive: true, force: true });
  res.json({ ok: true });
});

// ---------- библиотека промптов ----------
api.get('/prompts', (req, res) => res.json(db.prepare('SELECT id,name,text FROM prompts WHERE user_id=? ORDER BY name').all(req.user.id)));
api.post('/prompts', (req, res) => {
  const name = String(req.body.name || '').trim().replace(/\s+/g, '-').slice(0, 30), text = String(req.body.text || '').trim().slice(0, 4000);
  if (!name || !text) return res.status(400).json({ error: 'Нужны название и текст' });
  db.prepare('INSERT INTO prompts(user_id,name,text) VALUES (?,?,?) ON CONFLICT(user_id,name) DO UPDATE SET text=excluded.text').run(req.user.id, name, text);
  res.json({ ok: true });
});
api.delete('/prompts/:id', (req, res) => res.json({ ok: db.prepare('DELETE FROM prompts WHERE id=? AND user_id=?').run(+req.params.id, req.user.id).changes > 0 }));

import { mountExtras } from './extras.js';
mountExtras(api);
