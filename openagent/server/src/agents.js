// Агенты: у каждого своя задача, свои коннекторы, расписание и память-заметки. Главный агент — это обычный чат: он знает «команду» и поручает работу профильным агентам.
import { db, now } from './db.js';
import { CONNECTORS, connectedIds } from './integrations.js';

db.exec(`CREATE TABLE IF NOT EXISTS agents (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, emoji TEXT NOT NULL DEFAULT '🤖', instructions TEXT NOT NULL DEFAULT '',
  is_main INTEGER NOT NULL DEFAULT 0, connectors TEXT, write_ok INTEGER NOT NULL DEFAULT 0,
  every_min INTEGER, next_run INTEGER, enabled INTEGER NOT NULL DEFAULT 1,
  notes TEXT NOT NULL DEFAULT '', last_run INTEGER, runs INTEGER NOT NULL DEFAULT 0, last_result TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
)`);
try { db.exec('ALTER TABLE conversations ADD COLUMN agent_id INTEGER'); } catch {}

export const MAIN_DEFAULT = 'Ты главный агент пользователя. Простое делаешь сам. Регулярное и узкое поручаешь профильным агентам из команды (agent_ask), недостающих создаёшь по просьбе (agent_save). Результаты собираешь в один короткий ответ.';

export const getAgent = (uid, id) => db.prepare('SELECT * FROM agents WHERE id=? AND user_id=?').get(+id, uid);
export function ensureMain(uid) {
  let m = db.prepare('SELECT * FROM agents WHERE user_id=? AND is_main=1').get(uid);
  if (!m) { const t = now(); const id = db.prepare('INSERT INTO agents(user_id,name,emoji,instructions,is_main,created_at) VALUES (?,?,?,?,1,?)').run(uid, 'Главный', '🧭', MAIN_DEFAULT, t).lastInsertRowid; m = db.prepare('SELECT * FROM agents WHERE id=?').get(id); }
  return m;
}
export const listAgents = (uid) => { ensureMain(uid); return db.prepare('SELECT * FROM agents WHERE user_id=? ORDER BY is_main DESC, id').all(uid); };
export const team = (uid) => db.prepare('SELECT * FROM agents WHERE user_id=? AND is_main=0 ORDER BY id').all(uid);
const parseConn = (a) => { if (!a.connectors) return null; try { const x = JSON.parse(a.connectors); return Array.isArray(x) ? x : null; } catch { return null; } };
/** Множество разрешённых коннекторов агента (null — все подключённые пользователем). */
export const allowSet = (a) => { const c = a && !a.is_main ? parseConn(a) : null; return c ? new Set(c) : null; };

export const publicAgent = (a) => ({ id: a.id, name: a.name, emoji: a.emoji, instructions: a.instructions, isMain: !!a.is_main, connectors: parseConn(a), writeOk: !!a.write_ok, everyMin: a.every_min, nextRun: a.next_run, enabled: !!a.enabled, notes: a.notes, lastRun: a.last_run, runs: a.runs, lastResult: a.last_result });

export function saveAgent(uid, b, id = null) {
  const cur = id ? getAgent(uid, id) : null;
  if (id && !cur) throw new Error('Агент не найден');
  const name = String(b.name ?? cur?.name ?? '').trim().slice(0, 40); if (!name) throw new Error('Нужно имя агента');
  if (!id && db.prepare('SELECT COUNT(*) n FROM agents WHERE user_id=?').get(uid).n >= 30) throw new Error('Не больше 30 агентов');
  const instructions = String(b.instructions ?? cur?.instructions ?? '').trim().slice(0, 4000);
  const emoji = String(b.emoji ?? cur?.emoji ?? '🤖').trim().slice(0, 4) || '🤖';
  let connectors = cur?.connectors ?? null;
  if ('connectors' in b) connectors = Array.isArray(b.connectors) && !b.connectors.includes('*') ? JSON.stringify(b.connectors.filter((x) => CONNECTORS.some((c) => c.id === x))) : null;
  const writeOk = 'writeOk' in b ? (b.writeOk ? 1 : 0) : cur?.write_ok || 0;
  let every = 'everyMin' in b || 'every_minutes' in b ? (+(b.everyMin ?? b.every_minutes) || null) : cur?.every_min ?? null;
  if (every) every = Math.min(Math.max(every, 5), 10080 * 4);
  const enabled = 'enabled' in b ? (b.enabled ? 1 : 0) : cur?.enabled ?? 1;
  const t = now();
  const next = every && enabled ? (cur?.every_min === every && cur?.next_run ? cur.next_run : t + every * 60e3) : null;
  if (cur) {
    db.prepare('UPDATE agents SET name=?,emoji=?,instructions=?,connectors=?,write_ok=?,every_min=?,next_run=?,enabled=? WHERE id=?').run(cur.is_main ? cur.name : name, emoji, instructions || cur.instructions, connectors, cur.is_main ? 0 : writeOk, cur.is_main ? cur.every_min : every, cur.is_main ? cur.next_run : next, enabled, cur.id);
    return getAgent(uid, cur.id);
  }
  const nid = db.prepare('INSERT INTO agents(user_id,name,emoji,instructions,connectors,write_ok,every_min,next_run,enabled,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)').run(uid, name, emoji, instructions, connectors, writeOk, every, next, enabled, t).lastInsertRowid;
  return getAgent(uid, nid);
}
export const deleteAgent = (uid, id) => db.prepare('DELETE FROM agents WHERE id=? AND user_id=? AND is_main=0').run(+id, uid).changes > 0;
export function agentNote(uid, id, note) {
  const a = getAgent(uid, id); if (!a) return 'Ошибка: агент не найден';
  const line = `[${new Date().toISOString().slice(0, 16).replace('T', ' ')}] ${String(note).slice(0, 500)}`;
  db.prepare('UPDATE agents SET notes=? WHERE id=?').run(((a.notes ? a.notes + '\n' : '') + line).slice(-3000), a.id);
  return 'Записано в память агента';
}
export function recordRun(id, result) { db.prepare('UPDATE agents SET last_run=?, runs=runs+1, last_result=? WHERE id=?').run(now(), String(result || '').slice(0, 1500), id); }

const connName = (id) => CONNECTORS.find((c) => c.id === id)?.name || id;
const describe = (a) => { const c = parseConn(a); return `id ${a.id} «${a.name}» ${a.emoji}: ${a.instructions.replace(/\s+/g, ' ').slice(0, 160)} [коннекторы: ${c ? (c.map(connName).join(', ') || 'нет') : 'все подключённые'}${a.every_min ? `; каждые ${a.every_min >= 60 ? Math.round(a.every_min / 60) + ' ч' : a.every_min + ' мин'}${a.enabled ? '' : ' (пауза)'}` : ''}]`; };
export function rosterText(uid) { const t = team(uid); return t.length ? t.slice(0, 20).map(describe).join('\n') : 'Агентов пока нет.'; }

/** Блок системного промпта: для отдельного агента — его задача/память; для обычного чата и главного — команда и правила поручений. */
export function agentSystemBlock(user, agent, { automation = false } = {}) {
  if (agent && !agent.is_main) {
    const c = parseConn(agent); const have = connectedIds(user.id).filter((x) => !c || c.includes(x)).map(connName);
    return `ТЫ — АГЕНТ «${agent.name}» ${agent.emoji}, отдельный агент пользователя со своей задачей.\nЗадача: ${agent.instructions || '(не задана — уточни у пользователя)'}\nКоннекторы агента: ${have.join(', ') || 'нет подключённых — используй веб-поиск и общие инструменты'}.${agent.notes ? `\nТвоя память между запусками (заметки):\n${agent.notes}` : ''}\nДержись своей задачи, не берись за чужое. Важное на будущее (что уже обработано, найденные id, договорённости) сохраняй через agent_note — только факты, коротко.${automation ? `\nЭто АВТОНОМНЫЙ запуск без пользователя: сделай работу и дай отчёт 3–6 строк — что сделал, что нашёл, что требует внимания человека. Если нечего сообщать — одна строка «Без изменений». Действия, меняющие данные или что-то отправляющие, ${agent.write_ok ? 'тебе разрешены, но только в рамках задачи' : 'тебе ЗАПРЕЩЕНЫ — опиши в отчёте, что предлагаешь сделать'}.` : ''}`;
  }
  const m = agent || db.prepare('SELECT * FROM agents WHERE user_id=? AND is_main=1').get(user.id);
  const t = team(user.id);
  const conns = connectedIds(user.id).map(connName);
  const parts = [];
  if (t.length || conns.length) parts.push(`ГЛАВНЫЙ АГЕНТ: ${m?.instructions || MAIN_DEFAULT}`);
  if (t.length) parts.push(`Команда агентов пользователя (поручай им через agent_ask{agent:id, task}, когда задача по их профилю; результат пересказывай кратко; не дублируй их работу сам):\n${rosterText(user.id)}`);
  if (conns.length) parts.push(`Подключённые коннекторы: ${conns.join(', ')} (их инструменты появляются, когда в запросе упомянут сервис).`);
  if (!t.length) parts.push('Если пользователь просит завести агента/ассистента для постоянной задачи — создай его через agent_save (имя, инструкция, нужные коннекторы, при необходимости every_minutes).');
  return parts.join('\n');
}

// ---- расписание ----
let starter = null;
export const setAgentStarter = (fn) => { starter = fn; };
/** Запуск агента в новом чате (виден в списке чатов как «🤖 Имя»). */
export function runAgentNow(agent, extra = '') {
  const user = db.prepare('SELECT * FROM users WHERE id=?').get(agent.user_id);
  if (!user || !starter) return null;
  const t = now();
  const id = db.prepare('INSERT INTO conversations(user_id,title,mode,created_at,updated_at,agent_id) VALUES (?,?,?,?,?,?)').run(user.id, `${agent.emoji} ${agent.name}`, 'chat', t, t, agent.id).lastInsertRowid;
  const conv = db.prepare('SELECT * FROM conversations WHERE id=?').get(id);
  db.prepare('UPDATE agents SET last_run=?, runs=runs+1 WHERE id=?').run(t, agent.id);
  try { starter(user, conv, `[Запуск агента «${agent.name}»]\n${extra || agent.instructions || 'Выполни свою задачу.'}`, { automation: true, everyMin: agent.every_min, agentId: agent.id }); } catch (e) { console.error('agent run', e.message); }
  return Number(id);
}
export function startAgentScheduler() {
  setInterval(() => {
    const due = db.prepare('SELECT * FROM agents WHERE enabled=1 AND is_main=0 AND every_min IS NOT NULL AND next_run IS NOT NULL AND next_run<=?').all(now());
    for (const a of due) { db.prepare('UPDATE agents SET next_run=? WHERE id=?').run(now() + a.every_min * 60e3, a.id); runAgentNow(a); }
  }, 20000);
}

/** Готовые шаблоны для быстрого создания. */
export const TEMPLATES = [
  { name: 'Дайджест новостей', emoji: '📰', instructions: 'Каждое утро собирай главные новости по темам пользователя (спроси у него темы при первом запуске и запомни через agent_note). Используй веб-поиск и RSS. Отчёт: 5–7 пунктов со ссылками.', connectors: [], everyMin: 1440 },
  { name: 'Секретарь почты', emoji: '📬', instructions: 'Проверяй почту, выделяй важное и срочное, коротко пересказывай, предлагай ответы. Письма не отправляй — только черновик в отчёте.', connectors: [], everyMin: 120 },
  { name: 'Охотник за ценами', emoji: '🏷️', instructions: 'Следи за ценой и наличием товаров, которые назовёт пользователь. Сравнивай с прошлыми значениями из заметок и сообщай, только если цена упала или товар появился.', connectors: [], everyMin: 360 },
  { name: 'Дежурный по GitHub', emoji: '🐙', instructions: 'Смотри новые issues и pull request в репозиториях пользователя, выделяй то, что требует реакции, и группируй по срочности.', connectors: ['github', 'gitlab', 'sentry'], everyMin: 180 },
  { name: 'Менеджер задач', emoji: '✅', instructions: 'Раз в день разбирай задачи из Todoist/Linear/Jira/Trello: что просрочено, что на сегодня, что можно отложить. Составь план дня.', connectors: ['todoist', 'linear', 'jira', 'trello', 'ical'], everyMin: 1440 },
  { name: 'Умный дом', emoji: '🏠', instructions: 'Следи за состоянием устройств Home Assistant, сообщай о необычном (открытые окна, свет без людей, высокая температура).', connectors: ['homeassistant', 'ntfy', 'telegram'], everyMin: 60 },
  { name: 'Финансовый обзор', emoji: '💳', instructions: 'Показывай баланс и последние платежи Stripe, курсы валют; выделяй резкие изменения.', connectors: ['stripe'], everyMin: 1440 },
  { name: 'Контент-наблюдатель', emoji: '▶️', instructions: 'Следи за новыми видео каналов YouTube из списка пользователя и коротко пересказывай, что вышло.', connectors: ['youtube'], everyMin: 720 },
];
