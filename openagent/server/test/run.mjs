import fs from 'node:fs';
import { mkUser, mkConv, runOnce, codeDir } from './harness.mjs';
import { CODE, CHAT, CODE_HARD, CHAT_HARD, CODE_STRESS } from './tasks.mjs';
const HARD = process.env.HARD === '1';
const which = process.argv[2] || 'all', only = process.argv[3];
const user = mkUser();
const rows = [];
for (const [mode, list] of (process.env.STRESS === '1' ? [['code', CODE_STRESS]] : [['code', HARD ? CODE_HARD : CODE], ['chat', HARD ? CHAT_HARD : CHAT]])) {
  if (which !== 'all' && which !== mode) continue;
  for (const t of list) {
    if (only && !t.id.includes(only)) continue;
    const conv = mkConv(user, mode);
    const dir = codeDir(user.id, conv.id);
    t.setup?.(dir);
    const r = await runOnce(user, conv, t.text, { effort: 'auto' });
    let verdict; try { verdict = t.check(r, dir); } catch (e) { verdict = 'check error ' + e.message; }
    const pass = verdict === true, stepsOk = r.steps <= t.maxSteps;
    rows.push({ id: t.id, pass, steps: r.steps, maxSteps: t.maxSteps, stepsOk, sec: +(r.ms / 1000).toFixed(1), tools: r.tools.map((x) => x.name).join(','), why: pass ? '' : verdict, err: r.err });
    console.log(`${pass ? 'PASS' : 'FAIL'} ${stepsOk ? '    ' : 'STEP'} ${t.id.padEnd(20)} steps=${r.steps}/${t.maxSteps} ${(r.ms / 1000).toFixed(1)}s tools=[${rows.at(-1).tools}] ${pass ? '' : '— ' + verdict} ${r.err ? 'ERR ' + r.err : ''}`);
    if (process.env.VERBOSE) console.log('   ANSWER:', r.answer.slice(0, 400).replace(/\n/g, ' '));
  }
}
const p = rows.filter((x) => x.pass).length;
console.log(`\nИТОГО: ${p}/${rows.length} прошли; в лимит шагов: ${rows.filter((x) => x.stepsOk).length}/${rows.length}; среднее ${(rows.reduce((s, x) => s + x.sec, 0) / rows.length).toFixed(1)}s`);
fs.writeFileSync(process.env.OUT || '/tmp/claude-0/scr/last.json', JSON.stringify(rows, null, 1));
process.exit(0);
