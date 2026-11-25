// Подключение Gmail и Google Календаря через OAuth 2.0 (серверный поток с кодом авторизации). Refresh-токен хранится в таблице integrations (коннектор «google»).
import jwt from 'jsonwebtoken';
import { config } from './config.js';
import { db, now } from './db.js';

export const SCOPES = { gmail: 'https://www.googleapis.com/auth/gmail.modify', calendar: 'https://www.googleapis.com/auth/calendar' };
export const googleReady = () => !!(config.googleOAuth.clientId && config.googleOAuth.clientSecret && config.publicUrl);
const redirectUri = () => `${config.publicUrl.replace(/\/+$/, '')}/oauth/google/callback`;
const q = (o) => new URLSearchParams(o).toString();

/** Ссылка на экран согласия Google; state подписан и живёт 10 минут. */
export function googleStartUrl(uid, services) {
  if (!googleReady()) throw new Error('На сервере не настроен вход через Google для Gmail/Календаря (GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, PUBLIC_URL)');
  const want = (services?.length ? services : ['gmail', 'calendar']).filter((x) => SCOPES[x]);
  const state = jwt.sign({ uid, g: 1 }, config.jwtSecret, { expiresIn: '10m' });
  return `https://accounts.google.com/o/oauth2/v2/auth?${q({ client_id: config.googleOAuth.clientId, redirect_uri: redirectUri(), response_type: 'code', scope: ['openid', 'email', ...want.map((x) => SCOPES[x])].join(' '), access_type: 'offline', prompt: 'consent', include_granted_scopes: 'true', state })}`;
}

async function tokenCall(params) {
  const r = await fetch('https://oauth2.googleapis.com/token', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: q({ client_id: config.googleOAuth.clientId, client_secret: config.googleOAuth.clientSecret, ...params }), signal: AbortSignal.timeout(15000) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error_description || j.error || `HTTP ${r.status}`);
  return j;
}
const row = (uid) => { const r = db.prepare("SELECT creds FROM integrations WHERE user_id=? AND connector='google'").get(uid); try { return r ? JSON.parse(r.creds) : null; } catch { return null; } };
const save = (uid, c) => db.prepare("INSERT INTO integrations(user_id,connector,creds,created_at) VALUES (?,?,?,?) ON CONFLICT(user_id,connector) DO UPDATE SET creds=excluded.creds").run(uid, 'google', JSON.stringify(c), now());

/** Какие сервисы Google разрешены пользователем: ['gmail','calendar']. */
export function googleServices(uid) { const c = row(uid); if (!c?.refresh_token) return []; return Object.keys(SCOPES).filter((k) => String(c.scope || '').includes(SCOPES[k])); }
export const googleEmail = (uid) => row(uid)?.email || '';
export const googleRevoke = async (uid) => { const c = row(uid); db.prepare("DELETE FROM integrations WHERE user_id=? AND connector='google'").run(uid); if (c?.refresh_token) await fetch(`https://oauth2.googleapis.com/revoke?${q({ token: c.refresh_token })}`, { method: 'POST', signal: AbortSignal.timeout(8000) }).catch(() => {}); };

/** Действующий access-токен (обновляется по refresh-токену). */
export async function googleAccess(uid) {
  const c = row(uid); if (!c?.refresh_token) throw new Error('Google не подключён (Коннекторы → Gmail → «Войти через Google»)');
  if (c.access_token && c.expiry > Date.now() + 60e3) return c.access_token;
  let j; try { j = await tokenCall({ grant_type: 'refresh_token', refresh_token: c.refresh_token }); } catch (e) { throw new Error(/invalid_grant/.test(e.message) ? 'Доступ к Google отозван или истёк — войдите заново (Коннекторы → Gmail)' : e.message); }
  save(uid, { ...c, access_token: j.access_token, expiry: Date.now() + (j.expires_in || 3000) * 1000, scope: j.scope || c.scope });
  return j.access_token;
}

const page = (ok, msg) => `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OpenAgent</title><body style="font-family:system-ui;background:#111;color:#eee;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;text-align:center"><div style="padding:24px"><div style="font-size:56px">${ok ? '✅' : '⚠️'}</div><h2>${ok ? 'Google подключён' : 'Не получилось'}</h2><p style="opacity:.75">${msg}</p></div>`;
export async function googleCallback(req, res) {
  try {
    if (req.query.error) return res.status(400).send(page(false, 'Доступ не выдан: ' + String(req.query.error).slice(0, 80)));
    const st = jwt.verify(String(req.query.state || ''), config.jwtSecret);
    if (!st.g || !st.uid) throw new Error('неверный state');
    const j = await tokenCall({ grant_type: 'authorization_code', code: String(req.query.code || ''), redirect_uri: redirectUri() });
    const old = row(st.uid) || {};
    const refresh = j.refresh_token || old.refresh_token;
    if (!refresh) throw new Error('Google не выдал refresh-токен — удалите доступ OpenAgent в myaccount.google.com/permissions и повторите');
    let email = old.email || '';
    try { email = JSON.parse(Buffer.from(String(j.id_token).split('.')[1], 'base64url').toString()).email || email; } catch {}
    save(st.uid, { refresh_token: refresh, access_token: j.access_token, expiry: Date.now() + (j.expires_in || 3000) * 1000, scope: j.scope || '', email });
    res.send(page(true, `${email ? email + ' · ' : ''}Вернитесь в приложение OpenAgent.`));
  } catch (e) { res.status(400).send(page(false, String(e.message).slice(0, 200))); }
}
