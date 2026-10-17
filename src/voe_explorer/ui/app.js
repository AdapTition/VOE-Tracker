"use strict";

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = () => window.pywebview.api;

const ui = {
  state: null,
  openMenu: null,       // card id with open ⋯ menu
  confirmDelete: null,  // card id awaiting delete confirmation
  expanded: new Set(),  // card ids with other days shown
  renameId: null,
  city: { value: "м.. Вінниця (Вінницька Область/М.Вінниця)", id: "510100000", name: "Вінниця" },
  lastText: "",
  healthWindow: "day",
  raw: { id: null, kind: "schedule", items: [], sel: 0, tab: "html" },
  lastOk: 0,            // when get_state last answered
  installError: null,
};
const NO_STATE_MS = 60000;   // no fresh state for this long: never keep showing the old status as current

// ---------- polling ----------
let ticking = false;
async function tick() {
  if (ticking) return;   // the previous call is still waiting for an answer
  ticking = true;
  try {
    const s = await api().get_state();
    if (s && !s.error) { ui.state = s; ui.lastOk = Date.now(); }
  } catch (e) { /* bridge not ready yet */ }
  ticking = false;
  if (ui.state) render();
}
setInterval(() => { if (ui.state && Date.now() - ui.lastOk > NO_STATE_MS) render(); }, 5000);

// the app itself stopped answering: show every card as "could not update"
function frozen(s) {
  if (Date.now() - ui.lastOk <= NO_STATE_MS) return s;
  return {
    ...s,
    health: { state: "unknown", text: "Перевіряємо VOE…" },
    cards: s.cards.map((c) => ({ ...c, level: "stale", headline: "Не вдалося оновити", loading: false })),
  };
}

// ---------- main render ----------
function render() {
  const s = frozen(ui.state);
  const h = s.health || { state: "unknown", text: "Перевіряємо VOE…" };
  $("#health .dot").className = "dot " + h.state;
  $("#health .health-text").textContent = h.text;

  let banners = "";
  if (s.update) {
    banners += `<div class="banner"><span>Є нова версія ${esc(s.update.version)}</span>
      <button data-act="update" data-url="${esc(s.update.url)}">Завантажити</button></div>`;
  }
  if (s.install_offer) {
    banners += `<div class="banner"><span>Програма запущена з тимчасової папки.</span>
      <span class="actions"><button class="link" data-act="dismiss-install">Не треба</button>
      <button data-act="install">Встановити на цей комп'ютер</button></span></div>`;
    if (ui.installError) banners += `<div class="banner err"><span>Не вдалося встановити: ${esc(ui.installError)}</span></div>`;
  }
  $("#banners").innerHTML = banners;

  if (!s.cards.length) {
    $("#cards").innerHTML = `<div class="empty"><b>Поки що немає жодної адреси</b>
      Додайте свій будинок — і тут буде видно, чи є світло і коли його дадуть.</div>`;
    return;
  }
  $("#cards").innerHTML = s.cards.map(cardHtml).join("");
}

function stripHtml(hours, isToday, dim) {
  const now = new Date().getHours();
  const cells = hours.map((st, i) =>
    `<button class="h h-${esc(st)}${isToday && i === now ? " now" : ""}" data-act="legend" title="${String(i).padStart(2, "0")}:00–${String(i + 1).padStart(2, "0")}:00"></button>`).join("");
  return `<div class="strip-row"><div class="strip${dim ? " dim" : ""}">${cells}</div>
    <button class="q" data-act="legend" title="Що означають кольори">?</button></div>
    <div class="hours"><span>00</span><span>06</span><span>12</span><span>18</span><span>24</span></div>`;
}

function cardHtml(c) {
  const dim = c.level === "stale" || c.level === "site_changed";
  const sub = [];
  if (c.level === "off" || c.level === "possible") {
    if (c.reason) sub.push(esc(c.reason));
    if (c.until) sub.push("до " + esc(c.until));
    if (c.source && c.source !== (c.reason || "").toLowerCase()) sub.push(`<span class="src">${esc(c.source)}</span>`);
  } else if (c.level === "stale") {
    sub.push(c.data_at ? `Не вдалося оновити · останні дані о ${esc(c.data_at)}` : "Ще не вдалося отримати дані з VOE");
  } else if (c.level === "site_changed") {
    sub.push("Перевірте, чи є нова версія програми");
  }

  let body = "";
  if (c.today) body += stripHtml(c.today.hours, true, dim);
  const meta = [];
  if (c.data_at && c.level !== "stale") meta.push(`графік станом на ${esc(c.data_at)}`);
  if (c.loading) meta.push(`<span class="loading">оновлюється…</span>`);
  if (meta.length) body += `<div class="meta">${meta.map((m) => `<span>${m}</span>`).join("")}</div>`;

  body += c.planned.map((p) => `<div class="planned">🔧 Планові роботи · ${esc(p.text)}</div>`).join("");

  if (c.other_days.length) {
    const open = ui.expanded.has(c.id);
    body += `<button class="days-toggle" data-act="days" data-id="${esc(c.id)}">${open ? "Сховати інші дні ▴" : "Інші дні ▾"}</button>`;
    if (open) {
      body += c.other_days.map((d) => `<div class="other-day"><div class="dl">${esc(d.label)}</div>${stripHtml(d.hours, false, dim)}</div>`).join("");
    }
  }

  return `<section class="card">
    <div class="card-top">
      <div><div class="label">${esc(c.label)}</div><div class="addr">${esc(c.address)}</div></div>
      <button class="more" data-act="menu" data-id="${esc(c.id)}" title="Ще">⋯</button>
    </div>
    <div class="status lvl-${esc(c.level)}"><span class="bullet">●</span>${esc(c.headline)}</div>
    <div class="status-sub">${sub.join(" · ") || "&nbsp;"}</div>
    ${body}
    ${ui.openMenu === c.id ? menuHtml(c) : ""}
  </section>`;
}

function menuHtml(c) {
  if (ui.confirmDelete === c.id) {
    return `<div class="menu"><div class="confirm">Видалити «${esc(c.label)}»?
      <div><button data-act="delete-yes" data-id="${esc(c.id)}">Так</button><button data-act="delete-no">Ні</button></div></div></div>`;
  }
  return `<div class="menu">
    <button data-act="rename" data-id="${esc(c.id)}">Перейменувати</button>
    <button data-act="up" data-id="${esc(c.id)}">Вгору</button>
    <button data-act="down" data-id="${esc(c.id)}">Вниз</button>
    <button data-act="raw" data-id="${esc(c.id)}">Відповідь VOE</button>
    <button class="danger" data-act="delete" data-id="${esc(c.id)}">Видалити</button>
  </div>`;
}

// ---------- clicks on cards / banners ----------
document.addEventListener("click", async (e) => {
  const t = e.target.closest("[data-act]");
  if (!e.target.closest("#legend") && !(t && t.dataset.act === "legend")) $("#legend").hidden = true;
  if (!t) {
    if (ui.openMenu && !e.target.closest(".menu")) { ui.openMenu = null; ui.confirmDelete = null; render(); }
    return;
  }
  const id = t.dataset.id;
  switch (t.dataset.act) {
    case "menu": ui.openMenu = ui.openMenu === id ? null : id; ui.confirmDelete = null; render(); break;
    case "up": await api().move(id, -1); closeMenu(); break;
    case "down": await api().move(id, 1); closeMenu(); break;
    case "delete": ui.confirmDelete = id; render(); break;
    case "delete-no": closeMenu(); break;
    case "delete-yes": await api().remove(id); closeMenu(); break;
    case "rename": openRename(id); break;
    case "raw": ui.openMenu = null; openRaw(id, "schedule"); break;
    case "days": ui.expanded.has(id) ? ui.expanded.delete(id) : ui.expanded.add(id); render(); break;
    case "legend": showLegend(t); break;
    case "update": api().open_url(t.dataset.url); break;
    case "install": {
      ui.installError = null;
      const r = await api().install_self();
      if (r && r.error) { ui.installError = r.error; render(); }
      break;
    }
    case "dismiss-install": await api().dismiss_install(); tick(); break;
  }
});

async function closeMenu() { ui.openMenu = null; ui.confirmDelete = null; await tick(); }

function showLegend(anchor) {
  const lg = $("#legend");
  lg.hidden = false;
  const r = anchor.getBoundingClientRect();
  const left = Math.min(Math.max(8, r.left - 150), window.innerWidth - lg.offsetWidth - 8);
  let top = r.bottom + 8;
  if (top + lg.offsetHeight > window.innerHeight - 8) top = r.top - lg.offsetHeight - 8;
  lg.style.left = left + "px";
  lg.style.top = top + "px";
}

// ---------- overlays ----------
document.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => { b.closest(".overlay").hidden = true; }));
document.querySelectorAll(".overlay").forEach((o) => o.addEventListener("click", (e) => { if (e.target === o) o.hidden = true; }));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") document.querySelectorAll(".overlay").forEach((o) => { o.hidden = true; });
});

// ---------- rename ----------
function openRename(id) {
  const c = ui.state.cards.find((x) => x.id === id);
  ui.renameId = id; ui.openMenu = null; render();
  $("#r-label").value = c ? c.label : "";
  $("#rename-sheet").hidden = false;
  $("#r-label").focus();
}
async function saveRename() {
  await api().rename(ui.renameId, $("#r-label").value);
  $("#rename-sheet").hidden = true;
  tick();
}
$("#r-save").addEventListener("click", saveRename);
$("#r-label").addEventListener("keydown", (e) => { if (e.key === "Enter") saveRename(); });

// ---------- add address ----------
$("#add").addEventListener("click", () => {
  $("#f-label").value = ""; $("#f-text").value = ""; $("#f-result").innerHTML = "";
  $("#f-city-search").hidden = true;
  $("#add-sheet").hidden = false;
  $("#f-label").focus();
});

$("#f-city-change").addEventListener("click", () => {
  $("#f-city-search").hidden = false; $("#f-city-q").value = ""; $("#f-city-results").innerHTML = ""; $("#f-city-q").focus();
});

let cityTimer = null;
$("#f-city-q").addEventListener("input", () => {
  clearTimeout(cityTimer);
  const q = $("#f-city-q").value.trim();
  if (q.length < 3) { $("#f-city-results").innerHTML = ""; return; }
  cityTimer = setTimeout(async () => {
    $("#f-city-results").innerHTML = `<div class="msg">Шукаємо…</div>`;
    const res = await api().search_cities(q);
    if (res.error) { $("#f-city-results").innerHTML = `<div class="msg err">${esc(res.error)}</div>`; return; }
    if (!res.length) { $("#f-city-results").innerHTML = `<div class="msg">Нічого не знайшли</div>`; return; }
    $("#f-city-results").innerHTML = res.map((c, i) => `<button class="choice" data-i="${i}">${esc(c.value.replace(/^(\S+?)\.\.\s*/, "$1 "))}</button>`).join("");
    $("#f-city-results").querySelectorAll(".choice").forEach((b) => b.addEventListener("click", () => {
      ui.city = res[+b.dataset.i];
      $("#f-city-name").textContent = ui.city.name;
      $("#f-city-search").hidden = true;
    }));
  }, 400);
});

const prettyStreet = (v) => v.replace(/^(\S+)\.\s+/, "$1 ");

async function find() {
  const text = $("#f-text").value.trim();
  if (!text) return;
  ui.lastText = text;
  busy(true);
  const res = await api().resolve(text, ui.city);
  busy(false);
  showResolution(res);
}
$("#f-find").addEventListener("click", find);
$("#f-text").addEventListener("keydown", (e) => { if (e.key === "Enter") find(); });

function busy(on) {
  $("#f-find").disabled = on;
  if (on) $("#f-result").innerHTML = `<div class="msg">Шукаємо… сайт VOE буває повільним, зачекайте трохи.</div>`;
}

function showResolution(res) {
  const box = $("#f-result");
  if (res.error) { box.innerHTML = `<div class="msg err">${esc(res.error)}</div>`; return; }
  if (res.kind === "not_found") {
    box.innerHTML = `<div class="msg">Не знайшли таку вулицю. Спробуйте написати лише назву, наприклад „Ботанічний“.</div>`;
    return;
  }
  if (res.kind === "choose_street") {
    box.innerHTML = `<div class="msg">Яку саме вулицю ви маєте на увазі?</div><div class="choices">${
      res.street_choices.map((s, i) => `<button class="choice" data-i="${i}">${esc(prettyStreet(s.value))}</button>`).join("")}</div>`;
    box.querySelectorAll(".choice").forEach((b) => b.addEventListener("click", async () => {
      const street = res.street_choices[+b.dataset.i];
      busy(true);
      const r = await api().choose_street(ui.city, street, "", ui.lastText);
      busy(false);
      showResolution(r);
    }));
    return;
  }
  if (res.kind === "choose_house") {
    const street = res.street;
    box.innerHTML = `<div class="msg">${esc(prettyStreet(street.value))}: ${res.house_choices.length ? "оберіть номер будинку" : "вкажіть номер будинку"}</div>
      <div class="choices grid">${res.house_choices.map((h, i) => `<button class="choice" data-i="${i}">${esc(h.value)}</button>`).join("")}</div>
      <label class="field" style="margin-top:10px">Інший номер<input id="f-house"></label>`;
    box.querySelectorAll(".choice").forEach((b) => b.addEventListener("click", async () => {
      const r = await api().pick_house(ui.city, street, res.house_choices[+b.dataset.i], ui.lastText);
      showResolution(r);
    }));
    $("#f-house").addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      busy(true);
      const r = await api().choose_street(ui.city, street, e.target.value, ui.lastText);
      busy(false);
      showResolution(r);
    });
    return;
  }
  // found
  box.innerHTML = `<div class="found"><b>${esc(prettyStreet(res.street.value))}, ${esc(res.house.value)}</b>
    <button class="primary" id="f-add">Додати</button></div>`;
  $("#f-add").addEventListener("click", async () => {
    const label = $("#f-label").value.trim() || "Дім";
    const out = await api().add_address(label, ui.city, res.street, res.house);
    if (out.error) { box.insertAdjacentHTML("beforeend", `<div class="msg err">${esc(out.error)}</div>`); return; }
    $("#add-sheet").hidden = true;
    tick();
  });
}

// ---------- health history ----------
$("#health").addEventListener("click", () => { $("#health-sheet").hidden = false; loadHealth(); });
document.querySelectorAll("#health-sheet [data-window]").forEach((b) => b.addEventListener("click", () => {
  ui.healthWindow = b.dataset.window;
  document.querySelectorAll("#health-sheet [data-window]").forEach((x) => x.classList.toggle("on", x === b));
  loadHealth();
}));
$("#h-raw").addEventListener("click", () => { $("#health-sheet").hidden = true; openRaw(null, "probe"); });

async function loadHealth() {
  const h = await api().health_history(ui.healthWindow);
  if (h.error) { $("#h-stats").textContent = h.error; return; }
  const start = new Date(h.start).getTime(), end = new Date(h.end).getTime(), span = end - start;
  $("#h-bar").innerHTML = h.segments.map((s) => {
    const w = (new Date(s.end) - new Date(s.start)) / span * 100;
    return `<div class="s-${esc(s.state)}" style="width:${w}%" title="${fmtTime(s.start)}–${fmtTime(s.end)}"></div>`;
  }).join("");
  const ticks = ui.healthWindow === "day" ? 4 : 7;
  let axis = "";
  for (let i = 0; i <= ticks; i++) {
    const d = new Date(start + span * i / ticks);
    axis += `<span>${ui.healthWindow === "day" ? fmtHM(d) : fmtDM(d)}</span>`;
  }
  $("#h-axis").innerHTML = axis;
  const st = h.stats;
  $("#h-stats").textContent = `Падінь: ${st.down_count} · загалом ${st.down_minutes} хв` +
    (st.avg_s != null ? ` · середній час ${st.avg_s.toFixed(1)} с · найгірший ${st.max_s.toFixed(1)} с` : "");
}
const pad = (n) => String(n).padStart(2, "0");
const fmtHM = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
const fmtDM = (d) => `${pad(d.getDate())}.${pad(d.getMonth() + 1)}`;
const fmtTime = (iso) => { const d = new Date(iso); return `${fmtDM(d)} ${fmtHM(d)}`; };

// ---------- raw responses ----------
document.querySelectorAll("#raw-kinds [data-kind]").forEach((b) => b.addEventListener("click", () => openRaw(ui.raw.id, b.dataset.kind)));

async function openRaw(id, kind) {
  ui.raw = { id, kind, items: [], sel: 0, tab: kind === "schedule" || kind === "planned" ? "html" : "json" };
  document.querySelectorAll("#raw-kinds [data-kind]").forEach((x) => {
    x.classList.toggle("on", x.dataset.kind === kind);
    x.hidden = x.dataset.kind === "schedule" && !id;
  });
  $("#raw-sheet").hidden = false;
  render();
  $("#raw-list").innerHTML = `<li>Завантажуємо…</li>`;
  $("#raw-detail").innerHTML = "";
  const res = await api().get_raw(kind === "schedule" ? id : null, kind);
  ui.raw.items = res.items || [];
  renderRaw();
}

function renderRaw() {
  const r = ui.raw;
  if (!r.items.length) { $("#raw-list").innerHTML = `<li>Відповідей ще немає</li>`; $("#raw-detail").innerHTML = ""; return; }
  $("#raw-list").innerHTML = r.items.map((it, i) =>
    `<li class="${i === r.sel ? "on" : ""}" data-i="${i}">${esc(it.at)}<br><span class="code">${it.status ?? "немає відповіді"} · ${it.elapsed_s} с</span></li>`).join("");
  $("#raw-list").querySelectorAll("li[data-i]").forEach((li) => li.addEventListener("click", () => { r.sel = +li.dataset.i; renderRaw(); }));

  const it = r.items[r.sel];
  const raw = r.tab === "html" ? (it.html ?? "(немає HTML)") : (it.json ?? "(немає)");
  $("#raw-detail").innerHTML = `${understoodHtml(it.understood)}
    <div class="raw-tools">
      <div class="seg-switch" style="margin:0">
        <button data-tab="html" class="${r.tab === "html" ? "on" : ""}">HTML</button>
        <button data-tab="json" class="${r.tab === "json" ? "on" : ""}">JSON</button>
      </div>
      <button class="act" id="raw-copy">Скопіювати</button>
      <button class="act" id="raw-save">Зберегти у файл</button>
      <span id="raw-note" class="loading"></span>
    </div>
    <pre class="raw">${esc(raw)}</pre>`;
  $("#raw-detail").querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { r.tab = b.dataset.tab; renderRaw(); }));
  $("#raw-copy").addEventListener("click", () => copyText(raw));
  $("#raw-save").addEventListener("click", async () => {
    const out = await api().save_raw(it.id);
    $("#raw-note").textContent = out.path ? `Збережено: ${out.path}` : (out.error || "");
  });
}

function understoodHtml(u) {
  if (!u || !Object.keys(u).length) return "";
  if (u.error) return `<div class="understood"><b class="bad">${esc(u.error)}</b></div>`;
  if (u.works != null) return `<div class="understood">Програма знайшла планових робіт: <b>${u.works}</b></div>`;
  const lines = [];
  lines.push(`<b>Як програма це зрозуміла:</b>`);
  lines.push(`Світла зараз немає (за повідомленням): <b>${u.power_off_now ? "так" : "ні"}</b>`);
  if (u.reason) lines.push(`Причина: <b>${esc(u.reason)}</b>`);
  if (u.start || u.end) lines.push(`Початок: ${esc(u.start || "—")} · Завершення: ${esc(u.end || "—")}`);
  u.message_lines.forEach((m) => lines.push(`<span style="color:#6b6b66">«${esc(m)}»</span>`));
  if (u.warning) lines.push(`<span class="warn">${esc(u.warning)}</span>`);
  u.days.forEach((d) => lines.push(`${esc(d.label)}: ${d.hours.map((h, i) => h === "on" ? "" : `${pad(i)}h=${esc(h)}`).filter(Boolean).join(", ") || "усі години — світло є"}`));
  if (u.unknown_classes.length) lines.push(`<span class="bad">Невідомі класи комірок: ${esc(u.unknown_classes.join(", "))}</span>`);
  return `<div class="understood">${lines.join("<br>")}</div>`;
}

function copyText(text) {
  const done = () => { $("#raw-note").textContent = "Скопійовано"; };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text, done));
  } else fallbackCopy(text, done);
}
function fallbackCopy(text, done) {
  const ta = document.createElement("textarea");
  ta.value = text; document.body.appendChild(ta); ta.select();
  try { document.execCommand("copy"); done(); } finally { ta.remove(); }
}

// ---------- start ----------
function start() { tick(); setInterval(tick, 2000); }
if (window.pywebview && window.pywebview.api) start();
else window.addEventListener("pywebviewready", start);
