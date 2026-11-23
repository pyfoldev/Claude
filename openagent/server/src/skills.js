// Установка навыков и плагинов с GitHub: поиск репозиториев и импорт SKILL.md / commands / agents в один клик.
import fs from 'node:fs';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { db } from './db.js';
import { workspaceOf } from './workspace.js';

const UA = { 'User-Agent': 'OpenAgent' };
const gh = async (url, token) => {
  const r = await fetch(url.startsWith('http') ? url : `https://api.github.com${url}`, { headers: { ...UA, Accept: 'application/vnd.github+json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }, signal: AbortSignal.timeout(20000) });
  if (r.status === 403 || r.status === 429) throw new Error('Лимит GitHub API — привяжите GitHub в настройках и повторите');
  if (!r.ok) throw new Error(`GitHub ${r.status}`);
  return r.json();
};
const raw = async (owner, repo, ref, p) => {
  const r = await fetch(`https://raw.githubusercontent.com/${owner}/${repo}/${ref}/${p.split('/').map(encodeURIComponent).join('/')}`, { headers: UA, signal: AbortSignal.timeout(20000) });
  if (!r.ok) throw new Error(`raw ${r.status}`);
  return Buffer.from(await r.arrayBuffer());
};

export function parseRepoRef(input) {
  const s = String(input).trim().replace(/\.git$/, '');
  let m = s.match(/github\.com\/([^/\s]+)\/([^/\s#?]+)(?:\/(?:tree|blob)\/([^/\s]+)(?:\/([^\s#?]+))?)?/i);
  if (m) return { owner: m[1], repo: m[2], ref: m[3], sub: (m[4] || '').replace(/\/$/, '') };
  m = s.match(/^([\w.-]+)\/([\w.-]+)(?:@([\w./-]+))?$/);
  if (m) return { owner: m[1], repo: m[2], ref: m[3], sub: '' };
  throw new Error('Укажите репозиторий: owner/repo или ссылку на GitHub');
}

export async function searchRepos(q, token) {
  q = String(q || '').trim();
  const queries = q
    ? [`${q} topic:claude-skills`, `${q} topic:agent-skills`, `${q} topic:claude-code-plugin`, `${q} skills in:name,description`]
    : ['topic:claude-skills', 'topic:agent-skills', 'topic:claude-code-plugin'];
  const seen = new Map();
  const results = await Promise.allSettled(queries.map((x) => gh(`/search/repositories?q=${encodeURIComponent(x)}&sort=stars&order=desc&per_page=12`, token)));
  let limited = null;
  for (const r of results) {
    if (r.status === 'rejected') { limited = r.reason; continue; }
    for (const it of r.value.items || []) if (!seen.has(it.full_name)) seen.set(it.full_name, { repo: it.full_name, description: it.description || '', stars: it.stargazers_count, updated: it.pushed_at, topics: (it.topics || []).slice(0, 5), url: it.html_url });
  }
  if (token && q) { // поиск по файлам SKILL.md (нужен токен)
    try {
      const j = await gh(`/search/code?q=${encodeURIComponent(q + ' filename:SKILL.md')}&per_page=15`, token);
      for (const it of j.items || []) { const n = it.repository.full_name; if (!seen.has(n)) seen.set(n, { repo: n, description: it.repository.description || '', stars: 0, updated: '', topics: [], url: it.repository.html_url }); }
    } catch {}
  }
  if (!seen.size && limited) throw limited;
  return [...seen.values()].sort((a, b) => b.stars - a.stars).slice(0, 25);
}

function frontmatter(md) {
  const m = md.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!m) return { meta: {}, body: md };
  const meta = {};
  for (const line of m[1].split(/\r?\n/)) { const k = line.match(/^([\w-]+):\s*(.*)$/); if (k) meta[k[1]] = k[2].replace(/^["']|["']$/g, '').trim(); }
  return { meta, body: m[2] };
}
const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9а-яё._-]+/gi, '-').replace(/^-+|-+$/g, '').slice(0, 50) || 'skill';

async function fetchRepoDir(owner, repo, ref, token) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'oa-gh-'));
  const zip = path.join(tmp, 'r.zip');
  const url = token ? `https://api.github.com/repos/${owner}/${repo}/zipball/${ref || ''}` : `https://codeload.github.com/${owner}/${repo}/zip/${ref || 'HEAD'}`;
  const r = await fetch(url, { headers: { ...UA, ...(token ? { Authorization: `Bearer ${token}` } : {}) }, redirect: 'follow', signal: AbortSignal.timeout(90000) });
  if (!r.ok) throw new Error(r.status === 404 ? 'Репозиторий или ветка не найдены (для приватных привяжите GitHub)' : `GitHub ${r.status}`);
  const len = +r.headers.get('content-length') || 0;
  if (len > 150e6) throw new Error('Репозиторий слишком большой (>150 МБ)');
  fs.writeFileSync(zip, Buffer.from(await r.arrayBuffer()));
  const u = spawnSync('unzip', ['-q', '-o', zip, '-d', path.join(tmp, 'x')], { timeout: 60000 });
  if (u.status !== 0 && u.status !== 1) throw new Error('Не удалось распаковать архив (нужен unzip на сервере)');
  const top = fs.readdirSync(path.join(tmp, 'x'));
  return { tmp, root: top.length === 1 ? path.join(tmp, 'x', top[0]) : path.join(tmp, 'x') };
}
function walkAll(root, limit = 30000) {
  const out = []; const stack = [''];
  while (stack.length && out.length < limit) {
    const rel = stack.pop(); let ents;
    try { ents = fs.readdirSync(path.join(root, rel), { withFileTypes: true }); } catch { continue; }
    for (const e of ents) {
      if (e.name === '.git' || e.name === 'node_modules') continue;
      const p = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) stack.push(p); else if (e.isFile()) out.push({ path: p, size: fs.statSync(path.join(root, p)).size });
    }
  }
  return out;
}

export async function installFromGithub(user, input, token) {
  const { owner, repo, ref, sub } = parseRepoRef(input);
  const { tmp, root } = await fetchRepoDir(owner, repo, ref, token);
  try {
    const all = walkAll(root);
    const files = all.filter((t) => !sub || t.path === sub || t.path.startsWith(sub + '/'));
    const source = `${owner}/${repo}`;
    const ws = workspaceOf(user.id);
    const targets = [];
    for (const t of files) {
      const base = path.posix.basename(t.path).toLowerCase();
      if (base === 'skill.md') targets.push({ mdPath: t.path, dir: path.posix.dirname(t.path), kind: 'skill' });
      else if (/(^|\/)(commands|agents)\/[^/]+\.md$/i.test(t.path)) targets.push({ mdPath: t.path, dir: null, kind: /(^|\/)agents\//i.test(t.path) ? 'agent' : 'command' });
    }
    const out = { repo: source, installed: [], skipped: [] };
    const put = (name, desc, content) => db.prepare('INSERT INTO skills(user_id,name,description,content,source) VALUES (?,?,?,?,?) ON CONFLICT(user_id,name) DO UPDATE SET description=excluded.description, content=excluded.content, source=excluded.source')
      .run(user.id, name, desc.slice(0, 200), content.slice(0, 60000), source);
    for (const t of targets.slice(0, 60)) {
      try {
        const md = fs.readFileSync(path.join(root, t.mdPath), 'utf8');
        const { meta, body } = frontmatter(md);
        const dirName = t.dir && t.dir !== '.' ? path.posix.basename(t.dir) : path.posix.basename(t.mdPath, '.md');
        const base = slug(meta.name || dirName);
        const name = t.kind === 'skill' ? base : `${t.kind}-${base}`;
        let content = body.trim();
        if (t.kind === 'skill' && t.dir && t.dir !== '.') {
          const sibs = files.filter((x) => x.path.startsWith(t.dir + '/') && x.path !== t.mdPath && x.size < 500000).slice(0, 60);
          if (sibs.length) {
            const dest = path.join(ws, 'skills', name);
            for (const x of sibs) { const p = path.join(dest, x.path.slice(t.dir.length + 1)); fs.mkdirSync(path.dirname(p), { recursive: true }); fs.copyFileSync(path.join(root, x.path), p); }
            content += `\n\n---\n[Файлы навыка лежат в ${dest}]\n` + sibs.map((x) => `- ${x.path.slice(t.dir.length + 1)}`).join('\n');
          }
        }
        if (!content) { out.skipped.push(`${t.mdPath} (пусто)`); continue; }
        put(name, meta.description || body.split('\n').find((l) => l.trim() && !l.startsWith('#')) || name, content);
        out.installed.push(name);
      } catch (e) { out.skipped.push(`${t.mdPath}: ${e.message}`); }
    }
    if (!out.installed.length) {
      const readme = files.find((t) => /^readme(\.md)?$/i.test(path.posix.basename(t.path)) && path.posix.dirname(t.path) === (sub || '.'));
      if (readme) {
        const md = fs.readFileSync(path.join(root, readme.path), 'utf8').slice(0, 30000);
        put(slug(repo), md.split('\n').find((l) => l.trim() && !l.startsWith('#')) || `README ${source}`, md);
        out.installed.push(slug(repo)); out.note = 'SKILL.md не найден — добавлен README как справочный навык';
      }
    }
    return out;
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
}
