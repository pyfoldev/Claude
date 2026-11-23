// MCP-сервер (stdio) с инструментами OpenAgent для движка opencode: публикация сайтов, файлы пользователю, документы, графики, картинки, поиск, память.
// Запускается самим opencode (см. opencodeEngine.js). Пользователь — OA_UID. Файлы/картинки, которые нужно показать в чате, возвращаются маркером [[OA_FILE:{json}]].
import readline from 'node:readline';
import { db } from './db.js';
import { runTool, voiceFunction } from './tools.js';
import { workspaceOf } from './workspace.js';
import { isOwnerEmail } from './config.js';

const NAMES = ['ask_user', 'web_search', 'lookup', 'deploy_site', 'send_file', 'create_file', 'edit_document', 'html_app', 'chart', 'plot_function', 'diagram', 'draw_svg', 'generate_image', 'memory_save', 'memory_search'];
const user = db.prepare('SELECT * FROM users WHERE id=?').get(+process.env.OA_UID || 0);
if (user) user.role = isOwnerEmail(user.email) ? 'owner' : 'user';

const defs = NAMES.map((n) => {
  const f = voiceFunction(n); if (!f) return null;
  const schema = JSON.parse(JSON.stringify(f.parameters));
  let description = f.description;
  if (n === 'deploy_site') {
    schema.properties.confirmed_by_user = { type: 'boolean', description: 'true ТОЛЬКО если пользователь прямо попросил опубликовать/задеплоить сайт' };
    description += ' Пути (dir, send_file path) — АБСОЛЮТНЫЕ. Публиковать только по прямой просьбе пользователя.';
  }
  if (n === 'ask_user') description += ' После вызова СРАЗУ заверши ответ — дождись выбора пользователя.';
  if (n === 'send_file') description += ' path — абсолютный.';
  return { name: n, description, inputSchema: schema };
}).filter(Boolean);

const out = (o) => process.stdout.write(JSON.stringify({ jsonrpc: '2.0', ...o }) + '\n');

async function call(name, args) {
  if (!user) return 'Ошибка: пользователь не найден';
  const files = [];
  const ctx = { cwd: workspaceOf(user.id), autonomy: 'auto', userText: args?.confirmed_by_user ? 'опубликуй сайт' : '', attach: (f) => files.push(f), onOutput() {}, endTurn() {}, signal: AbortSignal.timeout(180000) };
  const text = String(await runTool(user, name, args || {}, ctx));
  return text + files.map((f) => `\n[[OA_FILE:${JSON.stringify(f)}]]`).join('');
}

readline.createInterface({ input: process.stdin }).on('line', async (line) => {
  let m; try { m = JSON.parse(line); } catch { return; }
  if (m.method === 'initialize') return out({ id: m.id, result: { protocolVersion: m.params?.protocolVersion || '2024-11-05', capabilities: { tools: {} }, serverInfo: { name: 'openagent', version: '1.0.0' } } });
  if (m.method === 'tools/list') return out({ id: m.id, result: { tools: defs } });
  if (m.method === 'tools/call') {
    try { const t = await call(m.params?.name, m.params?.arguments); out({ id: m.id, result: { content: [{ type: 'text', text: t }] } }); }
    catch (e) { out({ id: m.id, result: { content: [{ type: 'text', text: `Ошибка: ${e.message}` }], isError: true } }); }
    return;
  }
  if (m.id !== undefined && m.method) out({ id: m.id, error: { code: -32601, message: 'method not found' } });
});
