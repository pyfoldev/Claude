// Коннекторы: подключения к внешним сервисам по токену/ключу. Каждый коннектор — набор действий; подключённые превращаются в инструменты агента int_<коннектор>_<действие>.
// Действия, которые что-то меняют/отправляют (write: true), без разрешения не выполняются: в обычном чате — после «да» пользователя, у автономного агента — только если ему разрешена запись.
import { db, now } from './db.js';

db.exec(`CREATE TABLE IF NOT EXISTS integrations (
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, connector TEXT NOT NULL, creds TEXT NOT NULL, created_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, connector)
)`);

const S = { type: 'string' }, I = { type: 'integer' }, B = { type: 'boolean' };
const obj = (properties = {}, required = []) => ({ type: 'object', properties, required });
const trunc = (s, n = 6000) => { s = typeof s === 'string' ? s : JSON.stringify(s, null, 1); return s.length > n ? s.slice(0, n) + `\n[… обрезано ${s.length - n} симв.]` : s; };

/** HTTP-вызов с таймаутом; JSON — в объект, иначе текст. Ошибки HTTP — с началом тела ответа. */
export async function http(url, { method = 'GET', headers = {}, body, form, signal, raw } = {}) {
  const h = { 'User-Agent': 'OpenAgent/1.0', Accept: 'application/json', ...headers };
  let b = body;
  if (form) { b = new URLSearchParams(form).toString(); h['Content-Type'] = 'application/x-www-form-urlencoded'; }
  else if (body !== undefined && typeof body !== 'string') { b = JSON.stringify(body); h['Content-Type'] ||= 'application/json'; }
  const r = await fetch(url, { method, headers: h, body: b, signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(20000)]) : AbortSignal.timeout(20000) });
  const t = await r.text();
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${t.slice(0, 300)}`);
  if (raw) return t;
  try { return JSON.parse(t); } catch { return t; }
}
const bearer = (t) => ({ Authorization: `Bearer ${t}` });
const basic = (u, p) => ({ Authorization: 'Basic ' + Buffer.from(`${u}:${p}`).toString('base64') });
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== '')).toString();
const host = (u, def) => String(u || def).replace(/\/+$/, '').replace(/^(?!https?:\/\/)/, 'https://');

/** ICS → ближайшие события (без внешних библиотек: разворачиваем строки, берём DTSTART/SUMMARY/LOCATION, простые RRULE пропускаем). */
function parseIcs(text) {
  const src = text.replace(/\r?\n[ \t]/g, '');
  const out = [];
  for (const m of src.matchAll(/BEGIN:VEVENT([\s\S]*?)END:VEVENT/g)) {
    const g = (k) => (m[1].match(new RegExp(`^${k}[^:\\n]*:(.*)$`, 'm')) || [])[1]?.trim();
    const dt = g('DTSTART'); if (!dt) continue;
    const d = dt.replace(/^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2}))?(Z?)$/, (_, y, mo, da, h = '00', mi = '00', s = '00', z) => `${y}-${mo}-${da}T${h}:${mi}:${s}${z || ''}`);
    const t = Date.parse(d); if (!Number.isFinite(t)) continue;
    out.push({ t, title: (g('SUMMARY') || '(без названия)').replace(/\\,/g, ',').replace(/\\n/g, ' '), where: (g('LOCATION') || '').replace(/\\,/g, ','), allDay: !/T/.test(dt) });
  }
  return out;
}

const gql = (url, headers, query, variables, signal) => http(url, { method: 'POST', headers, body: { query, variables }, signal }).then((j) => { if (j.errors) throw new Error(j.errors.map((e) => e.message).join('; ').slice(0, 300)); return j.data; });

export const CONNECTORS = [
  { id: 'telegram', name: 'Telegram-бот', icon: '✈️', desc: 'Писать в Telegram от имени вашего бота и читать входящие', aliases: /telegram|телеграм|тг\b/i,
    fields: [{ k: 'bot_token', label: 'Токен бота', secret: true, hint: 'Создайте бота у @BotFather' }, { opt: true, k: 'chat_id', label: 'Chat ID по умолчанию', hint: 'Ваш числовой id (узнайте у @userinfobot)' }],
    actions: [
      { name: 'send_message', write: true, desc: 'Отправить сообщение в Telegram', params: obj({ text: S, chat_id: { type: 'string', description: 'если не указан — по умолчанию' } }, ['text']), run: (c, a, s) => http(`https://api.telegram.org/bot${c.bot_token}/sendMessage`, { method: 'POST', body: { chat_id: a.chat_id || c.chat_id, text: String(a.text).slice(0, 4000) }, signal: s }).then(() => 'Отправлено') },
      { name: 'get_updates', desc: 'Последние входящие сообщения боту', params: obj(), run: (c, a, s) => http(`https://api.telegram.org/bot${c.bot_token}/getUpdates?limit=15`, { signal: s }).then((j) => (j.result || []).map((u) => { const m = u.message || u.channel_post || {}; return `${m.from?.username || m.chat?.title || m.chat?.id}: ${m.text || '[не текст]'}`; }).join('\n') || 'Новых сообщений нет') },
    ] },
  { id: 'slack', name: 'Slack', icon: '💬', desc: 'Каналы Slack: читать историю и писать сообщения', aliases: /slack|слак/i,
    fields: [{ k: 'token', label: 'Bot token (xoxb-…)', secret: true, hint: 'api.slack.com/apps → OAuth & Permissions' }],
    actions: [
      { name: 'list_channels', desc: 'Список каналов', params: obj(), run: (c, a, s) => http('https://slack.com/api/conversations.list?limit=100&types=public_channel,private_channel', { headers: bearer(c.token), signal: s }).then((j) => { if (!j.ok) throw new Error(j.error); return j.channels.map((x) => `${x.name} (${x.id})`).join('\n'); }) },
      { name: 'history', desc: 'Последние сообщения канала', params: obj({ channel: { type: 'string', description: 'id канала (C…)' }, limit: I }, ['channel']), run: (c, a, s) => http(`https://slack.com/api/conversations.history?${qs({ channel: a.channel, limit: Math.min(+a.limit || 15, 40) })}`, { headers: bearer(c.token), signal: s }).then((j) => { if (!j.ok) throw new Error(j.error); return j.messages.map((m) => `${new Date(m.ts * 1000).toISOString().slice(5, 16)} ${m.user || m.bot_id || ''}: ${m.text}`).join('\n'); }) },
      { name: 'post_message', write: true, desc: 'Написать в канал', params: obj({ channel: S, text: S }, ['channel', 'text']), run: (c, a, s) => http('https://slack.com/api/chat.postMessage', { method: 'POST', headers: bearer(c.token), body: { channel: a.channel, text: a.text }, signal: s }).then((j) => { if (!j.ok) throw new Error(j.error); return 'Отправлено'; }) },
    ] },
  { id: 'discord', name: 'Discord (вебхук)', icon: '🎮', desc: 'Отправлять сообщения в канал Discord через вебхук', aliases: /discord|дискорд/i,
    fields: [{ k: 'webhook_url', label: 'Webhook URL', secret: true, hint: 'Настройки канала → Интеграции → Вебхуки' }],
    actions: [{ name: 'send', write: true, desc: 'Отправить сообщение в Discord', params: obj({ content: S }, ['content']), run: (c, a, s) => http(c.webhook_url, { method: 'POST', body: { content: String(a.content).slice(0, 1900) }, signal: s, raw: true }).then(() => 'Отправлено') }] },
  { id: 'github', name: 'GitHub', icon: '🐙', desc: 'Issues и pull request репозиториев, поиск кода', aliases: /github|гитхаб|issue|pull request|\bpr\b/i,
    fields: [{ k: 'token', label: 'Personal Access Token', secret: true, hint: 'github.com/settings/tokens' }],
    actions: [
      { name: 'list_issues', desc: 'Открытые issues репозитория', params: obj({ repo: { type: 'string', description: 'owner/name' }, state: { type: 'string', enum: ['open', 'closed', 'all'] } }, ['repo']), run: (c, a, s) => http(`https://api.github.com/repos/${a.repo}/issues?${qs({ state: a.state || 'open', per_page: 15 })}`, { headers: { ...bearer(c.token), Accept: 'application/vnd.github+json' }, signal: s }).then((j) => j.map((i) => `#${i.number} ${i.pull_request ? '[PR] ' : ''}${i.title} — ${i.user?.login} (${i.state})`).join('\n') || 'Пусто') },
      { name: 'create_issue', write: true, desc: 'Создать issue', params: obj({ repo: S, title: S, body: S }, ['repo', 'title']), run: (c, a, s) => http(`https://api.github.com/repos/${a.repo}/issues`, { method: 'POST', headers: { ...bearer(c.token), Accept: 'application/vnd.github+json' }, body: { title: a.title, body: a.body || '' }, signal: s }).then((j) => `Создано: ${j.html_url}`) },
      { name: 'search_code', desc: 'Поиск по коду на GitHub', params: obj({ query: S }, ['query']), run: (c, a, s) => http(`https://api.github.com/search/code?${qs({ q: a.query, per_page: 8 })}`, { headers: { ...bearer(c.token), Accept: 'application/vnd.github+json' }, signal: s }).then((j) => (j.items || []).map((i) => `${i.repository.full_name}: ${i.path}\n  ${i.html_url}`).join('\n') || 'Ничего') },
    ] },
  { id: 'gitlab', name: 'GitLab', icon: '🦊', desc: 'Issues и merge request проектов GitLab', aliases: /gitlab|гитлаб|merge request/i,
    fields: [{ k: 'token', label: 'Personal Access Token', secret: true }, { opt: true, k: 'base_url', label: 'Адрес (по умолчанию gitlab.com)', hint: 'https://gitlab.example.com' }],
    actions: [
      { name: 'list_issues', desc: 'Issues проекта', params: obj({ project: { type: 'string', description: 'id или group/name' }, state: { type: 'string', enum: ['opened', 'closed', 'all'] } }, ['project']), run: (c, a, s) => http(`${host(c.base_url, 'gitlab.com')}/api/v4/projects/${encodeURIComponent(a.project)}/issues?${qs({ state: a.state || 'opened', per_page: 15 })}`, { headers: { 'PRIVATE-TOKEN': c.token }, signal: s }).then((j) => j.map((i) => `#${i.iid} ${i.title} (${i.state})`).join('\n') || 'Пусто') },
      { name: 'list_merge_requests', desc: 'Merge request проекта', params: obj({ project: S }, ['project']), run: (c, a, s) => http(`${host(c.base_url, 'gitlab.com')}/api/v4/projects/${encodeURIComponent(a.project)}/merge_requests?state=opened&per_page=15`, { headers: { 'PRIVATE-TOKEN': c.token }, signal: s }).then((j) => j.map((i) => `!${i.iid} ${i.title} — ${i.author?.username}`).join('\n') || 'Пусто') },
      { name: 'create_issue', write: true, desc: 'Создать issue', params: obj({ project: S, title: S, description: S }, ['project', 'title']), run: (c, a, s) => http(`${host(c.base_url, 'gitlab.com')}/api/v4/projects/${encodeURIComponent(a.project)}/issues`, { method: 'POST', headers: { 'PRIVATE-TOKEN': c.token }, body: { title: a.title, description: a.description || '' }, signal: s }).then((j) => `Создано: ${j.web_url}`) },
    ] },
  { id: 'notion', name: 'Notion', icon: '📝', desc: 'Поиск и чтение страниц Notion, добавление записей в базы', aliases: /notion|ноушн|нотион/i,
    fields: [{ k: 'token', label: 'Internal integration token', secret: true, hint: 'notion.so/my-integrations; не забудьте дать интеграции доступ к страницам' }],
    actions: (() => { const H = (c) => ({ ...bearer(c.token), 'Notion-Version': '2022-06-28' }); const title = (p) => { const t = Object.values(p.properties || {}).find((x) => x.type === 'title'); return t?.title?.map((x) => x.plain_text).join('') || '(без названия)'; };
      return [
        { name: 'search', desc: 'Поиск страниц и баз по названию', params: obj({ query: S }, ['query']), run: (c, a, s) => http('https://api.notion.com/v1/search', { method: 'POST', headers: H(c), body: { query: a.query, page_size: 10 }, signal: s }).then((j) => j.results.map((p) => `${p.object === 'database' ? '[база] ' : ''}${p.object === 'database' ? p.title?.map((x) => x.plain_text).join('') : title(p)} — id ${p.id}`).join('\n') || 'Ничего') },
        { name: 'read_page', desc: 'Прочитать текст страницы', params: obj({ page_id: S }, ['page_id']), run: (c, a, s) => http(`https://api.notion.com/v1/blocks/${a.page_id}/children?page_size=100`, { headers: H(c), signal: s }).then((j) => j.results.map((b) => { const t = b[b.type]?.rich_text?.map((x) => x.plain_text).join(''); return t ? (b.type.startsWith('heading') ? '## ' : b.type.includes('list') ? '- ' : '') + t : ''; }).filter(Boolean).join('\n') || '(пусто)') },
        { name: 'add_to_database', write: true, desc: 'Добавить запись (страницу) в базу Notion', params: obj({ database_id: S, title: S, text: S }, ['database_id', 'title']), run: async (c, a, s) => { const db0 = await http(`https://api.notion.com/v1/databases/${a.database_id}`, { headers: H(c), signal: s }); const tk = Object.entries(db0.properties).find(([, v]) => v.type === 'title')?.[0] || 'Name'; const j = await http('https://api.notion.com/v1/pages', { method: 'POST', headers: H(c), body: { parent: { database_id: a.database_id }, properties: { [tk]: { title: [{ text: { content: a.title } }] } }, ...(a.text ? { children: [{ object: 'block', type: 'paragraph', paragraph: { rich_text: [{ text: { content: String(a.text).slice(0, 1900) } }] } }] } : {}) }, signal: s }); return `Создано: ${j.url}`; } },
      ]; })() },
  { id: 'linear', name: 'Linear', icon: '📐', desc: 'Задачи Linear: смотреть и создавать', aliases: /linear|линеар/i,
    fields: [{ k: 'api_key', label: 'API-ключ', secret: true, hint: 'Linear → Settings → API' }],
    actions: [
      { name: 'list_issues', desc: 'Мои/последние задачи', params: obj({ limit: I }), run: (c, a, s) => gql('https://api.linear.app/graphql', { Authorization: c.api_key }, 'query($n:Int){issues(first:$n,orderBy:updatedAt){nodes{identifier title state{name} assignee{name}}}}', { n: Math.min(+a.limit || 15, 40) }, s).then((d) => d.issues.nodes.map((i) => `${i.identifier} ${i.title} [${i.state?.name}] ${i.assignee?.name || ''}`).join('\n') || 'Пусто') },
      { name: 'list_teams', desc: 'Команды (нужны для создания задач)', params: obj(), run: (c, a, s) => gql('https://api.linear.app/graphql', { Authorization: c.api_key }, '{teams{nodes{id name key}}}', {}, s).then((d) => d.teams.nodes.map((t) => `${t.key} ${t.name} — id ${t.id}`).join('\n')) },
      { name: 'create_issue', write: true, desc: 'Создать задачу', params: obj({ team_id: S, title: S, description: S }, ['team_id', 'title']), run: (c, a, s) => gql('https://api.linear.app/graphql', { Authorization: c.api_key }, 'mutation($i:IssueCreateInput!){issueCreate(input:$i){issue{identifier url}}}', { i: { teamId: a.team_id, title: a.title, description: a.description || '' } }, s).then((d) => `Создано: ${d.issueCreate.issue.identifier} ${d.issueCreate.issue.url}`) },
    ] },
  { id: 'todoist', name: 'Todoist', icon: '✅', desc: 'Задачи Todoist: список, добавление, выполнение', aliases: /todoist|тудуист|задач[аиу]/i,
    fields: [{ k: 'token', label: 'API-токен', secret: true, hint: 'Todoist → Настройки → Интеграции → Разработчик' }],
    actions: [
      { name: 'list_tasks', desc: 'Открытые задачи (фильтр Todoist: today, overdue, …)', params: obj({ filter: S }), run: (c, a, s) => http(`https://api.todoist.com/rest/v2/tasks?${qs({ filter: a.filter })}`, { headers: bearer(c.token), signal: s }).then((j) => j.slice(0, 40).map((t) => `${t.id}: ${t.content}${t.due ? ` (до ${t.due.string})` : ''}`).join('\n') || 'Пусто') },
      { name: 'add_task', write: true, desc: 'Добавить задачу', params: obj({ content: S, due_string: { type: 'string', description: 'например «завтра в 10:00»' } }, ['content']), run: (c, a, s) => http('https://api.todoist.com/rest/v2/tasks', { method: 'POST', headers: bearer(c.token), body: { content: a.content, due_string: a.due_string, due_lang: 'ru' }, signal: s }).then((j) => `Добавлено: ${j.content} (id ${j.id})`) },
      { name: 'complete_task', write: true, desc: 'Отметить выполненной', params: obj({ id: S }, ['id']), run: (c, a, s) => http(`https://api.todoist.com/rest/v2/tasks/${a.id}/close`, { method: 'POST', headers: bearer(c.token), signal: s, raw: true }).then(() => 'Готово') },
    ] },
  { id: 'trello', name: 'Trello', icon: '🗂️', desc: 'Доски и карточки Trello', aliases: /trello|трелло/i,
    fields: [{ k: 'key', label: 'API key', secret: true, hint: 'trello.com/power-ups/admin' }, { k: 'token', label: 'Token', secret: true }],
    actions: [
      { name: 'list_boards', desc: 'Мои доски и их списки', params: obj(), run: (c, a, s) => http(`https://api.trello.com/1/members/me/boards?${qs({ key: c.key, token: c.token, fields: 'name', lists: 'open' })}`, { signal: s }).then((j) => j.map((b) => `${b.name} (${b.id}): ${(b.lists || []).map((l) => `${l.name}=${l.id}`).join(', ')}`).join('\n')) },
      { name: 'list_cards', desc: 'Карточки списка', params: obj({ list_id: S }, ['list_id']), run: (c, a, s) => http(`https://api.trello.com/1/lists/${a.list_id}/cards?${qs({ key: c.key, token: c.token, fields: 'name,due' })}`, { signal: s }).then((j) => j.map((x) => `${x.name}${x.due ? ` (до ${x.due.slice(0, 10)})` : ''} — ${x.id}`).join('\n') || 'Пусто') },
      { name: 'add_card', write: true, desc: 'Создать карточку', params: obj({ list_id: S, name: S, desc: S }, ['list_id', 'name']), run: (c, a, s) => http(`https://api.trello.com/1/cards?${qs({ key: c.key, token: c.token, idList: a.list_id, name: a.name, desc: a.desc })}`, { method: 'POST', signal: s }).then((j) => `Создано: ${j.shortUrl}`) },
    ] },
  { id: 'jira', name: 'Jira', icon: '🧭', desc: 'Задачи Jira: поиск по JQL и создание', aliases: /jira|джира/i,
    fields: [{ k: 'domain', label: 'Домен (company.atlassian.net)' }, { k: 'email', label: 'Email аккаунта' }, { k: 'token', label: 'API-токен', secret: true, hint: 'id.atlassian.com → Security → API tokens' }],
    actions: [
      { name: 'search', desc: 'Поиск задач по JQL', params: obj({ jql: { type: 'string', description: 'например: assignee = currentUser() AND resolution = Unresolved' } }, ['jql']), run: (c, a, s) => http(`${host(c.domain, '')}/rest/api/3/search/jql?${qs({ jql: a.jql, maxResults: 15, fields: 'summary,status,assignee' })}`, { headers: basic(c.email, c.token), signal: s }).then((j) => (j.issues || []).map((i) => `${i.key} ${i.fields.summary} [${i.fields.status?.name}] ${i.fields.assignee?.displayName || ''}`).join('\n') || 'Ничего') },
      { name: 'create_issue', write: true, desc: 'Создать задачу', params: obj({ project: { type: 'string', description: 'ключ проекта' }, summary: S, description: S, type: S }, ['project', 'summary']), run: (c, a, s) => http(`${host(c.domain, '')}/rest/api/3/issue`, { method: 'POST', headers: basic(c.email, c.token), body: { fields: { project: { key: a.project }, summary: a.summary, issuetype: { name: a.type || 'Task' }, ...(a.description ? { description: { type: 'doc', version: 1, content: [{ type: 'paragraph', content: [{ type: 'text', text: a.description }] }] } } : {}) } }, signal: s }).then((j) => `Создано: ${j.key}`) },
    ] },
  { id: 'airtable', name: 'Airtable', icon: '🧮', desc: 'Таблицы Airtable: читать и добавлять записи', aliases: /airtable|эйртейбл|айртейбл/i,
    fields: [{ k: 'token', label: 'Personal access token', secret: true, hint: 'airtable.com/create/tokens' }],
    actions: [
      { name: 'list_records', desc: 'Записи таблицы', params: obj({ base_id: { type: 'string', description: 'app…' }, table: S, max: I, formula: S }, ['base_id', 'table']), run: (c, a, s) => http(`https://api.airtable.com/v0/${a.base_id}/${encodeURIComponent(a.table)}?${qs({ maxRecords: Math.min(+a.max || 15, 50), filterByFormula: a.formula })}`, { headers: bearer(c.token), signal: s }).then((j) => j.records.map((r) => `${r.id}: ${JSON.stringify(r.fields)}`).join('\n') || 'Пусто') },
      { name: 'create_record', write: true, desc: 'Добавить запись', params: obj({ base_id: S, table: S, fields: { type: 'object', description: 'поле → значение' } }, ['base_id', 'table', 'fields']), run: (c, a, s) => http(`https://api.airtable.com/v0/${a.base_id}/${encodeURIComponent(a.table)}`, { method: 'POST', headers: bearer(c.token), body: { fields: a.fields }, signal: s }).then((j) => `Создано ${j.id}`) },
    ] },
  { id: 'homeassistant', name: 'Home Assistant', icon: '🏠', desc: 'Умный дом: состояния устройств и управление', aliases: /home ?assistant|умн\S* дом|свет|розетк|термостат|кондиционер/i,
    fields: [{ k: 'url', label: 'Адрес (http://homeassistant.local:8123)' }, { k: 'token', label: 'Long-lived access token', secret: true, hint: 'Профиль → Безопасность' }],
    actions: [
      { name: 'get_states', desc: 'Состояния устройств (фильтр по домену: light, switch, climate, sensor…)', params: obj({ domain: S }), run: (c, a, s) => http(`${host(c.url, '')}/api/states`, { headers: bearer(c.token), signal: s }).then((j) => j.filter((e) => !a.domain || e.entity_id.startsWith(a.domain + '.')).slice(0, 60).map((e) => `${e.entity_id}: ${e.state}${e.attributes?.friendly_name ? ` (${e.attributes.friendly_name})` : ''}`).join('\n') || 'Пусто') },
      { name: 'call_service', write: true, desc: 'Вызвать сервис (включить свет: light/turn_on, выключить: light/turn_off)', params: obj({ domain: S, service: S, entity_id: S, data: { type: 'object' } }, ['domain', 'service']), run: (c, a, s) => http(`${host(c.url, '')}/api/services/${a.domain}/${a.service}`, { method: 'POST', headers: bearer(c.token), body: { ...(a.data || {}), ...(a.entity_id ? { entity_id: a.entity_id } : {}) }, signal: s }).then(() => 'Выполнено') },
    ] },
  { id: 'ical', name: 'Календарь (iCal)', icon: '📅', desc: 'Ближайшие события из любого календаря по секретной ссылке iCal (Google, Яндекс, Apple, Outlook)', aliases: /календар|расписани|встреч|событи|ical|google calendar/i,
    fields: [{ k: 'url', label: 'Секретная ссылка .ics', secret: true, hint: 'Google Календарь → Настройки календаря → Секретный адрес в формате iCal' }],
    actions: [{ name: 'upcoming', desc: 'События на ближайшие дни', params: obj({ days: I }), run: async (c, a, s) => { const t = await http(c.url.replace(/^webcal:/, 'https:'), { raw: true, signal: s, headers: { Accept: 'text/calendar' } }); const from = Date.now() - 3600e3, to = Date.now() + (Math.min(+a.days || 7, 60)) * 864e5; const ev = parseIcs(t).filter((e) => e.t >= from && e.t <= to).sort((x, y) => x.t - y.t).slice(0, 40); return ev.map((e) => `${new Date(e.t).toISOString().slice(0, e.allDay ? 10 : 16).replace('T', ' ')} ${e.title}${e.where ? ` @ ${e.where}` : ''}`).join('\n') || 'Событий нет'; } }] },
  { id: 'ntfy', name: 'Push-уведомления (ntfy)', icon: '🔔', desc: 'Присылать уведомления на телефон через ntfy.sh или свой сервер', aliases: /ntfy|пуш|push|уведоми/i,
    fields: [{ k: 'topic', label: 'Тема (topic)', hint: 'придумайте длинное случайное имя и подпишитесь в приложении ntfy' }, { opt: true, k: 'server', label: 'Сервер (по умолчанию ntfy.sh)' }, { opt: true, k: 'token', label: 'Токен (если сервер закрытый)', secret: true }],
    actions: [{ name: 'push', write: true, desc: 'Отправить push-уведомление на телефон', params: obj({ message: S, title: S, priority: { type: 'integer', description: '1–5' } }, ['message']), run: (c, a, s) => http(`${host(c.server, 'ntfy.sh')}/${c.topic}`, { method: 'POST', headers: { ...(c.token ? bearer(c.token) : {}), ...(a.title ? { Title: `=?UTF-8?B?${Buffer.from(String(a.title)).toString('base64')}?=` } : {}), ...(a.priority ? { Priority: String(a.priority) } : {}) }, body: String(a.message), signal: s, raw: true }).then(() => 'Отправлено') }] },
  { id: 'webhook', name: 'Вебхук (Zapier / Make / n8n)', icon: '🪝', desc: 'Отправлять данные в любой вебхук — связка с тысячами сервисов', aliases: /webhook|вебхук|zapier|make\.com|n8n/i,
    fields: [{ k: 'url', label: 'URL вебхука', secret: true }, { opt: true, k: 'header', label: 'Заголовок авторизации (необязательно, «Имя: значение»)', secret: true }],
    actions: [{ name: 'post', write: true, desc: 'Отправить JSON на вебхук', params: obj({ payload: { type: 'object', description: 'любые данные' } }, ['payload']), run: (c, a, s) => { const h = {}; if (c.header?.includes(':')) h[c.header.split(':')[0].trim()] = c.header.split(':').slice(1).join(':').trim(); return http(c.url, { method: 'POST', headers: h, body: a.payload || {}, signal: s }).then((r) => `Отправлено. Ответ: ${trunc(r, 500)}`); } }] },
  { id: 'youtube', name: 'YouTube', icon: '▶️', desc: 'Поиск видео и свежие ролики каналов', aliases: /youtube|ютуб|ролик|видео/i,
    fields: [{ k: 'api_key', label: 'API key (Data API v3)', secret: true, hint: 'console.cloud.google.com → YouTube Data API v3' }],
    actions: [
      { name: 'search', desc: 'Поиск видео', params: obj({ query: S, max: I }, ['query']), run: (c, a, s) => http(`https://www.googleapis.com/youtube/v3/search?${qs({ part: 'snippet', type: 'video', q: a.query, maxResults: Math.min(+a.max || 6, 15), key: c.api_key })}`, { signal: s }).then((j) => j.items.map((i) => `${i.snippet.title} — ${i.snippet.channelTitle}\n  https://youtu.be/${i.id.videoId}`).join('\n') || 'Ничего') },
      { name: 'channel_videos', desc: 'Свежие видео канала', params: obj({ channel_id: { type: 'string', description: 'UC…' } }, ['channel_id']), run: (c, a, s) => http(`https://www.googleapis.com/youtube/v3/search?${qs({ part: 'snippet', channelId: a.channel_id, order: 'date', type: 'video', maxResults: 8, key: c.api_key })}`, { signal: s }).then((j) => j.items.map((i) => `${i.snippet.publishedAt.slice(0, 10)} ${i.snippet.title}\n  https://youtu.be/${i.id.videoId}`).join('\n') || 'Ничего') },
    ] },
  { id: 'stripe', name: 'Stripe', icon: '💳', desc: 'Баланс, платежи и клиенты Stripe (только чтение)', aliases: /stripe|страйп|платеж|выручк/i,
    fields: [{ k: 'secret_key', label: 'Restricted key (rk_…)', secret: true, hint: 'Dashboard → Developers → API keys; выдайте права только на чтение' }],
    actions: [
      { name: 'balance', desc: 'Баланс', params: obj(), run: (c, a, s) => http('https://api.stripe.com/v1/balance', { headers: bearer(c.secret_key), signal: s }).then((j) => `Доступно: ${j.available.map((x) => `${x.amount / 100} ${x.currency.toUpperCase()}`).join(', ')}; в ожидании: ${j.pending.map((x) => `${x.amount / 100} ${x.currency.toUpperCase()}`).join(', ')}`) },
      { name: 'recent_charges', desc: 'Последние платежи', params: obj({ limit: I }), run: (c, a, s) => http(`https://api.stripe.com/v1/charges?limit=${Math.min(+a.limit || 10, 30)}`, { headers: bearer(c.secret_key), signal: s }).then((j) => j.data.map((x) => `${new Date(x.created * 1000).toISOString().slice(0, 16).replace('T', ' ')} ${x.amount / 100} ${x.currency.toUpperCase()} ${x.status} ${x.billing_details?.email || ''}`).join('\n') || 'Платежей нет') },
    ] },
  { id: 'vercel', name: 'Vercel', icon: '▲', desc: 'Проекты и деплои Vercel', aliases: /vercel|вёрсел|версел|деплой/i,
    fields: [{ k: 'token', label: 'Access token', secret: true, hint: 'vercel.com/account/tokens' }],
    actions: [
      { name: 'list_projects', desc: 'Проекты', params: obj(), run: (c, a, s) => http('https://api.vercel.com/v9/projects?limit=30', { headers: bearer(c.token), signal: s }).then((j) => j.projects.map((p) => `${p.name} (${p.id})`).join('\n') || 'Пусто') },
      { name: 'list_deployments', desc: 'Последние деплои', params: obj({ project_id: S }), run: (c, a, s) => http(`https://api.vercel.com/v6/deployments?${qs({ projectId: a.project_id, limit: 10 })}`, { headers: bearer(c.token), signal: s }).then((j) => j.deployments.map((d) => `${new Date(d.created).toISOString().slice(0, 16).replace('T', ' ')} ${d.name} ${d.state} https://${d.url}`).join('\n') || 'Пусто') },
    ] },
  { id: 'sentry', name: 'Sentry', icon: '🛡️', desc: 'Ошибки в продакшене: свежие проблемы проектов', aliases: /sentry|сентри|ошибк\S* в проду/i,
    fields: [{ k: 'token', label: 'Auth token', secret: true, hint: 'sentry.io/settings/auth-tokens' }, { k: 'org', label: 'Slug организации' }, { opt: true, k: 'base_url', label: 'Адрес (по умолчанию sentry.io)' }],
    actions: [{ name: 'list_issues', desc: 'Неразрешённые ошибки организации', params: obj({ query: S, limit: I }), run: (c, a, s) => http(`${host(c.base_url, 'sentry.io')}/api/0/organizations/${c.org}/issues/?${qs({ query: a.query || 'is:unresolved', limit: Math.min(+a.limit || 10, 25) })}`, { headers: bearer(c.token), signal: s }).then((j) => j.map((i) => `${i.shortId} ${i.title} — ${i.count} раз, ${i.project?.slug}\n  ${i.permalink}`).join('\n') || 'Ошибок нет') }] },
  { id: 'twilio', name: 'SMS (Twilio)', icon: '📟', desc: 'Отправка SMS через Twilio', aliases: /twilio|смс|sms/i,
    fields: [{ k: 'sid', label: 'Account SID' }, { k: 'auth', label: 'Auth token', secret: true }, { k: 'from', label: 'Ваш номер Twilio (+…)' }],
    actions: [{ name: 'send_sms', write: true, desc: 'Отправить SMS', params: obj({ to: { type: 'string', description: '+7…' }, body: S }, ['to', 'body']), run: (c, a, s) => http(`https://api.twilio.com/2010-04-01/Accounts/${c.sid}/Messages.json`, { method: 'POST', headers: basic(c.sid, c.auth), form: { To: a.to, From: c.from, Body: String(a.body).slice(0, 1500) }, signal: s }).then((j) => `Отправлено (${j.status})`) }] },
];

const byId = (id) => CONNECTORS.find((c) => c.id === id);
export const getConnector = byId;
export const connectedIds = (uid) => db.prepare('SELECT connector FROM integrations WHERE user_id=?').all(uid).map((r) => r.connector);
const credsOf = (uid, id) => { const r = db.prepare('SELECT creds FROM integrations WHERE user_id=? AND connector=?').get(uid, id); try { return r ? JSON.parse(r.creds) : null; } catch { return null; } };

/** Каталог для приложения: значения секретных полей не отдаются. */
export function catalog(uid) {
  const have = new Map(db.prepare('SELECT connector, creds FROM integrations WHERE user_id=?').all(uid).map((r) => [r.connector, r.creds]));
  return CONNECTORS.map((c) => { let cr = {}; try { cr = JSON.parse(have.get(c.id) || '{}'); } catch {} return { id: c.id, name: c.name, icon: c.icon, desc: c.desc, connected: have.has(c.id), fields: c.fields.map((f) => ({ k: f.k, label: f.label, secret: !!f.secret, opt: !!f.opt, hint: f.hint || '', value: have.has(c.id) ? (f.secret ? (cr[f.k] ? '••••••' : '') : cr[f.k] || '') : '' })), actions: c.actions.map((a) => ({ name: a.name, desc: a.desc, write: !!a.write })) }; });
}
export function saveCreds(uid, id, input) {
  const c = byId(id); if (!c) throw new Error('Неизвестный коннектор');
  const old = credsOf(uid, id) || {}; const next = {};
  for (const f of c.fields) { const v = String(input?.[f.k] ?? '').trim(); next[f.k] = v === '••••••' || (!v && f.secret && old[f.k]) ? old[f.k] || '' : v; }
  const req = c.fields.filter((f) => !f.opt);
  for (const f of req) if (!next[f.k]) throw new Error(`Заполните поле «${f.label}»`);
  db.prepare('INSERT INTO integrations(user_id,connector,creds,created_at) VALUES (?,?,?,?) ON CONFLICT(user_id,connector) DO UPDATE SET creds=excluded.creds').run(uid, id, JSON.stringify(next), now());
}
export const removeCreds = (uid, id) => db.prepare('DELETE FROM integrations WHERE user_id=? AND connector=?').run(uid, id);

/** Проверка подключения: первое безопасное (не write) действие без параметров, где возможно. */
export async function testConnector(uid, id) {
  const c = byId(id), cr = credsOf(uid, id); if (!c || !cr) return 'Не подключено';
  const a = c.actions.find((x) => !x.write && !(x.params.required || []).length);
  if (!a) return 'Ключи сохранены (проверка недоступна для этого коннектора — попробуйте в чате)';
  try { const r = await a.run(cr, {}); return `Работает: ${trunc(String(r), 200)}`; } catch (e) { return `Ошибка: ${e.message}`; }
}

// ---- интеграция с агентом ----
const fname = (cid, an) => `int_${cid}_${an}`;
/** Инструменты подключённых коннекторов. allow — множество разрешённых id (null = все подключённые); text — для отбора по упоминанию (если не агент). */
export function integrationToolDefs(uid, { allow = null, text = '', all = false, used = null } = {}) {
  const out = [];
  for (const id of connectedIds(uid)) {
    if (allow && !allow.has(id)) continue;
    const c = byId(id); if (!c) continue;
    if (!all && !allow && !(c.aliases.test(text) || [...(used || [])].some((u) => u.startsWith(`int_${id}_`)))) continue;
    for (const a of c.actions) out.push({ type: 'function', function: { name: fname(id, a.name), description: `[${c.name}] ${a.desc}${a.write ? ' (изменяет данные/отправляет — только по просьбе пользователя)' : ''}`.slice(0, 400), parameters: a.write ? { ...a.params, properties: { ...a.params.properties, confirmed: { type: 'boolean', description: 'true только после явного «да» пользователя' } } } : a.params } });
  }
  return out.slice(0, 48);
}
export const connectedSummary = (uid) => connectedIds(uid).map((id) => byId(id)?.name).filter(Boolean);

export async function runIntegration(user, name, args, ctx = {}) {
  const m = /^int_([a-z0-9]+)_(.+)$/.exec(name); if (!m) return 'Ошибка: неизвестный инструмент';
  const c = byId(m[1]); const a = c?.actions.find((x) => x.name === m[2]);
  if (!c || !a) return 'Ошибка: у коннектора нет такого действия';
  if (ctx.allow && !ctx.allow.has(c.id)) return `Ошибка: коннектор «${c.name}» не разрешён этому агенту`;
  const cr = credsOf(user.id, c.id); if (!cr) return `Ошибка: коннектор «${c.name}» не подключён (Настройки → Коннекторы)`;
  if (a.write) {
    if (ctx.automation && !ctx.writeOk) return `ОТКАЗАНО: у автономного агента нет разрешения на изменение данных в «${c.name}». Опиши в отчёте, что хотел сделать (${a.desc}), — пользователь решит сам или включит агенту «Разрешить действия».`;
    if (!ctx.automation && ctx.autonomy !== 'auto' && args.confirmed !== true) return `ОТКАЗАНО (режим «спрашивать»): «${c.name}: ${a.desc}» изменяет данные или что-то отправляет. Вызови ask_user с вопросом и вариантами «Да» / «Нет», покажи, что именно будет сделано. Повтори вызов с confirmed=true только после явного «Да».`;
  }
  try { const { confirmed, ...rest } = args || {}; return trunc(await a.run(cr, rest, ctx.signal)); } catch (e) { return `Ошибка ${c.name}: ${e.message}`; }
}
