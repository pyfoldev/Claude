// Сравнение моделей river.ai: кодинг (запуск тестов), решение задач (точный ответ), зрение (картинка).
// Запуск: RIVER_API_KEY=... node scripts/bench.mjs [model1,model2]
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';

const BASE = process.env.RIVER_BASE_URL || 'https://api.river.ai/v1';
const KEY = process.env.RIVER_API_KEY;
const only = process.argv[2]?.split(',');

async function chat(model, content, opts = {}) {
  let r;
  for (let attempt = 0; attempt < 7; attempt++) {
    r = await chat1(model, content, opts);
    if (!r.err || !/rate|429|overload/i.test(r.err)) return r;
    await new Promise((res) => setTimeout(res, 6000 * (attempt + 1)));
  }
  return r;
}
async function chat1(model, content, { max = 6000 } = {}) {
  const t0 = Date.now();
  try {
    const r = await fetch(`${BASE}/chat/completions`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${KEY}` },
      body: JSON.stringify({ model, temperature: 0, max_tokens: max, messages: [{ role: 'user', content }] }), signal: AbortSignal.timeout(240000) });
    const j = await r.json();
    if (!r.ok) return { err: JSON.stringify(j).slice(0, 150), ms: Date.now() - t0 };
    return { text: j.choices?.[0]?.message?.content || '', ms: Date.now() - t0, tokens: j.usage?.completion_tokens };
  } catch (e) { return { err: e.message, ms: Date.now() - t0 }; }
}

const CODE = [
  ['lru', 'Реализуй на Python класс LRUCache(capacity) с методами get(key)->значение или -1 и put(key, value). Операции за O(1).',
   `c=LRUCache(2);c.put(1,1);c.put(2,2);assert c.get(1)==1;c.put(3,3);assert c.get(2)==-1;c.put(4,4);assert c.get(1)==-1;assert c.get(3)==3;assert c.get(4)==4`],
  ['roman', 'Напиши на Python функции to_roman(n) для 1..3999 и from_roman(s).',
   `assert to_roman(1994)=='MCMXCIV';assert to_roman(3999)=='MMMCMXCIX';assert from_roman('MCMXCIV')==1994;assert all(from_roman(to_roman(i))==i for i in range(1,4000))`],
  ['intervals', 'Напиши на Python функцию merge(intervals): объединяет пересекающиеся и соприкасающиеся отрезки [[a,b],...], возвращает отсортированный список списков.',
   `assert merge([[1,3],[2,6],[8,10],[15,18]])==[[1,6],[8,10],[15,18]];assert merge([[1,4],[4,5]])==[[1,5]];assert merge([])==[];assert merge([[5,6],[1,2]])==[[1,2],[5,6]]`],
  ['calc', 'Напиши на Python функцию calc(s): вычисляет арифметическое выражение со скобками, + - * / (деление float), унарным минусом и пробелами. Без eval/ast.',
   `assert calc('1 + 2 * 3')==7;assert calc('(1+2)*3')==9;assert calc('-(2+3)*2')==-10;assert abs(calc('10/4')-2.5)<1e-9;assert calc(' 2*(3+(4-1))*-1 ')==-12`],
  ['toposort', 'Напиши на Python функцию topo(n, edges): топологическая сортировка вершин 0..n-1 по рёбрам (u,v) u->v. Верни список порядка или None при цикле.',
   `o=topo(4,[(0,1),(1,2),(0,3),(3,2)]);assert o is not None and o.index(0)<o.index(1)<o.index(2) and o.index(0)<o.index(3)<o.index(2) and sorted(o)==[0,1,2,3];assert topo(3,[(0,1),(1,2),(2,0)]) is None;assert sorted(topo(3,[]))==[0,1,2]`],
  ['dijkstra', 'Напиши на Python функцию dijkstra(n, edges, src): edges=[(u,v,w)] ориентированные, возвращает список кратчайших расстояний до всех вершин (float("inf") если недостижимо).',
   `d=dijkstra(5,[(0,1,4),(0,2,1),(2,1,2),(1,3,1),(2,3,5)],0);assert d[:4]==[0,3,1,4] and d[4]==float('inf')`],
  ['lps', 'Напиши на Python функцию lps(s): самая длинная палиндромная подстрока (если несколько — самая левая).',
   `assert lps('babad')=='bab';assert lps('cbbd')=='bb';assert lps('a')=='a';assert lps('forgeeksskeegfor')=='geeksskeeg'`],
  ['bugfix', `Исправь баг. Функция должна возвращать k-й по величине (1-й = максимум) элемент списка БЕЗ учёта повторов:\n\ndef kth(nums, k):\n    nums.sort()\n    return nums[k]\n\nВерни исправленную функцию kth на Python (не мутируй входной список).`,
   `a=[3,1,4,1,5,9,2,6,5,3,5];assert kth(a,1)==9;assert kth(a,3)==5;assert kth(a,7)==1;assert a==[3,1,4,1,5,9,2,6,5,3,5]`],
];

const py = (code) => spawnSync('python3', ['-c', code], { encoding: 'utf8' }).stdout.trim();
const SOLVE = [
  ['sum35', 'Найди сумму всех натуральных n < 1000, которые делятся на 3 или на 5, но НЕ делятся на 15.', py('print(sum(n for n in range(1,1000) if (n%3==0 or n%5==0) and n%15!=0))')],
  ['dice', 'Бросают два правильных кубика. Какова вероятность, что сумма очков — простое число? Ответ — несократимая дробь a/b.', '5/12'],
  ['inradius', 'Треугольник со сторонами 13, 14, 15. Найди радиус вписанной окружности.', '4'],
  ['divisors', 'Сколько натуральных делителей у числа 720?', '30'],
  ['mississippi', 'Сколько различных слов можно составить перестановкой всех букв слова MISSISSIPPI?', '34650'],
  ['integral', 'Вычисли определённый интеграл от 0 до 1 функции x·e^x dx. Ответ — число.', '1'],
  ['last2', 'Найди последние две цифры числа 7^2025. Ответ — двузначная строка.', '07'],
  ['coprime', 'Сколько целых чисел от 1 до 1000 не делятся ни на 2, ни на 3, ни на 5?', py('print(sum(1 for n in range(1,1001) if n%2 and n%3 and n%5))')],
  ['trains', 'Из A в B (расстояние 360 км) одновременно навстречу выезжают два поезда: 70 км/ч и 50 км/ч. Через сколько минут они встретятся? Ответ — целое число минут.', '180'],
  ['logic', 'У Анны, Бориса и Веры по одному питомцу: кошка, собака, попугай (у каждого свой). Анна не держит собаку. Борис не держит ни кошку, ни собаку. Вера не держит кошку. Кто держит собаку? Ответ — одно имя.', 'Вера'],
  ['fib', 'Пусть F(1)=F(2)=1, F(n)=F(n-1)+F(n-2). Найди F(30) mod 1000. Ответ — число.', py('a,b=1,1\nfor _ in range(29): a,b=b,a+b\nprint(a%1000)')],
  ['geom', 'В прямоугольнике 6×8 проведена диагональ. Найди площадь круга, описанного вокруг прямоугольника, делённую на π. Ответ — число.', '25'],
  ['sumdigits', 'Найди сумму цифр числа 2^100. Ответ — число.', py('print(sum(map(int,str(2**100))))')],
  ['probcard', 'Из колоды 52 карты берут 5 карт без возвращения. Сколько существует способов выбрать ровно 2 туза? Ответ — число.', py('from math import comb;print(comb(4,2)*comb(48,3))')],
];

const norm = (s) => String(s).toLowerCase().replace(/\s+/g, '').replace(/[.,;]$/, '').replace(/,/g, '.');
function checkAnswer(text, exp) {
  const m = [...text.matchAll(/ANSWER:\s*([^\n]+)/gi)].pop();
  if (!m) return false;
  const a = norm(m[1].replace(/[*`$\\]/g, '').replace(/^=+/, '').replace(/\\?frac\{(\d+)\}\{(\d+)\}/, '$1/$2'));
  return a === norm(exp) || a.endsWith('=' + norm(exp)) || a.replace(/[^0-9a-zа-я./]/g, '') === norm(exp);
}
function runCode(text, tests) {
  const m = [...text.matchAll(/```(?:python|py)?\n([\s\S]*?)```/g)].pop();
  if (!m) return false;
  const r = spawnSync('python3', ['-c', m[1] + '\n' + tests], { encoding: 'utf8', timeout: 15000 });
  return r.status === 0;
}

// картинка для vision-теста
fs.writeFileSync('/tmp/vision.png', Buffer.from(spawnSync('python3', ['-c', `
from PIL import Image, ImageDraw
import sys
im=Image.new('RGB',(400,300),'white'); d=ImageDraw.Draw(im)
d.ellipse((40,60,200,220),fill=(220,30,30)); d.rectangle((230,90,360,220),fill=(30,60,220))
d.text((110,130),'42',fill='white'); d.text((270,150),'7',fill='white')
im.save(sys.stdout.buffer,'PNG')`], { maxBuffer: 1e7 }).stdout));
const IMG = 'data:image/png;base64,' + fs.readFileSync('/tmp/vision.png').toString('base64');
async function vision(model) {
  const t0 = Date.now();
  try {
    const r = await fetch(`${BASE}/chat/completions`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${KEY}` },
      body: JSON.stringify({ model, max_tokens: 3000, messages: [{ role: 'user', content: [{ type: 'text', text: 'На картинке две фигуры с числами. Назови цвет и форму каждой фигуры и число на ней.' }, { type: 'image_url', image_url: { url: IMG } }] }] }), signal: AbortSignal.timeout(120000) });
    const j = await r.json();
    if (!r.ok) return { ok: false, note: 'ошибка ' + r.status, ms: Date.now() - t0 };
    const t = (j.choices?.[0]?.message?.content || '').toLowerCase();
    const ok = /42/.test(t) && /7/.test(t) && /(красн|red)/.test(t) && /(син|blue)/.test(t);
    return { ok, note: ok ? 'видит' : 'не видит/ошибся', ms: Date.now() - t0 };
  } catch (e) { return { ok: false, note: e.message, ms: Date.now() - t0 }; }
}

async function pool(items, n, fn) {
  const out = []; let i = 0;
  await Promise.all(Array.from({ length: n }, async () => { while (i < items.length) { const k = i++; out[k] = await fn(items[k]); } }));
  return out;
}

const models = (await (await fetch(`${BASE}/models`, { headers: { Authorization: `Bearer ${KEY}` } })).json()).data.map((m) => m.id).filter((m) => !only || only.includes(m));
const results = [];
for (const model of models) {
  const t0 = Date.now();
  const code = await pool(CODE, +(process.env.BENCH_CONC || 2), async ([id, task, tests]) => {
    const r = await chat(model, `${task}\n\nВерни ТОЛЬКО один блок кода \`\`\`python с полным решением, без примеров запуска.`);
    return { id, ok: r.text ? runCodeSafe(r.text, tests) : false, ms: r.ms, err: r.err };
  });
  const solve = await pool(SOLVE, +(process.env.BENCH_CONC || 2), async ([id, q, exp]) => {
    const r = await chat(model, `${q}\n\nРеши аккуратно и проверь. В последней строке напиши: ANSWER: <только итоговое значение>`);
    return { id, ok: r.text ? checkAnswer(r.text, exp) : false, ms: r.ms, err: r.err, got: (r.text || '').match(/ANSWER:\s*([^\n]+)/gi)?.pop(), exp };
  });
  const vis = await vision(model);
  const avg = (a) => Math.round(a.reduce((s, x) => s + x.ms, 0) / a.length / 100) / 10;
  const res = { model, code: code.filter((x) => x.ok).length + '/' + code.length, solve: solve.filter((x) => x.ok).length + '/' + solve.length, vision: vis.ok, visionNote: vis.note,
    codeAvgSec: avg(code), solveAvgSec: avg(solve), errors: [...code, ...solve].filter((x) => x.err).length, failedSolve: solve.filter((x) => !x.ok).map((x) => `${x.id}(${x.got || x.err || 'нет ответа'}≠${x.exp})`), failedCode: code.filter((x) => !x.ok).map((x) => x.id), totalSec: Math.round((Date.now() - t0) / 1000) };
  console.log(JSON.stringify(res));
  results.push(res);
}
function runCodeSafe(t, tests) { try { return runCode(t, tests); } catch { return false; } }
fs.writeFileSync(process.env.BENCH_OUT || '/tmp/bench.json', JSON.stringify(results, null, 2));
