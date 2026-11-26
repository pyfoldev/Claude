// Вебхук GitHub для мгновенного обновления: POST /hooks/deploy (событие push). Подпись X-Hub-Signature-256 проверяется секретом DEPLOY_WEBHOOK_SECRET.
// Обновление выполняет deploy/update.sh (команда openagent-update): проверка кода → снимок → замена → перезапуск → проверка → откат при сбое.
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';
import fs from 'node:fs';

let last = 0;
export function verifySignature(secret, raw, header) {
  if (!secret || !header || !header.startsWith('sha256=')) return false;
  const want = crypto.createHmac('sha256', secret).update(raw).digest();
  let got; try { got = Buffer.from(header.slice(7), 'hex'); } catch { return false; }
  return got.length === want.length && crypto.timingSafeEqual(got, want);
}
export function deployHook(env = process.env, run = (cmd) => { fs.mkdirSync('/var/lib/openagent-deploy', { recursive: true }); const out = fs.openSync('/var/log/openagent-deploy.log', 'a'); spawn('setsid', ['-f', cmd], { detached: true, stdio: ['ignore', out, out] }).unref(); }) {
  return (req, res) => {
    const secret = env.DEPLOY_WEBHOOK_SECRET;
    if (!secret) return res.status(404).json({ error: 'not found' });
    const raw = Buffer.isBuffer(req.body) ? req.body : Buffer.from(typeof req.body === 'string' ? req.body : JSON.stringify(req.body || {}));
    if (!verifySignature(secret, raw, req.get('x-hub-signature-256'))) return res.status(401).json({ error: 'bad signature' });
    const ev = req.get('x-github-event');
    if (ev === 'ping') return res.json({ ok: true, pong: true });
    if (ev !== 'push') return res.json({ ok: true, ignored: ev });
    let p = {}; try { p = JSON.parse(raw.toString('utf8')); } catch {}
    const branch = env.DEPLOY_BRANCH || 'main';
    if (p.ref !== `refs/heads/${branch}`) return res.json({ ok: true, ignored: p.ref });
    const now = Date.now(); if (now - last < 15000) return res.status(202).json({ ok: true, queued: false, note: 'recent run' });
    last = now;
    try { run(env.DEPLOY_UPDATE_CMD || '/usr/local/bin/openagent-update'); } catch (e) { return res.status(500).json({ error: e.message }); }
    res.status(202).json({ ok: true, started: true });
  };
}
