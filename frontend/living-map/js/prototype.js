/* ==========================================================================
   Worldwalker — Living Map Prototype
   Architecture test. No frameworks, no network, no AI, no real backend.

     data/*.json  ->  CAMPAIGN STATE
                        |
                        v
                   MAP VIEW MODEL     (markers / washes / routes to draw)
                        |
                        v
                   MAP RENDERER       (soft influence washes + HTML markers + SVG routes)
                        |
                        v
                    VISIBLE MAP

   The player is allowed to SEE the living world. The simulation only carries
   INFORMATION QUALITY (information_status: confirmed | rumored | unconfirmed |
   unknown_identity) plus a plain activity `status`. Nothing is hidden from the
   player because their character hasn't personally learned about it.

   Political geography is a restrained grand-strategy overlay: low-opacity
   influence washes centred on each faction, plus clean labels. No hard
   polygon borders. The Naruto artwork stays dominant.
   ========================================================================== */

"use strict";

/* ----------------------------------------------------------------------
   tiny utils
   ---------------------------------------------------------------------- */
const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const el = (t, c, h) => { const n = document.createElement(t); if (c) n.className = c; if (h != null) n.innerHTML = h; return n; };
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const monogram = (t, accent, size) =>
  `<span class="monogram"${size ? ` data-size="${size}"` : ""} style="--accent:${accent || "var(--gold)"}">${esc(t)}</span>`;

function toast(msg, warn) {
  const t = el("div", "toast" + (warn ? " warn" : ""), esc(msg));
  $("#toastStack").appendChild(t);
  setTimeout(() => { t.style.transition = "opacity .4s"; t.style.opacity = "0"; }, 3800);
  setTimeout(() => t.remove(), 4300);
}

/* ----------------------------------------------------------------------
   loaded data + live state
   ---------------------------------------------------------------------- */
const TH = { regional: 2.0, local: 4.0 };      // scale thresholds for semantic zoom
const CAM = { min: 1, max: 9 };
const AUTO_DAYS_PER_SEC = 0.6;                  // accelerated prototype travel

const state = {
  day: 1, era: "", season: "",
  mode: "political",
  camera: { s: 1, px: 0, py: 0, ts: 1, tpx: 0, tpy: 0 },
  _band: "world",

  regions: {}, factions: {}, dangerColors: {}, relationshipColors: {},
  player: null, npcs: {}, locations: {}, groups: {}, features: {}, worldEvents: {},
  transients: {}, routes: {}, relationships: {}, canon: {},
  moves: {},            // id -> { routeId, durationDays, progress, vprogress, status, auto, from, to, meta }
  scenarios: {},

  worldState: { konohaTension: 1, rootKnowledge: 0 },
  risks: [],
  chronicle: [],
  chronFilter: "all",
  selection: { kind: null, id: null },
  inspector: { tab: "sel" },

  _visKey: "",
  _arrivedQueue: [],
};

/* ----------------------------------------------------------------------
   CHRONICLE
   ---------------------------------------------------------------------- */
const CHRON_GLYPH = {
  action: "✦", world: "◈", relationship: "❧", training: "⚑", travel: "➹",
  mission: "✉", intrigue: "◉", canon: "☯", development: "❖", report: "❂",
  political: "⚑", combat: "⚔", player: "✦",
};
function chron(type, text) { state.chronicle.unshift({ day: state.day, type, text }); }

function renderChronicle() {
  const list = $("#chronicleList");
  const f = state.chronFilter;
  const mine = ["action", "training", "travel", "relationship", "intrigue", "mission", "report"];
  const rows = state.chronicle.filter((e) =>
    f === "all" ? true :
    f === "mine" ? mine.includes(e.type) :
    f === "world" ? (e.type === "world" || e.type === "development" || e.type === "political") :
    f === "canon" ? e.type === "canon" : true
  );
  const nw = state._newChronKeys || new Set();
  const dayWord = state.sourceKey === "live" || state.sourceKey === "real" ? "Turn" : "Day";
  list.innerHTML = rows.map((e) => `
    <li class="chron-entry${nw.has(chronKey(e)) ? " ce-new" : ""}" data-type="${e.type}">
      <span class="ce-glyph">${CHRON_GLYPH[e.type] || "•"}</span>
      <span class="ce-body"><span class="ce-type">${e.type}</span>${esc(e.text)}</span>
      <span class="ce-day">${e.day ? dayWord + " " + e.day : ""}</span>
    </li>`).join("");
  // one-shot: clear the "new" flags after they've been shown once
  if (nw.size) setTimeout(() => { state._newChronKeys = new Set(); }, 1800);
}

/* ======================================================================
   EVENT SYSTEM  —  one state transition drives BOTH map and Chronicle
   ====================================================================== */
const REDUCERS = {
  day_advanced(ev) {
    state.day = ev.day;
    const g = state.primaryCanon;
    if (g && !g.triggered) {
      g.daysOut -= 1;
      if (g.daysOut <= 0) applyEvent({ type: "canon_event_triggered" });
    }
    Object.entries(state.moves).forEach(([id, m]) => {
      if (m.status !== "active") return;
      const nextProgress = clamp(m.progress + 1 / m.durationDays, 0, 1);
      m._animFrom = m.vprogress;
      m._animTo = nextProgress;
      m._animStarted = performance.now();
      m._animDuration = clamp(520 + Math.abs(nextProgress - m.vprogress) * 1100, 620, 1250);
      m.progress = nextProgress;
    });
    Object.values(state.transients).forEach((t) => { if (t.expiresDay && state.day > t.expiresDay) t._gone = true; });
    Object.keys(state.transients).forEach((k) => { if (state.transients[k]._gone) delete state.transients[k]; });
  },

  entity_move_started(ev) {
    const route = state.routes[ev.routeId];
    if (route) route.status = "active";
    state.moves[ev.entityId] = {
      routeId: ev.routeId, durationDays: ev.durationDays || 4,
      progress: ev.progress || 0, vprogress: ev.progress || 0,
      status: "active", auto: !!ev.auto, from: ev.from, to: ev.to,
      meta: { covert: !!ev.covert, risk: ev.risk || "Low", kind: route ? route.kind : null },
    };
    if (ev.entityId === state.player.id) state.player.status = ev.covert ? "Traveling covertly" : "Traveling";
  },

  entity_arrived(ev) {
    const m = state.moves[ev.entityId];
    if (m) { const route = state.routes[m.routeId]; if (route) route.status = "completed"; }
    delete state.moves[ev.entityId];
    if (ev.entityId === state.player.id) {
      state.player.status = "In residence";
      if (ev.at) { state.player.homeLocation = ev.at; state.player.loc = ev.at; }
      const loc = state.locations[ev.at];
      if (loc) { state.player.x = loc.x; state.player.y = loc.y; }
    } else {
      const ent = state.npcs[ev.entityId] || state.groups[ev.entityId];
      const loc = state.locations[ev.at];
      if (ent && loc) { ent.x = loc.x; ent.y = loc.y; ent.status = "Arrived at " + loc.name; }
    }
  },

  /* information quality only — never moves an entity out of view */
  info_updated(ev) {
    const ent = state.npcs[ev.entityId] || state.groups[ev.entityId] ||
                state.features[ev.entityId] || state.worldEvents[ev.entityId] || state.transients[ev.entityId];
    if (!ent) return;
    if (ev.infoStatus) ent.infoStatus = ev.infoStatus;
    if (ev.status) ent.status = ev.status;
    if (ev.note != null) ent.infoNote = ev.note;
    if (ev.x != null) ent.x = ev.x;       // the entity genuinely moved / was pinpointed
    if (ev.y != null) ent.y = ev.y;
    ent._pulseUntilDay = state.day + 1;
  },

  region_controller_changed(ev) {
    const r = state.regions[ev.regionId];
    if (!r) return;
    r.controller = ev.newController;
    if (ev.danger) r.danger = ev.danger;
    if (ev.relationship) r.relationship = ev.relationship;
  },

  region_danger_changed(ev) {
    const r = state.regions[ev.regionId];
    if (r) r.danger = ev.level;
  },

  world_event_started(ev) {
    const e = state.worldEvents[ev.eventId] || state.features[ev.eventId];
    if (!e) return;
    e.status = ev.status || "active";
    if (ev.infoStatus) e.infoStatus = ev.infoStatus;
    if (ev.note) e.infoNote = ev.note;
    e._pulseUntilDay = state.day + 1;
  },

  world_event_resolved(ev) {
    const e = state.worldEvents[ev.eventId] || state.features[ev.eventId];
    if (e) e.status = "resolved";
  },

  feature_discovered(ev) {
    const f = state.features[ev.featureId];
    if (!f || !f.discovery) return;
    f.name = f.discovery.name;
    f.importance = f.discovery.importance || f.importance;
    f.inspector = { summary: f.discovery.summary };
    f.status = "identified";
    f.infoStatus = "confirmed";
    f.infoNote = "Identified";
    f._pulseUntilDay = state.day + 1;
  },

  canon_event_triggered() {
    const g = state.primaryCanon;
    if (!g) return;
    g.triggered = true; g.daysOut = 0; g.triggeredDay = state.day;
    REDUCERS.region_danger_changed({ regionId: g.impactRegion, level: g.impactDanger || "critical" });
    const risk = `${g.name} is unfolding at ${g.locationRaw || locName(g.impactRegion)}`;
    if (!state.risks.includes(risk)) state.risks.push(risk);
    focusOn(g.x, g.y, 2.0);
  },

  training_thread_started() {
    rel("kakashi", +3);
    state.relationships.kakashi.sub = "Squad instructor · evaluating you";
    addGoal("Prove advanced Lightning Release control", "training", "Kakashi is watching");
    state.worldEvents.kakashi_training = {
      id: "kakashi_training", type: "training", name: "Training — Kakashi & Ren",
      x: 0.505, y: 0.523, parent: "konoha", region: "land_of_fire",
      scope: "local", importance: "medium", status: "active", infoStatus: "confirmed",
      inspector: { summary: "Kakashi is putting your Lightning Release through supervised control drills at Training Ground Three." },
      _pulseUntilDay: state.day + 1,
    };
    chron("relationship", "Kakashi Hatake +3 (now " + state.relationships.kakashi.score + ").");
  },

  investigation_started() {
    state.worldState.konohaTension = Math.min(5, state.worldState.konohaTension + 1);
    state.worldState.rootKnowledge += 1;
    rel("danzo", -2);
    state.relationships.danzo.sub = "Root · aware of you";
    const g = state.player.goals.find((x) => x.text === "Investigate Root activity");
    if (g) g.note = "Active · lead: unsigned requisitions";
    addGoal("Identify the unclaimed requisition seal", "intrigue", "From Root inquiry");
    state.worldEvents.root_inquiry = {
      id: "root_inquiry", type: "investigation", name: "Root Inquiry — discreet",
      x: 0.452, y: 0.482, parent: "konoha", region: "land_of_fire",
      scope: "local", importance: "medium", status: "active", infoStatus: "confirmed",
      inspector: { summary: "You are quietly cross-referencing duty rosters and requisitions against a seal no office will claim." },
    };
    chron("world", "Village tension rises to " + state.worldState.konohaTension + "/5 — someone noticed the questions.");
  },

  time_skipped(ev) {
    const days = ev.days || 21;
    state.player.chakraControl = Math.min(100, state.player.chakraControl + 7);
    state.player.chakra.cur = state.player.chakra.max;
    const i = state.player.abilities.indexOf("Lightning Release (basics)");
    if (i >= 0) state.player.abilities[i] = "Lightning Release (developing)";
    const picks = shuffle(WORLD_DEVS.slice()).slice(0, 2);
    picks.forEach((d) => { chron(d.type, d.text + " (while you trained)"); if (d.spawn) d.spawn(); });
    for (let n = 0; n < days; n++) REDUCERS.day_advanced({ day: state.day + 1 });
    chron("training", "Twenty-one days of chakra-control drills. Your Lightning Release stopped scattering.");
    chron("training", "Chakra control +7 (now " + state.player.chakraControl + "). Reserves fully recovered.");
  },
};

const CHRONICLE_FOR = {
  entity_move_started: (ev) => {
    if (ev.silent) return null;
    if (ev.entityId === state.player.id)
      return { type: "travel", text: ev.covert
        ? `Left ${locName(ev.from)} covertly at dusk — no papers filed. Destination: ${locName(ev.to)}.`
        : `Set out from ${locName(ev.from)} for ${locName(ev.to)}.` };
    return { type: "world", text: `${entName(ev.entityId)} is on the move toward ${locName(ev.to)}.` };
  },
  entity_arrived: (ev) => ev.entityId === state.player.id
    ? { type: "travel", text: `Arrived in ${locName(ev.at)} after a covert crossing.` }
    : { type: "world", text: `${entName(ev.entityId)} reached ${locName(ev.at)}.` },
  info_updated: (ev) => ev.chronicle ? { type: "report", text: ev.chronicle } : null,
  region_controller_changed: (ev) => ev.chronicle ? { type: "political", text: ev.chronicle } : null,
  region_danger_changed: (ev) => ev.chronicle ? { type: "world", text: ev.chronicle } : null,
  world_event_started: (ev) => ev.chronicle ? { type: "world", text: ev.chronicle } : null,
  feature_discovered: (ev) => ev.chronicle ? { type: "development", text: ev.chronicle } : null,
  canon_event_triggered: () => ({ type: "canon", text: (state.scenarios.gaara_trigger || {}).chronicle
    || `CANON — ${(state.primaryCanon || {}).name || "A major canon event"} unfolds, with or without you.` }),
  training_thread_started: () => ({ type: "training", text: "Kakashi agreed to evaluate your Lightning Release control at Training Ground Three." }),
  investigation_started: () => ({ type: "intrigue", text: "Began quietly mapping Root's movements inside the village. Danzō -2." }),
  time_skipped: () => null,
  day_advanced: () => null,
};

function applyEvent(ev) {
  (REDUCERS[ev.type] || (() => {}))(ev);
  const c = CHRONICLE_FOR[ev.type] && CHRONICLE_FOR[ev.type](ev);
  if (c) chron(c.type, c.text);
}

/** public dispatch: apply, drain queued arrivals, then refresh everything affected. */
function dispatch(ev) {
  applyEvent(ev);
  let q = state._arrivedQueue; state._arrivedQueue = [];
  while (q && q.length) {
    q.forEach((a) => applyEvent({ type: "entity_arrived", entityId: a.id, at: a.to }));
    q = state._arrivedQueue; state._arrivedQueue = [];
  }
  renderTimeline();
  renderPlayerPanel();
  renderChronicle();
  renderInspector();
  refreshRegions();
  refreshRoutes();
  rebuildMarkers();
  kick();
}

/* helpers used by reducers -------------------------------------------- */
function rel(id, d) {
  if (!state.relationships[id]) state.relationships[id] = { score: 0, sub: (state.npcs[id] || {}).role || "" };
  state.relationships[id].score += d;
}
function addGoal(text, tag, note) {
  if (state.player.goals.some((g) => g.text === text)) return;
  state.player.goals.push({ text, tag: tag || "ambition", note: note || "New" });
}
function locName(id) { return (state.locations[id] || {}).name || (id ? id : "the field"); }
function entName(id) {
  return (state.npcs[id] || state.groups[id] || state.features[id] || state.worldEvents[id] || state.transients[id] || {}).name || id;
}
function shuffle(a) { for (let i = a.length - 1; i > 0; i--) { const j = (Math.random() * (i + 1)) | 0; [a[i], a[j]] = [a[j], a[i]]; } return a; }

/* living-world developments rolled by "Advance 1 Day" ---------------- */
const WORLD_DEVS = [
  { type: "world", text: "A merchant convoy leaves Konoha for the Land of Tea under light guard.",
    spawn: () => spawnTransient("convoy", { type: "group", name: "Merchant Convoy", x: 0.54, y: 0.63, scope: "regional", importance: "low", days: 3, summary: "Lightly-guarded caravan on the Tea road." }) },
  { type: "development", text: "A diplomatic delegation from the Land of Iron arrives in Konoha.",
    spawn: () => spawnTransient("iron_delegation", { type: "world_event", name: "Iron Delegation", x: 0.49, y: 0.482, parent: "konoha", scope: "regional", importance: "medium", days: 4, summary: "Envoys of the Land of Iron are guests of the Hokage this week." }) },
  { type: "world", text: "Rumours spread through the markets about Akatsuki activity near the western borders.",
    spawn: () => { const e = state.worldEvents.akatsuki_suna; if (e) { e.infoNote = "Multiple market rumours"; e._pulseUntilDay = state.day + 1; } } },
  { type: "development", text: "Naruto begins a fresh training period under Kakashi and Yamato.",
    spawn: () => spawnTransient("naruto_arc", { type: "training", name: "Naruto: new training", x: 0.5, y: 0.523, parent: "konoha", scope: "local", importance: "low", days: 6, summary: "Naruto and Yamato have booked Training Ground Three for a wind-nature push." }) },
  { type: "world", text: "Sunagakure formally requests additional border patrols along the Land of Rivers.",
    spawn: () => spawnTransient("suna_request", { type: "mission", name: "Suna: patrol request", x: 0.2, y: 0.6, scope: "regional", importance: "medium", days: 8, summary: "The Sand asks the Leaf to reinforce the shared frontier." }) },
];
function spawnTransient(id, o) {
  state.transients[id] = {
    id, type: o.type, name: o.name, x: o.x, y: o.y, parent: o.parent || null,
    region: o.region || null, scope: o.scope || "regional", importance: o.importance || "low",
    status: "active", infoStatus: "confirmed", expiresDay: state.day + (o.days || 3),
    inspector: { summary: o.summary || "" }, _pulseUntilDay: state.day + 1,
  };
}

/* ======================================================================
   CAMERA + PROJECTION
   ====================================================================== */
let stageEl, scalerEl, regionSvg, routeSvg, markerLayer, washLayer;
let _lastStageSize = { W: 900, H: 675 };
function stageSize() {
  const w = stageEl.clientWidth, h = stageEl.clientHeight;
  if (w > 10 && h > 10) _lastStageSize = { W: w, H: h };
  return _lastStageSize;
}
function clampCamera() {
  const { W, H } = stageSize(), c = state.camera;
  c.s = clamp(c.s, CAM.min, CAM.max);
  c.px = clamp(c.px, W - W * c.s, 0);
  c.py = clamp(c.py, H - H * c.s, 0);
  c.ts = clamp(c.ts, CAM.min, CAM.max);
  c.tpx = clamp(c.tpx, W - W * c.ts, 0);
  c.tpy = clamp(c.tpy, H - H * c.ts, 0);
}
function applyScalerTransform() {
  const c = state.camera;
  scalerEl.style.transform = `translate(${c.px}px, ${c.py}px) scale(${c.s})`;
}
function screenOf(nx, ny) {
  const { W, H } = stageSize(), c = state.camera;
  return { x: c.px + nx * W * c.s, y: c.py + ny * H * c.s };
}
function focusOn(nx, ny, targetScale) {
  const { W, H } = stageSize(), c = state.camera;
  c.ts = clamp(targetScale != null ? targetScale : c.s, CAM.min, CAM.max);
  c.tpx = W / 2 - nx * W * c.ts;
  c.tpy = H / 2 - ny * H * c.ts;
  clampCamera();
  kick();
}
function bandFor(s) { return s < TH.regional ? "world" : s < TH.local ? "regional" : "local"; }
function updateBand() {
  const b = bandFor(state.camera.s);
  const changed = b !== state._band;
  state._band = b;
  washLayer.dataset.band = b;
  markerLayer.dataset.band = b;
  if (changed) updateZoomPill();
  return changed;
}

/* ======================================================================
   MAP VIEW MODEL — world information stays visible, but live individual
   positions require a meaningful player tie or shared group membership.
   ====================================================================== */
function npcIsTrackable(n) {
  if (!n) return false;
  if (typeof n._mapTrackEligible === "boolean") return n._mapTrackEligible;
  if (n.trackOnMap || n.companion || n.partyMember || n.teamMember || n.sharedOrganization) return true;
  const rel = state.relationships && state.relationships[n.id];
  return !!rel && Math.abs(Number(rel.score) || 0) >= 20;
}

function buildMarkers() {
  const out = [];
  const P = state.player;

  out.push({ id: P.id, kind: "player", type: "player", name: P.name, x: P.x, y: P.y,
    importance: "critical", scope: "world", infoStatus: "confirmed", pulse: "none", selectable: true });

  Object.values(state.locations).forEach((l) => {
    out.push({ id: l.id, kind: "location", type: l.type === "village" ? "village" : "landmark",
      name: l.name, x: l.x, y: l.y, importance: l.importance || (l.type === "village" ? "high" : "low"),
      scope: l.scope || (l.type === "village" ? "world" : "local"), infoStatus: "confirmed", pulse: "none", selectable: true });
  });

  Object.values(state.npcs).forEach((n) => {
    if (!npcIsTrackable(n)) return;
    if (n._unmapped) return;                                  // real mode: no resolvable location -> inspector only
    const x = n.x != null ? n.x : n.trueX, y = n.y != null ? n.y : n.trueY;
    if (x == null || y == null) return;
    out.push({ id: n.id, kind: "npc", type: "npc", name: n.name, x, y,
      importance: n.importance || "medium", scope: n.scope || "local",
      infoStatus: n.infoStatus || "confirmed", note: n.infoNote, status: n.status,
      pulse: pulseState(n), selectable: true });
  });

  Object.values(state.groups).forEach((g) => {
    let x = g.x != null ? g.x : g.trueX, y = g.y != null ? g.y : g.trueY;
    const m = state.moves[g.id];
    if (m) { const p = sampleRoute(state.routes[m.routeId].points, m.vprogress); x = p.x; y = p.y; }
    out.push({ id: g.id, kind: "group", type: "group", name: g.name, x, y,
      importance: g.importance || "medium", scope: g.scope || "regional",
      infoStatus: g.infoStatus || "confirmed", note: g.infoNote, status: g.status,
      pulse: pulseState(g), selectable: true });
  });

  Object.values(state.features).forEach((f) => {
    if (f.status === "dormant") return;      // the event hasn't occurred in the sim yet
    out.push({ id: f.id, kind: "feature", type: f.type === "hideout" ? "hideout" : (f.type || "world_event"),
      name: f.name, x: f.x, y: f.y, importance: f.importance || "medium", scope: f.scope || "regional",
      infoStatus: f.infoStatus || "confirmed", note: f.infoNote, status: f.status,
      pulse: pulseState(f), selectable: true });
  });

  [...Object.values(state.worldEvents), ...Object.values(state.transients)].forEach((e) => {
    if (e.status === "dormant" || e.status === "resolved") return;
    out.push({ id: e.id, kind: state.worldEvents[e.id] ? "worldEvent" : "transient",
      type: e.type || "world_event", name: e.name, x: e.x, y: e.y,
      importance: e.importance || "low", scope: e.scope || "regional",
      infoStatus: e.infoStatus || "confirmed", note: e.infoNote, status: e.status,
      pulse: pulseState(e), selectable: true });
  });

  const g = state.primaryCanon;
  if (g && g.id !== "none" && (g.locResolved !== false)) {
    const active = g.triggered;
    out.push({ id: "primary_canon", kind: "canon", type: active ? "canon_event" : "canon_pending",
      name: g.name, x: g.x, y: g.y, importance: active ? "critical" : "high", scope: "world",
      infoStatus: "confirmed", status: active ? "Active" : "Approaching",
      pulse: active ? (state.day <= (g.triggeredDay + (g.activeDays || 5)) ? "strong" : "none") : "gentle",
      selectable: true });
  }

  // LIVE: combat happening in Worldwalker, if its location resolves
  if (state.combat && state.combat.active) {
    const cr = window.WorldwalkerStateAdapter.makeResolver(RAW.registry).resolve(state.combat.location || state.player.homeLocationRaw || "");
    const cx = cr.resolved ? cr.x : state.player.x, cy = cr.resolved ? cr.y : state.player.y;
    out.push({ id: "live_combat", kind: "combat", type: "combat", name: "Combat: " + (state.combat.enemy || "active"),
      x: cx + 0.015, y: cy - 0.02, importance: "critical", scope: "world",
      infoStatus: "confirmed", status: "Being resolved in Worldwalker", pulse: "strong", selectable: true });
  }

  Object.values(state.regions).forEach((r) => {
    if (!r.label) return;
    out.push({ id: r.id, kind: "region", type: "region", name: r.name,
      capital: r.capital ? (state.locations[r.capital] || {}).name : null,
      x: r.label[0], y: r.label[1], importance: "high", scope: r.scope || "world",
      stance: r.relationship, infoStatus: "confirmed", pulse: "none", selectable: true,
      sub: r.scope === "regional" });
  });

  return out;
}
function pulseState(e) {
  if (e._pulseUntilDay && state.day <= e._pulseUntilDay && (e.importance === "high" || e.importance === "critical")) return "strong";
  return "none";
}

function filterMarkers(list) {
  const s = state.camera.s, band = state._band, mode = state.mode;
  return list.filter((m) => {
    if (m.kind === "player") return true;

    if (m.type === "region") {
      if (band === "local") return false;
      if (m.sub && band === "world") return false;
      return true;
    }

    if (m.scope === "regional" && s < TH.regional - 0.001) return false;
    if (m.scope === "local" && s < TH.local - 0.001) return false;

    if (band === "world") {
      const big = ["village", "canon_event", "canon_pending"].includes(m.type);
      if (!big && m.importance !== "critical" && m.importance !== "high") return false;
    }
    if (band === "regional" && m.importance === "low" &&
        ["training", "mission", "world_event", "investigation"].includes(m.type)) return false;

    if (mode === "political") {
      if (["world_event", "training", "investigation"].includes(m.type) && m.importance !== "critical") return false;
      if (m.type === "danger" && m.importance === "low") return false;
    }
    if (mode === "relationships") {
      if (["mission", "training", "world_event", "investigation", "group"].includes(m.type)) return false;
    }
    if (mode === "events") {
      if (m.type === "landmark" && band !== "local") return false;
    }
    if (mode === "danger") {
      if (m.type === "training") return false;
      if (m.type === "mission" && m.importance === "low") return false;
    }
    return true;
  });
}

/* ======================================================================
   MAP RENDERER — soft influence / danger washes
   ====================================================================== */
function factionColor(id) { return (state.factions[id] || state.factions.unknown || { color: "#6b6350" }).color; }

function buildRegionSvg() {
  const gradP = Object.entries(state.factions).map(([id, f]) => `
    <radialGradient id="wash_${id}" cx="50%" cy="50%" r="50%">
      <stop offset="0%"  stop-color="${f.color}" stop-opacity="0.42"/>
      <stop offset="52%" stop-color="${f.color}" stop-opacity="0.17"/>
      <stop offset="100%" stop-color="${f.color}" stop-opacity="0"/>
    </radialGradient>`).join("");
  const gradD = Object.entries(state.dangerColors).map(([lvl, c]) => `
    <radialGradient id="wash_danger_${lvl}" cx="50%" cy="50%" r="50%">
      <stop offset="0%"  stop-color="${c}" stop-opacity="0.55"/>
      <stop offset="45%" stop-color="${c}" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="${c}" stop-opacity="0"/>
    </radialGradient>`).join("");
  regionSvg.innerHTML =
    `<defs>
       <filter id="washBlur" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="0.013"/></filter>
       ${gradP}${gradD}
     </defs>
     <g id="washLayer"></g>
     <g id="hitLayer"></g>`;
  washLayer = $("#washLayer", regionSvg);
  const hit = $("#hitLayer", regionSvg);
  Object.values(state.regions).forEach((r) => {
    const poly = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    poly.setAttribute("points", r.polygon.map((p) => p.join(",")).join(" "));
    poly.setAttribute("class", "region-poly");
    poly.dataset.region = r.id;
    poly.addEventListener("click", (e) => { e.stopPropagation(); select("region", r.id); });
    hit.appendChild(poly);
  });
  refreshRegions();
}

function dangerBlobs() {
  const blobs = [];
  const RAD = { moderate: 0.09, high: 0.12, critical: 0.16 };
  Object.values(state.regions).forEach((r) => {
    if (!r.danger || r.danger === "low") return;
    const cap = state.locations[r.capital];
    const at = cap ? [cap.x, cap.y] : r.influence.at;
    blobs.push({ x: at[0], y: at[1], r: RAD[r.danger] || 0.09, level: r.danger });
  });
  [...Object.values(state.features), ...Object.values(state.worldEvents), ...Object.values(state.transients)].forEach((e) => {
    if (e.status !== "active") return;
    if (!["danger", "world_event"].includes(e.type)) return;
    const lvl = e.importance === "high" ? "high" : "moderate";
    blobs.push({ x: e.x, y: e.y, r: e.importance === "high" ? 0.12 : 0.085, level: lvl });
  });
  const g = state.primaryCanon;
  if (g && g.triggered) blobs.push({ x: g.x, y: g.y, r: 0.17, level: "critical" });
  return blobs;
}

function refreshRegions() {
  if (!washLayer) return;
  let blobs = [], kind = "none";
  if (state.mode === "political") {
    kind = "political";
    blobs = Object.values(state.regions).map((r) => ({
      x: r.influence.at[0], y: r.influence.at[1], r: r.influence.r, grad: "wash_" + r.controller, id: r.id,
    }));
  } else if (state.mode === "danger") {
    kind = "danger";
    blobs = dangerBlobs().map((b) => ({ x: b.x, y: b.y, r: b.r, grad: "wash_danger_" + b.level }));
  }
  washLayer.dataset.kind = kind;
  washLayer.dataset.band = state._band;
  washLayer.innerHTML = blobs.map((b) =>
    `<circle cx="${b.x}" cy="${b.y}" r="${b.r}" fill="url(#${b.grad})" filter="url(#washBlur)"${
      b.id && state.selection.kind === "region" && state.selection.id === b.id ? ' class="is-sel"' : ""}/>`).join("");
  $$(".region-poly", regionSvg).forEach((poly) =>
    poly.classList.toggle("is-selected", state.selection.kind === "region" && state.selection.id === poly.dataset.region));
}

/* routes ------------------------------------------------------------- */
function buildRouteSvg() {
  routeSvg.innerHTML = "";
  Object.values(state.routes).forEach((rt) => {
    if (rt.hidden) return;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M " + rt.points.map((p) => p.join(" ")).join(" L "));
    path.setAttribute("class", "route-path " + rt.status + (rt.kind ? " " + rt.kind : ""));
    path.dataset.route = rt.id;
    routeSvg.appendChild(path);
  });
}
function refreshRoutes() {
  $$(".route-path", routeSvg).forEach((p) => {
    const rt = state.routes[p.dataset.route];
    if (rt) p.setAttribute("class", "route-path " + rt.status + (rt.kind ? " " + rt.kind : ""));
  });
}

/* markers ---------------------------------------------------------- */
let _markerEls = new Map();
function rebuildMarkers() {
  const vis = filterMarkers(buildMarkers());
  const key = vis.map((m) => m.id + m.type + m.infoStatus + m.pulse).join("|") + "#" + state.mode +
              "#" + state._band + "#" + state.selection.kind + state.selection.id;
  if (key === state._visKey) { positionMarkers(); return; }
  state._visKey = key;

  const next = new Set(vis.map((m) => m.id));
  _markerEls.forEach((elm, id) => { if (!next.has(id)) { elm.remove(); _markerEls.delete(id); } });

  vis.forEach((m) => {
    let elm = _markerEls.get(m.id);
    const sel = state.selection.kind === m.kind && state.selection.id === m.id;
    const fuzzy = m.infoStatus && m.infoStatus !== "confirmed";
    const cls = `marker marker--${m.type}` +
                (fuzzy ? ` info-${m.infoStatus}` : "") +
                (m.pulse === "strong" ? " pulse-strong" : m.pulse === "gentle" ? " pulse-gentle" : "") +
                (sel ? " is-selected" : "") + (m.sub ? " sub" : "") +
                (m.type === "region" && m.stance ? " stance" : "");
    let html;
    if (m.type === "region") {
      const stanceCol = state.relationshipColors[m.stance] || "var(--parchment)";
      html = `<span class="marker-label rl"${state.mode === "relationships" ? ` style="--stance:${stanceCol}"` : ""}>
        <span class="rl-nation">${esc(m.name)}</span>
        ${m.capital ? `<span class="rl-capital">${esc(m.capital)}</span>` : ""}
      </span>`;
    } else {
      const subLabel = m.infoStatus === "rumored" ? "rumored"
        : m.infoStatus === "unconfirmed" ? "unconfirmed"
        : m.infoStatus === "unknown_identity" ? "unidentified" : "";
      html = `<span class="marker-dot"></span>
        <span class="marker-label">${esc(m.name)}</span>
        ${subLabel ? `<span class="marker-sub">${subLabel}</span>` : ""}`;
    }
    if (!elm) {
      elm = el("button", cls, html);
      elm.dataset.id = m.id; elm.dataset.kind = m.kind;
      elm.addEventListener("click", (e) => { e.stopPropagation(); select(m.kind, m.id); });
      markerLayer.appendChild(elm);
      _markerEls.set(m.id, elm);
    } else {
      elm.className = cls;
      elm.innerHTML = html;
    }
    elm.dataset.x = m.x; elm.dataset.y = m.y;
  });
  positionMarkers();
}
function positionMarkers() {
  const { W, H } = stageSize();
  _markerEls.forEach((elm) => {
    const id = elm.dataset.id, kind = elm.dataset.kind;
    const entity = kind === "player" ? state.player
      : kind === "npc" ? state.npcs[id]
      : kind === "group" ? state.groups[id] : null;
    const x = entity && Number.isFinite(Number(entity.x)) ? Number(entity.x) : +elm.dataset.x;
    const y = entity && Number.isFinite(Number(entity.y)) ? Number(entity.y) : +elm.dataset.y;
    elm.dataset.x = x; elm.dataset.y = y;
    const moving = !!(state.moves && state.moves[id] && state.moves[id].status === "active");
    elm.classList.toggle("is-moving", moving);
    const p = screenOf(x, y);
    if (p.x < -60 || p.x > W + 60 || p.y < -60 || p.y > H + 60) { elm.style.display = "none"; return; }
    elm.style.display = "";
    elm.style.transform = `translate(${p.x}px, ${p.y}px) translate(-50%, -50%)`;
  });
  if (!state.player || !state.moves) return;
  const m = state.moves[state.player.id];
  const tp = $("#travelProgress");
  if (m && tp) tp.textContent = Math.round(m.vprogress * 100) + "%";
}

function sampleRoute(points, t) {
  if (!points || !points.length) return { x: 0, y: 0 };
  if (points.length === 1) return { x: points[0][0], y: points[0][1] };
  const segs = []; let total = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const L = Math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1]);
    segs.push(L); total += L;
  }
  let d = clamp(t, 0, 1) * total;
  for (let i = 0; i < segs.length; i++) {
    if (d <= segs[i] || i === segs.length - 1) {
      const f = segs[i] ? d / segs[i] : 0;
      return { x: points[i][0] + (points[i + 1][0] - points[i][0]) * f,
               y: points[i][1] + (points[i + 1][1] - points[i][1]) * f };
    }
    d -= segs[i];
  }
  return { x: points[points.length - 1][0], y: points[points.length - 1][1] };
}

/* ======================================================================
   ANIMATION LOOP
   ====================================================================== */
let _raf = null, _last = 0;
function kick() { if (!_raf) { _last = performance.now(); _raf = requestAnimationFrame(frame); } }
function frame(ts) {
  const dt = Math.min(0.05, (ts - _last) / 1000); _last = ts;
  let busy = false;

  const c = state.camera;
  const ds = c.ts - c.s, dx = c.tpx - c.px, dy = c.tpy - c.py;
  if (Math.abs(ds) > 0.002 || Math.abs(dx) > 0.4 || Math.abs(dy) > 0.4) {
    const k = Math.min(1, dt * 9);
    c.s += ds * k; c.px += dx * k; c.py += dy * k;
    clampCamera(); busy = true;
  } else { c.s = c.ts; c.px = c.tpx; c.py = c.tpy; }

  const arrived = [];
  Object.entries(state.moves).forEach(([id, m]) => {
    if (m.status !== "active") return;
    if (m.auto && m.progress < 1) { m.progress = clamp(m.progress + dt * AUTO_DAYS_PER_SEC / m.durationDays, 0, 1); busy = true; }
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      m.vprogress = m.progress;
    } else if (m._animStarted != null && m._animTo != null) {
      const t = clamp((ts - m._animStarted) / Math.max(1, m._animDuration || 800), 0, 1);
      const eased = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      m.vprogress = m._animFrom + (m._animTo - m._animFrom) * eased;
      if (t < 1) busy = true;
      else { m.vprogress = m._animTo; delete m._animStarted; delete m._animFrom; delete m._animTo; }
    } else {
      const dp = m.progress - m.vprogress;
      if (Math.abs(dp) > 0.0002) {
        m.vprogress += dp * (1 - Math.exp(-dt * 6.5));
        busy = true;
      } else m.vprogress = m.progress;
    }
    const rt = state.routes[m.routeId];
    if (!rt || !Array.isArray(rt.points) || !rt.points.length) return;
    const p = sampleRoute(rt.points, m.vprogress);
    const ent = id === state.player.id ? state.player : (state.npcs[id] || state.groups[id]);
    if (ent) { ent.x = p.x; ent.y = p.y; }
    if (m.progress >= 1 && m.vprogress >= 0.999 && !m._done) { m._done = true; arrived.push({ id, to: m.to }); }
  });

  applyScalerTransform();
  if (updateBand()) rebuildMarkers(); else positionMarkers();

  arrived.forEach((arrival) => {
    const mv = state.moves[arrival.id];
    if (mv && mv.meta && mv.meta.visual) {
      // a LIVE presentation transition — no campaign bookkeeping, just snap + tidy up
      const rt = state.routes[mv.routeId];
      if (rt) { const end = rt.points[rt.points.length - 1]; state.player.x = end[0]; state.player.y = end[1]; }
      delete state.moves[arrival.id];
      if (mv.routeId === "_live_move") delete state.routes._live_move;
      rebuildMarkers();
    } else {
      dispatch({ type: "entity_arrived", entityId: arrival.id, at: arrival.to });
    }
  });

  if (busy) _raf = requestAnimationFrame(frame);
  else _raf = null;
}

/* ======================================================================
   INTERACTION — wheel zoom, drag pan
   ====================================================================== */
function bindMapInteraction() {
  stageEl.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = stageEl.getBoundingClientRect();
    const cx = e.clientX - rect.left, cy = e.clientY - rect.top, c = state.camera;
    const factor = Math.exp(-e.deltaY * 0.0016);
    const ns = clamp(c.s * factor, CAM.min, CAM.max);
    const lx = (cx - c.px) / c.s, ly = (cy - c.py) / c.s;
    c.s = ns; c.px = cx - lx * ns; c.py = cy - ly * ns;
    c.ts = c.s; c.tpx = c.px; c.tpy = c.py;
    clampCamera(); applyScalerTransform();
    if (updateBand()) rebuildMarkers(); else positionMarkers();
  }, { passive: false });

  let dragging = false, lastX = 0, lastY = 0, moved = 0;
  stageEl.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    dragging = true; moved = 0; lastX = e.clientX; lastY = e.clientY;
    stageEl.classList.add("is-panning"); stageEl.setPointerCapture(e.pointerId);
  });
  stageEl.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    const c = state.camera;
    c.px += e.clientX - lastX; c.py += e.clientY - lastY;
    moved += Math.abs(e.clientX - lastX) + Math.abs(e.clientY - lastY);
    lastX = e.clientX; lastY = e.clientY;
    c.ts = c.s; c.tpx = c.px; c.tpy = c.py;
    clampCamera(); applyScalerTransform(); positionMarkers();
  });
  const end = () => { dragging = false; stageEl.classList.remove("is-panning"); };
  stageEl.addEventListener("pointerup", end);
  stageEl.addEventListener("pointercancel", end);
  stageEl.addEventListener("click", () => { if (moved < 4) select(null, null); });

  new ResizeObserver(() => { clampCamera(); applyScalerTransform(); positionMarkers(); }).observe(stageEl);
}

function updateZoomPill() {
  const b = state._band;
  $("#zoomPill").innerHTML = b === "world" ? "World <span>view</span>"
    : b === "regional" ? "Regional <span>view</span>" : "Local <span>view</span>";
}

/* ======================================================================
   SELECTION + INSPECTOR
   ====================================================================== */
function select(kind, id) {
  state.selection = { kind, id };
  state.inspector.tab = "sel";
  if (kind === "region") { const r = state.regions[id]; if (r && r.label) focusOn(r.label[0], r.label[1], 1.7); }
  else if (kind === "location") {
    const l = state.locations[id];
    if (l) focusOn(l.x, l.y, l.type === "village" ? 4.7 : 6.2);
  } else if (id) {
    const mk = _markerEls.get(id);
    if (mk) {
      const x = +mk.dataset.x, y = +mk.dataset.y, p = screenOf(x, y), { W, H } = stageSize();
      if (p.x < 40 || p.x > W - 40 || p.y < 40 || p.y > H - 40) focusOn(x, y, clamp(state.camera.s, 3.4, 5));
    }
  }
  renderInspector();
  refreshRegions();
  rebuildMarkers();
}

function infoBadge(infoStatus, status, note) {
  const M = {
    confirmed: ["k-known", "◉ Confirmed"],
    rumored: ["k-suspected", "◈ Rumored"],
    unconfirmed: ["k-suspected", "◈ Unconfirmed"],
    unknown_identity: ["k-suspected", "◈ Identity unknown"],
  };
  const [cls, label] = M[infoStatus] || M.confirmed;
  const line = status ? `${label} · ${esc(status)}` : label;
  return `<div class="know-badge ${cls}">${line}</div>` + (note ? `<div class="know-note">“${esc(note)}”</div>` : "");
}
function heroStyle(scene, faction) {
  if (scene) return `background-image:url('${scene}')`;
  const map = { konoha: "#2f5a38", suna: "#7a6238", ame: "#3d4157", kiri: "#356065", kumo: "#5a616b", iwa: "#5a4a3a" };
  return `background:linear-gradient(160deg, ${map[faction] || "#3a2f20"}, #14100b)`;
}

function renderInspector() {
  const box = $("#inspector");
  const tab = state.inspector.tab;
  const tabs = `
    <div class="insp-tabs">
      <button class="insp-tab ${tab !== "world" ? "is-active" : ""}" data-tab="sel">Selected</button>
      <button class="insp-tab ${tab === "world" ? "is-active" : ""}" data-tab="world">World Pulse</button>
    </div>`;
  let body;
  if (tab === "world") body = worldPulseHTML();
  else {
    const s = state.selection;
    body = !s.kind ? `<p class="sc-note" style="margin-top:20px">Select a country, village, marker or person on the map. Different things become selectable at different zoom levels.</p>`
      : s.kind === "player" ? playerInspectorHTML()
      : s.kind === "npc" ? npcInspectorHTML(s.id)
      : s.kind === "location" ? locationInspectorHTML(s.id)
      : s.kind === "region" ? regionInspectorHTML(s.id)
      : s.kind === "feature" ? featureInspectorHTML(s.id)
      : (s.kind === "worldEvent" || s.kind === "transient") ? eventInspectorHTML(s.id)
      : s.kind === "group" ? groupInspectorHTML(s.id)
      : s.kind === "canon" ? canonInspectorHTML()
      : s.kind === "combat" ? combatInspectorHTML()
      : `<p class="sc-note">No inspector for “${esc(s.kind)}”.</p>`;
  }
  box.innerHTML = tabs + body;
  box.scrollTop = 0;
  wireInspector(box);
}

function playerInspectorHTML() {
  const P = state.player, m = state.moves[P.id];
  const vis = m && m.meta && m.meta.visual;
  const travel = !m ? "" : vis ? `
    <div class="sec">
      <div class="know-badge k-suspected">➹ Relocating on the map</div>
      <div class="kv"><span class="kv-k">Now at:</span> <b>${esc(P.homeLocationRaw || locName(P.homeLocation))}</b></div>
      <div class="kv"><span class="kv-k">Source:</span> <b>Live Worldwalker</b></div>
    </div>` : `
    <div class="sec">
      <div class="know-badge k-suspected">➹ ${esc(P.status)}</div>
      <div class="kv"><span class="kv-k">Origin:</span> <b>${esc(locName(m.from))}</b></div>
      <div class="kv"><span class="kv-k">Destination:</span> <b>${esc(locName(m.to))}</b></div>
      <div class="kv"><span class="kv-k">Progress:</span> <b id="travelProgress">${Math.round(m.vprogress * 100)}%</b></div>
      <div class="kv"><span class="kv-k">Risk:</span> <b>${esc(m.meta.risk)}</b></div>
    </div>`;
  return `
    <div class="insp-hero">
      <div style="display:flex;gap:12px;align-items:center">
        ${monogram(P.monogram, "var(--lightning)", "lg")}
        <div>
          <span class="insp-kicker">${esc(P.rank)} · ${esc(P.affiliation)}</span>
          <div class="insp-name" style="font-size:19px">${esc(P.name)}</div>
          <div class="insp-sub">${esc(m ? "en route" : (P.homeLocationRaw || locName(P.homeLocation)))}</div>
        </div>
      </div>
    </div>
    ${P.status && !m ? `<div class="know-badge k-known">◉ ${esc(P.status)}</div>` : ""}
    ${travel}
    ${state.readOnly && P.locResolved === false ? `<div class="know-note">Player location not currently represented on map (placed at map centre).</div>` : ""}
    ${state.readOnly && P.locApprox ? `<div class="know-note">Player position on map is approximate (nearest resolvable place).</div>` : ""}
    <div class="sec">
      <div class="kv"><span class="kv-k">Health:</span> <b>${P.health.cur}/${P.health.max}</b></div>
      <div class="kv"><span class="kv-k">${esc(P.resourceName || "Chakra")}:</span> <b>${P.chakra.cur}/${P.chakra.max}</b></div>
      ${P.chakraControl != null ? `<div class="kv"><span class="kv-k">Chakra control:</span> <b>${P.chakraControl}</b></div>` : ""}
      ${P.powerTier ? `<div class="kv"><span class="kv-k">Power tier:</span> <b>${esc(P.powerTier)}</b></div>` : ""}
    </div>
    ${P.stats ? `<div class="sec"><h3 class="sec-title">Stats</h3>
      <div class="pill-row">${Object.entries(P.stats).map(([k, v]) => `<span class="pill">${esc(k)} ${esc(v)}</span>`).join("")}</div></div>` : ""}
    <div class="sec"><h3 class="sec-title">Abilities</h3>
      <div class="pill-row">${P.abilities.map((a) => `<span class="pill">${esc(a)}</span>`).join("")}</div>
    </div>
    ${state.readOnly
      ? `<p class="sc-note">Read-only mirror of a real Worldwalker campaign. Switch the data source (top bar) back to the demo for interactive behaviour.</p>`
      : `<p class="sc-note">The player can see the living world. The simulation only tracks how <em>reliable</em> each piece of information is.</p>`}`;
}

function npcInspectorHTML(id) {
  const n = state.npcs[id];
  const r = state.relationships[id];
  return `
    <div class="insp-hero">
      <div class="insp-hero-img" style="${heroStyle(n.scene)}"><span class="insp-hero-cap">${esc(n.name)}</span></div>
      <div style="display:flex;gap:12px;align-items:center">
        ${monogram(n.initials, n.accent, "lg")}
        <div>
          <span class="insp-kicker">${esc(n.role)}</span>
          <div class="insp-name" style="font-size:18px">${esc(n.name)}</div>
        </div>
      </div>
    </div>
    ${infoBadge(n.infoStatus || "confirmed", n.status, n.infoNote)}
    ${n._unmapped ? `<div class="know-note">Location not currently represented on map${n._locRaw ? ` (recorded as “${esc(n._locRaw)}”)` : ""}.</div>` : ""}
    <div class="sec">
      <div class="kv"><span class="kv-k">Relationship with you:</span> <b>${r ? r.score : "— (not met)"}</b></div>
      <div class="kv"><span class="kv-k">Recent:</span> ${esc(n.recent)}</div>
    </div>
    ${(n.affiliations && n.affiliations.length) ? `<div class="sec"><h3 class="sec-title">Affiliations</h3>
      <div class="pill-row">${n.affiliations.map((a) => `<span class="pill">${esc(a)}</span>`).join("")}</div></div>` : ""}
    <div class="sec"><h3 class="sec-title">Context</h3>
      <p style="font-size:12.5px;line-height:1.6;color:var(--text-dim);margin:0">${esc(n.bio)}</p>
    </div>
    ${(n.abilities && n.abilities.length) ? `<div class="sec"><h3 class="sec-title">Known Abilities</h3>
      <div class="pill-row">${n.abilities.map((a) => `<span class="pill">${esc(a)}</span>`).join("")}</div></div>` : ""}
    <div class="sec"><h3 class="sec-title">Interact</h3>
      <div class="npc-actions">
        <button class="npc-act" data-na="talk">Talk</button>
        <button class="npc-act" data-na="train">Train</button>
        <button class="npc-act" data-na="favor">Ask Favor</button>
        <button class="npc-act" data-na="travel">Travel With</button>
      </div>
      <p class="sc-note">${state.readOnly
        ? "Read-only campaign mirror — these would route to the Worldwalker engine."
        : `Shortcuts, not the whole list. Type anything you'd try with ${esc(n.name.split(" ")[0])} into the action bar.`}</p>
    </div>`;
}

function locationInspectorHTML(id) {
  const l = state.locations[id];
  if (l.type !== "village") {
    return `
      <div class="insp-hero">
        <span class="insp-kicker">${esc((state.locations[l.parent] || {}).name || "Local site")} · Local</span>
        <div class="insp-name">${esc(l.name)}</div>
        <div class="insp-sub">${esc(l.type)}</div>
      </div>
      <div class="know-badge k-known">◉ Confirmed</div>
      <div class="sec"><p style="font-size:12.5px;line-height:1.6;color:var(--text-dim);margin:0">${esc((l.inspector || {}).summary || "")}</p></div>
      <p class="sc-note">Local sites appear only when you zoom close to Konoha.</p>`;
  }
  const devs = (l.developments || []).map((d) => `<div class="dev-item">${esc(d)}</div>`).join("");
  const here = Object.values(state.npcs).filter((n) =>
    !state.moves[n.id] &&
    (n.trueLocation === id || (state.locations[n.trueLocation] || {}).parent === id));
  return `
    <div class="insp-hero">
      <div class="insp-hero-img" style="${heroStyle(l.scene, l.id)}"><span class="insp-hero-cap">${esc(l.kanji || "")}</span></div>
      <span class="insp-kicker">${esc((state.regions[l.region] || {}).name || "")} · Hidden Village</span>
      <div class="insp-name">${esc(l.name)}</div>
      <div class="insp-sub">${esc(l.short || "")}</div>
    </div>
    <div class="sec">
      <div class="kv"><span class="kv-k">${esc(l.leaderLabel)}:</span> <b>${esc(l.leader)}</b></div>
      <div class="kv"><span class="kv-k">Status:</span> <b>${esc(l.status)}</b></div>
      ${l.id === "konoha" ? `<div class="kv"><span class="kv-k">Village tension:</span> <b>${state.worldState.konohaTension}/5</b></div>` : ""}
    </div>
    <div class="sec"><h3 class="sec-title">Current Developments</h3>${devs}</div>
    ${here.length ? `<div class="sec"><h3 class="sec-title">People here now</h3>${here.map((n) => `
      <div class="rel-row" data-npc="${n.id}">${monogram(n.initials, n.accent, "sm")}
      <div class="rel-meta"><div class="rel-name">${esc(n.name)}</div><div class="rel-sub">${esc(n.status || n.role)}</div></div></div>`).join("")}
      <p class="sc-note">Zoom in to see them on the map.</p></div>` : ""}
    <div class="sec"><h3 class="sec-title">Shortcuts</h3>
      <div class="shortcut-grid">
        <button class="sc-btn" data-sc="people">People</button>
        <button class="sc-btn" data-sc="missions">Missions</button>
        <button class="sc-btn" data-sc="training">Training</button>
        <button class="sc-btn" data-sc="orgs">Organizations</button>
      </div>
      <p class="sc-note">Shortcuts surface common threads. You can still type anything into the action bar.</p>
      <div id="scPanel"></div>
    </div>`;
}

function regionInspectorHTML(id) {
  const r = state.regions[id];
  const fac = state.factions[r.controller] || { name: r.controller, color: "#6b6350" };
  const devs = Object.values({ ...state.worldEvents, ...state.features, ...state.transients })
    .filter((e) => e.region === id && e.status !== "dormant" && e.status !== "resolved")
    .map((e) => `<div class="dev-item">${esc(e.name)}${e.infoStatus && e.infoStatus !== "confirmed" ? " (" + e.infoStatus.replace("_", " ") + ")" : ""}</div>`).join("")
    || `<div class="dev-item">Quiet, for now.</div>`;
  const villages = Object.values(state.locations).filter((l) => l.type === "village" && l.region === id)
    .map((l) => `<button class="sc-btn" data-loc="${l.id}">${esc(l.name)}</button>`).join("");
  return `
    <div class="insp-hero">
      <span class="insp-kicker">${r.scope === "regional" ? "Sub-region" : "Great Nation"}</span>
      <div class="insp-name">${esc(r.name)} <span style="font-size:14px;color:var(--text-faint)">${esc(r.kanji || "")}</span></div>
    </div>
    <div class="insp-statline">
      <span class="stat-chip"><span class="dot" style="background:${fac.color}"></span>Controller <b>${esc(fac.name)}</b></span>
      <span class="stat-chip"><span class="dot" style="background:${state.dangerColors[r.danger] || "#5a9e63"}"></span>Danger <b>${esc(r.danger)}</b></span>
      <span class="stat-chip"><span class="dot" style="background:${state.relationshipColors[r.relationship] || "#7a715c"}"></span>Toward you <b>${esc(r.relationship)}</b></span>
    </div>
    ${villages ? `<div class="sec"><h3 class="sec-title">Villages</h3><div class="shortcut-grid">${villages}</div></div>` : ""}
    <div class="sec"><h3 class="sec-title">Developments here</h3>${devs}</div>
    <p class="sc-note">Region control, danger and stance are data. Political mode shows them as a soft influence wash — the artwork is never covered.</p>`;
}

function featureInspectorHTML(id) {
  const f = state.features[id];
  return `
    <div class="insp-hero">
      <span class="insp-kicker">Map feature · ${esc(f.type)}</span>
      <div class="insp-name">${esc(f.name)}</div>
      <div class="insp-sub">${esc((state.regions[f.region] || {}).name || "")}</div>
    </div>
    ${infoBadge(f.infoStatus || "confirmed", f.status, f.infoNote)}
    <div class="sec"><p style="font-size:12.5px;line-height:1.6;color:var(--text-dim);margin:0">${esc((f.inspector || {}).summary || "")}</p></div>
    ${f.status !== "identified" && f.discovery ? `<p class="sc-note">Investigate this feature to learn what it really is. (Director → “Investigate Unknown Hideout”, or just type it.)</p>` : ""}`;
}

function eventInspectorHTML(id) {
  const e = state.worldEvents[id] || state.transients[id];
  return `
    <div class="insp-hero">
      <span class="insp-kicker">${esc(String(e.type).replace("_", " "))} · ${esc(e.importance)} importance</span>
      <div class="insp-name">${esc(e.name)}</div>
      <div class="insp-sub">${esc((state.regions[e.region] || {}).name || (state.locations[e.parent] || {}).name || "")}</div>
    </div>
    ${infoBadge(e.infoStatus || "confirmed", e.status, e.infoNote)}
    <div class="sec"><p style="font-size:12.5px;line-height:1.6;color:var(--text-dim);margin:0">${esc((e.inspector || {}).summary || "")}</p></div>
    ${e.expiresDay ? `<div class="sec"><div class="kv"><span class="kv-k">Expires:</span> <b>~Day ${e.expiresDay}</b></div></div>` : ""}
    <p class="sc-note">Not every event matters equally. Importance + zoom + map mode decide whether it is drawn.</p>`;
}

function groupInspectorHTML(id) {
  const g = state.groups[id] || state.transients[id];
  const m = state.moves[id];
  return `
    <div class="insp-hero">
      <span class="insp-kicker">Group · ${esc(g.faction || "unaligned")}</span>
      <div class="insp-name">${esc(g.name)}</div>
    </div>
    ${infoBadge(g.infoStatus || "confirmed", g.status, g.infoNote)}
    <div class="sec"><p style="font-size:12.5px;line-height:1.6;color:var(--text-dim);margin:0">${esc((g.inspector || {}).summary || "")}</p></div>
    ${m ? `<div class="sec">
      <div class="kv"><span class="kv-k">Route:</span> <b>${esc(m.routeId)}</b></div>
      <div class="kv"><span class="kv-k">Progress:</span> <b>${Math.round(m.vprogress * 100)}%</b></div>
    </div>` : ""}
    <p class="sc-note">The group is shown on the map even if the player hasn't met it — only its identity is marked uncertain when it is.</p>`;
}

function canonImg(g) {
  return `assets/canon/${(g && g.banner) ? g.banner : "gaara_rescue"}_v1.webp`;
}
function combatInspectorHTML() {
  const c = state.combat || {};
  return `
    <div class="insp-hero">
      <div class="insp-hero-img" style="background-image:url('assets/scenes/battlefield_dusk.webp');height:96px"><span class="insp-hero-cap">Combat</span></div>
      <span class="insp-kicker">Live · Worldwalker</span>
      <div class="insp-name">Combat active</div>
      <div class="insp-sub">${esc(c.location || "current location")}</div>
    </div>
    <div class="know-badge k-suspected">⚔ Being resolved in Worldwalker</div>
    <div class="sec">
      <div class="kv"><span class="kv-k">Opponent:</span> <b>${esc(c.enemy || "—")}</b></div>
      ${c.round ? `<div class="kv"><span class="kv-k">Round:</span> <b>${c.round}</b></div>` : ""}
      <div class="kv"><span class="kv-k">Player HP:</span> <b>${state.player.health.cur}/${state.player.health.max}</b></div>
    </div>
    <p class="sc-note">The Living Map only shows that a fight is underway. Resolve it in Worldwalker — the tactical screen is not connected in this milestone.</p>`;
}

function canonInspectorHTML() {
  const g = state.primaryCanon;
  const st = g.triggered ? "UNFOLDING NOW" : g.daysOut <= 3 ? "imminent" : "approaching";
  return `
    <div class="insp-hero">
      <div class="insp-hero-img" style="background-image:url('${canonImg(g)}');height:96px"><span class="insp-hero-cap">${esc(g.name)}</span></div>
      <span class="insp-kicker">Canon event${g.locationRaw ? " · " + esc(g.locationRaw) : ""}</span>
    </div>
    <div class="know-badge ${g.triggered ? "k-suspected" : "k-known"}">☯ ${st}</div>
    <div class="sec">
      <div class="kv"><span class="kv-k">Estimated:</span> <b>${g.triggered ? "active" : "~" + g.daysOut + " days out"}</b></div>
      ${g.triggered ? `<div class="kv"><span class="kv-k">Since:</span> <b>Day ${g.triggeredDay}</b></div>` : ""}
    </div>
    ${g.summary ? `<div class="sec"><p style="font-size:12px;line-height:1.6;color:var(--text-dim);margin:0">${esc(g.summary)}</p></div>` : ""}
    <p class="sc-note">Canon history advances on its own timeline. When it fires, its region's danger and this marker respond whether or not the player took part.</p>`;
}

function worldPulseHTML() {
  const g = state.primaryCanon;
  const st = g.triggered ? "unfolding now" : g.daysOut <= 3 ? "imminent" : "approaching";
  const riskLines = (state.combat && state.combat.active
    ? [`Combat active${state.combat.location ? " at " + state.combat.location : ""} — being resolved in Worldwalker`] : [])
    .concat(state.risks || []);
  const risks = riskLines.length
    ? riskLines.map((r) => `<div class="risk-item"><span class="risk-dot"></span>${esc(r)}</div>`).join("")
    : `<p style="font-size:11.5px;color:var(--text-faint);font-style:italic">No active risk indicators.</p>`;
  const log = state.chronicle.filter((e) => ["world", "development", "canon", "political"].includes(e.type)).slice(0, 9)
    .map((e) => `<div class="dev-item">${esc(e.text)} <small style="color:var(--text-faint)">(Day ${e.day})</small></div>`).join("")
    || `<p style="font-size:11.5px;color:var(--text-faint);font-style:italic">Quiet so far. Advance a day.</p>`;
  return `
    <div class="sec"><h3 class="sec-title">Canon Timeline</h3>
      <div class="insp-hero-img" style="background-image:url('${canonImg(g)}');height:84px;margin-bottom:8px"><span class="insp-hero-cap" style="font-size:13px">${esc(g.name)}</span></div>
      <div class="kv"><span class="kv-k">Status:</span> <b>${st}</b></div>
      <div class="kv"><span class="kv-k">Estimated:</span> <b>${g.triggered ? "active" : "~" + g.daysOut + " days out"}</b></div>
      ${g.locationRaw ? `<div class="kv"><span class="kv-k">Location:</span> <b>${esc(g.locationRaw)}</b></div>` : ""}
      <p class="sc-note">Canon events keep approaching whether or not the player takes part.</p>
    </div>
    ${state.firedCanon && state.firedCanon.length ? `<div class="sec"><h3 class="sec-title">Canon Events Fired</h3>${
      state.firedCanon.slice().reverse().map((e) => `<div class="dev-item">${esc(e.title)}${e.day ? ` <small style="color:var(--text-faint)">(canon day ${e.day})</small>` : ""}</div>`).join("")}</div>` : ""}
    <div class="sec"><h3 class="sec-title">Risk Indicators</h3>${risks}</div>
    <div class="sec"><h3 class="sec-title">World Developments</h3>${log}</div>`;
}

function wireInspector(box) {
  $$(".insp-tab", box).forEach((t) => t.addEventListener("click", () => { state.inspector.tab = t.dataset.tab; renderInspector(); }));
  $$("[data-npc]", box).forEach((r) => r.addEventListener("click", () => select("npc", r.dataset.npc)));
  $$("[data-loc]", box).forEach((b) => b.addEventListener("click", () => select("location", b.dataset.loc)));
  $$(".sc-btn[data-sc]", box).forEach((b) => b.addEventListener("click", () => locShortcut(b.dataset.sc)));
  $$(".npc-act", box).forEach((b) => b.addEventListener("click", () => npcAction(b.dataset.na)));
}

function locShortcut(kind) {
  const l = state.locations[state.selection.id];
  const panel = $("#scPanel"); if (!panel || !l) return;
  if (kind === "people") {
    panel.innerHTML = (l.people || []).map((pid) => {
      const n = state.npcs[pid]; if (!n) return "";
      return `<div class="rel-row" data-npc="${pid}">${monogram(n.initials, n.accent, "sm")}
        <div class="rel-meta"><div class="rel-name">${esc(n.name)}</div><div class="rel-sub">${esc(n.status || n.role)}</div></div></div>`;
    }).join("") || `<p class="sc-note">No known contacts here yet.</p>`;
    $$("[data-npc]", panel).forEach((r) => r.addEventListener("click", () => select("npc", r.dataset.npc)));
  } else if (kind === "missions") {
    panel.innerHTML = `<div class="dev-item">Border Patrol — Land of Rivers frontier (available)</div>
      <div class="dev-item">Courier run — sealed dispatch to the daimyō (D-rank)</div>
      <div class="dev-item">Escort — merchant convoy toward the Land of Tea</div>
      <p class="sc-note">Or type your own approach: “take the border patrol but scout for Root couriers.”</p>`;
  } else if (kind === "training") {
    panel.innerHTML = `<div class="dev-item">Training Ground Three — open. Kakashi is sometimes here after morning drills.</div>
      <button class="sc-btn" style="margin-top:8px" id="scTrainKakashi">Ask Kakashi to evaluate your Lightning Release</button>`;
    $("#scTrainKakashi").addEventListener("click", runDemoA);
  } else if (kind === "orgs") {
    panel.innerHTML = (l.orgs || []).map((o) => {
      const root = /root/i.test(o);
      return `<div class="dev-item">${esc(o)}${root ? ` &nbsp;<button class="sc-btn" style="padding:2px 8px" id="scRoot">Investigate</button>` : ""}</div>`;
    }).join("") + `<p class="sc-note">Type “look into the Medical Corps requisition records” to go off-menu.</p>`;
    const rb = $("#scRoot", panel); if (rb) rb.addEventListener("click", runDemoC);
  }
}

function npcAction(kind) {
  const n = state.npcs[state.selection.id];
  if (blockIfReadOnly((kind || "interact") + " · " + (n ? n.name : ""))) return;
  if (kind === "train" && n.id === "kakashi") return runDemoA();
  const relScore = (state.relationships[n.id] || {}).score;
  if (kind === "talk") {
    openScene({ bg: n.scene, portrait: monogram(n.initials, n.accent, "lg"), kicker: "CONVERSATION", title: "A Few Words",
      narrative: `You catch ${n.name} between duties. Not a briefing — just talk. ${n.name.split(" ")[0]} slows down to listen.`,
      context: [["Relationship", relScore != null ? relScore : "—"], ["Setting", n.status || "the village"]],
      onAccept: () => { rel(n.id, 1); chron("relationship", `Spoke with ${n.name}. ${n.name.split(" ")[0]} +1.`); refreshAll(); toast(`${n.name.split(" ")[0]} +1`); } });
  } else if (kind === "favor") {
    openScene({ bg: n.scene, portrait: monogram(n.initials, n.accent, "lg"), kicker: "REQUEST", title: "Asking a Favor",
      narrative: `You lay out what you need from ${n.name}. They don't say no. They don't quite say yes either.`,
      context: [["Relationship", relScore != null ? relScore : "—"], ["Standing", state.player.rank]],
      onAccept: () => { chron("action", `Asked ${n.name} for a favor. They'll consider it.`); refreshAll(); } });
  } else if (kind === "travel") {
    openScene({ bg: n.scene, portrait: monogram(n.initials, n.accent, "lg"), kicker: "PROTOTYPE INTERPRETATION", title: "Travel Together",
      narrative: `The full Worldwalker engine would resolve this here — ${n.name}'s own obligations, the route, what you meet on the road.`,
      context: [["Requested", `Travel with ${n.name}`]], acceptLabel: "Understood",
      onAccept: () => { chron("action", `Proposed travelling with ${n.name} (prototype stub).`); refreshAll(); } });
  }
}
function refreshAll() { renderPlayerPanel(); renderChronicle(); renderInspector(); refreshRegions(); refreshRoutes(); rebuildMarkers(); }

/* ======================================================================
   LEFT PLAYER PANEL + TIMELINE + LEGEND
   ====================================================================== */
function renderPlayerPanel() {
  const P = state.player, loc = state.locations[P.homeLocation] || {};
  const panel = $("#playerPanel");
  const m = state.moves[P.id];
  const natureTags = P.natures.map((n) => `<span class="tag tag--nature">${n.known ? "" : "?"} ${esc(n.name)}</span>`).join("");
  const abilities = P.abilities.map((a) => `<li class="list-li"><span class="li-glyph">✦</span><span>${esc(a)}</span></li>`).join("");
  const goals = P.goals.map((g) => `<li class="list-li goal" data-tag="${g.tag}"><span class="li-glyph">◆</span><span>${esc(g.text)}<small>${esc(g.note || "")}</small></span></li>`).join("");
  const rels = Object.entries(state.relationships).map(([id, r]) => {
    const n = state.npcs[id] || { name: id, initials: "?", accent: "#8a7d63" };
    const neg = r.score < 0, pct = clamp((r.score + 20) / 120 * 100, 4, 100);
    return `<div class="rel-row ${neg ? "neg" : ""}" data-npc="${id}">${monogram(n.initials, n.accent, "sm")}
      <div class="rel-meta"><div class="rel-name">${esc(n.name)}</div><div class="rel-sub">${esc(r.sub)}</div>
      <div class="rel-bar"><i style="width:${pct}%"></i></div></div><div class="rel-score">${r.score}</div></div>`;
  }).join("");
  const visualMove = m && m.meta && m.meta.visual;
  const travelCard = !m ? "" : visualMove ? `
    <div class="travel-card">
      <h4>➹ Relocating on the map</h4>
      <div class="travel-row"><span>Now at</span><b>${esc(P.homeLocationRaw || (loc.name || "—"))}</b></div>
      <div class="travel-row"><span>Source</span><b>Live Worldwalker</b></div>
      <div class="travel-prog"><i style="width:${Math.round(m.vprogress * 100)}%"></i></div>
    </div>` : `
    <div class="travel-card">
      <h4>➹ ${esc(P.status)}</h4>
      <div class="travel-row"><span>Origin</span><b>${esc(locName(m.from))}</b></div>
      <div class="travel-row"><span>Destination</span><b>${esc(locName(m.to))}</b></div>
      <div class="travel-row"><span>Risk</span><b>${esc(m.meta.risk)}</b></div>
      <div class="travel-prog"><i style="width:${Math.round(m.vprogress * 100)}%"></i></div>
    </div>`;

  panel.innerHTML = `
    <div class="pc-head">
      ${monogram(P.monogram, "var(--lightning)", "lg")}
      <div class="pc-id">
        <h1>${esc(P.name)}</h1>
        <div class="pc-line">${P.age ? "Age " + esc(P.age) + " · " : ""}${esc(P.affiliation)}</div>
        <div class="pc-tags">
          <span class="tag tag--rank">${esc(P.rank)}</span>
          <span class="tag">◉ ${esc((m && !visualMove) ? "En route" : (P.homeLocationRaw || loc.name || "—"))}</span>
          ${m ? `<span class="tag tag--travel">➹ ${esc(P.status)}</span>` : `<span class="tag">${esc(P.status)}</span>`}
        </div>
        <div class="pc-tags">${natureTags}</div>
      </div>
    </div>
    ${travelCard}
    <div class="sec">
      <div class="meter"><div class="meter-row"><span>Health</span><span>${P.health.cur}/${P.health.max}</span></div>
        <div class="meter-bar"><div class="meter-fill hp" style="width:${clamp(P.health.cur / (P.health.max || 1) * 100, 0, 100)}%"></div></div></div>
      <div class="meter"><div class="meter-row"><span>${esc(P.resourceName || "Chakra")}</span><span>${P.chakra.cur}/${P.chakra.max}</span></div>
        <div class="meter-bar"><div class="meter-fill ck" style="width:${clamp(P.chakra.cur / (P.chakra.max || 1) * 100, 0, 100)}%"></div></div></div>
      ${P.chakraControl != null ? `<div class="meter"><div class="meter-row"><span>Chakra control</span><span>${P.chakraControl}</span></div>
        <div class="meter-bar"><div class="meter-fill cc" style="width:${P.chakraControl}%"></div></div></div>` : ""}
    </div>
    ${P.stats ? `<div class="sec"><h3 class="sec-title">Stats${P.powerTier ? ` · ${esc(P.powerTier)}` : ""}</h3>
      <div class="pill-row">${Object.entries(P.stats).map(([k, v]) => `<span class="pill">${esc(k)} ${esc(v)}</span>`).join("")}</div></div>` : ""}
    <div class="sec"><h3 class="sec-title">Key Abilities</h3><ul class="list">${abilities}</ul></div>
    <div class="sec"><h3 class="sec-title">Current Goals &amp; Threads</h3><ul class="list">${goals}</ul></div>
    <div class="sec"><h3 class="sec-title">Key Relationships</h3>${rels}</div>`;

  $$(".rel-row", panel).forEach((row) => row.addEventListener("click", () => select("npc", row.dataset.npc)));
}

function renderTimeline() {
  const dayWord = state.sourceKey === "real" ? "Turn" : "Day";
  $("#timelineDate").textContent = state.timelineLabel
    ? `${state.era} · ${state.timelineLabel}`
    : `${state.era} — ${state.season} · ${dayWord} ${state.day}`;
  const chip = $("#canonChip"), st = $("#canonState"), g = state.primaryCanon;
  const nameEl = $(".canon-name", chip);
  if (nameEl) nameEl.textContent = g.name;
  chip.classList.remove("is-imminent", "is-now");
  const unit = state.sourceKey === "real" ? "d" : "d";
  if (g.triggered) { st.textContent = "unfolding now"; chip.classList.add("is-now"); }
  else if (g.daysOut <= 3) { st.textContent = `imminent · ~${g.daysOut}${unit}`; chip.classList.add("is-imminent"); }
  else { st.textContent = `approaching · ~${g.daysOut}${unit}`; }
}

function renderLegend() {
  const box = $("#mapLegend"), mode = state.mode;
  let rows, note = "";
  if (mode === "political") {
    rows = ["konoha", "suna", "ame", "kiri", "kumo", "iwa"].map((f) => [state.factions[f].color, state.factions[f].name]);
    note = "Soft influence washes — who holds each broad area. Turn Political off to remove the layer.";
  } else if (mode === "danger") {
    rows = ["moderate", "high", "critical"].map((d) => [state.dangerColors[d], d[0].toUpperCase() + d.slice(1)]);
    note = "Danger concentrates around events and crises, not whole countries.";
  } else if (mode === "relationships") {
    rows = ["friendly", "neutral", "strained", "hostile", "unknown"].map((r) => [state.relationshipColors[r], r[0].toUpperCase() + r.slice(1)]);
    note = "Country labels tint by their stance toward you. The artwork is otherwise untouched.";
  } else {
    rows = [["var(--leaf)", "Mission / opportunity"], ["var(--danger)", "Danger event"], ["var(--training)", "Training thread"],
            ["var(--intrigue)", "Investigation"], ["var(--blood)", "Canon event"]];
    note = "Illustrated map — event, mission and canon markers only.";
  }
  box.innerHTML = `<h4>${mode} view</h4>` +
    rows.map(([c, t]) => `<div class="legend-row"><span class="legend-sw" style="background:${c}"></span>${esc(t)}</div>`).join("") +
    `<div class="legend-note">${note}</div>`;
}

/* ======================================================================
   SCENE OVERLAY
   ====================================================================== */
let sceneAccept = null;
function openScene(o) {
  const ov = $("#sceneOverlay");
  $("#sceneBg").style.backgroundImage = o.bg ? `url('${o.bg}')` : "none";
  $("#scenePortrait").innerHTML = o.portrait || "";
  $("#sceneKicker").textContent = o.kicker || "EVENT";
  $("#sceneTitle").textContent = o.title || "";
  $("#sceneNarrative").textContent = o.narrative || "";
  const ctx = $("#sceneContext");
  ctx.innerHTML = (o.context || []).map(([k, v]) => `<div><span class="sc-k">${esc(k)}:</span> <b>${esc(v)}</b></div>`).join("");
  ctx.style.display = (o.context && o.context.length) ? "block" : "none";
  $("#sceneAccept").textContent = o.acceptLabel || "Accept";
  sceneAccept = o.onAccept || null;
  $("#sceneAltInput").value = "";
  ov.hidden = false;
}
function closeScene() { $("#sceneOverlay").hidden = true; sceneAccept = null; }

/* ======================================================================
   FREEFORM ACTIONS
   ====================================================================== */
function runDemoA() {
  if (blockIfReadOnly("Ask Kakashi to train")) return;
  openScene({
    bg: state.npcs.kakashi.scene, portrait: monogram("KH", "#8fb3c7", "lg"),
    kicker: "TRAINING REQUEST", title: "Training Request",
    narrative: "You find Kakashi at Training Ground Three after the morning exercises. He lowers his book a fraction — that's a yes, or close enough. “Show me what your Lightning Release actually does. Then we'll talk about the Chidori.”",
    context: [["Relationship", state.relationships.kakashi.score], ["Relevant Trait", "Lightning Nature"], ["Current Rank", state.player.rank]],
    acceptLabel: "Accept evaluation",
    onAccept: () => { dispatch({ type: "training_thread_started" }); focusOn(0.505, 0.523, 4.6); toast("New training thread + Kakashi +3"); },
  });
}
function runDemoB() {
  if (blockIfReadOnly("Covert travel to Amegakure")) return;
  openScene({
    bg: state.locations.ame.scene, portrait: monogram(state.player.monogram, "var(--danger)", "lg"),
    kicker: "COVERT DEPARTURE", title: "Slipping the Leash",
    narrative: "No papers filed, no squad notified. You take the eastern culvert out past the wall at dusk and turn west, toward the rain.",
    context: [["Destination", "Amegakure"], ["Authorisation", "None — unsanctioned"], ["Travel time", "~4 days (accelerated)"]],
    acceptLabel: "Go",
    onAccept: () => {
      state.mode = "danger"; syncModeButtons();
      state.risks.push("Unauthorised border crossing — Konoha");
      dispatch({ type: "entity_move_started", entityId: state.player.id, routeId: "ren_to_ame",
        from: state.player.homeLocation, to: "ame", durationDays: 4, covert: true, risk: "Moderate", auto: true });
      select("player", state.player.id);
      toast("Now traveling covertly → Amegakure. Watch the route.", true);
    },
  });
}
function runDemoC() {
  if (blockIfReadOnly("Investigate Root")) return;
  openScene({
    bg: "assets/scenes/academy_classroom.webp", portrait: monogram("根", "var(--intrigue)", "lg"),
    kicker: "QUIET INQUIRIES", title: "Pulling Threads",
    narrative: "Duty rosters that don't reconcile, requisitions signed with a seal nobody will claim. Root leaves no shadow. It still leaves paperwork.",
    context: [["Knowledge", "Root +1"], ["Danzō standing", "wary"], ["Konoha tension", (state.worldState.konohaTension + 1) + "/5"]],
    acceptLabel: "Follow the lead",
    onAccept: () => { dispatch({ type: "investigation_started" }); focusOn(0.478, 0.492, 4.6); toast("Investigation thread opened · Danzō -2"); },
  });
}
function runDemoD() {
  if (blockIfReadOnly("Train for three weeks")) return;
  openScene({
    bg: "assets/scenes/academy_classroom.webp", portrait: monogram(state.player.monogram, "var(--gold-bright)", "lg"),
    kicker: "TIME SKIP", title: "Three Weeks of Drills",
    narrative: "Twenty-one days. Chakra-control ladders at dawn, the same three seals until they stop being decisions. The world outside does not wait.",
    context: [["Time", "+21 days"], ["Chakra control", "+7"], ["Lightning Release", "basics → developing"]],
    acceptLabel: "Commit the time",
    onAccept: () => { dispatch({ type: "time_skipped", days: 21 }); toast("21 days passed. The world moved without you."); },
  });
}
function genericScene(text) {
  openScene({
    bg: "assets/scenes/battlefield_dusk.webp", portrait: monogram(state.player.monogram, "var(--lightning)", "lg"),
    kicker: "PROTOTYPE INTERPRETATION", title: "Freeform Action Received",
    narrative: "The full Worldwalker engine would resolve this here — weighing your abilities, relationships, the world's state, and what everyone else is doing about it.",
    context: [["Your action", text], ["Engine status", "not implemented in this prototype"], ["What's real", "the map only moves when the engine says so"]],
    acceptLabel: "Understood", onAccept: () => toast("Prototype stub — no world change applied."),
  });
}
const has = (s, ...w) => w.some((x) => s.includes(x));
function handleAction(raw) {
  const text = (raw || "").trim(); if (!text) return;
  if (blockIfReadOnly(text)) return;
  const s = text.toLowerCase();
  chron("action", `You: “${text}”`); renderChronicle();
  if (has(s, "train", "training", "drill") && has(s, "three weeks", "3 weeks", "three week", "21 days", "for weeks", "a few weeks")) return runDemoD();
  if (has(s, "kakashi") && has(s, "train", "teach", "learn", "tutor", "spar", "evaluate", "mentor") && has(s, "chidori", "lightning", "raiton", "nature", "electric")) return runDemoA();
  if (has(s, "leave", "travel", "depart", "go to", "head", "sneak", "slip", "journey", "set out") &&
      has(s, "amegakure", " ame", "the rain", "rain village", "hidden rain") &&
      has(s, "secret", "covert", "quiet", "unseen", "unsanction", "without", "sneak", "night", "hidden")) return runDemoB();
  if (has(s, "root", "danzo", "danzō") && has(s, "spy", "investigate", "probe", "snoop", "dig", "surveil", "watch", "infiltrate", "look into", "tail")) return runDemoC();
  if (has(s, "hideout", "laboratory", "lab") && has(s, "investigate", "scout", "search", "explore", "look")) return director_hideout();
  genericScene(text);
}

/* ======================================================================
   ADVANCE 1 DAY + DIRECTOR
   ====================================================================== */
function advanceDay() {
  if (blockIfReadOnly("Advance 1 Day")) return;
  dispatch({ type: "day_advanced", day: state.day + 1 });
  if (Math.random() < 0.85) {
    const d = WORLD_DEVS[(Math.random() * WORLD_DEVS.length) | 0];
    chron(d.type, d.text); if (d.spawn) d.spawn();
    toast("Day " + state.day + " — " + d.text.split(" — ")[0].split(".")[0]);
  } else toast("Day " + state.day + " — quiet on every front.");
  refreshAll(); renderTimeline();
}

function director_kakashiMission() {
  if (blockIfReadOnly("Director action")) return;
  const sc = state.scenarios.kakashi_mission || {};
  if (state.moves.kakashi) { toast("Kakashi is already out."); return; }
  state.npcs.kakashi.scope = "regional";   // a jonin on assignment is trackable at regional zoom
  dispatch({ type: "entity_move_started", entityId: "kakashi", routeId: "kakashi_mission",
    from: "konoha", to: "fire_east_border", durationDays: 26, auto: true, silent: true });
  dispatch({ type: "info_updated", entityId: "kakashi", infoStatus: "confirmed",
    status: sc.status || "On assignment", note: sc.note || "On assignment", chronicle: sc.chronicle });
  toast(sc.toast || "Kakashi is on assignment");
}
function director_kakashiIntel() {
  if (blockIfReadOnly("Director action")) return;
  const sc = state.scenarios.kakashi_intel || {};
  if (!state.moves.kakashi) { toast("Kakashi is in the village — nothing to report."); return; }
  dispatch({ type: "info_updated", entityId: "kakashi", infoStatus: "confirmed",
    note: sc.note || "Field report near the border", x: sc.reportedX, y: sc.reportedY, chronicle: sc.chronicle });
  focusOn(sc.reportedX, sc.reportedY, Math.max(state.camera.s, 2.4));
  toast(sc.toast || "Field report logged");
}
function director_missingNin() {
  if (blockIfReadOnly("Director action")) return;
  const sc = state.scenarios.missing_nin || {};
  dispatch({ type: "world_event_started", eventId: "missing_nin", infoStatus: "rumored",
    status: "active", note: "Traveller reports", chronicle: sc.chronicle });
  dispatch({ type: "region_danger_changed", regionId: sc.dangerRegion || "land_of_rivers",
    level: sc.dangerLevel || "moderate",
    chronicle: `Danger in the ${(state.regions[sc.dangerRegion || "land_of_rivers"] || {}).name} rises to ${sc.dangerLevel || "moderate"}.` });
  const f = state.features.missing_nin;
  focusOn(f.x, f.y - 0.06, Math.max(state.camera.s, 2.6));
  select("feature", "missing_nin");
  toast(sc.toast || "Missing-nin sighting");
}
function director_hideout() {
  if (blockIfReadOnly("Director action")) return;
  const sc = state.scenarios.hideout_investigate || {};
  if (state.features.unknown_hideout.status === "identified") { toast("Already identified — Orochimaru laboratory."); return; }
  dispatch({ type: "feature_discovered", featureId: "unknown_hideout", chronicle: sc.chronicle });
  select("feature", "unknown_hideout");
  toast(sc.toast || "Hideout identified");
}
function director_politicalShift() {
  if (blockIfReadOnly("Director action")) return;
  const sc = state.scenarios.political_shift || {};
  if (state.regions.land_of_rain.controller === (sc.newController || "akatsuki")) { toast("Rain already shifted."); return; }
  dispatch({ type: "region_controller_changed", regionId: sc.region || "land_of_rain",
    newController: sc.newController || "akatsuki", danger: sc.danger || "high", relationship: sc.relationship || "hostile",
    chronicle: sc.chronicle });
  toast(sc.toast || "Political shift applied");
}
function director_gaaraNow() {
  if (blockIfReadOnly("Director action")) return;
  if (state.primaryCanon.triggered) { toast("That canon event is already active."); return; }
  dispatch({ type: "canon_event_triggered" });
  toast("Canon — " + state.primaryCanon.name + " has begun.");
}

function buildDirector() {
  const pop = $("#directorPop");
  pop.innerHTML = `
    <h3>Director</h3>
    <div class="dir-sub">Development-only. Fires state events the real engine would emit.</div>
    <div class="dir-group"><h4>World</h4>
      <button class="dir-btn" data-d="advance">Advance 1 Day<small>roll one living-world development</small></button>
      <button class="dir-btn" data-d="gaara">Trigger Gaara Rescue Crisis now<small>skip the countdown</small></button>
      <button class="dir-btn" data-d="political">Demo Political Shift<small>Land of Rain → Akatsuki influence</small></button>
    </div>
    <div class="dir-group"><h4>Information quality — Kakashi</h4>
      <button class="dir-btn" data-d="kmission">Demo Kakashi Mission<small>he leaves; still on the map, status “On assignment”</small></button>
      <button class="dir-btn" data-d="kintel">Demo Field Report<small>pinpoints him near the eastern border</small></button>
    </div>
    <div class="dir-group"><h4>Map features</h4>
      <button class="dir-btn" data-d="missing">Demo Missing-nin Sighting<small>rumored marker + soft danger zone near Rivers</small></button>
      <button class="dir-btn" data-d="hideout">Demo Investigate Unknown Hideout<small>rename → Orochimaru laboratory</small></button>
    </div>
    <div class="dir-group"><h4>Camera</h4>
      <button class="dir-btn" data-d="focus">Focus Player</button>
      <button class="dir-btn" data-d="reset">Reset View</button>
    </div>`;
  const map = {
    advance: advanceDay, gaara: director_gaaraNow, political: director_politicalShift,
    kmission: director_kakashiMission, kintel: director_kakashiIntel,
    missing: director_missingNin, hideout: director_hideout,
    focus: () => focusOn(state.player.x, state.player.y, 4.7),
    reset: () => { state.camera.ts = 1; state.camera.tpx = 0; state.camera.tpy = 0; kick(); },
  };
  $$(".dir-btn", pop).forEach((b) => b.addEventListener("click", () => { map[b.dataset.d](); }));
}
function toggleDirector(anchor) {
  const pop = $("#directorPop");
  if (!pop.hidden) { pop.hidden = true; return; }
  const r = anchor.getBoundingClientRect();
  pop.style.left = clamp(r.left - 150, 8, window.innerWidth - 340) + "px";
  pop.style.bottom = (window.innerHeight - r.top + 8) + "px";
  pop.hidden = false;
}

/* ======================================================================
   MAP MODES
   ====================================================================== */
function syncModeButtons() {
  $$("#mapModes .mode-btn").forEach((b) => b.classList.toggle("is-active", b.dataset.mode === state.mode));
  stageEl.dataset.mode = state.mode;
  renderLegend(); refreshRegions(); rebuildMarkers();
}

/* ======================================================================
   BOOTSTRAP  —  two data sources through the SAME renderer
   ====================================================================== */
let LIVING = { demo: null, real: null };   // two LivingMapState objects
let RAW = {};                              // loaded json

/** DEMO campaign -> LivingMapState (same shape the adapter produces). */
function buildDemoLivingState() {
  const D = RAW.demo, RM = RAW.regions;
  const npcs = clone(D.npcs), groups = clone(D.groups), features = clone(D.features), worldEvents = clone(D.worldEvents);
  const setInfo = (o) => Object.values(o).forEach((e) => { e.infoStatus = e.information_status || e.infoStatus || "confirmed"; });
  setInfo(npcs); setInfo(groups); setInfo(features); setInfo(worldEvents);
  const canon = clone(D.canon);
  return {
    sourceKey: "demo", sourceLabel: "Demo Campaign — Ren Arakawa", readOnly: false,
    era: D.meta.era, season: D.meta.season, day: D.meta.day, timelineLabel: "",
    player: Object.assign(clone(D.player), { loc: D.player.homeLocation }),
    relationships: clone(D.relationships),
    canon, primaryCanon: canon.gaara_rescue, firedCanon: [],
    locations: clone(D.locations), npcs, groups, features, worldEvents,
    transients: {}, routes: clone(D.routes), scenarios: clone(D.scenarios || {}),
    worldState: { konohaTension: 1, rootKnowledge: 0 },
    risks: ["Rain territory sealed — travellers turned away"],
    chronicle: [
      { day: 1, type: "canon", text: "Early Shippūden. Naruto has returned to Konoha after two years with Jiraiya." },
      { day: 1, type: "world", text: "Sunagakure reports increased Akatsuki movement near its borders." },
      { day: 1, type: "mission", text: "Border patrol posting opened on the Land of Rivers frontier." },
      { day: 1, type: "action", text: "Ren Arakawa promoted to Chūnin; field authorisation signed by the Hokage." },
    ],
    regions: clone(RM.regions), factions: RM.factions, dangerColors: RM.dangerColors, relationshipColors: RM.relationshipColors,
    diagnostics: null,
  };
}
function clone(o) { return JSON.parse(JSON.stringify(o)); }

/** Full swap of a LivingMapState into `state` and a from-scratch re-render. */
function applyLivingState(L, o) {
  o = o || {};
  Object.assign(state, {
    sourceKey: L.sourceKey, sourceLabel: L.sourceLabel, readOnly: !!L.readOnly,
    era: L.era, season: L.season, day: L.day, timelineLabel: L.timelineLabel || "",
    player: L.player, relationships: L.relationships, canon: L.canon, primaryCanon: L.primaryCanon,
    firedCanon: L.firedCanon || [], locations: L.locations, npcs: L.npcs, groups: L.groups,
    features: L.features, worldEvents: L.worldEvents, transients: {}, routes: L.routes || {},
    scenarios: L.scenarios || {}, worldState: L.worldState || {}, risks: L.risks || [],
    chronicle: L.chronicle || [], regions: L.regions, factions: L.factions,
    dangerColors: L.dangerColors, relationshipColors: L.relationshipColors,
    diagnostics: L.diagnostics || null, combat: L.combat || { active: false },
    travelGraph: L.travelGraph || null, live: L.live || null,
    mode: "political", chronFilter: "all",
    moves: {}, selection: { kind: null, id: null }, inspector: { tab: "sel" }, _visKey: "",
    _newChronKeys: new Set(),
  });
  state.camera = { s: 1, px: 0, py: 0, ts: 1, tpx: 0, tpy: 0 };
  state._band = "world";

  Object.values(state.groups).forEach((g) => {   // demo: groups that start mid-route
    if (g.move && g.move.status === "active") {
      state.moves[g.id] = { routeId: g.move.routeId, durationDays: g.move.durationDays, progress: g.move.progress || 0,
        vprogress: g.move.progress || 0, status: "active", auto: !!g.move.auto, from: null, to: "suna",
        meta: { kind: (state.routes[g.move.routeId] || {}).kind } };
      const rt = state.routes[g.move.routeId]; if (rt) rt.status = "active";
    }
  });

  _markerEls.forEach((el) => el.remove()); _markerEls = new Map();
  stageEl.dataset.mode = state.mode;
  stageEl.classList.toggle("is-readonly", state.readOnly);
  stageEl.classList.toggle("is-live", state.sourceKey === "live");
  $$("#mapModes .mode-btn").forEach((b) => b.classList.toggle("is-active", b.dataset.mode === "political"));
  $$("#chronFilters .chip").forEach((c) => c.classList.toggle("is-active", c.dataset.filter === "all"));
  $("#dataSourceSel").value = state.sourceKey;
  $("#readonlyTag").hidden = !state.readOnly;
  $("#readonlyTag").textContent = state.sourceKey === "live"
    ? "◉ Live Worldwalker — read-only mirror" : "◉ Real Campaign Copy — read-only mirror";
  $("#directorBtn").style.display = state.readOnly ? "none" : "";
  $("#liveStatus").hidden = state.sourceKey !== "live";
  updateCombatTag();

  buildRegionSvg(); buildRouteSvg(); buildDirector();
  renderPlayerPanel(); renderTimeline(); renderChronicle(); renderLegend(); updateZoomPill();
  washLayer.dataset.band = markerLayer.dataset.band = state._band;
  clampCamera(); applyScalerTransform();

  state.selection = o.selection || { kind: "location", id: "konoha" };
  renderInspector(); refreshRegions(); rebuildMarkers();
  renderDiagnostics();
}

/** Dev-only data-source switch. */
function applySource(key) {
  LiveBridge.stop();
  if (key === "live") {
    applyLivingState(clone(LIVING.live || placeholderLive()), { selection: { kind: "player", id: "player" } });
    LiveBridge.start();
    return;
  }
  applyLivingState(clone(LIVING[key]), { selection: key === "real" ? { kind: "player", id: "player" } : { kind: "location", id: "konoha" } });
}

/* ======================================================================
   LIVE READ-ONLY BRIDGE  —  polls Worldwalker's existing GET APIs via
   bridge_proxy.py (/ww/*). Never sends a mutating request.
   ====================================================================== */
function placeholderLive() {
  const L = clone(LIVING.real);       // reuse the region/faction scaffolding
  L.sourceKey = "live"; L.sourceLabel = "Live Worldwalker"; L.readOnly = true;
  L.era = "Live"; L.season = ""; L.timelineLabel = "waiting for Worldwalker…";
  L.chronicle = [{ day: 0, type: "world", text: "Waiting for a running Worldwalker campaign…" }];
  L.risks = []; L.diagnostics = null; L.combat = { active: false };
  L.live = { busy: false, campaignActive: null, wwVersion: "" };
  return L;
}

const LiveBridge = (() => {
  let timer = null, running = false, fails = 0, polls = 0;
  let lastFp = "", lastChangeAt = 0, lastPollOk = false, statusKey = "disconnected";
  const OPTS = () => ({
    registry: RAW.registry, canonTimeline: RAW.canonTL,
    regionDefs: RAW.regions.regions, factionDefs: RAW.regions.factions,
    dangerColors: RAW.regions.dangerColors, relationshipColors: RAW.regions.relationshipColors,
  });

  function setStatus(k, detail) {
    statusKey = k;
    const map = {
      disconnected: ["Disconnected", "Worldwalker is not currently available."],
      connecting: ["Connecting", "Looking for a running Worldwalker…"],
      connected: ["Connected", "Live"],
      unavailable: ["Campaign unavailable", "Worldwalker is running but no campaign is loaded."],
      busy: ["Worldwalker busy", "Worldwalker is resolving a turn — showing the last snapshot."],
      stale: ["Stale data", "Lost contact — showing the last good snapshot."],
    };
    const [label, text] = map[k] || [k, k];
    const pill = $("#liveStatus");
    if (pill) { pill.dataset.state = k; pill.textContent = "LIVE · " + label; pill.title = detail || text; }
    if (state.sourceKey === "live") {
      state._live = Object.assign(state._live || {}, {
        statusKey: k, statusText: label, polls,
        lastChangeAgo: lastChangeAt ? Math.round((Date.now() - lastChangeAt) / 1000) + "s ago" : "—",
        target: (LiveBridge._status && LiveBridge._status.target) || "—",
      });
      if (($("#diagDrawer") || {}).hidden === false) renderDiagnostics();
    }
  }

  async function jget(path) {
    const r = await fetch(path, { cache: "no-store" });
    const j = await r.json().catch(() => ({}));
    return { ok: r.ok, code: r.status, j };
  }

  async function pollOnce() {
    polls++;
    try {
      const st = await jget("/api/state");
      if (!st.ok || (st.j && st.j.error)) { onFail(); return; }
      if (st.j && st.j.campaign_active === false) { fails = 0; setStatus("unavailable"); return; }
      const [panels, combat] = await Promise.all([
        jget("/api/panels").then((x) => x.j).catch(() => null),
        jget("/api/combat/state").then((x) => x.j).catch(() => null),
      ]);
      fails = 0; lastPollOk = true;
      const payload = {
        state: st.j.state || {}, panels: panels || {}, combat: combat || {},
        meta: { version: (st.j.state || {}).campaign_last_saved_version, busy: !!st.j.busy, campaignActive: true },
      };
      const mapImage = panels && panels.map_image;
      if (mapImage && scalerEl) scalerEl.style.backgroundImage = `url('${String(mapImage).replace(/'/g, "%27")}')`;
      const campaignWorld = document.getElementById("mapCampaignWorld");
      if (campaignWorld) campaignWorld.textContent = (st.j.state || {}).world || "Campaign";
      if (st.j.busy) { setStatus("busy"); return; }   // don't rebuild mid-turn
      const fp = fingerprint(payload);
      if (fp === lastFp) { setStatus("connected"); return; }

      const prev = lastFp ? state : null;
      const LN = window.WorldwalkerStateAdapter.buildLivingMapStateFromLive(payload, OPTS());
      LIVING.live = LN;
      lastFp = fp; lastChangeAt = Date.now();
      if (!prev) { applyLivingState(clone(LN), { selection: { kind: "player", id: "player" } }); }
      else applyLiveDelta(clone(LN));
      setStatus("connected");
    } catch (e) { onFail(); }
  }

  function onFail() {
    fails++;
    if (fails >= 2) setStatus(lastPollOk ? "stale" : "disconnected");
    else setStatus("connecting");
  }

  function fingerprint(p) {
    const s = p.state || {}, pa = p.panels || {}, cb = (p.combat || {}).combat || {};
    return JSON.stringify({
      turn: s.turn, wt: s.world_time, cd: s.canon_day, loc: s.location, hp: s.hp, ck: s.resource,
      rank: (s.special || {})["Shinobi Rank"], titles: (s.titles || []).length, lvl: s.level,
      rep: s.reputation, we: (s.world_events || []).length, cf: (s.canon_events_fired || []).length,
      q: (s.quests || []).map((x) => x && x.name + ":" + (x.objectives || []).map((o) => o.progress).join(",")).join("|"),
      orgs: Object.keys(s.organizations || {}).length,
      combat: !!(cb.active || cb.round || cb.enemy),
      chron: (s.simulation_events || []).slice(-1).map((e) => e && e.id).join(""),
      people: ((pa.relationships_view || {}).people || []).map((r) => r.name + r.last_known_location).join("|"),
    });
  }

  /* soft update: keep camera / selection / mode, animate the meaningful bits */
  function applyLiveDelta(LN) {
    const oldPlayerLoc = state.player.homeLocation;
    const curXY = { x: state.player.x, y: state.player.y };   // may be mid-transition
    const playerMove = state.moves[state.player.id];
    const hadVisualMove = !!(playerMove && playerMove.meta && playerMove.meta.visual);
    const oldChronKeys = new Set(state.chronicle.map(chronKey));

    Object.assign(state, {
      era: LN.era, day: LN.day, timelineLabel: LN.timelineLabel,
      player: LN.player, relationships: LN.relationships, primaryCanon: LN.primaryCanon,
      canon: LN.canon, firedCanon: LN.firedCanon || [], locations: LN.locations, npcs: LN.npcs,
      groups: LN.groups, worldEvents: LN.worldEvents, regions: LN.regions, risks: LN.risks || [],
      diagnostics: LN.diagnostics || null, combat: LN.combat || { active: false },
      travelGraph: LN.travelGraph || null,
    });
    // chronicle: keep order, flag genuinely new entries for a one-shot pulse
    state._newChronKeys = new Set(LN.chronicle.map(chronKey).filter((k) => !oldChronKeys.has(k)));
    state.chronicle = LN.chronicle;

    const newLoc = state.player.homeLocation;
    if (newLoc && oldPlayerLoc && newLoc !== oldPlayerLoc && state.player.locResolved !== false) {
      // a real location change -> animate from wherever the marker currently is
      const toXY = { x: state.player.x, y: state.player.y };
      startLiveTransition(curXY, toXY, oldPlayerLoc, newLoc);
    } else if (hadVisualMove) {
      // a transition is still running to the same place — don't snap it to the end
      state.player.x = curXY.x; state.player.y = curXY.y;
    }
    renderPlayerPanel(); renderTimeline(); renderChronicle();
    updateCombatTag();
    refreshRegions(); rebuildMarkers();
    if (state.selection.kind === "player" || (state.selection.kind === "canon")) renderInspector();
    if (state.selection.kind === "npc" && !state.npcs[state.selection.id]) { state.selection = { kind: "player", id: "player" }; renderInspector(); }
    renderDiagnostics();
  }

  return {
    _status: null,
    async probe() {
      try {
        const r = await fetch("/api/state", { cache: "no-store" });
        const j = await r.json();
        const status = { discovered: r.ok, campaign_active: !!(j && j.state), target: location.origin };
        LiveBridge._status = status; return status;
      }
      catch { LiveBridge._status = null; return null; }
    },
    start() {
      if (running) return; running = true; fails = 0; polls = 0; lastFp = ""; lastPollOk = false;
      setStatus("connecting");
      const tick = () => {
        if (!running) return;
        const gap = document.hidden ? 8000 : 1800;   // ~1-2s active; back off when hidden
        pollOnce().finally(() => { if (running) timer = setTimeout(tick, gap); });
      };
      tick();
      document.addEventListener("visibilitychange", onVis);
    },
    stop() {
      running = false; if (timer) clearTimeout(timer); timer = null;
      document.removeEventListener("visibilitychange", onVis);
    },
  };
  function onVis() { /* next tick picks up the new gap automatically */ }
})();

function chronKey(e) { return (e.day || 0) + "|" + String(e.text || "").slice(0, 70); }

/* a purely-visual travel transition for LIVE mode (not authoritative pathfinding) */
function startLiveTransition(fromXY, toXY, fromName, toName) {
  let points = null;
  const tg = state.travelGraph;
  if (tg && tg.edges) {
    const path = bfsPath(tg.edges, matchNode(tg, fromName), matchNode(tg, toName));
    if (path && path.length >= 2) {
      const res = window.WorldwalkerStateAdapter.makeResolver(RAW.registry);
      const pts = path.map((n) => res.resolve(n)).filter((r) => r.resolved).map((r) => [r.x, r.y]);
      if (pts.length >= 2) points = pts;
    }
  }
  if (!points) {
    const mx = (fromXY.x + toXY.x) / 2, my = (fromXY.y + toXY.y) / 2;
    const dx = toXY.x - fromXY.x, dy = toXY.y - fromXY.y, L = Math.hypot(dx, dy) || 1;
    points = [[fromXY.x, fromXY.y], [mx - dy / L * 0.05, my + dx / L * 0.05], [toXY.x, toXY.y]];
  }
  state.routes._live_move = { id: "_live_move", points, status: "active", kind: "transition" };
  state.moves[state.player.id] = {
    routeId: "_live_move", durationDays: 1.1, progress: 0, vprogress: 0, status: "active",
    auto: true, from: null, to: null, meta: { kind: "transition", visual: true, risk: "—", covert: false },
  };
  state.player.x = fromXY.x; state.player.y = fromXY.y;
  kick();
}
function matchNode(tg, name) {
  const names = (tg.nodes || []).map((n) => n.name);
  const low = String(name || "").toLowerCase();
  return names.find((n) => n.toLowerCase() === low) || names.find((n) => n.toLowerCase().includes(low) || low.includes(n.toLowerCase())) || name;
}
function bfsPath(edges, a, b) {
  if (!edges[a] || !edges[b]) return null;
  const q = [[a]], seen = new Set([a]);
  while (q.length) {
    const path = q.shift(), last = path[path.length - 1];
    if (last === b) return path;
    for (const e of edges[last] || []) if (!seen.has(e.to)) { seen.add(e.to); q.push(path.concat(e.to)); }
  }
  return null;
}

function updateCombatTag() {
  const tag = $("#combatTag");
  if (!tag) return;
  const on = state.combat && state.combat.active;
  tag.hidden = !on;
  if (on) tag.textContent = "⚔ Combat active — being resolved in Worldwalker" +
    (state.combat.location ? " (" + state.combat.location + ")" : "");
  stageEl.classList.toggle("is-combat", !!on);
}

function setMobileView(view, focus = true) {
  const allowed = new Set(["chronicle", "actions", "character", "map", "more"]);
  const next = allowed.has(view) ? view : "map";
  document.body.dataset.mobileView = next;
  $$("#mobileBottomNav [data-mobile-view]").forEach((button) => {
    button.setAttribute("aria-selected", String(button.dataset.mobileView === next));
  });
  if (focus && window.matchMedia("(max-width:720px)").matches) window.scrollTo({ top: 0, behavior: "auto" });
  if (next === "map") requestAnimationFrame(() => { clampCamera(); applyScalerTransform(); positionMarkers(); });
  if (next === "actions" && focus) requestAnimationFrame(() => $("#actionInput")?.focus({ preventScroll: true }));
}

function syncResponsiveView() {
  if (window.matchMedia("(max-width:720px)").matches) {
    if (!document.body.dataset.mobileView) setMobileView("map", false);
  } else {
    delete document.body.dataset.mobileView;
  }
}

async function boot() {
  stageEl = $("#mapStage"); scalerEl = $("#mapScaler");
  regionSvg = $("#regionSvg"); routeSvg = $("#routeSvg"); markerLayer = $("#markerLayer");

  try {
    // The real save copy is git-ignored (private). A fresh clone falls back to
    // the sanitized fixture so "Real Campaign Copy" still renders something.
    const saveJson = (u) => fetch(u).then((r) => (r.ok ? r.json() : Promise.reject(new Error(u + " -> " + r.status))));
    const save = await saveJson("sample_data/real_naruto_save.json")
      .catch(() => saveJson("sample_data/sanitized_naruto_fixture.json"));
    const [demo, regions, registry, canonTL] = await Promise.all([
      fetch("data/demo_campaign.json").then((r) => r.json()),
      fetch("data/map_regions.json").then((r) => r.json()),
      fetch("data/naruto_location_registry.json").then((r) => r.json()),
      fetch("data/naruto_canon_timeline.json").then((r) => r.json()),
    ]);
    RAW = { demo, regions, save, registry, canonTL };
  } catch (err) {
    stageEl.innerHTML = `<div style="padding:24px;color:#e9ddc6;font:14px/1.6 system-ui">
      <b>Could not load data.</b><br>Run from a local server:<br>
      <code>python -m http.server 8777</code> &nbsp;then open &nbsp;<code>http://localhost:8777/</code><br><br>
      <span style="color:#8a7d63">(Browsers block fetch() of local files opened via file://)</span></div>`;
    console.error(err); return;
  }

  LIVING.demo = buildDemoLivingState();
  try {
    LIVING.real = window.WorldwalkerStateAdapter.buildLivingMapState(RAW.save, {
      registry: RAW.registry, canonTimeline: RAW.canonTL,
      regionDefs: RAW.regions.regions, factionDefs: RAW.regions.factions,
      dangerColors: RAW.regions.dangerColors, relationshipColors: RAW.regions.relationshipColors,
      territoriesByName: { Konohagakure: "Konohagakure", Sunagakure: "Sunagakure", Amegakure: "Amegakure",
        Kirigakure: "Kirigakure", Kumogakure: "Kumogakure", Iwagakure: "Iwagakure", "Land of Iron": "Iron Country" },
      saveFileName: "real_naruto_save.json",
    });
  } catch (err) {
    console.error("adapter failed", err);
    LIVING.real = LIVING.demo;   // fall back so the prototype still runs
  }

  bindMapInteraction();
  syncResponsiveView();
  $$("#mobileBottomNav [data-mobile-view]").forEach((button) => {
    button.addEventListener("click", () => setMobileView(button.dataset.mobileView));
  });
  window.addEventListener("resize", syncResponsiveView, { passive: true });

  // shared one-time wiring
  $$("#mapModes .mode-btn").forEach((b) => b.addEventListener("click", () => { state.mode = b.dataset.mode; syncModeButtons(); }));
  $$("#chronFilters .chip").forEach((c) => c.addEventListener("click", () => {
    $$("#chronFilters .chip").forEach((x) => x.classList.remove("is-active"));
    c.classList.add("is-active"); state.chronFilter = c.dataset.filter; renderChronicle();
  }));
  const submit = () => { const v = $("#actionInput").value; $("#actionInput").value = ""; handleAction(v); };
  $("#actionForm").addEventListener("submit", (e) => { e.preventDefault(); submit(); });
  $("#actionInput").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } });
  $$("#shortcuts .shortcut[data-fill]").forEach((btn) => btn.addEventListener("click", () => { handleAction(btn.dataset.fill); }));
  $("#advanceDayBtn").addEventListener("click", advanceDay);
  $("#directorBtn").addEventListener("click", () => toggleDirector($("#directorBtn")));
  $("#diagBtn").addEventListener("click", () => { const d = $("#diagDrawer"); d.hidden = !d.hidden; });
  $("#diagClose").addEventListener("click", () => { $("#diagDrawer").hidden = true; });
  $("#dataSourceSel").addEventListener("change", (e) => applySource(e.target.value));
  document.addEventListener("click", (e) => {
    const pop = $("#directorPop");
    if (!pop.hidden && !pop.contains(e.target) && e.target.id !== "directorBtn") pop.hidden = true;
  });
  $("#ctlZoomIn").addEventListener("click", () => focusOn(centerN().x, centerN().y, Math.min(CAM.max, state.camera.s * 1.6)));
  $("#ctlZoomOut").addEventListener("click", () => focusOn(centerN().x, centerN().y, Math.max(CAM.min, state.camera.s / 1.6)));
  $("#ctlFocus").addEventListener("click", () => focusOn(state.player.x, state.player.y, 4.7));
  $("#ctlReset").addEventListener("click", () => { state.camera.ts = 1; state.camera.tpx = 0; state.camera.tpy = 0; kick(); });
  $("#sceneClose").addEventListener("click", closeScene);
  $("#sceneOverlay").addEventListener("click", (e) => { if (e.target.id === "sceneOverlay") closeScene(); });
  $("#sceneAccept").addEventListener("click", () => { const h = sceneAccept; closeScene(); if (h) h(); });
  const altSubmit = () => { const v = $("#sceneAltInput").value.trim(); closeScene(); if (v) handleAction(v); };
  $("#sceneAltForm").addEventListener("submit", (e) => { e.preventDefault(); altSubmit(); });
  $("#sceneAltInput").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); altSubmit(); } });
  $("#infoBtn").addEventListener("click", () => { $("#aboutOverlay").hidden = false; });
  $("#mapCloseBtn").addEventListener("click", () => window.parent.postMessage({ type: "worldwalker-map-close" }, location.origin));
  $("#aboutClose").addEventListener("click", () => { $("#aboutOverlay").hidden = true; });
  $("#aboutOverlay").addEventListener("click", (e) => { if (e.target.id === "aboutOverlay") e.currentTarget.hidden = true; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeScene(); $("#aboutOverlay").hidden = true; $("#directorPop").hidden = true; $("#diagDrawer").hidden = true; } });

  // Default: Live Worldwalker if the read-only bridge can see a running campaign, else Real Campaign Copy.
  await LiveBridge.probe();
  applySource("live");
}
function centerN() {
  const { W, H } = stageSize(), c = state.camera;
  return { x: (W / 2 - c.px) / (W * c.s), y: (H / 2 - c.py) / (H * c.s) };
}

/* ---------- read-only guard + diagnostics ---------- */
function blockIfReadOnly(what) {
  if (!state.readOnly) return false;
  if (window.parent && window.parent !== window) {
    window.parent.postMessage({ type: "worldwalker-map-action", action: what || "" }, location.origin);
    return true;
  }
  const live = state.sourceKey === "live";
  openScene({
    bg: "assets/scenes/battlefield_dusk.webp", portrait: monogram("↺", "var(--gold-bright)", "lg"),
    kicker: live ? "LIVE — READ-ONLY" : "READ-ONLY CAMPAIGN MIRROR",
    title: live ? "Live map is read-only" : "Action not applied",
    narrative: live
      ? "Live map is read-only in this milestone. Enter actions in Worldwalker."
      : "Read-only campaign mirror. Future integration would send this action to the Worldwalker engine.",
    context: [["Requested", what || "(freeform action)"],
      ["Data source", live ? "Live Worldwalker" : "Real Campaign Copy"],
      ["Authority", "Worldwalker only"], ["Mutations", "disabled"]],
    acceptLabel: "Understood", onAccept: () => {},
  });
  return true;
}

function renderDiagnostics() {
  const box = $("#diagBody");
  const d = state.diagnostics;
  if (!d) { box.innerHTML = `<p class="diag-note">Diagnostics apply to <b>Real Campaign Copy</b> and <b>Live Worldwalker</b>. Switch the data source (top bar) to inspect them.</p>`; return; }
  const row = (k, v) => `<div class="diag-row"><span>${esc(k)}</span><b>${esc(v)}</b></div>`;
  const list = (title, arr) => arr && arr.length
    ? `<div class="diag-sub"><h5>${esc(title)} (${arr.length})</h5><ul>${arr.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : "";
  const lp = state.sourceKey === "live" ? (state._live || {}) : {};
  box.innerHTML =
    (state.sourceKey === "live" ? row("Live status", lp.statusText || "—") + row("Polls", lp.polls || 0) +
      row("Last change", lp.lastChangeAgo || "—") + row("Bridge target", lp.target || "—") : "") +
    row("Source", d.saveFile) +
    row("Save version / schema", d.saveVersion + " / schema " + d.schemaVersion) +
    row("World", d.world) +
    row("Campaign", d.campaignName) +
    row("Campaign turn", d.turn) +
    row("World date", d.worldTime) +
    row("Canon day", d.canonDay) +
    row("Next canon event", d.primaryCanon) +
    row("Resolved current player location", d.playerLocation || "—") +
    row("Resolved locations", d.resolvedLocations) +
    row("Unresolved locations", d.unresolvedLocations) +
    row("Approximate locations", (d.approximateLocations || []).length) +
    row("Alias matches", (d.aliasMatches || []).length) +
    row("Mapped NPCs", d.mappedNpcs) +
    row("Unmapped NPCs", d.unmappedNpcs) +
    row("Active quests", d.activeQuests) +
    row("World events", d.worldEvents) +
    row("Canon events fired", d.canonEventsFired) +
    row("Organizations", d.organizations) +
    row("Faction clocks", d.factionClocks) +
    row("Travel-graph nodes", d.travelGraphNodes) +
    row("Chronicle entries loaded", d.chronicleEntries) +
    list("Resolved event locations", d.eventLocations) +
    list("Resolved NPC locations", d.npcLocations) +
    list("Approximate locations", d.approximateLocations) +
    list("Alias matches", d.aliasMatches) +
    list("Unresolved location names", d.unresolvedNames) +
    list("Mapped NPCs", d.mappedNpcNames) +
    list("Unmapped NPCs", d.unmappedNpcNames) +
    list("Organization rosters", d.orgRosterLines) +
    (d.notes && d.notes.length ? `<div class="diag-sub"><h5>Adapter notes</h5><ul>${d.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></div>` : "");
}
function centerN() {
  const { W, H } = stageSize(), c = state.camera;
  return { x: (W / 2 - c.px) / (W * c.s), y: (H / 2 - c.py) / (H * c.s) };
}

document.addEventListener("DOMContentLoaded", boot);
