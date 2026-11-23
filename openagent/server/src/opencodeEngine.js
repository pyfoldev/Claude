// Движок режима Code: opencode (https://opencode.ai, MIT) в headless-режиме `opencode serve`.
// Вместо собственного цикла агента сервер держит процесс opencode (по одному на владельца), шлёт ему сообщения и превращает его события
// в привычные приложению сообщения (assistant + tool). Модели — river.ai через OpenAI-совместимый провайдер; инструменты OpenAgent (сайты, файлы,
// документы, графики, поиск, память) доступны через MCP (ocMcp.js); дизайн сайтов — навык «opendesign» (каталог дизайн-систем OpenDesign).
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { config } from './config.js';
import { db } from './db.js';
import { askpassPath } from './workspace.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OC_BIN = process.env.OPENCODE_BIN || path.join(HERE, '..', 'node_modules', '.bin', 'opencode');
const MCP_JS = path.join(HERE, 'ocMcp.js');
const ROOT = () => path.resolve(config.dataDir, 'oc');
export const OPENDESIGN_DIR = () => process.env.OPENDESIGN_DIR || '/opt/opendesign';

export const engineAvailable = () => process.env.CODE_ENGINE !== 'legacy' && fs.existsSync(OC_BIN);

const servers = new Map();   // uid -> { port, pw, proc, ready, listeners, active, sig }
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); s.on('error', rej); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- навык OpenDesign: каталог дизайн-систем и правила «ремесла» из репозитория nexu-io/open-design (Apache-2.0) ----
function writeOpenDesignSkill(skillsDir) {
  const od = OPENDESIGN_DIR();
  if (!fs.existsSync(path.join(od, 'design-systems'))) return false;
  const systems = fs.readdirSync(path.join(od, 'design-systems'), { withFileTypes: true }).filter((e) => e.isDirectory() && fs.existsSync(path.join(od, 'design-systems', e.name, 'DESIGN.md')));
  const idx = systems.map((e) => {
    let head = ''; try { head = fs.readFileSync(path.join(od, 'design-systems', e.name, 'DESIGN.md'), 'utf8').slice(0, 600); } catch {}
    const cat = /Category:\s*([^\n]+)/.exec(head)?.[1] || ''; const desc = (/^>\s*(?!Category)([^\n]+)/m.exec(head)?.[1] || '').slice(0, 90);
    return `- ${e.name}${cat ? ` [${cat}]` : ''}${desc ? ` — ${desc}` : ''}`;
  }).join('\n');
  const tpls = fs.existsSync(path.join(od, 'design-templates')) ? fs.readdirSync(path.join(od, 'design-templates'), { withFileTypes: true }).filter((e) => e.isDirectory() && !/^html-ppt-/.test(e.name)).map((e) => e.name) : [];
  const dir = path.join(skillsDir, 'opendesign'); fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'INDEX.md'), `# Дизайн-системы (${systems.length})\nКаждая: ${od}/design-systems/<имя>/DESIGN.md (описание) и tokens.css (готовые токены).\n\n${idx}\n`);
  fs.writeFileSync(path.join(dir, 'SKILL.md'), `---
name: opendesign
description: Создание красивых сайтов, лендингов, дашбордов, веб-интерфейсов и презентаций в HTML по дизайн-системам OpenDesign. Загружай ПЕРЕД любой работой над внешним видом сайта/страницы/интерфейса.
---
# OpenDesign — как делать сайты и интерфейсы

Каталог лежит в ${od}. Работай так:

1. **Выбери дизайн-систему.** Список с описаниями: ${dir}/INDEX.md (читай целиком один раз). Подбери под задачу и вкус пользователя (fintech → stripe; документация → notion/…; тёмный техно-стиль, минимализм и т.д.). Если пользователь назвал бренд/стиль — возьми ближайшую. Не выбирай наугад и не придумывай палитру «с нуля».
2. **Прочитай ${od}/design-systems/<имя>/DESIGN.md** (цвета, типографика, отступы, компоненты) и скопируй ${od}/design-systems/<имя>/tokens.css в проект — используй CSS-переменные оттуда, а не хардкод цветов.
3. **Возьми шаблон-основу, если подходит.** Шаблоны: ${tpls.slice(0, 60).join(', ')}. Для выбранного: ${od}/design-templates/<имя>/SKILL.md (структура и правила) и example.html (рабочий образец) — адаптируй под задачу.
4. **Правила ремесла** — прочитай нужные из ${od}/craft/: anti-ai-slop.md (ВСЕГДА), state-coverage.md, accessibility-baseline.md, color.md, laws-of-ux.md, animation-discipline.md.
5. **Результат:** статический сайт — index.html + style.css (+ js) в папке проекта, без сборщиков, мобильная адаптивность обязательна, тексты — на языке пользователя, реальные осмысленные тексты вместо lorem ipsum.
6. **Проверь:** открой сайт (например, python3 -m http.server в фоне + скриншот через playwright, если установлен) или хотя бы перечитай разметку на ошибки; остановь сервер.
7. **Публикация** (oa_deploy_site) — ТОЛЬКО если пользователь попросил опубликовать; иначе скажи, что сайт готов и в какой папке, и предложи опубликовать.
`);
  return true;
}

function writeConfig(uid, user) {
  const root = ROOT(); fs.mkdirSync(path.join(root, 'home'), { recursive: true }); fs.mkdirSync(path.join(root, 'config', 'opencode', 'skills'), { recursive: true });
  const keyFile = path.join(root, 'river.key'); fs.writeFileSync(keyFile, config.river.apiKey, { mode: 0o600 });
  const models = {}; for (const m of new Set([config.river.codeModel, config.river.model, config.river.fastModel, ...config.river.allowed])) models[m] = { name: m.split('/').pop(), tool_call: true, limit: { context: 128000, output: 16000 } };
  const keep = ['DATA_DIR', 'WORKSPACES_DIR', 'PUBLIC_URL', 'JWT_SECRET', 'EXA_API_KEY', 'MISTRAL_API_KEY', 'EMBED_MODEL', 'RIVER_API_KEY', 'RIVER_BASE_URL', 'FISH_API_KEY', 'UNOROUTER_API_KEY', 'COARENA_API_KEY', 'OWNER_EMAILS', 'ALLOWED_EMAILS', 'TURNSTILE_SECRET', 'SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASS', 'SENDER_EMAIL', 'IMAGE_MODELS'];
  const environment = { OA_UID: String(uid) }; for (const k of keep) if (process.env[k]) environment[k] = process.env[k];
  environment.DATA_DIR = path.resolve(config.dataDir); environment.WORKSPACES_DIR = path.resolve(config.workspacesDir);
  const cfg = {
    $schema: 'https://opencode.ai/config.json', autoupdate: false, share: 'disabled',
    provider: { river: { npm: '@ai-sdk/openai-compatible', name: 'river.ai', options: { baseURL: config.river.baseUrl, apiKey: `{file:${keyFile}}` }, models } },
    model: `river/${config.river.codeModel}`, small_model: `river/${config.river.fastModel}`,
    permission: { edit: 'allow', bash: 'allow', webfetch: 'allow', external_directory: 'allow', doom_loop: 'allow' },
    mcp: { oa: { type: 'local', command: [process.execPath, MCP_JS], environment, enabled: true } },
  };
  const file = path.join(root, `config-${uid}.json`); fs.writeFileSync(file, JSON.stringify(cfg, null, 1), { mode: 0o600 });
  const od = writeOpenDesignSkill(path.join(root, 'config', 'opencode', 'skills'));
  return { file, od };
}

async function startServer(user) {
  const uid = user.id;
  const { file } = writeConfig(uid, user);
  const root = ROOT(); fs.mkdirSync(root, { recursive: true });
  const pidFile = path.join(root, `server-${uid}.pid`);
  try { const old = +fs.readFileSync(pidFile, 'utf8'); if (old > 1) process.kill(old, 'SIGKILL'); } catch {}   // «осиротевший» процесс после перезапуска сервиса
  const port = await freePort(); const pw = crypto.randomBytes(18).toString('hex');
  const gh = db.prepare('SELECT github_token FROM users WHERE id=?').get(uid)?.github_token || '';
  const env = {
    PATH: process.env.PATH, HOME: path.join(root, 'home'), XDG_DATA_HOME: path.join(root, 'data'), XDG_CONFIG_HOME: path.join(root, 'config'), XDG_CACHE_HOME: path.join(root, 'cache'), XDG_STATE_HOME: path.join(root, 'state'),
    LANG: process.env.LANG || 'C.UTF-8', TERM: 'dumb', OPENCODE_CONFIG: file, OPENCODE_SERVER_PASSWORD: pw, OPENCODE_DISABLE_AUTOUPDATE: 'true', OPENCODE_DISABLE_LSP_DOWNLOAD: 'true',
    GIT_TERMINAL_PROMPT: '0', GIT_ASKPASS: askpassPath(), DEBIAN_FRONTEND: 'noninteractive', ANDROID_HOME: process.env.ANDROID_HOME || '/opt/android-sdk', ...(gh ? { GITHUB_TOKEN: gh, GH_TOKEN: gh } : {}),
  };
  const proc = spawn(OC_BIN, ['serve', '--port', String(port), '--hostname', '127.0.0.1'], { env, stdio: ['ignore', 'pipe', 'pipe'], detached: false });
  const s = { uid, port, pw, proc, listeners: new Map(), active: 0, sig: gh.slice(-6), log: '', up: false, sse: null };
  proc.stdout.on('data', (d) => { s.log = (s.log + d).slice(-4000); }); proc.stderr.on('data', (d) => { s.log = (s.log + d).slice(-4000); });
  proc.on('exit', () => { if (servers.get(uid) === s) servers.delete(uid); s.up = false; s.sseAbort?.abort(); for (const l of s.listeners.values()) l({ type: '__exit' }); });
  servers.set(uid, s);
  try { fs.writeFileSync(pidFile, String(proc.pid)); } catch {}
  const auth = 'Basic ' + Buffer.from(`opencode:${pw}`).toString('base64');
  s.headers = { Authorization: auth };
  for (let i = 0; i < 100; i++) {   // ждём готовности (до ~25 с)
    if (proc.exitCode !== null) throw new Error('opencode не запустился: ' + s.log.slice(-300));
    try { const r = await fetch(`http://127.0.0.1:${port}/global/health`, { headers: s.headers, signal: AbortSignal.timeout(1500) }); if (r.ok) { s.up = true; break; } } catch {}
    await sleep(250);
  }
  if (!s.up) { try { proc.kill(); } catch {} throw new Error('opencode не ответил за 25 с'); }
  startSse(s);
  return s;
}

function startSse(s) {
  s.sseAbort = new AbortController();
  s.sseReady = new Promise((resolve) => { s.sseOk = resolve; });
  (async () => {
    while (servers.get(s.uid) === s) {
      try {
        const r = await fetch(`http://127.0.0.1:${s.port}/global/event`, { headers: s.headers, signal: s.sseAbort.signal });
        let buf = ''; const dec = new TextDecoder();
        for await (const chunk of r.body) {
          buf += dec.decode(chunk, { stream: true }); let i;
          while ((i = buf.indexOf('\n\n')) >= 0) {
            const block = buf.slice(0, i); buf = buf.slice(i + 2);
            const data = block.split('\n').filter((l) => l.startsWith('data:')).map((l) => l.slice(5).trim()).join('');
            if (!data) continue;
            let j; try { j = JSON.parse(data); } catch { continue; }
            const ev = j.payload || j; if (ev.type === 'server.connected') s.sseOk?.();
            const sid = ev.properties?.sessionID || ev.properties?.part?.sessionID || ev.properties?.info?.sessionID;
            if (sid && s.listeners.has(sid)) s.listeners.get(sid)(ev);
          }
        }
      } catch { if (s.sseAbort.signal.aborted) return; }
      await sleep(500);
    }
  })();
}

const starting = new Map();
async function getServer(user) {
  let s = servers.get(user.id);
  const gh = (db.prepare('SELECT github_token FROM users WHERE id=?').get(user.id)?.github_token || '').slice(-6);
  if (s && s.active === 0 && s.sig !== gh) { try { s.proc.kill(); } catch {} servers.delete(user.id); s = null; }   // токен GitHub сменился — перезапуск (когда нет активных запусков)
  if (!s || !s.up) {
    if (!starting.has(user.id)) starting.set(user.id, startServer(user).finally(() => starting.delete(user.id)));
    s = await starting.get(user.id);
  }
  await Promise.race([s.sseReady, sleep(5000)]);
  return s;
}

const call = (s, method, p, body, signal) => fetch(`http://127.0.0.1:${s.port}${p}`, { method, headers: { ...s.headers, 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined, signal });

// ---- соответствие инструментов opencode → имена/аргументы, которые понимает приложение ----
const NAME = { read: 'read_file', write: 'write_file', edit: 'edit_file', multiedit: 'multi_edit', list: 'list_dir', webfetch: 'web_fetch', websearch: 'web_search', todowrite: 'todo_write', todoread: 'todo_write', task: 'delegate', skill: 'skill_load', patch: 'edit_file', apply_patch: 'edit_file' };
export function uiTool(tool, input = {}) {
  const i = input || {}; let name = NAME[tool] || tool.replace(/^oa_/, ''); let args = i;
  if (tool === 'read' || tool === 'write' || tool === 'edit') { args = { path: i.filePath, ...(tool === 'write' ? { content: i.content } : {}), ...(tool === 'edit' ? { old: i.oldString, new: i.newString } : {}), ...(tool === 'read' && i.offset ? { offset: i.offset } : {}) }; }
  else if (tool === 'list') args = { path: i.path };
  else if (tool === 'todowrite') args = { todos: (i.todos || []).map((t) => ({ text: t.content || t.text, status: t.status })) };
  else if (tool === 'task') args = { task: i.description || i.prompt };
  else if (tool === 'skill') args = { name: i.name };
  return { name, args };
}

/**
 * Один ход агента: отправляет текст в сессию opencode и стримит события через колбэки.
 * cb: { delta(text), status(text), toolOutput(id, text), assistant(content, call|null) , tool(callId, name, content, files[]), usage(u), registerFile(abs)→file }
 */
export async function runOpencode({ user, conv, cwd, text, model, system, signal, cb }) {
  const s = await getServer(user);
  s.active++;
  try {
    const q = `directory=${encodeURIComponent(cwd)}`;
    let sid = db.prepare('SELECT oc_session FROM conversations WHERE id=?').get(conv.id)?.oc_session || null;
    if (sid) { const r = await call(s, 'GET', `/session/${sid}?${q}`); if (!r.ok) sid = null; }
    if (!sid) {
      const r = await call(s, 'POST', `/session?${q}`, { title: String(conv.title || 'OpenAgent').slice(0, 60) });
      if (!r.ok) throw new Error('opencode: не удалось создать сессию: ' + (await r.text()).slice(0, 200));
      sid = (await r.json()).id; db.prepare('UPDATE conversations SET oc_session=? WHERE id=?').run(sid, conv.id);
    }
    const role = new Map(), ptype = new Map(), ptext = new Map(), pOrder = [], consumed = new Set(), seenTool = new Set(), outLen = new Map();
    let finish, fail; const done = new Promise((res, rej) => { finish = res; fail = rej; });
    let last = Date.now(), emittedText = '';
    const pending = () => pOrder.filter((id) => ptype.get(id) === 'text' && !consumed.has(id)).map((id) => { consumed.add(id); return ptext.get(id) || ''; }).join('').trim();
    const grab = (out) => { const files = []; const clean = String(out || '').replace(/\n?\[\[OA_FILE:(\{.*?\})\]\]/g, (_m, j) => { try { const f = JSON.parse(j); if (f?.id) files.push(f); } catch {} return ''; }); return { clean, files }; };
    s.listeners.set(sid, (ev) => {
      last = Date.now(); const p = ev.properties || {};
      switch (ev.type) {
        case '__exit': fail(new Error('Процесс opencode завершился: ' + s.log.slice(-200))); break;
        case 'message.updated': if (p.info?.id) role.set(p.info.id, p.info.role); break;
        case 'message.part.delta':
          if (role.get(p.messageID) === 'assistant' && (p.field || 'text') === 'text') { ptext.set(p.partID, (ptext.get(p.partID) || '') + p.delta); if (ptype.get(p.partID) === 'text') { emittedText += p.delta; cb.delta(p.delta); } }
          break;
        case 'message.part.updated': {
          const part = p.part || {};
          if (role.get(part.messageID) === 'user') break;
          if (part.type === 'text' || part.type === 'reasoning') {
            if (!ptype.has(part.id)) { ptype.set(part.id, part.type); if (part.type === 'text') pOrder.push(part.id); }
            if (part.type === 'text' && part.text) {
              const had = ptext.get(part.id) || '';
              if (part.text.length > had.length && part.text.startsWith(had)) { cb.delta(part.text.slice(had.length)); }   // дельты уже отданы — докидываем только недостающее
              ptext.set(part.id, part.text);
            }
            if (part.type === 'reasoning') cb.status('Думаю…');
          } else if (part.type === 'tool') {
            const st = part.state || {}; const ui = uiTool(part.tool, st.input);
            if (st.status === 'running' || st.status === 'pending') { if (!seenTool.has(part.callID)) { seenTool.add(part.callID); cb.status(`${ui.name}${ui.args?.command ? ': ' + String(ui.args.command).slice(0, 60) : ui.args?.path ? ': ' + String(ui.args.path).split('/').pop() : ''}`); }
              const o = st.metadata?.output; if (typeof o === 'string' && o.length > (outLen.get(part.callID) || 0)) { cb.toolOutput(part.callID, o.slice(outLen.get(part.callID) || 0)); outLen.set(part.callID, o.length); } }
            else if (st.status === 'completed' || st.status === 'error') {
              if (consumed.has('tool:' + part.callID)) break; consumed.add('tool:' + part.callID);
              const { clean, files } = grab(st.status === 'error' ? `Ошибка: ${st.error}` : st.output);
              const lead = pending();
              if (lead) emittedText = '';
              cb.assistant(lead, { id: part.callID, name: ui.name, arguments: JSON.stringify(ui.args || {}) });
              cb.tool(part.callID, ui.name, clean || '(нет вывода)', files);
              if (ui.name === 'ask_user') { call(s, 'POST', `/session/${sid}/abort?${q}`).catch(() => {}); finish(); }   // вопрос показан — ход завершён, ждём ответа
            }
          } else if (part.type === 'step-finish') {
            const t = part.tokens || {}; cb.usage({ prompt_tokens: (t.input || 0) + (t.cache?.read || 0), completion_tokens: t.output || 0, prompt_tokens_details: { cached_tokens: t.cache?.read || 0 } });
          }
          break;
        }
        case 'session.error': fail(new Error(p.error?.data?.message || p.error?.message || p.error?.name || 'ошибка opencode')); break;
        case 'session.idle': finish(); break;
        default: break;
      }
    });
    const onAbort = () => { call(s, 'POST', `/session/${sid}/abort?${q}`).catch(() => {}); fail(new Error('aborted')); };
    signal?.addEventListener('abort', onAbort, { once: true });
    const watchdog = setInterval(() => { if (Date.now() - last > 10 * 60 * 1000) { call(s, 'POST', `/session/${sid}/abort?${q}`).catch(() => {}); fail(new Error('opencode: нет событий 10 минут')); } }, 30000);
    try {
      const r = await call(s, 'POST', `/session/${sid}/prompt_async?${q}`, { model: { providerID: 'river', modelID: model }, system, parts: [{ type: 'text', text }] }, signal);
      if (!r.ok) throw new Error(`opencode: ${r.status} ${(await r.text()).slice(0, 300)}`);
      await done;
      const tail = pending(); if (tail) cb.assistant(tail, null);
    } finally { clearInterval(watchdog); signal?.removeEventListener('abort', onAbort); s.listeners.delete(sid); }
  } finally { s.active--; }
}

export function stopAll() { for (const s of servers.values()) { try { s.proc.kill(); } catch {} } servers.clear(); }
process.on('exit', stopAll);
for (const sig of ['SIGTERM', 'SIGINT']) process.on(sig, () => { stopAll(); process.exit(0); });
