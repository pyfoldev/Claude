import crypto from 'node:crypto';
import jwt from 'jsonwebtoken';
import nodemailer from 'nodemailer';
import { Router } from 'express';
import { config, isOwnerEmail, isAllowedEmail } from './config.js';
import { db, now } from './db.js';

export const authRouter = Router();

const hash = (email, code) => crypto.createHmac('sha256', config.jwtSecret).update(`${email}:${code}`).digest('hex');
const emailOk = (e) => typeof e === 'string' && /^[^\s@]{1,64}@[^\s@]{1,255}\.[^\s@]{2,}$/.test(e) && e.length < 320;

let transport;
const mailer = () => (transport ||= nodemailer.createTransport({
  host: config.smtp.host, port: config.smtp.port, secure: config.smtp.port === 465,
  auth: { user: config.smtp.user, pass: config.smtp.pass },
}));

async function verifyTurnstile(token, ip) {
  if (!config.turnstile.secret) return true; // капча не настроена — пропускаем (только dev)
  if (!token) return false;
  const r = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ secret: config.turnstile.secret, response: token, remoteip: ip || '' }),
  });
  return !!(await r.json()).success;
}

function issueToken(email, name) {
  let u = db.prepare('SELECT * FROM users WHERE email=?').get(email);
  const role = isOwnerEmail(email) ? 'owner' : 'user';
  if (!u) {
    const id = db.prepare('INSERT INTO users(email,name,role,created_at) VALUES (?,?,?,?)').run(email, name || null, role, now()).lastInsertRowid;
    u = db.prepare('SELECT * FROM users WHERE id=?').get(id);
  } else {
    db.prepare('UPDATE users SET role=?, name=COALESCE(name,?) WHERE id=?').run(role, name || null, u.id);
    u = db.prepare('SELECT * FROM users WHERE id=?').get(u.id);
  }
  const token = jwt.sign({ uid: u.id }, config.jwtSecret, { expiresIn: '180d' });
  return { token, user: { id: u.id, email: u.email, name: u.name, role: u.role } };
}

const ipHits = new Map();
const limited = (ip, max = 10) => {
  const t = now(); const arr = (ipHits.get(ip) || []).filter((x) => t - x < 3600e3);
  arr.push(t); ipHits.set(ip, arr); return arr.length > max;
};

authRouter.get('/config', (_req, res) => {
  res.json({
    captchaUrl: config.turnstile.siteKey ? `${config.publicUrl}/captcha` : null,
    googleClientId: config.googleClientIds[0] || null,
    githubDeviceFlow: !!config.githubClientId,
  });
});

authRouter.post('/send-code', async (req, res) => {
  const email = String(req.body.email || '').trim().toLowerCase();
  if (!emailOk(email)) return res.status(400).json({ error: 'Некорректный e-mail' });
  if (limited(req.ip)) return res.status(429).json({ error: 'Слишком много попыток' });
  if (!(await verifyTurnstile(req.body.captcha, req.ip))) return res.status(400).json({ error: 'Капча не пройдена' });
  if (!isAllowedEmail(email)) return res.status(403).json({ error: 'Этот e-mail не допущен к серверу' });
  const prev = db.prepare('SELECT sent_at FROM otps WHERE email=?').get(email);
  if (prev && now() - prev.sent_at < 45e3) return res.status(429).json({ error: 'Код уже отправлен, подожди минуту' });
  const code = String(crypto.randomInt(0, 1e6)).padStart(6, '0');
  db.prepare('INSERT OR REPLACE INTO otps(email,code_hash,expires,attempts,sent_at) VALUES (?,?,?,0,?)')
    .run(email, hash(email, code), now() + 10 * 60e3, now());
  try {
    await mailer().sendMail({
      from: `OpenAgent <${config.smtp.sender}>`, to: email, subject: `Код входа OpenAgent: ${code}`,
      text: `Ваш код входа: ${code}\nОн действует 10 минут. Если это были не вы — проигнорируйте письмо.`,
      html: `<div style="background:#000;padding:32px;font-family:-apple-system,Segoe UI,sans-serif;color:#fff">
        <div style="max-width:360px;margin:auto"><div style="font-size:18px;opacity:.6">OpenAgent</div>
        <div style="font-size:40px;letter-spacing:10px;font-weight:600;margin:24px 0">${code}</div>
        <div style="opacity:.5;font-size:13px">Код действует 10 минут. Если это были не вы — просто проигнорируйте письмо.</div></div></div>`,
    });
  } catch (e) {
    console.error('mail failed:', e.message);
    return res.status(502).json({ error: 'Не удалось отправить письмо' });
  }
  res.json({ ok: true });
});

authRouter.post('/verify', (req, res) => {
  const email = String(req.body.email || '').trim().toLowerCase();
  const code = String(req.body.code || '').trim();
  const row = db.prepare('SELECT * FROM otps WHERE email=?').get(email);
  if (!row || row.expires < now() || row.attempts >= 5) return res.status(400).json({ error: 'Код истёк — запроси новый' });
  db.prepare('UPDATE otps SET attempts=attempts+1 WHERE email=?').run(email);
  const a = Buffer.from(row.code_hash), b = Buffer.from(hash(email, code));
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return res.status(400).json({ error: 'Неверный код' });
  db.prepare('DELETE FROM otps WHERE email=?').run(email);
  res.json(issueToken(email));
});

authRouter.post('/google', async (req, res) => {
  try {
    const r = await fetch(`https://oauth2.googleapis.com/tokeninfo?id_token=${encodeURIComponent(req.body.idToken || '')}`);
    const j = await r.json();
    if (!r.ok || !config.googleClientIds.includes(j.aud) || j.email_verified !== 'true') {
      return res.status(401).json({ error: 'Google-токен недействителен' });
    }
    const email = j.email.toLowerCase();
    if (!isAllowedEmail(email)) return res.status(403).json({ error: 'Этот e-mail не допущен к серверу' });
    res.json(issueToken(email, j.name));
  } catch (e) { res.status(500).json({ error: e.message }); }
});

export function requireAuth(req, res, next) {
  const h = req.headers.authorization || '';
  const token = h.startsWith('Bearer ') ? h.slice(7) : req.query.token;
  try {
    const { uid } = jwt.verify(token, config.jwtSecret);
    const u = db.prepare('SELECT * FROM users WHERE id=?').get(uid);
    if (!u) throw new Error('no user');
    u.role = isOwnerEmail(u.email) ? 'owner' : 'user';
    req.user = u;
    next();
  } catch { res.status(401).json({ error: 'unauthorized' }); }
}
