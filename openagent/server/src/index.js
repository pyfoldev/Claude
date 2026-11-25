import express from 'express';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { config, SERVER_V } from './config.js';
import { authRouter } from './auth.js';
import { api } from './routes.js';
import { startScheduler } from './scheduler.js';
import { startAgentScheduler } from './agents.js';
import { mountSites } from './sites.js';
import { mountShare } from './extras.js';
import { attachWs } from './sttStream.js';
import { gigaamUp } from './gigaam.js';

if (!process.env.JWT_SECRET || /^(change-me|dev-insecure)/.test(process.env.JWT_SECRET)) console.error('⚠ JWT_SECRET не задан или стандартный — любой может подделать токен входа. Задайте длинную случайную строку в .env!');
const app = express();
app.set('trust proxy', 1);
app.use(express.json({ limit: '2mb' }));

const pub = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'public');
app.get('/captcha', (_req, res) => {
  res.set('Cache-Control', 'no-store');
  res.type('html').send(
    fs.readFileSync(path.join(pub, 'captcha.html'), 'utf8').replaceAll('__SITEKEY__', config.turnstile.siteKey));
});
// версия/возможности сервера: приложение по ним понимает, обновлён ли сервер (потоковое распознавание, потоковая озвучка, команды телефону)
// Офлайн-модель управления телефоном: приложение скачивает её отсюда (положите phone.gguf в DATA_DIR/models/). Поддерживает докачку (Range).
app.get('/models/phone.gguf', (req, res) => {
  const f = path.resolve(config.dataDir, 'models', 'phone.gguf');
  if (fs.existsSync(f)) return res.sendFile(f);
  // нет цельного файла — склеиваем «на лету» из частей phone.gguf.partNN (папка dist/phone-gguf репозитория или DATA_DIR/models/phone-gguf)
  const here = path.dirname(fileURLToPath(import.meta.url));
  const dirs = [path.resolve(config.dataDir, 'models', 'phone-gguf'), path.resolve(here, '..', '..', '..', 'dist', 'phone-gguf'), path.resolve(here, '..', '..', 'dist', 'phone-gguf'), path.resolve(config.dataDir, 'models')];
  for (const d of dirs) {
    let parts; try { parts = fs.readdirSync(d).filter((n) => /^phone\.gguf\.part\d+$/.test(n)).sort(); } catch { continue; }
    if (!parts.length) continue;
    const files = parts.map((n) => path.join(d, n));
    res.setHeader('Content-Type', 'application/octet-stream'); res.setHeader('Content-Length', files.reduce((a, x) => a + fs.statSync(x).size, 0));
    let i = 0; const next = () => { if (i >= files.length) return res.end(); const st = fs.createReadStream(files[i++]); st.on('error', () => res.destroy()); st.on('end', next); st.pipe(res, { end: false }); };
    res.on('close', () => {}); return next();
  }
  res.status(404).json({ error: 'phone.gguf не найден: положите файл в DATA_DIR/models/ или папку dist/phone-gguf с частями' });
});
app.get('/health', (_req, res) => res.json({ ok: true, v: SERVER_V, features: [...(gigaamUp() ? ['stt-gigaam'] : []), 'stt-stream', 'tts-stream', 'phone', 'docs', 'diag', 'bridge', 'pplx', 'tts-pcm', 'mcp', 'notes', 'todos', 'secrets', 'share', 'compare', 'export', 'watch', 'lookup', 'voice-agent', 'agents', 'integrations'] }));
mountSites(app);
mountShare(app);
// Вебхуки автоматизаций: POST /hooks/<token> — запускает задачу агента (токен = секрет в ссылке)
const hookHits = new Map();
app.post('/hooks/:token', express.text({ type: '*/*', limit: '200kb' }), async (req, res) => {
  const { db } = await import('./db.js'); const { runScheduleNow } = await import('./scheduler.js');
  const s = db.prepare('SELECT * FROM schedules WHERE hook_token=? AND enabled=1').get(String(req.params.token));
  if (!s) return res.status(404).json({ error: 'not found' });
  const t = Date.now(), arr = (hookHits.get(s.id) || []).filter((x) => t - x < 60000);
  if (arr.length >= 20) return res.status(429).json({ error: 'too many requests' });
  arr.push(t); hookHits.set(s.id, arr);
  runScheduleNow(s, typeof req.body === 'string' ? req.body : JSON.stringify(req.body));
  res.json({ ok: true });
});
app.use('/auth', authRouter);
app.use('/api', api);
app.use((err, _req, res, _next) => { console.error(err); res.status(500).json({ error: err.message }); });

startScheduler();
startAgentScheduler();
gigaamUp();   // прогрев проверки доступности GigaAM (дальше кэшируется)
const server = app.listen(config.port, () => console.log(`OpenAgent server on :${config.port}`));
attachWs(server);
server.requestTimeout = 0;
server.headersTimeout = 65000;
