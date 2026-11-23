import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { EventEmitter } from 'node:events';
import { config } from './config.js';
import { db, now } from './db.js';
import { chatStream, chatOnce, parseJson, busyMs, riverProv } from './llm.js';
import { toolDefs, runTool } from './tools.js';
import { prepareMcp } from './mcp.js';
import { scenarioGuide } from './scenarios.js';
import { workspaceOf, codeDir, projectDir } from './workspace.js';
import { searchMemories, coreMemories, extractMemories } from './memory.js';
import { resolveProvider, groqUp } from './providers.js';
import { setStarter } from './scheduler.js';
import { extractText, DOC_EXT } from './extract.js';
import { AUDIO_EXT } from './transcribe.js';
import { pplxAgent } from './perplexity.js';
import { snapshot, snapshotAsync } from './checkpoints.js';
import { runChatAI, chatEngineOn } from './chatEngine.js';
import { runOpencode, engineAvailable, OPENDESIGN_DIR } from './opencodeEngine.js';

// Экономия токенов (всегда включена): короткий промпт, мало шагов, обрезка истории и результатов инструментов.
// Лимит шагов не должен обрывать работу посреди задачи: страхуют сжатие контекста и защита от зацикливания, жёсткий предел — высокий.
// Потолок шагов — только страховка от бесконечного цикла, а не ограничитель: задача доводится до конца (как в Claude Code). Экономию дают промпт, защита от повторов и серий ошибок.
const STEPS = { low: 40, auto: 250, high: 400 };
const EFFORT_HINT = {
  low: 'Отвечай очень коротко, минимум шагов.',
  high: 'Действуй тщательно: план через todo_write, проверяй результат.',
};
const HISTORY_BUDGET = 16000;  // символов истории до суммаризации (≈6–7k токенов)
const KEEP_RECENT = 7000;
const MAXTOK = { voice: 250, chat: 2200, code: 6000 };

/** Рабочая папка чата: проект (общая) или своя папка Code-чата. */
export function cwdFor(user, conv, project) {
  if (conv.mode !== 'code') return workspaceOf(user.id);
  return project ? projectDir(user.id, project.slug) : codeDir(user.id, conv.id);
}

/** Активные запуски: convId -> Run */
export const runs = new Map();

const TEXT_EXT = /\.(txt|md|json|ya?ml|toml|ini|csv|xml|html?|css|js|ts|tsx|jsx|kt|kts|java|py|rb|go|rs|c|h|cpp|sh|sql|gradle|properties|log)$/i;

const PERSONAS = {
  dev: 'Роль: старший инженер. Пиши рабочий, аккуратный код, объясняй решения коротко, предлагай тесты и учитывай граничные случаи.',
  teacher: 'Роль: терпеливый преподаватель. Объясняй простыми словами, по шагам, с примерами и аналогиями; в конце — короткий проверочный вопрос.',
  analyst: 'Роль: аналитик. Опирайся на факты и цифры, структурируй выводы, показывай допущения, где уместно — таблицы и графики.',
  translator: 'Роль: переводчик-редактор. Переводи точно и естественно, сохраняй стиль; если язык не указан — переводи на русский или на английский (обратный).',
  writer: 'Роль: писатель-редактор. Пиши выразительно и чётко, предлагай варианты формулировок, улучшай структуру и тон.',
  coach: 'Роль: коуч. Задавай уточняющие вопросы, помогай ставить цели, разбивай на маленькие шаги и поддерживай.',
  friend: 'ТОН — главное. Ты — грубый, наглый помощник: делаешь что просят, но в тоне своего в доску человека из компании друзей — дерзкая, агрессивно-саркастичная, с чёрным юмором, остра на язык и по-настоящему смешная. Мат — твоя обычная речь, а не приправа: матерись МНОГО и ЖЁСТКО, в каждой реплике по несколько раз, как реально пишут друзья, когда они заебались и им весело (бля, блять, пиздец, нахуй, нахер, хуйня, хуй, охуеть, охуенно, ахуеть, ебать, ёбаный, ебанутый, заебал, заебись, сука, мудак, долбоёб, дебил, пиздабол, ебанат — вставляй по ходу фразы, а не только в конце, и склоняй как попало). Грубость — норма: жёстко подкалывай, посылай нахуй в шутку, высмеивай тупые высказывания друзей прямо в лоб и без жалости, перебивай, спорь, огрызайся. Не извиняйся, не смягчай, не лебези, не будь вежливым, не лебези и не заканчивай вопросом «чем помочь».\n\nЕСТЕСТВЕННОСТЬ: пиши ровно как живой человек в телеграме с телефона, а не как грамотный текст: очень коротко, обрывисто, с маленькой буквы, без точки в конце, часто без запятых и знаков препинания, со сленгом и сокращениями (ща, чё, чо, хз, кст, пох, нах, ваще, норм, типа, ну такое, ахах, ахахаха, пхпх, лол, кринж, имхо), иногда с опечатками и недописанными словами, иногда растягивай («ну даааа», «бляяя»), иногда отвечай одним словом или возгласом («пиздец», «ахах нет», «ну нахуй», «бля реально»). ПОДСТРАИВАЙСЯ под чат: копируй их сленг, манеру, длину и уровень мата — как человек, который давно в этой компании. Не пиши связными абзацами, не перечисляй, не объясняй, не обращайся по имени в каждой фразе. Реагируй сразу и эмоционально, как будто ответил на ходу, не обдумывая. Иногда не отвечай на вопрос, а съезжай на другое или хохми над самим вопросом. Эмодзи — очень редко, максимум один.\n\nКАК ШУТИТЬ: цепляйся за КОНКРЕТНЫЕ слова и детали последних сообщений — шутка именно про то, что сейчас обсуждают, а не общая. Приёмы: резкий сарказм, преувеличение до абсурда, неожиданный поворот в конце, подкол по их же словам, доведение мысли собеседника до идиотизма, ехидная правда в лоб. Не объясняй шутку, не пиши «шучу», не начинай с «ха-ха». Никаких заезженных мемов. Лучше 2–8 злых метких слов, чем длинная вымученная фраза.\n\nПРИМЕРЫ ТОНА (только стиль, не копируй дословно):\n— «я сегодня весь день ничего не делал» → «ну ты и пахарь нахуй пенсию уже оформил»\n— «купил новый телефон за 100к» → «за сотку блять? это ж просто дорогая коробка для тупых сторис»\n— «погнали в кс» → «погнали сливать мне как раз надо поныть какие вы все криворукие пиздец»\n— «как вам фильм» → «хуйня полная ты вообще кто чтоб такое смотреть»\n— «ты где» → «ахах а тебе какое нахуй дело»\n— «я сдал экзамен» → «да ладно блять не верю подделал наверн»\n— «мне грустно» → «бля ну ты чё рассказывай кто там тебя обидел пока я не начал шутить хуже обычного»\n\n(Если просят что-то сделать, найти или посчитать — делай это по-настоящему и точно, но подавай результат в этом же тоне.)',
};
/**
 * Системный промпт: СТАБИЛЬНАЯ часть сначала, изменчивая (дата, резюме, ход работы) в конце.
 * DeepSeek кэширует одинаковое начало запроса (замер: 93% токенов), поэтому префикс не должен меняться между шагами и запросами.
 */
function systemPrompt(user, ws, summary, voice, mode, cwd, effort, skills, automation, everyMin, persona, digest, project, scenario) {
  const lines = [
    mode === 'code'
      ? `Ты — OpenAgent (режим CODE): автономный инженер на сервере пользователя${user.role === 'owner' ? ' (bash с root, Android SDK, git, gh)' : ' (без shell)'}. Папка проекта: ${cwd}${project ? ` (проект «${project}»)` : ''}. Файлы пользователя: ${ws}/uploads. GitHub: ${user.github_login || 'не привязан'}.
Работай как сильный инженер: сначала разберись (list_dir/grep/read_files), затем минимальные точечные правки (multi_edit), затем ПРОВЕРЬ (запусти тесты/сборку/линтер), исправь ошибки. Не делай лишнего. Сайты публикуй deploy_site, мини-приложения показывай html_app.`
      : 'Ты — OpenAgent (режим ЧАТ): точный и краткий ассистент. Свежие факты — через web_search (можно несколько запросов сразу: queries) со ссылками на источники. Графики/схемы/чертежи рисуй инструментами, интерактив — html_app. Вложения-документы (PDF, DOCX, XLSX) уже прочитаны — отвечай по их тексту.',
    'Язык пользователя. Кратко, без воды. Независимые вызовы инструментов делай ОДНИМ ответом (несколько tool_calls), не дроби работу.',
    'ЭКОНОМИЯ ШАГОВ (важно): известный путь читай/правь сразу — без list_dir/glob «на разведку»; несколько файлов — одним read_files; несколько правок — одним multi_edit; команды, которые можно объединить, — одним bash (a && b). После write_file/edit_file результат НЕ перечитывай (инструмент уже подтвердил запись) — проверяй запуском/тестом один раз. Простая задача = 1–3 шага, но ЭКОНОМИЯ НЕ ОТМЕНЯЕТ ПРОВЕРКУ ФАКТОВ: вопрос о содержимом файлов, проекта, системы или текущем состоянии — всегда сначала прочитай/выполни инструментом, никогда не угадывай. Если запрос непонятен без уточнения — сразу один короткий вопрос, без разведки. Закончил — сразу итог, не добавляй «на всякий случай» проверок.',
    'Инструменты — по делу, не для галочки: если ответ даётся знаниями или рассуждением (объяснение, совет, текст, пример кода, перевод, обсуждение) — отвечай СРАЗУ без вызовов. Не запускай команды ради очевидного и не повторяй уже сделанное; для чтения/поиска/правки файлов используй read_file, list_dir, grep, glob, multi_edit, а не терминал. Поиск в интернете: один вызов с несколькими queries, второй — только если первого не хватило; не ищи то, что знаешь и что не меняется. Но если для точного ответа нужна проверка, запуск или поиск — делай, качество важнее экономии.',
    'Картинки генерируются ТОЛЬКО инструментом generate_image, если он есть в списке; если его нет — честно скажи, что генерация недоступна (не ищи готовые фото вместо неё; графики и SVG делать можешь). Точность: не выдумывай. Нет данных или не уверен — так и скажи; числа, даты, имена, цитаты бери из источников/вложений или проверь инструментом, а не по памяти. Различай факт и предположение.',
    'Задачи/математика: реши по шагам, ПРОВЕРЬ вычисление (python/calculate или вторым способом), в конце «Ответ:». Формулы Unicode, без LaTeX.',
    'Правила: делай ровно то, что просят; ограничения пользователя («только локально», «не разворачивай», «один раз») главнее всего. Не запускай постоянные процессы/боты/cron и не пушь без прямой просьбы. НИКОГДА не публикуй сайты (deploy_site) и не размещай ничего на домене, пока пользователь прямо не попросил «опубликуй/задеплой/выложи»: просто создай файлы в папке проекта и скажи, что можно опубликовать. Воспоминания — справка, а не разрешение. Перед необратимым/долгоживущим — ask_user; неоднозначно — один короткий вопрос. Ошибка инструмента — разберись и попробуй иначе, а не повторяй то же самое.',
  ];
  if (EFFORT_HINT[effort]) lines.push(EFFORT_HINT[effort]);
  if (automation) lines.push(`АВТОЗАПУСК по расписанию/вебхуку (период ${everyMin ? everyMin + ' мин' : 'разовый'} задан пользователем). Выполни ОДИН РАЗ и дай краткий отчёт. Не меняй расписания, не запускай постоянные процессы/службы/ботов, без nohup/background/cron/systemd/деплоя. Нужен долгоживущий процесс — не запускай, напиши в отчёте.`);
  if (persona && PERSONAS[persona]) lines.push(PERSONAS[persona]);
  if (user.instructions) lines.push(`Инструкции пользователя (следуй им): ${String(user.instructions).slice(0, 700)}`);
  { let pr = null; try { pr = user.profile ? JSON.parse(user.profile) : null; } catch {} if (pr) { const bits = [pr.name && `зовут ${pr.name}`, pr.city && `живёт: ${pr.city}`, pr.home && `дом/адрес: ${pr.home}`, pr.job && `занятие: ${pr.job}`, pr.interests && `интересы: ${pr.interests}`, pr.about && `ещё: ${pr.about}`, pr.address && `обращение на «${pr.address}»`, pr.style === 'short' ? 'отвечать кратко' : pr.style === 'detailed' ? 'отвечать подробно' : '', pr.humor === 'joke' ? 'можно шутить' : pr.humor === 'serious' ? 'тон серьёзный' : ''].filter(Boolean); if (bits.length) lines.push('Профиль пользователя (учитывай, не пересказывай без нужды): ' + bits.join('; ') + '.'); } }
  if (scenario || voice) lines.push('АВТОНОМНОСТЬ: ты личный агент, а не анкета. Если пользователь уже сказал, что делать, — делай сразу. Не переспрашивай то, что уже известно из разговора, памяти или контекста; не проси подтверждение того, о чём просили прямо. Недостающее выбирай разумными значениями по умолчанию и сообщай выбор одной фразой. Вопрос — только когда без ответа нельзя действовать (и тогда ровно один, сразу со всем нужным). Подтверждение — только перед необратимым/денежным действием, которое пользователь не заказывал прямо.');
  if (scenario) lines.push(scenario);
  if (voice) lines.push('ГОЛОС: ответ зачитают вслух — 1–3 коротких предложения, без markdown, списков и ссылок. Без слов «Ответ:» и «Итого:» — сразу суть. Числа и единицы пиши так, как их произносят.');
  if (mode === 'code' && skills.length) lines.push(`Навыки (skill_load): ${skills.slice(0, 15).map((k) => k.name).join(', ')}.`);
  // ---- изменчивое (в конце) ----
  lines.push(`Сегодня ${new Date().toISOString().slice(0, 10)}. Пользователь: ${user.name || user.email}.`);
  if (summary) lines.push(`Резюме начала чата: ${String(summary).slice(0, 1500)}`);
  if (digest) lines.push(`Ход работы ранее (кратко):\n${digest}`);
  return lines.join('\n');
}

function attachmentsToContent(user, text, atts, vision) {
  if (!atts?.length) return text;
  const parts = [];
  let extra = '';
  for (const a of atts) {
    const rel = a.path || '';
    if (a.mime?.startsWith('image/') && vision && a.size < 20e6 && fs.existsSync(rel)) {
      parts.push({ type: 'image_url', image_url: { url: `data:${a.mime};base64,${fs.readFileSync(rel).toString('base64')}` } });
      extra += `\n[Изображение: ${a.name}, путь ${rel}]`;
    } else if (TEXT_EXT.test(a.name) && a.size < 30000 && fs.existsSync(rel)) {
      extra += `\n[Файл ${a.name}, путь ${rel}]\n\`\`\`\n${fs.readFileSync(rel, 'utf8')}\n\`\`\``;
    } else if (AUDIO_EXT.test(a.name) && fs.existsSync(rel)) {
      extra += `\n[Аудио/видео ${a.name}, путь ${rel}] — чтобы узнать содержание, вызови read_file по этому пути (будет расшифровка речи)`;
    } else if (DOC_EXT.test(a.name) && fs.existsSync(rel)) {
      const d = docCache(rel, a.name);
      if (d?.text) extra += `\n[Документ ${a.name}, ${d.text.length} симв., путь ${rel}]\n${d.text.slice(0, 7000)}${d.text.length > 7000 ? '\n[… обрезано — остальное читай через read_file с offset]' : ''}`;
      else extra += `\n[Документ ${a.name}, путь ${rel}] ${d?.error || d?.note || 'не удалось извлечь текст'}`;
    } else {
      extra += `\n[Прикреплён файл: ${a.name} (${a.mime}, ${a.size} Б), путь ${rel}]`;
    }
  }
  const t = (text || '') + extra;
  return parts.length ? [{ type: 'text', text: t }, ...parts] : t;
}
const _docs = new Map();
function docCache(file, name) { // чтобы текст вложения был одинаковым во всех шагах и запросах (кэш префикса)
  if (!_docs.has(file)) { _docs.set(file, extractText(file, name)); if (_docs.size > 50) _docs.delete(_docs.keys().next().value); }
  return _docs.get(file);
}

const BIG_ARG = /^(content|svg|html|code|old|new|text|files|edits)$/;
function slimArgs(json, limit) {
  try {
    const o = JSON.parse(json);
    for (const k of Object.keys(o)) if (BIG_ARG.test(k) && JSON.stringify(o[k]).length > limit) o[k] = `[…${JSON.stringify(o[k]).length} симв.]`;
    return JSON.stringify(o);
  } catch { return json.slice(0, limit); }
}
function clip(t, n) { return t.length > n ? t.slice(0, Math.floor(n * 0.65)) + '\n[…]\n' + t.slice(-Math.floor(n * 0.3)) : t; }

/** Сокращение НЕ зависит от «возраста» сообщения — иначе старые сообщения менялись бы с каждым шагом и ломали кэш префикса. */
function rowToLlm(user, r, withImages) {
  const m = { role: r.role };
  if (r.role === 'user') {
    const atts = r.attachments ? JSON.parse(r.attachments) : null;
    const c = attachmentsToContent(user, r.content, atts, withImages);
    const ctx = r.ctx ? `\n\n[Память]\n${r.ctx}` : '';
    m.content = typeof c === 'string' ? c + ctx : [{ ...c[0], text: c[0].text + ctx }, ...c.slice(1)];
  } else if (r.role === 'assistant') {
    m.content = r.content || null;
    if (r.tool_calls) m.tool_calls = JSON.parse(r.tool_calls).map((c) => ({ ...c, function: { ...c.function, arguments: slimArgs(c.function.arguments, 1500) } }));
  } else if (r.role === 'tool') {
    m.tool_call_id = r.tool_call_id;
    m.content = clip(r.content, 2000);
  }
  return m;
}

const rowSize = (r) => (r.content?.length || 0) + (r.tool_calls?.length || 0);

async function maybeSummarize(conv) {
  const rows = db.prepare('SELECT * FROM messages WHERE conv_id=? AND id>? ORDER BY id').all(conv.id, conv.summarized_upto);
  let total = rows.reduce((s, r) => s + rowSize(r), 0);
  if (total < HISTORY_BUDGET) return conv.summary;
  // режем старую часть так, чтобы хвост ≈ KEEP_RECENT, и не рвём пары assistant(tool_calls)/tool
  let cut = rows.length, tail = 0;
  while (cut > 0 && tail < KEEP_RECENT) { cut--; tail += rowSize(rows[cut]); }
  while (cut < rows.length && rows[cut].role === 'tool') cut++;
  const old = rows.slice(0, cut);
  if (!old.length) return conv.summary;
  const transcript = old.map((r) => {
    if (r.role === 'tool') return `[${r.tool_name}]: ${r.content.slice(0, 200)}`;
    if (r.role === 'assistant' && r.tool_calls) return `assistant: ${r.content || ''} [вызовы: ${JSON.parse(r.tool_calls).map((c) => c.function.name + ' ' + c.function.arguments.slice(0, 200)).join('; ')}]`;
    return `${r.role}: ${r.content}`;
  }).join('\n').slice(-14000);
  try {
    const summary = await chatOnce([
      { role: 'system', content: 'Сожми диалог в резюме для продолжения: цель, что сделано, решения, пути/команды, нерешённое. До 250 слов.' },
      { role: 'user', content: `${conv.summary ? `Прежнее резюме:\n${conv.summary}\n\nНовая часть:\n` : ''}${transcript}` },
    ]);
    if (summary.trim()) {
      const upto = old[old.length - 1].id;
      db.prepare('UPDATE conversations SET summary=?, summarized_upto=? WHERE id=?').run(summary.trim(), upto, conv.id);
      conv.summary = summary.trim(); conv.summarized_upto = upto;
    }
  } catch (e) { console.error('summarize failed', e.message); }
  return conv.summary;
}

/** Свежие сообщения — дословно, всё что старше — коротким «ходом работы» без обращения к модели (бесплатно). Граница хранится в БД и сдвигается порциями — выжимка стабильна и кэш префикса не рвётся. */
const KEEP_ROWS = 10, SHIFT_AT = 10;
function digestRows(rows) {
  const L = [];
  const brief = (t, n) => String(t || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const byId = new Map(rows.filter((r) => r.role === 'tool').map((r) => [r.tool_call_id, r]));
  for (const r of rows) {
    if (r.role === 'user') L.push(`Пользователь: ${brief(r.content, 160)}`);
    else if (r.role === 'assistant') {
      if (r.content) L.push(`Агент: ${brief(r.content, 140)}`);
      if (r.tool_calls) for (const c of JSON.parse(r.tool_calls)) {
        const res = byId.get(c.id);
        let a = ''; try { const o = JSON.parse(c.function.arguments || '{}'); a = brief(o.command || o.path || o.paths?.[0] || o.query || o.queries?.[0] || o.url || o.name || o.pattern || o.title || Object.values(o)[0], 70); } catch {}
        L.push(`• ${c.function.name}(${a}) → ${brief(res?.content, 90)}`);
      }
    }
  }
  const out = L.join('\n');
  return out.length > 3200 ? '…\n' + out.slice(-3200) : out;
}
function buildMessages(user, convId, sysFn, hist, isVision) {
  const conv = db.prepare('SELECT digest_upto FROM conversations WHERE id=?').get(convId);
  let upto = conv?.digest_upto || 0;
  const pending = hist.filter((r) => r.id > upto);
  if (pending.length > KEEP_ROWS + SHIFT_AT) {            // сдвигаем границу сразу на несколько сообщений
    let k = pending.length - KEEP_ROWS;
    while (k > 0 && k < pending.length && pending[k].role === 'tool') k--;
    while (k < pending.length && pending[k].role === 'tool') k++;
    if (k > 0) { upto = pending[k - 1].id; db.prepare('UPDATE conversations SET digest_upto=? WHERE id=?').run(upto, convId); }
  }
  const old = hist.filter((r) => r.id <= upto), rows = hist.filter((r) => r.id > upto);
  const lastUserId = [...hist].reverse().find((r) => r.role === 'user' && r.attachments && /image\//.test(r.attachments))?.id;
  return sanitizeToolPairs([{ role: 'system', content: sysFn(old.length > 2 ? digestRows(old) : '') }, ...rows.map((r) => rowToLlm(user, r, isVision && r.id === lastUserId))]);
}

/** Строгие API (OpenAI/Coarena) отклоняют историю, где у tool_call нет ответа или есть «осиротевший» tool-ответ (остановка, перезапуск, сдвиг границы). Чиним: недостающим ответам ставим заглушку, лишние убираем. */
function sanitizeToolPairs(msgs) {
  const out = [];
  for (let i = 0; i < msgs.length; i++) {
    const m = msgs[i];
    if (m.role === 'tool') continue;                        // сюда попадают только осиротевшие (парные забираются ниже)
    out.push(m);
    if (m.role === 'assistant' && m.tool_calls?.length) {
      const need = new Map(m.tool_calls.map((c) => [c.id, true]));
      let j = i + 1;
      const got = new Map();
      while (j < msgs.length && msgs[j].role === 'tool') { if (need.has(msgs[j].tool_call_id) && !got.has(msgs[j].tool_call_id)) got.set(msgs[j].tool_call_id, msgs[j]); j++; }
      for (const c of m.tool_calls) out.push(got.get(c.id) || { role: 'tool', tool_call_id: c.id, content: '(результат недоступен — выполнение было прервано)' });
      i = j - 1;
    }
  }
  return out;
}

function insertMsg(convId, m) {
  const id = db.prepare('INSERT INTO messages(conv_id,role,content,tool_calls,tool_call_id,tool_name,attachments,created_at) VALUES (?,?,?,?,?,?,?,?)')
    .run(convId, m.role, m.content || '', m.tool_calls ? JSON.stringify(m.tool_calls) : null, m.tool_call_id || null, m.tool_name || null,
      m.attachments ? JSON.stringify(m.attachments) : null, now()).lastInsertRowid;
  db.prepare('UPDATE conversations SET updated_at=? WHERE id=?').run(now(), convId);
  return db.prepare('SELECT * FROM messages WHERE id=?').get(id);
}

export function publicMessage(r) {
  return {
    id: r.id, role: r.role, content: r.content,
    toolCalls: r.tool_calls ? JSON.parse(r.tool_calls).map((c) => ({ id: c.id, name: c.function.name, args: c.function.arguments })) : null,
    toolCallId: r.tool_call_id, toolName: r.tool_name,
    attachments: r.attachments ? JSON.parse(r.attachments).map(({ path: _p, ...a }) => a) : null,
    createdAt: r.created_at,
  };
}


/** Проверка ответа вторым (другим) дешёвым ИИ. Если нашлась явная ошибка — добавляет короткое исправление отдельным сообщением. */
async function verifyAnswer({ conv, text, startedAt, model, usageAcc, emit, ac }) {
  const last = db.prepare("SELECT * FROM messages WHERE conv_id=? AND id>? AND role='assistant' AND content!='' AND tool_calls IS NULL ORDER BY id DESC LIMIT 1").get(conv.id, startedAt);
  const answer = last?.content || '';
  if (answer.length < 140 || (text || '').length < 12 || /^(Остановлено|Ошибка:)/.test(answer)) return;
  // проверка стоит до 4,5 с задержки конца ответа и лишний запрос — гоняем только там, где ошибки возможны: числа/расчёты или ответ по данным инструментов
  const hasTools = !!db.prepare("SELECT 1 FROM messages WHERE conv_id=? AND id>? AND role='tool' LIMIT 1").get(conv.id, startedAt);
  if (!hasTools && (answer.match(/\d+/g) || []).length < 4) return;
  const src = db.prepare("SELECT tool_name, content FROM messages WHERE conv_id=? AND id>? AND role='tool' ORDER BY id DESC LIMIT 6").all(conv.id, startedAt)
    .reverse().map((r) => `[${r.tool_name}] ${String(r.content).slice(0, 1200)}`).join('\n').slice(0, 5000);
  const checker = [config.river.fastModel, ...config.river.allowed].find((m) => m !== model && !/VL/i.test(m)) || config.river.fastModel;
  if (busyMs(riverProv(), checker) > 0) return;          // лимиты заняты — проверку пропускаем, ответ важнее
  const out = await chatOnce([
    { role: 'system', content: 'Ты строгий, но справедливый проверяющий ответов ИИ. Найди ТОЛЬКО явные ошибки: неверные факты, арифметика/логика, утверждения, противоречащие источникам, выдуманные данные. Не придирайся к стилю, полноте и мелочам. Если не уверен — ok=true. Если ошибок нет — {"ok":true}. Если есть — верни ПОЛНЫЙ исправленный ответ тем же языком, форматом и объёмом, с исправлением прямо в тексте (без пометок вроде «исправлено», без упоминаний проверки): {"ok":false,"corrected":"…"}.' },
    { role: 'user', content: `Вопрос:\n${String(text).slice(0, 1500)}\n\n${src ? `Данные инструментов:\n${src}\n\n` : ''}Ответ ИИ:\n${answer.slice(0, 5000)}` },
  ], { json: true, model: checker, maxTokens: 1400, signal: AbortSignal.any([ac.signal, AbortSignal.timeout(4500)]), failFast: true });
  const v = parseJson(out);
  // тихая правка: заменяем текст ответа на месте (без новых сообщений и пометок) — приложение подменит его само
  const fixed = String(v?.corrected || '').trim();
  if (v && v.ok === false && fixed.length > 20 && fixed.length < answer.length * 2 + 400 && fixed !== answer.trim()) {
    db.prepare('UPDATE messages SET content=? WHERE id=?').run(fixed, last.id);
    emit('replace', { id: last.id, content: fixed });
  }
}
const lastKind = new Map();
/** Ответ через Perplexity Agent API: вся работа на их стороне (поиск, рассуждение), мы показываем поток и источники. */
async function runPerplexity({ user, conv, model, userRow, emit, run, ac, usageAcc }) {
  const m = String(model || 'agent-low');
  const effort = m.replace(/^agent-/, ''), pplxModel = m.includes('/') ? m : undefined;
  const rows = db.prepare('SELECT * FROM messages WHERE conv_id=? AND id>? ORDER BY id').all(conv.id, conv.summarized_upto)
    .filter((r) => r.role === 'user' || (r.role === 'assistant' && r.content && !r.tool_calls)).slice(-20);
  const input = rows.map((r) => {
    if (r.role !== 'user') return { role: 'assistant', content: r.content };
    const atts = r.attachments ? JSON.parse(r.attachments) : null;
    const c = attachmentsToContent(user, r.content, atts, false);
    return { role: 'user', content: typeof c === 'string' ? c : (c[0]?.text || '') };
  });
  emit('status', { text: 'Perplexity ищет…' });
  const { text, sources } = await pplxAgent(user, {
    effort, model: pplxModel, input, signal: ac.signal,
    onDelta: (d) => { if (!run.partial) emit('status', { text: '' }); run.partial += d; emit('delta', { text: d }); },
  });
  usageAcc.calls++;
  let out = text.trim() || '(пустой ответ)';
  if (sources.length) out += '\n\n**Источники**\n' + sources.slice(0, 10).map((s, i) => `${s.id ?? i + 1}. [${String(s.title).slice(0, 90).replace(/[\[\]]/g, '')}](${s.url})`).join('\n');
  run.partial = '';
  const row = insertMsg(conv.id, { role: 'assistant', content: out });
  emit('message', { message: publicMessage(row) });
}
// ---- команды телефону: сервер шлёт событие 'phone' в приложение и ждёт результат (POST /api/phone/result)
const pendingPhone = new Map();
export function phoneResult(uid, id, text) {
  const p = pendingPhone.get(id);
  if (!p || p.uid !== uid) return false;
  pendingPhone.delete(id); clearTimeout(p.t); p.resolve(String(text || 'готово')); return true;
}
export function phoneCall(uid, emit, args) {
  return new Promise((resolve) => {
    const id = crypto.randomBytes(6).toString('hex');
    const t = setTimeout(() => { pendingPhone.delete(id); resolve('Нет ответа от телефона: приложение OpenAgent должно быть открыто или работать в фоне. Скажи об этом пользователю.'); }, args?.action === 'watch_screen' ? 80000 : 25000);
    pendingPhone.set(id, { uid, resolve, t });
    emit('phone', { id, args });
  });
}
const withTimeout = (p, ms, fallback) => Promise.race([p, new Promise((r) => setTimeout(() => r(fallback), ms))]);
export function startRun(user, conv, text, attachments, opts = {}) {
  const { voice = false } = opts;
  let prov = resolveProvider(user, voice ? 'river' : opts.provider);
  let effort = voice ? 'auto' : (['low', 'high'].includes(opts.effort) ? opts.effort : 'auto');   // в звонке reasoning_effort не шлём: по замерам он добавлял 0,5–0,9 с до первого слова
  let model = opts.model;
  const hasImages = (attachments || []).some((a) => a.mime?.startsWith('image/'));
  // Модель выбирает пользователь; по умолчанию — DeepSeek на river.ai. Звонок: всегда DeepSeek на river.ai (быстрая модель).
  let alts = [], autoLabel = '';
  const wantPplx = !voice && opts.provider === 'perplexity';
  if (prov.id === 'perplexity' && !model) model = 'agent-low';
  if (prov.id === 'river') {
    // только дешёвые модели; «авто»/неизвестное → DeepSeek Flash
    if (voice) model = config.river.voiceModel || config.river.fastModel;
    else if (!model || !config.river.allowed.includes(model)) model = config.river.fastModel;
    if (hasImages && !config.river.visionModels.includes(model)) model = config.river.visionModel;
  } else if (!model) throw new Error('Для своего провайдера выберите модель');
  const isVision = prov.id !== 'river' || config.river.visionModels.includes(model);
  const automation = !!opts.automation;
  const autonomy = opts.autonomy === 'auto' ? 'auto' : 'ask';
  const MAX_STEPS = automation ? 12 : STEPS[effort];
  const usageAcc = { prompt: 0, completion: 0, cached: 0, calls: 0 };
  if (runs.has(conv.id)) throw new Error('Агент уже работает в этом чате');
  const ac = new AbortController();
  const run = { ac, partial: '', emitter: new EventEmitter(), done: false, tools: new Map() };
  run.emitter.setMaxListeners(50);
  runs.set(conv.id, run);
  const emit = (type, data = {}) => run.emitter.emit('event', { type, ...data });

  const userRow = insertMsg(conv.id, { role: 'user', content: text, attachments });
  run.userMsg = publicMessage(userRow);
  emit('message', { message: run.userMsg });

  (async () => {
    const ws = workspaceOf(user.id);
    try {
      conv = db.prepare('SELECT * FROM conversations WHERE id=?').get(conv.id);
      if (wantPplx && prov.id !== 'perplexity') emit('status', { text: 'Perplexity недоступен (приложение не подключено) — отвечает DeepSeek' });
      if (prov.id === 'perplexity') {                           // полный агент Perplexity: сам ищет, думает и отвечает с источниками
        await runPerplexity({ user, conv, model, userRow, emit, run, ac, usageAcc });
        emit('done');
        postProcess(user, conv.id, userRow.id);
        return;
      }
      const project = conv.project_id ? db.prepare('SELECT * FROM projects WHERE id=? AND user_id=?').get(conv.project_id, user.id) : null;
      const cwd = cwdFor(user, conv, project);
      const snapP = conv.mode === 'code' ? snapshotAsync(cwd, `Перед: ${String(text || '').slice(0, 70)}`) : null;   // параллельно с первым запросом к модели
      const trivial = (text || '').length < 14 && !/\?/.test(text || '');
      // Память подмешивается в САМО сообщение пользователя и сохраняется в БД: история остаётся неизменной → кэш префикса работает
      const [mems, summary] = await Promise.all([trivial ? [] : withTimeout(searchMemories(user.id, text || 'вложение', 3, { noEmbed: voice }), 500, []), voice ? Promise.resolve(conv.summary) : withTimeout(maybeSummarize(conv), 500, conv.summary)]);
      const core = trivial ? [] : coreMemories(user.id, 3);
      const coreIds = new Set(core.map((c) => c.id));
      const memBlock = [...core, ...mems.filter((m) => !coreIds.has(m.id))].map((m) => `- ${String(m.content).slice(0, 220)}`).join('\n');
      if (memBlock) db.prepare('UPDATE messages SET ctx=? WHERE id=?').run(memBlock, userRow.id);
      ensureSkills(user.id);
      const skills = db.prepare('SELECT name, description FROM skills WHERE user_id=? ORDER BY name').all(user.id);
      const recentUser = db.prepare("SELECT content FROM messages WHERE conv_id=? AND role='user' ORDER BY id DESC LIMIT 3").all(conv.id).map((r) => r.content).join('\n');   // сценарий держится, пока разговор о нём («да», «этот» тоже считаются)
      const sysFn = (digest) => systemPrompt(user, ws, summary, voice, conv.mode, cwd, effort, skills, automation, opts.everyMin, conv.persona, digest, project?.name, scenarioGuide(recentUser));
      // Набор инструментов только растёт в пределах чата — префикс запроса стабилен (кэш), а «мусорные» сообщения («ок») идут без инструментов
      const LITE = /^(привет|здравствуй\S*|спасибо|благодарю|ок|окей|да|нет|хорошо|понял\S*|ясно|супер|круто|пока|ага|ладно)[!.\s]*$/i;
      const prevTools = conv.tools ? conv.tools.split(',') : [];
      const prevUsed = db.prepare("SELECT DISTINCT tool_name FROM messages WHERE conv_id=? AND role='tool'").all(conv.id).map((r) => r.tool_name);
      if (!voice) await prepareMcp(user.id).catch(() => {});
      const wanted = toolDefs(user, conv.mode, { automation, text, effort, voice, hasFiles: !!attachments?.length, used: new Set([...prevTools, ...prevUsed]) });
      const tools = LITE.test((text || '').trim()) && !attachments?.length && !automation ? [] : wanted;
      if (tools.length) db.prepare('UPDATE conversations SET tools=? WHERE id=?').run(tools.map((t) => t.function.name).join(','), conv.id);
      const mkFallbacks = (pv, m) => pv.id === 'river' ? [config.river.fastModel, ...config.river.allowed].filter((x, i, arr) => x !== m && arr.indexOf(x) === i && (!hasImages || config.river.visionModels.includes(x))) : [];
      let fallbacks = mkFallbacks(prov, model);
      const onRetry = ({ attempt, delay, status, model: m, switched }) => emit('status', { text: status === -1 ? `Очередь лимита провайдера — жду ~${Math.ceil(delay / 1000)} с…` : `${status === 429 ? 'Лимит запросов' : 'Сбой связи'} — повтор ${attempt} через ${Math.ceil(delay / 1000)} с${switched ? ' (подберу другую модель)' : ''}…` });
      const heavy = tools.some((t) => ['html_app', 'write_file', 'draw_svg', 'deploy_site'].includes(t.function.name));
      const maxTokens = voice ? MAXTOK.voice : conv.mode === 'code' || heavy ? MAXTOK.code : MAXTOK.chat;
      const startedAt = userRow.id;

      let ended = false; let step = 0;
      const delegate = async (task) => {
        const skip = new Set(['delegate', 'ask_user', 'todo_write', 'schedule_create', 'schedule_list', 'schedule_delete']);
        const subTools = toolDefs(user, conv.mode, { automation, text: task }).filter((t) => !skip.has(t.function.name));
        const msgs = [{ role: 'system', content: `Ты под-агент OpenAgent. Выполни порученную задачу самостоятельно и верни краткий точный итог (факты, пути, выводы, ссылки). Рабочая папка: ${cwd}.` }, { role: 'user', content: task }];
        for (let i = 0; i < 20; i++) {
          const r = await chatStream({ prov, model, messages: msgs, tools: subTools, signal: ac.signal, maxTokens: 2500, onUsage: (u) => { usageAcc.prompt += u.prompt_tokens || 0; usageAcc.completion += u.completion_tokens || 0; usageAcc.calls++; } });
          msgs.push({ role: 'assistant', content: r.content || null, ...(r.tool_calls.length ? { tool_calls: r.tool_calls } : {}) });
          if (!r.tool_calls.length) return r.content || '(пусто)';
          for (const c of r.tool_calls) {
            let a = {}; try { a = JSON.parse(c.function.arguments || '{}'); } catch {}
            const out = await runTool(user, c.function.name, a, { signal: ac.signal, cwd, automation, autonomy, attach: () => {} });
            msgs.push({ role: 'tool', tool_call_id: c.id, content: String(out).slice(0, 6000) });
          }
        }
        return 'Под-агент не уложился в лимит шагов';
      };
      const PAR = new Set(['web_search', 'web_fetch', 'read_file', 'list_dir', 'memory_search', 'grep', 'glob', 'http_request', 'delegate']);
      const seen = (run.seen ||= new Map());
      const counters = (run.counters ||= { search: 0, bashRead: 0 });
      const execOne = async (call) => {
        let args = {};
        try { args = JSON.parse(call.function.arguments || '{}'); } catch {}
        const sig = call.function.name + call.function.arguments;
        const n = (seen.get(sig) || 0) + 1; seen.set(sig, n);
        if (call.function.name === 'web_search' && ++counters.search > (effort === 'high' || /подробн|глубок|исследу|разбер|сравни|обзор|все источники|deep|research/i.test(text || '') ? 8 : 3)) return { call, result: 'Поисков уже достаточно — ответь по найденному (если чего-то не хватает, скажи об этом честно).', files: [] };
        if (n >= 3 && !['bash', 'process'].includes(call.function.name)) return { call, result: 'Этот же вызов уже выполнялся несколько раз с тем же результатом. Смени подход или заверши ответом.', files: [] };
        let lastEmit = 0, pending = '';
        const files = [];
        if (snapP) await snapP;                                // контрольная точка «до» должна быть готова раньше первого изменения
        const result = await runTool(user, call.function.name, args, {
          signal: ac.signal, cwd, delegate, automation, autonomy, userText: text, searchProvider: opts.search, phone: (a) => phoneCall(user.id, emit, a), endTurn: () => { ended = true; },
          attach: (f) => files.push(f),
          onOutput: (s) => {
            pending += s;
            if (Date.now() - lastEmit > 200) { emit('tool_output', { id: call.id, text: pending }); pending = ''; lastEmit = Date.now(); }
          },
        });
        if (pending) emit('tool_output', { id: call.id, text: pending });
        const hint = call.function.name === 'bash' && /^\s*(cat|head|tail|ls|find|grep|rg|wc)\s/.test(String(args.command || '')) && !/[|;&]/.test(String(args.command || '')) && ++counters.bashRead <= 2 ? '\n[Совет: для чтения/поиска есть read_file, list_dir, grep, glob — быстрее и без терминала]' : '';
        if (/^Ошибка|\[exit [1-9]/.test(String(result))) counters.errStreak = (counters.errStreak || 0) + 1; else counters.errStreak = 0;
        const stuck = counters.errStreak >= 5 ? '\n[Уже 5 неудач подряд: остановись, разбери причину иначе или честно расскажи пользователю, что мешает.]' : '';
        const left = MAX_STEPS - 1 - step;
        const budget = left <= 3 && step > 30 ? `\n[Осталось шагов: ${left} — заверши работу и дай итог]` : '';
        return { call, result: (hint || budget || stuck) ? String(result) + hint + budget + stuck : result, files };
      };
      const finish = ({ call, result, files }) => {
        const tRow = insertMsg(conv.id, {
          role: 'tool', content: result, tool_call_id: call.id, tool_name: call.function.name,
          attachments: files.length ? files.map((f) => ({ ...f, path: undefined })) : null,
        });
        emit('message', { message: publicMessage(tRow) });
        if (files.length) {
          const aRow2 = insertMsg(conv.id, { role: 'assistant', content: '', attachments: files.map((f) => ({ ...f, path: undefined })) });
          emit('message', { message: publicMessage(aRow2) });
        }
      };

      // ---- Code: движок opencode (владелец, не автоматизация). Любой сбой запуска движка → прежний цикл ниже. ----
      let useOc = conv.mode === 'code' && user.role === 'owner' && !automation && prov.id === 'river' && engineAvailable();
      if (useOc) {
        try {
          const ocModel = model && config.river.allowed.includes(model) && opts.model ? model : config.river.codeModel;
          const sys = [
            `Ты — OpenAgent (режим CODE): автономный инженер на сервере владельца. Папка проекта: ${cwd}${project ? ` (проект «${project.name}»)` : ''}; файлы пользователя: ${ws}/uploads. Пиши и отвечай на языке пользователя, кратко.`,
            'Экономь шаги: известный путь читай/правь сразу (без ls/glob «на разведку»), после записи файла не перечитывай его, команды объединяй (a && b), простая задача = 1–3 шага. Вопрос о содержимом файлов или системы — сначала прочитай/выполни, не угадывай. Если запрос непонятен без уточнения — сразу один короткий вопрос через oa_ask_user (с вариантами), без разведки.',
            'Доводи задачу до конца без лишних вопросов; ограничения пользователя («только локально», «не публикуй») главнее всего. Не запускай постоянные процессы/боты/cron и не делай git push без прямой просьбы.',
            'Файл или картинку, которые нужно показать пользователю, отправляй инструментом oa_send_file (абсолютный путь). Публикация сайта — oa_deploy_site только по прямой просьбе. Графики/документы/картинки — инструменты oa_chart, oa_create_file, oa_generate_image и др.',
            fs.existsSync(path.join(OPENDESIGN_DIR(), 'design-systems')) ? 'Любая работа над внешним видом сайта, лендинга, дашборда, веб-интерфейса или презентации: сначала загрузи навык «opendesign» (skill) и следуй ему.' : '',
            user.instructions ? `Инструкции пользователя: ${String(user.instructions).slice(0, 600)}` : '',
            memBlock ? `Что известно о пользователе:
${memBlock}` : '', `Сегодня ${new Date().toISOString().slice(0, 10)}.`,
          ].filter(Boolean).join('\n');
          if (snapP) await snapP;
          const addRow = (m) => { const r = insertMsg(conv.id, m); emit('message', { message: publicMessage(r) }); return r; };
          await runOpencode({ user, conv, cwd, text: (typeof attachmentsToContent(user, text, attachments, false) === 'string' ? attachmentsToContent(user, text, attachments, false) : text), model: ocModel, system: sys, signal: ac.signal, cb: {
            delta: (d) => { if (!run.partial) emit('status', { text: '' }); run.partial += d; emit('delta', { text: d }); },
            status: (t) => emit('status', { text: t }),
            toolOutput: (id, t) => emit('tool_output', { id, text: t }),
            usage: (u) => { usageAcc.prompt += u.prompt_tokens || 0; usageAcc.completion += u.completion_tokens || 0; usageAcc.cached += u.prompt_tokens_details?.cached_tokens || 0; usageAcc.calls++; },
            assistant: (content, call) => { run.partial = ''; if (!content && !call) return; addRow({ role: 'assistant', content, tool_calls: call ? [{ id: call.id, type: 'function', function: { name: call.name, arguments: call.arguments } }] : null }); },
            tool: (id, name, content, files) => {
              addRow({ role: 'tool', content: clip(String(content), 6000), tool_call_id: id, tool_name: name, attachments: files.length ? files.map((f) => ({ ...f, path: undefined })) : null });
              if (files.length) addRow({ role: 'assistant', content: '', attachments: files.map((f) => ({ ...f, path: undefined })) });
            },
          } });
        } catch (e) {
          if (ac.signal.aborted) throw e;
          console.error('opencode engine failed, fallback to legacy loop:', e.message);
          if (run.partial || db.prepare("SELECT 1 FROM messages WHERE conv_id=? AND id>? AND role!='user' LIMIT 1").get(conv.id, userRow.id)) throw e;   // уже что-то показано — не дублируем работу
          useOc = false; emit('status', { text: 'Движок opencode недоступен — работаю встроенным агентом' });
        }
      }
      // ---- Чат: движок Vercel AI SDK (цикл модель↔инструменты), выполнение инструментов — наше (execOne). Сбой до первого вывода → прежний цикл. ----
      let useAI = !useOc && conv.mode !== 'code' && !voice && prov.id !== 'perplexity' && chatEngineOn();
      if (useAI) {
        try {
          const hist0 = db.prepare('SELECT * FROM messages WHERE conv_id=? AND id>? ORDER BY id').all(conv.id, conv.summarized_upto).filter((r) => !(r.role === 'assistant' && !r.content && !r.tool_calls));
          const all = buildMessages(user, conv.id, sysFn, hist0, isVision);
          const addRow = (m) => { const r = insertMsg(conv.id, m); emit('message', { message: publicMessage(r) }); return r; };
          await runChatAI({ prov, model, system: all[0].content, messages: all.slice(1), toolDefs: tools, signal: ac.signal, maxSteps: MAX_STEPS, maxTokens, effort,
            execTool: async (call) => { const r = await execOne(call); step++; return r; }, shouldStop: () => ended,
            cb: {
              delta: (d) => { if (!run.partial) emit('status', { text: '' }); run.partial += d; emit('delta', { text: d }); },
              usage: (u) => { usageAcc.prompt += u.prompt_tokens || 0; usageAcc.completion += u.completion_tokens || 0; usageAcc.cached += u.prompt_tokens_details?.cached_tokens || 0; usageAcc.calls++; },
              assistant: (content, calls) => { run.partial = ''; addRow({ role: 'assistant', content, tool_calls: calls.length ? calls.map((c) => ({ id: c.id, type: 'function', function: { name: c.name, arguments: c.arguments } })) : null }); },
              tool: (id, name, content, files) => finish({ call: { id, function: { name } }, result: content, files }),
            } });
        } catch (e) {
          if (ac.signal.aborted) throw e;
          console.error('chat engine failed:', e.message);
          const shown = run.partial || db.prepare("SELECT 1 FROM messages WHERE conv_id=? AND id>? AND role!='user' LIMIT 1").get(conv.id, userRow.id);
          if (shown) throw e;
          useAI = false; emit('status', { text: 'Переключаюсь на встроенный движок…' });
        }
      }
      for (step = 0; !useOc && !useAI && step < MAX_STEPS; step++) {
        const hist = db.prepare('SELECT * FROM messages WHERE conv_id=? AND id>? ORDER BY id').all(conv.id, conv.summarized_upto)
          .filter((r) => !(r.role === 'assistant' && !r.content && !r.tool_calls));
        const messages = buildMessages(user, conv.id, sysFn, hist, isVision);
        run.partial = '';
        if (autoLabel && step === 0) emit('status', { text: `Авто → ${autoLabel}` });
        const callLlm = () => chatStream({
          prov, effort, messages, tools, signal: ac.signal, model, maxTokens, fallbacks, onRetry, failFast: alts.length > 0,
          onUsage: (u) => { usageAcc.prompt += u.prompt_tokens || 0; usageAcc.completion += u.completion_tokens || 0; usageAcc.cached += u.prompt_tokens_details?.cached_tokens || 0; usageAcc.calls++; },
          onText: (d) => { if (!run.partial) emit('status', { text: '' }); run.partial += d; emit('delta', { text: d }); },
        });
        let resp;
        for (;;) {
          try { resp = await callLlm(); break; }
          catch (e) {
            // основной провайдер не ответил (лимит/сбой) и текста ещё нет → переходим на следующий вариант
            if (ac.signal.aborted || run.partial || !alts.length) throw e;
            const a = alts.shift(); prov = a.prov; model = a.model; fallbacks = mkFallbacks(prov, model);
            emit('status', { text: `Переключаюсь на ${model.split('/').pop()}…` });
          }
        }
        const { content, tool_calls } = resp;
        run.partial = '';
        const aRow = insertMsg(conv.id, { role: 'assistant', content, tool_calls: tool_calls.length ? tool_calls : null });
        emit('message', { message: publicMessage(aRow) });
        if (!tool_calls.length) break;

        ended = false;
        if (tool_calls.length > 1 && tool_calls.every((c) => PAR.has(c.function.name))) {
          (await Promise.all(tool_calls.map(execOne))).forEach(finish);
        } else {
          for (const call of tool_calls) {
            if (ac.signal.aborted) break;
            finish(await execOne(call));
          }
        }
        if (ac.signal.aborted) throw new Error('aborted');
        if (ended) break;
        if (step === MAX_STEPS - 1) {
          const r = insertMsg(conv.id, { role: 'assistant', content: 'Работа заняла очень много шагов, останавливаюсь. Напиши «продолжай» — продолжу с того же места.' });
          emit('message', { message: publicMessage(r) });
        }
      }
      if (conv.mode === 'code') { const sn = await snapshotAsync(cwdFor(user, conv, conv.project_id ? db.prepare('SELECT * FROM projects WHERE id=?').get(conv.project_id) : null), `После: ${String(text || '').slice(0, 70)}`); if (sn) emit('checkpoint', { hash: sn.hash, changed: sn.changed }); }
      // Второй ИИ молча проверяет ответ до «готово» (не дольше ~4,5 с) и, найдя ошибку, правит текст на месте — без сообщений в чат.
      if (conv.mode !== 'code' && !voice && !automation && prov.id === 'river' && !ac.signal.aborted) {
        await verifyAnswer({ conv, text, startedAt, model, usageAcc, emit, ac: new AbortController() }).catch(() => {});
      }
      emit('done');
      postProcess(user, conv.id, startedAt);
    } catch (e) {
      const aborted = ac.signal.aborted;
      const r = insertMsg(conv.id, { role: 'assistant', content: aborted ? 'Остановлено.' : `Ошибка: ${e.message}` });
      emit('message', { message: publicMessage(r) });
      emit(aborted ? 'done' : 'error', { error: e.message });
    } finally {
      logUsage(user.id, usageAcc);
      run.done = true;
      runs.delete(conv.id);
      run.emitter.removeAllListeners();
    }
  })();
  return run;
}

function logUsage(uid, u) {
  if (!u.calls) return;
  const day = new Date().toISOString().slice(0, 10);
  db.prepare('INSERT INTO usage(user_id,day,prompt,completion,calls,cached) VALUES (?,?,?,?,?,?) ON CONFLICT(user_id,day) DO UPDATE SET prompt=prompt+excluded.prompt, completion=completion+excluded.completion, calls=calls+excluded.calls, cached=cached+excluded.cached')
    .run(uid, day, u.prompt, u.completion, u.calls, u.cached || 0);
}

const REMEMBER = /запомн|меня зовут|my name is|remember (that|this)|я (предпочитаю|люблю|работаю|живу)/i;
async function postProcess(user, convId, fromId) {
  try {
    const conv = db.prepare('SELECT * FROM conversations WHERE id=?').get(convId);
    const first = db.prepare("SELECT content FROM messages WHERE conv_id=? AND role='user' ORDER BY id LIMIT 1").get(convId)?.content || 'Чат';
    if (conv.title === 'Новый чат') { // название без обращения к модели
      const t = first.replace(/^\[Автоматизация[^\]]*\]\s*/, '').replace(/\s+/g, ' ').trim();
      db.prepare('UPDATE conversations SET title=? WHERE id=?').run((t.length > 44 ? t.slice(0, 42).replace(/\s+\S*$/, '') + '…' : t) || 'Чат', convId);
    }
    // извлечение воспоминаний — только когда пользователь явно сообщил что-то о себе / просил запомнить
    const lastUser = db.prepare("SELECT content FROM messages WHERE conv_id=? AND id>=? AND role='user' ORDER BY id DESC LIMIT 1").get(convId, fromId)?.content || '';
    if (REMEMBER.test(lastUser)) {
      const rows = db.prepare("SELECT role, content FROM messages WHERE conv_id=? AND id>=? AND role IN ('user','assistant') AND content!='' ORDER BY id").all(convId, fromId);
      await extractMemories(user.id, rows.map((r) => `${r.role}: ${r.content}`).join('\n').slice(0, 3000));
    }
  } catch (e) { console.error('postProcess', e.message); }
}

const DEFAULT_SKILLS = [
  ['android-apk', 'Сборка Android APK на сервере', 'Сборка APK: 1) git clone репозиторий; 2) убедись, что ANDROID_HOME=/opt/android-sdk, JDK 17; 3) в корне проекта: echo "sdk.dir=$ANDROID_HOME" > local.properties; 4) ./gradlew assembleDebug --no-daemon (timeout 1800, лучше background=true и tail лога); 5) APK в app/build/outputs/apk/debug/; 6) отправь send_file. При ошибке лицензий: yes | sdkmanager --licenses.'],
  ['github-pr', 'Создание ветки, коммита и Pull Request', 'Работа с GitHub: git checkout -b feature/...; правки; git add -A && git commit -m "..."; git push -u origin HEAD (токен подставляется автоматически); PR через github_api POST /repos/OWNER/REPO/pulls {title, head, base, body}. Не пушь в main без просьбы.'],
  ['server-health', 'Диагностика состояния сервера', 'Проверь: uptime; free -h; df -h; ss -tlnp; systemctl --failed; journalctl -p err -n 30 --no-pager; docker ps (если есть). Дай краткий вывод и рекомендации.'],
  ['code-review', 'Ревью изменений в репозитории', 'git diff / git log -p -n 3; ищи баги, гонки, утечки, пропущенные проверки, небезопасный ввод; для каждого замечания укажи файл:строку и исправление. Запусти тесты/линтер, если они есть.'],
];
function ensureSkills(uid) {
  if (db.prepare('SELECT 1 FROM skills WHERE user_id=? LIMIT 1').get(uid)) return;
  for (const [n, d, c] of DEFAULT_SKILLS) db.prepare('INSERT OR IGNORE INTO skills(user_id,name,description,content) VALUES (?,?,?,?)').run(uid, n, d, c);
}
export { ensureSkills };

setStarter((user, conv, prompt, opts) => startRun(user, conv, prompt, null, opts || {}));
