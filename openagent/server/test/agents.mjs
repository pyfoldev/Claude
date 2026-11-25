// Агенты и коннекторы без модели и сети: создание, расписание, выдача инструментов, запреты на запись, главный агент.
import { mkUser } from './harness.mjs';
import { runTool, toolDefs } from '../src/tools.js';
import { db } from '../src/db.js';
import { saveAgent, listAgents, team, agentSystemBlock, getAgent, allowSet } from '../src/agents.js';
import { saveCreds, catalog, connectedIds } from '../src/integrations.js';

const user = mkUser('agents@example.com', 'owner');
let fail = 0; const ok = (name, cond, info = '') => { console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${cond ? '' : ' → ' + info}`); if (!cond) fail++; };
const names = (defs) => defs.map((d) => d.function.name);
let calls = []; globalThis.fetch = async (url, o = {}) => { calls.push({ url: String(url), method: o.method || 'GET' }); return new Response(JSON.stringify({ ok: true, result: [] }), { status: 200 }); };

ok('главный создаётся сам', listAgents(user.id).length === 1 && listAgents(user.id)[0].is_main === 1);
ok('каталог: 20 коннекторов, ничего не подключено', catalog(user.id).length === 22 && connectedIds(user.id).length === 0);
try { saveCreds(user.id, 'telegram', { bot_token: '' }); ok('пустой токен отклоняется', false); } catch (e) { ok('пустой токен отклоняется', /Заполните/.test(e.message), e.message); }
saveCreds(user.id, 'telegram', { bot_token: '123:abc', chat_id: '42' }); saveCreds(user.id, 'todoist', { token: 'tdtok' });
const cat = catalog(user.id).find((c) => c.id === 'telegram');
ok('секреты не отдаются клиенту', cat.fields.find((f) => f.k === 'bot_token').value === '••••••' && cat.fields.find((f) => f.k === 'chat_id').value === '42');
saveCreds(user.id, 'telegram', { bot_token: '••••••', chat_id: '43' });
ok('звёздочки сохраняют старый секрет', JSON.parse(db.prepare("SELECT creds FROM integrations WHERE user_id=? AND connector='telegram'").get(user.id).creds).bot_token === '123:abc');

// инструменты в обычном чате: по упоминанию
ok('без упоминания коннекторов нет', !names(toolDefs(user, 'chat', { text: 'привет, как дела' })).some((n) => n.startsWith('int_')));
ok('упомянули Telegram — его инструменты есть', names(toolDefs(user, 'chat', { text: 'напиши мне в телеграм' })).includes('int_telegram_send_message'));
ok('обычный чат без команды: agent_* нет', !names(toolDefs(user, 'chat', { text: 'привет' })).includes('agent_ask'));
ok('«заведи агента» открывает agent_save', names(toolDefs(user, 'chat', { text: 'заведи агента для новостей' })).includes('agent_save'));

// создание агента инструментом
let out = await runTool(user, 'agent_save', { name: 'Новостник', emoji: '📰', instructions: 'Собирай новости', connectors: ['telegram'], every_minutes: 60 }, { autonomy: 'auto' });
ok('agent_save создаёт', /сохранён \(id \d+\)/.test(out), out);
const ag = team(user.id)[0];
ok('расписание выставлено', ag.every_min === 60 && ag.next_run > Date.now());
ok('у агента только свой коннектор', [...allowSet(ag)].join() === 'telegram');
ok('главный видит команду', /Новостник/.test(agentSystemBlock(user, null)) && /agent_ask/.test(agentSystemBlock(user, null)));
ok('обычный чат теперь получает agent_ask', names(toolDefs(user, 'chat', { text: 'привет' })).includes('agent_ask'));
const sub = names(toolDefs(user, 'chat', { automation: true, agent: ag, text: 'x' }));
ok('агенту: telegram есть, todoist нет, agent_note есть, agent_ask нет', sub.includes('int_telegram_send_message') && !sub.some((n) => n.startsWith('int_todoist')) && sub.includes('agent_note') && !sub.includes('agent_ask'), sub.join());
ok('блок агента содержит задачу', /Собирай новости/.test(agentSystemBlock(user, ag, { automation: true })) && /ЗАПРЕЩЕНЫ/.test(agentSystemBlock(user, ag, { automation: true })));

// запись: автономный без write_ok — отказ; чат без confirmed — отказ; с confirmed — идёт запрос
calls = [];
out = await runTool(user, 'int_telegram_send_message', { text: 'hi' }, { automation: true, agent: ag, autonomy: 'ask' });
ok('автономный агент без write_ok: отказ, запроса нет', /ОТКАЗАНО/.test(out) && !calls.length, out);
out = await runTool(user, 'int_telegram_send_message', { text: 'hi' }, { autonomy: 'ask' });
ok('чат: без confirmed — просит подтверждение', /ask_user/.test(out) && !calls.length, out);
out = await runTool(user, 'int_telegram_send_message', { text: 'hi', confirmed: true }, { autonomy: 'ask' });
ok('чат: с confirmed — отправляет', /Отправлено/.test(out) && calls.length === 1 && /sendMessage/.test(calls[0].url), out);
saveAgent(user.id, { writeOk: true }, ag.id);
calls = [];
out = await runTool(user, 'int_telegram_send_message', { text: 'hi' }, { automation: true, agent: getAgent(user.id, ag.id), autonomy: 'ask' });
ok('автономный с write_ok — отправляет', /Отправлено/.test(out) && calls.length === 1, out);
out = await runTool(user, 'int_todoist_list_tasks', {}, { automation: true, agent: getAgent(user.id, ag.id) });
ok('чужой коннектор агенту запрещён', /не разрешён/.test(out), out);
out = await runTool(user, 'int_github_list_issues', { repo: 'a/b' }, { autonomy: 'auto' });
ok('неподключённый коннектор — понятная ошибка', /не подключён/.test(out), out);

// agent_ask без обработчика, удаление
out = await runTool(user, 'agent_delete', { id: ag.id }, { autonomy: 'ask' });
ok('удаление требует подтверждения', /ОТКАЗАНО/.test(out), out);
out = await runTool(user, 'agent_delete', { id: ag.id, confirmed: true }, { autonomy: 'ask' });
ok('удаление с подтверждением', /удалён/.test(out) && team(user.id).length === 0, out);
out = await runTool(user, 'agent_note', { note: 'x' }, {});
ok('agent_note вне агента — понятный ответ', /только отдельному/.test(out), out);
console.log(fail ? `\n${fail} ПРОВАЛОВ` : '\nвсё прошло'); process.exit(fail ? 1 : 0);
