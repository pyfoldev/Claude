// Gmail и Календарь через OAuth без сети: ссылка согласия, обмен кода, обновление токена, действия и запреты.
import { mkUser } from './harness.mjs';
import { config } from '../src/config.js';
config.googleOAuth.clientId = 'cid.apps.googleusercontent.com'; config.googleOAuth.clientSecret = 'csecret'; config.publicUrl = 'https://srv.test';
const { googleStartUrl, googleCallback, googleServices } = await import('../src/googleOAuth.js');
const { runTool, toolDefs } = await import('../src/tools.js');
const { catalog, connectedIds } = await import('../src/integrations.js');
import jwt from 'jsonwebtoken';
const user = mkUser('g@example.com', 'owner');
let fail = 0; const ok = (n, c, i = '') => { console.log(`${c ? 'PASS' : 'FAIL'} ${n}${c ? '' : ' → ' + i}`); if (!c) fail++; };
const calls = []; let tokenN = 0;
globalThis.fetch = async (url, o = {}) => {
  url = String(url); calls.push({ url, method: o.method || 'GET', body: o.body, auth: o.headers?.Authorization });
  const J = (x) => new Response(JSON.stringify(x), { status: 200 });
  if (url.includes('oauth2.googleapis.com/token')) { tokenN++; const b = new URLSearchParams(String(o.body)); return b.get('grant_type') === 'authorization_code' ? J({ access_token: 'AT1', refresh_token: 'RT1', expires_in: 3600, scope: 'openid email https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/calendar', id_token: 'x.' + Buffer.from(JSON.stringify({ email: 'me@gmail.com' })).toString('base64url') + '.y' }) : J({ access_token: 'AT' + tokenN, expires_in: 3600 }); }
  if (url.includes('/messages?')) return J({ messages: [{ id: 'm1' }] });
  if (url.includes('/messages/m1?format=metadata')) return J({ id: 'm1', labelIds: ['UNREAD'], snippet: 'привет', payload: { headers: [{ name: 'From', value: 'Аня <a@x.ru>' }, { name: 'Subject', value: 'Встреча' }, { name: 'Date', value: 'Tue, 24 Nov 2026 10:00:00 +0300' }] } });
  if (url.includes('/messages/m1?format=full')) return J({ id: 'm1', threadId: 't1', payload: { headers: [{ name: 'Subject', value: 'Встреча' }], mimeType: 'multipart/alternative', parts: [{ mimeType: 'text/plain', body: { data: Buffer.from('Текст письма').toString('base64url') } }] } });
  if (url.includes('/events?')) return J({ items: [{ id: 'e1', summary: 'Планёрка', start: { dateTime: '2026-11-26T10:00:00+03:00' } }] });
  return J({ id: 'x', ok: true });
};
const names = (d) => d.map((x) => x.function.name);
let u = googleStartUrl(user.id, ['gmail', 'calendar']);
const U = new URL(u);
ok('ссылка согласия', U.hostname === 'accounts.google.com' && U.searchParams.get('access_type') === 'offline' && /gmail\.modify/.test(U.searchParams.get('scope')) && U.searchParams.get('redirect_uri') === 'https://srv.test/oauth/google/callback');
ok('state подписан и содержит пользователя', jwt.verify(U.searchParams.get('state'), config.jwtSecret).uid === user.id);
ok('до входа Google не подключён', googleServices(user.id).length === 0 && !connectedIds(user.id).includes('gmail'));
ok('каталог: oauth-флаг и готовность', (() => { const g = catalog(user.id).find((c) => c.id === 'gmail'); return g.oauth === 'google' && g.oauthReady && !g.connected; })());
// callback
let out = { code: 0, body: '' }; const res = { status(c) { out.code = c; return this; }, send(b) { out.body = b; } };
await googleCallback({ query: { code: 'CODE', state: U.searchParams.get('state') } }, res);
ok('callback: успех, страница с почтой', out.code === 0 && /me@gmail\.com/.test(out.body) && /Google подключён/.test(out.body), out.body.slice(0, 120));
ok('подключены Gmail и Календарь', googleServices(user.id).join() === 'gmail,calendar' && connectedIds(user.id).includes('calendar'));
await googleCallback({ query: { code: 'C', state: 'bad' } }, res); ok('поддельный state отклонён', out.code === 400);
ok('инструменты по упоминанию', names(toolDefs(user, 'chat', { text: 'что в моей почте gmail?' })).includes('int_gmail_list_messages') && names(toolDefs(user, 'chat', { text: 'что у меня в календаре' })).includes('int_calendar_list_events'));
let r = await runTool(user, 'int_gmail_list_messages', { query: 'is:unread' }, { autonomy: 'ask' });
ok('список писем', /m1 \|.*Аня.*Встреча.*\[новое\]/.test(r), r);
ok('запрос с Bearer-токеном', calls.some((c) => c.url.includes('/messages?') && c.auth === 'Bearer AT1'));
r = await runTool(user, 'int_gmail_read_message', { id: 'm1' }, {}); ok('чтение письма', /Текст письма/.test(r) && /t1/.test(r), r);
r = await runTool(user, 'int_calendar_list_events', { days: 3 }, {}); ok('события', /Планёрка/.test(r), r);
calls.length = 0; r = await runTool(user, 'int_gmail_send_message', { to: 'a@x.ru', subject: 'Привет', body: 'Текст' }, { autonomy: 'ask' });
ok('отправка без «да» — отказ', /ОТКАЗАНО/.test(r) && !calls.length, r);
r = await runTool(user, 'int_gmail_send_message', { to: 'a@x.ru', subject: 'Привет', body: 'Текст', confirmed: true }, { autonomy: 'ask' });
const sent = calls.find((c) => c.url.endsWith('/messages/send')); const raw = Buffer.from(JSON.parse(sent.body).raw, 'base64url').toString();
ok('отправка с «да»: MIME, тема в UTF-8', /отправлено/.test(r) && /^To: a@x\.ru/.test(raw) && /Subject: =\?UTF-8\?B\?/.test(raw), r + raw.slice(0, 80));
calls.length = 0; r = await runTool(user, 'int_calendar_create_event', { summary: 'Обед', start: '2026-11-27T13:00:00+03:00', end: '2026-11-27T14:00:00+03:00', attendees: ['a@x.ru'], confirmed: true }, { autonomy: 'ask' });
const ev = JSON.parse(calls.find((c) => c.url.includes('/events?sendUpdates'))?.body || '{}');
ok('создание события', ev.summary === 'Обед' && ev.start.dateTime && ev.attendees[0].email === 'a@x.ru', JSON.stringify(ev));
r = await runTool(user, 'int_calendar_create_event', { summary: 'ДР', start: '2026-12-01', end: '2026-12-02', confirmed: true }, { autonomy: 'ask' });
ok('событие на весь день (date)', !!JSON.parse(calls.at(-1).body).start.date);
r = await runTool(user, 'int_calendar_delete_event', { id: 'e1' }, { automation: true, agent: { write_ok: 0 } });
ok('автономный без write_ok не удаляет', /ОТКАЗАНО/.test(r), r);
// просроченный токен → обновление
const { db } = await import('../src/db.js');
const row = JSON.parse(db.prepare("SELECT creds FROM integrations WHERE user_id=? AND connector='google'").get(user.id).creds); row.expiry = Date.now() - 1000;
db.prepare("UPDATE integrations SET creds=? WHERE user_id=? AND connector='google'").run(JSON.stringify(row), user.id);
calls.length = 0; await runTool(user, 'int_calendar_list_events', {}, {});
ok('просроченный токен обновляется', calls[0].url.includes('oauth2.googleapis.com/token') && /AT\d/.test(calls.at(-1).auth), JSON.stringify(calls.map((c) => c.url.slice(0, 50))));
console.log(fail ? `\n${fail} ПРОВАЛОВ` : '\nвсё прошло'); process.exit(fail ? 1 : 0);
