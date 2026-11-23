// Тест-стенд агента: гоняет реальный startRun с живой моделью, считает шаги/инструменты/время и проверяет результат.
// Запуск: DATA_DIR=/tmp/x/data WORKSPACES_DIR=/tmp/x/ws node --env-file=.env test/harness.mjs [code|chat|all] [фильтр-id]
import fs from 'node:fs';
import path from 'node:path';
import { db, now } from '../src/db.js';
import { startRun, runs } from '../src/agent.js';
import { codeDir, workspaceOf } from '../src/workspace.js';

export function mkUser(email = 'tester@example.com', role = 'owner') {
  let u = db.prepare('SELECT * FROM users WHERE email=?').get(email);
  if (!u) { const id = db.prepare('INSERT INTO users(email,name,role,created_at) VALUES (?,?,?,?)').run(email, 'Тестер', role, now()).lastInsertRowid; u = db.prepare('SELECT * FROM users WHERE id=?').get(id); }
  return u;
}
export function mkConv(user, mode) {
  const id = db.prepare('INSERT INTO conversations(user_id,title,mode,created_at,updated_at) VALUES (?,?,?,?,?)').run(user.id, 'Новый чат', mode, now(), now()).lastInsertRowid;
  return db.prepare('SELECT * FROM conversations WHERE id=?').get(id);
}
export function runOnce(user, conv, text, opts = {}) {
  return new Promise((resolve) => {
    const t0 = Date.now(); const tools = []; let firstDelta = 0, err = null;
    const run = startRun(user, conv, text, null, opts);
    run.emitter.on('event', (e) => {
      if (e.type === 'delta' && !firstDelta) firstDelta = Date.now() - t0;
      if (e.type === 'message' && e.message.role === 'assistant' && e.message.toolCalls) for (const c of e.message.toolCalls) tools.push({ name: c.name, args: c.args });
      if (e.type === 'error') err = e.error;
      if (e.type === 'done' || e.type === 'error') {
        const msgs = db.prepare('SELECT * FROM messages WHERE conv_id=? ORDER BY id').all(conv.id);
        const finals = msgs.filter((m) => m.role === 'assistant' && m.content && !m.tool_calls);
        const toolMsgs = msgs.filter((m) => m.role === 'tool');
        setTimeout(() => resolve({ ms: Date.now() - t0, firstDelta, tools, steps: msgs.filter((m) => m.role === 'assistant' && m.tool_calls).length + 1, answer: finals.at(-1)?.content || '', toolResults: toolMsgs.map((m) => ({ name: m.tool_name, out: m.content })), err }), 50);
      }
    });
  });
}
export { codeDir, workspaceOf, runs, db };
