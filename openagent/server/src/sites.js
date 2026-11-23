// Хостинг статических сайтов на домене сервера: https://<домен>/s/<slug>/
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import express from 'express';
import { config } from './config.js';
import { db, now } from './db.js';

db.exec(`CREATE TABLE IF NOT EXISTS sites (
  slug TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'site',
  spa INTEGER NOT NULL DEFAULT 0,
  size INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
)`);

const ROOT = path.resolve(config.dataDir, 'sites');
fs.mkdirSync(ROOT, { recursive: true });
const MAX_FILES = 800, MAX_BYTES = 40 * 1024 * 1024;
const SKIP = new Set(['node_modules', '.git', '.gradle', '__pycache__', '.venv']);
const slugify = (s) => String(s || 'site').toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40) || 'site';
export const siteUrl = (slug) => `${config.publicUrl}/s/${slug}/`;

function copyDir(src, dst, stat) {
  for (const e of fs.readdirSync(src, { withFileTypes: true })) {
    if (SKIP.has(e.name) || e.isSymbolicLink()) continue;
    const s = path.join(src, e.name), d = path.join(dst, e.name);
    if (e.isDirectory()) { fs.mkdirSync(d, { recursive: true }); copyDir(s, d, stat); }
    else if (e.isFile()) {
      const size = fs.statSync(s).size;
      if (++stat.files > MAX_FILES || (stat.bytes += size) > MAX_BYTES) throw new Error('Сайт слишком большой (лимит 800 файлов / 40 МБ)');
      fs.copyFileSync(s, d);
    }
  }
}

export function deploySite(user, { name, title, dir, files, spa, kind = 'site' }, cwd) {
  let slug = slugify(name);
  const prev = db.prepare('SELECT user_id FROM sites WHERE slug=?').get(slug);
  if (prev && prev.user_id !== user.id) slug = `${slug}-${crypto.randomBytes(2).toString('hex')}`;
  const tmp = path.join(ROOT, `.tmp-${crypto.randomBytes(4).toString('hex')}`);
  fs.mkdirSync(tmp, { recursive: true });
  const stat = { files: 0, bytes: 0 };
  try {
    if (files && typeof files === 'object') {
      for (const [p, content] of Object.entries(files)) {
        const rel = path.normalize(String(p)).replace(/^([/\\])+/, '');
        if (rel.startsWith('..')) throw new Error(`Недопустимый путь: ${p}`);
        const dest = path.join(tmp, rel); fs.mkdirSync(path.dirname(dest), { recursive: true });
        const buf = Buffer.from(String(content), /^data:|^base64:/.test(String(content)) ? 'base64' : 'utf8');
        stat.files++; stat.bytes += buf.length; if (stat.files > MAX_FILES || stat.bytes > MAX_BYTES) throw new Error('Сайт слишком большой');
        fs.writeFileSync(dest, buf);
      }
    } else if (dir) {
      const src = path.resolve(cwd, dir);
      if (!fs.existsSync(src) || !fs.statSync(src).isDirectory()) throw new Error(`Папка не найдена: ${dir}`);
      copyDir(src, tmp, stat);
    } else throw new Error('Нужен dir или files');
    if (!fs.existsSync(path.join(tmp, 'index.html'))) {
      const html = fs.readdirSync(tmp).find((f) => /\.html?$/i.test(f));
      if (html) fs.copyFileSync(path.join(tmp, html), path.join(tmp, 'index.html')); else throw new Error('В сайте нет index.html');
    }
    const final = path.join(ROOT, slug);
    fs.rmSync(final, { recursive: true, force: true });
    fs.renameSync(tmp, final);
  } catch (e) { fs.rmSync(tmp, { recursive: true, force: true }); throw e; }
  const t = now();
  db.prepare(`INSERT INTO sites(slug,user_id,title,kind,spa,size,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)
    ON CONFLICT(slug) DO UPDATE SET title=excluded.title, kind=excluded.kind, spa=excluded.spa, size=excluded.size, updated_at=excluded.updated_at`)
    .run(slug, user.id, String(title || name).slice(0, 80), kind, spa ? 1 : 0, stat.bytes, t, t);
  return { slug, url: siteUrl(slug), files: stat.files, bytes: stat.bytes };
}

export const listSites = (uid) => db.prepare('SELECT slug,title,kind,size,created_at,updated_at FROM sites WHERE user_id=? ORDER BY updated_at DESC').all(uid)
  .map((s) => ({ slug: s.slug, title: s.title, kind: s.kind, size: s.size, url: siteUrl(s.slug), updatedAt: s.updated_at }));
export function deleteSite(uid, slug) {
  const r = db.prepare('DELETE FROM sites WHERE slug=? AND user_id=?').run(slugify(slug), uid);
  if (r.changes) fs.rmSync(path.join(ROOT, slugify(slug)), { recursive: true, force: true });
  return r.changes > 0;
}

/** Публичная раздача (без авторизации): /s/<slug>/… */
export function mountSites(app) {
  // редирект только если в пути НЕТ завершающего «/» (иначе Express считает оба пути одним маршрутом → бесконечный цикл)
  app.get('/s/:slug', (req, res, next) => {
    if (req.path.endsWith('/')) return next();
    const q = req.originalUrl.includes('?') ? req.originalUrl.slice(req.originalUrl.indexOf('?')) : '';
    res.redirect(301, `/s/${req.params.slug}/${q}`);
  });
  app.use('/s/:slug', (req, res, next) => {
    const slug = slugify(req.params.slug);
    const row = db.prepare('SELECT spa FROM sites WHERE slug=?').get(slug);
    const dir = path.join(ROOT, slug);
    if (!row || !fs.existsSync(dir)) return res.status(404).type('html').send('<h3 style="font-family:sans-serif">Сайт не найден</h3>');
    res.set({ 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-cache', 'Referrer-Policy': 'no-referrer' });
    express.static(dir, { index: 'index.html', extensions: ['html'], dotfiles: 'ignore' })(req, res, () => {
      if (row.spa && req.method === 'GET' && !path.extname(req.path)) return res.sendFile(path.join(dir, 'index.html'));
      next();
    });
  });
}
