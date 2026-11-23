// Дополнительные функции: подключения (MCP), заметки (в т.ч. голосовые), задачи, секреты, публичные ссылки на чаты, сравнение моделей, экспорт.
import crypto from 'node:crypto';
import multer from 'multer';
import { db, now } from './db.js';
import { config } from './config.js';
import { encSecret, decSecret, resolveProvider } from './providers.js';
import { chatOnce, parseJson } from './llm.js';
import { deepgramTranscribe } from './sttStream.js';
import { pplxAgent } from './perplexity.js';
import { listMissions, setMissionStatus, deleteMission } from './missions.js';
import { addAccount, listAccounts, removeAccount, presetFor } from './mail.js';
import { MCP_PRESETS, mcpAllServers, mcpTools, forgetMcp } from './mcp.js';

const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 60 * 1024 * 1024 } });

// ================= секреты =================
export const listSecretNames = (uid) => db.prepare('SELECT name FROM secrets WHERE user_id=? ORDER BY name').all(uid).map((r) => r.name);
const secretMap = (uid) => { const m = {}; for (const r of db.prepare('SELECT name,value FROM secrets WHERE user_id=?').all(uid)) { try { m[r.name] = decSecret(r.value); } catch {} } return m; };

/** {{secret:NAME}} в аргументах инструмента заменяется значением (модель сама значений не видит). */
export function injectSecrets(user, val) {
  const m = secretMap(user.id);
  if (!Object.keys(m).length) return val;
  const re = /\{\{\s*secret:([A-Za-z0-9_.-]+)\s*\}\}/g;
  const walk = (v) => typeof v === 'string' ? v.replace(re, (_, n) => m[n] ?? `{{secret:${n}}}`) : Array.isArray(v) ? v.map(walk) : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, walk(x)])) : v;
  return walk(val);
}
/** Значения секретов в ответах инструментов заменяются обратно на {{secret:NAME}}. */
export function maskSecrets(user, text) {
  let t = String(text ?? '');
  const m = secretMap(user.id);
  for (const [n, v] of Object.entries(m)) if (v && v.length >= 6) t = t.split(v).join(`{{secret:${n}}}`);
  return t;
}

// ================= задачи =================
export function tasksTool(user, a) {
  const op = String(a.op || 'list');
  if (op === 'add') {
    const text = String(a.text || '').trim().slice(0, 300); if (!text) return 'Ошибка: нужен text';
    const due = a.due ? Date.parse(a.due) : null;
    const id = db.prepare('INSERT INTO todos(user_id,text,due,created_at) VALUES (?,?,?,?)').run(user.id, text, Number.isFinite(due) ? due : null, now()).lastInsertRowid;
    return `Задача #${id} добавлена: ${text}`;
  }
  if (op === 'done') return db.prepare('UPDATE todos SET done=1, done_at=? WHERE id=? AND user_id=?').run(now(), +a.id, user.id).changes ? `Задача #${a.id} выполнена` : 'Задача не найдена';
  if (op === 'delete') return db.prepare('DELETE FROM todos WHERE id=? AND user_id=?').run(+a.id, user.id).changes ? `Задача #${a.id} удалена` : 'Задача не найдена';
  const rows = db.prepare('SELECT * FROM todos WHERE user_id=? ORDER BY done, id DESC LIMIT 60').all(user.id);
  return rows.length ? rows.map((r) => `#${r.id} [${r.done ? 'x' : ' '}] ${r.text}${r.due ? ` (до ${new Date(r.due).toISOString().slice(0, 16).replace('T', ' ')})` : ''}`).join('\n') : 'Список задач пуст';
}

// ================= публичная страница чата =================
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
function md2html(t) {
  const blocks = String(t || '').split(/```/);
  return blocks.map((b, i) => i % 2 ? `<pre>${esc(b.replace(/^[^\n]*\n/, ''))}</pre>` : esc(b)
    .replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>')
    .replace(/(https?:\/\/[^\s<)]+)/g, '<a href="$1" rel="noopener nofollow">$1</a>').replace(/\n/g, '<br>')).join('');
}
export function mountShare(app) {
  app.get('/share/:token', (req, res) => {
    const sh = db.prepare('SELECT * FROM shares WHERE token=?').get(String(req.params.token));
    if (!sh) return res.status(404).type('html').send('<h3 style="font-family:sans-serif">Ссылка недействительна</h3>');
    const conv = db.prepare('SELECT * FROM conversations WHERE id=?').get(sh.conv_id);
    const rows = db.prepare("SELECT role, content FROM messages WHERE conv_id=? AND role IN ('user','assistant') AND content!='' ORDER BY id").all(sh.conv_id);
    const body = rows.map((r) => `<div class="m ${r.role}">${md2html(r.content)}</div>`).join('');
    res.set({ 'X-Robots-Tag': 'noindex', 'Cache-Control': 'no-store', 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'", 'Referrer-Policy': 'no-referrer' });
    res.type('html').send(`<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>${esc(conv?.title || 'Чат')}</title>
<style>body{margin:0;background:#000;color:#ececf0;font:16px/1.55 system-ui,sans-serif}main{max-width:720px;margin:0 auto;padding:28px 18px 60px}h1{font:600 22px/1.3 Georgia,serif;margin:0 0 22px}.m{margin:14px 0;padding:12px 16px;border-radius:20px;overflow-wrap:anywhere}.user{background:#2b2b30;margin-left:12%}.assistant{background:#101012;border:1px solid #26262b}pre{background:#060607;padding:12px;border-radius:12px;overflow:auto;font-size:13px}code{background:#1c1c20;padding:1px 5px;border-radius:6px}a{color:#c4c5cc}footer{color:#77777f;font-size:13px;margin-top:34px;text-align:center}</style></head><body><main><h1>${esc(conv?.title || 'Чат')}</h1>${body}<footer>Сделано в OpenAgent</footer></main></body></html>`);
  });
}

// ================= маршруты =================
export function mountExtras(api) {
  const own = (req) => db.prepare('SELECT * FROM conversations WHERE id=? AND user_id=?').get(+req.params.id, req.user.id);

  // ---- подключения (MCP) ----
  api.get('/mcp', (req, res) => res.json({
    presets: MCP_PRESETS,
    servers: mcpAllServers(req.user.id).map((s) => ({ id: s.id, name: s.name, url: s.url, enabled: !!s.enabled, auth: !!(s.headers && s.headers !== '{}') })),
  }));
  api.post('/mcp', async (req, res) => {
    const b = req.body; const url = String(b.url || '').trim();
    if (!/^https:\/\//.test(url) && !/^http:\/\/(localhost|127\.)/.test(url)) return res.status(400).json({ error: 'Нужен адрес https://…' });
    const headers = {};
    if (b.token) headers[String(b.header || 'Authorization').slice(0, 40)] = (b.header && !/^authorization$/i.test(b.header)) ? String(b.token) : `Bearer ${String(b.token).replace(/^Bearer\s+/i, '')}`;
    const id = Number(db.prepare('INSERT INTO mcp_servers(user_id,name,url,headers,created_at) VALUES (?,?,?,?,?)').run(req.user.id, String(b.name || url).slice(0, 60), url, JSON.stringify(headers), now()).lastInsertRowid);
    const s = db.prepare('SELECT * FROM mcp_servers WHERE id=?').get(id);
    try { const tools = await mcpTools(s, { force: true }); res.json({ id, tools: tools.map((t) => t.name) }); }
    catch (e) { res.json({ id, tools: [], error: e.message }); }
  });
  api.post('/mcp/:id/test', async (req, res) => {
    const s = db.prepare('SELECT * FROM mcp_servers WHERE id=? AND user_id=?').get(+req.params.id, req.user.id);
    if (!s) return res.sendStatus(404);
    try { forgetMcp(s.id); const tools = await mcpTools(s, { force: true }); res.json({ tools: tools.map((t) => t.name) }); } catch (e) { res.json({ tools: [], error: e.message }); }
  });
  api.patch('/mcp/:id', (req, res) => {
    if (typeof req.body.enabled === 'boolean') db.prepare('UPDATE mcp_servers SET enabled=? WHERE id=? AND user_id=?').run(req.body.enabled ? 1 : 0, +req.params.id, req.user.id);
    res.json({ ok: true });
  });
  api.delete('/mcp/:id', (req, res) => { db.prepare('DELETE FROM mcp_servers WHERE id=? AND user_id=?').run(+req.params.id, req.user.id); forgetMcp(+req.params.id); res.json({ ok: true }); });

  // ---- заметки ----
  api.get('/notes', (req, res) => res.json(db.prepare('SELECT id,title,text,summary,source,updated_at AS updatedAt FROM notes WHERE user_id=? ORDER BY updated_at DESC LIMIT 300').all(req.user.id)));
  api.post('/notes', (req, res) => {
    const text = String(req.body.text || '').trim(); if (!text) return res.status(400).json({ error: 'Пустая заметка' });
    const t = now();
    const id = Number(db.prepare('INSERT INTO notes(user_id,title,text,source,created_at,updated_at) VALUES (?,?,?,?,?,?)').run(req.user.id, String(req.body.title || text.split('\n')[0]).slice(0, 80), text.slice(0, 20000), 'text', t, t).lastInsertRowid);
    res.json({ id });
  });
  api.post('/notes/audio', upload.single('audio'), async (req, res) => {
    if (!req.file) return res.status(400).json({ error: 'нет аудио' });
    try {
      const text = await deepgramTranscribe(req.file.buffer, req.file.originalname, req.file.mimetype, req.body.language || '');
      if (!text) return res.status(422).json({ error: 'Речь не распознана' });
      let title = text.split(/[.!?\n]/)[0].slice(0, 60), summary = '';
      if (text.length > 160) {
        try {
          const j = parseJson(await chatOnce([{ role: 'system', content: 'Из расшифровки голосовой заметки сделай JSON {"title":"заголовок до 6 слов","summary":"суть в 1–3 предложениях, затем пункты действий, если есть"}. Язык оригинала.' }, { role: 'user', content: text.slice(0, 8000) }], { json: true, maxTokens: 300, signal: AbortSignal.timeout(15000), failFast: true }));
          if (j?.title) title = String(j.title).slice(0, 80); if (j?.summary) summary = String(j.summary).slice(0, 1200);
        } catch {}
      }
      const t = now();
      const id = Number(db.prepare('INSERT INTO notes(user_id,title,text,summary,source,created_at,updated_at) VALUES (?,?,?,?,?,?,?)').run(req.user.id, title || 'Голосовая заметка', text.slice(0, 20000), summary || null, 'voice', t, t).lastInsertRowid);
      res.json({ id, title, text, summary });
    } catch (e) { res.status(502).json({ error: e.message }); }
  });
  api.patch('/notes/:id', (req, res) => {
    const n = db.prepare('SELECT * FROM notes WHERE id=? AND user_id=?').get(+req.params.id, req.user.id); if (!n) return res.sendStatus(404);
    db.prepare('UPDATE notes SET title=?, text=?, updated_at=? WHERE id=?').run(String(req.body.title ?? n.title).slice(0, 80), String(req.body.text ?? n.text).slice(0, 20000), now(), n.id);
    res.json({ ok: true });
  });
  api.delete('/notes/:id', (req, res) => { db.prepare('DELETE FROM notes WHERE id=? AND user_id=?').run(+req.params.id, req.user.id); res.json({ ok: true }); });

  // ---- задачи ----
  api.get('/todos', (req, res) => res.json(db.prepare('SELECT id,text,done,due,created_at AS createdAt FROM todos WHERE user_id=? ORDER BY done, id DESC LIMIT 300').all(req.user.id).map((r) => ({ ...r, done: !!r.done }))));
  api.post('/todos', (req, res) => {
    const text = String(req.body.text || '').trim().slice(0, 300); if (!text) return res.status(400).json({ error: 'Пустая задача' });
    res.json({ id: Number(db.prepare('INSERT INTO todos(user_id,text,due,created_at) VALUES (?,?,?,?)').run(req.user.id, text, req.body.due || null, now()).lastInsertRowid) });
  });
  api.patch('/todos/:id', (req, res) => {
    if (typeof req.body.done === 'boolean') db.prepare('UPDATE todos SET done=?, done_at=? WHERE id=? AND user_id=?').run(req.body.done ? 1 : 0, req.body.done ? now() : null, +req.params.id, req.user.id);
    if (typeof req.body.text === 'string') db.prepare('UPDATE todos SET text=? WHERE id=? AND user_id=?').run(req.body.text.slice(0, 300), +req.params.id, req.user.id);
    res.json({ ok: true });
  });
  api.delete('/todos/:id', (req, res) => { db.prepare('DELETE FROM todos WHERE id=? AND user_id=?').run(+req.params.id, req.user.id); res.json({ ok: true }); });

  // ---- секреты ----
  api.get('/secrets', (req, res) => res.json(listSecretNames(req.user.id)));
  api.post('/secrets', (req, res) => {
    const name = String(req.body.name || '').trim(), value = String(req.body.value || '');
    if (!/^[A-Za-z0-9_.-]{1,40}$/.test(name) || !value) return res.status(400).json({ error: 'Имя: латиница, цифры, _ . - (до 40 символов); значение обязательно' });
    db.prepare('INSERT INTO secrets(user_id,name,value,created_at) VALUES (?,?,?,?) ON CONFLICT(user_id,name) DO UPDATE SET value=excluded.value').run(req.user.id, name, encSecret(value), now());
    res.json({ ok: true });
  });
  api.delete('/secrets/:name', (req, res) => { db.prepare('DELETE FROM secrets WHERE user_id=? AND name=?').run(req.user.id, String(req.params.name)); res.json({ ok: true }); });

  // ---- публичные ссылки на чаты ----
  api.get('/conversations/:id/share', (req, res) => {
    if (!own(req)) return res.sendStatus(404);
    const s = db.prepare('SELECT token FROM shares WHERE conv_id=? AND user_id=?').get(+req.params.id, req.user.id);
    res.json({ url: s ? `${config.publicUrl}/share/${s.token}` : null });
  });
  api.post('/conversations/:id/share', (req, res) => {
    if (!own(req)) return res.sendStatus(404);
    let s = db.prepare('SELECT token FROM shares WHERE conv_id=? AND user_id=?').get(+req.params.id, req.user.id);
    if (!s) { s = { token: crypto.randomBytes(16).toString('hex') }; db.prepare('INSERT INTO shares(token,user_id,conv_id,created_at) VALUES (?,?,?,?)').run(s.token, req.user.id, +req.params.id, now()); }
    res.json({ url: `${config.publicUrl}/share/${s.token}` });
  });
  api.delete('/conversations/:id/share', (req, res) => { db.prepare('DELETE FROM shares WHERE conv_id=? AND user_id=?').run(+req.params.id, req.user.id); res.json({ ok: true }); });

  // ---- сравнение моделей: один вопрос — несколько моделей параллельно ----
  api.post('/compare', async (req, res) => {
    const text = String(req.body.text || '').trim().slice(0, 4000);
    const targets = (Array.isArray(req.body.targets) ? req.body.targets : []).slice(0, 3);
    if (!text || targets.length < 2) return res.status(400).json({ error: 'Нужен вопрос и минимум две модели' });
    const sys = 'Отвечай по-русски (если вопрос на другом языке — на нём), точно и по делу.';
    const out = await Promise.all(targets.map(async (t) => {
      const t0 = Date.now(); const label = `${t.provider || 'river'} · ${t.model}`;
      try {
        let answer;
        if (t.provider === 'perplexity') {
          const m = String(t.model || 'agent-low');
          answer = (await pplxAgent(req.user, { effort: m.replace(/^agent-/, ''), model: m.includes('/') ? m : undefined, input: [{ role: 'user', content: text }], signal: AbortSignal.timeout(90000) })).text;
        } else {
          const prov = resolveProvider(req.user, t.provider || 'river');
          answer = await chatOnce([{ role: 'system', content: sys }, { role: 'user', content: text }], { prov, model: t.model, maxTokens: 900, signal: AbortSignal.timeout(60000) });
        }
        return { provider: t.provider, model: t.model, label, text: String(answer).trim(), ms: Date.now() - t0 };
      } catch (e) { return { provider: t.provider, model: t.model, label, error: e.message, ms: Date.now() - t0 }; }
    }));
    res.json(out);
  });

  // ---- профиль (мастер первоначальной настройки) ----
  api.get('/profile', (req, res) => { let p = {}; try { p = JSON.parse(db.prepare('SELECT profile FROM users WHERE id=?').get(req.user.id)?.profile || '{}'); } catch {} res.json(p); });
  api.post('/profile', (req, res) => {
    const b = req.body || {}; const clip = (v, n = 300) => String(v || '').trim().slice(0, n);
    const p = { name: clip(b.name, 60), city: clip(b.city, 80), job: clip(b.job, 160), interests: clip(b.interests, 300), about: clip(b.about, 600), style: clip(b.style, 30), address: clip(b.address, 20), humor: clip(b.humor, 20), home: clip(b.home, 160) };
    db.prepare('UPDATE users SET profile=?, name=COALESCE(NULLIF(?,\'\'), name) WHERE id=?').run(JSON.stringify(p), p.name, req.user.id);
    res.json({ ok: true });
  });

  // ---- миссии ----
  api.get('/missions', (req, res) => res.json(listMissions(req.user.id)));
  api.patch('/missions/:id', (req, res) => res.json({ ok: setMissionStatus(req.user.id, req.params.id, ['active', 'paused', 'done'].includes(req.body.status) ? req.body.status : 'paused') }));
  api.delete('/missions/:id', (req, res) => res.json({ ok: deleteMission(req.user.id, req.params.id) }));

  // ---- почта ----
  api.get('/mail', (req, res) => res.json(listAccounts(req.user.id)));
  api.get('/mail/hint', (req, res) => res.json({ hint: presetFor(String(req.query.email || ''))?.hint || 'Укажите адреса IMAP и SMTP вашего провайдера и пароль приложения.', known: !!presetFor(String(req.query.email || '')) }));
  api.post('/mail', async (req, res) => { try { res.json({ email: await addAccount(req.user.id, req.body) }); } catch (e) { res.status(400).json({ error: e.message }); } });
  api.delete('/mail/:id', (req, res) => res.json({ ok: removeAccount(req.user.id, req.params.id) }));

  // ---- журнал действий агента: что он делал на телефоне и сервере (прозрачность автономной работы) ----
  const AUDIT = new Set(['mail', 'mission_create', 'phone', 'bash', 'http_request', 'deploy_site', 'delete_site', 'github_api', 'schedule_create', 'schedule_delete', 'process']);
  api.get('/activity', (req, res) => {
    const since = now() - Math.min(+req.query.days || 7, 30) * 86400e3;
    const rows = db.prepare("SELECT m.id, m.created_at, m.tool_calls, c.id AS cid, c.title FROM messages m JOIN conversations c ON c.id=m.conv_id WHERE c.user_id=? AND m.role='assistant' AND m.tool_calls IS NOT NULL AND m.created_at>? ORDER BY m.id DESC LIMIT 600").all(req.user.id, since);
    const out = [];
    for (const r of rows) {
      let calls; try { calls = JSON.parse(r.tool_calls); } catch { continue; }
      for (const c of calls) {
        const name = c.function?.name; if (!AUDIT.has(name)) continue;
        let a = {}; try { a = JSON.parse(c.function.arguments || '{}'); } catch {}
        const outward = name === 'phone' ? ['call', 'sms', 'message'].includes(a.action) || !!a.confirmed : ['deploy_site', 'delete_site', 'schedule_create', 'schedule_delete'].includes(name);
        const summary = name === 'phone' ? [a.action, a.text || a.to || a.app || a.query || a.url || a.until || '', a.action === 'message' || a.action === 'sms' ? `«${String(a.text || '').slice(0, 60)}»` : ''].filter(Boolean).join(' · ')
          : name === 'bash' ? String(a.command || '').slice(0, 140) : name === 'http_request' ? `${a.method || 'GET'} ${String(a.url || '').slice(0, 100)}` : name === 'github_api' ? `${a.method || 'GET'} ${a.path || ''}` : String(a.name || a.slug || a.action || a.pid || '').slice(0, 100);
        out.push({ ts: r.created_at, convId: r.cid, title: r.title, tool: name, summary, outward });
        if (out.length >= 250) return res.json(out);
      }
    }
    res.json(out);
  });

  // ---- резервная копия ----
  api.get('/export', (req, res) => {
    const convs = db.prepare('SELECT id,title,mode,created_at,updated_at FROM conversations WHERE user_id=? ORDER BY id').all(req.user.id).map((c) => ({
      ...c, messages: db.prepare("SELECT role, content, created_at FROM messages WHERE conv_id=? AND role IN ('user','assistant') AND content!='' ORDER BY id").all(c.id),
    }));
    const data = {
      exportedAt: new Date().toISOString(), app: 'OpenAgent', conversations: convs,
      memories: db.prepare('SELECT kind, content, importance FROM memories WHERE user_id=?').all(req.user.id),
      notes: db.prepare('SELECT title, text, summary, source, created_at FROM notes WHERE user_id=?').all(req.user.id),
      todos: db.prepare('SELECT text, done, due FROM todos WHERE user_id=?').all(req.user.id),
      prompts: db.prepare('SELECT name, text FROM prompts WHERE user_id=?').all(req.user.id),
    };
    res.set({ 'Content-Type': 'application/json; charset=utf-8', 'Content-Disposition': 'attachment; filename="openagent-backup.json"' });
    res.send(JSON.stringify(data, null, 1));
  });
}
