import fs from 'node:fs';
import path from 'node:path';
import { config } from './config.js';

export function workspaceOf(userId) {
  const dir = path.resolve(config.workspacesDir, String(userId));
  fs.mkdirSync(path.join(dir, 'uploads'), { recursive: true });
  const mem = path.join(dir, 'MEMORY.md');
  if (!fs.existsSync(mem)) fs.writeFileSync(mem, '# Заметки агента\n\nЭтот файл читается в начале каждого чата. Записывай сюда важные инструкции, команды сборки и соглашения.\n');
  return dir;
}

export function askpassPath() {
  const p = path.resolve(config.dataDir, 'git-askpass.sh');
  if (!fs.existsSync(p)) {
    fs.writeFileSync(p, '#!/bin/sh\ncase "$1" in Username*) echo x-access-token;; *) echo "$GITHUB_TOKEN";; esac\n', { mode: 0o755 });
  }
  return p;
}

/** Owner видит весь диск, остальные — только свою рабочую папку. */
export function resolvePath(user, p, base) {
  const ws = workspaceOf(user.id);
  const abs = path.resolve(base || ws, p || '.');
  if (user.role !== 'owner' && abs !== ws && !abs.startsWith(ws + path.sep)) {
    throw new Error('Доступ вне рабочей папки запрещён');
  }
  return abs;
}

/** Папка проекта для режима Code: у каждого code-чата своя. */
export function codeDir(userId, convId) {
  const d = path.join(workspaceOf(userId), 'code', String(convId));
  fs.mkdirSync(d, { recursive: true });
  return d;
}

/** Постоянная папка проекта (общая для всех Code-чатов проекта). */
export function projectDir(userId, slug) {
  const d = path.join(workspaceOf(userId), 'projects', slug);
  fs.mkdirSync(d, { recursive: true });
  return d;
}
