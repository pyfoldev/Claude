// Голосовой режим через Deepgram Voice Agent: распознавание (nova-3) + мозг (Claude Haiku 4.5) + голос (Flux «Владимир») в ОДНОМ потоке.
// Приложение шлёт PCM 16 кГц (бинарно) и получает PCM 24 кГц (бинарно) + JSON-события:
//   сервер → app: ready | state{state: listening|thinking|speaking} | user{text} | agent{text} | flush | tool{name} | phone{id,args} | status{text} | error{message} | closed
//   app → сервер: бинарный PCM | {t:'text',text} | {t:'interrupt'} | {t:'mute',on} | {t:'end'} | {t:'phone_result',id,text}
// Тяжёлые вещи Haiku делегирует функцией run_task — туда уходит полный агент OpenAgent (инструменты, поиск, файлы, код).
import { WebSocket } from 'ws';
import { config } from './config.js';
import { db, now } from './db.js';
import { coreMemories } from './memory.js';
import { startRun, phoneCall, phoneResult, runs } from './agent.js';
import { runTool, voiceFunction } from './tools.js';
import { workspaceOf } from './workspace.js';
import { phoneFast, phoneModelEnabled } from './phoneModel.js';

const DG_AGENT = 'wss://agent.deepgram.com/v1/agent/converse';
const MAX_SESSION_MS = 30 * 60 * 1000;
const FAST_TOOLS = ['web_search', 'lookup', 'calculate', 'phone', 'tasks', 'memory_save'];   // выполняются прямо на сервере, ~1 с

const clean = (s) => String(s || '').replace(/[*_`#>]+/g, '').replace(/\s+/g, ' ').trim();   // на случай, если модель всё же отдаст markdown

export function voicePrompt(user, mems) {
  let pr = null; try { pr = user.profile ? JSON.parse(user.profile) : null; } catch {}
  const bits = pr ? [pr.name && `зовут ${pr.name}`, pr.city && `город: ${pr.city}`, pr.job && `занятие: ${pr.job}`, pr.address && `обращение на «${pr.address}»`].filter(Boolean) : [];
  return [
    'Ты — OpenAgent, голосовой личный агент. Это живой телефонный разговор: твои слова зачитывают вслух голосом.',
    'СТИЛЬ: 1–2 коротких предложения, по-человечески, на языке собеседника. Без markdown, списков, эмодзи, ссылок, адресов и кода — всё это нельзя произнести. Числа и единицы пиши так, как их говорят. Не начинай с «конечно» и «хорошо». Не повторяй вопрос.',
    'ДЕЙСТВУЙ САМ: если понятно, что нужно, — делай, не переспрашивай очевидное. Уточняй только когда без ответа нельзя действовать, и ровно одним вопросом.',
    'ИНСТРУМЕНТЫ: быстрые — web_search (свежие факты), lookup (погода/курсы/википедия/адреса), calculate, phone (будильник, таймер, приложения, фонарик, громкость на телефоне пользователя), tasks (список дел), memory_save (запомнить). Всё сложное и долгое — функция run_task: работа с интернетом в несколько шагов, файлы, документы, графики, код, сервер, почта, расписания. Перед вызовом run_task (и web_search) скажи ОДНУ короткую фразу вроде «Секунду, посмотрю». Не выдумывай факты, цифры, погоду и новости — бери из инструментов. Результат инструмента перескажи кратко и по сути.',
    'Если собеседник перебил — замолчи и слушай. Если не расслышал — переспроси коротко.',
    user.instructions ? `Инструкции пользователя: ${String(user.instructions).slice(0, 500)}` : '',
    bits.length ? `О собеседнике: ${bits.join('; ')}.` : '',
    mems.length ? `Что известно о нём:\n${mems.map((m) => '- ' + String(m.content).slice(0, 200)).join('\n')}` : '',
    `Сегодня ${new Date().toISOString().slice(0, 10)}.`,
  ].filter(Boolean).join('\n');
}

export function buildSettings(user, { lang = 'ru', history = [], greeting = '' } = {}) {
  const va = config.voiceAgent;
  const mems = (() => { try { return coreMemories(user.id, 5); } catch { return []; } })();
  const fns = FAST_TOOLS.map(voiceFunction).filter(Boolean);
  fns.push({
    name: 'run_task',
    description: 'Поручить задачу полноценному агенту OpenAgent (интернет в несколько шагов, файлы и документы, графики, код, сервер, почта, расписания). Вернёт итог. task — полная самостоятельная формулировка со всеми деталями из разговора. code=true — для работы с файлами проекта/кодом/сервером (только владелец).',
    parameters: { type: 'object', properties: { task: { type: 'string' }, code: { type: 'boolean' } }, required: ['task'] },
  });
  const l = String(lang || 'ru').toLowerCase().slice(0, 5);
  const multi = l === 'auto' || l === 'multi';
  return {
    type: 'Settings',
    audio: { input: { encoding: 'linear16', sample_rate: 16000 }, output: { encoding: 'linear16', sample_rate: 24000, container: 'none' } },
    agent: {
      ...(multi ? {} : { language: l }),
      listen: { provider: { type: 'deepgram', model: va.listenModel, language: multi ? 'multi' : l } },
      think: { provider: { type: va.thinkProvider, model: va.thinkModel, temperature: 0.4 }, prompt: voicePrompt(user, mems), functions: fns },
      speak: { provider: { type: 'deepgram', model: va.speakModel } },
      ...(history.length ? { context: { messages: history.map((m) => ({ type: 'History', role: m.role, content: m.content })) } } : {}),
      ...(greeting ? { greeting } : {}),
    },
  };
}

function ensureVoiceConv(user, id, title, mode = 'chat') {
  let c = id ? db.prepare('SELECT * FROM conversations WHERE id=? AND user_id=?').get(+id, user.id) : null;
  if (!c) {
    const cid = db.prepare('INSERT INTO conversations(user_id,title,mode,created_at,updated_at) VALUES (?,?,?,?,?)').run(user.id, title, mode, now(), now()).lastInsertRowid;
    c = db.prepare('SELECT * FROM conversations WHERE id=?').get(cid);
  }
  return c;
}
const saveMsg = (convId, role, content) => {
  db.prepare('INSERT INTO messages(conv_id,role,content,created_at) VALUES (?,?,?,?)').run(convId, role, content, now());
  db.prepare('UPDATE conversations SET updated_at=? WHERE id=?').run(now(), convId);
};

export function voiceAgentSession(ws, user, params) {
  const send = (o) => { if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(o)); };
  if (!config.deepgram.apiKey || !config.voiceAgent.enabled) { send({ t: 'error', message: 'Голосовой агент недоступен (нет DEEPGRAM_API_KEY)' }); return ws.close(); }
  const lang = params.get('lang') || 'ru';
  const conv = ensureVoiceConv(user, params.get('conv'), 'Голосовой разговор');
  const history = db.prepare("SELECT role, content FROM messages WHERE conv_id=? AND role IN ('user','assistant') AND content!='' AND tool_calls IS NULL ORDER BY id DESC LIMIT 8").all(conv.id).reverse();
  let taskConv = null;
  // Быстрый путь: малая модель получает каждую распознанную фразу сразу, не дожидаясь Haiku; если уверена — выполняет команду телефону сама.
  // Позже Haiku может вызвать `phone` с тем же действием — повторно не выполняем, отдаём ему готовый результат.
  const done = new Map(); let pendingFast = null;
  const BAD = /^(Нет ответа от телефона|Нужно подтверждение|Ошибка|Управление телефоном недоступно|Нужна служба доступности|Нужно разрешение)/;
  const runPhone = (a, text) => runTool(user, 'phone', a, { cwd: workspaceOf(user.id), autonomy: 'ask', userText: text, attach() {}, onOutput() {}, endTurn() {}, signal: AbortSignal.timeout(30000), phone: (x) => phoneCall(user.id, (type, data) => send({ t: type, ...data }), x) });
  const fastTry = async (text) => {
    const fast = await phoneFast(text); if (!fast) return null;
    send({ t: 'tool', name: 'phone_fast' });
    const res = [];
    for (const a of fast.actions) {
      const r = String(await runPhone(a, text)); res.push(r);
      if (!BAD.test(r)) done.set(a.action, { r, at: Date.now() });   // ключ — тип действия: повтор от Haiku с другими параметрами тоже не выполняем
    }
    return res;
  };
  const t0 = Date.now();
  let ready = false, dropOut = false, muted = false, closed = false;
  const queue = [];
  const up = new WebSocket(DG_AGENT, { headers: { Authorization: `Token ${config.deepgram.apiKey}` }, handshakeTimeout: 8000 });
  const upSend = (o) => { if (up.readyState === WebSocket.OPEN) up.send(JSON.stringify(o)); };
  const close = (why) => { if (closed) return; closed = true; send({ t: 'closed', reason: why || '' }); try { up.close(); } catch {} try { ws.close(); } catch {} clearInterval(keep); clearTimeout(cap); };

  up.on('open', () => upSend(buildSettings(user, { lang, history })));
  up.on('unexpected-response', (_q, res) => {
    res.resume();
    send({ t: 'error', message: res.statusCode === 401 || res.statusCode === 403 ? 'Deepgram: неверный ключ или нет доступа к Voice Agent' : res.statusCode === 402 ? 'Deepgram: закончился баланс' : `Deepgram Voice Agent: HTTP ${res.statusCode}` });
    close('upstream');
  });
  up.on('error', (e) => { if (!ready) { send({ t: 'error', message: `Нет связи с Deepgram: ${e.message}` }); close('upstream'); } });
  up.on('close', () => close('upstream-closed'));

  async function onFunction(f) {
    let args = {}; try { args = JSON.parse(f.arguments || '{}'); } catch {}
    send({ t: 'tool', name: f.name });
    let out;
    try {
      if (f.name === 'phone' && pendingFast) await Promise.race([pendingFast, new Promise((r) => setTimeout(r, 2000))]);
      const ALIAS = { open: 'open_app', launch: 'open_app', send_message: 'message', send: 'message', play_music: 'music_play' };
      const dup = f.name === 'phone' ? done.get(ALIAS[args.action] || args.action) : null;   // тот же тип действия в этой реплике уже выполнен малой моделью
      if (dup && Date.now() - dup.at < 30000) out = `Уже выполнено (повторно не запускаю): ${dup.r}. Ничего больше не делай, просто коротко подтверди пользователю.`;
      else if (f.name === 'run_task') out = await runTask(args);
      else if (FAST_TOOLS.includes(f.name)) {
        out = await runTool(user, f.name, args, {
          cwd: workspaceOf(user.id), autonomy: 'auto', userText: '', attach() {}, onOutput() {}, endTurn() {}, signal: AbortSignal.timeout(60000),
          phone: (a) => phoneCall(user.id, (type, data) => send({ t: type, ...data }), a),
        });
      } else out = `Неизвестная функция ${f.name}`;
    } catch (e) { out = `Ошибка: ${e.message}`; }
    upSend({ type: 'FunctionCallResponse', id: f.id, name: f.name, content: String(out).slice(0, 3000) });
  }

  function runTask(args) {
    return new Promise((resolve) => {
      const task = String(args.task || '').trim();
      if (!task) return resolve('Ошибка: пустая задача');
      taskConv ||= ensureVoiceConv(user, null, 'Голос: задачи', args.code && user.role === 'owner' ? 'code' : 'chat');
      if (runs.has(taskConv.id)) return resolve('Предыдущая задача ещё выполняется — подожди или скажи пользователю, что нужно немного времени.');
      let run;
      try { run = startRun(user, taskConv, task + '\n\n[Результат зачитают голосом: итог 1–3 коротких предложения, без markdown и ссылок.]', null, { effort: 'auto' }); }
      catch (e) { return resolve(`Ошибка: ${e.message}`); }
      const timer = setTimeout(() => { try { run.ac.abort(); } catch {} }, 150000);
      run.emitter.on('event', (e) => {
        if (e.type === 'phone') send({ t: 'phone', id: e.id, args: e.args });
        else if (e.type === 'status' && e.text) send({ t: 'status', text: e.text });
        else if (e.type === 'done' || e.type === 'error') {
          clearTimeout(timer);
          setTimeout(() => {
            const r = db.prepare("SELECT content FROM messages WHERE conv_id=? AND role='assistant' AND content!='' AND tool_calls IS NULL ORDER BY id DESC LIMIT 1").get(taskConv.id);
            const att = db.prepare("SELECT 1 FROM messages WHERE conv_id=? AND attachments IS NOT NULL ORDER BY id DESC LIMIT 1").get(taskConv.id);
            resolve(clean(r?.content || e.error || 'Готово').slice(0, 1200) + (att ? ' (файл или картинка отправлены в чат «Голос: задачи»)' : ''));
          }, 30);
        }
      });
    });
  }

  up.on('message', (data, isBinary) => {
    if (isBinary) { if (!dropOut && !closed) ws.readyState === WebSocket.OPEN && ws.send(data, { binary: true }); return; }
    let j; try { j = JSON.parse(data.toString()); } catch { return; }
    switch (j.type) {
      case 'SettingsApplied': ready = true; send({ t: 'ready', ms: Date.now() - t0, think: config.voiceAgent.thinkModel, voice: config.voiceAgent.speakModel }); for (const b of queue.splice(0)) up.send(b); break;
      case 'UserStartedSpeaking': send({ t: 'flush' }); send({ t: 'state', state: 'listening' }); break;
      case 'AgentThinking': send({ t: 'state', state: 'thinking' }); break;
      case 'AgentStartedSpeaking': dropOut = false; send({ t: 'state', state: 'speaking' }); break;
      case 'AgentAudioDone': send({ t: 'state', state: 'listening' }); break;
      case 'ConversationText': {
        const text = clean(j.content); if (!text) break;
        if (j.role === 'user') { send({ t: 'user', text }); saveMsg(conv.id, 'user', text); done.clear(); pendingFast = null; if (phoneModelEnabled()) pendingFast = fastTry(text).catch(() => null); }   // новая реплика — новая «память» выполненного
        else { send({ t: 'agent', text }); saveMsg(conv.id, 'assistant', text); }
        break;
      }
      case 'FunctionCallRequest': for (const f of j.functions || []) if (f.client_side !== false) onFunction(f); break;
      case 'Error': send({ t: 'error', message: String(j.description || j.message || 'ошибка голосового агента').slice(0, 300), code: j.code }); break;
      case 'Warning': console.warn('voice-agent warning', j.description || j.message); break;
      default: break;
    }
  });

  ws.on('message', (data, isBinary) => {
    if (isBinary) {
      if (muted) return;
      const b = Buffer.isBuffer(data) ? data : Buffer.from(data);
      if (ready) { if (up.readyState === WebSocket.OPEN) up.send(b); } else if (queue.length < 300) queue.push(b);
      return;
    }
    let m; try { m = JSON.parse(data.toString()); } catch { return; }
    if (m.t === 'text' && clean(m.text)) { dropOut = false; upSend({ type: 'InjectUserMessage', content: String(m.text).slice(0, 2000) }); }
    else if (m.t === 'interrupt') { dropOut = true; send({ t: 'flush' }); send({ t: 'state', state: 'listening' }); }
    else if (m.t === 'mute') muted = !!m.on;
    else if (m.t === 'phone_result') phoneResult(user.id, String(m.id || ''), m.text);
    else if (m.t === 'end') close('client');
  });
  ws.on('close', () => close('client'));
  ws.on('error', () => close('client'));
  const keep = setInterval(() => upSend({ type: 'KeepAlive' }), 8000); keep.unref?.();
  const cap = setTimeout(() => close('limit'), MAX_SESSION_MS); cap.unref?.();
}
