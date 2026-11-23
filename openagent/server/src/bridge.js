// «Мост через телефон»: сервер (Гонконг) не может обращаться к Groq, поэтому запросы к api.groq.com выполняет само приложение.
// Приложение держит WebSocket /api/llm-bridge; сервер присылает HTTP-запрос (без ключа), приложение добавляет СВОЙ ключ Groq,
// выполняет запрос и построчно возвращает ответ. Ключ Groq остаётся только на телефоне.
import crypto from 'node:crypto';

const sessions = new Map();          // userId -> { ws, pending: Map }
const END = Symbol('end');

export const bridgeUp = (uid) => { const s = sessions.get(uid); return !!s && s.ws.readyState === 1; };
/** Есть ли у приложения ключ для этого хоста (приложение присылает список при подключении). */
export const bridgeHas = (uid, host) => { const s = sessions.get(uid); return !!s && s.ws.readyState === 1 && s.hosts.has(host); };

export function registerBridge(uid, ws) {
  const old = sessions.get(uid);
  const s = { ws, pending: new Map(), hosts: new Set() };
  sessions.set(uid, s);
  try { old?.ws.close(); } catch {}
  ws.on('message', (data) => {
    let m; try { m = JSON.parse(data.toString()); } catch { return; }
    if (m.t === 'caps') { s.hosts = new Set((m.hosts || []).map(String)); return; }
    const p = s.pending.get(m.id);
    if (!p) return;
    if (m.t === 'head') p.onHead(m);
    else if (m.t === 'data') p.onData(m.s || '');
    else if (m.t === 'end') { s.pending.delete(m.id); p.onEnd(); }
    else if (m.t === 'err') { s.pending.delete(m.id); p.onErr(m.message || 'ошибка моста'); }
  });
  const gone = () => {
    if (sessions.get(uid) === s) sessions.delete(uid);
    for (const [, p] of s.pending) p.onErr('Телефон отключился');
    s.pending.clear();
  };
  ws.on('close', gone); ws.on('error', gone);
  ws.send(JSON.stringify({ t: 'hello' }));
}

/** fetch-подобный вызов через телефон. Возвращает объект, совместимый с тем, что ждёт llm.js (ok/status/headers.get/body/text/json). */
export function bridgeFetch(uid, url, init = {}) {
  const s = sessions.get(uid);
  if (!s || s.ws.readyState !== 1) return Promise.reject(new Error('Телефон не подключён: Groq работает только через приложение'));
  const id = crypto.randomBytes(6).toString('hex');
  return new Promise((resolve, reject) => {
    let head = null, waiting = null, finished = false;
    const queue = [];
    const push = (v) => { if (waiting) { const w = waiting; waiting = null; w(v); } else queue.push(v); };
    const abort = () => { if (finished) return; finished = true; s.pending.delete(id); try { s.ws.send(JSON.stringify({ t: 'abort', id })); } catch {} push(END); };
    const body = {
      [Symbol.asyncIterator]() {
        return {
          async next() {
            const v = queue.length ? queue.shift() : await new Promise((r) => { waiting = r; });
            if (v === END) return { done: true, value: undefined };
            if (v instanceof Error) throw v;
            return { done: false, value: v };
          },
          async return() { abort(); return { done: true, value: undefined }; },
        };
      },
    };
    const readAll = async () => { let out = ''; for await (const c of body) out += c.toString('utf8'); return out; };
    const timer = setTimeout(() => { if (!head) { s.pending.delete(id); reject(new Error('Телефон не ответил (проверьте, что приложение открыто)')); } }, 25000);
    s.pending.set(id, {
      onHead: (h) => {
        head = h; clearTimeout(timer);
        const hd = Object.fromEntries(Object.entries(h.headers || {}).map(([k, v]) => [k.toLowerCase(), v]));
        resolve({ ok: h.status >= 200 && h.status < 300, status: h.status, headers: { get: (k) => hd[String(k).toLowerCase()] ?? null }, body, text: readAll, json: async () => JSON.parse(await readAll()) });
      },
      onData: (str) => push(Buffer.from(str, 'utf8')),
      onEnd: () => { finished = true; push(END); },
      onErr: (msg) => { clearTimeout(timer); if (!head) reject(new Error(msg)); else push(new Error(msg)); },
    });
    init.signal?.addEventListener('abort', () => { clearTimeout(timer); if (!head) { s.pending.delete(id); reject(new Error('aborted')); } abort(); }, { once: true });
    s.ws.send(JSON.stringify({ t: 'req', id, url, method: init.method || 'POST', headers: init.headers || {}, body: init.body ?? null }));
  });
}
