/**
 * Долговременная память (3 слоя):
 *  1. Ядро     — важные факты о пользователе (importance >= 0.8) всегда попадают в промпт.
 *  2. Эпизоды  — извлечённые после каждого диалога факты/предпочтения/проекты,
 *                гибридный поиск: векторы (mistral-embed) + BM25 (FTS5) → RRF.
 *  3. Сводки   — скользящее резюме каждого чата (см. agent.js) + MEMORY.md в рабочей папке,
 *                который агент правит сам, как CLAUDE.md.
 * Дубликаты сливаются по косинусной близости, слабые/старые воспоминания вытесняются.
 */
import { db, now } from './db.js';
import { embed, chatOnce, parseJson } from './llm.js';

const MEM_MAX = 600;
const DUP_SIM = 0.9;

const toBuf = (f) => Buffer.from(f.buffer, f.byteOffset, f.byteLength);
const fromBuf = (b) => new Float32Array(b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength));
function cosine(a, b) {
  let d = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) { d += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
  return d / (Math.sqrt(na * nb) || 1);
}
const ftsQuery = (q) => {
  const w = (q.toLowerCase().match(/[\p{L}\p{N}]{2,}/gu) || []).slice(0, 24);
  return w.length ? w.map((x) => `"${x}"`).join(' OR ') : null;
};

export async function saveMemory(userId, { content, kind = 'fact', importance = 0.5 }) {
  content = String(content).trim().slice(0, 1000);
  if (!content) return null;
  importance = Math.max(0, Math.min(1, +importance || 0.5));
  const [vec] = (await embed([content])) || [];
  const t = now();
  if (vec) {
    const rows = db.prepare('SELECT id, embedding, importance FROM memories WHERE user_id=? AND embedding IS NOT NULL').all(userId);
    let best = null, bs = 0;
    for (const r of rows) { const s = cosine(vec, fromBuf(r.embedding)); if (s > bs) { bs = s; best = r; } }
    if (best && bs >= DUP_SIM) {
      db.prepare('UPDATE memories SET content=?, kind=?, importance=?, embedding=?, updated_at=? WHERE id=?')
        .run(content, kind, Math.max(importance, best.importance), toBuf(vec), t, best.id);
      db.prepare('DELETE FROM memories_fts WHERE rowid=?').run(best.id);
      db.prepare('INSERT INTO memories_fts(rowid, content) VALUES (?,?)').run(best.id, content);
      return best.id;
    }
  }
  const id = db.prepare('INSERT INTO memories(user_id,content,kind,importance,embedding,created_at,updated_at) VALUES (?,?,?,?,?,?,?)')
    .run(userId, content, kind, importance, vec ? toBuf(vec) : null, t, t).lastInsertRowid;
  db.prepare('INSERT INTO memories_fts(rowid, content) VALUES (?,?)').run(id, content);
  prune(userId);
  return Number(id);
}

export function forgetMemory(userId, id) {
  const r = db.prepare('DELETE FROM memories WHERE id=? AND user_id=?').run(id, userId);
  if (r.changes) db.prepare('DELETE FROM memories_fts WHERE rowid=?').run(id);
  return r.changes > 0;
}

function prune(userId) {
  const n = db.prepare('SELECT COUNT(*) c FROM memories WHERE user_id=?').get(userId).c;
  if (n <= MEM_MAX) return;
  const t = now();
  const rows = db.prepare('SELECT id, importance, uses, updated_at, last_used FROM memories WHERE user_id=?').all(userId);
  const score = (r) => {
    const days = (t - (r.last_used || r.updated_at)) / 864e5;
    return r.importance * Math.exp(-days / 120) + Math.min(r.uses, 10) * 0.02;
  };
  rows.sort((a, b) => score(a) - score(b));
  for (const r of rows.slice(0, n - MEM_MAX + 30)) forgetMemory(userId, r.id);
}

export async function searchMemories(userId, query, limit = 8, { noEmbed = false } = {}) {
  const K = 60;
  const rank = new Map();
  const add = (id, i) => rank.set(id, (rank.get(id) || 0) + 1 / (K + i));
  const q = ftsQuery(query);
  if (q) {
    try {
      db.prepare(`SELECT m.id FROM memories_fts f JOIN memories m ON m.id=f.rowid
        WHERE memories_fts MATCH ? AND m.user_id=? ORDER BY bm25(memories_fts) LIMIT 20`)
        .all(q, userId).forEach((r, i) => add(r.id, i));
    } catch {}
  }
  // эмбеддинг — сетевой вызов (+0,3–0,6 с до ответа): нужен, только если у пользователя есть векторные воспоминания и словарный поиск ничего не нашёл
  const needVec = !noEmbed && rank.size < 2 && !!db.prepare('SELECT 1 FROM memories WHERE user_id=? AND embedding IS NOT NULL LIMIT 1').get(userId);
  const [vec] = needVec ? ((await Promise.race([embed([query]), new Promise((r) => setTimeout(() => r(null), 450))])) || []) : [];
  if (vec) {
    db.prepare('SELECT id, embedding FROM memories WHERE user_id=? AND embedding IS NOT NULL').all(userId)
      .map((r) => ({ id: r.id, s: cosine(vec, fromBuf(r.embedding)) }))
      .filter((r) => r.s > 0.55).sort((a, b) => b.s - a.s).slice(0, 20)
      .forEach((r, i) => add(r.id, i));
  }
  const ids = [...rank.entries()].sort((a, b) => b[1] - a[1]).slice(0, limit).map(([id]) => id);
  if (!ids.length) return [];
  const rows = db.prepare(`SELECT id, content, kind, importance FROM memories WHERE id IN (${ids.map(() => '?').join(',')})`).all(...ids);
  const t = now();
  db.prepare(`UPDATE memories SET uses=uses+1, last_used=? WHERE id IN (${ids.map(() => '?').join(',')})`).run(t, ...ids);
  return ids.map((id) => rows.find((r) => r.id === id)).filter(Boolean);
}

export function coreMemories(userId, limit = 6) {
  return db.prepare("SELECT id, content, kind, importance FROM memories WHERE user_id=? AND kind IN ('profile','preference') AND importance>=0.85 ORDER BY importance DESC, updated_at DESC LIMIT ?").all(userId, limit);
}

export function listMemories(userId) {
  return db.prepare('SELECT id, content, kind, importance, updated_at FROM memories WHERE user_id=? ORDER BY updated_at DESC LIMIT 500').all(userId);
}

/** Фоновое извлечение воспоминаний после хода агента. */
export async function extractMemories(userId, exchange) {
  try {
    const out = await chatOnce([
      { role: 'system', content:
`Ты строгий модуль долговременной памяти ИИ-агента. Почти всегда ответ — пустой список.
Сохраняй ТОЛЬКО: (а) явные просьбы пользователя «запомни…»; (б) устойчивые личные факты и предпочтения (имя, язык общения, стиль ответов, основной стек).
КАТЕГОРИЧЕСКИ НЕ сохраняй: что агент делал в этой сессии, состояние/настройки серверов, развёртывания, боты, разовые задачи и инструкции («не разворачивай», «запусти один раз»), содержимое файлов, URL, секреты, догадки.
Не сохраняй ничего, что может быть воспринято как разрешение или инструкция что-то делать. Максимум 2 пункта, importance не ниже 0.7, одно самодостаточное предложение на языке пользователя.
Верни JSON: {"memories":[{"content":"...","kind":"profile|preference|fact","importance":0.7-1.0}]}. Если нечего — {"memories":[]}.` },
      { role: 'user', content: exchange.slice(0, 12000) },
    ], { json: true });
    const j = parseJson(out);
    for (const m of (j?.memories || []).filter((x) => (+x.importance || 0) >= 0.7).slice(0, 2)) await saveMemory(userId, m);
  } catch (e) { console.error('memory extract failed:', e.message); }
}
