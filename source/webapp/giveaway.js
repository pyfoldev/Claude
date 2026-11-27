(() => {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready(); tg.expand();
    try { tg.setBackgroundColor("#0b1020"); tg.setHeaderColor("#0b1020"); } catch (e) {}
  }
  const id = new URLSearchParams(location.search).get("id") || "";
  const initData = tg ? tg.initData : "";
  const $ = (x) => document.getElementById(x);
  const title = $("title"), meta = $("meta"), hint = $("hint"), slot = $("slot"),
        input = $("answer"), submit = $("submit"), status = $("status");
  const headers = { "X-Init-Data": initData };
  let need = 5;

  const hideForm = () => { hint.hidden = input.hidden = submit.hidden = true; slot.replaceChildren(); };
  const done = (text) => { hideForm(); status.textContent = text; status.className = "ok"; };
  const update = () => { submit.disabled = input.value.trim().length < need; };
  input.addEventListener("input", () => {
    input.value = input.value.toUpperCase().replace(/[^A-Z0-9]/g, "");
    update();
  });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !submit.disabled) submit.click(); });

  async function loadImage() {
    const r = await fetch("/giveaway/api/image?id=" + encodeURIComponent(id), { headers });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      hideForm(); status.textContent = j.message || "Конкурс недоступен.";
      return;
    }
    need = parseInt(r.headers.get("X-Code-Length") || "5", 10) || 5;
    input.maxLength = need;
    const img = new Image(260, 100);
    img.id = "code"; img.alt = "Код проверки";
    const imageUrl = URL.createObjectURL(await r.blob());
    img.onload = img.onerror = () => URL.revokeObjectURL(imageUrl);
    img.src = imageUrl;
    slot.replaceChildren(img);
    input.value = ""; update(); input.focus();
  }

  async function load() {
    if (!initData) { hideForm(); status.textContent = "Откройте конкурс из Telegram."; return; }
    const r = await fetch("/giveaway/api/info?id=" + encodeURIComponent(id), { headers });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) { hideForm(); status.textContent = j.message || "Конкурс недоступен."; return; }
    title.textContent = "🎁 Конкурс №" + j.id + (j.chat ? " · " + j.chat : "");
    meta.textContent = "Итоги: " + j.ends + " · победителей: " + j.winners + " · участников: " + j.count;
    if (j.joined) { done("✅ Вы уже участвуете. Удачи!"); return; }
    await loadImage();
  }

  submit.onclick = async () => {
    submit.disabled = true; status.textContent = "Проверяем…"; status.className = "";
    let j = { ok: false, message: "Ошибка сети, попробуйте ещё раз." };
    try {
      const r = await fetch("/giveaway/api/join", {
        method: "POST", headers: { "Content-Type": "application/json", "X-Init-Data": initData },
        body: JSON.stringify({ id, answer: input.value.trim() }),
      });
      j = await r.json();
    } catch (e) { /* сеть */ }
    if (j.ok) {
      done(j.already ? "✅ Вы уже участвуете. Удачи!" : "🎉 Вы участвуете в конкурсе! Удачи!");
      if (tg && tg.HapticFeedback) { try { tg.HapticFeedback.notificationOccurred("success"); } catch (e) {} }
      setTimeout(() => tg && tg.close(), 1800);
      return;
    }
    status.textContent = j.message || "Не получилось.";
    if (j.error === "expired") { await loadImage(); return; }
    if (j.error === "attempts" || j.error === "member" || j.error === "closed") { hideForm(); status.textContent = j.message; return; }
    document.querySelector("main").classList.add("shake");
    setTimeout(() => document.querySelector("main").classList.remove("shake"), 400);
    input.value = ""; update(); input.focus();
  };

  load().catch(() => { hideForm(); status.textContent = "Ошибка сети, откройте конкурс заново."; });
})();
