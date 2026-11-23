// Контрольные точки: «теневой» git-репозиторий внутри папки проекта (.oa-snap). Не трогает настоящий .git проекта.
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync, execFile } from 'node:child_process';
import crypto from 'node:crypto';
import { config } from './config.js';

/** Репозиторий контрольных точек лежит ВНЕ проекта (DATA_DIR/snaps/<hash>) — не засоряет ls/find/list_dir. Старые .oa-snap внутри проекта продолжают работать. */
const gdir = (dir) => {
  const legacy = path.join(dir, '.oa-snap');
  if (fs.existsSync(path.join(legacy, 'HEAD'))) return legacy;
  return path.join(path.resolve(config.dataDir), 'snaps', crypto.createHash('sha1').update(path.resolve(dir)).digest('hex').slice(0, 16));
};
const EXCLUDE = ['.oa-snap', 'node_modules/', 'build/', '.gradle/', 'dist/', '.next/', '__pycache__/', '.venv/', 'target/', '*.apk', '*.aab', '*.zip', '*.jar', '*.mp4', '*.iso', '.git/'].join('\n') + '\n';

function git(dir, args, opts = {}) {
  const r = spawnSync('git', [`--git-dir=${gdir(dir)}`, `--work-tree=${dir}`, '-c', 'user.name=OpenAgent', '-c', 'user.email=agent@openagent.local', '-c', 'core.quotepath=off', ...args], { encoding: 'utf8', timeout: 30000, maxBuffer: 20e6, ...opts });
  return { ok: r.status === 0, out: (r.stdout || '') + (r.stderr || '') };
}
function ensure(dir) {
  const g = gdir(dir);
  if (!fs.existsSync(path.join(g, 'HEAD'))) {
    fs.mkdirSync(g, { recursive: true });
    git(dir, ['init', '-q', '--template=']);
    fs.mkdirSync(path.join(g, 'info'), { recursive: true });
    fs.writeFileSync(path.join(g, 'info', 'exclude'), EXCLUDE);
  }
}

const gitA = (dir, args) => new Promise((resolve) => execFile('git', [`--git-dir=${gdir(dir)}`, `--work-tree=${dir}`, '-c', 'user.name=OpenAgent', '-c', 'user.email=agent@openagent.local', '-c', 'core.quotepath=off', ...args], { encoding: 'utf8', timeout: 30000, maxBuffer: 20e6 }, (err, stdout, stderr) => resolve({ ok: !err, out: (stdout || '') + (stderr || '') })));
/** Та же контрольная точка, но без блокировки сервера: git работает в отдельном процессе, пока модель уже думает. */
export async function snapshotAsync(dir, message) {
  try {
    if (!fs.existsSync(dir)) return null;
    ensure(dir);
    await gitA(dir, ['add', '-A']);
    const st = (await gitA(dir, ['status', '--porcelain'])).out.trim();
    const first = !(await gitA(dir, ['rev-parse', '--verify', 'HEAD'])).ok;
    if (!st && !first) return null;
    const r = await gitA(dir, ['commit', '-q', '--allow-empty', '-m', String(message).replace(/\s+/g, ' ').slice(0, 120)]);
    if (!r.ok) return null;
    return { hash: (await gitA(dir, ['rev-parse', '--short', 'HEAD'])).out.trim(), changed: st ? st.split('\n').length : 0 };
  } catch { return null; }
}

export function snapshot(dir, message) {
  try {
    if (!fs.existsSync(dir)) return null;
    ensure(dir);
    git(dir, ['add', '-A']);
    const st = git(dir, ['status', '--porcelain']).out.trim();
    const first = !git(dir, ['rev-parse', '--verify', 'HEAD']).ok;
    if (!st && !first) return null;                                   // ничего не изменилось
    const r = git(dir, ['commit', '-q', '--allow-empty', '-m', String(message).replace(/\s+/g, ' ').slice(0, 120)]);
    if (!r.ok) return null;
    return { hash: git(dir, ['rev-parse', '--short', 'HEAD']).out.trim(), changed: st ? st.split('\n').length : 0 };
  } catch { return null; }
}

export function listCheckpoints(dir, limit = 25) {
  try {
    if (!fs.existsSync(path.join(gdir(dir), 'HEAD'))) return [];
    const out = git(dir, ['log', `-${limit}`, '--pretty=format:%h\x1f%s\x1f%ct', '--shortstat']).out;
    const res = []; let cur = null;
    for (const line of out.split('\n')) {
      if (line.includes('\x1f')) { const [hash, subject, ts] = line.split('\x1f'); cur = { hash, subject, ts: +ts * 1000, files: 0, ins: 0, del: 0 }; res.push(cur); }
      else if (cur && /file/.test(line)) { cur.files = +(/(\d+) file/.exec(line)?.[1] || 0); cur.ins = +(/(\d+) insertion/.exec(line)?.[1] || 0); cur.del = +(/(\d+) deletion/.exec(line)?.[1] || 0); }
    }
    return res;
  } catch { return []; }
}

export function checkpointFiles(dir, hash) {
  const r = git(dir, ['show', '--name-status', '--pretty=format:', hash]);
  return r.ok ? r.out.split('\n').filter(Boolean).slice(0, 80).map((l) => ({ code: l.slice(0, 1), file: l.slice(2).trim() })) : [];
}

/** Откат рабочей папки к точке. Перед откатом делается страховочная точка — откат тоже можно отменить. */
export function restore(dir, hash) {
  if (!/^[0-9a-f]{4,40}$/.test(hash)) throw new Error('Некорректная точка');
  ensure(dir);
  snapshot(dir, `Перед откатом к ${hash}`);
  const added = git(dir, ['diff', '--name-only', '--diff-filter=A', hash, 'HEAD']).out.split('\n').filter(Boolean);   // файлы, появившиеся после точки
  const r = git(dir, ['checkout', '-f', hash, '--', '.']);
  if (!r.ok && !/did not match/.test(r.out)) throw new Error(r.out.slice(0, 200));
  for (const f of added) { const p = path.resolve(dir, f); if (p.startsWith(dir + path.sep)) { try { fs.rmSync(p, { force: true }); } catch {} } }
  snapshot(dir, `Откат к ${hash}`);
  return { restored: hash, removed: added.length };
}
