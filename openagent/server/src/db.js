import Database from 'better-sqlite3';
import fs from 'node:fs';
import path from 'node:path';
import { config } from './config.js';

fs.mkdirSync(config.dataDir, { recursive: true });
fs.mkdirSync(config.workspacesDir, { recursive: true });

export const db = new Database(path.join(config.dataDir, 'openagent.db'));
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');
db.pragma('synchronous = NORMAL');
db.pragma('cache_size = -32000');
db.pragma('temp_store = MEMORY');
db.pragma('mmap_size = 134217728');
db.pragma('busy_timeout = 5000');

db.exec(`
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  name TEXT,
  role TEXT NOT NULL DEFAULT 'user',
  github_token TEXT,
  github_login TEXT,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS otps (
  email TEXT PRIMARY KEY,
  code_hash TEXT NOT NULL,
  expires INTEGER NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  sent_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT 'Новый чат',
  summary TEXT NOT NULL DEFAULT '',
  summarized_upto INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY,
  conv_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  tool_calls TEXT,
  tool_call_id TEXT,
  tool_name TEXT,
  attachments TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conv_id, id);
CREATE TABLE IF NOT EXISTS files (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  mime TEXT NOT NULL,
  size INTEGER NOT NULL,
  path TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'fact',
  importance REAL NOT NULL DEFAULT 0.5,
  embedding BLOB,
  uses INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  last_used INTEGER
);
CREATE INDEX IF NOT EXISTS idx_mem_user ON memories(user_id);
CREATE TABLE IF NOT EXISTS providers (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  base_url TEXT NOT NULL,
  api_key TEXT NOT NULL,
  effort_param INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS schedules (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  prompt TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'code',
  every_min INTEGER,
  next_run INTEGER,
  enabled INTEGER NOT NULL DEFAULT 1,
  last_run INTEGER,
  runs INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS skills (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL,
  UNIQUE(user_id, name)
);
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(content, tokenize='unicode61 remove_diacritics 2');
`);

const ucols = db.prepare('PRAGMA table_info(users)').all().map((c) => c.name);
if (!ucols.includes('voice_id')) db.exec('ALTER TABLE users ADD COLUMN voice_id TEXT');
if (!ucols.includes('voice_name')) db.exec('ALTER TABLE users ADD COLUMN voice_name TEXT');
const pcols = db.prepare('PRAGMA table_info(providers)').all().map((c) => c.name);
if (!pcols.includes('extra_models')) db.exec("ALTER TABLE providers ADD COLUMN extra_models TEXT NOT NULL DEFAULT ''");
if (!ucols.includes('instructions')) db.exec("ALTER TABLE users ADD COLUMN instructions TEXT NOT NULL DEFAULT ''");
const scols = db.prepare('PRAGMA table_info(skills)').all().map((c) => c.name);
if (!scols.includes('source')) db.exec('ALTER TABLE skills ADD COLUMN source TEXT');
db.exec(`CREATE TABLE IF NOT EXISTS usage (
  user_id INTEGER NOT NULL, day TEXT NOT NULL, prompt INTEGER NOT NULL DEFAULT 0, completion INTEGER NOT NULL DEFAULT 0, calls INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, day)
)`);
db.exec(`
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  slug TEXT NOT NULL,
  repo TEXT,
  created_at INTEGER NOT NULL,
  UNIQUE(user_id, slug)
);
CREATE TABLE IF NOT EXISTS prompts (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  text TEXT NOT NULL,
  UNIQUE(user_id, name)
);
`);
const mcols = db.prepare('PRAGMA table_info(messages)').all().map((c) => c.name);
if (!mcols.includes('ctx')) db.exec('ALTER TABLE messages ADD COLUMN ctx TEXT');
const sch = db.prepare('PRAGMA table_info(schedules)').all().map((c) => c.name);
if (!sch.includes('hook_token')) db.exec('ALTER TABLE schedules ADD COLUMN hook_token TEXT');
const ucs = db.prepare('PRAGMA table_info(usage)').all().map((c) => c.name);
if (!ucs.includes('cached')) db.exec('ALTER TABLE usage ADD COLUMN cached INTEGER NOT NULL DEFAULT 0');
const cols = db.prepare('PRAGMA table_info(conversations)').all().map((c) => c.name);
if (!cols.includes('digest_upto')) db.exec('ALTER TABLE conversations ADD COLUMN digest_upto INTEGER NOT NULL DEFAULT 0');
if (!cols.includes('tools')) db.exec("ALTER TABLE conversations ADD COLUMN tools TEXT NOT NULL DEFAULT ''");
if (!cols.includes('project_id')) db.exec('ALTER TABLE conversations ADD COLUMN project_id INTEGER');
if (!cols.includes('persona')) db.exec("ALTER TABLE conversations ADD COLUMN persona TEXT NOT NULL DEFAULT ''");
if (!cols.includes('pinned')) db.exec('ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0');
if (!cols.includes('mode')) db.exec("ALTER TABLE conversations ADD COLUMN mode TEXT NOT NULL DEFAULT 'chat'");

export const now = () => Date.now();

try { db.exec('CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conv_id, id); CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at)'); } catch {}

// ---- подключения (MCP), заметки, задачи, секреты, публичные ссылки на чаты ----
db.exec(`
CREATE TABLE IF NOT EXISTS mcp_servers (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, url TEXT NOT NULL, headers TEXT, enabled INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT '', text TEXT NOT NULL DEFAULT '', summary TEXT, source TEXT NOT NULL DEFAULT 'text',
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS todos (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  text TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, due INTEGER, created_at INTEGER NOT NULL, done_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(user_id, done, id DESC);
CREATE TABLE IF NOT EXISTS secrets (
  id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, value TEXT NOT NULL, created_at INTEGER NOT NULL, UNIQUE(user_id, name)
);
CREATE TABLE IF NOT EXISTS shares (
  token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  conv_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE, created_at INTEGER NOT NULL
);
`);
for (const col of ['watch_url TEXT', 'watch_hash TEXT', 'watch_text TEXT']) { try { db.exec(`ALTER TABLE schedules ADD COLUMN ${col}`); } catch {} }

// ---- почта (IMAP/SMTP) и миссии ----
db.exec(`
CREATE TABLE IF NOT EXISTS mail_accounts (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  imap_host TEXT NOT NULL, imap_port INTEGER NOT NULL DEFAULT 993,
  smtp_host TEXT NOT NULL, smtp_port INTEGER NOT NULL DEFAULT 465,
  login TEXT NOT NULL,
  pass TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  UNIQUE(user_id, email)
);
CREATE TABLE IF NOT EXISTS missions (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  goal TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  notes TEXT NOT NULL DEFAULT '',
  every_min INTEGER NOT NULL DEFAULT 60,
  steps INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
`);
try { db.exec('ALTER TABLE schedules ADD COLUMN mission_id INTEGER'); } catch {}
try { db.exec("ALTER TABLE users ADD COLUMN profile TEXT NOT NULL DEFAULT ''"); } catch {}
