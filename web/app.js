"use strict";

const $ = (id) => document.getElementById(id);
const gridEl = $("grid");

const FOCUS_SCALE = 1.45;      // keep in sync with --focus-scale in style.css
const PREVIEW_DELAY = 280;     // ms a tile must stay focused before its clip starts
const REPEAT_DELAY = 380;      // hold-to-repeat for d-pad / stick
const REPEAT_RATE = 120;
const IDLE_ATTRACT = 45_000;   // start the idle showcase after this long with no input
const ATTRACT_STEP = 14_000;   // time on each game in the showcase
const LAUNCH_SCREEN = 10_000;  // how long the "Launching…" screen stays up
const PLAYTIME_POLL = 60_000;  // the server itself re-reads Steam every 2 minutes

let data = null;
let tiles = [];          // tile elements in DOM order
let games = [];          // parallel to tiles
let focusIdx = 0;
let mode = "grid";       // grid | detail | launching
let suppressUntil = 0;   // ignore input briefly after the window regains focus
let lastInput = performance.now();
let attractTimer = null;
let play = { games: {} };

// ── data / rendering ────────────────────────────────────────────────

async function load() {
  const res = await fetch("/api/games", { cache: "no-store" });
  data = await res.json();
  $("title").textContent = data.title;
  document.title = data.title;
  renderLegend();
  render();
}

function typeOf(g) {
  return data.types[g.type] || { label: g.type, color: "#888" };
}

function renderLegend() {
  const used = new Set(data.games.map((g) => g.type));
  $("legend").replaceChildren(
    ...Object.entries(data.types)
      .filter(([k]) => used.has(k))
      .map(([, t]) => {
        const li = document.createElement("li");
        li.innerHTML = `<i></i>${t.label}`;
        li.style.setProperty("--c", t.color);
        return li;
      })
  );
}

function render() {
  const keepId = games[focusIdx]?.id;
  const typeOrder = Object.keys(data.types);
  const byPlayers = new Map();
  for (const g of data.games) {
    if (!byPlayers.has(g.players)) byPlayers.set(g.players, []);
    byPlayers.get(g.players).push(g);
  }
  const counts = [...byPlayers.keys()].sort((a, b) => b - a);

  tiles = [];
  games = [];
  const sections = counts.map((n) => {
    const list = byPlayers.get(n).sort(
      (a, b) => typeOrder.indexOf(a.type) - typeOrder.indexOf(b.type) || a.title.localeCompare(b.title)
    );
    const sec = document.createElement("section");
    sec.className = "section";
    sec.dataset.count = list.length;
    sec.innerHTML = `
      <h2 class="section-head">
        <span class="num">${n}</span>
        <span class="label">${n === 1 ? "player · pass the pad" : "players"}</span>
        <span class="pips">${"<span></span>".repeat(Math.min(n, 8))}</span>
      </h2>`;
    const grid = document.createElement("div");
    grid.className = "grid";
    for (const g of list) {
      const el = makeTile(g);
      el.dataset.idx = tiles.length;
      tiles.push(el);
      games.push(g);
      grid.append(el);
    }
    sec.append(grid);
    return sec;
  });
  gridEl.replaceChildren(...sections);
  sizeSections();
  applyPlaytime();

  const idx = games.findIndex((g) => g.id === keepId);
  setFocus(idx >= 0 ? idx : 0, { instant: true });
}

// Each section spans as many page columns as it has tiles, so small groups share a row.
function sizeSections() {
  const cols = parseInt(getComputedStyle(gridEl).getPropertyValue("--cols")) || 4;
  for (const sec of gridEl.querySelectorAll(".section")) {
    sec.style.gridColumn = `span ${Math.min(Number(sec.dataset.count), cols)}`;
  }
}
addEventListener("resize", sizeSections);

function makeTile(g) {
  const t = typeOf(g);
  const el = document.createElement("div");
  el.className = "tile";
  el.style.setProperty("--c", t.color);
  el.innerHTML = `
    ${g.cover ? `<img src="${g.cover}" alt="" loading="lazy">` : `<div class="noart">${esc(g.title)}</div>`}
    <div class="badges left">
      <span class="badge time" hidden></span>
      <span class="badge lan" hidden></span>
    </div>
    <div class="badges">
      ${g.local ? `<span class="badge type">LANIT original</span>` : ""}
      ${g.installed ? "" : `<span class="badge missing">Not installed</span>`}
    </div>
    <div class="caption">${esc(g.title)}</div>`;
  el.addEventListener("mousemove", (e) => {
    if (mode !== "grid" || (e.movementX === 0 && e.movementY === 0)) return;
    const i = Number(el.dataset.idx);
    if (i !== focusIdx) setFocus(i, { noScroll: true });
  });
  el.addEventListener("click", () => {
    if (mode !== "grid") return;
    setFocus(Number(el.dataset.idx), { noScroll: true });
    openDetail();
  });
  return el;
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

// ── playtime counters ───────────────────────────────────────────────

function fmtMinutes(m) {
  if (m < 60) return `${Math.round(m)} min`;
  const h = m / 60;
  return h < 10 ? `${h.toFixed(1)} h` : `${Math.round(h).toLocaleString()} h`;
}

function playtimeOf(g) {
  return play.games?.[g.id] || null;
}

function playtimeText(g) {
  const p = playtimeOf(g);
  if (!p) return "";
  const total = p.minutes ? `${fmtMinutes(p.minutes)} played` : "Never played";
  return p.lan_minutes ? `${total} · +${fmtMinutes(p.lan_minutes)} this LAN` : total;
}

async function loadPlaytime() {
  try {
    play = await (await fetch("/api/playtime", { cache: "no-store" })).json();
  } catch {
    return;
  }
  applyPlaytime();
  $("play-source").textContent = play.source
    ? `Playtime: ${play.source.replace(/ \(.*/, "")} · ${play.updated}`
    : "";
}

function applyPlaytime() {
  tiles.forEach((el, i) => {
    const p = playtimeOf(games[i]);
    const time = el.querySelector(".badge.time");
    const lan = el.querySelector(".badge.lan");
    time.hidden = !p;
    lan.hidden = !p?.lan_minutes;
    if (!p) return;
    time.textContent = p.minutes ? fmtMinutes(p.minutes) : "Never played";
    time.classList.toggle("fresh", !p.minutes);
    lan.textContent = `+${fmtMinutes(p.lan_minutes)} this LAN`;
  });
}

// ── focus + gameplay preview ────────────────────────────────────────

let previewTimer = null;
let previewVideo = null;

function setFocus(i, { instant = false, noScroll = false } = {}) {
  if (!tiles.length) return;
  tiles[focusIdx]?.classList.remove("focused");
  focusIdx = Math.max(0, Math.min(tiles.length - 1, i));
  const el = tiles[focusIdx];
  el.style.transformOrigin = growOrigin(el);
  el.classList.add("focused");
  if (!noScroll) scrollToTile(el, instant);
  startPreview(el, games[focusIdx]);
}

// Tiles in the outer columns grow inwards so they never leave the screen.
function growOrigin(el) {
  const view = gridEl.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  const pad = parseFloat(getComputedStyle(gridEl).paddingLeft);
  const h = r.left - view.left < pad + 20 ? "left" : view.right - r.right < pad + 20 ? "right" : "center";
  return `${h} center`;
}

function scrollToTile(el, instant) {
  const view = gridEl.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  const grow = (r.height * (FOCUS_SCALE - 1)) / 2;
  const topPad = 110 + grow, bottomPad = 100 + grow;
  const section = el.closest(".section");
  const isFirstRow = section && r.top - section.getBoundingClientRect().top < 120;
  const wantTop = isFirstRow ? Math.min(section.getBoundingClientRect().top + grow, r.top) : r.top;
  let delta = 0;
  if (wantTop < view.top + topPad) delta = wantTop - (view.top + topPad);
  else if (r.bottom > view.bottom - bottomPad) delta = r.bottom - (view.bottom - bottomPad);
  if (delta) gridEl.scrollBy({ top: delta, behavior: instant ? "instant" : "smooth" });
}

function stopPreview() {
  clearTimeout(previewTimer);
  if (previewVideo) {
    previewVideo.pause();
    previewVideo.removeAttribute("src");
    previewVideo.load();
    previewVideo.remove();
    previewVideo = null;
  }
}

function startPreview(el, g) {
  stopPreview();
  if (!g.clip || mode !== "grid") return;
  previewTimer = setTimeout(() => {
    const v = document.createElement("video");
    v.muted = true;
    v.loop = true;
    v.playsInline = true;
    v.preload = "auto";
    v.src = g.clip;
    v.addEventListener("playing", () => v.classList.add("playing"), { once: true });
    el.append(v);
    v.play().catch(() => {});
    previewVideo = v;
  }, PREVIEW_DELAY);
}

// ── navigation ──────────────────────────────────────────────────────

function move(dir) {
  const cur = tiles[focusIdx].getBoundingClientRect();
  const cx = cur.left + cur.width / 2, cy = cur.top + cur.height / 2;
  const vertical = dir === "up" || dir === "down";
  let best = -1, bestScore = Infinity;
  tiles.forEach((el, i) => {
    if (i === focusIdx) return;
    const r = el.getBoundingClientRect();
    const dx = r.left + r.width / 2 - cx, dy = r.top + r.height / 2 - cy;
    const primary = { left: -dx, right: dx, up: -dy, down: dy }[dir];
    if (primary <= 10) return;
    const ortho = vertical ? Math.abs(dx) : Math.abs(dy);
    if (!vertical && ortho > cur.height / 2) return; // left/right stays in the row
    const score = primary + ortho * (vertical ? 0.6 : 3);
    if (score < bestScore) { bestScore = score; best = i; }
  });
  // End of a row: left/right continues into the previous/next row.
  if (best < 0 && dir === "right") best = focusIdx + 1 < tiles.length ? focusIdx + 1 : -1;
  if (best < 0 && dir === "left") best = focusIdx - 1;
  if (best >= 0) setFocus(best);
}

function jumpGroup(step) {
  const sections = [...gridEl.querySelectorAll(".section")];
  const cur = sections.indexOf(tiles[focusIdx].closest(".section"));
  const next = sections[Math.max(0, Math.min(sections.length - 1, cur + step))];
  const first = next.querySelector(".tile");
  if (first) setFocus(Number(first.dataset.idx));
}

// ── detail + launch ─────────────────────────────────────────────────

function openDetail() {
  const g = games[focusIdx];
  const t = typeOf(g);
  stopPreview();
  mode = "detail";
  const card = $("detail");
  card.style.setProperty("--c", t.color);
  $("detail-title").textContent = g.title;
  $("detail-blurb").textContent = g.blurb || "";
  $("detail-type").textContent = t.label;
  $("detail-players").textContent = g.players === 1 ? "1 player · take turns" : `Up to ${g.players} players`;
  $("detail-time").textContent = playtimeText(g);
  $("detail-time").hidden = !playtimeOf(g);
  $("detail-play-label").textContent = g.installed ? "Play" : "Install via Steam";
  const img = $("detail-cover");
  img.src = g.cover || "";
  img.hidden = !g.cover;
  const v = $("detail-video");
  if (g.clip) { v.src = g.clip; v.hidden = false; v.play().catch(() => {}); }
  else { v.removeAttribute("src"); v.hidden = true; }
  card.hidden = false;
}

function closeDetail() {
  const v = $("detail-video");
  v.pause();
  v.removeAttribute("src");
  v.load();
  $("detail").hidden = true;
  mode = "grid";
  startPreview(tiles[focusIdx], games[focusIdx]);
}

function detailStep(step) {
  const i = focusIdx + step;
  if (i < 0 || i >= tiles.length) return;
  setFocus(i);
  stopPreview();
  openDetail();
}

let launchTimer = null;

async function launch() {
  const g = games[focusIdx];
  closeDetail();
  stopPreview();
  mode = "launching";
  $("launching-title").textContent = g.title;
  $("launching-sub").textContent = g.local
    ? "Starting…"
    : g.installed ? "Starting through Steam…" : "Not installed yet: Steam will offer to install it";
  $("launching").hidden = false;
  try {
    await fetch(`/api/launch/${encodeURIComponent(g.id)}`, { method: "POST" });
  } catch {
    $("launching-sub").textContent = "Could not reach the launcher. Is server.py running?";
  }
  clearTimeout(launchTimer);
  launchTimer = setTimeout(endLaunch, LAUNCH_SCREEN);
}

function endLaunch() {
  clearTimeout(launchTimer);
  $("launching").hidden = true;
  mode = "grid";
  startPreview(tiles[focusIdx], games[focusIdx]);
}

// ── idle showcase: slow random tour with (fake) review quotes ───────

let recent = [];
let lastQuote = null;

function startAttract() {
  document.body.classList.add("attract");
  attractStep();
  attractTimer = setInterval(attractStep, ATTRACT_STEP);
}

function stopAttract() {
  if (!attractTimer) return false;
  clearInterval(attractTimer);
  attractTimer = null;
  document.body.classList.remove("attract");
  $("quote").hidden = true;
  return true;
}

function attractStep() {
  // Random, but not one of the last few games shown.
  const pool = tiles.map((_, i) => i).filter((i) => !recent.includes(i));
  const i = pool[Math.floor(Math.random() * pool.length)];
  recent = [...recent, i].slice(-Math.min(8, tiles.length - 1));
  setFocus(i, { noScroll: true });
  // Park the tile in the upper part of the screen; the quote sits below it.
  const view = gridEl.getBoundingClientRect();
  const r = tiles[i].getBoundingClientRect();
  gridEl.scrollBy({ top: r.top + r.height / 2 - (view.top + view.height * 0.36), behavior: "smooth" });
  showQuote(games[i]);
}

function showQuote(g) {
  const options = g.quotes?.length ? g.quotes : [{ q: g.blurb || g.title, by: "The back of the box" }];
  let pick = options[Math.floor(Math.random() * options.length)];
  if (options.length > 1 && pick === lastQuote) pick = options[(options.indexOf(pick) + 1) % options.length];
  lastQuote = pick;

  const box = $("quote");
  box.style.setProperty("--c", typeOf(g).color);
  $("quote-game").textContent = g.title;
  $("quote-meta").textContent = [
    g.players === 1 ? "1 player" : `${g.players} players`,
    playtimeText(g),
  ].filter(Boolean).join(" · ");
  $("quote-text").textContent = pick.q;
  $("quote-by").textContent = `— ${pick.by}`;
  // Restart the entrance animation for every new quote.
  box.hidden = true;
  void box.offsetWidth;
  box.hidden = false;
}

setInterval(() => {
  const idle = performance.now() - lastInput > IDLE_ATTRACT;
  if (!idle || attractTimer || !document.hasFocus()) return;
  if (mode === "detail") closeDetail();
  if (mode === "grid") startAttract();
}, 2_000);

// ── input: one action stream from gamepads, keyboard and mouse ──────

let lastFire = { action: null, src: null, t: 0 };

function fire(action, src) {
  const now = performance.now();
  // Steam's desktop controller layout also turns the d-pad into arrow keys,
  // so the same press can arrive twice: once per source. Drop the echo.
  if (lastFire.action === action && lastFire.src !== src && now - lastFire.t < 200) return;
  lastFire = { action, src, t: now };
  if (now < suppressUntil || !document.hasFocus()) return;

  lastInput = now;
  document.body.classList.toggle("no-cursor", src !== "mouse");
  // The first press after the showcase only wakes the kiosk up.
  if (stopAttract()) {
    scrollToTile(tiles[focusIdx]);
    return;
  }

  if (mode === "grid") {
    if (["up", "down", "left", "right"].includes(action)) move(action);
    else if (action === "select") openDetail();
    else if (action === "prevGroup") jumpGroup(-1);
    else if (action === "nextGroup") jumpGroup(1);
  } else if (mode === "detail") {
    if (action === "select") launch();
    else if (action === "back") closeDetail();
    else if (action === "left") detailStep(-1);
    else if (action === "right") detailStep(1);
  } else if (mode === "launching") {
    if (action === "back") endLaunch();
  }
}

const REPEATABLE = new Set(["up", "down", "left", "right"]);
const held = new Map();

function readPad(p, active) {
  const b = (i) => p.buttons[i]?.pressed;
  const ax = p.axes[0] || 0, ay = p.axes[1] || 0;
  if (b(12) || ay < -0.55) active.add("up");
  if (b(13) || ay > 0.55) active.add("down");
  if (b(14) || ax < -0.55) active.add("left");
  if (b(15) || ax > 0.55) active.add("right");
  if (b(0) || b(9)) active.add("select");   // A / Start
  if (b(1) || b(8)) active.add("back");     // B / Back
  if (b(4)) active.add("prevGroup");        // LB
  if (b(5)) active.add("nextGroup");        // RB
}

// Polled on a timer rather than requestAnimationFrame: rAF is throttled whenever
// the compositor thinks the window is occluded, which drops short taps.
function pollPads() {
  const t = performance.now();
  const active = new Set();
  for (const p of navigator.getGamepads?.() || []) if (p) readPad(p, active);
  for (const a of active) {
    const h = held.get(a);
    if (!h) {
      held.set(a, { since: t, last: t });
      fire(a, "pad");
    } else if (REPEATABLE.has(a) && t - h.since > REPEAT_DELAY && t - h.last > REPEAT_RATE) {
      h.last = t;
      fire(a, "pad");
    }
  }
  for (const a of [...held.keys()]) if (!active.has(a)) held.delete(a);
}

function updatePadStatus() {
  const n = [...(navigator.getGamepads?.() || [])].filter(Boolean).length;
  $("pad-status").textContent = n
    ? `${n} controller${n > 1 ? "s" : ""} connected`
    : "No controller yet: press any button";
}

const KEYS = {
  ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right",
  Enter: "select", " ": "select", Escape: "back", Backspace: "back",
  PageUp: "prevGroup", PageDown: "nextGroup",
};

addEventListener("keydown", (e) => {
  const a = KEYS[e.key];
  if (!a) return;
  e.preventDefault();
  if (e.repeat && !REPEATABLE.has(a)) return;
  fire(a, "key");
});

$("detail").addEventListener("click", (e) => {
  if (e.target.closest("#detail-play")) launch();
  else if (!e.target.closest(".detail-media")) closeDetail();
});
$("launching").addEventListener("click", endLaunch);
addEventListener("mousemove", (e) => {
  if (e.movementX === 0 && e.movementY === 0) return;
  document.body.classList.remove("no-cursor");
  lastInput = performance.now();
  stopAttract();
});
addEventListener("gamepadconnected", updatePadStatus);
addEventListener("gamepaddisconnected", updatePadStatus);

// A game took over: stop videos and the showcase so the game gets the machine.
addEventListener("blur", () => {
  stopAttract();
  stopPreview();
});

// Coming back from a game: swallow the button that got us here, refresh badges.
addEventListener("focus", () => {
  suppressUntil = performance.now() + 600;
  lastInput = performance.now();
  if (mode === "launching") endLaunch();
  load();
  loadPlaytime();
});

// ── clock ───────────────────────────────────────────────────────────

function tick() {
  $("clock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
setInterval(tick, 10_000);
tick();

load().then(() => {
  updatePadStatus();
  loadPlaytime();
  setInterval(loadPlaytime, PLAYTIME_POLL);
  setInterval(pollPads, 16);
});
