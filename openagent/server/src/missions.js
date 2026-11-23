// Миссии: долгосрочные цели, над которыми агент работает САМ — по шагам, по расписанию, с заметками о прогрессе — и сообщает, когда готово или нужен вы.
import { db, now } from './db.js';

export function missionPrompt(id) {
  const m = db.prepare('SELECT * FROM missions WHERE id=?').get(id);
  if (!m) return null;
  return `[МИССИЯ #${m.id}] Ты автономно ведёшь долгосрочную цель пользователя.
Цель: ${m.goal}
Прогресс (твои прошлые заметки):
${m.notes || '(пока ничего не сделано)'}
Выполнено шагов: ${m.steps}.

Сделай следующий полезный шаг доступными инструментами (поиск, чтение страниц, почта, коннекторы), не повторяя уже сделанное. В КОНЦЕ обязательно вызови mission_update{id:${m.id}, note:"что сделано и что дальше", status:"active|done|blocked"}:
- active — работа продолжается (в note: следующий шаг);
- done — цель достигнута (в note: итоговый результат для пользователя, коротко и по делу);
- blocked — нужен ввод или решение пользователя (в note: один конкретный вопрос).
Ничего не публикуй, не отправляй сообщения и не трать деньги, если это прямо не разрешено в цели.`;
}

export function createMission(user, a) {
  const goal = String(a.goal || '').trim().slice(0, 600);
  if (!goal) return 'Ошибка: нужна цель (goal)';
  if (db.prepare("SELECT COUNT(*) n FROM missions WHERE user_id=? AND status='active'").get(user.id).n >= 5) return 'Уже идёт 5 миссий — сначала завершите или поставьте на паузу одну из них';
  const every = Math.min(Math.max(+a.check_every_minutes || 60, 15), 10080);
  const t = now();
  const id = Number(db.prepare('INSERT INTO missions(user_id,goal,every_min,created_at,updated_at) VALUES (?,?,?,?,?)').run(user.id, goal, every, t, t).lastInsertRowid);
  db.prepare('INSERT INTO schedules(user_id,name,prompt,mode,every_min,next_run,created_at,mission_id) VALUES (?,?,?,?,?,?,?,?)').run(user.id, `Миссия: ${goal.slice(0, 40)}`, '(миссия)', 'chat', every, t + 60e3, t, id);
  return `Миссия #${id} запущена: «${goal.slice(0, 80)}». Первый шаг через минуту, дальше каждые ${every >= 60 ? Math.round(every / 60) + ' ч' : every + ' мин'}. Сообщу, когда будет готово или понадобится ваш ответ.`;
}

export function updateMission(user, a) {
  const m = db.prepare('SELECT * FROM missions WHERE id=? AND user_id=?').get(+a.id, user.id);
  if (!m) return 'Миссия не найдена';
  const status = ['active', 'done', 'blocked', 'paused'].includes(a.status) ? a.status : 'active';
  const line = a.note ? `[${new Date().toISOString().slice(0, 16).replace('T', ' ')}] ${String(a.note).slice(0, 600)}` : '';
  const notes = (m.notes ? m.notes + '\n' : '') + line;
  db.prepare('UPDATE missions SET status=?, notes=?, steps=steps+1, updated_at=? WHERE id=?').run(status, notes.slice(-3500), now(), m.id);
  if (status !== 'active') db.prepare('UPDATE schedules SET enabled=0, next_run=NULL WHERE mission_id=?').run(m.id);
  return `Миссия #${m.id}: ${status}`;
}

export function setMissionStatus(uid, id, status) {
  const m = db.prepare('SELECT * FROM missions WHERE id=? AND user_id=?').get(+id, uid);
  if (!m) return false;
  db.prepare('UPDATE missions SET status=?, updated_at=? WHERE id=?').run(status, now(), m.id);
  if (status === 'active') db.prepare('UPDATE schedules SET enabled=1, next_run=? WHERE mission_id=?').run(now() + 60e3, m.id);
  else db.prepare('UPDATE schedules SET enabled=0, next_run=NULL WHERE mission_id=?').run(m.id);
  return true;
}
export function deleteMission(uid, id) {
  const m = db.prepare('SELECT id FROM missions WHERE id=? AND user_id=?').get(+id, uid);
  if (!m) return false;
  db.prepare('DELETE FROM schedules WHERE mission_id=?').run(m.id); db.prepare('DELETE FROM missions WHERE id=?').run(m.id);
  return true;
}
export const listMissions = (uid) => db.prepare(`SELECT id, goal, status, notes, every_min AS everyMin, steps, created_at AS createdAt, updated_at AS updatedAt FROM missions WHERE user_id=? ORDER BY (status='active') DESC, updated_at DESC`).all(uid);
export function missionsText(uid) {
  const l = listMissions(uid);
  return l.length ? l.map((m) => `#${m.id} [${m.status}] ${m.goal.slice(0, 90)} · шагов ${m.steps}${m.notes ? ' · ' + m.notes.split('\n').pop().slice(0, 120) : ''}`).join('\n') : 'Миссий нет';
}
