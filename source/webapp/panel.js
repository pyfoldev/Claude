"use strict";
// Веб-панель. Весь вывод строится через createElement/textContent — данные никогда не попадают в разметку как HTML.
const tg = window.Telegram && window.Telegram.WebApp;
if (tg) {
  try { tg.ready(); tg.expand(); tg.setHeaderColor("#0b1020"); tg.setBackgroundColor("#0b1020"); if (tg.setBottomBarColor) tg.setBottomBarColor("#0b1020"); if (tg.disableVerticalSwipes) tg.disableVerticalSwipes(); } catch (e) { /* старый клиент */ }
}
const initData = tg ? tg.initData : "";
if (typeof LANG !== "undefined" && LANG === "en") {            // статичные подписи страницы
  document.documentElement.lang = "en"; document.title = tr(document.title);
  for (const [id, a] of [["chat", "aria-label"], ["tabs", "aria-label"]]) { const e = document.getElementById(id); if (e) e.setAttribute(a, tr(e.getAttribute(a) || "")); }
  const t = document.getElementById("chatTitle"); if (t) t.textContent = tr(t.textContent);
}
const $ = (id) => document.getElementById(id);
const state = { me: null, chat: null, tab: null, more: false, statsHours: 168, reportsAll: false, openReports: 0 };

// ---------- построение DOM ----------
function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v === true) n.setAttribute(k, "");
    else if (v !== false && v != null) n.setAttribute(k, (k === "aria-label" || k === "placeholder" || k === "title") ? tr(String(v)) : v);
  }
  for (const kid of kids.flat(2)) if (kid != null && kid !== false) n.append(kid.nodeType ? kid : document.createTextNode(tr(String(kid))));
  return n;
}
const NS = "http://www.w3.org/2000/svg";
function icon(name, size) {
  const svg = document.createElementNS(NS, "svg");
  const s = String(size || 20);
  for (const [k, v] of Object.entries({ width: s, height: s, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", focusable: "false" })) svg.setAttribute(k, v);
  for (const [tag, attrs] of (window.ICONS[name] || window.ICONS.info)) {
    const part = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) part.setAttribute(k, v);
    svg.append(part);
  }
  return svg;
}
const haptic = (kind) => { try { if (!tg || !tg.HapticFeedback) return; if (kind === "ok" || kind === "error") tg.HapticFeedback.notificationOccurred(kind === "ok" ? "success" : "error"); else if (kind === "select") tg.HapticFeedback.selectionChanged(); else tg.HapticFeedback.impactOccurred("light"); } catch (e) { /* без вибро */ } };
function toast(msg, err) {
  const t = $("toast"); t.replaceChildren(icon(err ? "circle-alert" : "circle-check", 18), el("span", null, msg));
  t.className = "show" + (err ? " err" : ""); haptic(err ? "error" : "ok");
  clearTimeout(toast.h); toast.h = setTimeout(() => (t.className = ""), 2800);
}

// ---------- сеть ----------
async function api(method, path, body, raw) {
  const r = await fetch("/panel/api" + path, {
    method, headers: Object.assign({ "X-Init-Data": initData, "X-Lang": LANG }, body !== undefined ? { "Content-Type": "application/json" } : {}),
    body: body !== undefined ? JSON.stringify(body) : undefined });
  if (raw && r.ok) return r;
  let data = null; try { data = await r.json(); } catch (e) { /* пустой ответ */ }
  if (r.status === 401) throw new Error(tr("Сессия устарела — закройте и откройте панель заново."));
  if (!r.ok) throw new Error(tr((data && data.error) || "Ошибка " + r.status));
  return data;
}
async function act(fn, okMsg) {
  try { const r = await fn(); if (okMsg) toast(okMsg); return r === undefined ? true : r; } catch (e) { toast(e.message, true); return undefined; }
}

// ---------- форматирование ----------
const fmtTime = (ts) => new Date(ts * 1000).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const fmtDate = (ts) => new Date(ts * 1000).toLocaleString("ru-RU", { day: "numeric", month: "short" });
const fmtDur = (s) => !s ? "" : s % 86400 === 0 ? ` на ${s / 86400} дн.` : s % 3600 === 0 ? ` на ${s / 3600} ч.` : ` на ${Math.max(Math.round(s / 60), 1)} мин.`;
const fmtNum = (n) => Number(n).toLocaleString("ru-RU");
const cleanTitle = (t) => t.replace(/^[^\p{L}\p{N}]+/u, "");
const cid = () => state.chat.id;
const base = () => `/chats/${cid()}`;
const rankIs = (n) => !!state.chat && state.chat.rank >= n;
const RANK_NAME = { 1: "модератор", 2: "модератор", 3: "админ", 4: "старший админ", 5: "создатель" };

// ---------- компоненты ----------
function screen(title, lead) { return [el("h1", null, title), lead ? el("p", { class: "lead" }, lead) : null]; }
function group(title, hint, ...rows) {
  return groupI(title, null, hint, ...rows);
}
function groupI(title, ico, hint, ...rows) {
  const g = el("section", null, title ? el("div", { class: "gh" }, ico ? icon(ico, 16) : null, el("h2", null, title)) : null, el("div", { class: "group" }, rows), hint ? el("p", { class: "foot" }, hint) : null);
  return g;
}
function row(opts, ...extra) {
  const { ico, tone, title, sub, value, onclick, chevron, stack } = opts;
  const body = [ico ? el("span", { class: "ico " + (tone || "") }, icon(ico, 18)) : null,
    el("span", { class: "grow" }, el("span", { class: "t" }, title), sub ? el("span", { class: "s" }, sub) : null),
    value != null ? el("span", { class: "v" }, value) : null, extra, chevron ? el("span", { class: "chev" }, icon("chevron-right", 18)) : null];
  return onclick ? el("button", { class: "row", onclick }, body) : el("div", { class: "row" + (stack ? " stack" : "") }, body);
}
function toggle(on, onChange, label) {
  const b = el("button", { class: "switch", role: "switch", "aria-checked": String(!!on), "aria-label": label || "Переключатель", onclick: () => { const v = b.getAttribute("aria-checked") !== "true"; haptic("select"); onChange(v ? 1 : 0, b); } });
  return b;
}
function segmented(options, current, onPick, label) {
  const wrap = el("div", { class: "seg", role: "group", "aria-label": label || "Выбор" });
  for (const [text, value] of options) wrap.append(el("button", { "aria-pressed": String(String(value) === String(current)), onclick: () => { if (String(value) !== String(current)) { haptic("select"); onPick(value); } } }, text));
  return wrap;
}
function btn(label, onclick, opts) {
  const { cls, ico } = opts || {};
  return el("button", { class: "btn " + (cls || ""), onclick }, ico ? icon(ico, 18) : null, label);
}
function dangerBtn(label, onConfirm, ico) {  // двухшаговое подтверждение вместо модалки
  let armed = false, timer;
  const b = el("button", { class: "btn danger", onclick: () => {
    if (!armed) { armed = true; b.classList.add("armed"); b.replaceChildren(icon("circle-alert", 18), "Точно? Нажмите ещё раз"); haptic("select"); timer = setTimeout(reset, 3200); return; }
    clearTimeout(timer); reset(); onConfirm();
  } }, ico ? icon(ico, 18) : null, label);
  function reset() { armed = false; b.classList.remove("armed"); b.replaceChildren(ico ? icon(ico, 18) : "", label); }
  return b;
}
function empty(ico, title, text) { return el("div", { class: "empty" }, icon(ico, 44), el("b", null, title), text ? el("p", null, text) : null); }
const skeletons = (n) => el("div", { class: "group" }, Array.from({ length: n }, () => el("div", { class: "skeleton" })));
function field(attrs) { return el("input", Object.assign({ class: "field", autocomplete: "off", autocapitalize: "off", spellcheck: "false" }, attrs)); }
function select(options, value, onChange, mini) {
  const s = el("select", { class: "field" + (mini ? " mini" : ""), onchange: () => onChange(s.value) }, options.map(([t, v]) => el("option", { value: v }, t)));
  s.value = String(value); return s;
}

// ---------- разделы ----------
const SECTIONS = {
  settings: { title: "Настройки", ico: "settings", need: 4, fn: viewSettings, sub: "Капча, антиспам, 18+, ИИ и другое" },
  reports: { title: "Жалобы", ico: "flag", need: 1, fn: viewReports, sub: "Очередь жалоб участников и ИИ" },
  history: { title: "История", ico: "history", need: 1, fn: viewHistory, sub: "Наказания участника" },
  stats: { title: "Статистика", ico: "chart-column", need: 1, fn: viewStats, sub: "Активность и самые активные" },
  filters: { title: "Стоп-слова", ico: "list-filter", need: 3, fn: viewFilters, sub: "Слова и выражения, которые удаляются" },
  links: { title: "Ссылки", ico: "link", need: 3, fn: viewLinks, sub: "Белый список доменов" },
  log: { title: "Журнал", ico: "scroll-text", need: 4, fn: viewLog, sub: "Копия действий в отдельный чат или канал" },
  ranks: { title: "Ранги", ico: "shield-check", need: 1, fn: viewRanks, sub: "Модераторы и доступ команд" },
  texts: { title: "Тексты", ico: "file-text", need: 4, fn: viewTexts, sub: "Правила и приветствие" },
  owner: { title: "Владелец", ico: "crown", need: 0, fn: viewOwner, sub: "Бот целиком: функции, чаты, пользователи", owner: true },
};
const PRIMARY = ["settings", "reports", "history", "stats"];

function available() {
  return Object.entries(SECTIONS).filter(([, s]) => s.owner ? state.me.is_owner : rankIs(s.need)).map(([id]) => id);
}
function layout() {
  const av = available();
  if (av.length <= 5) return { tabs: av, rest: [] };
  const tabs = PRIMARY.filter((id) => av.includes(id));
  return { tabs, rest: av.filter((id) => !tabs.includes(id)) };
}
function go(id, more) { state.tab = id; state.more = !!more; render(); }

function renderTabs() {
  const { tabs, rest } = layout();
  const nav = $("tabs"); nav.replaceChildren();
  const mk = (id, ico, title, selected, handler, badge) => el("button", { class: "tab", role: "tab", "aria-selected": String(selected), onclick: handler }, icon(ico, 24), title, badge ? el("span", { class: "badge" }, badge > 9 ? "9+" : badge) : null);
  for (const id of tabs) nav.append(mk(id, SECTIONS[id].ico, SECTIONS[id].title, state.tab === id && !state.more, () => go(id, false), id === "reports" ? state.openReports : 0));
  if (rest.length) nav.append(mk("more", "ellipsis", "Ещё", state.tab === "more" || state.more, () => go("more", false)));
  syncBack();
}
function syncBack() {
  if (!tg || !tg.BackButton) return;
  const sub = state.more && state.tab !== "more";
  try { sub ? tg.BackButton.show() : tg.BackButton.hide(); } catch (e) { /* нет кнопки */ }
}
if (tg && tg.BackButton) tg.BackButton.onClick(() => { if (state.more) go("more", false); });

let renderToken = 0;
async function render(keepScroll) {
  const token = ++renderToken, y = keepScroll ? window.scrollY : 0;
  const { tabs, rest } = layout();
  const all = [...tabs, ...rest];
  const view = $("view");
  if (!all.length) { renderTabs(); view.replaceChildren(...screen("Нет доступа"), empty("lock", "Нужен ранг модератора", "У вас нет прав в выбранном чате. Выберите другой чат сверху.")); return; }
  if (state.tab !== "more" && !all.includes(state.tab)) { state.tab = tabs[0] || "more"; state.more = false; }
  if (state.tab === "more" && !rest.length) { state.tab = tabs[0]; }
  renderTabs();
  if (!keepScroll) view.replaceChildren(skeletons(5));
  try {
    const content = state.tab === "more" ? viewMore(rest) : await SECTIONS[state.tab].fn();
    if (token !== renderToken) return;
    view.replaceChildren(...[content].flat().filter(Boolean));
    view.classList.remove("enter"); void view.offsetWidth; if (!keepScroll) view.classList.add("enter");
    window.scrollTo(0, y);
  } catch (e) {
    if (token !== renderToken) return;
    view.replaceChildren(empty("circle-alert", "Не получилось загрузить", e.message), el("div", { class: "actions" }, btn("Повторить", () => render(), { ico: "refresh-cw" })));
  }
  syncBack();
}
const refresh = () => render(true);

function viewMore(rest) {
  return [...screen("Ещё"), group(null, null, ...rest.map((id) => row({ ico: SECTIONS[id].ico, title: SECTIONS[id].title, sub: SECTIONS[id].sub, chevron: true, onclick: () => go(id, true) })))];
}

// ---------- настройки ----------
const PAGE_ICON = { captcha: "shield-check", spam: "ban", filters: "list-filter", raid: "siren", nsfw: "eye-off", voice: "mic", aimod: "shield-alert", ai: "bot", games: "gamepad-2", warns: "triangle-alert", report: "flag" };
async function viewSettings() {
  const d = await api("GET", base() + "/settings"), vals = d.values, root = el("div", { class: "stackcol" });
  const set = (key, v) => act(async () => { await api("POST", base() + "/settings", { key, value: v }); vals[key] = v; draw(); }, "Сохранено");
  const draw = () => root.replaceChildren(...d.pages.map((p) => {
    const m = /^(.*?)\s*\((.+)\)\s*$/.exec(cleanTitle(p.title)), name = m ? m[1] : cleanTitle(p.title);
    return groupI(name, PAGE_ICON[p.id], m ? m[2][0].toUpperCase() + m[2].slice(1) : null, ...p.rows.map((r) => r.type === "toggle"
      ? row({ title: r.label }, toggle(vals[r.key], (v) => set(r.key, v), r.label))
      : row({ title: r.label, stack: true }, segmented(r.values, vals[r.key], (v) => set(r.key, v), r.label))));
  }));
  draw();
  return [...screen("Настройки", "Изменения применяются сразу."), root];
}

// ---------- стоп-слова ----------
async function viewFilters() {
  const d = await api("GET", base() + "/filters");
  let kind = "word"; const text = field({ placeholder: "слово, фраза или выражение", maxlength: "200" });
  const kindSeg = el("div"); const drawKind = () => kindSeg.replaceChildren(segmented([["Слово или фраза", "word"], ["Регулярное выражение", "regex"]], kind, (v) => { kind = v; drawKind(); }, "Тип"));
  drawKind();
  const add = async () => { if (await act(() => api("POST", base() + "/filters", { kind, pattern: text.value }), "Фильтр добавлен")) refresh(); };
  text.addEventListener("keydown", (e) => { if (e.key === "Enter") add(); });
  return [...screen("Стоп-слова", "Сообщения с этими словами удаляются. Админов и модераторов фильтры не трогают."),
    group("Новый фильтр", "Выражения: до 200 символов, без просмотров и вложенных повторов. Действие при срабатывании — в настройках, раздел «Стоп-слова».",
      row({ stack: true, title: "" }, kindSeg), row({ stack: true, title: "" }, el("div", { class: "compose" }, text, btn("Добавить", add, { cls: "primary", ico: "plus" })))),
    d.filters.length ? group(`Фильтры · ${d.filters.length} из ${d.limit}`, null, ...d.filters.map((f) => row({ title: f.pattern }, el("span", { class: "chip" }, f.kind === "word" ? "слово" : "regexp"),
      el("button", { class: "icon-btn danger", "aria-label": "Удалить фильтр " + f.pattern, onclick: async () => { if (await act(() => api("DELETE", `${base()}/filters/${f.id}`), "Фильтр удалён")) refresh(); } }, icon("trash-2", 20)))))
      : empty("list-filter", "Фильтров пока нет", "Добавьте слово выше — оно начнёт удаляться во всех сообщениях участников.")];
}

// ---------- ссылки ----------
async function viewLinks() {
  const d = await api("GET", base() + "/links"), input = field({ placeholder: "example.com или *.example.com", inputmode: "url" });
  const add = async () => { if (await act(() => api("POST", base() + "/links", { domain: input.value }), "Домен добавлен")) refresh(); };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") add(); });
  const mode = { off: "Ссылки разрешены всем", newbies: "Ссылки запрещены новичкам", all: "Ссылки запрещены всем" }[d.mode];
  return [...screen("Ссылки", "Домены из этого списка разрешены всегда, даже если ссылки запрещены."),
    group(null, "Режим меняется в настройках, раздел «Антиспам». Работает при включённом антиспаме.", row({ ico: "info", title: mode })),
    group("Добавить домен", "«*.домен» разрешает и поддомены.", row({ stack: true, title: "" }, el("div", { class: "compose" }, input, btn("Добавить", add, { cls: "primary", ico: "plus" })))),
    d.links.length ? group(`Разрешённые · ${d.links.length}`, null, ...d.links.map((l) => row({ title: l }, el("button", { class: "icon-btn danger", "aria-label": "Убрать " + l, onclick: async () => { if (await act(() => api("POST", base() + "/links/remove", { domain: l }), "Домен убран")) refresh(); } }, icon("trash-2", 20)))))
      : empty("link", "Список пуст", "Добавьте домены, ссылки на которые нужно разрешать.")];
}

// ---------- журнал ----------
async function viewLog() {
  const d = await api("GET", base() + "/log"), input = field({ placeholder: "-1001234567890", inputmode: "numeric" });
  const connect = async () => { const n = Number(input.value.trim()); if (!Number.isInteger(n) || n === 0) { toast("Нужен числовой id чата или канала", true); return; } if (await act(() => api("POST", base() + "/log", { chat_id: n }), "Журнал подключён")) refresh(); };
  return [...screen("Журнал", "Копия действий модерации, смены настроек и рангов в отдельный чат или канал."),
    group(null, null, row({ ico: d.log_chat_id ? "circle-check" : "info", tone: d.log_chat_id ? "ok" : "", title: d.log_chat_id ? "Подключён" : "Не подключён", sub: d.log_chat_id ? "Чат или канал " + d.log_chat_id : "Действия сейчас нигде не дублируются" })),
    group("Подключить", "Вы должны быть админом того чата или канала, а бот — уметь туда писать: он отправит пробное сообщение.",
      row({ stack: true, title: "" }, el("div", { class: "compose" }, input, btn("Подключить", connect, { cls: "primary" })))),
    d.log_chat_id ? el("div", { class: "actions" }, dangerBtn("Отключить журнал", async () => { if (await act(() => api("POST", base() + "/log", { chat_id: 0 }), "Журнал отключён")) refresh(); }, "x")) : null];
}

// ---------- ранги и доступ команд ----------
async function viewRanks() {
  const d = await api("GET", base() + "/ranks"), canEdit = rankIs(4);
  const rankOpts = (max) => Array.from({ length: max }, (_, i) => [`Ранг ${i + 1}`, i + 1]);
  const setRank = async (user_id, rank, okMsg) => { if (await act(() => api("POST", base() + "/ranks", { user_id, rank }), okMsg)) refresh(); };
  const uid = field({ placeholder: "id пользователя", inputmode: "numeric" }); let newRank = 1;
  const parts = [...screen("Ранги", `Ваш ранг: ${d.my_rank} (${RANK_NAME[d.my_rank] || "—"}). Админы Telegram получают ранг 3, создатель — 5.`)];
  parts.push(d.ranks.length ? group("Модераторы", null, ...d.ranks.map((r) => row({ title: r.name, sub: "id " + r.user_id },
    canEdit ? select(rankOpts(4), r.rank, (v) => setRank(r.user_id, Number(v), "Ранг изменён"), true) : el("span", { class: "chip" }, "ранг " + r.rank),
    canEdit ? el("button", { class: "icon-btn danger", "aria-label": "Снять ранг у " + r.name, onclick: () => setRank(r.user_id, 0, "Ранг снят") }, icon("trash-2", 20)) : null)))
    : group("Модераторы", null, empty("shield-check", "Пока никого", "Админы Telegram считаются модераторами автоматически.")));
  if (canEdit) {
    parts.push(group("Назначить модератора", "Выдать можно ранг ниже вашего, но не выше 4.", row({ stack: true, title: "" }, uid, select(rankOpts(4), 1, (v) => (newRank = Number(v))),
      btn("Назначить", () => { const n = Number(uid.value.trim()); if (!Number.isInteger(n)) { toast("Нужен числовой id", true); return; } setRank(n, newRank, "Модератор назначен"); }, { cls: "primary", ico: "plus" }))));
    parts.push(group("Доступ команд", "Минимальный ранг для каждой команды. Открыть команду всем нельзя — это небезопасно.", ...d.access.map((a) => row({ title: a.command }, a.changed ? el("span", { class: "chip accent" }, "изменено") : null,
      select([1, 2, 3, 4, 5].map((n) => [`Ранг ${n}`, n]), a.need, async (v) => { if (await act(() => api("POST", base() + "/access", { command: a.command, rank: Number(v) }), "Сохранено")) refresh(); }, true)))));
    parts.push(el("div", { class: "actions" }, dangerBtn("Сбросить доступ к умолчанию", async () => { if (await act(() => api("POST", base() + "/access/reset", {}), "Доступ сброшен")) refresh(); }, "rotate-ccw")));
  }
  return parts;
}

// ---------- тексты ----------
async function viewTexts() {
  const d = await api("GET", base() + "/texts");
  const block = (key, title, hint) => {
    const ta = el("textarea", { class: "field", maxlength: "2000", placeholder: "Пока пусто" }); ta.value = d.texts[key];
    const count = el("span", { class: "s" }), upd = () => (count.textContent = `${ta.value.length} / 2000`);
    ta.addEventListener("input", upd); upd();
    return group(title, hint, row({ stack: true, title: "" }, ta, el("div", { class: "compose" }, el("span", { class: "grow v" }, count), btn("Сохранить", () => act(() => api("POST", base() + "/texts", { key, text: ta.value }), "Сохранено"), { cls: "primary" }))));
  };
  return [...screen("Тексты"), block("rules", "Правила", "Показываются по команде «правила»."), block("welcome", "Приветствие", "{name} заменяется на имя вошедшего.")];
}

// ---------- жалобы ----------
const REPORT_STATUS = { open: ["открыта", "bad"], deleted: ["сообщение удалено", "ok"], muted: ["мут", "ok"], banned: ["бан", "ok"], dismissed: ["отклонена", ""] };
async function viewReports() {
  const d = await api("GET", base() + "/reports");
  state.openReports = d.reports.filter((r) => r.status === "open").length; renderTabs();
  const go1 = (id, action, msg) => async () => { if (await act(() => api("POST", `${base()}/reports/${id}`, { action }), msg)) refresh(); };
  const items = state.reportsAll ? d.reports : d.reports.filter((r) => r.status === "open");
  const filter = segmented([[`Открытые · ${state.openReports}`, 0], ["Все", 1]], state.reportsAll ? 1 : 0, (v) => { state.reportsAll = !!v; refresh(); }, "Фильтр жалоб");
  const cards = items.map((r) => {
    const [stText, stTone] = REPORT_STATUS[r.status] || [r.status, ""];
    return group(null, null,
      row({ ico: "flag", tone: r.status === "open" ? "bad" : "", title: `Жалоба №${r.id}`, sub: fmtTime(r.ts) }, el("span", { class: "chip " + stTone }, stText)),
      row({ stack: true, title: "" }, el("div", null, el("span", { class: "s" }, "От " + r.reporter.name + " на"), el("div", { class: "t" }, el("b", null, r.target.name))),
        r.reason ? el("div", { class: "t" }, "Причина: ", r.reason) : null, r.text ? el("p", { class: "quote" }, r.text) : null,
        r.status === "open" ? el("div", { class: "actions" },
          r.message_id ? btn("Удалить", go1(r.id, "del", "Сообщение удалено"), { ico: "trash-2" }) : null,
          btn("Мут 1 ч", go1(r.id, "mute", "Мут выдан"), { ico: "lock" }),
          dangerBtn("Бан", go1(r.id, "ban", "Бан выдан"), "ban"),
          btn("Отклонить", go1(r.id, "dismiss", "Жалоба отклонена"), { ico: "x" })) : null));
  });
  return [...screen("Жалобы"), filter, ...(cards.length ? cards : [group(null, null, empty("inbox", state.reportsAll ? "Жалоб не было" : "Очередь пуста", "Когда участник пожалуется или ИИ найдёт нарушение, карточка появится здесь."))])];
}

// ---------- история ----------
const ACTION_ICON = { "бан": "ban", "мут": "lock", "кик": "log-out", "варн": "triangle-alert", "снять варн": "rotate-ccw", "разбан": "rotate-ccw", "размут": "rotate-ccw", "удаление": "trash-2", "ранг": "shield-check", "жалоба": "flag", "ошибка ИИ": "circle-alert" };
function viewHistory() {
  const q = field({ placeholder: "@ник или id участника" }), out = el("div", { class: "stackcol" });
  const load = async (page) => {
    const d = await act(() => api("GET", `${base()}/history?user=${encodeURIComponent(q.value.trim())}&page=${page}`)); if (!d || d === true) return;
    const chips = [];
    if (d.warns) chips.push(el("span", { class: "chip bad" }, "варнов: " + d.warns));
    for (const k of ["ban", "mute"]) if (k in d.active) chips.push(el("span", { class: "chip bad" }, (k === "ban" ? "бан " : "мут ") + (d.active[k] ? "до " + fmtTime(d.active[k]) : "бессрочно")));
    if (d.reports.total) chips.push(el("span", { class: "chip" }, `жалоб: ${d.reports.total}${d.reports.open ? " (открытых " + d.reports.open + ")" : ""}`));
    out.replaceChildren(
      group(null, null, el("div", { class: "row" }, el("span", { class: "avatar" }, (d.user.name || "?").slice(0, 1).toUpperCase()), el("span", { class: "grow" }, el("span", { class: "t" }, el("b", null, d.user.name)), el("span", { class: "s" }, "id " + d.user.id)), chips.length ? null : el("span", { class: "chip ok" }, "чисто")),
        chips.length ? el("div", { class: "row" }, el("div", { class: "actions" }, chips)) : null),
      d.items.length ? group(`Записи · ${d.total}`, null, ...d.items.map((i) => row({ ico: ACTION_ICON[i.action] || "info", title: i.action + fmtDur(i.duration), sub: [i.reason, `${i.actor.name} · ${fmtTime(i.ts)}`].filter(Boolean).join(" — ") })))
        : group(null, null, empty("circle-check", "В журнале чисто", "У этого участника не было наказаний.")),
      d.pages > 1 ? el("div", { class: "actions" }, btn("Назад", () => load(d.page - 1), { ico: "chevron-left" }), el("span", { class: "v" }, `${d.page + 1} / ${d.pages}`), btn("Дальше", () => load(d.page + 1), { ico: "chevron-right" })) : null);
    if (d.page === 0) out.scrollIntoView({ block: "nearest" });
  };
  q.addEventListener("keydown", (e) => { if (e.key === "Enter") load(0); });
  return [...screen("История", "Все наказания участника: когда, кто, на какой срок и за что."), group(null, null, row({ stack: true, title: "" }, el("div", { class: "compose" }, q, el("button", { class: "btn primary", "aria-label": "Найти", onclick: () => load(0) }, icon("search", 20))))), out];
}

// ---------- статистика ----------
function barsSimple(values, labels, ariaLabel) {
  const W = 320, H = 90, svg = document.createElementNS(NS, "svg"), max = Math.max(1, ...values), w = W / values.length;
  svg.setAttribute("viewBox", `0 0 ${W} ${H + 16}`); svg.setAttribute("class", "chart"); svg.setAttribute("preserveAspectRatio", "none"); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", tr(ariaLabel));
  values.forEach((n, i) => {
    const h = n ? Math.max((n / max) * H, 2) : 0, r = document.createElementNS(NS, "rect");
    r.setAttribute("class", "bar-r"); r.setAttribute("x", String(i * w + w * 0.14)); r.setAttribute("y", String(H - h)); r.setAttribute("width", String(w * 0.72)); r.setAttribute("height", String(h)); r.setAttribute("rx", "1.5");
    const t = document.createElementNS(NS, "title"); t.textContent = labels[i] + ": " + n; r.append(t); svg.append(r);
  });
  const lab = (x, text, anchor) => { const t = document.createElementNS(NS, "text"); t.setAttribute("x", String(x)); t.setAttribute("y", String(H + 12)); t.setAttribute("text-anchor", anchor); t.textContent = text; svg.append(t); };
  lab(0, labels[0], "start"); lab(W, labels[labels.length - 1], "end");
  return svg;
}
async function viewStats() {
  const hours = state.statsHours, d = await api("GET", `${base()}/stats?hours=${hours}`);
  const c = await api("GET", `${base()}/charts`).catch(() => null);
  const wd = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"], hh = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0") + ":00");
  const joinSeries = c ? c.joins.map(([ts, n]) => [ts, n]) : [];
  const extra = c ? [
    group("Когда пишут", "Сообщения по часам суток за 30 дней", el("div", { class: "row" }, barsSimple(c.by_hour, hh, "Сообщения по часам суток"))),
    group("По дням недели", null, el("div", { class: "row" }, barsSimple(c.by_weekday, wd, "Сообщения по дням недели"))),
    group("Новые участники", `Сейчас в чате: ${fmtNum(c.members)}`, el("div", { class: "row" }, chart(joinSeries, "day"))),
  ] : [];
  const periods = [["24 ч", 24], ["7 дн", 168], ["30 дн", 720], ["90 дн", 2160]];
  const label = periods.find((p) => p[1] === hours)[0];
  const max = Math.max(1, ...d.top.map((t) => t.n));
  return [...screen("Статистика", `${fmtNum(d.total)} сообщений за ${label.replace(" ч", " часа").replace(" дн", " дней")}`),
    segmented(periods, hours, (v) => { state.statsHours = v; render(); }, "Период"),
    group("Сообщения", null, el("div", { class: "row" }, chart(d.series, d.bucket))),
    ...extra,
    group("Самые активные", null, ...(d.top.length ? d.top.map((t, i) => { const r = row({ title: `${i + 1}. ${t.name}`, value: fmtNum(t.n) }); r.classList.add("rank"); const f = el("span", { class: "fill" }); f.style.setProperty("--w", Math.round(t.n / max * 100) + "%"); r.prepend(f); return r; }) : [empty("chart-column", "Данных пока нет", "Статистика копится по мере того, как участники пишут.")]))];
}
function chart(series, bucket) {
  const W = 320, H = 110, svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H + 16}`); svg.setAttribute("class", "chart"); svg.setAttribute("preserveAspectRatio", "none"); svg.setAttribute("role", "img");
  if (!series.length) { svg.setAttribute("aria-label", tr("Нет данных")); return svg; }
  const max = Math.max(...series.map((s) => s[1])), w = W / series.length;
  svg.setAttribute("aria-label", tr(`График сообщений, максимум ${max} за ${bucket === "hour" ? "час" : "день"}`));
  for (const f of [0.5, 1]) { const l = document.createElementNS(NS, "line"); l.setAttribute("x1", "0"); l.setAttribute("x2", String(W)); const y = String(H - f * H + 0.5); l.setAttribute("y1", y); l.setAttribute("y2", y); svg.append(l); }
  series.forEach(([ts, n], i) => {
    const h = n ? Math.max((n / max) * H, 2) : 0, r = document.createElementNS(NS, "rect");
    r.setAttribute("class", "bar-r"); r.setAttribute("x", String(i * w + w * 0.14)); r.setAttribute("y", String(H - h)); r.setAttribute("width", String(w * 0.72)); r.setAttribute("height", String(h)); r.setAttribute("rx", "1.5");
    const t = document.createElementNS(NS, "title"); t.textContent = fmtTime(ts) + ": " + n; r.append(t); svg.append(r);
  });
  const lab = (x, text, anchor) => { const t = document.createElementNS(NS, "text"); t.setAttribute("x", String(x)); t.setAttribute("y", String(H + 12)); t.setAttribute("text-anchor", anchor); t.textContent = text; svg.append(t); };
  lab(0, fmtDate(series[0][0]), "start"); lab(W, "пик " + fmtNum(max), "end");
  return svg;
}

// ---------- владелец ----------
async function viewOwner() {
  const [st, chats, bans, flags] = await Promise.all([api("GET", "/owner/status"), api("GET", "/owner/chats"), api("GET", "/owner/bans"), api("GET", "/owner/flags")]);
  const up = (s) => `${Math.floor(s / 86400)} д ${Math.floor((s % 86400) / 3600)} ч`;
  const q = field({ placeholder: "Найти: @ник, id или имя" }), res = el("div", { class: "stackcol" });
  const search = async () => {
    const d = await act(() => api("GET", "/owner/users?q=" + encodeURIComponent(q.value))); if (!d || d === true) return;
    res.replaceChildren(d.users.length ? group(null, null, ...d.users.map((u) => row({ title: u.name || "—", sub: `${u.username ? "@" + u.username + " · " : ""}id ${u.id}` },
      u.banned ? btn("Разбанить", async () => { if (await act(() => api("POST", "/owner/ban", { user_id: u.id, ban: false }), "Разбанен")) search(); }) : dangerBtn("Бан в боте", async () => { if (await act(() => api("POST", "/owner/ban", { user_id: u.id, ban: true }), "Забанен в боте")) search(); })))) : group(null, null, empty("search", "Никого не нашёл")));
  };
  q.addEventListener("keydown", (e) => { if (e.key === "Enter") search(); });
  search();                                                  // сразу показываем всех известных пользователей
  return [...screen("Владелец", "Управление ботом целиком."),
    group("Статус", null, row({ title: "Работает", value: up(st.uptime) }), row({ title: "Пользователей", value: fmtNum(st.users) }), row({ title: "Чатов", value: `${st.chats_active} из ${st.chats_total}` }),
      row({ title: "База", value: `${st.db_backend}, ${fmtNum(Math.round(st.db_bytes / 1024))} КБ` }), row({ title: "ИИ / расшифровка", value: `${st.ai_configured ? "да" : "нет"} / ${st.stt_configured ? "да" : "нет"}` }),
      row({ title: "В блок-листе", value: `${bans.users.length} польз. · ${bans.chats.length} чатов` })),
    group("Функции", "Действуют сразу во всех чатах.", ...flags.flags.map((f) => row({ title: f.label }, toggle(f.value, async (v) => { if (await act(() => api("POST", "/owner/flags", { key: f.key, value: v }), "Сохранено")) refresh(); }, f.label)))),
    group("Чаты", null, ...chats.chats.map((c) => row({ title: c.title, sub: `${c.id} · ${c.members} участн.` }, el("span", { class: "chip " + (c.banned ? "bad" : c.active ? "ok" : "") }, c.banned ? "заблокирован" : c.active ? "активен" : "неактивен")))),
    group("Пользователи", null, row({ stack: true, title: "" }, el("div", { class: "compose" }, q, el("button", { class: "btn primary", "aria-label": "Найти", onclick: search }, icon("search", 20))))), res,
    group("Резервная копия", "Файл содержит данные всех чатов — храните его так же бережно, как токен.", row({ ico: "download", title: "Скачать копию базы", chevron: true, onclick: () => act(async () => {
      const r = await api("GET", "/owner/backup", undefined, true), blob = await r.blob(), a = el("a", { href: URL.createObjectURL(blob), download: "bot-backup" });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }, "Копия скачана") }))];
}

// ---------- запуск ----------
async function boot() {
  const view = $("view");
  if (!initData) { view.replaceChildren(...screen("Панель"), empty("lock", "Откройте из Telegram", "Панель работает как мини-приложение: нажмите кнопку «Открыть веб-панель» в чате с ботом.")); return; }
  view.replaceChildren(skeletons(4));
  const d = await act(() => api("GET", "/me")); if (!d || d === true) { view.replaceChildren(empty("circle-alert", "Не удалось войти", "Закройте панель и откройте её заново.")); return; }
  state.me = d;
  const sel = $("chat");
  for (const c of d.chats) sel.append(el("option", { value: c.id }, c.title));
  const want = Number(new URLSearchParams(location.search).get("chat"));
  if (want && d.chats.some((c) => c.id === want)) sel.value = String(want);
  const pick = async () => {
    state.chat = d.chats.find((c) => String(c.id) === sel.value) || null;
    $("chatTitle").textContent = state.chat ? state.chat.title : tr(d.is_owner ? "Владелец" : "Нет чатов");
    $("chatSub").textContent = state.chat ? tr(`Ранг ${state.chat.rank} · ${RANK_NAME[state.chat.rank] || ""}`) : d.user.name;
    const chev = $("chatChevron"); chev.replaceChildren(d.chats.length > 1 ? icon("chevron-down", 18) : "");
    sel.disabled = d.chats.length < 2;
    state.openReports = 0;
    if (state.chat && rankIs(1)) { try { state.openReports = (await api("GET", base() + "/reports")).reports.filter((r) => r.status === "open").length; } catch (e) { /* бейдж необязателен */ } }
    state.more = false; if (state.tab === "more" || !state.tab) state.tab = null;
    render();
  };
  sel.addEventListener("change", pick);
  if (!d.chats.length && d.is_owner) state.tab = "owner";
  pick();
}
boot();
