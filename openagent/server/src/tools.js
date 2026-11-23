import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { generateImage, imageEnabled } from './images.js';
import crypto from 'node:crypto';
import mime from './mime.js';
import { db, now } from './db.js';
import { workspaceOf, resolvePath, askpassPath } from './workspace.js';
import { webSearch, fetchPage } from './search.js';
import { createSchedule, listSchedules, deleteSchedule } from './scheduler.js';
import { chartSvg, plotSvg, geometrySvg, graphviz, sanitizeSvg, calculate } from './viz.js';
import { installFromGithub, searchRepos } from './skills.js';
import { extractText, DOC_EXT } from './extract.js';
import { transcribeFile, AUDIO_EXT } from './transcribe.js';
import { describeImage } from './vision.js';
import { pplxUp, pplxSearch } from './perplexity.js';
import { spawnSync as _spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const DOCS_PY = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'py', 'docs.py');
import { deploySite, listSites, deleteSite } from './sites.js';
import { lookup, LOOKUP_SOURCES } from './connectors.js';
import { mcpToolDefs, mcpCall } from './mcp.js';
import { injectSecrets, maskSecrets, tasksTool, listSecretNames } from './extras.js';
import { mailTool, hasMail } from './mail.js';
import { dataQuery } from './datatools.js';
import { createMission, updateMission, missionsText } from './missions.js';
import { assertPublicUrl, safeFetch } from './safeurl.js';
import { saveMemory, searchMemories, forgetMemory } from './memory.js';

const OUT_LIMIT = 3500;
const jobs = new Map();
const SKIP = new Set(['node_modules', '.git', '.oa-snap', 'build', '.gradle', 'dist', '__pycache__', '.venv']);

function walk(root, max = 4000) {
  const out = []; const stack = [root];
  while (stack.length && out.length < max) {
    const d = stack.pop();
    let ents; try { ents = fs.readdirSync(d, { withFileTypes: true }); } catch { continue; }
    for (const e of ents) { const p = path.join(d, e.name); if (e.isDirectory()) { if (!SKIP.has(e.name)) stack.push(p); } else out.push(p); }
  }
  return out;
}
const globRe = (g) => {   // маска → regex за один проход (раньше замены портили друг друга, и `*.txt` не находил ничего)
  let r = '';
  for (let i = 0; i < g.length; i++) {
    const c = g[i];
    if (c === '*') { if (g[i + 1] === '*') { i++; if (g[i + 1] === '/') { i++; r += '(?:.*/)?'; } else r += '.*'; } else r += '[^/]*'; }
    else if (c === '?') r += '[^/]';
    else r += c.replace(/[.+^${}()|\\[\]]/g, '\\$&');
  }
  return new RegExp('^' + r + '$');
};

const fn = (name, description, properties, required = []) => ({
  type: 'function',
  function: { name, description, parameters: { type: 'object', properties, required } },
});

const T = (name, description, properties = {}, required = []) => ({ type: 'function', function: { name, description, parameters: { type: 'object', properties, required } } });
const S = { type: 'string' }, N = { type: 'number' }, I = { type: 'integer' }, B = { type: 'boolean' }, O = { type: 'object' };
const A = (items) => ({ type: 'array', items });
const THEME = { type: 'string', enum: ['dark', 'light'] };

// Каталог инструментов — описания намеренно короткие: они уходят в каждый запрос и стоят токенов.
const CATALOG = {
  web_search: T('web_search', 'Поиск в интернете (Exa или Perplexity — по настройкам пользователя: результаты + текст страниц). category: news|research paper|github|pdf|company|tweet; days — только свежее за N дней; domains — ограничить сайтами.', { query: S, queries: { ...A(S), description: 'несколько запросов сразу (параллельно, до 4)' }, read: { ...I, description: '0-3 страниц' }, category: S, days: I, domains: A(S) }, []),
  web_fetch: T('web_fetch', 'Текст страницы по URL.', { url: S, max_chars: I }, ['url']),
  ask_user: T('ask_user', 'Спросить пользователя и завершить ход. type: single (один вариант), multi (несколько), text (свободный ввод).', { question: S, options: A(S), type: { type: 'string', enum: ['single', 'multi', 'text'] } }, ['question']),
  calculate: T('calculate', 'Точное вычисление выражения (sin, sqrt, ln, ^, pi).', { expression: S }, ['expression']),
  memory_save: T('memory_save', 'Запомнить устойчивый факт (только если просили). Без секретов.', { content: S, kind: S, importance: N }, ['content']),
  memory_forget: T('memory_forget', 'Забыть воспоминание по id.', { id: I }, ['id']),
  todo_write: T('todo_write', 'План задач (чек-лист для пользователя). Передавай весь список. status: pending|in_progress|done.', { todos: A({ type: 'object', properties: { text: S, status: S }, required: ['text', 'status'] }) }, ['todos']),
  bash: T('bash', 'Команда bash на сервере (root). Долгое — большой timeout.', { command: S, timeout: I, background: B, cwd: S, confirmed: { ...B, description: 'только после явного «да» пользователя' } }, ['command']),
  read_file: T('read_file', 'Прочитать файл (текст, а также PDF/DOCX/XLSX/PPTX).', { path: S, offset: I, limit: I }, ['path']),
  read_files: T('read_files', 'Прочитать сразу несколько файлов за один вызов.', { paths: A(S), limit: { ...I, description: 'строк на файл' } }, ['paths']),
  multi_edit: T('multi_edit', 'Несколько правок одного файла за один вызов (атомарно: если одна не применилась — файл не меняется). edits: [{old,new,replace_all?}].', { path: S, edits: A(O) }, ['path', 'edits']),
  write_file: T('write_file', 'Записать файл.', { path: S, content: S }, ['path', 'content']),
  edit_file: T('edit_file', 'Заменить фрагмент old→new (один раз или replace_all).', { path: S, old: S, new: S, replace_all: B }, ['path', 'old', 'new']),
  list_dir: T('list_dir', 'Список файлов.', { path: S }),
  grep: T('grep', 'Поиск regex по файлам.', { pattern: S, path: S, glob: S, ignore_case: B }, ['pattern']),
  glob: T('glob', 'Поиск файлов по маске.', { pattern: S, path: S }, ['pattern']),
  generate_image: T('generate_image', 'Сгенерировать изображение/фото/арт/иллюстрацию/логотип по описанию (бесплатная модель FLUX). prompt — подробно на АНГЛИЙСКОМ: объект, стиль, свет, композиция. aspect: square|portrait|landscape. Модель выбирается автоматически (не указывай). Картинка сама отправляется пользователю. При ошибке НЕ повторяй вызов — сообщи причину.', { prompt: S, aspect: S }, ['prompt']),
  phone: T('phone', 'Управление ТЕЛЕФОНОМ пользователя (выполняется в приложении). action: open_app{app} | close_app{app} | alarm{hour,minute,label} | timer{seconds,label} | stopwatch{op:start|stop|status} | flashlight{on} | toggle{target:wifi|bluetooth|airplane|dnd|autorotate|nfc|hotspot|location|battery_saver,on} | volume{level:0-100,target:media|ring|alarm} | brightness{level:0-100} | open_url{url} | system{op:home|back|recents|notifications|quick_settings|lock} | read_screen (список элементов экрана, каждый с номером [N] и координатами) | tap{index:N | text | x,y,scroll?} нажать — НАДЁЖНЕЕ ВСЕГО по номеру index из последнего списка; если элемента нет на экране — text + scroll:true; после нажатия приходит обновлённый экран, а при «⚠ экран не изменился» нажми точнее | long_press{text | x,y} | scroll{direction:down|up|left|right,times} прокрутить ленту (down = дальше вниз) | swipe{x,y,x2,y2} | type{text,field?,append?,submit?} ввести текст в поле | enter подтвердить/искать | wait{seconds} | media{op:play|pause|toggle|next|prev|stop|forward|rewind|volume_up|volume_down|status} управление музыкой/плеером | music_play{query,app?} включить музыку по запросу (app: Spotify, YouTube Music…) | contacts{query} найти контакт | call{to,confirmed} позвонить (to: имя или номер) | sms{to,text,confirmed} | message{app:whatsapp|telegram,to,text,confirmed} написать в мессенджер | remind{text,minutes | at:«2026-11-20T18:30»} напоминание (уведомление на телефоне точно в срок) | calendar_list{days} события календаря | calendar_add{title,at,minutes,location} | notifications{app?,minutes?} недавние уведомления (что пришло в Telegram/почту и т.д.) | location где пользователь сейчас (широта,долгота) | http_get{url,method?,headers?,body?,save_as?} запрос С ТЕЛЕФОНА (обходит блокировки по региону/IP сервера; save_as=имя → ответ сохраняется файлом phone-data/ИМЯ на сервере для python, в ответе — структура и пример) | site_probe{url} читает HTML и скрипты сайта С ТЕЛЕФОНА без браузера и находит адреса API/WebSocket (работает, даже если web_capture не открывает страницу) | web_capture{url,seconds≤25,js?,hook?} открывает страницу в скрытом браузере телефона (с JS, как настоящий браузер) и показывает: какие API/WebSocket она вызывает и что отвечают, JS-ошибки, глобальные объекты страницы; js — свой JavaScript, результат вернётся (напр. «JSON.stringify(window.__STATE__)», «JSON.stringify(localStorage)»); hook:false — без перехвата, если страница с ним падает | watch_screen{until:слова через запятую,seconds≤45} ждать появления текста на экране (отклик водителя, статус заказа) | screen (посмотреть экран: делает снимок и описывает его; вызывай ТОЛЬКО когда пользователь сам просит посмотреть/объяснить/прочитать, что на экране, и не чаще, чем нужно). Для действий в приложениях: open_app → read_screen → tap/type/scroll (после каждого действия приходит обновлённый экран; нажимай по тексту кнопки, иначе по координатам из списка), повторяй, пока цель не достигнута (не больше ~12 шагов), затем коротко ответь. Для музыки используй media / music_play, не тапай без нужды. Если сказано, что нужно разрешение — передай это пользователю.', { action: S, app: S, hour: I, minute: I, seconds: I, label: S, on: B, target: S, level: I, url: S, op: S, text: S, x: I, y: I, x2: I, y2: I, direction: S, times: I, query: S, field: S, append: B, submit: B, js: S, hook: B, index: I, scroll: B, method: S, headers: O, body: S, save_as: S, at: S, minutes: I, days: I, to: S, until: S, confirmed: B }, ['action']),
  create_file: T('create_file', 'Создать файл ЛЮБОГО формата и отправить его пользователю. docx/pdf: content — Markdown (# заголовки, - списки, 1. нумерация, | таблицы |, **жирный**, *курсив*, ``` код, --- разрыв страницы). pptx: Markdown, слайды разделяй строкой ---, заголовок слайда «# …», пункты «- …», заметки «Notes: …». xlsx: JSON {"sheets":[{"name":"Лист","rows":[["A","B"],[1,2],["=SUM(A2:B2)"]]}]} или CSV. Остальное (txt, md, html, csv, json, xml, yaml, py, js, sql, …): content — сам текст. path — имя файла с расширением.', { path: S, content: S }, ['path', 'content']),
  edit_document: T('edit_document', 'Отредактировать существующий docx/xlsx/pptx, сохранив оформление. ops — список операций. docx: {op:"replace",old,new} | {op:"append",md} | {op:"insert_after",anchor,md} | {op:"delete_paragraph",contains} | {op:"set_cell",table,row,col,text}. xlsx: {op:"set",sheet,cell,value} | {op:"append_row",sheet,values} | {op:"set_range",sheet,start,rows} | {op:"add_sheet",name,rows} | {op:"delete_sheet",name} | {op:"replace",old,new}. pptx: {op:"replace",old,new} | {op:"add_slide",title,bullets,notes} | {op:"delete_slide",index} | {op:"set_text",slide,shape,text}. Для текстовых файлов — edit_file/write_file. Изменённый файл отправляется пользователю.', { path: S, ops: A(O) }, ['path', 'ops']),
  send_file: T('send_file', 'Отправить файл пользователю (APK, архив).', { path: S, caption: S }, ['path']),
  python: T('python', 'Python 3 (sympy, numpy, matplotlib). Для точных расчётов и проверки. Новые картинки показываются автоматически.', { code: S, timeout: I }, ['code']),
  chart: T('chart', 'График/диаграмма/таблица картинкой. type: bar|hbar|line|area|scatter|pie|donut|histogram|table. bar/line/area: labels+series[{name,data}]; scatter: series[{name,data:[[x,y]]}]; pie/donut/histogram: labels+values (histogram: values); table: columns+rows.', { type: S, title: S, labels: A(S), values: A(N), series: A(O), columns: A(S), rows: A(A({})), xlabel: S, ylabel: S, stacked: B, trend: B, bins: I, theme: THEME }, ['type']),
  plot_function: T('plot_function', 'График функций и параметрических кривых. Выражения: + - * / ^ sin cos tan sqrt abs ln exp pi.', { functions: A(S), parametric: A(O), xmin: N, xmax: N, ymin: N, ymax: N, points: A(O), equal: B, title: S, theme: THEME }),
  geometry: T('geometry', 'Точный чертёж по координатам. objects: {type:point,name,x,y}|segment{a,b,dashed,label}|line|polygon{points,fill}|circle{center,r,fill}|arc{center,r,from,to}|angle{vertex,p1,p2,label,right}|vector|text{x,y,text}. Ссылки — имя точки или [x,y]. Сначала посчитай координаты.', { objects: A(O), grid: B, axes: B, title: S, theme: THEME }, ['objects']),
  diagram: T('diagram', 'Схема/граф/блок-схема на Graphviz DOT.', { dot: S, title: S, theme: THEME }, ['dot']),
  draw_svg: T('draw_svg', 'Произвольный SVG-рисунок (<svg viewBox>), в том числе АНИМИРОВАННЫЙ: в приложении анимация играет (SMIL: <animate>, <animateTransform>, <animateMotion>, <set>; CSS: @keyframes в <style>; JavaScript не работает). Для зацикливания repeatCount="indefinite" / animation-iteration-count:infinite. Один вызов = один рисунок: не перерисовывай сам, пока не попросят правки. Фон тёмный добавится сам — светлые линии/текст.', { svg: S, title: S, theme: THEME }, ['svg']),
  deploy_site: T('deploy_site', 'Опубликовать статический сайт на домене: https://<домен>/s/<name>/. Либо dir (папка с index.html, путь от текущей), либо files {путь: содержимое}. Возвращает URL; в приложении открывается превью.', { name: S, title: S, dir: S, files: O, spa: B }, ['name']),
  html_app: T('html_app', 'Интерактивное мини-приложение в одном HTML (калькулятор, игра, симулятор, визуализация, форма). Показывается в чате «живым» и сохраняется как сайт. Весь CSS/JS внутри, без внешних зависимостей, мобильная вёрстка, тёмная тема.', { html: S, title: S }, ['html', 'title']),
  list_sites: T('list_sites', 'Список опубликованных сайтов.'),
  delete_site: T('delete_site', 'Удалить сайт.', { name: S }, ['name']),
  skill_load: T('skill_load', 'Загрузить навык по имени.', { name: S }, ['name']),
  skill_save: T('skill_save', 'Сохранить навык.', { name: S, description: S, content: S }, ['name', 'content']),
  skill_search: T('skill_search', 'Искать навыки/плагины на GitHub.', { query: S }, ['query']),
  skill_install: T('skill_install', 'Установить навыки из репозитория GitHub (owner/repo).', { repo: S }, ['repo']),
  schedule_create: T('schedule_create', 'Автоматизация: запускать prompt по расписанию. every_minutes (мин. 5) или run_in_minutes. СЛЕЖЕНИЕ за страницей (цена, наличие, новости): watch_url (+ watch_text — слово/фраза, за появлением которой следить) и every_minutes≥15: агент запускается, только если страница изменилась.', { name: S, prompt: S, every_minutes: I, run_in_minutes: I, mode: { type: 'string', enum: ['chat', 'code'] }, watch_url: S, watch_text: S }, ['name', 'prompt']),
  schedule_list: T('schedule_list', 'Список автоматизаций.'),
  schedule_delete: T('schedule_delete', 'Удалить автоматизацию.', { id: I }, ['id']),
  delegate: T('delegate', 'Поручить подзадачу под-агенту (отдельный контекст, параллельно). Вернёт итог.', { task: S }, ['task']),
  http_request: T('http_request', 'HTTP-запрос.', { method: S, url: S, headers: O, body: S }, ['url']),
  github_api: T('github_api', 'GitHub REST API от имени пользователя.', { method: S, path: S, body: O }, ['path']),
  lookup: T('lookup', 'Данные без ключей: weather(город) | wiki(тема) | rates(USD RUB / bitcoin) | arxiv | hn | geocode(адрес→координаты) | reverse(«lat,lon»→адрес) | nearby(«lat,lon аптека|кафе|банкомат|заправка…» — ближайшие места) | rss(url).', { source: S, query: S, lang: S }, ['source']),
  tasks: T('tasks', 'Список дел пользователя: op=add(text,due?) | list | done(id) | delete(id).', { op: S, text: S, due: S, id: I }, ['op']),
  data_query: T('data_query', 'Разбор сохранённого ответа API (файл из phone-data) БЕЗ написания кода. op: show | find{query} — записи, содержащие текст | nearest{lat,lon,n,filter?} — ближайшие записи по координатам (filter — только записи с этим текстом, напр. номер маршрута) | list — файлы.', { op: S, file: S, query: S, lat: { type: 'number' }, lon: { type: 'number' }, n: I, filter: S }, ['op']),
  mail: T('mail', 'Почта пользователя (IMAP/SMTP). op: list{unseen=true,limit,since_days} — входящие | search{query} | read{uid} — прочитать письмо | mark{uid,action:read|unread|flag|archive} | send{to,subject,text,reply_to_uid?,confirmed}. uid берётся из list/search. Для отправки без прямой просьбы пользователя нужен confirmed=true после его «да».', { op: S, uid: S, query: S, limit: I, since_days: I, unseen: B, action: S, to: S, subject: S, text: S, reply_to_uid: I, confirmed: B, account: S, folder: S }, ['op']),
  mission_create: T('mission_create', 'Запустить МИССИЮ — долгую цель, над которой ты будешь работать сам по шагам в фоне (поиск вариантов, мониторинг, сбор информации, ведение дела) и отчитаешься, когда готово или нужен ответ пользователя. check_every_minutes — как часто делать шаг (15…10080, по умолчанию 60).', { goal: S, check_every_minutes: I }, ['goal']),
  mission_update: T('mission_update', 'Отчёт по миссии после шага: note — что сделано/следующий шаг/итог/вопрос; status: active | done | blocked.', { id: I, note: S, status: S }, ['id', 'note']),
  mission_list: T('mission_list', 'Список миссий пользователя и их прогресс.', {}, []),
  process: T('process', 'Фоновые процессы bash: list|log|kill.', { action: S, pid: I, lines: I }, ['action']),
};

const RX = {
  phone: /автобус|трамва|троллейбус|остановк|маршрут\S* (№|номер)?|go2|bus-pvl|когда (приедет|будет)|напомни|напоминани|календар|встреч[ауи]|событи[яе]|уведомлен|где я\b|мо[её] местоположен|рядом со мной|ближайш|такси|taxi|indrive|индрайв|позвони|набери|напиши (ему|ей|им|в |кому)|смс|sms|whatsapp|ватсап|вотсап|telegram|телеграм|телега|почт[уаыеу]|gmail|письм|контакт|мессендж|маркетплейс|wildberries|ozon|озон|kaspi|каспи|музык|песн[юяь]|трек|плейлист|пауз[ауе]|следующ\S+ (трек|песн)|предыдущ\S+ (трек|песн)|спотифай|spotify|нажми|тапни|кликни|прокрут|пролистай|свайп|листай|введи в|напиши в|будильник|таймер|секундомер|фонарик|фонар[ьи]\b|вай-?фай|wi-?fi|блютуз|bluetooth|авиарежим|режим полёта|режим полета|не беспокоить|яркост|громкост|тише|громче|автоповорот|на телефоне|на экране телефона|(открой|запусти|закрой|выключи|включи|останови)\s+(приложени|ютуб|youtube|телеграм|telegram|ватсап|whatsapp|инстаграм|instagram|тикток|tiktok|хром|chrome|камер|галере|настройки|карты|музык|spotify|браузер|калькулятор|часы)/i,
  file: /файл|документ|таблиц|презентац|слайд|pdf|word|excel|docx|xlsx|pptx|csv|json|отчёт|отчет|резюме|договор|накладн|смет[ауы]|реферат|эксель|ворд|пдф|архив|транскриб|расшифр|аудио|запись|подкаст|видео/i,
  img: /сгенерируй|генерац\S* (картин|изображен|фото|арт)|(нарису|создай|сделай|придумай)\S* (мне )?(картин|изображен|фото|фотк|арт|иллюстрац|логотип|постер|обои|аватар|баннер|обложк)|иллюстрац|логотип|обои на|generate .{0,12}image|midjourney|stable diffusion|flux/i,
  viz: /svg|анимац|анимирован|гифк|gif|график|диаграмм|чертеж|чертёж|нарису|схем|гистограмм|таблиц|визуализ|построй|геометр|парабол|окружност|треугольн|вектор|plot|chart|diagram|draw/i,
  math: /реши|задач|вычисл|интеграл|производн|уравнен|вероятн|матриц|python|посчита|статистик|симуляц|докажи|найди (знач|корн|сумм|площ|объ)|\d\s*[-+*/^×÷]\s*\d/i,
  pub: /опублику|опубликов|задеплой|деплой|выложи|разверни|захост|размести|на домен|publish|deploy|\bhost\b|в интернет|ссылк.{0,20}сайт|сайт.{0,20}ссылк/i,
  site: /сайт|веб|лендинг|landing|страниц|деплой|опублику|превью|html|приложени|игр[ауы]|калькулятор|интерактив|симулятор|виджет|форм[ауы]|site|app\b/i,
  skill: /навык|скилл|плагин|skill|plugin/i,
  sched: /расписан|автоматиз|каждые|каждый (час|день|день)|по таймеру|регулярн|cron|через \d+ ?(мин|час)/i,
  mem: /запомн|забудь|remember|forget/i,
  gh: /pull request|\bPR\b|issue|релиз|workflow|github/i,
  http: /\bapi\b|curl|http|эндпоинт|запрос к/i,
  look: /рядом|ближайш|поблизости|адрес этого места|погод|температур|на улице|прогноз|википед|курс\S* (доллар|евро|валют|рубл|тенге|юан)|доллар|евро\b|биткоин|bitcoin|крипт|эфир|arxiv|hacker news|\bhn\b|\brss\b|координат|геокод|где находится|wikipedia/i,
  mail: /почт|письм|e-?mail|емейл|gmail|inbox|входящ|рассылк|непрочитан/i,
  mission: /миссию|миссия|долгосрочн|пока не (найдёшь|найдешь|получится|будет|появится)|в течение (дня|недели|месяца|\d+ ?(дн|нед|час))|веди (это|мой|моё|проект|дело)|доведи до конца|самостоятельно (веди|доведи|займись)|займись (этим )?сам|продолжай искать|держи в курсе|следи и сообщ/i,
  task: /задач[ауи]\b|список дел|to-?do|туду|напомни|добавь в дела|мои дела/i,
  proc: /процесс|в фоне|фоново|background|лог/i,
};

/** Набор инструментов под запрос: лишние не отправляем — экономия токенов на каждом шаге. */
export function toolDefs(user, mode = 'code', o = {}) {
  const text = o.text || '';
  const owner = user.role === 'owner';
  const n = new Set(['web_search', 'web_fetch', 'ask_user', 'calculate']);
  const add = (...x) => x.forEach((k) => n.add(k));
  if (mode === 'code') {
    add('read_file', 'read_files', 'write_file', 'edit_file', 'multi_edit', 'list_dir', 'grep', 'glob', 'send_file', 'todo_write');
    if (RX.pub.test(text) || o.used?.has('deploy_site')) add('deploy_site', 'list_sites', 'delete_site');
    if (RX.site.test(text)) add('html_app');
    if (owner) add('bash', 'python');
  } else {
    if (RX.math.test(text) && owner) add('python');
    if (RX.site.test(text)) add('html_app');
    if (RX.pub.test(text) || o.used?.has('deploy_site')) add('deploy_site');
  }
  if (!o.automation && (mode === 'code' || RX.file.test(text) || o.hasFiles || o.used?.has('create_file') || o.used?.has('edit_document'))) add('create_file', 'edit_document', 'read_file');
  if (!o.automation && (o.voice || RX.phone.test(text) || o.used?.has('phone'))) add('phone');
  if (RX.img.test(text) && imageEnabled()) add('generate_image');
  if (RX.viz.test(text) || o.used?.has('chart')) add('chart', 'plot_function', 'geometry', 'diagram', 'draw_svg');
  if (RX.pub.test(text)) add('list_sites', 'delete_site');
  if (RX.skill.test(text)) add('skill_load', 'skill_save', 'skill_search', 'skill_install');
  if (RX.sched.test(text)) add('schedule_create', 'schedule_list', 'schedule_delete');
  if (RX.mem.test(text)) add('memory_save', 'memory_forget');
  if (user.github_login && RX.gh.test(text)) add('github_api');
  if (RX.http.test(text)) add('http_request');
  if (/автобус|трамва|троллейбус|остановк|go2|bus-pvl|phone-data/i.test(text) || o.used?.has('data_query')) add('data_query');
  if (RX.look.test(text) || /такси|taxi|автобус|трамва|остановк/i.test(text) || o.used?.has('lookup')) add('lookup');
  if (RX.task.test(text) || o.used?.has('tasks')) add('tasks');
  const mailOn = hasMail(user.id);
  if (mailOn && (RX.mail.test(text) || o.used?.has('mail') || /\[МИССИЯ/.test(text))) add('mail');
  if (!o.automation && (RX.mission.test(text) || o.used?.has('mission_create'))) add('mission_create', 'mission_list', 'mission_update');
  if (o.automation && /\[МИССИЯ/.test(text)) add('mission_update', 'lookup');
  if (owner && mode === 'code' && RX.proc.test(text)) add('process');
  if (o.effort === 'high' && mode === 'code') add('delegate');
  for (const u of o.used || []) if (CATALOG[u]) add(u); // инструменты, уже применявшиеся в диалоге
  if (o.voice) for (const k of [...n]) if (!['web_search', 'phone', 'calculate', 'lookup', 'data_query'].includes(k)) n.delete(k);   // звонок: только нужное — короче запрос, быстрее ответ
  if (o.automation) ['ask_user', 'schedule_create', 'schedule_delete', 'schedule_list', 'delegate', 'mission_create', 'mission_list'].forEach((k) => n.delete(k));
  if (!owner) ['bash', 'python', 'process'].forEach((k) => n.delete(k));
  const base = [...n].map((k) => CATALOG[k]).filter(Boolean);
  return o.voice || o.noMcp ? base : base.concat(mcpToolDefs(user.id));
}
export const ALL_TOOL_NAMES = Object.keys(CATALOG);
/** Описание инструмента в формате функции Deepgram Voice Agent. */
export const voiceFunction = (name) => { const d = CATALOG[name]?.function; return d ? { name: d.name, description: d.description.slice(0, 600), parameters: d.parameters } : null; };


const RISKY = /(\bsystemctl\s+(enable|start|restart|reload)\b|\bservice\s+\S+\s+(start|restart)\b|\bnohup\b|\bpm2\b|\bcrontab\b|\bat\s+now\b|docker(\s+compose)?\s+(run\s+.*-d|up\b.*-d|compose\s+up)|\bgit\s+push\b|\brm\s+-[a-z]*r[a-z]*f?\s+(\/|~|\$HOME)(\s|$)|\bmkfs\b|\bdd\s+if=|\bshutdown\b|\breboot\b|\bnpm\s+publish\b|\bkubectl\s+(apply|delete)\b|\bscreen\s+-dm|\btmux\s+new(-session)?\s+-d|\bsetsid\b|\bdisown\b|\bsystemd-run\b)/i;
function riskCheck(args, ctx) {
  if (ctx.autonomy !== 'ask' || args.confirmed) return null;
  const why = args.background ? 'запуск в фоне' : (String(args.command).match(RISKY)?.[0] || null);
  if (!why) return null;
  return `ОТКАЗАНО (режим «спрашивать»): команда выглядит рискованной или долгоживущей («${String(why).trim()}»). Не выполняй её сам. Вызови ask_user с вопросом и вариантами «Да, выполнить» / «Нет, не надо». Повтори команду с confirmed=true только после явного «Да» от пользователя. Если пользователь просил запустить что-то ОДИН РАЗ — запусти на переднем плане с timeout и без nohup/background.`;
}
const trunc = (s, n = OUT_LIMIT) => (s.length > n ? `[... обрезано ${s.length - n} символов ...]\n${s.slice(-n)}` : s);

function shellEnv(user) {
  const env = { ...process.env, TERM: 'dumb', GIT_TERMINAL_PROMPT: '0', GIT_ASKPASS: askpassPath(), DEBIAN_FRONTEND: 'noninteractive' };
  delete env.JWT_SECRET; delete env.SMTP_PASS; delete env.RIVER_API_KEY; delete env.MISTRAL_API_KEY; delete env.DEEPGRAM_API_KEY; delete env.FISH_API_KEY; delete env.TURNSTILE_SECRET;
  const u = db.prepare('SELECT github_token FROM users WHERE id=?').get(user.id);
  if (u?.github_token) { env.GITHUB_TOKEN = u.github_token; env.GH_TOKEN = u.github_token; }
  return env;
}

function runBash(user, args, ctx) {
  return new Promise((resolve) => {
    const ws = workspaceOf(user.id);
    const cwd = args.cwd ? resolvePath(user, args.cwd, ctx.cwd) : (ctx.cwd || ws);
    const timeout = Math.min(Math.max(+args.timeout || 120, 1), 3600) * 1000;
    if (args.background) {
      const log = path.join(ws, `.bg-${Date.now()}.log`);
      const out = fs.openSync(log, 'a');
      const p = spawn('bash', ['-lc', args.command], { cwd, env: shellEnv(user), detached: true, stdio: ['ignore', out, out] });
      p.unref();
      jobs.set(p.pid, { pid: p.pid, cmd: args.command.slice(0, 120), log, started: Date.now(), userId: user.id });
      return resolve(`Запущено в фоне. pid=${p.pid}, лог: ${log}\nПроверка: tail -n 50 ${log}; kill -0 ${p.pid} && echo running`);
    }
    const p = spawn('bash', ['-lc', args.command], { cwd, env: shellEnv(user), detached: true });
    let out = '';
    let killed = '';
    const push = (d) => { const s = d.toString(); out += s; if (out.length > 400000) out = out.slice(-200000); ctx.onOutput?.(s); };
    p.stdout.on('data', push); p.stderr.on('data', push);
    const kill = (why) => { killed = why; try { process.kill(-p.pid, 'SIGKILL'); } catch {} };
    const timer = setTimeout(() => kill(`таймаут ${timeout / 1000}с`), timeout);
    const onAbort = () => kill('остановлено пользователем');
    ctx.signal?.addEventListener('abort', onAbort);
    p.on('close', (code) => {
      clearTimeout(timer);
      ctx.signal?.removeEventListener('abort', onAbort);
      resolve(`${trunc(out) || '(нет вывода)'}\n[exit ${killed ? `killed: ${killed}` : code}]`);
    });
    p.on('error', (e) => { clearTimeout(timer); resolve(`Ошибка запуска: ${e.message}`); });
  });
}

function htmlToText(html) {
  return html
    .replace(/<(script|style|noscript)[\s\S]*?<\/\1>/gi, '')
    .replace(/<br\s*\/?>|<\/(p|div|li|h\d|tr)>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n\n').trim();
}

export function registerFile(user, absPath, name) {
  const st = fs.statSync(absPath);
  const id = crypto.randomBytes(12).toString('hex');
  name = name || path.basename(absPath);
  db.prepare('INSERT INTO files(id,user_id,name,mime,size,path,created_at) VALUES (?,?,?,?,?,?,?)')
    .run(id, user.id, name, mime(name), st.size, absPath, now());
  return { id, name, mime: mime(name), size: st.size };
}

function emitImage(user, ctx, svg, title) {
  if (!svg || svg.length < 20) throw new Error('Пустое изображение');
  const dir = path.join(workspaceOf(user.id), 'charts'); fs.mkdirSync(dir, { recursive: true });
  const name = `${crypto.randomBytes(4).toString('hex')}.svg`;
  const p = path.join(dir, name); fs.writeFileSync(p, svg);
  const f = registerFile(user, p, `${String(title).replace(/[^\p{L}\p{N} _.-]+/gu, '').slice(0, 40) || 'image'}.svg`);
  ctx.attach?.({ ...f, caption: title });
  return `Изображение «${title}» показано пользователю в чате. Оно уже готово — НЕ рисуй его заново и не вызывай инструмент повторно, пока пользователь не попросит правки; ответь коротко (1–2 предложения, что нарисовано${/<animate|@keyframes/i.test(svg) ? ' и что анимируется' : ''}).`;
}

// ответ HTTP-запроса с телефона: коротко показываем модели, а целиком кладём в файл для python
function shapeOf(v, d = 0) {
  if (Array.isArray(v)) return `массив[${v.length}]${v.length ? ' из ' + shapeOf(v[0], d + 1) : ''}`;
  if (v && typeof v === 'object') { const ks = Object.keys(v); return d >= 2 ? `{${ks.slice(0, 12).join(',')}}` : '{' + ks.slice(0, 14).map((k) => `${k}: ${shapeOf(v[k], d + 1)}`).join(', ') + (ks.length > 14 ? ', …' : '') + '}'; }
  return v === null ? 'null' : typeof v === 'string' ? `"${v.slice(0, 24)}"` : String(v);
}
function summarizeHttp(user, args, status, body) {
  let j = null; try { j = JSON.parse(body); } catch {}
  let saved = '';
  if (args.save_as) {
    const name = String(args.save_as).replace(/[^\w.-]+/g, '_').slice(0, 60) || 'data.json';
    const dir = path.join(workspaceOf(user.id), 'phone-data'); fs.mkdirSync(dir, { recursive: true });
    const file = path.join(dir, name); fs.writeFileSync(file, body);
    saved = `\nСохранено: ${file} (${Math.round(body.length / 1024)} КБ) — читай в python.`;
  }
  const head = `HTTP ${status} · ${Math.round(body.length / 1024) || '<1'} КБ${saved}`;
  if (args.save_as) return `${head}\n${j ? 'Структура: ' + shapeOf(j).slice(0, 1200) : 'Не JSON. Начало: ' + body.slice(0, 500)}\nПример: ${(j ? JSON.stringify(Array.isArray(j) ? j.slice(0, 2) : j).slice(0, 700) : '')}`;
  return `${head}\n${body.slice(0, 6000)}${body.length > 6000 ? '\n[… обрезано; используй save_as, чтобы обработать целиком]' : ''}`;
}

async function runPython(user, args, ctx) {
  const cwd = ctx.cwd || workspaceOf(user.id);
  const script = path.join(cwd, `.run_${crypto.randomBytes(3).toString('hex')}.py`);
  fs.writeFileSync(script, String(args.code));
  const snap = new Map(fs.readdirSync(cwd).map((n) => { try { return [n, fs.statSync(path.join(cwd, n)).mtimeMs]; } catch { return [n, 0]; } }));
  const out = await new Promise((resolve) => {
    const p = spawn('python3', [script], { cwd, env: { ...shellEnv(user), MPLBACKEND: 'Agg', PYTHONIOENCODING: 'utf-8' }, detached: true });
    let buf = ''; const push = (d) => { buf += d; if (buf.length > 200000) buf = buf.slice(-100000); ctx.onOutput?.(d.toString()); };
    p.stdout.on('data', push); p.stderr.on('data', push);
    const kill = () => { try { process.kill(-p.pid, 'SIGKILL'); } catch {} };
    const timer = setTimeout(() => { kill(); buf += '\n[таймаут]'; }, Math.min(Math.max(+args.timeout || 60, 1), 300) * 1000);
    ctx.signal?.addEventListener('abort', kill);
    p.on('close', (code) => { clearTimeout(timer); resolve(`${trunc(buf) || '(нет вывода)'}\n[exit ${code}]`); });
    p.on('error', (e) => { clearTimeout(timer); resolve(`Ошибка запуска python3: ${e.message}`); });
  });
  try { fs.unlinkSync(script); } catch {}
  let shown = 0;
  for (const n of fs.readdirSync(cwd)) {
    if (shown >= 4 || !/\.(png|jpe?g|svg|gif|webp)$/i.test(n)) continue;
    const p = path.join(cwd, n); let st; try { st = fs.statSync(p); } catch { continue; }
    if (st.mtimeMs > (snap.get(n) ?? 0) + 1 || !snap.has(n)) { const f = registerFile(user, p); ctx.attach?.({ ...f, caption: n }); shown++; }
  }
  return out + (shown ? `\n[показано изображений: ${shown}]` : '');
}

/** Выполняет инструмент, возвращает строку-результат. ctx: {signal,onOutput,attach(file)} */
const PUB_OK = /опублику|опубликов|задеплой|деплой|выложи|разверни|захост|размести|на домен|publish|deploy|\bhost\b|в интернет|(^|\s)(да|давай|ага|ок|угу)([\s.!,]|$)/i;
const editAlias = (a) => {   // модели называют параметры правок по-разному — приводим к old/new
  if (!a || typeof a !== 'object') return a;
  const fix = (e) => ({ ...e, old: e.old ?? e.old_string ?? e.oldText ?? e.old_text ?? e.find ?? e.search, new: e.new ?? e.new_string ?? e.newText ?? e.new_text ?? e.replace ?? e.replacement });
  return { ...fix(a), ...(Array.isArray(a.edits) ? { edits: a.edits.map(fix) } : {}) };
};
export async function runTool(user, name, args, ctx) {
  try {
    if (name === 'edit_file' || name === 'multi_edit') args = editAlias(args);
    if (name.startsWith('mcp_')) return maskSecrets(user, await mcpCall(user.id, name, injectSecrets(user, args), ctx.signal));
    if (name === 'bash' || name === 'http_request') { args = injectSecrets(user, args); const out = await runTool0(user, name, args, ctx); return maskSecrets(user, out); }
    return await runTool0(user, name, args, ctx);
  } catch (e) { return `Ошибка: ${e.message}`; }
}
async function runTool0(user, name, args, ctx) {
  try {
    switch (name) {
      case 'mail': return await mailTool(user, args, { userText: ctx.userText, autonomy: ctx.autonomy });
      case 'mission_create': return createMission(user, args);
      case 'mission_update': return updateMission(user, args);
      case 'mission_list': return missionsText(user.id);
      case 'data_query': return dataQuery(user, args);
      case 'lookup': return await lookup(String(args.source), String(args.query || ''), args.lang, ctx.signal);
      case 'tasks': return tasksTool(user, args);
      case 'bash': {
        if (user.role !== 'owner') return 'Ошибка: shell недоступен для этого аккаунта.';
        { const r = riskCheck(args, ctx); if (r) return r; }
        if (ctx.automation) args = { ...args, background: false, timeout: Math.min(+args.timeout || 120, 300) };
        return await runBash(user, args, ctx);
      }
      case 'read_file': {
        const p = resolvePath(user, args.path, ctx.cwd);
        let raw;
        if (AUDIO_EXT.test(p)) { ctx.onOutput?.('Расшифровываю аудио…'); const t = await transcribeFile(p); if (!t.text) return `Ошибка: ${t.error || 'речь не распознана'}`; raw = t.text; }
        else if (DOC_EXT.test(p)) { const d = extractText(p, p); if (!d?.text) return `Ошибка: ${d?.error || d?.note || 'не удалось извлечь текст'}`; raw = d.text; } else { const b = fs.readFileSync(p); if (b.subarray(0, 4000).includes(0)) return `Ошибка: бинарный файл неизвестного формата (${path.extname(p) || 'без расширения'}, ${b.length} Б)`; raw = b.toString('utf8'); }
        const lines = raw.split('\n');
        const off = Math.max((args.offset || 1) - 1, 0), lim = args.limit || 250;
        const body = lines.slice(off, off + lim).map((l, i) => `${off + i + 1}\t${l.slice(0, 2000)}`).join('\n');
        return trunc(body, 8000) + (lines.length > off + lim ? `\n[... ещё ${lines.length - off - lim} строк]` : '');
      }
      case 'read_files': {
        const out = []; let used = 0;
        for (const rel of (args.paths || []).slice(0, 12)) {
          try {
            const p = resolvePath(user, rel, ctx.cwd);
            const raw = DOC_EXT.test(p) ? (extractText(p, p)?.text || '') : fs.readFileSync(p, 'utf8');
            const lines = raw.split('\n'); const lim = args.limit || 120;
            let body = lines.slice(0, lim).map((l, i) => `${i + 1}\t${l.slice(0, 600)}`).join('\n') + (lines.length > lim ? `\n[… ещё ${lines.length - lim} строк]` : '');
            if (used + body.length > 12000) body = body.slice(0, Math.max(0, 12000 - used)) + '\n[… лимит вывода]';
            used += body.length; out.push(`===== ${rel} =====\n${body}`);
          } catch (e) { out.push(`===== ${rel} =====\nОшибка: ${e.message}`); }
          if (used >= 12000) break;
        }
        return out.join('\n\n') || 'Нет путей';
      }
      case 'multi_edit': {
        const p = resolvePath(user, args.path, ctx.cwd);
        let src = fs.readFileSync(p, 'utf8'); let applied = 0;
        for (const [i, e] of (args.edits || []).entries()) {
          if (typeof e.old !== 'string' || !e.old) return `Ошибка в правке #${i + 1}: не указан old`;
          const n = src.split(e.old).length - 1;
          if (n === 0) return `Ошибка в правке #${i + 1}: фрагмент не найден — файл НЕ изменён`;
          if (n > 1 && !e.replace_all) return `Ошибка в правке #${i + 1}: фрагмент встречается ${n} раз (уточни или replace_all) — файл НЕ изменён`;
          src = e.replace_all ? src.split(e.old).join(e.new) : src.replace(e.old, () => e.new); applied++;
        }
        fs.writeFileSync(p, src);
        return `Применено правок: ${applied}. Файл сохранён — перечитывать не нужно.`;
      }
      case 'write_file': {
        const p = resolvePath(user, args.path, ctx.cwd);
        fs.mkdirSync(path.dirname(p), { recursive: true });
        fs.writeFileSync(p, args.content ?? '');
        return `Записано ${Buffer.byteLength(args.content ?? '')} байт в ${p}. Перечитывать не нужно.`;
      }
      case 'edit_file': {
        const p = resolvePath(user, args.path, ctx.cwd);
        const src = fs.readFileSync(p, 'utf8');
        if (typeof args.old !== 'string' || !args.old) return 'Ошибка: не указан фрагмент old (что заменить)';
        const n = src.split(args.old).length - 1;
        if (n === 0) return 'Ошибка: фрагмент не найден (проверь точное совпадение, включая пробелы и переносы)';
        if (n > 1 && !args.replace_all) return `Ошибка: фрагмент встречается ${n} раз — уточни или replace_all`;
        fs.writeFileSync(p, args.replace_all ? src.split(args.old).join(args.new) : src.replace(args.old, () => args.new));
        return `Заменено (${args.replace_all ? n : 1}). Файл сохранён — перечитывать не нужно.`;
      }
      case 'list_dir': {
        const p = resolvePath(user, args.path || '.', ctx.cwd);
        return fs.readdirSync(p, { withFileTypes: true }).filter((e) => e.name !== '.oa-snap').slice(0, 500)
          .map((e) => (e.isDirectory() ? e.name + '/' : `${e.name}  (${fs.statSync(path.join(p, e.name)).size} B)`)).join('\n') || '(пусто)';
      }
      case 'web_search':
        const qs = [...new Set([args.query, ...(Array.isArray(args.queries) ? args.queries : [])].filter(Boolean).map(String))].slice(0, 4);
        if (!qs.length) return 'Ошибка: нужен query или queries';
        const opts = { signal: ctx.signal, provider: ctx.searchProvider || 'auto', pplx: pplxUp(user) ? (q, n, sig) => pplxSearch(user, q, n, sig) : null, read: qs.length > 1 ? 1 : args.read ?? 2, category: args.category, days: args.days, domains: Array.isArray(args.domains) ? args.domains : undefined };
        const outs = await Promise.all(qs.map((q) => webSearch(q, opts)));
        return trunc(outs.join('\n---\n'), qs.length > 1 ? 7000 : 4500);
      case 'web_fetch': {
        if (user.role !== 'owner') await assertPublicUrl(args.url);
        const p = await fetchPage(args.url, { signal: ctx.signal, max: Math.min(args.max_chars || 4000, 15000) });
        return p.error ? `Ошибка: ${p.error}` : `# ${p.title}\n${p.url}\n\n${p.text}`;
      }
      case 'grep': {
        const root = resolvePath(user, args.path || '.', ctx.cwd);
        { // быстрый путь: ripgrep (учитывает .gitignore)
          const a = ['-n', '--no-heading', '--max-columns', '220', '-m', '40', '--max-count', '40'];
          if (args.ignore_case) a.push('-i'); if (args.glob) a.push('-g', args.glob); a.push('-e', String(args.pattern), '.');
          const r = spawnSync('rg', a, { cwd: root, encoding: 'utf8', timeout: 15000, maxBuffer: 8e6 });
          if (!r.error && (r.status === 0 || r.status === 1)) { const o = (r.stdout || '').split('\n').slice(0, 200).join('\n').trim(); return o || 'Совпадений нет'; }
        }
        let re; try { re = new RegExp(args.pattern, args.ignore_case ? 'i' : ''); } catch (e) { return `Ошибка регулярки: ${e.message}`; }
        const gre = args.glob ? globRe(args.glob.includes('/') ? args.glob : '**/' + args.glob) : null;
        const hits = [];
        for (const f of walk(root)) {
          const rel = path.relative(root, f);
          if (gre && !gre.test(rel)) continue;
          let txt; try { if (fs.statSync(f).size > 1.5e6) continue; txt = fs.readFileSync(f, 'utf8'); } catch { continue; }
          if (txt.includes('\0')) continue;
          txt.split('\n').forEach((l, i) => { if (hits.length < 200 && re.test(l)) hits.push(`${rel}:${i + 1}:${l.slice(0, 220)}`); });
          if (hits.length >= 200) break;
        }
        return hits.join('\n') || 'Совпадений нет';
      }
      case 'glob': {
        const root = resolvePath(user, args.path || '.', ctx.cwd);
        const re = globRe(args.pattern.includes('/') ? args.pattern : '**/' + args.pattern);
        const r = walk(root).map((f) => path.relative(root, f)).filter((f) => re.test(f)).slice(0, 300);
        return r.join('\n') || 'Файлов не найдено';
      }
      case 'http_request': {
        const doFetch = user.role === 'owner' ? fetch : safeFetch;
        const r = await doFetch(args.url, { method: (args.method || 'GET').toUpperCase(), headers: args.headers || {}, body: ['GET', 'HEAD'].includes((args.method || 'GET').toUpperCase()) ? undefined : args.body, signal: ctx.signal });
        const t = await r.text();
        return `HTTP ${r.status}\n${trunc(t, 6000)}`;
      }
      case 'process': {
        if (user.role !== 'owner') return 'Ошибка: недоступно';
        const mine = [...jobs.values()].filter((j) => j.userId === user.id);
        const alive = (pid) => { try { process.kill(pid, 0); return true; } catch { return false; } };
        if (args.action === 'list') return mine.map((j) => `pid ${j.pid} ${alive(j.pid) ? 'running' : 'finished'} · ${Math.round((Date.now() - j.started) / 1000)}с · ${j.cmd}\n  лог: ${j.log}`).join('\n') || 'Фоновых процессов нет';
        const j = mine.find((x) => x.pid === args.pid);
        if (!j) return 'Процесс не найден';
        if (args.action === 'kill') { try { process.kill(-j.pid, 'SIGKILL'); } catch { try { process.kill(j.pid, 'SIGKILL'); } catch {} } return 'Остановлен'; }
        const lines = fs.readFileSync(j.log, 'utf8').split('\n');
        return `${alive(j.pid) ? '[running]' : '[finished]'}\n` + trunc(lines.slice(-(args.lines || 60)).join('\n'));
      }
      case 'github_api': {
        const u = db.prepare('SELECT github_token FROM users WHERE id=?').get(user.id);
        if (!u?.github_token) return 'GitHub не привязан';
        const m = (args.method || 'GET').toUpperCase();
        const r = await fetch('https://api.github.com' + (args.path.startsWith('/') ? args.path : '/' + args.path), { method: m, signal: ctx.signal,
          headers: { Authorization: `Bearer ${u.github_token}`, Accept: 'application/vnd.github+json', 'User-Agent': 'OpenAgent', 'Content-Type': 'application/json' },
          body: m === 'GET' ? undefined : JSON.stringify(args.body || {}) });
        return `HTTP ${r.status}\n${trunc(await r.text(), 6000)}`;
      }
      case 'chart': return emitImage(user, ctx, chartSvg(args), args.title || 'График');
      case 'plot_function': return emitImage(user, ctx, plotSvg(args), args.title || 'График функции');
      case 'geometry': return emitImage(user, ctx, geometrySvg(args), args.title || 'Чертёж');
      case 'diagram': return emitImage(user, ctx, sanitizeSvg(graphviz(args.dot, args.theme), args.theme), args.title || 'Диаграмма');
      case 'draw_svg': return emitImage(user, ctx, sanitizeSvg(args.svg, args.theme), args.title || 'Рисунок', true);
      case 'calculate': return calculate(args.expression);
      case 'python': {
        if (user.role !== 'owner') return 'Ошибка: недоступно для этого аккаунта';
        return await runPython(user, args, ctx);
      }
      case 'skill_search': {
        const u = db.prepare('SELECT github_token FROM users WHERE id=?').get(user.id);
        const r = await searchRepos(args.query, u?.github_token);
        return r.map((x) => `${x.repo} ★${x.stars} — ${x.description}`).join('\n') || 'Ничего не найдено';
      }
      case 'skill_install': {
        const u = db.prepare('SELECT github_token FROM users WHERE id=?').get(user.id);
        const r = await installFromGithub(user, args.repo, u?.github_token);
        return `Установлено из ${r.repo}: ${r.installed.join(', ') || 'ничего'}${r.skipped.length ? `\nПропущено: ${r.skipped.slice(0, 5).join('; ')}` : ''}${r.note ? '\n' + r.note : ''}`;
      }
      case 'deploy_site': {
        if (!PUB_OK.test(ctx.userText || '') ) return 'ОТКАЗ: пользователь не просил публиковать сайт. Не публикуй. Файлы оставь в папке проекта и предложи опубликовать, если он захочет.';
        const r = deploySite(user, args, ctx.cwd || workspaceOf(user.id));
        return `Опубликовано: ${r.url} (файлов: ${r.files}). Покажи пользователю ссылку.`;
      }
      case 'html_app': {
        const html = String(args.html || '');
        if (html.length < 30) return 'Ошибка: пустой HTML';
        const r = deploySite(user, { name: `app-${crypto.randomBytes(3).toString('hex')}`, title: args.title, files: { 'index.html': html }, kind: 'app' }, ctx.cwd);
        return `Приложение «${args.title || 'app'}» запущено: ${r.url}`;
      }
      case 'list_sites': return listSites(user.id).map((s) => `${s.slug} — ${s.title} · ${s.url}`).join('\n') || 'Сайтов нет';
      case 'delete_site': return deleteSite(user.id, args.name) ? 'Сайт удалён' : 'Не найден';
      case 'todo_write': return 'Список задач обновлён';
      case 'ask_user': ctx.endTurn?.(); return 'Вопрос показан пользователю. Заверши ход и дождись ответа.';
      case 'delegate': return ctx.delegate ? await ctx.delegate(String(args.task || '')) : 'Делегирование недоступно';
      case 'skill_load': {
        const r = db.prepare('SELECT content FROM skills WHERE user_id=? AND name=?').get(user.id, String(args.name));
        return r ? r.content : 'Навык не найден';
      }
      case 'skill_save': {
        db.prepare('INSERT INTO skills(user_id,name,description,content) VALUES (?,?,?,?) ON CONFLICT(user_id,name) DO UPDATE SET description=excluded.description, content=excluded.content')
          .run(user.id, String(args.name).slice(0, 60), String(args.description || '').slice(0, 200), String(args.content).slice(0, 20000));
        return 'Навык сохранён';
      }
      case 'schedule_create': return createSchedule(user, args);
      case 'schedule_list': return listSchedules(user.id).map((s) => `#${s.id} ${s.name} · ${s.every_min ? `каждые ${s.every_min} мин` : 'разово'} · ${s.enabled ? 'вкл' : 'выкл'} · следующий ${s.next_run ? new Date(s.next_run).toISOString() : '—'}`).join('\n') || 'Автоматизаций нет';
      case 'schedule_delete': return deleteSchedule(user.id, +args.id) ? 'Удалено' : 'Не найдено';
      case 'phone': {
        if (!ctx.phone) return 'Управление телефоном недоступно в этом режиме';
        // модели иногда называют параметры по-своему — приводим к нашим
        args = { ...args }; args.to ||= args.contact || args.name || args.recipient || args.person || args.number || args.phone_number; args.text ||= args.message || args.body || args.content;
        args.app ||= args.messenger || args.application || args.package;
        const ACT = { send_message: 'message', send: 'message', whatsapp: 'message', telegram: 'message', click: 'tap', press: 'tap', open: 'open_app', launch: 'open_app', scroll_down: 'scroll', swipe_up: 'scroll', screen_text: 'read_screen', play_music: 'music_play', set_alarm: 'alarm', set_timer: 'timer' };
        if (ACT[args.action]) args.action = ACT[args.action];
        // действия «вовне» (звонок, сообщение, заказ, оплата, отправка) — только с подтверждением пользователя
        const said = String(ctx.userText || '');
        // пользователь уже прямо попросил это действие в последнем сообщении (или ответил «да/давай») — повторно не переспрашиваем
        const explicit = (['call'].includes(args.action) && /позвони|звони|набери|созвон|дозвон/i.test(said)) || (['sms', 'message'].includes(args.action) && /напиши|написать|отправь|отправить|сообщи|скажи (ему|ей|им)|ответь|смс|сообщени|передай/i.test(said)) || (['tap', 'long_press'].includes(args.action) && /вызови|вызывай|закажи|заказ|заказывай|оформи|купи|оплати|поехали|давай|подтверждаю|согласен|отправляй|отправь|(?:^|[\s,.!?])(?:да|ок|окей|ага)(?:$|[\s,.!?])|верно|хорошо|начина|найди водител/i.test(said));
        const outward = ['call', 'sms', 'message'].includes(args.action) || (['tap', 'long_press'].includes(args.action) && /заказать|заказ[уы]? |оплат|купить|оформ|подтверд|найти водител|отправить|send|order|pay|buy|confirm|place/i.test(String(args.text || '')));
        if (outward && ctx.autonomy === 'ask' && !args.confirmed && !explicit) return 'Нужно подтверждение: пользователь прямо этого не просил. Коротко скажи, что собираешься сделать (кому/что/сколько), дождись «да» и повтори вызов с confirmed=true.';
        const r = String(await ctx.phone(args));
        const hr = /^httpresp:(\d+)\n([\s\S]*)$/.exec(r);
        if (hr) return summarizeHttp(user, args, +hr[1], hr[2]);
        const m = /^screenshot:([0-9a-f]+)([\s\S]*)$/.exec(r);
        if (args.action === 'screen' && m) {     // скриншот с телефона → описываем vision-моделью, основной модели отдаём текст
          const row = db.prepare('SELECT path FROM files WHERE id=? AND user_id=?').get(m[1], user.id);
          if (!row || !fs.existsSync(row.path)) return 'Снимок экрана не найден на сервере';
          try {
            const q = String(ctx.userText || '').slice(0, 400);
            const hint = m[2].trim() ? `\nТекст, найденный системой на экране: ${m[2].trim().slice(0, 1500)}` : '';
            return await describeImage(user, row.path, `Это снимок экрана телефона пользователя. Вопрос пользователя: «${q}». Опиши коротко и по делу, что на экране (приложение, главное содержимое, важный текст, кнопки/действия) и ответь на вопрос. По-русски, без вступлений.${hint}`, ctx.signal);
          } catch (e) { return m[2].trim() ? `Vision недоступен (${e.message}). Текст на экране:\n${m[2].trim().slice(0, 2000)}` : `Не удалось разобрать снимок: ${e.message}`; }
        }
        if (r.startsWith('text:')) return 'Снимка нет, но система передала текст экрана:\n' + r.slice(5).slice(0, 3000);
        return r.slice(0, 3000);
      }
      case 'generate_image': {
        if (!imageEnabled()) return 'Ошибка: генерация изображений не настроена на сервере';
        const r = await generateImage(args, path.join(workspaceOf(user.id), 'images'), ctx.signal);
        const f = registerFile(user, r.file);
        ctx.attach?.({ ...f, caption: String(args.prompt || '').slice(0, 120) });
        return `Изображение создано (${r.model}) и отправлено пользователю. Кратко опиши, что получилось, и предложи доработки.`;
      }
      case 'create_file': {
        const p = resolvePath(user, args.path, ctx.cwd);
        const ext = path.extname(p).toLowerCase().slice(1);
        fs.mkdirSync(path.dirname(p), { recursive: true });
        const content = String(args.content ?? '');
        if (['docx', 'pdf', 'pptx', 'xlsx'].includes(ext)) {
          const r = _spawnSync('python3', [DOCS_PY, 'create', ext, p], { input: content, encoding: 'utf8', timeout: 90000 });
          if (r.error || r.status !== 0) return 'Ошибка создания ' + ext + ': ' + String(r.stderr || r.error?.message || '').split('\n').filter(Boolean).slice(-2).join(' ').slice(0, 400) + (/No module/.test(r.stderr || '') ? ' (на сервере: pip3 install --break-system-packages python-docx openpyxl python-pptx reportlab)' : '');
        } else fs.writeFileSync(p, content);
        const f = registerFile(user, p);
        ctx.attach?.({ ...f, caption: '' });
        return `Файл ${f.name} создан (${f.size} Б) и отправлен пользователю.`;
      }
      case 'edit_document': {
        const p = resolvePath(user, args.path, ctx.cwd);
        if (!fs.existsSync(p)) return 'Ошибка: файл не найден';
        const bak = p.replace(/(\.[^.]+)$/, '.orig$1'); if (!fs.existsSync(bak)) fs.copyFileSync(p, bak);   // копия оригинала
        const r = _spawnSync('python3', [DOCS_PY, 'edit', p], { input: JSON.stringify(args.ops || []), encoding: 'utf8', timeout: 90000 });
        if (r.error || r.status !== 0) return 'Ошибка правки: ' + String(r.stderr || r.error?.message || '').split('\n').filter(Boolean).slice(-2).join(' ').slice(0, 400);
        const f = registerFile(user, p);
        ctx.attach?.({ ...f, caption: '' });
        return `Готово: ${String(r.stdout).trim().slice(0, 500)}. Обновлённый файл отправлен пользователю (оригинал сохранён как ${path.basename(bak)}).`;
      }
      case 'send_file': {
        const p = resolvePath(user, args.path, ctx.cwd);
        if (!fs.existsSync(p) || !fs.statSync(p).isFile()) return 'Ошибка: файл не найден';
        const f = registerFile(user, p);
        ctx.attach?.({ ...f, caption: args.caption || '' });
        return `Файл ${f.name} (${f.size} Б) отправлен пользователю`;
      }
      case 'memory_save': {
        const id = await saveMemory(user.id, args);
        return id ? `Сохранено (id ${id})` : 'Пустое содержимое';
      }
      case 'memory_search': {
        const r = await searchMemories(user.id, args.query, 10);
        return r.length ? r.map((m) => `#${m.id} [${m.kind}] ${m.content}`).join('\n') : 'Ничего не найдено';
      }
      case 'memory_forget':
        return forgetMemory(user.id, args.id) ? 'Удалено' : 'Не найдено';
      default:
        return `Неизвестный инструмент: ${name}`;
    }
  } catch (e) {
    return `Ошибка: ${e.message}`;
  }
}
