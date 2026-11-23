// Проверка чисел в ответе малой модели обычным алгоритмом: время будильника, длительность таймера/напоминания, уровни громкости/яркости.
// Модель арифметику времени делает неточно («без четверти девять» → 5:15), а ошибка в будильнике выполнялась бы молча.
// Правило: параметры сверяются с независимым разбором фразы; не совпало или разобрать не удалось → команду берёт большая модель.
const W = { ноль: 0, один: 1, одна: 1, одну: 1, одно: 1, два: 2, две: 2, три: 3, четыре: 4, пять: 5, шесть: 6, семь: 7, восемь: 8, девять: 9, десять: 10, одиннадцать: 11, двенадцать: 12, тринадцать: 13, четырнадцать: 14, пятнадцать: 15, шестнадцать: 16, семнадцать: 17, восемнадцать: 18, девятнадцать: 19, двадцать: 20, тридцать: 30, сорок: 40, пятьдесят: 50, шестьдесят: 60, семьдесят: 70, восемьдесят: 80, девяносто: 90, сто: 100 };
const ORD = { первого: 1, второго: 2, третьего: 3, четвертого: 4, пятого: 5, шестого: 6, седьмого: 7, восьмого: 8, девятого: 9, десятого: 10, одиннадцатого: 11, двенадцатого: 12 };
const norm = (t) => String(t).toLowerCase().replace(/ё/g, 'е').replace(/[,!?;]+/g, ' ').replace(/\s+/g, ' ').trim();

/** Токены → числа: цифры и слова («двадцать пять» = 25). Возвращает [{v, i, j}] — значение и диапазон токенов. */
function numbers(toks) {
  const out = [];
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i];
    if (/^\d+$/.test(t)) { out.push({ v: +t, i, j: i + 1 }); continue; }
    if (t in W) {
      let v = W[t], j = i + 1;
      if (v >= 20 && v < 100 && v % 10 === 0 && j < toks.length && toks[j] in W && W[toks[j]] >= 1 && W[toks[j]] <= 9) { v += W[toks[j]]; j++; }
      out.push({ v, i, j }); i = j - 1;
    }
  }
  return out;
}
const UNIT = (t) => /^час(а|ов|у)?$/.test(t) ? 3600 : /^мин(ут|уты|уту|ута|ут[ыуа])?$/.test(t) || /^минут/.test(t) ? 60 : /^сек(унд|унды|унду|унда)?$/.test(t) || /^секунд/.test(t) ? 1 : /^м$/.test(t) ? 60 : 0;

/** «10 минут», «полтора часа», «час тридцать минут», «две минуты тридцать секунд» → секунды (или null) */
export function parseDuration(text) {
  let s = norm(text);
  const special = [[/(?:^| )(полчаса|пол часа|половину часа)(?= |$)/, 1800], [/(?:^| )полтора часа(?= |$)/, 5400], [/(?:^| )(полторы минуты)(?= |$)/, 90], [/(?:^| )(полминуты|пол минуты)(?= |$)/, 30],
    [/(?:^| )три четверти часа(?= |$)/, 2700], [/(?:^| )четверть часа(?= |$)/, 900], [/(?:^| )два с половиной часа(?= |$)/, 9000]];
  for (const [re, v] of special) if (re.test(s)) return v;
  let dm;
  if ((dm = /(\d+)\.5 час/.exec(s))) return +dm[1] * 3600 + 1800;
  if ((dm = /(\d+)\.5 мин/.exec(s))) return +dm[1] * 60 + 30;
  const toks = s.split(' ');
  const nums = numbers(toks);
  let total = 0, found = false, used = new Set();
  for (let k = 0; k < toks.length; k++) {
    const u = UNIT(toks[k]); if (!u) continue;
    const prev = nums.find((n) => n.j === k && !used.has(n.i));
    if (prev) { total += prev.v * u; used.add(prev.i); } else if (/^(час|минуту|секунду)$/.test(toks[k])) total += u;   // «час», «минуту» без числа = 1
    else continue;
    found = true;
  }
  const m = /(?:^|\D)(\d+) ?м(?: |$)/.exec(s); if (!found && m) return +m[1] * 60;
  return found && total > 0 ? total : null;
}

const PERIOD = { утра: 'am', дня: 'day', вечера: 'pm', ночи: 'night' };
function applyPeriod(h, p) {
  if (!p) return h;
  if (p === 'am') return h === 12 ? 0 : h;
  if (p === 'day') return h === 12 ? 12 : h < 12 ? h + 12 : h;
  if (p === 'pm') return h < 12 ? h + 12 : h;
  return h === 12 ? 0 : h >= 6 && h < 12 ? h + 12 : h;   // ночи
}
/** Время суток для будильника → {hour, minute} | null */
export function parseClock(text) {
  const s = norm(text);
  if (/(?:^| )полночь(?= |$)/.test(s)) return { hour: 0, minute: 0 };
  if (/(?:^| )полдень(?= |$)/.test(s)) return { hour: 12, minute: 0 };
  const toks = s.split(' ');
  const per = (() => { for (const t of toks) if (t in PERIOD) return PERIOD[t]; return null; })();
  let m;
  if ((m = /(?:^|\D)(\d{1,2})[:.](\d{2})(?!\d)/.exec(s))) { const h = +m[1], mi = +m[2]; if (h <= 23 && mi <= 59) return { hour: h > 12 ? h : applyPeriod(h, per), minute: mi }; }
  const ordAfter = (k) => { for (let i = k; i < Math.min(toks.length, k + 2); i++) if (toks[i] in ORD) return ORD[toks[i]]; return null; };
  const nums = numbers(toks);
  const at = (k) => nums.find((n) => n.i === k);
  for (let k = 0; k < toks.length; k++) {
    if (/^(половину|половине|пол)$/.test(toks[k])) { const o = ordAfter(k + 1); if (o) return { hour: applyPeriod(o - 1 || 12, per) % 24, minute: 30 }; }
    if (toks[k] === 'четверть' && toks[k - 1] !== 'без') { const o = ordAfter(k + 1); if (o) return { hour: applyPeriod(o - 1 || 12, per) % 24, minute: 15 }; }
    if (toks[k] === 'без') {
      const w = toks[k + 1]; const mm = { четверти: 45, пятнадцати: 45, десяти: 50, пяти: 55, двадцати: 40 }[w];
      const n = at(k + 2) || at(k + 3);
      if (mm && n) { const h = n.v - 1 || 12; return { hour: applyPeriod(h, per) % 24, minute: mm }; }
    }
  }
  // «N минут <порядковое>» (пятнадцать минут восьмого)
  for (const n of nums) if (toks[n.j] && /^мин/.test(toks[n.j]) && ordAfter(n.j + 1)) return { hour: applyPeriod(ordAfter(n.j + 1) - 1 || 12, per) % 24, minute: n.v };
  // «<час> <минуты> [период]» и «<час> [часов] [период]»
  const hrs = nums.filter((n) => !(toks[n.j] && /^(мин|сек)/.test(toks[n.j])));
  if (hrs.length >= 2 && hrs[1].i === hrs[0].j) { const h = hrs[0].v, mi = hrs[1].v; if (mi <= 59 && h <= 23) return { hour: h > 12 ? h : applyPeriod(h, per), minute: mi }; }
  if (hrs.length >= 3 && hrs[0].v === 0) return null;
  if (hrs.length >= 3 && hrs[1].i === hrs[0].j && hrs[2].i === hrs[1].j && hrs[1].v === 0 && hrs[2].v < 10) return { hour: applyPeriod(hrs[0].v, per), minute: hrs[2].v };
  if (hrs.length >= 1) { const h = hrs[0].v; if (h >= 0 && h <= 23 && (per || (h >= 4 && h <= 12) || h > 12)) return { hour: h > 12 ? h : applyPeriod(h, per), minute: 0 }; }
  return null;
}

const LVL = [[/(?:^| )(максимум|максимальную|полную|сто процентов|на сто)(?= |$)/, 100], [/(?:^| )(минимум|ноль|ноль процентов)(?= |$)/, 0], [/(?:^| )(половину|середину)(?= |$)/, 50], [/(?:^| )четверть(?= |$)/, 25]];
export function parseLevel(text) {
  const s = norm(text);
  const d = /(\d{1,3})(?:%| процент|(?= |$))/.exec(s); if (d) return +d[1];
  for (const [re, v] of LVL) if (re.test(s)) return v;
  const n = numbers(s.split(' ')); if (n.length) return n[n.length - 1].v;
  return null;
}

/** true — числа в действиях подтверждены независимым разбором фразы (или в действиях нет чисел). */
export function slotsOk(actions, text) {
  const numeric = actions.filter((a) => ['alarm', 'timer', 'remind', 'volume', 'brightness'].includes(a.action));
  if (!numeric.length) return true;
  if (actions.length > 1) return false;                    // составная команда с числом — пусть разбирает большая модель
  const a = numeric[0];
  if (a.action === 'timer') return parseDuration(text) === a.seconds;
  if (a.action === 'remind') { const d = parseDuration(text.replace(/^.*?через /, '')); return d !== null && d / 60 === a.minutes; }
  if (a.action === 'alarm') {
    if (/через/.test(norm(text))) return false;
    const c = parseClock(text); return !!c && c.hour === a.hour && c.minute === (a.minute ?? 0);
  }
  const lv = parseLevel(text); return lv !== null && lv === a.level;
}

// ---- Проверка «привязки к фразе»: малая модель иногда придумывает лишнее («позвонить пользователю», «фонарь выключить» вместо включить) ----
const OFF_RE = /выключ|отключ|выруб|погас|деактив|отруб|закрой|убери/;
const ON_RE = /включ|вруб|актив|запуст|зажг|засвет|посвет|раздай|открой|подключ/;
const stem = (w) => w.slice(0, Math.max(3, Math.min(5, w.length - 2)));
const hasWord = (text, word) => { const t = norm(text); return word.toLowerCase().split(/\s+/).filter(Boolean).every((w) => /^\d+$/.test(w) ? t.includes(w) : t.split(' ').some((x) => x.startsWith(stem(w)))); };

const KNOWN_APPS = new Set(["2гис", "alice", "avito", "calculator", "calendar", "camera", "chrome", "clock", "contacts", "discord", "duolingo", "facebook", "files", "gallery", "gmail", "google", "instagram", "mail", "maps", "music", "netflix", "notes", "ozon", "phone", "pinterest", "play market", "settings", "skype", "sms", "spotify", "telegram", "tiktok", "twitch", "twitter", "viber", "vk", "whatsapp", "wildberries", "youtube", "zoom", "госуслуги", "дзен", "кинопоиск", "магнит", "пятёрочка", "сбербанк", "тинькофф", "шазам", "яндекс карты", "яндекс музыка", "яндекс такси"]);   // приложения, на которых обучена модель; остальные имена — большой модели
const TARGET_RE = { wifi: /вай|wi-?fi/, bluetooth: /блют|bluetooth/, airplane: /авиа|полет|самолет/, dnd: /беспокоить|dnd/, autorotate: /поворот/, nfc: /nfc|нфс|нфц/, hotspot: /точк|раздач|раздай|модем|хотспот|hotspot/, location: /геолокац|gps|местоположен|геопозиц/, battery_saver: /экономи|энергосбереж/ };
const MUSIC_FILLER = new Set(['включи', 'поставь', 'песню', 'песня', 'трек', 'музыку', 'хочу', 'послушать', 'сыграй', 'запусти', 'давай', 'послушаем', 'найди', 'и', 'в', 'через', 'мне', 'пожалуйста', 'плиз', 'быстро', 'сейчас', 'слушай', 'ну', 'эй', 'алиса', 'окей', 'спасибо', 'ладно', 'будь', 'добр', 'спотифай', 'spotify', 'спотифае', 'яндекс', 'музыке', 'музыку', 'ютуб', 'youtube', 'music', 'можешь', 'а', 'ка', 'так', 'короче', 'срочно', 'прямо']);

/** true — действия опираются на то, что реально сказано. */
export function groundedOk(actions, text) {
  const t = norm(text);
  if (actions.length > 1 && !/( и |,|потом|затем|еще|заодно)/.test(String(text).toLowerCase().replace(/ё/g, 'е'))) return false;   // две команды без «и/потом» — выдумка
  for (const a of actions) {
    if (a.action === 'call' && !hasWord(t, a.to)) return false;                                   // кому звонить — только названо в фразе
    if (a.action === 'message' && (!hasWord(t, a.to) || !hasWord(t, a.text.split(' ')[0]))) return false;
    if (a.action === 'music_play') {
      if (!hasWord(t, a.query)) return false;
      const q = new Set(norm(a.query).split(' ').map(stem));      // все «лишние» слова фразы должны войти в запрос (иначе запрос обрезан: «линкин парк» → «парк»)
      for (const w of t.split(' ')) if (!MUSIC_FILLER.has(w) && !q.has(stem(w))) return false;
    }
    if (a.action === 'toggle' && TARGET_RE[a.target] && !TARGET_RE[a.target].test(t)) return false;   // «раздай интернет» ≠ вайфай
    if ((a.action === 'open_app' || a.action === 'close_app') && !KNOWN_APPS.has(String(a.app).toLowerCase())) return false;   // выдуманное/обрезанное имя приложения
    if (a.action === 'volume' && !/громк|звук|тише|громче/.test(t)) return false;
    if (a.action === 'brightness' && !/яркост|ярче|темнее/.test(t)) return false;
    if ('on' in a && (a.action === 'toggle' || a.action === 'flashlight')) {   // включить/выключить — направление должно совпасть с глаголом
      const off = OFF_RE.test(t), on = ON_RE.test(t) || /(^| )(вкл)( |$)/.test(t);
      if (off && !on && a.on !== false) return false;
      if (on && !off && a.on !== true) return false;
    }
  }
  return true;
}
