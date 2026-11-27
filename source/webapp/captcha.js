(() => {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready(); tg.expand();
    try { tg.setBackgroundColor("#0b1020"); tg.setHeaderColor("#0b1020"); } catch (e) {}
  }
  const token = new URLSearchParams(location.search).get("token") || "";
  const initData = tg ? tg.initData : "";
  const $ = (id) => document.getElementById(id);
  const slot = $("slot"), input = $("answer"), submit = $("submit"), status = $("status"), hint = $("hint"), ts = $("ts"), alt = $("alt");

  // Сообщаем серверу, почему у человека не открылся Cloudflare (попадает в журнал бота: «captcha[xxxxxx] клиент: …»).
  const report = (reason, extra) => {
    try {
      fetch("/captcha/report", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({ token, reason, ua: (navigator.userAgent || "").slice(0, 80) }, extra || {})) });
    } catch (_) { /* не критично */ }
  };
  window.addEventListener("error", (e) => report("js-error", { msg: String(e.message || e), src: String(e.filename || "").slice(-60), line: e.lineno || 0 }));

  const fail = (text) => { hint.textContent = text; input.hidden = submit.hidden = ts.hidden = alt.hidden = true; };
  const shake = () => {
    const m = document.querySelector("main"); m.classList.add("shake"); setTimeout(() => m.classList.remove("shake"), 400);
  };
  async function send(payload) {
    const r = await fetch("/captcha/verify", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ token, initData }, payload)),
    });
    return r.json();
  }
  const done = (result) => {
    const messages = { pending: "Проверка пройдена. Заявку рассмотрит администратор.",
      restricted: "Проверка пройдена. Ограничение модератора остаётся в силе.",
      recheck: "Проверка пройдена. Откройте следующую проверку в чате.",
      done: "Проверка пройдена ✓" };
    hint.textContent = messages[result] || messages.done;
    input.hidden = submit.hidden = ts.hidden = alt.hidden = true;
    status.textContent = ""; slot.replaceChildren();
    if (!result || result === "done") setTimeout(() => tg && tg.close(), 1200);
  };
  const releaseFailed = () => { status.textContent = ""; slot.replaceChildren(); fail("Проверка пройдена, но Telegram не применил результат. Обратитесь к администратору чата."); };

  const T = Object.assign({ load: 8000, alt: 6000, stall: 15000 }, window.__captchaTimeouts || {});   // окно __captchaTimeouts — для браузерных тестов
  let mode = "none";                 // turnstile | image
  let tsApi = null, widget = null, watchdog = null, altTimer = null, solved = false, interactive = false, fails = 0;

  // ---------- запасная капча: код с картинки ----------
  let need = 5;   // длину кода сообщает сервер (X-Code-Length): при повышенной сложности код длиннее
  const update = () => { submit.disabled = input.value.trim().length < need; };
  input.addEventListener("input", () => { input.value = input.value.toUpperCase().replace(/[^A-Z0-9]/g, ""); update(); });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !submit.disabled) submit.click(); });
  async function startImage() {
    const r = await fetch("/captcha/image?token=" + encodeURIComponent(token), { headers: { "X-Init-Data": initData } });
    if (!r.ok) return fail("Проверка недоступна или уже пройдена.");
    need = parseInt(r.headers.get("X-Code-Length") || "5", 10) || 5;
    input.maxLength = need; input.hidden = submit.hidden = false;
    hint.textContent = "Введите код с картинки";
    const img = new Image(260, 100);  // тег создаём сразу с адресом картинки
    img.id = "code"; img.alt = "Код проверки";
    const imageUrl = URL.createObjectURL(await r.blob());
    img.onload = img.onerror = () => URL.revokeObjectURL(imageUrl);
    img.src = imageUrl;
    slot.replaceChildren(img);
    input.focus();
  }
  submit.onclick = async () => {
    submit.disabled = true; status.textContent = "Проверяем…";
    let j = { ok: false };
    try { j = await send({ answer: input.value.trim() }); } catch (e) { /* сеть */ }
    if (j.ok) return done(j.result);
    if (j.error === "release_failed") return releaseFailed();
    status.textContent = j.error === "attempts" ? "Слишком много попыток." : "Неверный код, попробуйте ещё раз.";
    shake(); input.value = ""; update(); input.focus();
  };

  // Переход на капчу с картинкой: по ошибке Cloudflare, по таймауту, после неудач или кнопкой «Не получается?». Один раз.
  async function switchToImage(reason, code) {
    if (mode === "image") return;
    mode = "image";
    clearTimeout(watchdog); clearTimeout(altTimer);
    report(reason, code ? { code: String(code) } : {});
    try { if (tsApi && widget !== null) tsApi.remove(widget); } catch (e) { /* виджет мог не создаться */ }
    ts.hidden = true; alt.hidden = true; status.textContent = "";
    try { await startImage(); } catch (e) { fail("Ошибка сети, откройте проверку заново."); }
  }
  alt.onclick = () => switchToImage("manual");

  // ---------- Cloudflare Turnstile ----------
  function loadTurnstile() {
    return new Promise((resolve, reject) => {
      if (window.turnstile) return resolve(window.turnstile);
      const s = document.createElement("script");
      s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      s.async = true;
      const to = setTimeout(() => reject(new Error("timeout")), T.load);
      s.onload = () => { clearTimeout(to); window.turnstile ? resolve(window.turnstile) : reject(new Error("no api")); };
      s.onerror = () => { clearTimeout(to); reject(new Error("load")); };
      document.head.appendChild(s);
    });
  }
  async function startTurnstile(info) {
    mode = "turnstile";
    hint.textContent = "Подтвердите, что вы не бот";
    // кнопка «Не получается?» появляется сама через несколько секунд; если виджет молчит дольше (Cloudflare тормозит или режется) — сами
    // переходим на картинку. Пока человек проходит интерактивную проверку (before-interactive), автопереход не мешает.
    altTimer = setTimeout(() => { if (!solved) alt.hidden = false; }, T.alt);
    watchdog = setTimeout(() => { if (!solved && !interactive) switchToImage("turnstile-stalled"); }, T.stall);
    try { tsApi = await loadTurnstile(); } catch (e) { return switchToImage("turnstile-load", e.message); }
    if (mode !== "turnstile") return;
    ts.hidden = false;
    const t = tsApi;
    const onToken = async (value) => {
      solved = true; clearTimeout(watchdog);
      status.textContent = "Проверяем…";
      let j = { ok: false };
      try { j = await send({ turnstile: value }); } catch (e) { j = { ok: false, error: "network" }; }
      if (j.ok) return done(j.result);
    if (j.error === "release_failed") return releaseFailed();
      if (j.error === "network" || j.error === "attempts") {        // Cloudflare недоступен серверу или попытки кончились — картинка надёжнее
        return switchToImage(j.error === "network" ? "siteverify-network" : "turnstile-attempts");
      }
      status.textContent = "Проверка не пройдена, попробуйте ещё раз.";
      shake();
      if (++fails >= 2) alt.hidden = false;
      solved = false;
      if (widget !== null) t.reset(widget);
    };
    try {
      widget = t.render("#ts", {
        sitekey: info.sitekey, cData: info.cdata, theme: (tg && tg.colorScheme) || "auto", language: "auto",
        callback: onToken,
        "before-interactive-callback": () => { interactive = true; clearTimeout(watchdog); },
        "error-callback": (code) => { switchToImage("turnstile-error", code); return true; },
        "unsupported-callback": () => switchToImage("turnstile-unsupported"),
        "timeout-callback": () => { if (widget !== null) t.reset(widget); },
        "expired-callback": () => { solved = false; if (widget !== null) t.reset(widget); },
      });
    } catch (e) { return switchToImage("turnstile-render", e.message); }
  }

  async function load() {
    if (!initData) return fail("Откройте проверку из Telegram.");
    const r = await fetch("/captcha/info?token=" + encodeURIComponent(token), { headers: { "X-Init-Data": initData } });
    if (!r.ok) return fail("Проверка недоступна или уже пройдена.");
    const info = await r.json();
    if (info.mode === "turnstile") return startTurnstile(info);
    mode = "image";
    return startImage();
  }
  load().catch(() => fail("Ошибка сети, откройте проверку заново."));
})();
