"use strict";
/* Worldwalker RPG — frontend engine: API glue, rendering, animation, sound. */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));
const AUTH_TOKEN_STORAGE_KEY = "worldwalker_friend_auth_token";

function storedAuthToken() {
  try { return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || ""; }
  catch (_) { return ""; }
}

function persistAuthToken(value) {
  try {
    if (value) window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, value);
    else window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  } catch (_) { /* A normal session cookie can still carry the login. */ }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const CURRENCY_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M9.2 14.8c.4 1 1.5 1.7 2.8 1.7 1.7 0 2.8-.9 2.8-2s-1.1-1.7-2.8-2c-1.7-.3-2.8-.9-2.8-2s1.1-2 2.8-2c1.3 0 2.4.7 2.8 1.7"/><path d="M12 7.2v1.1M12 15.7v1.1"/></svg>';
// Shops are only loosely specified in the GM prompt, so an inventory item's
// price might be a plain number or free text like "50 Berries" — mirrors
// backend systems.py's parse_price() so the Buy button only appears/enables
// when the server-side purchase would actually succeed.
function parsePriceClient(value) {
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, value);
  if (typeof value === "string") {
    const m = value.replace(/,/g, "").match(/\d+(?:\.\d+)?/);
    if (m) return Math.max(0, parseFloat(m[0]));
  }
  return null;
}
function formatCurrencyClient(currency, includeName = true) {
  const c = currency && typeof currency === "object" ? currency : {};
  const scale = Number(c.minor_per_major || 0);
  if (scale > 1) {
    let minor = Math.round(Number(c.amount_minor ?? (Number(c.amount || 0) * scale)));
    const sign = minor < 0 ? "−" : "";
    minor = Math.abs(minor);
    const gold = Math.floor(minor / scale), remainder = minor % scale;
    const silver = Math.floor(remainder / 100), copper = remainder % 100;
    const parts = [];
    if (gold) parts.push(`${gold.toLocaleString()} Gold`);
    if (silver) parts.push(`${silver} Silver`);
    if (copper || !parts.length) parts.push(`${copper} Copper`);
    return sign + parts.join(" ");
  }
  const amount = Number(c.amount || 0).toLocaleString(undefined, { maximumFractionDigits: 4 });
  return includeName ? `${amount} ${c.name || "Currency"}` : amount;
}
function currencyRowHtml(name, amount, metadata = null) {
  const display = metadata ? formatCurrencyClient(metadata, true) : `${Number(amount || 0).toLocaleString(undefined, { maximumFractionDigits: 4 })} ${name || "Currency"}`;
  return `<div class="jrow currency-jrow"><i class="currency-icon">${CURRENCY_ICON_SVG}</i><b>${escapeHtml(display)}</b></div>`;
}
function currencyBalanceClient(data, name) {
  const primary = data.currency || {};
  if (!name || String(name).toLowerCase() === String(primary.name || "").toLowerCase()) return Number(primary.amount || 0);
  const entries = Object.entries(data.currencies || {});
  const found = entries.find(([key]) => String(key).toLowerCase() === String(name).toLowerCase());
  if (!found) return 0;
  return Number(found[1] && typeof found[1] === "object" ? found[1].amount : found[1]) || 0;
}
// A title is USUALLY a plain string, but a model that mimics the shape of
// its own context occasionally hands one back as {name/title: "..."} —
// naive escapeHtml(title) on that renders literal "[object Object]".
function titleLabel(t) {
  return (t && typeof t === "object" ? compactReadable(t.name || t.title) : "") || compactReadable(t) || "Title";
}

// One compact identity resolver powers every secondary portrait surface.
// Explicit campaign art always wins, followed by approved bundled canon art.
// Unknown people use initials rather than a misleading generic face.
const CANON_PORTRAIT_BY_NAME = new Map(Object.entries({
  "monkey d luffy": "luffy_departure.webp", "luffy": "luffy_departure.webp",
  "roronoa zoro": "zoro_shells.webp", "zoro": "zoro_shells.webp",
  "gon freecss": "gon_departure.webp", "gon": "gon_departure.webp",
  "kurapika": "kurapika_exam.webp", "naruto uzumaki": "naruto_graduation.webp", "naruto": "naruto_graduation.webp",
  "yahiko": "yahiko_akatsuki.webp", "pain": "pain_birth.webp", "nagato": "pain_birth.webp",
  "kang jinhyeok": "jinhyeok_tower.webp", "kang jinhyuk": "jinhyeok_tower.webp", "jinhyeok": "jinhyeok_tower.webp",
  "grid": "grid_pagma.webp", "rimuru tempest": "rimuru_awakens.webp", "rimuru": "rimuru_awakens.webp",
  "ichigo kurosaki": "ichigo_series_start.webp", "ichigo": "ichigo_series_start.webp",
  "yuji itadori": "yuji_finger.webp", "yuji": "yuji_finger.webp", "satoru gojo": "gojo_inventory.webp", "gojo": "gojo_inventory.webp",
  "yuta okkotsu": "yuta_enrolls.webp", "yuta": "yuta_enrolls.webp", "megumi fushiguro": "megumi_finger.webp", "megumi": "megumi_finger.webp",
  "maki zenin": "maki_second_year.webp", "maki": "maki_second_year.webp",
}));
const CANON_PORTRAIT_BY_ID = {
  luffy_departure: "luffy_departure.webp", zoro_shells: "zoro_shells.webp", gon_departure: "gon_departure.webp",
  kurapika_exam: "kurapika_exam.webp", naruto_birth: "naruto_birth.webp", naruto_graduation: "naruto_graduation.webp",
  yahiko_akatsuki: "yahiko_akatsuki.webp", pain_birth: "pain_birth.webp", jinhyeok_tower: "jinhyeok_tower.webp",
  grid_pagma: "grid_pagma.webp", rimuru_awakens: "rimuru_awakens.webp", ichigo_series_start: "ichigo_series_start.webp",
  yuji_finger: "yuji_finger.webp", gojo_inventory: "gojo_inventory.webp", yuta_enrolls: "yuta_enrolls.webp",
  megumi_finger: "megumi_finger.webp", maki_second_year: "maki_second_year.webp",
};
function normalizePersonName(value) {
  return String(value || "").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, " ").trim();
}
function safePortraitUrl(value) {
  const url = String(value || "").trim();
  return /^\/(?:assets|portrait-cache)\//.test(url) ? url : "";
}
function portraitUrlForPerson(name, record = {}, state = APP.state || {}) {
  const person = record && typeof record === "object" ? record : {};
  const explicit = safePortraitUrl(person.portrait_url || person.portrait || person.image_url || person._portrait_image);
  if (explicit) return explicit;
  if (normalizePersonName(name) === normalizePersonName(state.name)) return safePortraitUrl(state._portrait_image);
  const canonId = String(person.canon_character_id || person.canon_id || person.identity || "").trim();
  const file = CANON_PORTRAIT_BY_ID[canonId] || CANON_PORTRAIT_BY_NAME.get(normalizePersonName(name));
  return file ? `/assets/canon_portraits/${file}` : "";
}
function personInitials(name) {
  return String(name || "?").trim().split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "?";
}
function personPortraitHtml(name, record = {}, options = {}) {
  const url = portraitUrlForPerson(name, record, options.state || APP.state || {});
  const size = options.size || "sm";
  const classes = ["person-portrait", `person-portrait-${size}`, options.className || "", url ? "has-image" : "portrait-initials"].filter(Boolean).join(" ");
  const content = url ? `<img src="${escapeHtml(url)}" alt="">` : `<span aria-hidden="true">${escapeHtml(personInitials(name))}</span>`;
  const label = options.label || `${name || "Unknown person"} portrait`;
  return `<span class="${classes}" title="${escapeHtml(name || "Unknown person")}" role="img" aria-label="${escapeHtml(label)}" data-person-open="${escapeHtml(name || "")}">${content}</span>`;
}
function knownPersonRecords(state = APP.state || {}) {
  return { ...(state.contacts || {}), ...(state.npc_memories || {}) };
}
function mentionedPortraitsHtml(text, records = knownPersonRecords(), max = 3, size = "sm") {
  const haystack = normalizePersonName(text);
  if (!haystack) return "";
  const names = new Set([...Object.keys(records || {}), ...CANON_PORTRAIT_BY_NAME.keys()]);
  const matches = [...names].filter((name) => {
    const normalized = normalizePersonName(name);
    return normalized.length > 2 && (` ${haystack} `).includes(` ${normalized} `);
  }).sort((a, b) => b.length - a.length);
  const unique = [];
  matches.forEach((name) => {
    if (unique.some((existing) => normalizePersonName(existing).includes(normalizePersonName(name)) || normalizePersonName(name).includes(normalizePersonName(existing)))) return;
    unique.push(name);
  });
  const shown = unique.slice(0, max);
  return shown.length ? `<span class="portrait-stack" aria-label="People involved">${shown.map((name) => personPortraitHtml(name, records[name] || {}, { size })).join("")}</span>` : "";
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------
// Transport and retry handling live in api-client.js.

// Phone-host helper and future hosted-PWA support. API calls remain network
// only, so a phone never continues an outdated simulation while disconnected.
function initPhoneMode() {
  const params = new URLSearchParams(window.location.search);
  const phoneUrl = params.get("lan_url");
  if (params.get("phone_host") === "1" && phoneUrl) {
    document.body.classList.add("phone-hosting");
    $("#phone-host-url").textContent = phoneUrl;
    $("#phone-host-banner").hidden = false;
    $("#btn-copy-phone-url").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(phoneUrl); showToast("Phone address copied.", "notify"); }
      catch (_) { window.prompt("Copy this address:", phoneUrl); }
    });
  }
  // The pywebview desktop shell always talks to its own same-machine Flask
  // server, so there is no offline scenario for it to guard against — only
  // register for a real browser tab (e.g. a phone connecting over LAN),
  // where `window.pywebview` (injected by pywebview itself) is absent.
  if ("serviceWorker" in navigator && window.isSecureContext) {
    if (window.pywebview) {
      // Tear down any worker a previous desktop build left registered —
      // an already-active one keeps controlling this page (and serving
      // whatever it cached) indefinitely, even after the page itself
      // stops calling register(). This is a one-time cleanup, not a
      // recurring cost: once nothing is registered, this is a no-op.
      navigator.serviceWorker.getRegistrations().then((regs) => regs.forEach((r) => r.unregister())).catch(() => {});
    } else {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
  }
}
initPhoneMode();

// ---------------------------------------------------------------------------
// Global app state
// ---------------------------------------------------------------------------
const APP = {
  accountsEnabled: false,
  account: null,
  csrfToken: "",
  authToken: storedAuthToken(),
  worldsMeta: null,
  state: null,
  campaignActive: false,
  busy: false,
  soundEnabled: true,
  musicEnabled: true,
  animationsEnabled: true,
  music: { world: "", tracks: [], index: 0, userStarted: false },
  musicVolume: 0.35,
  multiplayer: null,
  multiplayerLastResult: 0,
  multiplayerPoll: null,
  activeChatThread: null,
  pendingLethal: null,   // {kind:'action'|'timeskip', action, assessment, timeskip:{...}}
  pendingPowerGoal: null, // the time-skip payload awaiting confirmed_power_goal
  pendingAdvance: null,
  pendingManualRoll: null,
  pendingDifficulty: null,
  challenge: null,
  pendingCampaign: null,
  pendingPreview: null,
  journalTab: "party",
  portraitAttempted: new Set(),
  portraitInFlight: false,
  deferPortraitGeneration: false,
  lastChapterCount: null,
  statusWindowOpen: false,
  lastLocation: null,
  lastCombatActive: false,
  lastMajorVisualKey: "",
  lastPortraitFormVisual: "",
  lastVisualState: null,
  lastEffectSignature: "",
  effectTimer: null,
  activeWorldCue: null,
  narutoDeathCueActive: false,
  mobileView: "chronicle",
  mobileStoryFilter: "all",
  mobileInstallPrompt: null,
  mobileLowData: false,
  mobileHaptics: true,
  mobileLargeText: false,
  mobileScrollCampaign: "",
  serverReachable: null,
  serverProbeTimer: null,
  trophyPrompted: new Set(),
  versionInfo: null,
};

function patchNotesStorageKey(version) {
  const account = APP.account?.id || APP.account?.username || APP.account?.name || "local-player";
  return `worldwalker_patch_notes_seen:${account}:${version}`;
}

function dismissPatchNotes() {
  const version = (APP.versionInfo?.build_id || APP.versionInfo?.version);
  if (version) {
    try { window.localStorage.setItem(patchNotesStorageKey(version), "1"); } catch (_) {}
  }
  closeModal("modal-patch-notes");
}

async function maybeShowPatchNotes() {
  try {
    APP.versionInfo = await apiGet(`/api/version?patch_notes=${Date.now()}`);
    const notes = APP.versionInfo.patch_notes || {};
    if (!APP.versionInfo.version) return;
    try { if (window.localStorage.getItem(patchNotesStorageKey(APP.versionInfo.build_id || APP.versionInfo.version)) === "1") return; } catch (_) {}
    $("#patch-notes-heading").textContent = notes.title || "Worldwalker Updated";
    $("#patch-notes-version").textContent = `BUILD ${APP.versionInfo.build_id || APP.versionInfo.version}`;
    $("#patch-notes-summary").textContent = notes.summary || "A new version is ready.";
    $("#patch-notes-list").innerHTML = (notes.highlights || []).map((row) => `<article><b>${escapeHtml(row.title || "Improvement")}</b><p>${escapeHtml(row.example || "")}</p></article>`).join("");
    openModal("modal-patch-notes");
  } catch (_) { /* Patch notes must never block the game boot. */ }
}

$("#btn-patch-notes-done").addEventListener("click", dismissPatchNotes);
$("#modal-patch-notes .modal-close").addEventListener("click", () => {
  const version = (APP.versionInfo?.build_id || APP.versionInfo?.version);
  if (version) try { window.localStorage.setItem(patchNotesStorageKey(version), "1"); } catch (_) {}
});

function setHostConnectionState(connected, message = "") {
  const wasUnavailable = APP.serverReachable === false;
  APP.serverReachable = connected;
  document.documentElement.classList.toggle("host-unreachable", !connected);
  const status = $("#asset-recovery-status");
  const title = $("#asset-recovery-title");
  const banner = $("#mobile-network-banner");
  if (!connected) {
    if (title) title.textContent = "Reconnecting to Worldwalker";
    if (status) status.textContent = message || "Keep Phone Mode open on the PC, keep the PC awake, and make sure both devices are on the same Wi-Fi.";
    if (banner) {
      banner.hidden = false;
      banner.textContent = "The game host is unavailable. Your typed draft remains on this phone.";
    }
  } else if (banner) {
    banner.hidden = true;
    banner.textContent = "";
  }
  return wasUnavailable;
}

async function probeGameServer({ restoreState = false } = {}) {
  if (!navigator.onLine) {
    setHostConnectionState(false, "This phone is offline. Reconnect to the same Wi-Fi as the Worldwalker PC.");
    return false;
  }
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 4500);
  try {
    const response = await fetch(`/api/version?connection_check=${Date.now()}`, {
      cache: "no-store", signal: controller.signal, headers: { "Accept": "application/json" },
    });
    if (!response.ok) throw new Error(`Host returned ${response.status}`);
    const wasUnavailable = setHostConnectionState(true);
    if (wasUnavailable && restoreState && APP.campaignActive) {
      const result = await apiGet("/api/state");
      renderState(result.state);
      showToast("Reconnected to the campaign.", "notify");
    }
    return true;
  } catch (_) {
    setHostConnectionState(false, "The phone cannot reach the Worldwalker PC. Keep Phone Mode open, prevent the PC from sleeping, and confirm both devices are on the same Wi-Fi.");
    return false;
  } finally {
    window.clearTimeout(timeout);
  }
}

window.worldwalkerRetry = async () => {
  const status = $("#asset-recovery-status");
  if (status) status.textContent = "Checking the Worldwalker host…";
  if (await probeGameServer({ restoreState: true })) window.location.reload();
};

// ---------------------------------------------------------------------------
// Sound
// ---------------------------------------------------------------------------
function playSfx(name) {
  if (!APP.soundEnabled) return;
  const el = document.getElementById("snd-" + name);
  if (!el) return;
  const worldPitch = {
    "One Piece": 0.94,
    "Hunter x Hunter": 1.02,
    "Naruto": 1.08,
    "Solo Max-Level Newbie": 1.15,
    "Overgeared": 0.88,
    "Reincarnated as a Slime": 1.04,
    "Bleach": 0.97,
    "Custom": 1,
  };
  const worldGain = {
    "One Piece": .82, "Hunter x Hunter": .76, "Naruto": .84,
    "Solo Max-Level Newbie": .72, "Overgeared": .9,
    "Reincarnated as a Slime": .7, "Bleach": .78, "Custom": .8,
  };
  try {
    // Give each interface its own subtle audio character without multiplying
    // the size of the installation with another full sound pack.
    el.playbackRate = worldPitch[APP.state?.world] || 1;
    el.volume = worldGain[APP.state?.world] || .8;
    el.currentTime = 0;
    el.play().catch(() => {});
  } catch (e) {}
}

const WORLD_CUE_VOLUMES = {
  naruto_advance: .58,
  naruto_character_start: .7,
  naruto_pain_start: .78,
  naruto_death: .76,
};

function stopWorldCue(restoreMusic = true) {
  const cue = APP.activeWorldCue;
  if (cue) {
    try { cue.pause(); cue.currentTime = 0; } catch (_) {}
    APP.activeWorldCue = null;
  }
  const player = musicPlayer();
  if (restoreMusic && player && !player.paused) fadeAudioTo(player, APP.musicVolume ?? .35, 350);
}

function playWorldCue(name) {
  if (!APP.soundEnabled) return;
  const el = document.getElementById("snd-" + name);
  if (!el) return;
  if (APP.activeWorldCue && APP.activeWorldCue !== el) stopWorldCue(false);
  const player = musicPlayer();
  const shouldDuckMusic = player && !player.paused;
  if (shouldDuckMusic) fadeAudioTo(player, Math.min(.1, APP.musicVolume ?? .35), 180);
  APP.activeWorldCue = el;
  try {
    el.playbackRate = 1;
    el.volume = WORLD_CUE_VOLUMES[name] ?? .72;
    el.currentTime = 0;
    el.onended = () => {
      if (APP.activeWorldCue !== el) return;
      APP.activeWorldCue = null;
      if (shouldDuckMusic && !player.paused) fadeAudioTo(player, APP.musicVolume ?? .35, 450);
    };
    el.play().catch(() => {
      if (APP.activeWorldCue === el) APP.activeWorldCue = null;
      if (shouldDuckMusic && !player.paused) fadeAudioTo(player, APP.musicVolume ?? .35, 250);
    });
  } catch (_) {
    if (APP.activeWorldCue === el) APP.activeWorldCue = null;
  }
}

function playNarutoAdvanceCue() {
  if (APP.state?.world === "Naruto") playWorldCue("naruto_advance");
}

function playCampaignStartCue(campaign) {
  if (campaign?.world !== "Naruto") { playSfx("world_event"); return; }
  if (campaign.canon_character_id === "pain_birth") playWorldCue("naruto_pain_start");
  else if (!campaign.canon_character_id) playWorldCue("naruto_character_start");
  else playSfx("world_event");
}

function playDeathCue() {
  if (APP.state?.world !== "Naruto") { playSfx("danger"); return; }
  if (APP.narutoDeathCueActive) return;
  APP.narutoDeathCueActive = true;
  playWorldCue("naruto_death");
}

function playNewCanonEventCues(previousState, nextState) {
  if (nextState?.world !== "Naruto") return;
  const previous = new Set(previousState?.canon_events_fired || []);
  const fresh = (nextState.canon_events_fired || []).filter((title) => !previous.has(title));
  if (fresh.some((title) => String(title).toLowerCase() === "pain's assault on konoha")) {
    playWorldCue("naruto_pain_start");
  }
}

// ---------------------------------------------------------------------------
// Portable world music — files live beside the EXE under music/<World>.
// ---------------------------------------------------------------------------
function musicPlayer() { return $("#music-player"); }

// Smooth fades instead of hard cuts when a track changes or the world's
// music context switches. `el._fadeTimer` lets a new fade cancel one already
// in flight instead of fighting over the volume value.
function fadeAudioTo(el, target, duration = 450) {
  clearInterval(el._fadeTimer);
  const start = el.volume;
  const delta = target - start;
  if (Math.abs(delta) < 0.005 || duration <= 0) { el.volume = Math.max(0, Math.min(1, target)); return; }
  const steps = Math.max(1, Math.round(duration / 30));
  let i = 0;
  el._fadeTimer = setInterval(() => {
    i += 1;
    el.volume = Math.max(0, Math.min(1, start + delta * (i / steps)));
    if (i >= steps) clearInterval(el._fadeTimer);
  }, duration / steps);
}

function renderMusicStatus(folder) {
  const current = APP.music.tracks[APP.music.index];
  $("#music-title").textContent = current ? `${current.name}${current.source === "Shared" ? " · Shared" : ""}` : "No music found";
  $("#music-help").textContent = current ? `${APP.music.index + 1} of ${APP.music.tracks.length} · ${APP.music.world}` : `Drop MP3/MP4 files into ${folder || `music/${APP.music.world}`}`;
  $("#btn-music-play").textContent = !musicPlayer().paused && current ? "❚❚" : "▶";
  $("#music-visualizer")?.classList.toggle("playing", !musicPlayer().paused && !!current);
}

function loadMusicTrack(index, playNow = false) {
  if (!APP.music.tracks.length) { renderMusicStatus(); return; }
  APP.music.index = (index + APP.music.tracks.length) % APP.music.tracks.length;
  const track = APP.music.tracks[APP.music.index];
  const player = musicPlayer();
  const targetVolume = APP.musicVolume ?? player.volume ?? 0.35;
  const switchingTrack = player.getAttribute("src") !== track.url;
  const swap = () => {
    if (switchingTrack) { player.src = track.url; player.load(); }
    renderMusicStatus();
    if (playNow && APP.musicEnabled) {
      player.volume = 0;
      player.play().then(() => { fadeAudioTo(player, targetVolume, 500); renderMusicStatus(); })
        .catch(() => { $("#music-help").textContent = "Press Play to start music."; });
    } else {
      fadeAudioTo(player, targetVolume, 350);
    }
  };
  if (switchingTrack && !player.paused) { fadeAudioTo(player, 0, 260); setTimeout(swap, 270); }
  else swap();
}

async function refreshMusic(world, keepPlaying = false) {
  const selectedWorld = world || APP.state?.world || "Custom World";
  const wasPlaying = !musicPlayer().paused || APP.music.userStarted;
  try {
    const data = await apiGet(`/api/music?world=${encodeURIComponent(selectedWorld)}`);
    const oldUrl = APP.music.tracks[APP.music.index]?.url;
    APP.music.world = data.world;
    APP.music.tracks = data.tracks || [];
    const sameIndex = APP.music.tracks.findIndex((track) => track.url === oldUrl);
    APP.music.index = sameIndex >= 0 ? sameIndex : 0;
    if (APP.music.tracks.length) loadMusicTrack(APP.music.index, keepPlaying && wasPlaying);
    else { musicPlayer().pause(); musicPlayer().removeAttribute("src"); renderMusicStatus(data.folder); }
  } catch (error) { $("#music-help").textContent = "Music folder could not be scanned."; }
}

async function openMusicFolder() {
  const result = await apiPost("/api/music/open_folder", { world: APP.state?.world || "Custom World" });
  showToast(`Opened music folder: ${result.folder}`, "system");
}

// ---------------------------------------------------------------------------
// Toasts + cinematic banner + screen fx
// ---------------------------------------------------------------------------
function showToast(message, tag, personName = "", personRecord = {}) {
  const stack = $("#toast-stack");
  const el = document.createElement("div");
  el.className = "toast " + (tag || "system");
  if (personName) el.innerHTML = `${personPortraitHtml(personName, personRecord, { size: "sm" })}<span>${escapeHtml(message)}</span>`;
  else el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => el.remove(), 5100);
}

const CINEMATIC_ICON = { level_up: "🎉", xp: "✦", notify: "★", danger: "⚠", message: "✉", world: "🌍", time: "⏳", damage: "💥", position: "👑", achievement: "🏆", canon_event: "⚡" };
function clearTransientFeedback() {
  const banner = $("#cinematic-banner");
  clearTimeout(banner._t);
  clearTimeout(banner._clearT);
  banner.classList.remove("show");
  banner.replaceChildren();
  $("#toast-stack").replaceChildren();
}

function showCinematic(type, message, worldSystem = "world") {
  const banner = $("#cinematic-banner");
  const icon = CINEMATIC_ICON[type] || "★";
  banner.innerHTML = `<div class="banner-card ${type === "danger" || type === "damage" ? "danger" : type === "achievement" ? "achievement" : type === "canon_event" ? "canon-event" : ""} ${worldSystem === "satisfy" ? "satisfy-system" : worldSystem === "tower" ? "tower-system" : ""}"><span class="banner-icon">${icon}</span><span>${escapeHtml(message)}</span></div>`;
  banner.classList.add("show");
  clearTimeout(banner._t);
  clearTimeout(banner._clearT);
  banner._t = setTimeout(() => {
    banner.classList.remove("show");
    banner._clearT = setTimeout(() => {
      if (!banner.classList.contains("show")) banner.replaceChildren();
    }, 500);
  }, 3200);
}

function flashScreen(kind) {
  const fx = $("#fx-layer");
  fx.classList.remove("flash-danger", "flash-success");
  void fx.offsetWidth;
  fx.classList.add(kind === "danger" ? "flash-danger" : "flash-success");
}

function shakeApp() {
  const shell = $(".app-shell");
  shell.classList.remove("shake");
  void shell.offsetWidth;
  shell.classList.add("shake");
}

function showWorldSystemNotice(notifications) {
  const world = APP.state?.world;
  if (!["Overgeared", "Solo Max-Level Newbie"].includes(world)) return;
  const messages = (notifications || []).map((row) => row?.display_message || row?.message).filter(Boolean).slice(0, 5);
  if (!messages.length) return;
  document.querySelector(".world-system-popup")?.remove();
  const popup = document.createElement("aside");
  popup.className = "world-system-popup";
  popup.dataset.system = world === "Overgeared" ? "satisfy" : "tower";
  popup.innerHTML = `<button type="button" aria-label="Close">×</button><small>${world === "Overgeared" ? "SATISFY NOTIFICATION" : "TOWER SYSTEM"}</small><b>${/quest/i.test(messages.join(" ")) ? "QUEST UPDATE" : "STATUS UPDATED"}</b><div>${messages.map((message) => `<p>${escapeHtml(message)}</p>`).join("")}</div>`;
  document.body.appendChild(popup);
  const close = () => popup.remove();
  popup.querySelector("button").addEventListener("click", close);
  window.setTimeout(close, 7500);
}

function handleNotifications(notifications) {
  showWorldSystemNotice(notifications);
  (notifications || []).forEach((n) => {
    const shownMessage = n.display_message || n.message;
    const records = knownPersonRecords();
    const explicitlyNamed = n.person || n.character || n.sender || n.npc || "";
    const inferredName = explicitlyNamed || Object.keys(records).find((name) => normalizePersonName(shownMessage).includes(normalizePersonName(name))) || "";
    const personName = typeof inferredName === "object" ? (inferredName.name || inferredName.display_name || "") : inferredName;
    const personRecord = personName ? (records[personName] || {}) : {};
    // Reserve the large cinematic interruption for genuinely major changes.
    // Routine stat, XP, and quest updates remain readable in the Chronicle.
    const majorCinematics = new Set(["level_up", "position", "danger", "damage", "achievement", "canon_event"]);
    const toastCinematics = new Set([...majorCinematics, "notify"]);
    if (toastCinematics.has(n.cinematic)) showToast(shownMessage, n.cinematic || n.tag, personName, personRecord);
    if (majorCinematics.has(n.cinematic)) {
      showCinematic(n.cinematic, shownMessage, n.world_system);
      if (n.cinematic === "level_up") { playSfx("level_up"); triggerAbilityEffect("growth", shownMessage); }
      else if (n.cinematic === "position") playSfx("level_up");
      else if (n.cinematic === "achievement") { playSfx("achievement"); triggerAbilityEffect("growth", shownMessage); }
      else if (n.cinematic === "xp") playSfx("xp");
      else if (n.cinematic === "danger") { playSfx("danger"); flashScreen("danger"); shakeApp(); triggerAbilityEffect("impact", shownMessage); }
      else if (n.cinematic === "damage") { playSfx("hit"); flashScreen("danger"); shakeApp(); triggerAbilityEffect("impact", shownMessage); }
      else if (n.cinematic === "canon_event") { playSfx("world_event"); flashScreen("danger"); shakeApp(); triggerAbilityEffect("canon", shownMessage); }
      else playSfx("notify");
    }
  });
}

// ---------------------------------------------------------------------------
// Chronicle — story beats are grouped and labelled instead of appearing as
// an undifferentiated stack of prose, rolls, and system boxes.
// ---------------------------------------------------------------------------
function storyEntryParts(entry) {
  const tag = entry.tag || "narrative";
  const raw = String(entry.text || "").trim().replace(/([.!?])\1+(?=[”"'’\s]|$)/g, "$1");
  const lines = raw.split("\n");
  const bracket = lines[0]?.match(/^\[([^\]]+)\]\s*$/);
  const labelByTag = { narrative: "Story", player: "Your action", system: "Notice", danger: "Urgent", roll: "Check", growth: "Growth", canon_event: "Major Canon Event" };
  const label = bracket ? bracket[1].replace(/[_-]+/g, " ") : (labelByTag[tag] || "Story");
  const body = bracket ? lines.slice(1).join("\n").trim() : raw.replace(/^>\s*/, "");
  return { tag, label, body: body || raw, hasOwnTitle: !!bracket };
}

function poneglyphTone(entry) {
  if (entry.detail?.chronicle_tone === "special" || ["canon_event", "danger", "reward", "discovery", "achievement"].includes(entry.tag)) return "special";
  // Legacy saves: classify explicit headings, never incidental words in prose.
  const heading = String(entry.text || "").match(/^\[([^\]]+)\]/)?.[1] || "";
  return /^(?:MAJOR (?:CANON )?EVENT|CANON EVENT|REWARD|LOOT|DISCOVERY|ACHIEVEMENT|TITLE ACQUIRED|LEVEL UP|BREAKTHROUGH)(?:\b|$)/i.test(heading) ? "special" : "standard";
}

function storyBeatLabel(entries) {
  const tags = new Set((entries || []).map((entry) => entry.tag || "narrative"));
  if (tags.has("danger")) return "Critical development";
  if (tags.has("player")) return "Player decision";
  if (tags.has("narrative")) return "Story beat";
  return "World update";
}

// Names/factions/locations the GM bolds are frequently the exact things a
// player doesn't yet know the meaning of ("Nen", "Haki", a faction name) —
// when a bolded term matches something already in the Codex, tie it back to
// that entry right where it's read instead of leaving the Codex as a
// separate tab the player has to remember to go check.
function codexLookup() {
  const codex = (APP.state && Array.isArray(APP.state.codex)) ? APP.state.codex : [];
  const map = new Map();
  codex.forEach((c) => { if (c && c.name) map.set(escapeHtml(String(c.name)).toLowerCase(), c); });
  return map;
}

// Bold a narrative's own proper nouns (the GM wraps them in **stars**, same
// convention as the update schema) — text is escaped first, so this can
// never introduce real markup, only <strong> around already-safe text.
function renderBoldedText(el, text) {
  const lookup = codexLookup();
  const escaped = escapeHtml(text).replace(/\*\*(.+?)\*\*/g, (whole, name) => {
    const entry = lookup.get(name.toLowerCase());
    if (!entry) return `<strong>${name}</strong>`;
    const hint = escapeHtml(String(entry.notes || entry.type || "No further detail recorded yet.")).slice(0, 220);
    return `<strong class="codex-term" data-codex-name="${escapeHtml(entry.name)}" title="${hint}">${name}</strong>`;
  });
  el.innerHTML = escaped;
}

// Hover already shows the native tooltip; a tap/click (phones have no
// hover) surfaces the same note as a toast and jumps straight to the full
// Codex entry for anyone who wants more than one line.
document.addEventListener("click", (e) => {
  const term = e.target.closest(".codex-term");
  if (!term) return;
  const name = term.getAttribute("data-codex-name") || "";
  const entry = ((APP.state && APP.state.codex) || []).find((c) => c && c.name === name);
  if (!entry) return;
  showToast(`${entry.name}${entry.type ? ` (${entry.type})` : ""}: ${entry.notes || "No further detail recorded yet."}`, "notify");
  APP.journalTab = "codex";
});

// Mirrors backend worlds.py's format_calendar_date/canon_day_to_calendar_parts
// exactly (same start days, same named months, same 30-day-month/12-month-year
// scheme) so the Chronicle's day-group headers read as real dates instead of
// the internal "Canon Day +7" counter, without a round trip per label.
const WORLD_START_DAY = {
  "One Piece": -7, "Hunter x Hunter": -7, "Naruto": -7, "Solo Max-Level Newbie": -3,
  "Overgeared": -3, "Reincarnated as a Slime": -7, "Custom World": -7,
};
const REAL_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const WORLD_CALENDAR_MONTHS = {
  "One Piece": REAL_MONTH_NAMES, "Naruto": REAL_MONTH_NAMES, "Hunter x Hunter": REAL_MONTH_NAMES,
  "Overgeared": REAL_MONTH_NAMES, "Reincarnated as a Slime": REAL_MONTH_NAMES,
};

function formatCalendarDate(world, canonDay, calendarEpoch, anchorDay) {
  return WorldCalendar.format(world, canonDay, calendarEpoch, anchorDay);
}

function dayLabel(canonDay) {
  const n = Number(canonDay);
  if (!Number.isFinite(n)) return "";
  const world = (APP.state && APP.state.world) || "Custom World";
  return formatCalendarDate(world, n, APP.state && APP.state.calendar_epoch, APP.state && APP.state.calendar_anchor_day);
}

// The Chronicle only ever grew by appending — nothing ever removed an old
// entry, so a long single play session (the normal way to use this app —
// nobody restarts mid-campaign) built up an ever-larger DOM tree over time.
// That's what actually made the app feel sluggish: more nodes for the
// browser to lay out and repaint on every scroll and re-render, not AI
// latency. Trimming old beats once the feed gets long keeps recent
// scrollback intact while capping how much the live DOM can grow — the
// full history still lives in the save file and Journal -> Chapters either
// way, this only bounds what stays mounted on screen.
const STORY_FEED_MAX_ENTRIES = 300;
function pruneStoryFeed(feed, maxEntries = STORY_FEED_MAX_ENTRIES) {
  let count = feed.querySelectorAll(".story-entry").length;
  while (count > maxEntries && feed.children.length > 1) {
    const oldest = feed.firstElementChild;
    if (!oldest) break;
    count -= oldest.querySelectorAll(".story-entry").length;
    oldest.remove();
  }
}

function appendStoryEntries(entries, options = {}) {
  const feed = $("#story-feed");
  if (!feed.children.length) feed._storyEntryIds = new Set();
  const seenIds = feed._storyEntryIds || (feed._storyEntryIds = new Set());
  const cleanEntries = (entries || []).filter((entry) => {
    if (!entry || !String(entry.text || "").trim() || (entry.id && seenIds.has(entry.id))) return false;
    if (entry.id) seenIds.add(entry.id);
    return true;
  });
  // Bound deduplication separately from visible scrollback.
  if (seenIds.size > 2400) feed._storyEntryIds = new Set([...seenIds].slice(-1200));
  if (!cleanEntries.length) return;
  const presentationWorld = APP.state?.world || document.body.dataset.world || "Custom World";
  const themedChronicle = new Set(["Naruto", "One Piece"]).has(presentationWorld);
  const turnEnvelope = themedChronicle ? document.createElement("article") : null;
  let firstNewBeat = null;
  if (turnEnvelope) {
    turnEnvelope.className = "world-turn-envelope";
    turnEnvelope.dataset.presentation = presentationWorld === "Naruto" ? "scroll" : "poneglyph";
    turnEnvelope.dataset.turn = APP.state?.turn || "";
  }
  triggerNarrativeVisuals(cleanEntries);
  // A multi-day skip returns entries stamped with different canon_day
  // values — split those into separate dated cards (like a history feed)
  // instead of lumping a whole week under one header. Entries without a
  // canon_day (ordinary single-action turns) merge into the current run.
  const runs = [];
  cleanEntries.forEach((entry) => {
    const day = entry.canon_day;
    const current = runs[runs.length - 1];
    const tone = presentationWorld === "One Piece" ? poneglyphTone(entry) : "standard";
    if (current && current.tone === tone && (day === undefined || day === null || day === current.day)) { current.entries.push(entry); return; }
    runs.push({ day, tone, entries: [entry] });
  });
  runs.forEach((run) => {
    const beat = document.createElement("section");
    const beatTags = new Set(run.entries.map((entry) => entry.tag || "narrative"));
    const beatKind = beatTags.has("canon_event") ? "canon" : beatTags.has("danger") ? "danger" : beatTags.has("growth") ? "growth" : beatTags.has("roll") ? "combat" : "story";
    beat.className = `story-beat story-beat-${beatKind}`;
    if (!firstNewBeat) firstNewBeat = beat;
    beat.dataset.beatKind = beatKind;
    const worldTime = String(run.entries.find((entry) => entry.world_time)?.world_time || "");
    const worldParts = worldTime.split(/\s+[—-]\s+/);
    const dateText = dayLabel(run.day) || (worldParts.length > 1 ? worldParts[0] : "");
    const clockLabel = worldParts.length > 1 ? worldParts.slice(1).join(" — ") : "";
    beat.innerHTML = `<header class="story-beat-head"><span>${escapeHtml(dateText || storyBeatLabel(run.entries))}</span>${clockLabel ? `<time>${escapeHtml(clockLabel)}</time>` : ""}<button type="button" class="mobile-beat-toggle" aria-expanded="true">Routine details</button></header>`;
    const entriesWrap = document.createElement("div");
    entriesWrap.className = "story-beat-entries";
    beat.appendChild(entriesWrap);
    let lastRow = null;
    // Only merge an entry into the previous one visually when NEITHER carries
    // its own AI-given title — that's the "two paragraphs of one flowing
    // scene" case. An entry with its own [TITLE] is a distinct, separately
    // dated/sequenced sub-event (e.g. several updates that all happen to
    // land on the same calendar day during a multi-day skip) and must keep
    // its own visible label — otherwise it silently reads as a continuation
    // of the previous event instead of a separate one.
    let lastWasUntitledNarrative = false;
    // Purely mechanical/administrative notices (an undo confirmation, a
    // stat-delta readout, "quest complete" bookkeeping) don't belong in the
    // middle of the story being told — collected here and rendered as one
    // collapsed strip at the end of the beat instead of a normal row, same
    // idea as the roll pill below but for things with no single narrative
    // line to attach to.
    const metaEntries = [];
    run.entries.forEach((entry) => {
      if (entry.tag === "receipt" && entry.detail?.schema === 1) {
        entriesWrap.appendChild(TurnFeedback.render(entry.detail));
        lastWasUntitledNarrative = false;
        return;
      }
      const part = storyEntryParts(entry);
      if (part.tag === "meta") {
        metaEntries.push(part);
        return;
      }
      // Attach a roll only when the preceding row is the action named by
      // its detail. Multi-action skips may return checks before their later
      // narrative cards; those checks stay as explicit rows so they can never
      // appear to belong to the final or otherwise unrelated queued action.
      if (part.tag === "roll" && lastRow) {
        const detailText = typeof entry.detail === "string" ? entry.detail : "";
        const actionMatch = detailText.match(/^Action:\s*(.*?)(?:\s+·|$)/);
        const actionText = actionMatch ? actionMatch[1].trim() : "";
        const rowText = lastRow.querySelector(".story-entry-copy")?.textContent?.trim() || "";
        if (actionText && rowText.includes(actionText)) {
          const pill = document.createElement("span");
          const positive = /SUCCESS|BREAKTHROUGH/.test(part.body);
          pill.className = "story-roll-pill " + (positive ? "hit" : "miss");
          pill.textContent = part.body.startsWith(actionText + " — ") ? part.body.slice(actionText.length + 3) : part.body;
          pill.title = detailText;
          lastRow.querySelector(".story-entry-copy")?.appendChild(pill);
          return;
        }
      }
      const div = document.createElement("div");
      const isContinuation = part.tag === "narrative" && !part.hasOwnTitle && lastWasUntitledNarrative;
      div.className = "story-entry " + part.tag + (isContinuation ? " continuation" : "");
      const sourceText = `${part.label} ${part.body}`;
      div.dataset.storyKind = part.tag === "roll" || /\bcombat\b/i.test(sourceText)
        ? "combat"
        : /\b(xp|level|stat|training|mastery|skill learned|breakthrough|growth)\b/i.test(sourceText)
          ? "growth"
          : part.tag === "narrative" || part.tag === "player" ? "story" : "world";
      lastWasUntitledNarrative = part.tag === "narrative" && !part.hasOwnTitle;
      const label = document.createElement("div");
      label.className = "story-entry-label";
      const labelText = document.createElement("span");
      labelText.textContent = part.label;
      label.appendChild(labelText);
      if (APP.multiplayer && entry.multiplayer_scope) {
        const scope = ["local", "shared", "reported"].includes(entry.multiplayer_scope)
          ? entry.multiplayer_scope : "local";
        const visibility = document.createElement("small");
        visibility.className = `story-visibility ${scope}`;
        visibility.textContent = scope === "local" ? "NEARBY" : scope.toUpperCase();
        visibility.title = scope === "local"
          ? "Only players close enough to witness this event receive it."
          : scope === "reported"
            ? "Your character learned this through a report, message, rumor, or broadcast."
            : "Every player receives this shared world event.";
        label.appendChild(visibility);
      }
      // bodyWrap (not body itself) is the grid's 2nd column — body keeps its
      // exact class/role as the typeText/renderBoldedText target either way,
      // but any richer beat extras below live as normal stacked children of
      // bodyWrap instead of extra grid siblings, so they can never fight the
      // label/body column placement no matter how many of them there are.
      const bodyWrap = document.createElement("div");
      bodyWrap.className = "story-entry-body";
      const body = document.createElement("div");
      body.className = "story-entry-copy";
      bodyWrap.appendChild(body);
      if (["narrative", "canon_event"].includes(part.tag)) {
        const correct = document.createElement("button");
        correct.type = "button";
        correct.className = "story-correct-entry";
        correct.textContent = "Correct this";
        correct.addEventListener("click", async () => {
          APP.correctionSource = { text: part.body, time: entry.world_time || dateText, entities: entry.detail?.entities || [] };
          try {
            await openJournal("corrections");
            if (APP.correctionSource.entities.length === 1) $("#correction-target").value = APP.correctionSource.entities[0];
            $("#correction-value").focus();
          } catch (error) { showToast(error.message, "danger"); }
        });
        bodyWrap.appendChild(correct);
      }
      div.append(label, bodyWrap);
      entriesWrap.appendChild(div);
      if (part.tag === "narrative" && APP.animationsEnabled && !themedChronicle) {
        typeText(body, part.body);
      } else if (part.tag === "narrative" || part.tag === "system" || part.tag === "canon_event") {
        renderBoldedText(body, part.body);
      } else {
        body.textContent = part.body;
      }
      // Only a dated multi-beat update carries this — a plain moment-to-
      // moment turn's entry.detail (if any) is the roll-tooltip string
      // handled above, never an object, so this can't misfire on those.
      if (entry.detail && typeof entry.detail === "object") {
        if (entry.detail.delivery) {
          const delivery = document.createElement("small");
          delivery.className = "story-delivery-source";
          delivery.textContent = entry.detail.delivery;
          label.appendChild(delivery);
        }
        if (entry.detail.entities && entry.detail.entities.length) {
          const chips = document.createElement("div");
          chips.className = "story-entry-chips";
          chips.innerHTML = entry.detail.entities.map((name) => `<span>${escapeHtml(name)}</span>`).join("");
          bodyWrap.insertBefore(chips, body);
        }
        if (entry.detail.quote && entry.detail.quote.text) {
          const quote = document.createElement("blockquote");
          quote.className = "story-entry-quote";
          quote.innerHTML = `<p>${escapeHtml(entry.detail.quote.text)}</p>` + (entry.detail.quote.speaker ? `<cite>— ${escapeHtml(entry.detail.quote.speaker)}</cite>` : "");
          bodyWrap.appendChild(quote);
        }
        if (entry.detail.map_changes && entry.detail.map_changes.length) {
          const details = document.createElement("details");
          details.className = "story-entry-map-changes";
          const n = entry.detail.map_changes.length;
          details.innerHTML = `<summary>${n} Map Change${n === 1 ? "" : "s"}</summary><ul>${entry.detail.map_changes.map((c) => `<li>${escapeHtml(c)}</li>`).join("")}</ul>`;
          bodyWrap.appendChild(details);
        }
        if (entry.detail.purchase_offer) {
          const offer = entry.detail.purchase_offer;
          const card = document.createElement("div");
          card.className = "story-purchase-offer";
          card.innerHTML = `<span class="story-purchase-offer-name">${escapeHtml(offer.item)}</span>` +
            (offer.vendor ? `<span class="story-purchase-offer-vendor">from ${escapeHtml(offer.vendor)}</span>` : "") +
            `<span class="story-purchase-offer-price">${escapeHtml(offer.price)} ${escapeHtml(offer.currency || "")}</span>` +
            `<button type="button" class="story-purchase-offer-buy" data-offer-buy="${escapeHtml(offer.id)}">Buy</button>`;
          bodyWrap.appendChild(card);
        }
      }
      lastRow = div;
    });
    if (metaEntries.length) {
      const strip = document.createElement("details");
      strip.className = "story-beat-system";
      strip.innerHTML = `<summary>System (${metaEntries.length})</summary>` +
        metaEntries.map((part) => `<div class="story-beat-system-row"><b>${escapeHtml(part.label)}</b><span>${escapeHtml(part.body)}</span></div>`).join("");
      entriesWrap.appendChild(strip);
    }
    if (presentationWorld === "One Piece") {
      const stone = turnEnvelope.cloneNode(false);
      stone.dataset.tone = run.tone;
      stone.appendChild(beat);
      feed.appendChild(stone);
    } else (turnEnvelope || feed).appendChild(beat);
  });
  if (turnEnvelope && presentationWorld !== "One Piece") feed.appendChild(turnEnvelope);
  pruneStoryFeed(feed);
  applyMobileStoryFilter(APP.mobileStoryFilter || "all");
  if (options.focusNew && firstNewBeat) {
    // A completed turn can contain several dated updates. Start at the first
    // one so the player reads downward instead of landing after the ending.
    // Desktop scrolls inside the Chronicle; mobile lets the Chronicle expand
    // and scrolls the page itself, so each layout needs its own scroll owner.
    requestAnimationFrame(() => {
      if (feed.scrollHeight > feed.clientHeight + 2) {
        // offsetTop is relative to offsetParent, and themed turn envelopes
        // introduce a different offsetParent than the Chronicle feed. Using
        // two unrelated offsetTop values made Naruto/One Piece calculate 0
        // and jump to the beginning of the entire campaign. Convert viewport
        // geometry into the feed's own scroll coordinates instead.
        const feedRect = feed.getBoundingClientRect();
        const beatRect = firstNewBeat.getBoundingClientRect();
        const target = feed.scrollTop + beatRect.top - feedRect.top - 8;
        feed.scrollTo({ top: Math.max(0, target), behavior: "auto" });
      } else {
        const pageTop = firstNewBeat.getBoundingClientRect().top + window.scrollY;
        window.scrollTo({ top: Math.max(0, pageTop - 12), behavior: "auto" });
      }
    });
  } else {
    feed.scrollTop = feed.scrollHeight + 400;
  }
}

function promptForTrophy(proposal) {
  if (!proposal?.id || APP.trophyPrompted.has(proposal.id) || document.querySelector(".trophy-consent")) return;
  APP.trophyPrompted.add(proposal.id);
  const overlay = document.createElement("div");
  overlay.className = "trophy-consent modal-overlay open";
  overlay.innerHTML = `<section class="trophy-consent-card" role="dialog" aria-modal="true" aria-labelledby="trophy-consent-title">
    <small>LEGACY KEEPSAKE PROPOSED</small>
    <h2 id="trophy-consent-title">${escapeHtml(proposal.title || "Campaign trophy")}</h2>
    <p>${escapeHtml(proposal.description || "Keep a permanent record of this moment in the trophy collection?")}</p>
    <div><button type="button" class="btn-ghost" data-trophy-choice="decline">LEAVE IT</button><button type="button" class="btn-primary" data-trophy-choice="accept">KEEP TROPHY</button></div>
  </section>`;
  document.body.appendChild(overlay);
  overlay.querySelectorAll("[data-trophy-choice]").forEach((button) => button.addEventListener("click", async () => {
    const accepted = button.dataset.trophyChoice === "accept";
    overlay.querySelectorAll("button").forEach((row) => row.disabled = true);
    try {
      const result = await apiPost("/api/trophies/resolve", { id: proposal.id, accepted });
      overlay.remove();
      if (result.story?.length) appendStoryEntries(result.story);
      if (result.state) renderState(result.state);
      showToast(accepted ? "Trophy added to your legacy collection." : "Trophy left behind.", "notify");
    } catch (error) {
      overlay.remove(); showToast(error.message, "danger");
    }
  }));
  overlay.querySelector("[data-trophy-choice='accept']")?.focus();
}

function checkTrophyProposals(state) {
  const proposal = (state?.trophy_proposals || []).find((row) => row?.id && !APP.trophyPrompted.has(row.id));
  if (proposal) window.setTimeout(() => promptForTrophy(proposal), 80);
}

function applyMobileStoryFilter(filter) {
  APP.mobileStoryFilter = filter || "all";
  $$("#mobile-chronicle-tools [data-story-filter]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.getAttribute("data-story-filter") === APP.mobileStoryFilter));
  });
  $$("#story-feed .story-entry").forEach((entry) => {
    entry.classList.toggle("mobile-filtered", APP.mobileStoryFilter !== "all" && entry.dataset.storyKind !== APP.mobileStoryFilter);
  });
  $$("#story-feed .story-beat").forEach((beat) => {
    const visible = Array.from(beat.querySelectorAll(".story-entry")).some((entry) => !entry.classList.contains("mobile-filtered"));
    beat.classList.toggle("mobile-empty", !visible);
  });
}

// Loading a save stays fast on its own — this fires as an unawaited
// follow-up right after, so the recap (if the real-world gap since the
// save was written was long enough) lands a moment later instead of
// blocking the load itself on an AI round trip.
function maybeFetchReentryRecap(state) {
  if (!state || !state._reentry_gap_hours) return;
  apiPost("/api/reentry_recap", {}).then((res) => {
    if (res.story && res.story.length) appendStoryEntries(res.story);
    if (res.state) renderState(res.state);
  }).catch(() => { /* best effort — a missed recap just means the world was silent this time */ });
}

function typeText(el, text) {
  const caret = document.createElement("span");
  caret.className = "typing-caret";
  let i = 0;
  const speed = text.length > 900 ? 2 : text.length > 400 ? 3 : 6; // chars per tick
  function tick() {
    i += speed;
    renderBoldedText(el, text.slice(0, i));
    el.appendChild(caret);
    if (i < text.length) requestAnimationFrame(tick);
    else caret.remove();
  }
  requestAnimationFrame(tick);
}

$("#btn-story-latest").addEventListener("click", () => {
  const feed = $("#story-feed");
  feed.scrollTo({ top: feed.scrollHeight, behavior: APP.animationsEnabled ? "smooth" : "auto" });
});

$("#btn-rate-turn-good").addEventListener("click", async () => {
  try {
    await apiPost("/api/turn/rate_good", {});
    showToast("Marked as a good turn — the GM will draw on it as a real example.", "notify");
  } catch (error) { showToast(error.message, "danger"); }
});

// ---------------------------------------------------------------------------
// State rendering
// ---------------------------------------------------------------------------
function setWidth(el, pct) { el.style.width = Math.max(0, Math.min(100, pct)) + "%"; }

function textList(value) {
  if (Array.isArray(value)) return value.map((x) => typeof x === "object" ? (x.text || x.name || JSON.stringify(x)) : String(x)).filter(Boolean);
  if (value && typeof value === "object") return Object.entries(value).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`);
  return value ? [String(value)] : [];
}
// Consequence chain (continuity.py): a short "why did this relationship end
// up here" trail attached to an NPC or faction. Most recent first, already
// capped server-side — this just renders it or omits the section entirely
// when there's nothing recorded yet.
function chainHistoryHtml(entries) {
  if (!Array.isArray(entries) || !entries.length) return "";
  const rows = entries.map((e) => `<li>${escapeHtml(e.event)}${e.canon_day != null ? ` <small>(Day ${escapeHtml(e.canon_day)})</small>` : ""}</li>`).join("");
  return `<p><b>History:</b></p><ul class="chain-history">${rows}</ul>`;
}

function questView(q, index = 0) {
  if (typeof q !== "object" || q === null) {
    return { name: String(q || `Quest ${index + 1}`), status: "Active", explanation: "No additional explanation has been discovered yet.", knowledge: [], conditions: [], objectives: [], branchState: {}, giver: "", locations: [], risks: [], firstStep: "", deadline: "", rewards: [], developments: [], commitments: [], optionalObjectives: [], progress: 0 };
  }
  const risks = textList(q.current_obstacles || q.risks || q.known_risks || q.consequences)
    .filter((value) => !/^no (?:immediate|specific|known) (?:pressure|danger|risk)/i.test(String(value || "")));
  return {
    name: q.name || q.title || `Quest ${index + 1}`,
    status: q.status || q.stage || "Active",
    explanation: q.explanation || q.description || q.notes || q.summary || "No additional explanation has been discovered yet.",
    knowledge: textList(q.discovered_clues || q.current_knowledge || q.knowledge || q.clues || q.known_facts),
    conditions: textList(q.clear_conditions || q.completion_conditions || q.conditions || q.objectives || q.objective),
    objectives: Array.isArray(q.objectives) ? q.objectives : [],
    branchState: q.branch_state && typeof q.branch_state === "object" ? q.branch_state : {},
    giver: q.giver || q.cause || q.employer || "",
    locations: textList(q.locations || q.location),
    risks,
    optionalObjectives: textList(q.optional_objectives),
    firstStep: q.next_hint || q.first_step || q.next_step || "",
    progress: Number(q.progress_percent || 0),
    deadline: q.deadline || "",
    rewards: textList(q.rewards || q.reward),
    developments: textList(q.developments || q.recent_developments),
    commitments: textList(q.commitments || q.promises),
  };
}

function triggerBlackFlash() {
  if (!APP.animationsEnabled) return;
  let fx = document.querySelector(".black-flash-fx");
  if (fx) fx.remove();
  fx = document.createElement("div");
  fx.className = "black-flash-fx";
  fx.setAttribute("aria-hidden", "true");
  fx.innerHTML = '<i></i><i></i><i></i><i></i><i></i><strong>BLACK FLASH</strong>';
  document.body.appendChild(fx);
  window.setTimeout(() => fx.remove(), 950);
}

// Short, non-blocking ability treatments live at the edge of the viewport.
// They communicate a major state change without covering the Chronicle or
// turning ordinary actions into modal interruptions.
function triggerAbilityEffect(kind, signature = "") {
  if (!APP.animationsEnabled || APP.mobileLowData) return;
  const effectSignature = `${kind}:${signature}`;
  if (effectSignature === APP.lastEffectSignature) return;
  APP.lastEffectSignature = effectSignature;
  window.clearTimeout(APP.effectTimer);
  document.querySelector(".ability-screen-fx")?.remove();
  const fx = document.createElement("div");
  fx.className = `ability-screen-fx ability-${kind}`;
  fx.setAttribute("aria-hidden", "true");
  fx.innerHTML = "<i></i><i></i><i></i><i></i><i></i><i></i>";
  document.body.appendChild(fx);
  APP.effectTimer = window.setTimeout(() => {
    fx.remove();
    if (APP.lastEffectSignature === effectSignature) APP.lastEffectSignature = "";
  }, kind === "domain" || kind === "bankai" ? 1550 : 1050);
}

function narrativeAbilityEffect(text) {
  const value = String(text || "");
  if (/\bBLACK FLASH\b/i.test(value)) return "black-flash";
  if (/\b(?:domain expansion|expands? (?:their |his |her )?domain|domain manifests?)\b/i.test(value)) return "domain";
  if (/\b(?:bankai|final release)\b/i.test(value) && /\b(?:activate|release|unleash|manifest|achiev|awaken|enter|use|invoke)\w*/i.test(value)) return "bankai";
  if (/\b(?:shikai|first release)\b/i.test(value) && /\b(?:activate|release|unleash|manifest|achiev|awaken|enter|use|invoke)\w*/i.test(value)) return "shikai";
  if (/\b(?:tailed beast|jinchuriki|jinchūriki|chakra cloak|nine[- ]tails|bijuu|bijū)\b/i.test(value) && /\b(?:transform|cloak|manifest|release|enter|activate|unleash)\w*/i.test(value)) return "bijuu";
  if (/\b(?:sharingan|rinnegan|byakugan|d[ōo]jutsu|mangeky[oō]|mystic eyes?)\b/i.test(value) && /\b(?:activate|awaken|open|manifest|use)\w*/i.test(value)) return "dojutsu";
  if (/\b(?:evolves?|evolution|transforms?|ascends?|awakens? a new form|class advancement)\b/i.test(value)) return "evolution";
  return "";
}

function triggerNarrativeVisuals(entries) {
  const candidates = (entries || []).filter((entry) => ["narrative", "growth", "canon_event", "danger"].includes(entry.tag || "narrative"));
  const joined = candidates.map((entry) => String(entry.text || "")).join("\n");
  const effect = narrativeAbilityEffect(joined);
  if (!effect) return;
  const signature = joined.slice(-180);
  if (effect === "black-flash") triggerBlackFlash();
  else triggerAbilityEffect(effect, signature);
}

function playTimeAdvanceEffect(amount, unit) {
  if (!APP.animationsEnabled || APP.mobileLowData) return;
  document.querySelector(".time-flow-fx")?.remove();
  const fx = document.createElement("div");
  fx.className = `time-flow-fx time-flow-${unit || "moment"}`;
  fx.setAttribute("aria-hidden", "true");
  const pages = [0, 1, 2, 3].map((index) => `<i style="--page:${index}"></i>`).join("");
  fx.innerHTML = `${pages}<span>${unit === "next_event" ? "NEXT EVENT" : unit === "moment" ? "NEXT BEAT" : `${Math.max(1, Number(amount || 1))} ${String(unit || "day").toUpperCase()}`}</span>`;
  document.body.appendChild(fx);
  window.setTimeout(() => fx.remove(), 900);
}

function questPresentation(world) {
  const presentations = {
    "Overgeared": { literal: true, tab_label: "Quests", rail_label: "Active Quest", empty_label: "No active quest", entry_label: "Quest", archive_label: "Completed / failed quests" },
    "Solo Max-Level Newbie": { literal: true, tab_label: "System Quests", rail_label: "Active Quest", empty_label: "No active quest", entry_label: "Quest", archive_label: "Completed / failed quests" },
    "Naruto": { literal: false, tab_label: "Mission Agenda", rail_label: "Current Assignment", empty_label: "No current assignment", entry_label: "Assignment", archive_label: "Mission history" },
    "One Piece": { literal: false, tab_label: "Voyage Log", rail_label: "Current Priority", empty_label: "No current priority", entry_label: "Priority", archive_label: "Past voyages and promises" },
    "Hunter x Hunter": { literal: false, tab_label: "Hunter Agenda", rail_label: "Current Case", empty_label: "No current case", entry_label: "Case", archive_label: "Closed cases and hunts" },
    "Bleach": { literal: false, tab_label: "Division Agenda", rail_label: "Current Order", empty_label: "No current order", entry_label: "Order", archive_label: "Completed orders and incidents" },
    "Reincarnated as a Slime": { literal: false, tab_label: "Journey Agenda", rail_label: "Current Concern", empty_label: "No current concern", entry_label: "Concern", archive_label: "Resolved concerns" },
  };
  return presentations[world] || { literal: false, tab_label: "Agenda", rail_label: "Current Direction", empty_label: "No current direction", entry_label: "Agenda", archive_label: "Past goals and outcomes" };
}

function humanLabel(value) {
  return String(value || "Detail").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function correctionReadable(value) {
  if (value === null || value === undefined) return "Not recorded";
  return typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
}

function compactReadable(value) {
  if (value === null || value === undefined || value === "") return "";
  if (Array.isArray(value)) return value.map(compactReadable).filter(Boolean).join("; ");
  if (typeof value === "object") return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  const text = String(value).trim();
  // Same JSON-string recovery as renderSkillCard: a field the model returned
  // as a JSON-encoded string instead of plain text would otherwise print its
  // literal braces/brackets straight into the UI.
  if ((text.startsWith("{") && text.endsWith("}")) || (text.startsWith("[") && text.endsWith("]"))) {
    try { return compactReadable(JSON.parse(text)); } catch (e) { /* not actually JSON */ }
  }
  return text;
}

function renderSkillCard(name, rawDetail) {
  if (rawDetail === null || rawDetail === undefined) rawDetail = {};
  if (typeof rawDetail === "string") {
    // The model occasionally returns a skill's detail as a JSON-encoded
    // string instead of an actual object — displaying that string verbatim
    // is exactly what shows up as literal {"rank":"B",...} brace-and-quote
    // soup in the Journal. Recover the real object when the string is
    // actually parseable JSON before falling back to showing it as text.
    const trimmed = rawDetail.trim();
    if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
      try { rawDetail = JSON.parse(trimmed); } catch (e) { /* not actually JSON — keep the original string */ }
    }
  }
  if (typeof rawDetail !== "object" || Array.isArray(rawDetail)) {
    return `<details class="skill-journal-card expandable-special-card"><summary><h3>✦ ${escapeHtml(name)}</h3><span class="expand-label"></span></summary><div class="expandable-special-body"><p>${escapeHtml(compactReadable(rawDetail) || "This skill has not been described yet.")}</p></div></details>`;
  }
  const detail = rawDetail;
  const rank = compactReadable(detail.rank ?? detail.tier ?? detail.level);
  const bonus = Number.isFinite(Number(detail.bonus)) ? Number(detail.bonus) : null;
  const category = compactReadable(detail.category);
  const effectType = compactReadable(detail.effect_type);
  const targetType = compactReadable(detail.target_type);
  const duration = Number(detail.duration_rounds || 0);
  const summary = compactReadable(detail.effect || detail.description || detail.summary) || "The exact practical effect has not been recorded yet.";
  const rows = [
    ["Combat use", detail.combat_usable ? [effectType && humanLabel(effectType), targetType && `targets ${humanLabel(targetType)}`, duration > 0 && `${duration} rounds`].filter(Boolean).join(" · ") : ""],
    ["How it works", detail.use || detail.activation || detail.usage || detail.requirements],
    ["Origin", detail.origin],
    ["Cost / limits", detail.limitation || detail.limitations || detail.cost || detail.drawback],
    ["How to improve", detail.growth_path || detail.growth || detail.next_steps],
    ["Developed applications", detail.developed_applications],
    ["Evolution history", detail.evolution_history],
  ].map(([label, value]) => [label, compactReadable(value)]).filter(([, value]) => value);
  const chips = [rank ? `<span>${escapeHtml(rank)}</span>` : "", category ? `<span>${escapeHtml(humanLabel(category))}</span>` : "", bonus !== null ? `<span>${bonus >= 0 ? "+" : ""}${escapeHtml(bonus)} check bonus</span>` : ""].filter(Boolean).join("");
  return `<details class="skill-journal-card expandable-special-card"><summary><h3>✦ ${escapeHtml(name)}</h3><div class="skill-summary-actions">${chips ? `<div class="skill-chips">${chips}</div>` : ""}<span class="expand-label"></span></div></summary><div class="expandable-special-body"><p class="skill-summary">${escapeHtml(summary)}</p>${rows.map(([label, value]) => `<div class="skill-detail"><b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span></div>`).join("")}</div></details>`;
}

function formatDuration(minutes) {
  const total = Math.max(0, Number(minutes || 0));
  if (total >= 1440) return `${Math.round(total / 144) / 10} day${total >= 2160 ? "s" : ""}`;
  if (total >= 60) return `${Math.round(total / 6) / 10} hour${total >= 90 ? "s" : ""}`;
  return `${Math.round(total)} minute${total === 1 ? "" : "s"}`;
}

function renderClassCard(rawClass) {
  const cls = rawClass && typeof rawClass === "object" ? { ...rawClass } : {};
  const rawDiscovery = cls.discovery && typeof cls.discovery === "object" ? cls.discovery : null;
  if (rawDiscovery?.concealed) {
    const publicName = rawDiscovery.public_name || "Unidentified Class Signature";
    const legacyAffinity = publicName.match(/^Unidentified (.+) Class$/i);
    cls.name = legacyAffinity ? `Unidentified Hidden Class — ${legacyAffinity[1]} affinity` : publicName;
    cls.description = rawDiscovery.clue || "A dormant class-shaped power is present, but its nature is not yet understood.";
    cls.effect = Number(rawDiscovery.progress || 0) < 70 ? "Some bonuses are already active; their exact source remains unclear." : cls.effect;
    if (Number(rawDiscovery.progress || 0) < 50) cls.signature_skill = "";
    if (Number(rawDiscovery.progress || 0) < 70) {
      cls.stat_bonuses = {};
      cls.limitation = "Use, appraisal, or class-relevant training is required to identify it.";
      cls.growth_path = "Experiment with the unusual capability and seek a way to appraise hidden paths.";
    }
  }
  if (!cls.name) return "";
  const bonuses = cls.stat_bonuses && typeof cls.stat_bonuses === "object"
    ? Object.entries(cls.stat_bonuses).map(([name, value]) => `${name} ${Number(value) >= 0 ? "+" : ""}${value}`).join(" · ")
    : "";
  const rows = [
    ["Class feature", cls.effect],
    ["Starting bonuses", bonuses],
    ["Signature skill", cls.signature_skill],
    ["Limits", cls.limitation],
    ["Advancement", cls.growth_path],
    ["World-scale balance", cls.canon_balance],
    ["Why it is rare", cls.rarity_reason],
  ].map(([label, value]) => [label, compactReadable(value)]).filter(([, value]) => value);
  const discovery = cls.discovery && typeof cls.discovery === "object" ? cls.discovery : null;
  const discoveryRow = discovery ? `<div class="class-discovery"><div><b>Discovery</b><span>${escapeHtml(discovery.stage || "dormant")} · ${escapeHtml(discovery.progress ?? 0)}%</span></div><i style="width:${Math.max(0, Math.min(100, Number(discovery.progress || 0)))}%"></i>${textList(discovery.reveal_requirements).length ? `<small>${textList(discovery.reveal_requirements).map(escapeHtml).join(" · ")}</small>` : ""}</div>` : "";
  return `<details class="skill-journal-card class-profile-card expandable-special-card"><summary><h3>◆ ${escapeHtml(cls.name)}</h3><div class="skill-summary-actions"><div class="skill-chips"><span>${escapeHtml(cls.kind || "Hidden Class")}</span><span>${escapeHtml(cls.rank || "Rare")}</span></div><span class="expand-label"></span></div></summary><div class="expandable-special-body"><p class="skill-summary">${escapeHtml(compactReadable(cls.description) || "A rare path whose full nature is still being discovered.")}</p>${discoveryRow}${rows.map(([label, value]) => `<div class="skill-detail"><b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span></div>`).join("")}</div></details>`;
}

function renderBleachReleases(special) {
  const profile = special?.["Zanpakuto Profile"] && typeof special["Zanpakuto Profile"] === "object" ? special["Zanpakuto Profile"] : {};
  const shikai = String(special?.Shikai || "Unachieved");
  const bankai = String(special?.Bankai || "Unachieved");
  const previewConcept = special?.PreviewConcept === true && !!profile.shikai_name;
  const achieved = (value) => !/^(?:unachieved|none|unknown|)$/i.test(value);
  const row = (label, value) => value ? `<div class="release-detail"><b>${escapeHtml(label)}</b><span>${escapeHtml(compactReadable(value))}</span></div>` : "";
  const shikaiDetails = `${previewConcept && !achieved(shikai) ? `<p class="hint">Previewed potential — this release is not yet achieved.</p>` : ""}${row("Release command", profile.release_command)}${row("Form", profile.shikai_form)}${row("Ability", profile.shikai_effect)}${row("Limits", profile.shikai_limitation)}${row("Counters", profile.shikai_counters)}`;
  const bankaiDetails = `${previewConcept && !achieved(bankai) ? `<p class="hint">Previewed potential — Bankai must still be earned in play.</p>` : ""}${row("Manifestation", profile.bankai_manifestation)}${row("Ability", profile.bankai_effect)}${row("Cost", profile.bankai_cost)}${row("Counters", profile.bankai_counters)}`;
  const shikaiCard = `<details class="release-card shikai-card expandable-special-card ${achieved(shikai) ? "awakened" : "sealed"}"><summary><header><span>始解</span><div><small>FIRST RELEASE</small><h3>${escapeHtml(achieved(shikai) ? (profile.shikai_name || shikai) : (previewConcept ? `Potential — ${profile.shikai_name}` : "Shikai — Unachieved"))}</h3></div><i class="expand-label"></i></header></summary><div class="expandable-special-body">${achieved(shikai) || previewConcept ? shikaiDetails : `<p>Learn the spirit's identity and true name through Jinzen, training, battle and a personal inner-world trial.</p>`}</div></details>`;
  const bankaiCard = `<details class="release-card bankai-card expandable-special-card ${achieved(bankai) ? "awakened" : "sealed"}"><summary><header><span>卍解</span><div><small>FINAL RELEASE</small><h3>${escapeHtml(achieved(bankai) ? (profile.bankai_name || bankai) : (previewConcept ? `Potential — ${profile.bankai_name}` : "Bankai — Unachieved"))}</h3></div><i class="expand-label"></i></header></summary><div class="expandable-special-body">${achieved(bankai) || previewConcept ? bankaiDetails : `<p>Requires an achieved Shikai, spirit manifestation, sufficient spiritual capacity and a character-specific mastery trial.</p>`}</div></details>`;
  return `<section class="bleach-release-grid">${shikaiCard}${bankaiCard}</section>`;
}

function renderJjkBirthSlot(slot) {
  if (!slot || typeof slot !== "object") return "";
  const rows = [
    ["Rule", slot.governing_rule], ["Activation", slot.activation], ["Targets", slot.targets],
    [slot.slot_type === "Heavenly Restriction" ? "Sacrifice" : "Limits", slot.sacrifice || slot.limitations],
    ["Applications", (slot.applications || []).map(row => typeof row === "object" ? `${row.name}: ${row.effect}${row.limitation ? ` — ${row.limitation}` : ""}` : row)],
    ["Costs", slot.costs], ["Counters", slot.counters], ["Weaknesses", slot.weaknesses], ["Enhancement", slot.enhancement], ["Growth", slot.growth_path],
    ["Domain potential", slot.domain_potential], ["Power", slot.power_grade],
  ].filter(([, value]) => compactReadable(value));
  return `<details class="world-system-card jjk-technique-card expandable-special-card" open><summary><header><small>${escapeHtml(slot.slot_type || "BIRTH SLOT")}</small><h3>${escapeHtml(slot.name || "Unrevealed")}</h3></header><span class="expand-label"></span></summary><div class="expandable-special-body">${rows.map(([label, value]) => `<div class="world-system-detail"><b>${escapeHtml(label)}</b><span>${escapeHtml(compactReadable(value))}</span></div>`).join("")}</div></details>`;
}

function worldIdentityLabel(state) {
  const special = state?.special || {}, world = state?.world;
  if (world === "One Piece") return special["Crew Role"] || special.Archetype || "Seafarer";
  if (world === "Hunter x Hunter") {
    const license = special["Hunter License"] || "Unlicensed", category = special["Nen Category"] || "Unknown";
    return !/^(?:unknown|none)$/i.test(category) ? `${license} · ${category} Nen` : license;
  }
  if (world === "Naruto") return special["Shinobi Rank"] || special.Archetype || "Shinobi";
  if (world === "Solo Max-Level Newbie") return special["System Class"] || special.Archetype || "Player";
  if (world === "Overgeared") return special.Class || "Player";
  if (world === "Reincarnated as a Slime") return special.Species || state.race || "Otherworlder";
  if (world === "Bleach") return special["Shinigami Rank"] || special.Archetype || "Soul Reaper";
  if (world === "Jujutsu Kaisen") return special.Grade || (special["Official Status"] || "Unassessed Sorcerer");
  return state?.class_profile?.name || special.Archetype || "Adventurer";
}

function renderNarutoLineagePanel(special = {}) {
  const profiles = [special["Kekkei Genkai Profile"], special["Dōjutsu Profile"]]
    .filter((profile) => profile && typeof profile === "object" && profile.name);
  const legacy = [
    ["Kekkei Genkai", special["Kekkei Genkai"]],
    ["Dōjutsu", special["Dōjutsu"]],
  ].filter(([, value]) => value && !/^(?:none|unknown|unawakened)$/i.test(String(value)));
  const knownNames = new Set(profiles.map((profile) => String(profile.name).toLowerCase()));
  legacy.forEach(([category, name]) => {
    if (!knownNames.has(String(name).toLowerCase())) profiles.push({ name, category, stage: "Established" });
  });
  const title = profiles.length ? profiles.map((profile) => profile.name).join(" + ") : "No special lineage awakened";
  const body = profiles.length ? profiles.map((profile) => {
    const rows = [
      ["Stage", profile.stage], ["Origin", profile.origin], ["Applications", profile.abilities],
      ["Limits", profile.limitations], ["Counters", profile.counters],
      ["Development", profile.growth_path], ["Canon parity", profile.canon_balance],
    ].filter(([, value]) => compactReadable(value));
    return `<section class="lineage-record"><header><small>${escapeHtml(profile.category || "Kekkei Genkai")}</small><h4>${escapeHtml(profile.name)}</h4></header>${rows.map(([label, value]) => `<div class="world-system-detail"><b>${escapeHtml(label)}</b><span>${escapeHtml(compactReadable(value))}</span></div>`).join("")}</section>`;
  }).join("") : `<div class="lineage-empty"><b>Ordinary shinobi development</b><span>This character currently relies on trained stats, learned jutsu, and chakra affinity rather than an inherited or original bloodline power.</span></div>`;
  return `<details class="world-system-card expandable-special-card naruto-lineage-system"><summary><span class="naruto-system-mark" aria-hidden="true">血</span><header><small>KEKKEI GENKAI & DŌJUTSU</small><h3>${escapeHtml(title)}</h3></header><span class="expand-label"></span></summary><div class="expandable-special-body lineage-records">${body}</div></details>`;
}

function renderNarutoJinchurikiPanel(host = {}) {
  if (!host?.beast) return "";
  const tails = Math.max(1, Math.min(10, Number(host.tails || 9)));
  const boosts = host.stat_boosts && typeof host.stat_boosts === "object" ? host.stat_boosts : {};
  const boostChips = Object.entries(boosts).map(([name, amount]) => `<span><b>+${escapeHtml(amount)}</b>${escapeHtml(name)}</span>`).join("");
  const reserve = Number(host.chakra_reserve_bonus_percent ?? Math.round((Number(host.reserve_multiplier || 1) - 1) * 100));
  const abilityList = (host.available_abilities || []).length
    ? host.available_abilities.map((ability) => `<li>${escapeHtml(compactReadable(ability))}</li>`).join("")
    : `<li>No deliberate access is available yet.</li>`;
  const locked = (host.locked_by_mastery || []).length
    ? `<details class="jinchuriki-nested"><summary>Abilities still locked <b>${escapeHtml(host.locked_by_mastery.length)}</b></summary><ul>${host.locked_by_mastery.map((ability) => `<li>${escapeHtml(compactReadable(ability))}</li>`).join("")}</ul></details>` : "";
  const drawbacks = (host.drawbacks || []).length
    ? `<details class="jinchuriki-nested danger"><summary>Risks and drawbacks <b>${escapeHtml(host.drawbacks.length)}</b></summary><ul>${host.drawbacks.map((row) => `<li>${escapeHtml(compactReadable(row))}</li>`).join("")}</ul></details>` : "";
  return `<details class="world-system-card expandable-special-card naruto-jinchuriki-system"><summary><span class="naruto-system-mark" aria-hidden="true">尾</span><header><small>JINCHŪRIKI</small><h3>${escapeHtml(host.beast)}</h3><p>${escapeHtml(host.mastery || "Unmastered")} · ${escapeHtml(Number(host.control || 0))}% control</p></header><span class="expand-label"></span></summary><div class="expandable-special-body jinchuriki-expanded"><figure class="jinchuriki-beast-figure"><div class="jinchuriki-beast-art" data-tails="${tails}" role="img" aria-label="Illustration of ${escapeHtml(host.beast)}"></div><figcaption>${escapeHtml(host.title || `${tails}-Tails`)} · ${escapeHtml(host.relationship || "Undeveloped bond")}</figcaption></figure><div class="jinchuriki-dossier"><section class="jinchuriki-status-strip"><div><small>SEAL</small><b>${escapeHtml(host.status || "Sealed host")}</b></div><div><small>CURRENT FORM</small><b>${escapeHtml(host.transformation_stage || "Base form")}</b></div><div><small>BOND</small><b>${escapeHtml(Number(host.bond_progress || 0))}%</b></div></section><section class="jinchuriki-boosts"><header><b>Host bonuses</b><span>Permanent mechanical gains from the sealed beast</span></header><div class="jinchuriki-boost-grid">${reserve ? `<span class="reserve-boost"><b>+${escapeHtml(reserve)}%</b>Chakra maximum</span>` : ""}${boostChips || `<span><b>0</b>Direct stat boosts while sealing is pending</span>`}</div></section><section class="jinchuriki-ability-section"><header><b>Abilities available now</b><span>${escapeHtml((host.available_abilities || []).length)} unlocked</span></header><ul>${abilityList}</ul></section>${locked}${drawbacks}<div class="jinchuriki-detail-grid"><div><b>Seal condition</b><span>${escapeHtml(compactReadable(host.seal) || "Not recorded")}</span></div><div><b>Beast natures</b><span>${escapeHtml(compactReadable(host.nature_transformations) || "Not recorded")}</span></div><div><b>Beast traits</b><span>${escapeHtml(compactReadable(host.beast_traits) || "Not recorded")}</span></div><div><b>Development path</b><span>${escapeHtml(compactReadable(host.progression) || "Build control and trust through play")}</span></div></div></div></div></details>`;
}

function renderNenPanel(nen = {}, special = {}, preview = false) {
  const discovered = String(nen.visibility || special["Nen Access"] || "Undiscovered") !== "Undiscovered";
  if (!discovered) {
    return `<details class="world-system-card expandable-special-card hxh-system nen-locked-panel" open><summary><span class="nen-aura-mark" aria-hidden="true">念</span><header><small>LATENT NEN</small><h3>Undiscovered</h3><p>Your aura identity already exists, but your character does not know it yet.</p></header><span class="expand-label"></span></summary><div class="expandable-special-body"><div class="world-system-detail"><b>What is visible</b><span>No affinity, Hatsu name, or ability mechanics are revealed before awakening.</span></div><div class="world-system-detail"><b>Discovery</b><span>Find a Nen teacher, survive a legitimate awakening, or encounter another setting-valid initiation. The ability revealed later remains the one fixed at creation.</span></div></div></details>`;
  }
  const hatsu = nen.hatsu_profile || {};
  const order = ["Enhancement", "Transmutation", "Conjuration", "Specialization", "Manipulation", "Emission"];
  const efficiency = nen.category_efficiency || {};
  const affinityNodes = order.map((name, index) => `<div class="nen-affinity-node n${index}${name === nen.category ? " primary" : ""}"><b>${escapeHtml(name)}</b><span>${escapeHtml(efficiency[name] ?? (name === nen.category ? 100 : "—"))}%</span></div>`).join("");
  const rows = [
    ["Governing effect", hatsu.effect || hatsu.governing_rule], ["Activation", hatsu.activation],
    ["Applications", hatsu.applications], ["Vows", hatsu.vows], ["Limits", hatsu.limitations],
    ["Counters", hatsu.counters], ["Aura cost", hatsu.aura_cost], ["Growth path", hatsu.growth_path],
  ].filter(([, value]) => compactReadable(value));
  return `<details class="world-system-card expandable-special-card hxh-system nen-profile-panel"${preview ? " open" : ""}><summary><span class="nen-aura-mark" aria-hidden="true">念</span><header><small>NEN PROFILE</small><h3>${escapeHtml(hatsu.name || special.Hatsu || "Developing Hatsu")}</h3><p>${escapeHtml(nen.category || special["Nen Category"] || "Unknown")} · Ten ${escapeHtml(nen.ten || 0)} · Zetsu ${escapeHtml(nen.zetsu || 0)} · Ren ${escapeHtml(nen.ren || 0)}</p></header><span class="expand-label"></span></summary><div class="expandable-special-body nen-profile-body"><section class="nen-affinity"><header><b>Aura affinity</b><span>Natural efficiency across the six Nen categories</span></header><div class="nen-affinity-graph"><div class="nen-hex-lines" aria-hidden="true"></div>${affinityNodes}<strong class="nen-affinity-core">${escapeHtml((nen.category || "?").slice(0, 1))}</strong></div></section><section class="nen-hatsu-dossier"><header><small>PERSONAL HATSU</small><h4>${escapeHtml(hatsu.name || "Developing Hatsu")}</h4><span>${escapeHtml(compactReadable(hatsu.category_mix) || nen.category || "Unknown")}</span></header>${rows.map(([label,value]) => `<div class="world-system-detail"><b>${escapeHtml(label)}</b><span>${escapeHtml(compactReadable(value))}</span></div>`).join("")}</section></div></details>`;
}

function renderActivityCard(eyebrow, title, rows, tone = "") {
  const valid = (rows || []).filter(([, value]) => value !== undefined && value !== null && compactReadable(value));
  if (!valid.length) return "";
  return `<details class="world-system-card expandable-special-card ${escapeHtml(tone)}"><summary><header><small>${escapeHtml(eyebrow)}</small><h3>${escapeHtml(compactReadable(title) || "Campaign record")}</h3></header><span class="expand-label"></span></summary><div class="expandable-special-body">${valid.map(([label,value]) => `<div class="world-system-detail"><b>${escapeHtml(label)}</b><span>${escapeHtml(compactReadable(value))}</span></div>`).join("")}</div></details>`;
}

function renderBleachActivity(data = {}) {
  const activity = data.world_activity?.bleach || {};
  const placement = activity.squad_placement || {}, relation = activity.zanpakuto_relationship || {}, duty = activity.duty || {};
  const kido = activity.kido_reference || {}, hado = Object.keys(kido.Hado || {}).length, bakudo = Object.keys(kido.Bakudo || {}).length;
  return `<section class="world-system-grid bleach-activity-grid">${renderActivityCard("SQUAD PLACEMENT", placement.status || "Awaiting placement", [["Evaluations",placement.evaluations], ["Interviews",placement.interviews], ["Offers",placement.offers], ["Player preferences",placement.player_preferences], ["Political pressure",placement.pressures]], "bleach-system")}${renderActivityCard("LIVING ZANPAKUTŌ", relation.name || "Unnamed Asauchi", [["Spirit",relation.spirit], ["Temperament",relation.temperament], ["Values",relation.values], ["Approval",relation.approval], ["Memories",relation.memories], ["Disagreements",relation.disagreements], ["Inner world",relation.inner_world_changes]], "bleach-system")}${renderActivityCard("KIDŌ REFERENCE", `${hado} Hadō · ${bakudo} Bakudō`, [["Hadō entries",Object.values(kido.Hado || {}).map(x=>`${x.number}: ${x.name} · mastery ${x.mastery}`)], ["Bakudō entries",Object.values(kido.Bakudo || {}).map(x=>`${x.number}: ${x.name} · mastery ${x.mastery}`)]], "bleach-system")}${renderActivityCard("SOUL REAPER DUTY", duty.current_assignment || "Awaiting assignment", [["Division culture",duty.division_culture], ["Patrols",duty.patrols], ["Konso",duty.konso], ["Hollow investigations",duty.hollow_investigations], ["Gigai use",duty.gigai_use], ["Soul-balance consequences",duty.soul_balance_consequences], ["Reiatsu interactions",activity.reiatsu_interactions]], "bleach-system")}</section>`;
}

function renderWorldProgression(world, special, classProfile, data = {}) {
  const value = (raw, fallback = "Not established") => compactReadable(raw) || fallback;
  const card = (eyebrow, title, rows, tone = "") => `<details class="world-system-card expandable-special-card ${tone}"><summary><header><small>${escapeHtml(eyebrow)}</small><h3>${escapeHtml(value(title))}</h3></header><span class="expand-label"></span></summary><div class="expandable-special-body">${rows.filter(([,v]) => v !== undefined && v !== null && value(v, "") !== "").map(([label,v]) => `<div class="world-system-detail"><b>${escapeHtml(label)}</b><span>${escapeHtml(value(v))}</span></div>`).join("")}</div></details>`;
  const namedRows = (rows, empty = "None recorded") => rows?.length ? rows.map((row) => {
    const title = row?.name || row?.class || "Record";
    const detail = row && typeof row === "object"
      ? Object.entries(row).filter(([key, entry]) => key !== "name" && entry !== undefined && entry !== null && compactReadable(entry)).map(([key, entry]) => `${humanLabel(key)}: ${compactReadable(entry)}`).join(" · ")
      : compactReadable(row);
    return `<div class="lit-system-row"><b>${escapeHtml(title)}</b><span>${escapeHtml(detail)}</span></div>`;
  }).join("") : `<p class="hint">${escapeHtml(empty)}</p>`;
  if (world === "One Piece") {
    const fruit = special["Devil Fruit Profile"] || {}, haki = special["Haki Profile"] || {};
    const activity = data.world_activity?.one_piece || {}, bounty = activity.bounty || {}, arc = activity.island_arc || {}, response = activity.world_response || {};
    const hakiLine = (name) => `${Number(haki[name]?.mastery || 0)} mastery${textList(haki[name]?.applications).length ? ` · ${textList(haki[name].applications).join(", ")}` : ""}`;
    const lastBounty = (bounty.history || []).at(-1) || {};
    return `<section class="world-system-grid">${card("DEVIL FRUIT", fruit.name || special["Devil Fruit"], [["Type",fruit.type],["Abilities",fruit.abilities],["Limits",fruit.limitations],["Awakening",fruit.awakening_status]], "one-piece-system")}${card("HAKI", "Haki Development", [["Observation",hakiLine("Observation")],["Armament",hakiLine("Armament")],["Conqueror",hakiLine("Conqueror")],["Breakthroughs",activity.haki_breakthroughs]], "one-piece-system")}${card("BOUNTY ASSESSMENT", `${Number(bounty.current ?? special.Bounty ?? 0).toLocaleString()} Berries`, [["Last act",lastBounty.act],["Strength shown",lastBounty.strength_demonstrated],["Notoriety",lastBounty.notoriety],["Government threat",lastBounty.government_threat],["Report source",lastBounty.source]], "one-piece-system")}${arc.name ? card("CURRENT ISLAND", arc.name, [["Authority",arc.ruler_or_faction],["Central problem",arc.central_problem],["Local culture",arc.local_culture],["Known secret",arc.secret_status === "Hidden" ? "Not yet discovered" : arc.secret],["Possible conclusions",arc.conclusions]], "one-piece-system") : ""}${card("WORLD RESPONSE", "How the seas reacted", [["Newspapers",response.newspapers],["Rumors",response.rumors],["Marine orders",response.marine_orders],["Rival attention",response.rival_attention],["Territory",response.territory_changes]], "one-piece-system")}</section>`;
  }
  if (world === "Hunter x Hunter") {
    const nen = special["Nen Profile"] || {}, hatsu = nen.hatsu_profile || {};
    const activity = data.world_activity?.hunter_x_hunter || {}, principles = activity.nen_principles || {}, career = activity.career || {};
    const principleRows = Object.entries(principles).map(([name,row]) => `${name}: ${row.mastery || 0} · ${row.last_feedback || "No recent feedback"}`);
    const intel = Object.entries(activity.technique_intel || {}).map(([name,row]) => `${name}: confirmed ${textList(row.confirmed).join(", ") || "none"}; suspected ${textList(row.suspected).join(", ") || "none"}; they know ${textList(row.they_know).join(", ") || "nothing confirmed"}`);
    return `${renderNenPanel(nen, special)}<section class="world-system-grid">${card("NEN FOUNDATIONS", "Ten through Hatsu", [["Separate mastery",principleRows]], "hxh-system")}${card("NEN INFORMATION", `${intel.length} opponents tracked`, [["Battle knowledge",intel]], "hxh-system")}${card("VOW REGISTRY", `${(activity.vows || []).length} vows`, [["Terms",activity.vows]], "hxh-system")}${card("HUNTER CAREER", career.license || "Unlicensed", [["Specialties",career.specialties],["Available work",career.available_work],["Completed work",career.completed_work],["Contacts",career.contacts],["Access",career.professional_access]], "hxh-system")}</section>`;
  }
  if (world === "Naruto") {
    const p = special["Shinobi Profile"] || {};
    const affinity = special["Chakra Affinity Profile"] || p.chakra_affinity || {};
    const host = special["Jinchūriki Profile"] || p.jinchuriki || {};
    const hostCard = renderNarutoJinchurikiPanel(host);
    const rates = affinity.learning_rates || {};
    const rateSummary = Object.entries(rates).map(([nature, rate]) => `${nature.replace(" Release", "")}: ${Number(rate).toFixed(2)}×`).join(" · ");
    const affinityCard = card("CHAKRA AFFINITY", affinity.primary || special["Nature Affinity"] || "Untested", [["Discovery",affinity.discovery_status],["Natural affinities",affinity.natural_affinities],["Learned proficiencies",affinity.proficiencies],["Mastered natures",affinity.mastered_natures],["Special mastery source",affinity.special_mastery_source],["Learning pace",rateSummary],["Native advantage",affinity.native_rule],["Off-affinity training",affinity.off_affinity_rule],["Combined natures",affinity.combined_nature_rule],["External access",affinity.external_natures]], "naruto-affinity-system");
    const activity = data.world_activity?.naruto || {}, career = activity.career || {}, intel = activity.intelligence || {}, beast = activity.tailed_beast_relationship || {};
    const specialties = Object.entries(activity.specialties || {}).filter(([,row])=>Number(row?.mastery || 0) > 0).map(([name,row])=>`${name}: ${row.mastery} · ${textList(row.known_techniques).join(", ") || "broad competence"}`);
    const activityCards = `${card("VILLAGE INTELLIGENCE", intel.clearance || "Civilian", [["Classified files",intel.classified_files],["Bingo book",intel.bingo_book],["Mission reports",intel.mission_reports],["Rumors",intel.rumors]], "naruto-system")}${card("SHINOBI SPECIALTIES", `${specialties.length} developed`, [["Competence",specialties]], "naruto-system")}${beast.beast ? card("TAILED-BEAST RELATIONSHIP", beast.beast, [["Trust",`${beast.trust || 0}%`],["Resentment",`${beast.resentment || 0}%`],["Cooperation",beast.cooperation],["Memories",beast.memories],["Promises",beast.promises],["Initiated contact",beast.initiated_contact]], "naruto-system") : ""}`;
    return `<section class="world-system-grid naruto-progression-grid">${card("SERVICE RECORD", career.rank || p.rank || special["Shinobi Rank"], [["Home village",p.home_village],["Clan",p.clan],["Mission history",career.mission_history],["Leadership",career.leadership_evidence],["Recommendations",career.recommendations],["Political support",career.political_support],["Opposition",career.political_opposition],["Promotion readiness",career.promotion_readiness]], "naruto-system naruto-service-system")}${affinityCard}${renderNarutoLineagePanel(special)}${hostCard}</section><section class="world-system-grid naruto-activity-grid">${activityCards}</section>`;
  }
  if (world === "Jujutsu Kaisen") {
    const sys = data.jjk_system || {}, slot = sys.birth_slot || special["Innate Technique Profile"] || special["Heavenly Restriction Profile"] || {};
    const progress = Object.entries(sys.progression || {}).map(([name,row]) => `${name}: ${Math.round(Number(row?.mastery || 0))}%`);
    const vows = (sys.binding_vows || []).map(vow => `${vow.name || "Binding Vow"}: ${vow.promise || "Promise recorded"} · Benefit: ${vow.benefit || "Recorded"} · Price: ${vow.price || "Recorded"} · ${vow.status || "Active"}`);
    const intel = Object.entries(sys.technique_intel || {}).map(([name,row]) => `${name}: confirmed — ${textList(row?.confirmed).join(", ") || "none"}; suspected — ${textList(row?.suspected).join(", ") || "none"}; unknown — ${textList(row?.unknowns).join(", ") || "unrecorded"}`);
    const exposure = Object.entries(sys.technique_exposure?.witnesses || {}).map(([name,facts]) => `${name}: ${textList(facts).join(", ")}`);
    const disclosure = Object.entries(sys.technique_disclosure?.opponents || {}).map(([name,row]) => `${name}: ${row.known ? `knows the rule · +${row.bonus || 0} (${row.source})` : "has not confirmed the rule"}`);
    const domain = sys.domain || {}, grade = sys.grade_record || {}, black = sys.black_flash || {};
    const clan = sys.clan || {}, soul = sys.soul || {}, curse = sys.curse_development || {}, hr = sys.heavenly_restriction_mastery || {};
    const domainCard = slot.slot_type === "Innate Cursed Technique" ? card("DOMAIN DEVELOPMENT", domain.name || "Innate Domain", [["Status",sys.domain_status || domain.status], ["Manifestation",domain.manifestation], ["Sure-hit",domain.sure_hit], ["Cost",domain.cost], ["Counterplay",domain.counterplay]], "jjk-domain-system") : "";
    const hrCard = slot.slot_type === "Heavenly Restriction" ? card("RESTRICTION MASTERY", slot.name, [["Body",`${Math.round(Number(hr.body || 0))}%`], ["Perception",`${Math.round(Number(hr.perception || 0))}%`], ["Cursed-tool fluency",`${Math.round(Number(hr.tool_fluency || 0))}%`], ["Adaptations",hr.adaptations]], "jjk-hr-system") : "";
    const clanCard = clan.name && clan.name !== "None" ? card("CLAN POSITION", clan.name, [["Standing",clan.standing], ["Obligations",clan.obligations], ["Favors",clan.favors], ["Sanctions",clan.sanctions], ["Inheritance claim",clan.inheritance_claim]], "jjk-clan-system") : "";
    const curseCard = sys.curse_identity && Object.keys(sys.curse_identity).length ? card("CURSED SPIRIT DEVELOPMENT", sys.curse_identity.source || "Sentient Curse", [["Origin instinct",sys.curse_identity.instinct], ["Feeding growth",sys.feeding_growth || 0], ["Humans killed",sys.humans_killed || 0], ["Fear resonance",curse.fear_resonance || 0], ["Infamy",curse.infamy || 0], ["Public assessment",curse.public_assessment], ["Territory",curse.territory]], "jjk-curse-system") : "";
    const soulCard = (soul.occupants || []).length || soul.possession_risk !== "None" ? card("SOUL & POSSESSION", `${Math.round(Number(soul.self_control ?? 100))}% self-control`, [["Soul integrity",`${Math.round(Number(soul.integrity ?? 100))}%`], ["Occupants",(soul.occupants || []).map(x=>`${x.name}: ${x.control || x.type}`)], ["Possession risk",soul.possession_risk]], "jjk-soul-system") : "";
    const clashes = (sys.domain_clashes || []).slice(-4).map(row=>`${row.player_domain} vs ${row.enemy_domain}: ${row.outcome} · ${row.player_score} to ${row.enemy_score} · ${row.barrier_interaction}`);
    return `<section class="world-system-grid jjk-system-grid">${renderJjkBirthSlot(slot)}${card("JUJUTSU RECORD", special.Grade || "Unassessed", [["Actual strength is separate",special["Official Status"]], ["School",special.School], ["Mission reliability",`${grade.mission_reliability || 0}%`], ["Headquarters recognition",grade.headquarters_recognition], ["Political support",grade.political_support], ["Promotion review",grade.promotion_recommendation], ["Missions",grade.missions_completed || 0], ["Exorcisms",grade.confirmed_exorcisms || 0], ["Reverse cursed technique",sys.reverse_cursed_technique], ["Maximum technique",sys.maximum_technique], ["Black Flashes",`${sys.black_flash_count || 0} · ${black.in_the_zone_turns ? `in the zone (${black.in_the_zone_turns} turns)` : "not in the zone"}`]], "jjk-system")}${domainCard}${hrCard}${clanCard}${curseCard}${soulCard}</section><details class="lit-system-section jjk-development-section"><summary>Progression, vows, missions, and technique intelligence</summary><div class="lit-system-body">${card("DEVELOPMENT TRACKS", `${(sys.unlocks || []).length} unlocks`, [["Mastery",progress], ["Unlocked",sys.unlocks]], "jjk-system")}${card("BINDING VOWS", `${vows.length} active or recorded`, [["Terms",vows]], "jjk-vow-system")}${card("TECHNIQUE INTELLIGENCE", `${intel.length} opponents tracked`, [["What you know",intel], ["Who has seen your technique",exposure], ["Revealing one's hand",disclosure], ["Active bonus",sys.technique_disclosure?.active_bonus ? `+${sys.technique_disclosure.active_bonus} against ${sys.technique_disclosure.active_opponent}` : "None"]], "jjk-intel-system")}${card("MISSION CASES", `${(sys.mission_dossiers || []).length} recorded`, [["Dossiers",sys.mission_dossiers]], "jjk-system")}${card("DOMAIN CLASHES", `${clashes.length} recent`, [["Resolved factors",clashes]], "jjk-domain-system")}</div></details>`;
  }
  if (world === "Solo Max-Level Newbie") {
    const p = special["System Profile"] || {}, sys = data.solo_system || {}, floor = sys.floor_state || {};
    const copied = Array.isArray(p.copied_abilities) ? p.copied_abilities : [];
    const copyRows = copied.map((entry) => typeof entry === "object" ? `${entry.name} — ${entry.condition_progress || 0}% · ${entry.copy_condition || "condition unknown"}` : entry);
    const hidden = (floor.hidden_conditions || []).map((entry) => `${entry.discovered ? "Known" : "Hidden"}: ${entry.discovered ? entry.name : "Unidentified condition"}${entry.completed ? " · Complete" : ""}`);
    const rivals = (sys.rivals || []).map((r) => `${r.name}: Floor ${r.floor}, Level ${r.level} — ${r.current_goal}`);
    const reports = (sys.floor_history || []).slice(-3).reverse();
    return `<section class="world-system-grid system-window-grid">${card("SYSTEM STATUS", `LEVEL ${data.level || 1}`, [["Experience",`${data.xp || 0} / ${data.xp_next || 100} XP`],["Floor",p.floor ?? special.Floor ?? 1],["Unspent points",p.unspent_stat_points || 0],["Build synergy",sys.build_synergies]], "solo-system")}${card("CURRENT SCENARIO", floor.name || `Floor ${p.floor ?? special.Floor ?? 1}`, [["Canon coverage",floor.canon_status],["Scenario",floor.scenario],["Clear condition",floor.clear_condition],["Environment rule",floor.environment_rule],["Factions",floor.factions],["Ecosystem",floor.ecosystem],["Recommended power",floor.recommended_power],["Administrator",`${floor.administrator?.name || "Unknown"} · ${floor.administrator?.personality || "Unknown"}`],["Administrator preference",floor.administrator?.preference],["Canon-parallel route",floor.mc_route],["Rewards",floor.rewards],["Hidden routes",hidden]], "solo-system")}${card("ABILITY COPY", `${copied.reduce((n,e)=>n+Number(e?.slot_cost || 1),0)} / ${p.copy_capacity || 1} slots`, [["Copied abilities",copyRows],["Observed attempts",(sys.copy_attempts || []).map(x=>`${x.name}: missing ${x.missing_conditions || x.copy_condition || "unknown"} · ${x.capacity_cost || x.slot_cost || 1} slot(s) · target awareness ${x.target_awareness || "unknown"}`)]], "solo-system")}</section><details class="lit-system-section"><summary>Foreknowledge, rivals, artifacts, and party roles</summary><div class="lit-system-body">${card("FOREKNOWLEDGE", `${sys.foreknowledge?.remembered?.length || 0} remembered`, [["Remembered",sys.foreknowledge?.remembered],["Confirmed in changed reality",sys.foreknowledge?.confirmed],["Now unreliable",sys.foreknowledge?.changed],["Suspected conditions",sys.foreknowledge?.suspected_hidden_conditions],["Spent exploits",sys.foreknowledge?.spent_exploits]], "solo-system")}${card("RIVAL PROGRESS", `${rivals.length} tracked`, [["Current positions",rivals]], "solo-system")}${card("ARTIFACTS", `${sys.artifact_index?.length || 0} indexed`, [["Known artifacts",(sys.artifact_index || []).map(a=>`${a.name} (${a.grade}) — ${textList(a.main_effect).join(", ")}`)]], "solo-system")}${card("PARTY ROLES", `${sys.party_roles?.length || 0} assigned`, [["Contributions",(sys.party_roles || []).map(x=>`${x.name}: ${x.role}`)]], "solo-system")}</div></details>${reports.length ? `<details class="lit-system-section"><summary>Recent floor reports</summary>${namedRows(reports.map(r=>({name:`Floor ${r.floor}`,objective:r.main_objective,hidden_completed:r.hidden_completed,hidden_missed:r.hidden_missed,xp_gained:r.xp_gained,levels_gained:r.levels_gained,items:r.items})))}</details>` : ""}`;
  }
  if (world === "Overgeared") {
    const p = special["Satisfy Profile"] || {}, sys = data.overgeared_system || {}, encyclopedia = data.class_encyclopedia || {};
    if (!sys.legendary_class_quests) sys.legendary_class_quests = sys.class_questlines || [];
    const paths = Object.entries(sys.production_paths || {}).map(([name,row]) => `${name}: ${row.mastery || 0} mastery (${row.rank || "Beginner"})`);
    const affinities = Object.entries(sys.npc_affinity || {}).map(([name,row]) => `${name}: ${row.score ?? 0} (${row.tier || "Unknown"})`);
    const rankings = Object.entries(sys.rankings || {}).map(([name,row]) => `${name}: ${row.band || "Unranked"} · ${row.score || 0}`);
    (sys.ranking_ecosystem || []).forEach((row) => rankings.push(`${row.name}: ${row.kind} · ${row.rank_score || 0} · ${row.trend || "Stable"} — ${row.reason || "World activity"}`));
    const orders = (sys.crafting_orders || []).map((o) => `${o.name}: ${o.progress || 0}% — ${o.status || "Active"}`);
    const classProgress = sys.class_progression || {};
    const role = sys.role_development || {};
    const behavior = Object.entries(sys.class_behavior?.routes || {}).map(([name,count])=>`${humanLabel(name)}: ${count}`);
    const legacy = Object.values(sys.equipment_legacies || {}).map(item=>`${item.name}: ${compactReadable(item.history) || "No history yet"} · disputes ${compactReadable(item.ownership_disputes) || "none"} · upgrades ${compactReadable(item.upgrades) || "none"} · synergy ${compactReadable(item.class_synergy) || "unrecorded"}`);
    const affinityHistory = Object.entries(sys.affinity_history || {}).map(([name,rows])=>`${name}: ${(rows || []).map(row=>`${row.before}→${row.after} because ${row.reason}`).join("; ")}`);
    const hasProduction = paths.length > 0 || Number(p.crafting_mastery || 0) > 0 || orders.length > 0;
    const productionCard = hasProduction ? card("PRODUCTION PATHS", `${p.crafting_mastery ?? 0} peak mastery`, [["Separate disciplines",paths],["Specialties",p.production_specialties],["Known recipes",p.known_recipes]], "overgeared-system") : "";
    const ordersCard = hasProduction ? card("CRAFTING ORDERS", `${orders.length} tracked`, [["Orders",orders],["Reminder","Materials and routine output remain in the Chronicle; only memorable reusable products enter the Bag."]], "overgeared-system") : "";
    const contracts = Object.values(sys.companion_contracts || {}).map(c => `${c.name}: Lv.${c.level || 1} · ${c.condition || "Stable"} · loyalty ${c.loyalty ?? 0}`);
    const families = (encyclopedia.families || []).map(f => `<details class="class-reference-row"><summary>${escapeHtml(f.name)}</summary><p>${escapeHtml(f.description)}</p><small>${escapeHtml((f.examples || []).join(", ") || "Original and hybrid paths")}</small></details>`).join("");
    const encyclopediaPanel = `<details class="lit-system-section"><summary>Class encyclopedia · ${encyclopedia.canon_name_count || 0} canon precedents</summary><div class="lit-system-body"><p class="hint">${escapeHtml(encyclopedia.note || "Classes develop through play.")}</p>${families}</div></details>`;
    return `<section class="world-system-grid">${card("SATISFY STATUS", `LEVEL ${data.level || 1}`, [["Experience",`${data.xp || 0} / ${data.xp_next || 100} XP`],["Class",p.primary_class || special.Class],["Class stage",`${classProgress.stage || "Foundation"} · ${classProgress.stage_progress || 0}%`]], "overgeared-system")}${card("SATISFY CLASS", p.primary_class || special.Class, [["Type",p.class_type || classProgress.class_type],["Rarity",p.class_rarity],["Secondary class",p.secondary_class],["Evolution evidence",behavior],["Next milestone",classProgress.next_unlock],["Personal class quests",sys.legendary_class_quests],["Guild",p.guild]], "overgeared-system")}${card("ROLE DEVELOPMENT", `${role.aligned_actions || 0} class-aligned actions`, [["Class features",p.class_features],["Specializations",p.specializations],["Advancement",p.advancement],["Major achievements",role.major_achievements],["Non-crafting routes",["Military","Religious","Political","Magical","Exploration","Social","Merchant","Command","Monster taming"]]], "overgeared-system")}${contracts.length ? card("CONTRACTED COMPANIONS", `${contracts.length} active`, [["Contracts",contracts]], "overgeared-system") : ""}${productionCard}${card("EQUIPMENT IDENTITY", `${legacy.length} remembered items`, [["Legacies",legacy]], "overgeared-system")}</section>${renderClassCard(classProfile)}${encyclopediaPanel}<details class="lit-system-section"><summary>Relationships, guild, territory, economy, and rankings</summary><div class="lit-system-body">${card("NPC AFFINITY", `${affinities.length} tracked`, [["Relationships",affinities],["Why they changed",affinityHistory]], "overgeared-system")}${card("GUILD & TERRITORY", sys.guild?.name || "Independent", [["Guild rank",sys.guild?.rank],["Guild resources",sys.guild?.resources],["Controlled territory",sys.territory?.controlled],["Morale",sys.territory?.morale],["Projects",sys.territory?.projects]], "overgeared-system")}${ordersCard}${card("ECONOMY & RANKINGS", `${sys.economy?.personal_gold ?? 0} personal Gold`, [["This turn",`${Number(sys.economy?.change_this_turn || 0) >= 0 ? "+" : ""}${sys.economy?.change_this_turn || 0} Gold`],["Important market effects",sys.economy?.important_effects],["Guild funds",sys.economy?.guild_funds],["Territory revenue",sys.economy?.territory_revenue],["Public standings",rankings]], "overgeared-system")}</div></details>`;
  }
  if (world === "Reincarnated as a Slime") {
    const p = special["Evolution Profile"] || {};
    const activity = data.world_activity?.slime || {}, nation = activity.nation || {}, evolution = activity.evolution || {};
    const subordinates = Object.entries(activity.subordinates || {}).map(([name,row])=>`${name}: ${row.role} · ${row.current_project} · training ${row.training} · concern ${textList(row.concerns).join(", ") || "none"}`);
    const analysis = Object.entries(activity.analysis_records || {}).map(([name,row])=>`${name}: ${row.stage} · ${textList(row.evidence).join("; ")}`);
    return `<section class="world-system-grid">${card("EVOLUTION", evolution.species || p.species || special.Species, [["Stage",evolution.stage || p.stage],["Naming",p.named_status],["Magicule capacity",p.magicule_capacity],["Possible routes",evolution.routes],["Next requirements",evolution.requirements || p.evolution_requirements],["Resistances",evolution.resistances],["Transformation consequences",evolution.consequences]], "slime-system")}${card("SKILL TAXONOMY", "Acquired Abilities", [["Intrinsic",p.intrinsic_skills],["Extra",p.extra_skills],["Unique",p.unique_skills],["Ultimate",p.ultimate_skills],["Resistances",p.resistances]], "slime-system")}${card("SYNTHESIS ANALYSIS", `${(activity.synthesis || []).length} analyses`, [["Possible combinations",activity.synthesis]], "slime-system")}${card("GREAT SAGE ANALYSIS", `${analysis.length} subjects`, [["Reports",analysis]], "slime-system")}${card("NATION", nation.legitimacy || "Unrecognized", [["Settlements",nation.settlements],["Specialists",nation.specialists],["Infrastructure",nation.infrastructure],["Defense",nation.defense],["Culture",nation.culture],["Trade",nation.trade],["Internal disagreements",nation.internal_pressures],["Alliances",nation.alliances]], "slime-system")}${card("NAMED SUBORDINATES", `${subordinates.length} autonomous followers`, [["Current lives",subordinates]], "slime-system")}${card("NAMING CONSEQUENCES", `${(activity.naming_history || []).length} records`, [["History",activity.naming_history]], "slime-system")}</section>`;
  }
  return "";
}

function loadPortraitImage(url) {
  const img = $("#portrait-img");
  if (!url || img.getAttribute("data-src") === url) return;
  img.classList.remove("loaded");
  const pre = new Image();
  pre.onload = () => {
    img.src = url;
    img.setAttribute("data-src", url);
    requestAnimationFrame(() => img.classList.add("loaded"));
  };
  pre.onerror = () => {
    $("#portrait-status").textContent = "PORTRAIT COULD NOT LOAD";
  };
  pre.src = url;
}

function renderAiPortrait(s) {
  const img = $("#portrait-img");
  const activeForm = s._portrait_active_form && typeof s._portrait_active_form === "object" ? s._portrait_active_form : {};
  const formName = String(activeForm.name || "").trim();
  const formEffect = portraitFormEffect(s);
  const portraitFrame = img.closest(".portrait-frame");
  portraitFrame?.classList.toggle("special-form-active", !!formName);
  if (portraitFrame) portraitFrame.dataset.formEffect = formEffect || "none";
  const formFx = $("#portrait-form-fx");
  if (formFx) formFx.dataset.formEffect = formEffect || "none";
  if (formName && formName !== APP.lastPortraitFormVisual) triggerAbilityEffect(formEffect || "evolution", formName);
  APP.lastPortraitFormVisual = formName;
  const hasDisplayPortrait = !!s._portrait_image;
  if (hasDisplayPortrait) {
    loadPortraitImage(s._portrait_image);
  } else {
    // Do not clear a successfully loaded portrait just because an effect or
    // transformation changed its generation signature.  The backend also
    // supplies the newest campaign portrait while the replacement renders;
    // this guard prevents a single delayed state response from flashing the
    // frame blank.
    if (!img.getAttribute("src")) img.classList.remove("loaded");
  }
  const status = $("#portrait-status");
  status.classList.toggle("generated", !!(s._portrait_generated || s._portrait_canon));
  if (s._portrait_canon) status.textContent = "CANON PORTRAIT · BUNDLED";
  else if (s._portrait_generated) status.textContent = formName ? `${formName.toUpperCase()} · ACTIVE PORTRAIT` : "AI PORTRAIT · CACHED";
  else if (s._portrait_previous) status.textContent = "UPDATING · PREVIOUS PORTRAIT SHOWN";
  else if (s._portrait_reference) status.textContent = "REFERENCE PORTRAIT";
  else if (!s._portrait_generation_enabled) status.textContent = "PORTRAITS OFF";
  else if (!s._portrait_generation_ready) status.textContent = "SET UP IMAGE AI FOR ART";
  else status.textContent = s._portrait_auto_generate ? "AI PORTRAIT QUEUED" : "AI PORTRAIT · GENERATE WHEN READY";
  $("#btn-portrait-regenerate").disabled = APP.portraitInFlight || !APP.campaignActive;
  if (!APP.deferPortraitGeneration && !s._portrait_canon && (s._portrait_auto_generate || formName)) ensureAiPortrait(s);
}

function renderActiveFormPanel(s) {
  const panel = $("#active-form-panel");
  if (!panel) return;
  const form = s?._portrait_active_form && typeof s._portrait_active_form === "object" ? s._portrait_active_form : {};
  const name = String(form.name || "").trim();
  panel.hidden = !name;
  if (!name) return;

  const details = String(form.details || form.description || form.effect || "").trim();
  const formEffect = portraitFormEffect(s) || "aura";
  const special = s?.special && typeof s.special === "object" ? s.special : {};
  const matchingBuffs = [...(s?.combat?.player_buffs || []), ...(s?.combat?.player_statuses || [])]
    .filter((row) => row && (row.effect_type === "transform" || String(row.name || "").toLowerCase() === name.toLowerCase()));
  const percent = (value) => `${Math.round(Number(value || 0) * 100)}%`;
  const bonusParts = [];
  matchingBuffs.forEach((row) => {
    if (Number(row.power_pct || 0)) bonusParts.push(`Power ${Number(row.power_pct) > 0 ? "+" : ""}${percent(row.power_pct)}`);
    if (Number(row.defense_pct || 0)) bonusParts.push(`Defense ${Number(row.defense_pct) > 0 ? "+" : ""}${percent(row.defense_pct)}`);
    if (Number(row.speed_pct || 0)) bonusParts.push(`Speed ${Number(row.speed_pct) > 0 ? "+" : ""}${percent(row.speed_pct)}`);
  });
  let structuredBonuses = form.stat_bonuses || form.bonuses;
  let worldAbilities = form.abilities;
  let worldRisk = form.risk || form.cost || form.limitation;
  if (formEffect === "bijuu") {
    const shinobi = special["Shinobi Profile"] || {};
    const host = special["Jinchūriki Profile"] || shinobi.jinchuriki || {};
    structuredBonuses ||= host.stat_boosts;
    worldAbilities ||= host.available_abilities;
    worldRisk ||= host.drawbacks;
    const reserve = Number(host.chakra_reserve_bonus_percent ?? Math.round((Number(host.reserve_multiplier || 1) - 1) * 100));
    if (reserve) bonusParts.push(`Chakra maximum +${reserve}%`);
  } else if (formEffect === "bankai" || formEffect === "shikai") {
    const blade = special["Zanpakuto Profile"] || {};
    worldAbilities ||= formEffect === "bankai" ? blade.bankai_effect : blade.shikai_effect;
    worldRisk ||= formEffect === "bankai" ? blade.bankai_cost : blade.shikai_limitation;
  } else if (formEffect === "domain") {
    const domain = s?.jjk_system?.domain || {};
    worldAbilities ||= [domain.sure_hit, domain.manifestation].filter(Boolean);
    worldRisk ||= domain.cost || domain.counterplay;
  }
  if (!bonusParts.length && structuredBonuses && typeof structuredBonuses === "object" && !Array.isArray(structuredBonuses)) {
    Object.entries(structuredBonuses).forEach(([key, value]) => bonusParts.push(`${humanLabel(key)} ${Number(value) > 0 ? "+" : ""}${value}`));
  }
  const abilities = Array.isArray(worldAbilities) ? worldAbilities.filter(Boolean).map(compactReadable).join(" · ") : compactReadable(worldAbilities);
  const risk = Array.isArray(worldRisk) ? worldRisk.filter(Boolean).map(compactReadable).join(" · ") : compactReadable(worldRisk);
  const unstable = /uncontrolled|unstable|berserk|corrupt|dangerous|overload/i.test(`${details} ${risk}`);

  $("#active-form-name").textContent = name;
  $("#active-form-state").textContent = unstable ? "UNSTABLE" : "CONTROLLED";
  $("#active-form-state").classList.toggle("unstable", unstable);
  $("#active-form-bonuses").textContent = bonusParts.length ? [...new Set(bonusParts)].join(" · ") : "Narrative transformation active";
  $("#active-form-abilities").textContent = abilities || details || "Its established abilities remain available while this form is active.";
  $("#active-form-risk").textContent = risk || (unstable ? details : "No special drawback is currently recorded.");
  panel.dataset.formEffect = formEffect;
}

async function ensureAiPortrait(s, force = false) {
  if (!s || !APP.campaignActive || !s._portrait_generation_enabled || !s._portrait_generation_ready) return;
  const signature = s._portrait_signature;
  if (!signature || APP.portraitInFlight || (!force && (s._portrait_generated || APP.portraitAttempted.has(signature)))) return;
  APP.portraitAttempted.add(signature);
  APP.portraitInFlight = true;
  const loading = $("#portrait-loading"), button = $("#btn-portrait-regenerate"), status = $("#portrait-status");
  loading.hidden = false; button.disabled = true; status.textContent = force ? "REGENERATING AI PORTRAIT" : "CREATING AI PORTRAIT";
  try {
    const result = await apiPost("/api/portrait/generate", { force });
    if (APP.state && APP.state._portrait_signature === result.signature) {
      APP.state._portrait_image = result.image_url + `?v=${Date.now()}`;
      APP.state._portrait_generated = true;
      loadPortraitImage(APP.state._portrait_image);
      status.classList.add("generated");
      status.textContent = result.cached ? "AI PORTRAIT · CACHED" : "AI PORTRAIT · UPDATED";
    }
  } catch (err) {
    status.classList.remove("generated");
    status.textContent = "WORLD PORTRAIT · GENERATION UNAVAILABLE";
    showToast(err.message || "AI portrait generation failed.", "danger");
  } finally {
    APP.portraitInFlight = false; loading.hidden = true; button.disabled = !APP.campaignActive;
  }
}

// A small shared line-icon set (Feather-style: 24x24 grid, 2px stroke,
// round caps/joins) standing in for the old emoji glyphs — consistent
// weight and color (currentColor) instead of whatever font the OS
// happens to render emoji in.
const SVG_ICON_ATTRS = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
const ICONS = {
  sword: `<svg ${SVG_ICON_ATTRS}><line x1="20.5" y1="3.5" x2="9" y2="15"/><path d="M14.5 8 18 11.5"/><path d="M9 15 4 20"/><path d="M4 20l-1 1"/><path d="M6.5 17.5 4 15l-1 3 3 3 3-1z"/></svg>`,
  zap: `<svg ${SVG_ICON_ATTRS}><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
  shield: `<svg ${SVG_ICON_ATTRS}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
  bookOpen: `<svg ${SVG_ICON_ATTRS}><path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2z"/><path d="M22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z"/></svg>`,
  eye: `<svg ${SVG_ICON_ATTRS}><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
  star: `<svg ${SVG_ICON_ATTRS}><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
  fileText: `<svg ${SVG_ICON_ATTRS}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="14" y2="17"/></svg>`,
  activity: `<svg ${SVG_ICON_ATTRS}><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`,
  box: `<svg ${SVG_ICON_ATTRS}><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>`,
  award: `<svg ${SVG_ICON_ATTRS}><circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/></svg>`,
  mail: `<svg ${SVG_ICON_ATTRS}><path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><polyline points="22 6 12 13 2 6"/></svg>`,
  clock: `<svg ${SVG_ICON_ATTRS}><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  compass: `<svg ${SVG_ICON_ATTRS}><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>`,
  edit: `<svg ${SVG_ICON_ATTRS}><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>`,
};

// Keyword-matched icon per ability name — every world's ability set is
// different (Taijutsu vs Strength vs Aura Control), so this matches on
// meaning rather than a fixed per-world lookup table.
const ABILITY_ICON_RULES = [
  [/strength|taijutsu|power|brawn/i, ICONS.sword],
  [/dexterity|agility|ninjutsu/i, ICONS.zap],
  [/constitution|endurance|vitality/i, ICONS.shield],
  [/intelligence|intellect|genjutsu|cunning/i, ICONS.bookOpen],
  [/wisdom|willpower|instinct|chakra/i, ICONS.eye],
  [/charisma|luck|aura|fortune/i, ICONS.star],
];
function abilityIcon(name) {
  for (const [re, icon] of ABILITY_ICON_RULES) if (re.test(name)) return icon;
  return ICONS.star;
}

const WORLD_UI_THEMES = {
  "One Piece": { sheet: "Crew Record", attributes: "Capabilities", skills: "Techniques & Titles", chronicle: "Voyage Log" },
  "Hunter x Hunter": { sheet: "Hunter Record", attributes: "Aptitudes", skills: "Nen & Titles", chronicle: "Case Log" },
  "Naruto": { sheet: "Shinobi Record", attributes: "Shinobi Arts", skills: "Jutsu & Titles", chronicle: "Mission Scroll" },
  "Solo Max-Level Newbie": { sheet: "Status Window", attributes: "System Stats", skills: "Skills & Achievements", chronicle: "System Log" },
  "Overgeared": { sheet: "Player Status", attributes: "Character Stats", skills: "Classes & Skills", chronicle: "Adventure Log" },
  "Reincarnated as a Slime": { sheet: "Analysis Record", attributes: "Existence Values", skills: "Unique Skills & Titles", chronicle: "Great Sage Record" },
  "Bleach": { sheet: "Soul Record", attributes: "Spiritual Arts", skills: "Techniques & Releases", chronicle: "Soul Chronicle" },
  "Jujutsu Kaisen": { sheet: "Sorcerer Record", attributes: "Jujutsu Aptitudes", skills: "Technique & Applications", chronicle: "Curse Chronicle" },
  "Custom World": { sheet: "Character Sheet", attributes: "Attributes", skills: "Skills & Titles", chronicle: "Chronicle" },
};
function applyWorldInterfaceTheme(world) {
  const theme = WORLD_UI_THEMES[world] || WORLD_UI_THEMES["Custom World"];
  $("#character-sheet-title").textContent = theme.sheet;
  $("#attributes-title").lastChild.textContent = theme.attributes;
  $("#skills-panel-title").textContent = theme.skills;
  $("#chronicle-title").textContent = theme.chronicle;
}

function isMobileLayout() { return window.matchMedia("(max-width: 720px)").matches; }

function mobileCampaignKey(kind) {
  const id = APP.state?.campaign_id || APP.account?.username || "local";
  return `worldwalker_mobile_${kind}_${id}`;
}

function mobileVibrate(pattern = 12) {
  if (!isMobileLayout() || !APP.mobileHaptics || !navigator.vibrate) return;
  try { navigator.vibrate(pattern); } catch (_) { /* haptics are optional */ }
}

function setMobileView(view, focus = true) {
  const allowed = new Set(["chronicle", "actions", "character", "map"]);
  if (isMobileLayout() && APP.mobileView) {
    try { localStorage.setItem(mobileCampaignKey(`scroll_${APP.mobileView}`), String(window.scrollY || 0)); } catch (_) {}
  }
  APP.mobileView = allowed.has(view) ? view : "chronicle";
  document.body.setAttribute("data-mobile-view", APP.mobileView);
  $$("#mobile-bottom-nav [data-mobile-view]").forEach((button) => {
    const selected = button.getAttribute("data-mobile-view") === view;
    button.setAttribute("aria-selected", String(selected));
  });
  if (!focus || !isMobileLayout()) return;
  let saved = 0;
  try { saved = Number(localStorage.getItem(mobileCampaignKey(`scroll_${APP.mobileView}`)) || 0); } catch (_) {}
  requestAnimationFrame(() => window.scrollTo({ top: saved, behavior: "auto" }));
  if (APP.mobileView === "actions") requestAnimationFrame(() => $("#action-input")?.focus({ preventScroll: true }));
  if (APP.mobileView === "map") requestAnimationFrame(() => { if (window.WorldAtlas) WorldAtlas.refresh(); });
}

function mobileTimeText() {
  const unit = $("#time-unit")?.value || "moment";
  const amount = Number($("#time-amount")?.value || 1);
  if (unit === "moment") return "Moment";
  if (unit === "next_event") return "Next major event";
  return `${amount} ${amount === 1 ? unit.replace(/s$/, "") : unit}`;
}

function syncMobileTimeInputs() {
  const unit = $("#time-unit"), amount = $("#time-amount");
  const mobileUnit = $("#mobile-time-unit"), mobileAmount = $("#mobile-time-amount");
  if (!unit || !amount || !mobileUnit || !mobileAmount) return;
  mobileUnit.value = unit.value;
  mobileAmount.value = amount.value || "1";
  const fixedAmount = ["moment", "next_event"].includes(unit.value);
  mobileAmount.hidden = fixedAmount;
  mobileAmount.disabled = fixedAmount;
}

function applyMobileTimeInputs() {
  const unit = $("#mobile-time-unit")?.value || "moment";
  const amount = $("#mobile-time-amount")?.value || "1";
  $("#time-unit").value = unit;
  $("#time-amount").value = ["moment", "next_event"].includes(unit) ? "1" : amount;
  syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help");
}

function renderMobileState(s) {
  const mobile = isMobileLayout();
  $("#mobile-status-ribbon").hidden = !mobile;
  $("#mobile-bottom-nav").hidden = !mobile;
  $("#mobile-advance-dock").hidden = !mobile;
  if (!mobile) return;
  const campaignId = s.campaign_id || APP.account?.username || "local";
  if (APP.mobileScrollCampaign !== campaignId) {
    APP.mobileScrollCampaign = campaignId;
    requestAnimationFrame(() => {
      let saved = 0;
      try { saved = Number(localStorage.getItem(mobileCampaignKey(`scroll_${APP.mobileView}`)) || 0); } catch (_) {}
      if (saved > 0) window.scrollTo({ top: saved, behavior: "auto" });
    });
  }
  if (!document.body.hasAttribute("data-mobile-view")) setMobileView("chronicle", false);
  const status = (Array.isArray(s.status) ? s.status.join(", ") : s.status) || "Normal";
  const tension = s._tension || { label: "Calm" };
  const combat = !!s.combat?.active;
  const tacticalCombat = combat && ['Naruto','One Piece','Bleach'].includes(s.world);
  const chips = [
    `<span class="mobile-status-chip"><span>HP</span><b>${escapeHtml(s.hp ?? 0)} / ${escapeHtml(s.hp_max ?? 0)}</b></span>`,
    `<span class="mobile-status-chip"><span>${escapeHtml(s.resource_name || "Energy")}</span><b>${escapeHtml(s.resource ?? 0)}</b></span>`,
    `<span class="mobile-status-chip"><span>Status</span><b>${escapeHtml(status)}</b></span>`,
    `<span class="mobile-status-chip"><span>Time</span><b>${escapeHtml(s.world_time || "Day 1")}</b></span>`,
    `<span class="mobile-status-chip ${/critical|danger/i.test(tension.label || "") ? "danger" : ""}"><span>Risk</span><b>${escapeHtml(tension.label || "Calm")}</b></span>`,
    combat ? `<span class="mobile-status-chip danger"><span>Combat</span><b>Round ${escapeHtml(s.combat?.round || 1)}</b></span>` : "",
  ].filter(Boolean);
  $("#mobile-status-ribbon").innerHTML = chips.join("");
  const count = (s.queued_actions || []).length;
  $("#mobile-queue-count").textContent = count;
  $("#mobile-action-count").textContent = `${count} queued action${count === 1 ? "" : "s"}`;
  if ($("#mobile-time-label")) $("#mobile-time-label").textContent = mobileTimeText();
  syncMobileTimeInputs();
  document.body.classList.toggle("mobile-combat-active", combat && !tacticalCombat);
  $("#mobile-combat-dock").hidden = !combat || tacticalCombat;
  $("#mobile-advance-dock").hidden = combat;
  $("#mobile-bottom-nav").hidden = combat;
}

function autoGrowMobileComposer() {
  const input = $("#action-input");
  if (!input || !isMobileLayout()) return;
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, Math.round(window.innerHeight * .38))}px`;
}

function saveMobileDraft() {
  const input = $("#action-input");
  if (!input) return;
  try { localStorage.setItem(mobileCampaignKey("draft"), input.value); } catch (_) {}
  autoGrowMobileComposer();
}

function restoreMobileDraft() {
  const input = $("#action-input");
  if (!input || input.value) return;
  try { input.value = localStorage.getItem(mobileCampaignKey("draft")) || ""; } catch (_) {}
  autoGrowMobileComposer();
}

// The freeform action picker lives in action-deck.js.

function pulseInterfaceTarget(element, kind = "updated") {
  if (!element || !APP.animationsEnabled || APP.mobileLowData) return;
  element.classList.remove("visual-update", "visual-danger");
  void element.offsetWidth;
  element.classList.add(kind === "danger" ? "visual-danger" : "visual-update");
  window.setTimeout(() => element.classList.remove("visual-update", "visual-danger"), 1250);
}

function animateStateChanges(previous, next) {
  if (!previous || !next || previous.campaign_id !== next.campaign_id || Number(previous.turn || 0) === Number(next.turn || 0)) return;
  requestAnimationFrame(() => {
    const summary = $("#stat-summary-body");
    if (Number(previous.level || 0) !== Number(next.level || 0) || Number(previous.xp || 0) !== Number(next.xp || 0)) pulseInterfaceTarget($("#level-summary"));
    if (Number(previous.hp || 0) !== Number(next.hp || 0)) pulseInterfaceTarget($("#bar-hp")?.closest(".bar-row"), Number(next.hp || 0) < Number(previous.hp || 0) ? "danger" : "updated");
    if (Number(previous.resource || 0) !== Number(next.resource || 0)) pulseInterfaceTarget($("#bar-resource")?.closest(".bar-row"));
    const oldStats = previous.stats || {};
    Object.entries(next.stats || {}).forEach(([name, value]) => {
      const delta = Number(value) - Number(oldStats[name] ?? value);
      if (!delta) return;
      const cell = $$(".attr-cell[data-stat-name]").find((row) => row.dataset.statName === name);
      if (!cell) return;
      pulseInterfaceTarget(cell, delta < 0 ? "danger" : "updated");
      const marker = document.createElement("small");
      marker.className = `stat-delta ${delta < 0 ? "negative" : "positive"}`;
      marker.textContent = `${delta > 0 ? "+" : ""}${delta}`;
      cell.appendChild(marker);
      window.setTimeout(() => marker.remove(), 1250);
    });
    const oldSkillCount = Object.keys(previous.skills || {}).length + (previous.titles || []).length;
    const newSkillCount = Object.keys(next.skills || {}).length + (next.titles || []).length;
    if (newSkillCount > oldSkillCount) pulseInterfaceTarget($("#skills-list")?.closest(".panel"));
    if ((next.quests || []).length > (previous.quests || []).length) pulseInterfaceTarget($("#active-quest-preview"));
    if ((next.world_events || []).length > (previous.world_events || []).length) pulseInterfaceTarget($("#world-feed-nav"));
    if (summary && Number(next.hp || 0) <= 0) pulseInterfaceTarget(summary, "danger");
  });
}

function renderState(state) {
  if (window.WorldwalkerRosterSync) state._organization_roster = WorldwalkerRosterSync.reconcile(state?._organization_roster, state || {});
  const rosterLabel = state?._organization_roster?.label || "Group";
  $$('#journal-tabs [data-tab="party"], [data-journal="party"]').forEach(button => { button.textContent = rosterLabel; });
  const mobileRosterLabel = $('[data-mobile-open="party"] b');
  if (mobileRosterLabel) mobileRosterLabel.textContent = rosterLabel;
  if (APP.retryRequest && APP.retryRequest.campaign !== recoveryCampaignKey(state)) APP.retryRequest = null;
  $("#turn-recovery-notice").hidden = !(state?.last_failed_turn?.route || APP.retryRequest);
  const previousState = APP.state;
  APP.state = state;
  if (window.WorldwalkerTeamMembership) WorldwalkerTeamMembership.handle(state);
  restorePendingRequest(state);
  checkTrophyProposals(state);
  const s = state;
  if (Number(s.hp || 0) > 0) APP.narutoDeathCueActive = false;
  document.body.setAttribute("data-world", s.world || "Custom World");
  document.body.classList.toggle("motion-off", !APP.animationsEnabled);
  applyWorldInterfaceTheme(s.world || "Custom World");
  applyPortraitAmbient(s);
  applyWorldAtmosphere(s);

  $("#hdr-world").textContent = s.world || "Custom World";
  $("#hdr-location").textContent = s.location || "Unknown";
  $("#hdr-turn").textContent = "Turn " + (s.turn || 0);
  const tension = s._tension || { score: 0, label: "Calm", reasons: [] };
  const tensionPill = $("#hdr-tension");
  tensionPill.textContent = "● " + tension.label;
  tensionPill.className = "pill tension-pill tension-" + tension.label.toLowerCase();
  tensionPill.title = tension.reasons && tension.reasons.length
    ? "How dangerous your current situation is: " + tension.reasons.join(", ") + "."
    : "How dangerous your current situation is, at a glance.";
  const saved = s._last_autosave || s.last_autosave || "";
  $("#hdr-autosave").textContent = saved ? `Saved ${String(saved).replace("T", " ").slice(0, 16)}` : "Not saved";
  renderQueuedActions(s.queued_actions || []);
  $("#scene-title").textContent = Number(s.turn || 0) > 0 ? "CURRENT SCENE" : "OPENING SCENE";
  $("#btn-retry-opening").hidden = Boolean(s.opening_complete);

  // Generated portraits are keyed by visually relevant state and update only
  // when appearance, form, or visible equipment actually changes.
  renderAiPortrait(s);
  renderActiveFormPanel(s);
  $("#portrait-name").textContent = s.name || "Traveler";
  $("#portrait-class").textContent = worldIdentityLabel(s);
  const locationEl = $("#portrait-location");
  const locationText = (s.location || "").trim();
  if (locationText) { $("#portrait-location-text").textContent = locationText; locationEl.hidden = false; }
  else locationEl.hidden = true;
  const posBadge = $("#position-badge");
  if (s.position && s.position.trim()) { posBadge.textContent = s.position; posBadge.style.display = ""; }
  else posBadge.style.display = "none";

  // scene
  updateScene(s);
  scheduleLivingMapRefresh(s);

  // stat summary
  $("#stat-level").textContent = "Level " + (s.level ?? 1);
  $("#stat-xp").textContent = `XP ${s.xp ?? 0} / ${s.xp_next ?? 100}`;
  setWidth($("#bar-hp"), 100 * (s.hp ?? 0) / Math.max(1, s.hp_max ?? 100));
  $("#bar-hp-text").textContent = `${s.hp ?? 0} / ${s.hp_max ?? 100}`;
  setWidth($("#bar-resource"), 100 * (s.resource ?? 0) / Math.max(1, s.resource_max ?? 100));
  $("#bar-resource-text").textContent = `${s.resource ?? 0} / ${s.resource_max ?? 100}`;
  $("#resource-label").textContent = s.resource_name || "Energy";
  setWidth($("#bar-xp"), 100 * (s.xp ?? 0) / Math.max(1, s.xp_next ?? 100));
  $("#level-summary").style.display = s._uses_xp ? "" : "none";
  $("#xp-summary").style.display = s._uses_xp ? "" : "none";
  const hasRace = !!(s.race && String(s.race).trim());
  $("#stat-race-label").hidden = !hasRace;
  $("#stat-race").hidden = !hasRace;
  if (hasRace) $("#stat-race").textContent = s.race;
  $("#stat-age").textContent = s.age ? String(s.age) : "Unknown";
  $("#stat-status").textContent = (s.status && s.status.length) ? s.status.join(", ") : "Normal";
  const fullWorldTime = s.world_time || "Day 1 — Morning";
  $("#stat-time").textContent = fullWorldTime;
  $("#stat-time").title = fullWorldTime;
  $("#stat-time").setAttribute("aria-label", `Current time: ${fullWorldTime}`);
  const towerLabel = $("#stat-tower-timer-label"), towerTimer = $("#stat-tower-timer");
  if (typeof s._tower_days_left === "number") {
    towerLabel.hidden = false; towerTimer.hidden = false;
    towerTimer.textContent = `${s._tower_days_left} day${s._tower_days_left === 1 ? "" : "s"} left`;
    towerTimer.classList.toggle("tower-timer-critical", s._tower_days_left <= 14);
  } else {
    towerLabel.hidden = true; towerTimer.hidden = true;
  }
  const currency = s.currency || {};
  const tracksCurrency = s._tracks_currency !== false && currency.tracked !== false;
  $("#currency-row").style.display = tracksCurrency ? "" : "none";
  $("#stat-currency-label").textContent = currency.name || "Currency";
  $("#stat-currency").textContent = currency.amount !== undefined ? formatCurrencyClient(currency, false) : "0";
  $("#stat-summary-body").classList.toggle("narrative-progression", !s._uses_xp);
  document.body.classList.toggle("health-critical", Number(s.hp || 0) > 0 && Number(s.hp || 0) / Math.max(1, Number(s.hp_max || 1)) <= .25);
  animateStateChanges(previousState, s);

  // attributes — dynamic per world (see backend worlds.WORLD_ABILITIES)
  const attrs = s.stats || {};
  const abilityProgress = s.ability_progress || {};
  const attrKeys = Object.keys(attrs);
  $("#attributes-grid").innerHTML = attrKeys.map((k) => {
    const v = attrs[k] ?? 1;
    const progress = Number(abilityProgress[k] || 0);
    const progressText = progress > .001
      ? (s._uses_xp ? `Practice +${progress.toFixed(progress >= 10 ? 1 : 2)}` : `${Math.round(progress * 100)}% to next point`)
      : "";
    return `<div class="attr-cell" data-stat-name="${escapeHtml(k)}"><div class="attr-name"><i class="a-icon">${abilityIcon(k)}</i>${escapeHtml(k)}</div><div class="attr-right">${progressText ? `<small class="attr-progress">${escapeHtml(progressText)}</small>` : ""}<span class="attr-val">${escapeHtml(v)}</span></div></div>`;
  }).join("");

  const isFullSheet = s._stat_style === "full_sheet";
  const hiddenWrap = $("#hidden-stats-wrap");
  if (isFullSheet) {
    const revealed = { ...(s.hidden_stats || {}) };
    if (s.class_profile?.name) revealed["Hidden Class"] = s.class_profile.name;
    // Skip any placeholder that collides with a visible core ability name
    // (e.g. Overgeared/Solo Max-Level Newbie already use "Luck" as a core stat).
    const placeholders = ["Fortune", "Hidden Class", "Talent"].filter((k) => !(k in revealed) && !attrKeys.includes(k));
    const cells = [
      ...Object.entries(revealed).map(([k, v]) => `<div class="attr-cell revealed"><div class="attr-name"><i class="a-icon">${abilityIcon(k)}</i>${escapeHtml(k)}</div><div class="attr-right"><span class="attr-val">${escapeHtml(v)}</span></div></div>`),
      ...placeholders.map((k) => `<div class="attr-cell locked"><div class="attr-name"><i class="a-icon">${abilityIcon(k)}</i>${escapeHtml(k)}</div><div class="attr-right"><span class="attr-val">???</span></div></div>`),
    ];
    $("#hidden-stats-grid").innerHTML = cells.join("");
    hiddenWrap.style.display = "";
  } else {
    hiddenWrap.style.display = "none";
  }

  // gear — worlds where itemization matters show the full equipped set,
  // others (per user request) only surface the signature weapon/held item.
  renderGearPanel(s);

  // skills & titles
  const classItems = s.class_profile?.name ? [`◆ ${escapeHtml(s.class_profile.name)} <small>(${escapeHtml(s.class_profile.kind || "Hidden Class")})</small>`] : [];
  const skillItems = Object.keys(s.skills || {}).map((k) => `✦ ${escapeHtml(k)}`);
  const titleItems = (s.titles || []).map((t) => `🏅 ${escapeHtml(titleLabel(t))}`);
  renderTagListHtml("#skills-list", [...classItems, ...titleItems, ...skillItems], "None");

  // affiliations — formal membership + rank in any group/kingdom/hierarchy,
  // distinct from general faction reputation. Panel stays hidden until the
  // player actually belongs to something.
  const affiliations = (s.affiliations || []).filter((a) => a && a.faction);
  const affPanel = $("#affiliations-panel");
  affPanel.style.display = affiliations.length ? "" : "none";
  if (affiliations.length) {
    renderTagListHtml("#affiliations-list", affiliations.map((a) =>
      `🛡 <b>${escapeHtml(a.rank || "Member")}</b> — ${escapeHtml(a.faction)}${a.status && a.status !== "active" ? ` <small>(${escapeHtml(a.status)})</small>` : ""}`
    ), "None");
  }

  // The left rail keeps quests and world events compact; either button opens
  // the complete journal view.
  const questPreview = $("#active-quest-preview");
  const activeQuests = s.quests || [];
  const questUi = questPresentation(s.world);
  const questTab = $('#journal-tabs button[data-tab="quests"]');
  if (questTab) questTab.textContent = questUi.tab_label;
  if (activeQuests.length) {
    const q = questView(activeQuests[0]);
    questPreview.classList.remove("empty");
    questPreview.innerHTML = `<span>${escapeHtml(questUi.rail_label)}</span><small>${escapeHtml(q.name)}</small>`;
  } else {
    questPreview.classList.add("empty");
    questPreview.innerHTML = `<span>${escapeHtml(questUi.rail_label)}</span><small>${escapeHtml(questUi.empty_label)}</small>`;
  }

  const feedItems = [...(s.world_events || []), ...(s.timeline || []).slice(-5)].slice(-8).map((e) => escapeHtml(typeof e === "object" ? (e.text || JSON.stringify(e)) : e));
  const worldFeedNav = $("#world-feed-nav");
  worldFeedNav.innerHTML = `<span>World Feed</span><small>${feedItems.length ? escapeHtml(String(feedItems.length) + " recent updates") : "No updates yet"}</small>`;

  // messages
  renderMessagesPanel(s);

  // time mode + world systems icons
  updateSelectedTimeLabel();
  updateWorldSystemIcons(s);

  // suggested actions
  const sugg = $("#suggested-actions");
  sugg.innerHTML = "";
  const suggestions = buildActionDeckChoices(s).filter(row => row.category === "recommended").slice(0, 3).map(row => row.text);
  const suggestionIcon = (action, index) => {
    const text = String(action || "").toLowerCase();
    if (/travel|journey|go to|head to|reach|visit|return/.test(text)) return "➜";
    if (/talk|ask|meet|contact|send|negotiate|diplom/.test(text)) return "◉";
    if (/train|learn|practice|study|master|improve/.test(text)) return "✦";
    if (/investigat|scout|search|track|inspect|find/.test(text)) return "⌕";
    if (/defend|protect|fight|attack|mobilize|prepare/.test(text)) return "⚑";
    return ["◆", "◇", "✧"][index % 3];
  };
  suggestions.forEach((a, index) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "suggestion-card";
    btn.setAttribute("aria-label", a);
    const people = mentionedPortraitsHtml(a, knownPersonRecords(s), 1, "xs");
    btn.innerHTML = `${people || `<span class="suggestion-card-icon" aria-hidden="true">${suggestionIcon(a, index)}</span>`}<span>${escapeHtml(a)}</span>`;
    btn.addEventListener("click", () => {
      const input = $("#action-input");
      const current = input.value.trim();
      input.value = current ? `${current}\n${a}` : a;
      saveMobileDraft();
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
      showToast("Suggested action added to the chat. Edit it or press Add Action.", "system");
    });
    sugg.appendChild(btn);
  });
  if (suggestions.length) {
    const own = document.createElement("button");
    own.type = "button";
    own.className = "suggestion-card suggestion-card-own";
    own.innerHTML = '<span class="suggestion-card-icon" aria-hidden="true">✎</span><span>Describe another approach</span>';
    own.addEventListener("click", () => {
      const input = $("#action-input");
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
    });
    sugg.appendChild(own);
  }
  const reasons = Array.isArray(s.last_cause_effect) ? s.last_cause_effect : [];
  const reasonBox = $("#change-reasons");
  reasonBox.hidden = !reasons.length;
  $("#change-reasons-list").innerHTML = reasons.map((row) => `<div class="change-reason"><b>${escapeHtml(row.target || row.category || "Change")}</b><span>${escapeHtml(row.change || "Changed")}</span><small>${escapeHtml(row.because || "The resolved turn changed this.")}</small></div>`).join("");
  if (APP.music.world !== (s.world || "Custom World")) refreshMusic(s.world, APP.music.userStarted);
  LivingAdventures.onState();
  renderCombatPanel(s);
  if (s.status_window_due && !APP.statusWindowOpen) { APP.statusWindowOpen = true; renderStatusWindow(s); openModal("modal-status-window"); }
  const chapters = Array.isArray(s.chapter_summaries) ? s.chapter_summaries : [];
  if (APP.lastChapterCount === null) {
    APP.lastChapterCount = chapters.length;
  } else if (chapters.length > APP.lastChapterCount) {
    renderChapterRecap(chapters[chapters.length - 1], s);
    openModal("modal-chapter-recap");
    APP.lastChapterCount = chapters.length;
  }
  renderMobileState(s);
  restoreMobileDraft();
}

// A chapter break already gets a quiet Chronicle note; this turns the same
// already-generated chapter_summaries entry into an actual "previously, on…"
// moment instead of something only visible if you go dig through the Journal.
function renderChapterRecap(chapter, s) {
  $("#recap-world").textContent = s.world || "Worldwalker";
  $("#recap-title").textContent = chapter.title || `Chapter ${chapter.number || ""}`;
  const turns = chapter.turns || [];
  $("#recap-timespan").textContent = [chapter.time_span, turns.length ? `Turns ${turns[0]}–${turns[1]}` : ""].filter(Boolean).join(" · ");
  $("#recap-summary").textContent = chapter.narrative_summary || chapter.summary || "No detailed account was recorded.";
  $("#recap-decisions").innerHTML = (chapter.key_decisions || []).slice(0, 8).map((d) => `<li>${escapeHtml(d)}</li>`).join("");
  $("#recap-changes").innerHTML = (chapter.lasting_changes || []).slice(0, 8).map((c) => `<li>${escapeHtml(c)}</li>`).join("");
}
$("#btn-recap-continue").addEventListener("click", () => { closeModal("modal-chapter-recap"); playSfx("notify"); });

// ---------------------------------------------------------------------------
// Status window — a periodic full-stats popup every ~3 in-game months,
// styled like an RPG character sheet rather than another plain modal.
// ---------------------------------------------------------------------------
function renderStatusWindow(s) {
  $("#sw-name").textContent = s.name || "Traveler";
  $("#sw-class").textContent = worldIdentityLabel(s);
  $("#sw-meta").textContent = `${s.world_time || "Day 1"} · ${s.location || "Unknown"}`;
  setWidth($("#sw-bar-hp"), 100 * (s.hp ?? 0) / Math.max(1, s.hp_max ?? 100));
  $("#sw-hp-text").textContent = `${s.hp ?? 0} / ${s.hp_max ?? 100}`;
  setWidth($("#sw-bar-resource"), 100 * (s.resource ?? 0) / Math.max(1, s.resource_max ?? 100));
  $("#sw-resource-text").textContent = `${s.resource ?? 0} / ${s.resource_max ?? 100}`;
  $("#sw-resource-label").textContent = s.resource_name || "Energy";
  $("#sw-xp-row").style.display = s._uses_xp ? "" : "none";
  if (s._uses_xp) {
    setWidth($("#sw-bar-xp"), 100 * (s.xp ?? 0) / Math.max(1, s.xp_next ?? 100));
    $("#sw-xp-text").textContent = `Level ${s.level ?? 1} · ${s.xp ?? 0} / ${s.xp_next ?? 100}`;
  }
  const attrs = s.stats || {};
  $("#sw-attributes").innerHTML = Object.entries(attrs).map(([k, v]) =>
    `<div class="status-window-attr"><i class="a-icon">${abilityIcon(k)}</i><span>${escapeHtml(k)}</span><b>${escapeHtml(v)}</b></div>`
  ).join("") || '<div class="hint">None recorded.</div>';
  const classItems = s.class_profile?.name ? [`<li>◆ ${escapeHtml(s.class_profile.name)} <small>(${escapeHtml(s.class_profile.kind || "Hidden Class")})</small></li>`] : [];
  const skillItems = Object.keys(s.skills || {}).map((k) => `<li>✦ ${escapeHtml(k)}</li>`);
  const titleItems = (s.titles || []).map((t) => `<li>🏅 ${escapeHtml(titleLabel(t))}</li>`);
  $("#sw-skills").innerHTML = [...classItems, ...titleItems, ...skillItems].join("") || '<li class="hint">None yet.</li>';
  const currency = s.currency || {};
  const misc = [
    (s._tracks_currency !== false && currency.tracked !== false && currency.name) ? `<div><b>${escapeHtml(currency.amount ?? 0)}</b> ${escapeHtml(currency.name)}</div>` : "",
    `<div>Turn ${escapeHtml(s.turn ?? 0)}</div>`,
    (s.affiliations || []).length ? `<div>${escapeHtml((s.affiliations[0] || {}).rank || "Member")} — ${escapeHtml((s.affiliations[0] || {}).faction || "")}</div>` : "",
  ].filter(Boolean).join("");
  $("#sw-misc").innerHTML = misc || '<div class="hint">Unaffiliated.</div>';
}
$("#btn-status-window-ok").addEventListener("click", async () => {
  closeModal("modal-status-window");
  APP.statusWindowOpen = false;
  try { await apiPost("/api/status_window/dismiss", {}); } catch (e) { /* best effort */ }
});

function renderQueuedActions(actions) {
  const box = $("#queued-actions");
  if (!box) return;
  if (!actions.length) {
    box.innerHTML = '<p class="hint">No actions queued. Add as many as you want, in order.</p>';
    return;
  }
  const unit = $("#time-unit")?.value || "moment";
  const amount = Number($("#time-amount")?.value || 1);
  const totalDays = unit === "days" ? amount : unit === "weeks" ? amount * 7 : unit === "months" ? amount * 30 : 0;
  const span = actions.length && totalDays ? totalDays / actions.length : 0;
  // This is only a quick itinerary label, not the real difficulty
  // assessment. Avoid implying that ordinary training or diplomacy needs a
  // roll; the deterministic assessment shown after Advance is authoritative.
  const actionType = (action) => /kill|death|assassinate|alone against|boss|invade/i.test(action) ? "Potentially lethal" : /fight|attack|duel|battle/i.test(action) ? "Combat" : /infiltrate|steal|escape/i.test(action) ? "Risky approach" : /master|awaken|evolve|bankai|domain expansion/i.test(action) ? "Major growth goal" : /train|practice|study|research|craft/i.test(action) ? "Focused growth" : /persuade|convince|negotiate|diplom/i.test(action) ? "Social action" : "Routine";
  const schedule = (index) => {
    if (unit === "moment") return index ? "Held for a later Advance" : "Next meaningful beat · up to 24 hours";
    if (unit === "next_event") return `Step ${index + 1} before the next major turning point`;
    const start = Math.floor(index * span) + 1, end = Math.max(start, Math.round((index + 1) * span));
    return `Approx. day ${start}${end > start ? `–${end}` : ""} · ${actionType(actions[index])}`;
  };
  const countdown = APP.state?._canon_countdown?.available ? `<div class="queue-interruption">Possible interruption: ${escapeHtml(APP.state._canon_countdown.label)}</div>` : "";
  box.innerHTML = actions.map((action, index) => `<div class="queued-action" data-action-index="${index}"><span class="queue-index">${index + 1}</span><span class="queue-copy"><b>${escapeHtml(action)}</b><small>${escapeHtml(schedule(index))}</small></span><span class="queue-controls"><button type="button" data-move-action="${index}" data-to-index="${index - 1}" title="Move earlier" ${index === 0 ? "disabled" : ""}>↑</button><button type="button" data-move-action="${index}" data-to-index="${index + 1}" title="Move later" ${index === actions.length - 1 ? "disabled" : ""}>↓</button><button type="button" data-duplicate-action="${index}" title="Duplicate queued action">⧉</button><button type="button" data-edit-action="${index}" title="Edit queued action">✎</button><button type="button" data-remove-action="${index}" title="Remove queued action">✕</button></span></div>`).join("") + countdown;
  if (APP.state) renderMobileState(APP.state);
}

$("#btn-music-play").addEventListener("click", async () => {
  if (!APP.music.tracks.length) await refreshMusic(APP.state?.world);
  const player = musicPlayer();
  if (!APP.music.tracks.length) { showToast("No music files found for this world or Shared.", "system"); return; }
  APP.music.userStarted = true;
  if (player.paused) { APP.musicEnabled = true; player.play().then(renderMusicStatus).catch(() => showToast("This file's audio codec is not supported. MP3 is recommended.", "danger")); }
  else { player.pause(); renderMusicStatus(); }
});
$("#btn-music-prev").addEventListener("click", () => { APP.music.userStarted = true; APP.musicEnabled = true; loadMusicTrack(APP.music.index - 1, true); });
$("#btn-music-next").addEventListener("click", () => { APP.music.userStarted = true; APP.musicEnabled = true; loadMusicTrack(APP.music.index + 1, true); });
$("#btn-music-refresh").addEventListener("click", () => refreshMusic(APP.state?.world, APP.music.userStarted));
$("#btn-music-folder").addEventListener("click", () => openMusicFolder().catch((e) => showToast(e.message, "danger")));
musicPlayer().addEventListener("ended", () => loadMusicTrack(APP.music.index + 1, true));
musicPlayer().addEventListener("play", renderMusicStatus);
musicPlayer().addEventListener("pause", renderMusicStatus);

function setMusicWidgetVolume(value, persist = false) {
  const volume = Math.max(0, Math.min(1, Number(value ?? .35)));
  APP.musicVolume = volume;
  musicPlayer().volume = volume;
  if ($("#music-widget-volume")) $("#music-widget-volume").value = volume;
  if ($("#st-music-volume")) $("#st-music-volume").value = volume;
  if ($("#music-volume-value")) $("#music-volume-value").textContent = `${Math.round(volume * 100)}%`;
  if (persist) apiPost("/api/settings", { music_volume: volume }).catch((error) => showToast(error.message, "danger"));
}
$("#music-widget-volume").addEventListener("input", (event) => setMusicWidgetVolume(event.target.value, false));
$("#music-widget-volume").addEventListener("change", (event) => setMusicWidgetVolume(event.target.value, true));

$("#queued-actions").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-remove-action], [data-edit-action], [data-move-action], [data-duplicate-action]");
  if (!button || APP.busy) return;
  try {
    let result;
    if (button.hasAttribute("data-remove-action")) {
      result = await apiPost("/api/actions/remove", { index: Number(button.getAttribute("data-remove-action")) });
    } else if (button.hasAttribute("data-move-action")) {
      result = await apiPost("/api/actions/move", { index: Number(button.getAttribute("data-move-action")), to_index: Number(button.getAttribute("data-to-index")) });
    } else if (button.hasAttribute("data-duplicate-action")) {
      const index = Number(button.getAttribute("data-duplicate-action"));
      result = await apiPost("/api/actions/queue", { action: APP.state.queued_actions[index] });
    } else {
      const index = Number(button.getAttribute("data-edit-action"));
      const revised = window.prompt("Edit queued action", APP.state.queued_actions[index]);
      if (revised === null) return;
      result = await apiPost("/api/actions/update", { index, action: revised });
    }
    APP.state.queued_actions = result.queued_actions || [];
    renderQueuedActions(APP.state.queued_actions);
  } catch (error) { showToast(error.message, "danger"); }
});

const WEAPON_KEY_RE = /weapon|sword|blade|staff|bow|spear|gun|dagger|fist|knife|axe|hammer|held/i;
function isWeaponSlot(key) { return WEAPON_KEY_RE.test(key); }

// ---------------------------------------------------------------------------
// Equipment mannequin — hover a body zone to see what's equipped there and
// its effect. Only shown for "full" gear-style worlds (Overgeared, Solo
// Max-Level Newbie, Custom World) where itemization actually matters.
// ---------------------------------------------------------------------------
const MANNEQUIN_ZONES = [
  { key: "head", label: "Head", re: /head|helm|hat|crown|circlet/i, cx: 150, cy: 30, r: 22 },
  { key: "chest", label: "Chest", re: /chest|armor|robe|vest|body|breastplate/i, cx: 150, cy: 109, rw: 36, rh: 52 },
  { key: "weapon", label: "Weapon", re: WEAPON_KEY_RE, cx: 90, cy: 130, r: 19 },
  { key: "offhand", label: "Off-Hand", re: /shield|off.?hand/i, cx: 210, cy: 130, r: 19 },
  { key: "legs", label: "Legs", re: /legs|pants|greaves|trousers/i, cx: 150, cy: 207, rw: 36, rh: 26 },
  { key: "feet", label: "Feet", re: /feet|boots|shoes|sandals/i, cx: 150, cy: 240, rw: 34, rh: 11 },
  { key: "accessory", label: "Accessory", re: /ring|necklace|amulet|accessory|bracelet|earring|belt/i, cx: 150, cy: 70, r: 11 },
];

function buildMannequinHtml(eq) {
  const entries = Object.entries(eq);
  const matched = new Set();
  const zoneItems = MANNEQUIN_ZONES.map((z) => {
    const hit = entries.find(([k]) => z.re.test(k));
    if (hit) matched.add(hit[0]);
    return { ...z, item: hit ? hit[1] : null, itemKey: hit ? hit[0] : null };
  });
  const leftover = entries.filter(([k]) => !matched.has(k));

  const shapes = zoneItems.map((z) => {
    const filled = z.item ? "filled" : "";
    const shape = z.rw
      ? `<rect class="mq-zone ${filled}" data-tip="${escapeHtml(z.label)}: ${escapeHtml(z.item || "empty")}" x="${z.cx - z.rw}" y="${z.cy - z.rh}" width="${z.rw * 2}" height="${z.rh * 2}" rx="10"/>`
      : `<circle class="mq-zone ${filled}" data-tip="${escapeHtml(z.label)}: ${escapeHtml(z.item || "empty")}" cx="${z.cx}" cy="${z.cy}" r="${z.r}"/>`;
    return shape;
  }).join("");

  // A proper front-facing humanoid outline (head, neck, shoulders, arms
  // bending in at the waist, hips, two separate legs, two feet) instead of
  // the old ellipse-plus-two-rects blob. Interactive mq-zone shapes above
  // overlay this at the matching body position.
  const svg = `<svg class="mannequin-svg" viewBox="0 0 300 260" xmlns="http://www.w3.org/2000/svg">
    <ellipse cx="150" cy="204" rx="58" ry="14" class="mq-shadow"/>
    <circle cx="150" cy="30" r="19" class="mq-silhouette"/>
    <circle cx="143" cy="27" r="2.2" class="mq-face"/>
    <circle cx="157" cy="27" r="2.2" class="mq-face"/>
    <rect x="142" y="46" width="16" height="12" class="mq-silhouette"/>
    <path class="mq-silhouette" d="M150,55
      C121,55 109,61 101,77
      C95,89 91,104 87,121
      C85,129 89,133 95,131
      C101,129 104,117 108,103
      C111,93 115,85 121,79
      L123,129
      C119,139 117,149 117,159
      L183,159
      C183,149 181,139 177,129
      L179,79
      C185,85 189,93 192,103
      C196,117 199,129 205,131
      C211,133 215,129 213,121
      C209,104 205,89 199,77
      C191,61 179,55 150,55 Z"/>
    <path class="mq-silhouette" d="M117,159 L183,159 L179,181 L121,181 Z"/>
    <path class="mq-silhouette" d="M121,181 L148,181 L145,231 L127,231 Z"/>
    <path class="mq-silhouette" d="M152,181 L179,181 L173,231 L155,231 Z"/>
    <ellipse cx="133" cy="239" rx="15" ry="8" class="mq-silhouette"/>
    <ellipse cx="167" cy="239" rx="15" ry="8" class="mq-silhouette"/>
    ${shapes}
  </svg>`;

  return `<div class="mannequin-wrap"><div class="mannequin-tooltip" id="mannequin-tip" style="display:none"></div>${svg}</div>` +
    (leftover.length ? `<div class="jrow"><b>Other Equipped</b><br/>${leftover.map(([k, v]) => `${escapeHtml(k)}: ${escapeHtml(v)}`).join("<br/>")}</div>` : "");
}

function wireMannequinTooltips() {
  const tip = $("#mannequin-tip");
  $$(".mq-zone").forEach((el) => {
    el.addEventListener("mouseenter", () => { tip.textContent = el.getAttribute("data-tip"); tip.style.display = "block"; });
    el.addEventListener("mouseleave", () => { tip.style.display = "none"; });
  });
}

function renderGearPanel(s) {
  const eq = s.equipment || {};
  const keys = Object.keys(eq);
  const panel = $("#gear-panel");
  const full = s._gear_style === "full";
  const shown = full ? keys : keys.filter(isWeaponSlot).length ? keys.filter(isWeaponSlot) : keys.slice(0, 1);
  $("#gear-panel-title").textContent = full ? "Gear" : "Weapon";
  if (!shown.length) { panel.style.display = "none"; return; }
  panel.style.display = "";
  $("#gear-list").classList.remove("empty");
  $("#gear-list").innerHTML = shown.map((k) => `<li><b>${escapeHtml(k)}</b>: ${escapeHtml(eq[k])}</li>`).join("");
}

function renderTagList(sel, arr, fmt, emptyText) {
  const el = $(sel);
  if (!arr.length) { el.classList.add("empty"); el.textContent = emptyText; return; }
  el.classList.remove("empty");
  el.innerHTML = arr.map((x) => `<li>${fmt(x)}</li>`).join("");
}
function renderTagListHtml(sel, htmlItems, emptyText) {
  const el = $(sel);
  if (!htmlItems.length) { el.classList.add("empty"); el.textContent = emptyText; return; }
  el.classList.remove("empty");
  el.innerHTML = htmlItems.map((h) => `<li>${h}</li>`).join("");
}

function renderMessagesPanel(s) {
  const threads = s.chat_threads || {};
  const unread = s.unread_chats || [];
  const rows = [];
  Object.entries(threads).forEach(([name, msgs]) => {
    if (!msgs.length) return;
    const last = msgs[msgs.length - 1];
    const isUnread = unread.some((u) => u.thread === name);
    rows.push({ name, last, isUnread, time: last.turn || 0 });
  });
  rows.sort((a, b) => b.time - a.time);
  const contacts = s.contacts || {};
  const items = rows.slice(0, 6).map((r) => `<span class="message-preview">${personPortraitHtml(r.name, contacts[r.name] || {}, { size: "xs" })}<span><b>${escapeHtml(r.name)}</b>${r.isUnread ? '<span class="unread-badge">•</span>' : ""}<small>${escapeHtml((r.last.text || "").slice(0, 60))}</small></span></span>`);
  renderTagListHtml("#messages-list", items, "No messages yet.");
}

const SCENE_ICON = { town_square: "sun", kingdom: "sun", indoor_grandhall: "sun", merchant_shop:"fire", tavern_inn:"fire", academy_classroom:"sun", ship_deck:"wind", arena_floor:"sun", harbor_port: "sun", forest_path: "wind", mountain_castle: "wind", starry_sky: "moon", night_wilderness: "moon", battlefield_dusk: "fire", monster_battlefield: "fire", duel: "wind", monster_lair: "fire", dungeon_cave: "cloud", tower_hub: "cloud" };
function updateWorldSystemIcons(s) {
  const cat = s._scene_category || "starry_sky";
  const active = SCENE_ICON[cat] || "sun";
  ["sun", "fire", "cloud", "wind", "moon"].forEach((k) => $("#sys-" + k).classList.toggle("active", k === active));
}

// ---------------------------------------------------------------------------
// Scene image + ambient FX
// ---------------------------------------------------------------------------
let scenePaint = { canvas: null, ctx: null, w: 0, h: 0, lastKey: null };

// Weather is tracked in state and normalized to the small native visual
// vocabulary used by the scene, portrait, and map ambience layers.
function weatherKeyFor(weather) {
  const w = String(weather || "").toLowerCase();
  if (/storm|thunder|typhoon|hurricane/.test(w)) return "storm";
  if (/rain|drizzle|monsoon/.test(w)) return "rain";
  if (/snow|blizzard|sleet/.test(w)) return "snow";
  if (/fog|mist|haze/.test(w)) return "fog";
  return "";
}

const FIRE_SCENES = new Set(["merchant_shop", "tavern_inn", "indoor_grandhall", "dungeon_cave", "monster_lair", "battlefield_dusk"]);
const STAR_SCENES = new Set(["starry_sky", "night_wilderness", "tower_hub"]);
const WIND_SCENES = new Set(["harbor_port", "ship_deck", "forest_path", "mountain_castle", "snow_region"]);
const WORLD_VISUAL_PROFILES = {
  "Naruto": { idle: "sakura", training: "chakra", portrait: "sakura" },
  "One Piece": { idle: "sea-spray", training: "wind", portrait: "sea-spray" },
  "Hunter x Hunter": { idle: "leaves", training: "nen", portrait: "nen" },
  "Bleach": { idle: "reishi", training: "spirit", portrait: "reishi" },
  "Jujutsu Kaisen": { idle: "cursed", training: "cursed", portrait: "cursed" },
  "Overgeared": { idle: "forge", training: "energy", portrait: "forge" },
  "Solo Max-Level Newbie": { idle: "tower", training: "system", portrait: "tower" },
  "Reincarnated as a Slime": { idle: "magicules", training: "magic", portrait: "magicules" },
  "Custom World": { idle: "motes", training: "energy", portrait: "motes" },
};

function timeOfDayFor(s) {
  const hour = Number(s?.calendar?.hour);
  if (Number.isFinite(hour)) {
    if (hour < 5 || hour >= 21) return "night";
    if (hour < 8) return "dawn";
    if (hour < 17) return "day";
    if (hour < 20) return "dusk";
    return "night";
  }
  const text = String(s?.world_time || "").toLowerCase();
  if (/night|midnight/.test(text)) return "night";
  if (/dawn|sunrise|morning/.test(text)) return "dawn";
  if (/dusk|sunset|evening/.test(text)) return "dusk";
  return "day";
}

function activityFor(s) {
  if (s?.combat?.active) return "combat";
  const text = [s?.current_activity, ...(s?.queued_actions || []), ...(s?.standing_orders || [])].join(" ").toLowerCase();
  if (/train|practice|study|meditat|spar/.test(text)) return "training";
  if (/travel|sail|walk|fly|journey|depart/.test(text)) return "travel";
  if (/craft|forge|smith|cook|brew/.test(text)) return "crafting";
  if (/talk|meet|negot|ask|diploma/.test(text)) return "social";
  return "idle";
}

function ambientModeFor(category, weather, s) {
  const weatherMode = weatherKeyFor(weather);
  if (weatherMode) return weatherMode;
  const profile = WORLD_VISUAL_PROFILES[s?.world] || WORLD_VISUAL_PROFILES["Custom World"];
  if (s?.combat?.active || ["duel", "monster_battlefield", "battlefield_dusk"].includes(category)) return "sparks";
  if (s?.world === "Naruto") return "sakura";
  if (activityFor(s) === "training") return profile.training;
  if (FIRE_SCENES.has(category)) return "embers";
  if (STAR_SCENES.has(category)) return "stars";
  if (WIND_SCENES.has(category)) return category === "forest_path" ? "leaves" : "wind";
  if (category === "rain_city") return "rain";
  if (category === "underwater") return "bubbles";
  if (s?.world === "Overgeared" && activityFor(s) === "crafting") return "embers";
  return profile.idle;
}

function stableAmbientUnit(seed) {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) { h ^= seed.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) / 4294967295;
}

function fillAmbientLayer(el, mode, count, key) {
  if (!el) return;
  const renderKey = `${mode}:${count}:${key}`;
  if (el.dataset.renderKey === renderKey) return;
  el.dataset.renderKey = renderKey;
  el.dataset.effect = mode;
  el.replaceChildren(...Array.from({ length: count }, (_, index) => {
    const mote = document.createElement("i");
    const u = (suffix) => stableAmbientUnit(`${key}:${index}:${suffix}`);
    mote.style.setProperty("--x", `${Math.round(u("x") * 100)}%`);
    mote.style.setProperty("--y", `${Math.round(u("y") * 100)}%`);
    mote.style.setProperty("--size", `${(2 + u("s") * 7).toFixed(1)}px`);
    mote.style.setProperty("--delay", `${(-u("d") * 9).toFixed(2)}s`);
    mote.style.setProperty("--duration", `${(4 + u("t") * 8).toFixed(2)}s`);
    mote.style.setProperty("--drift", `${Math.round((u("r") - .5) * 80)}px`);
    return mote;
  }));
}

function applyNativeSceneFx(category, weather, s) {
  const layer = $("#scene-ambient");
  const mode = ambientModeFor(category, weather, s);
  const time = timeOfDayFor(s);
  const activity = activityFor(s);
  document.body.setAttribute("data-time", time);
  document.body.setAttribute("data-weather", weatherKeyFor(weather) || "clear");
  document.body.setAttribute("data-activity", activity);
  layer.dataset.time = time;
  layer.dataset.activity = activity;
  const lighting = $("#scene-lighting");
  if (lighting) {
    lighting.dataset.time = time;
    lighting.dataset.weather = weatherKeyFor(weather) || "clear";
    lighting.dataset.activity = activity;
  }
  const count = mode === "rain" || mode === "snow" ? 26 : mode === "sakura" ? 24 : 18;
  fillAmbientLayer(layer, mode, count, `${s?.world}:${category}:${mode}`);
}

function applyPortraitAmbient(s) {
  const layer = $("#portrait-ambient");
  if (!layer) return;
  const profile = WORLD_VISUAL_PROFILES[s?.world] || WORLD_VISUAL_PROFILES["Custom World"];
  const formEffect = portraitFormEffect(s);
  const mode = formEffect === "bijuu" ? "chakra" : formEffect === "bankai" || formEffect === "shikai" ? "reishi" : formEffect === "domain" ? "cursed" : formEffect === "system" ? "tower" : s?.combat?.active ? "sparks" : s?.world === "Naruto" ? "sakura" : s?.world === "Overgeared" && activityFor(s) === "crafting" ? "embers" : profile.portrait;
  fillAmbientLayer(layer, mode, mode === "sakura" ? 16 : 12, `portrait:${s?.world}:${mode}`);
}

function applyWorldAtmosphere(s) {
  const layer = $("#world-atmosphere");
  const lighting = $("#world-lighting");
  if (!layer || !lighting) return;
  const profile = WORLD_VISUAL_PROFILES[s?.world] || WORLD_VISUAL_PROFILES["Custom World"];
  const mode = weatherKeyFor(s?.weather) || (s?.combat?.active ? "sparks" : profile.idle);
  const count = isMobileLayout() ? 8 : 14;
  fillAmbientLayer(layer, mode, count, `world:${s?.world}:${mode}`);
  lighting.dataset.time = timeOfDayFor(s);
  lighting.dataset.weather = weatherKeyFor(s?.weather) || "clear";
  lighting.dataset.activity = activityFor(s);
}

function portraitFormEffect(s) {
  const form = s?._portrait_active_form && typeof s._portrait_active_form === "object" ? s._portrait_active_form : {};
  const text = `${form.name || ""} ${form.description || ""} ${form.effect || ""}`.toLowerCase();
  if (!text.trim()) return "";
  if (/tailed|jinch|biju|bijū|chakra cloak|nine[- ]tails/.test(text)) return "bijuu";
  if (/bankai/.test(text)) return "bankai";
  if (/shikai|first release/.test(text)) return "shikai";
  if (/domain expansion|innate domain/.test(text)) return "domain";
  if (/sharingan|rinnegan|byakugan|d[ōo]jutsu|mangeky|eye/.test(text)) return "dojutsu";
  if (/system|monarch|tower/.test(text)) return "system";
  if (/evol|transform|awaken|form|mode/.test(text)) return "evolution";
  return "aura";
}

function applyNativeMapFx(nodes) {
  const layer = $("#map-ambient");
  if (!layer) return;
  const dangerNodes = (nodes || []).filter((n) => String(n.danger_level || "").toLowerCase() === "critical");
  const glows = dangerNodes.map((node) => {
    const glow = document.createElement("i");
    glow.className = "map-danger-glow";
    glow.style.left = `${node.x}%`;
    glow.style.top = `${node.y}%`;
    return glow;
  });
  const markers = (nodes || []).flatMap((node) => {
    const words = `${node.name || ""} ${node.kind || ""} ${node.status || ""}`.toLowerCase();
    let kind = "";
    if (node.recently_changed) kind = "claim";
    else if (/portal|gate|rift|garganta|senkaimon/.test(words)) kind = "portal";
    else if (/burn|fire|volcan|eruption/.test(words)) kind = "fire";
    else if (/storm|typhoon|hurricane|blizzard/.test(words)) kind = "storm";
    else if (String(node.danger_level || "").toLowerCase() === "critical") kind = "conflict";
    if (!kind) return [];
    const marker = document.createElement("i");
    marker.className = `map-event-marker map-event-${kind}`;
    marker.style.left = `${node.x}%`;
    marker.style.top = `${node.y}%`;
    return [marker];
  });
  const fog = (nodes || []).filter((node) => !node.discovered).slice(0, 14).map((node) => {
    const pocket = document.createElement("i");
    pocket.className = "map-fog-pocket";
    pocket.style.left = `${node.x}%`;
    pocket.style.top = `${node.y}%`;
    return pocket;
  });
  layer.replaceChildren(...fog, ...glows, ...markers);
  layer.dataset.dangerCount = String(dangerNodes.length);
}

function playSceneTransition(kind, s) {
  if (!APP.animationsEnabled) return;
  const transition = $("#scene-transition");
  transition.dataset.kind = kind;
  transition.dataset.world = s?.world || "Custom World";
  transition.classList.remove("playing");
  void transition.offsetWidth;
  transition.classList.add("playing");
}

function updateScene(s) {
  const url = s._scene_image;
  const cat = s._scene_category || "starry_sky";
  const sceneLabel = s._scene_label || cat;
  const img = $("#scene-img");
  document.body.setAttribute("data-scene", cat);
  const sceneBadge = $("#scene-category-badge");
  sceneBadge.textContent = sceneLabel.replace(/_/g, " ").toUpperCase();
  const artMatch = s._scene_confidence || {};
  sceneBadge.title = artMatch.score !== undefined
    ? `Art match ${artMatch.score}% · ${artMatch.label || "Environment"}: ${artMatch.reason || s._scene_reason || ""}`
    : (s._scene_reason || "Environment art selected from current location and activity.");
  $("#scene-location").textContent = s.location || "Unknown";
  $("#scene-world").textContent = s.world || "Custom World";

  applyNativeSceneFx(cat, s.weather, s);

  // A location change gets a quick cut-to-black-and-back in the scene box
  // only — deliberately not anywhere else in the UI — so travel reads as a
  // moment instead of the background image just silently swapping.
  if (APP.lastLocation === null) {
    APP.lastLocation = s.location;
  } else if (s.location && s.location !== APP.lastLocation) {
    APP.lastLocation = s.location;
    playSceneTransition("travel", s);
  }
  const combatActive = Boolean(s.combat?.active);
  if (combatActive && !APP.lastCombatActive) playSceneTransition("combat", s);
  APP.lastCombatActive = combatActive;
  const majorVisualKey = String(s.active_canon_event || s.active_major_event || "");
  if (majorVisualKey && majorVisualKey !== APP.lastMajorVisualKey) playSceneTransition("event", s);
  APP.lastMajorVisualKey = majorVisualKey;

  if (url) {
    if (img.getAttribute("data-src") !== url) {
      img.setAttribute("data-src", url);
      img.classList.remove("loaded");
      const pre = new Image();
      pre.onload = () => { img.src = url; requestAnimationFrame(() => img.classList.add("loaded")); };
      pre.src = url;
    }
  } else {
    img.removeAttribute("src");
    img.removeAttribute("data-src");
    img.classList.remove("loaded");
  }
  paintScene(cat, s.world || "Custom World");
}

// ---- Procedural scene fallback ------------------------------------------
// Generated environment art is the primary scene layer. This painter remains
// underneath it as an instant-loading fallback and preserves world tinting if
// a custom scene asset is absent. The particle canvas supplies subtle motion.
const SKY_BY_CATEGORY = {
  town_square: ["#3a6b8a", "#e8b774"], kingdom: ["#2c5678", "#e0a45f"], indoor_grandhall: ["#241a12", "#4a3420"],
  harbor_port: ["#2f7896", "#bfe6dc"], forest_path: ["#1f4a3a", "#5c9468"], mountain_castle: ["#233a55", "#8fa8c2"],
  battlefield_dusk: ["#2a1418", "#a3452f"], monster_lair: ["#0a0a10", "#241826"], dungeon_cave: ["#08090d", "#1c222c"],
  starry_sky: ["#040814", "#152238"], night_wilderness: ["#050a12", "#16233a"], tower_hub: ["#04060f", "#0e1a2e"],
  duel: ["#182238", "#b45d3d"], monster_battlefield: ["#16080c", "#6e1d1a"],
};

function resizeScenePaint() {
  const c = scenePaint.canvas;
  if (!c) return;
  const rect = c.parentElement.getBoundingClientRect();
  scenePaint.w = c.width = rect.width;
  scenePaint.h = c.height = rect.height;
}
window.addEventListener("resize", () => { resizeScenePaint(); if (scenePaint.lastKey) { const [cat, world] = scenePaint.lastKey.split("::"); drawScene(cat, world); } });

function paintScene(cat, world) {
  if (!scenePaint.canvas) {
    scenePaint.canvas = $("#scene-paint");
    scenePaint.ctx = scenePaint.canvas.getContext("2d");
  }
  const key = cat + "::" + world;
  resizeScenePaint();
  drawScene(cat, world);
  scenePaint.lastKey = key;
  requestAnimationFrame(() => scenePaint.canvas.classList.add("loaded"));
}

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}
function rgba(hex, a) { const [r, g, b] = hexToRgb(hex); return `rgba(${r},${g},${b},${a})`; }

function drawScene(cat, world) {
  const ctx = scenePaint.ctx, w = scenePaint.w, h = scenePaint.h;
  if (!ctx || !w || !h) return;
  ctx.clearRect(0, 0, w, h);
  const cs = getComputedStyle(document.body);
  const accent = (cs.getPropertyValue("--accent") || "#c7a15c").trim();
  const accent2 = (cs.getPropertyValue("--accent2") || "#75b6c8").trim();
  const sky = SKY_BY_CATEGORY[cat] || SKY_BY_CATEGORY.starry_sky;

  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, sky[0]);
  grad.addColorStop(0.55, mixHex(sky[0], sky[1], 0.5));
  grad.addColorStop(1, mixHex(sky[1], accent, 0.28));
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  // soft horizon glow
  const glow = ctx.createRadialGradient(w * 0.5, h * 0.72, 10, w * 0.5, h * 0.72, w * 0.6);
  glow.addColorStop(0, rgba(accent2, 0.16));
  glow.addColorStop(1, rgba(accent2, 0));
  ctx.fillStyle = glow; ctx.fillRect(0, 0, w, h);

  // soft nebula/cloud wash for night-flavored categories — breaks up the flat gradient
  if (["starry_sky", "night_wilderness", "tower_hub", "monster_lair", "dungeon_cave"].includes(cat)) {
    for (let i = 0; i < 3; i++) {
      const nx = w * rand(0.1, 0.9), ny = h * rand(0.05, 0.5), nr = w * rand(0.18, 0.34);
      const neb = ctx.createRadialGradient(nx, ny, 0, nx, ny, nr);
      neb.addColorStop(0, rgba(i % 2 ? accent2 : accent, 0.10));
      neb.addColorStop(1, rgba(accent2, 0));
      ctx.fillStyle = neb; ctx.fillRect(0, 0, w, h);
    }
  }

  const drawSkyline = (baseY, count, minH, maxH, color, alpha) => {
    ctx.fillStyle = rgba(color, alpha);
    let x = -20;
    while (x < w + 20) {
      const bw = rand(w / count * 0.5, w / count * 1.1);
      const bh = rand(minH, maxH);
      ctx.fillRect(x, baseY - bh, bw, bh + 40);
      if (Math.random() > 0.5) { ctx.beginPath(); ctx.moveTo(x, baseY - bh); ctx.lineTo(x + bw / 2, baseY - bh - rand(10, 26)); ctx.lineTo(x + bw, baseY - bh); ctx.closePath(); ctx.fill(); }
      x += bw + rand(2, 10);
    }
  };
  const drawMountains = (baseY, amp, color, alpha, seedOffset) => {
    ctx.fillStyle = rgba(color, alpha);
    ctx.beginPath(); ctx.moveTo(0, h);
    for (let x = 0; x <= w; x += w / 14) ctx.lineTo(x, baseY - Math.abs(Math.sin(x * 0.01 + seedOffset)) * amp - rand(0, amp * 0.3));
    ctx.lineTo(w, h); ctx.closePath(); ctx.fill();
  };
  const drawTrees = (baseY, count, color, alpha) => {
    ctx.fillStyle = rgba(color, alpha);
    for (let i = 0; i < count; i++) {
      const x = (w / count) * i + rand(-10, 10);
      const th = rand(h * 0.12, h * 0.3);
      ctx.beginPath(); ctx.moveTo(x, baseY); ctx.lineTo(x + th * 0.32, baseY); ctx.lineTo(x + th * 0.16, baseY - th); ctx.closePath(); ctx.fill();
    }
  };

  if (cat === "town_square" || cat === "kingdom" || cat === "indoor_grandhall") {
    drawMountains(h * 0.62, h * 0.1, accent2, 0.14, 1);
    drawSkyline(h * 0.78, 16, h * 0.08, h * 0.24, "#000000", 0.38);
    drawSkyline(h * 0.86, 22, h * 0.05, h * 0.16, "#000000", 0.55);
    if (cat === "kingdom") {
      ctx.fillStyle = rgba(accent, 0.75);
      ctx.beginPath(); ctx.moveTo(w * 0.44, h * 0.72); ctx.lineTo(w * 0.48, h * 0.5); ctx.lineTo(w * 0.5, h * 0.6); ctx.lineTo(w * 0.52, h * 0.46); ctx.lineTo(w * 0.56, h * 0.72); ctx.closePath(); ctx.fill();
    }
  } else if (cat === "harbor_port") {
    ctx.fillStyle = rgba("#0a2230", 0.5);
    ctx.fillRect(0, h * 0.74, w, h * 0.3);
    for (let i = 0; i < 4; i++) {
      const x = w * (0.15 + i * 0.22);
      ctx.strokeStyle = rgba("#000000", 0.5); ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(x, h * 0.55); ctx.lineTo(x, h * 0.78); ctx.stroke();
      ctx.fillStyle = rgba(accent, 0.6);
      ctx.beginPath(); ctx.moveTo(x, h * 0.55); ctx.lineTo(x + 26, h * 0.63); ctx.lineTo(x, h * 0.7); ctx.closePath(); ctx.fill();
    }
    drawSkyline(h * 0.82, 20, h * 0.03, h * 0.08, "#000000", 0.4);
  } else if (cat === "forest_path") {
    drawMountains(h * 0.5, h * 0.08, accent2, 0.1, 2);
    drawTrees(h * 0.86, 9, "#04140c", 0.5);
    drawTrees(h * 0.95, 13, "#020c07", 0.72);
  } else if (cat === "mountain_castle") {
    drawMountains(h * 0.55, h * 0.28, accent2, 0.28, 0.5);
    drawMountains(h * 0.68, h * 0.2, "#0c1420", 0.6, 2.2);
    ctx.fillStyle = rgba(accent, 0.7);
    ctx.fillRect(w * 0.46, h * 0.34, w * 0.03, h * 0.16);
    ctx.beginPath(); ctx.moveTo(w * 0.44, h * 0.34); ctx.lineTo(w * 0.475, h * 0.26); ctx.lineTo(w * 0.51, h * 0.34); ctx.closePath(); ctx.fill();
  } else if (cat === "duel") {
    drawMountains(h * 0.66, h * 0.12, accent2, 0.18, 1.8);
    ctx.fillStyle = rgba("#08080b", 0.72); ctx.fillRect(0, h * 0.78, w, h * 0.22);
    // Two readable fighting silhouettes, separated so the scene immediately
    // reads as a one-on-one confrontation rather than a generic battlefield.
    const fighter = (x, facing) => {
      ctx.save(); ctx.translate(x, h * 0.74); ctx.scale(facing, 1);
      ctx.fillStyle = rgba("#030305", 0.92);
      ctx.beginPath(); ctx.arc(0, -56, 12, 0, 7); ctx.fill();
      ctx.fillRect(-10, -45, 22, 39); ctx.fillRect(-8, -8, 8, 35); ctx.fillRect(6, -8, 8, 35);
      ctx.save(); ctx.translate(8, -36); ctx.rotate(-0.7); ctx.fillRect(0, -4, 48, 8); ctx.restore();
      ctx.strokeStyle = rgba(accent, 0.9); ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(46, -73); ctx.lineTo(12, -34); ctx.stroke();
      ctx.restore();
    };
    fighter(w * 0.32, 1); fighter(w * 0.68, -1);
  } else if (cat === "battlefield_dusk" || cat === "monster_battlefield") {
    ctx.fillStyle = rgba("#1a0a08", 0.6);
    ctx.fillRect(0, h * 0.78, w, h * 0.22);
    for (let i = 0; i < 10; i++) {
      const x = rand(0, w);
      ctx.strokeStyle = rgba("#050505", 0.6); ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(x, h * 0.8); ctx.lineTo(x + rand(-14, 14), h * 0.8 - rand(20, 60)); ctx.stroke();
    }
    if (cat === "monster_battlefield") {
      for (let i = 0; i < 11; i++) {
        const x = w * (0.04 + i * 0.09), y = h * rand(0.64, 0.79), size = rand(9, 18);
        ctx.fillStyle = rgba("#020203", 0.82);
        ctx.beginPath(); ctx.arc(x, y - size, size, Math.PI, 0); ctx.lineTo(x + size, y); ctx.lineTo(x - size, y); ctx.closePath(); ctx.fill();
        ctx.fillStyle = rgba(i % 2 ? accent : accent2, 0.8); ctx.fillRect(x - size * .45, y - size * 1.15, 2, 2); ctx.fillRect(x + size * .3, y - size * 1.15, 2, 2);
      }
    }
  } else if (cat === "monster_lair" || cat === "dungeon_cave") {
    ctx.fillStyle = "#000000";
    for (let i = 0; i < 8; i++) { const x = (w / 8) * i + rand(-10, 10); const dh = rand(h * 0.08, h * 0.32); ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x + 30, 0); ctx.lineTo(x + 15, dh); ctx.closePath(); ctx.fill(); }
    for (let i = 0; i < 8; i++) { const x = (w / 8) * i + rand(-10, 10); const dh = rand(h * 0.1, h * 0.34); ctx.beginPath(); ctx.moveTo(x, h); ctx.lineTo(x + 34, h); ctx.lineTo(x + 17, h - dh); ctx.closePath(); ctx.fill(); }
    const vign = ctx.createRadialGradient(w / 2, h / 2, h * 0.15, w / 2, h / 2, h * 0.9);
    vign.addColorStop(0, "rgba(0,0,0,0)"); vign.addColorStop(1, "rgba(0,0,0,.75)");
    ctx.fillStyle = vign; ctx.fillRect(0, 0, w, h);
    if (cat === "monster_lair") { ctx.fillStyle = rgba(accent2, 0.5); ctx.beginPath(); ctx.arc(w * 0.5, h * 0.6, 5, 0, 7); ctx.arc(w * 0.54, h * 0.6, 5, 0, 7); ctx.fill(); }
  } else if (cat === "starry_sky" || cat === "night_wilderness") {
    const moonX = w * 0.8, moonY = h * 0.22;
    const bloom = ctx.createRadialGradient(moonX, moonY, 4, moonX, moonY, 70);
    bloom.addColorStop(0, rgba(accent2, 0.45)); bloom.addColorStop(0.4, rgba(accent2, 0.14)); bloom.addColorStop(1, rgba(accent2, 0));
    ctx.fillStyle = bloom; ctx.fillRect(0, 0, w, h);
    const moonBody = ctx.createRadialGradient(moonX - 6, moonY - 6, 2, moonX, moonY, 22);
    moonBody.addColorStop(0, "#ffffff"); moonBody.addColorStop(1, mixHex("#ffffff", accent2, 0.5));
    ctx.fillStyle = moonBody;
    ctx.beginPath(); ctx.arc(moonX, moonY, 20, 0, 7); ctx.fill();
    drawMountains(h * 0.78, h * 0.12, "#03060c", 0.85, 1.4);
  } else if (cat === "tower_hub") {
    for (let i = 0; i < 6; i++) {
      const x = (w / 6) * i + w / 12;
      const beamGrad = ctx.createLinearGradient(x, 0, x, h);
      beamGrad.addColorStop(0, rgba(accent, 0.0)); beamGrad.addColorStop(0.5, rgba(accent, 0.16)); beamGrad.addColorStop(1, rgba(accent, 0.0));
      ctx.fillStyle = beamGrad; ctx.fillRect(x - 1, 0, 2, h);
    }
    drawSkyline(h * 0.86, 12, h * 0.1, h * 0.3, "#000000", 0.65);
  }

  // gentle top vignette to blend into panel
  const top = ctx.createLinearGradient(0, 0, 0, h * 0.3);
  top.addColorStop(0, "rgba(0,0,0,.25)"); top.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = top; ctx.fillRect(0, 0, w, h * 0.3);
}

function mixHex(hexA, hexB, t) {
  const a = hexToRgb(hexA), b = hexToRgb(hexB);
  const r = Math.round(a[0] + (b[0] - a[0]) * t), g = Math.round(a[1] + (b[1] - a[1]) * t), bl = Math.round(a[2] + (b[2] - a[2]) * t);
  return `rgb(${r},${g},${bl})`;
}

function rand(a, b) { return a + Math.random() * (b - a); }


// ---------------------------------------------------------------------------
// Modals
// ---------------------------------------------------------------------------
function openModal(id) {
  $("#" + id).classList.add("open");
  if (id === "modal-journal") $$("[data-journal]").forEach((b) => b.classList.toggle("nav-open", b.getAttribute("data-journal") === APP.journalTab));
}
function closeModal(id) {
  $("#" + id).classList.remove("open");
  if (id === "modal-journal") $$("[data-journal]").forEach((b) => b.classList.remove("nav-open"));
}
$$(".modal-close").forEach((b) => b.addEventListener("click", () => closeModal(b.getAttribute("data-close"))));
$$(".modal-backdrop").forEach((m) => m.addEventListener("click", (e) => {
  const locked = new Set(["modal-auth", "modal-welcome", "modal-difficult-check", "modal-timing-challenge", "modal-tactical-challenge", "modal-major-roll", "modal-lethal", "modal-power-goal", "modal-event-window"]);
  if (e.target === m && !locked.has(m.id)) closeModal(m.id);
}));

$("#btn-action-deck").addEventListener("click", () => openActionDeck());
$("#action-deck-duration").addEventListener("change", () => { actionDeckDurationTouched = true; });
$("#action-deck-write").addEventListener("click", () => {
  closeModal("modal-action-deck");
  setMobileView("actions", false);
  $("#action-input").focus();
});
$("#action-deck-categories").addEventListener("click", (event) => {
  const button = event.target.closest("[data-action-category]");
  if (!button) return;
  actionDeckPerson = "";
  actionDeckCategory = button.getAttribute("data-action-category") || "recommended";
  renderActionDeck();
});
$("#action-deck-person").addEventListener("click", (event) => {
  if (!event.target.closest("[data-clear-action-person]")) return;
  actionDeckPerson = ""; actionDeckCategory = "people"; renderActionDeck();
});
$("#action-deck-list").addEventListener("click", (event) => {
  const choices = buildActionDeckChoices(APP.state || {}, actionDeckPerson);
  const favoriteButton = event.target.closest("[data-favorite-action]");
  if (favoriteButton) {
    const id = favoriteButton.getAttribute("data-favorite-action");
    const action = choices.find((row) => row.id === id);
    if (!action) return;
    const stored = readActionDeckStore("favorites");
    const exists = stored.some((row) => row.id === id);
    writeActionDeckStore("favorites", exists ? stored.filter((row) => row.id !== id) : [{ id: action.id, label: action.label, text: action.text, description: action.description, category: action.category, person: action.person?.name || actionDeckPerson || "", duration: action.duration }, ...stored]);
    renderActionDeck();
    return;
  }
  const button = event.target.closest("[data-action-choice]");
  if (!button) return;
  const action = choices.find((row) => row.id === button.getAttribute("data-action-choice"));
  if (!action) return;
  if (action.person?.name) { actionDeckPerson = action.person.name; renderActionDeck(); return; }
  placeActionInComposer(action);
});
$("#modal-action-deck").addEventListener("click", (event) => {
  const savedButton = event.target.closest("[data-action-deck-saved]");
  if (!savedButton) return;
  try {
    const saved = JSON.parse(decodeURIComponent(savedButton.getAttribute("data-action-deck-saved")));
    if (saved.person && !saved.id.startsWith("queue:") && !saved.id.startsWith("ongoing:")) {
      actionDeckPerson = saved.person; renderActionDeck(); return;
    }
    placeActionInComposer(saved);
  } catch (_) { showToast("That saved action could not be opened.", "danger"); }
});

// Major/canon events use a short informational notice only. The event's
// actual scene, position-aware prompt, suggested actions and any combat all
// remain in their normal Chronicle/Action Chat panels behind it.
function openEventNotice(result) {
  const isCanon = result.interruption_kind === "canon_event";
  const isDanger = result.interruption_kind === "danger";
  const notice = result.event_notice || {};
  const eventBackdrop = $("#modal-event-window");
  const eventModal = eventBackdrop.querySelector(".event-window-modal");
  const world = String(result.state?.world || APP.state?.world || "Custom World");
  const worldSlug = world.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  eventBackdrop.classList.toggle("canon-cinematic", isCanon);
  eventBackdrop.classList.toggle("danger-event", isDanger);
  eventModal.dataset.eventWorld = worldSlug;
  mobileVibrate(isDanger || result.state?.combat?.active ? [30, 45, 30] : [15, 35, 15]);
  const title = result.major_event_title || result.state?.active_canon_event ||
    (isCanon ? "MAJOR CANON EVENT" : isDanger ? "DANGER" : "MAJOR EVENT");
  playSceneTransition(result.state?.combat?.active ? "combat" : "event", result.state || APP.state);
  $("#event-window-title").textContent = isCanon ? "CANON EVENT" : isDanger ? "DANGER" : "MAJOR EVENT";
  $("#event-window-kicker").textContent = result.state?.combat?.active
    ? "COMBAT HAS BEGUN"
    : isCanon ? "THE TIMELINE HAS REACHED THIS MOMENT" : "THE SIMULATION HAS STOPPED HERE";
  $("#event-window-heading").textContent = title;
  const contextText = result.interruption_context || result.interruption_reason ||
    "An important event has reached your character's current place in the story.";
  $("#event-window-context").textContent = contextText;
  const cast = $("#event-window-cast");
  cast.innerHTML = mentionedPortraitsHtml(`${title} ${contextText}`, knownPersonRecords(result.state || APP.state || {}), 3, "md");
  cast.hidden = !cast.innerHTML;
  const meta = $("#event-window-meta");
  const eventDay = Number.isFinite(Number(notice.canon_day)) ? Number(notice.canon_day) : Number(result.state?.canon_day);
  const dateLabel = Number.isFinite(eventDay)
    ? formatCalendarDate(result.state?.world || APP.state?.world || "Custom World", eventDay, result.state?.calendar_epoch, result.state?.calendar_anchor_day)
    : "";
  const metaBits = [dateLabel, notice.location, notice.scope ? humanLabel(notice.scope) : ""].filter(Boolean);
  meta.textContent = metaBits.join("  /  ");
  meta.hidden = !metaBits.length;
  const facts = $("#event-window-facts");
  const showFacts = !isDanger && Boolean(notice.player_location || notice.travel_time || notice.involvement);
  facts.hidden = !showFacts;
  $("#event-window-player-location").textContent = notice.player_location || result.state?.location || "Unknown";
  $("#event-window-travel").textContent = notice.travel_time || "Depends on the available route";
  $("#event-window-involvement").textContent = notice.involvement || "The situation is still developing.";
  const banner = $("#event-window-banner");
  const bannerUrl = isCanon ? (notice.scene_image || result.state?._scene_image || "") : "";
  if (bannerUrl && bannerUrl.includes("/assets/")) {
    banner.src = bannerUrl;
    banner.alt = `${title} scene in ${world}`;
    banner.hidden = false;
  } else {
    banner.removeAttribute("src"); banner.alt = ""; banner.hidden = true;
  }
  const particles = $("#event-window-particles");
  particles.replaceChildren();
  if (isCanon) {
    for (let index = 0; index < 18; index += 1) {
      const particle = document.createElement("i");
      particle.style.setProperty("--particle-x", `${5 + ((index * 47) % 91)}%`);
      particle.style.setProperty("--particle-size", `${2 + (index % 4)}px`);
      particle.style.setProperty("--particle-duration", `${4.8 + (index % 5) * .7}s`);
      particle.style.setProperty("--particle-delay", `${1.2 + (index % 7) * .31}s`);
      particle.style.setProperty("--particle-drift", `${-36 + (index % 8) * 11}px`);
      particles.appendChild(particle);
    }
  }
  $("#btn-event-window-replay").hidden = !isCanon;
  restartCanonCinematic();
  openModal("modal-event-window");
}

function restartCanonCinematic() {
  const modal = $("#modal-event-window .event-window-modal");
  if (!modal || !$("#modal-event-window").classList.contains("canon-cinematic")) return;
  modal.classList.remove("event-cinematic-playing");
  void modal.offsetWidth;
  modal.classList.add("event-cinematic-playing");
}

function closeEventNotice() {
  closeModal("modal-event-window");
  $("#time-unit").value = "moment";
  syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help");
  const input = $("#action-input");
  input.placeholder = APP.state?.combat?.active
    ? "Combat is active — use the combat controls, or describe a specific combat action here."
    : "Respond to the event here, add your action, then Advance the next beat.";
  requestAnimationFrame(() => (APP.state?.combat?.active ? $("#btn-combat-attack") : input).focus());
}
$("#btn-event-window-leave").addEventListener("click", closeEventNotice);
$("#btn-event-window-continue").addEventListener("click", closeEventNotice);
$("#btn-event-window-replay").addEventListener("click", restartCanonCinematic);

// ---------------------------------------------------------------------------
// Turn submission
// ---------------------------------------------------------------------------
function setBusy(b) {
  APP.busy = b;
  document.body.classList.toggle("app-busy", Boolean(b));
  const pill = $("#hdr-ai");
  $("#btn-send").disabled = b;
  if (b) { pill.textContent = "AI: GENERATING..."; pill.classList.add("busy"); }
  else { pill.textContent = "AI: READY"; pill.classList.remove("busy"); }
}

async function submitAction(text) {
  if (APP.busy || !text) return;
  if (!APP.campaignActive) { showToast("Start a campaign first.", "system"); openModal("modal-campaign"); return; }
  if (window.WorldwalkerTeamMembership?.preflightJoin) {
    const membership = await WorldwalkerTeamMembership.preflightJoin(text, APP.state);
    if (membership?.handled && !membership.accepted) return;
  }
  playSfx("ui_click");
  try {
    let result = await apiPost("/api/actions/queue", { action: text });
    if (result.status === "interpretation_required") {
      const understood = result.interpretation?.summary || text;
      if (!window.confirm(`I interpreted your action as:\n\n${understood}\n\nQueue this action?`)) return;
      result = await apiPost("/api/actions/queue", { action: text, confirmed_interpretation: true });
    }
    $("#action-input").value = "";
    try { localStorage.removeItem(mobileCampaignKey("draft")); } catch (_) {}
    autoGrowMobileComposer();
    APP.state.queued_actions = result.queued_actions || [];
    renderQueuedActions(APP.state.queued_actions);
    if (result.interpretation?.summary && result.interpretation.summary.toLowerCase() !== String(text).trim().toLowerCase()) {
      showToast(`Queued as: ${result.interpretation.summary}`, "system");
    }
  } catch (e) {
    showToast(e.message, "danger"); playSfx("error");
  }
}

async function handleTurnResult(result, action) {
  if (result.status === "lethal_confirm_required") {
    APP.pendingLethal = { kind: "action", action };
    $("#lethal-warning").textContent = result.assessment.lethal_warning || "Failure could kill your character.";
    $("#lethal-risk").textContent = "Risk: " + (result.assessment.lethal_risk || "high").toUpperCase();
    APP.pendingLethal.assessment = result.assessment;
    openModal("modal-lethal");
    return;
  }
  if (result.status === "impossible") {
    appendStoryEntries([{ text: "[ACTION NOT POSSIBLE]\n" + result.reason, tag: "meta" }]);
    return;
  }
  const previousState = APP.state;
  appendStoryEntries(result.story, { focusNew: true });
  if (result.roll) {
    playSfx("dice");
    if (result.roll.breakthrough) flashScreen("success");
    if (!result.roll.success) { flashScreen("danger"); shakeApp(); }
  }
  renderState(result.state);
  playNewCanonEventCues(previousState, result.state);
  handleNotifications(result.notifications);
  if (result.died) {
    playDeathCue(); shakeApp();
    openModal("modal-death");
  }
  refreshUsagePill();
}

// ---------------------------------------------------------------------------
// Combat — every round here is resolved entirely locally by the backend (the
// same d100-vs-difficulty math as a normal check, reusing real stats/skills),
// so clicking Attack/Defend/Flee is instant and free. The only AI call in
// this whole flow is the single narrate_combat() request once the fight
// ends, which turns the mechanical log into prose and applies loot/injury
// consequences exactly like any other resolved turn.
// ---------------------------------------------------------------------------
function combatLogLine(e) {
  if (e.actor === "system" && e.action === "bonus_turn") return { text: `Your speed advantage earns another full action before the enemy responds${e.reason ? ` (${e.reason})` : ""}.`, cls: "player" };
  const swingNote = e.extra_swing ? " [quickened action — faster]" : "";
  if (e.actor === "player" && e.action === "controlled") return { text: `You cannot act while ${e.status || "controlled"}.`, cls: "miss" };
  if (e.actor === "player" && e.action === "defend") return { text: "You brace for the enemy's attack.", cls: "player" };
  if (e.actor === "player" && e.action === "flee") return { text: e.success ? "You break away from the fight." : "You try to flee — it fails.", cls: e.success ? "player" : "miss" };
  if (e.actor === "player" && e.action === "overwhelm") {
    const label = e.ability && e.ability !== "Overwhelm" ? e.ability : "an overwhelming personal ability";
    return e.success
      ? { text: `You end the fight outright with ${label}!`, cls: "hit" }
      : { text: `You try to end the fight with ${label} — it doesn't land this time.`, cls: "miss" };
  }
  if (e.actor === "player" && e.action === "heal") {
    const label = e.ability && e.ability !== "Attack" ? e.ability : "a plain effort";
    const costNote = e.resource_cost ? ` (-${e.resource_cost} ${APP.state?.resource_name || "Energy"})` : "";
    return e.success
      ? { text: `You use ${label} and recover ${e.healed ?? 0} HP${swingNote}${costNote}.`, cls: "player" }
      : { text: `You try to use ${label} — it fizzles${swingNote}${costNote}.`, cls: "miss" };
  }
  if (e.actor === "player" && e.action === "debuff") {
    const label = e.ability && e.ability !== "Attack" ? e.ability : "an effect";
    const costNote = e.resource_cost ? ` (-${e.resource_cost} ${APP.state?.resource_name || "Energy"})` : "";
    return e.applied
      ? { text: `You use ${label} on ${e.target || "the enemy"} — it takes hold${e.potency_pct ? `, reducing their combat effectiveness by about ${e.potency_pct}%` : ", weakening them"}${swingNote}${costNote}.`, cls: "player" }
      : { text: `You try ${label} on ${e.target || "the enemy"} — it doesn't take hold${swingNote}${costNote}.`, cls: "miss" };
  }
  if (e.actor === "player" && ["buff", "shield", "cleanse", "control", "summon", "movement", "detect", "stealth", "transform", "utility"].includes(e.action)) {
    const label = e.ability && e.ability !== "Attack" ? e.ability : "the technique";
    const costNote = e.resource_cost ? ` (-${e.resource_cost} ${APP.state?.resource_name || "Energy"})` : "";
    if (!e.applied) return { text: `You try ${label}, but it fails to take hold${costNote}.`, cls: "miss" };
    if (e.action === "shield") return { text: `${label} forms a ${e.shield || 0}-point barrier${costNote}.`, cls: "player" };
    if (e.action === "cleanse") return { text: `${label} clears ${e.removed?.length ? e.removed.join(", ") : "harmful effects"}${costNote}.`, cls: "player" };
    if (e.action === "summon") return { text: `${label} calls ${e.summon || "an ally"} into the fight${costNote}.`, cls: "player" };
    if (e.action === "control") return { text: `${label} inflicts ${e.status || "Control"} on ${e.target || "the enemy"}${costNote}.`, cls: "player" };
    return { text: `${label} grants ${e.status || humanLabel(e.action)} for ${e.duration || 1} round${e.duration === 1 ? "" : "s"}${costNote}.`, cls: "player" };
  }
  if (e.actor === "player") {
    const label = e.ability && e.ability !== "Attack" ? e.ability : "a plain attack";
    const costNote = e.resource_cost ? ` (-${e.resource_cost} ${APP.state?.resource_name || "Energy"})` : "";
    if (e.shrugged) return { text: `${e.target || "The enemy"} completely shrugs off your ${label}${swingNote}${costNote}.`, cls: "miss" };
    return e.success
      ? { text: `You hit ${e.target || "the enemy"} with ${label} for ${e.damage ?? 0} dmg${e.massive ? " — MASSIVE" : ""}${e.breakthrough ? " — BREAKTHROUGH" : ""}${swingNote}${costNote}.`, cls: "hit" }
      : { text: `You try ${label} on ${e.target || "the enemy"} — it misses${swingNote}${costNote}.`, cls: "miss" };
  }
  if (e.actor === "enemy") {
    if (e.action === "controlled") return { text: `${e.name || "The enemy"} cannot act while ${e.status || "controlled"}.`, cls: "player" };
    if (e.shrugged) return { text: `You completely shrug off ${e.name || "the enemy"}'s attack${swingNote}.`, cls: "player" };
    const shieldNote = e.absorbed ? ` (${e.absorbed} absorbed by your barrier)` : "";
    const debuffNote = e.debuff_penalty ? ` [weakened: -${e.debuff_penalty} to the attack]` : "";
    const statusNote = e.inflicted_status ? ` You are now ${e.inflicted_status}.` : "";
    return e.success
      ? { text: `${e.name || "The enemy"} hits you for ${e.damage ?? 0} dmg${shieldNote}${debuffNote}${e.massive ? " — MASSIVE" : ""}${swingNote}.${statusNote}`, cls: "hit" }
      : { text: `${e.name || "The enemy"}'s attack misses${debuffNote}${swingNote}.`, cls: "miss" };
  }
  if (e.actor === "status") return { text: `${e.status || "A lingering effect"} deals ${e.damage || 0} damage to ${e.target === "player" ? "you" : "the enemy"}.`, cls: "hit" };
  return { text: "Something happens.", cls: "" };
}

const COMBAT_EFFECT_ICON = { damage: "⚔ ", heal: "🩹 ", buff: "⬆ ", debuff: "⛓ ", shield: "🛡 ", cleanse: "✦ ", control: "⊘ ", summon: "♟ ", movement: "➜ ", detect: "◉ ", stealth: "◌ ", transform: "◆ ", utility: "◇ " };
function combatAbilityEffectType(s, name) {
  const detail = (s.combat?.ability_options || {})[name] || (s.skills || {})[name];
  const t = String((detail && typeof detail === "object" ? detail.effect_type : "") || "").toLowerCase();
  const valid = ["damage", "heal", "buff", "debuff", "shield", "cleanse", "control", "summon", "movement", "detect", "stealth", "transform", "utility"];
  if (valid.includes(t)) return t;
  const blob = `${name} ${detail?.description || ""} ${detail?.effect || ""}`.toLowerCase();
  if (/heal|restore hp|regenerat/.test(blob)) return "heal";
  if (/shield|barrier|ward/.test(blob)) return "shield";
  if (/stun|bind|paraly|sleep|freeze|bakud/.test(blob)) return "control";
  if (/summon|familiar|construct/.test(blob)) return "summon";
  if (/transform|shikai|bankai|awakening/.test(blob)) return "transform";
  if (/stealth|invisib|conceal/.test(blob)) return "stealth";
  if (/detect|sense|scan/.test(blob)) return "detect";
  if (/dash|teleport|movement|blink/.test(blob)) return "movement";
  if (/buff|empower|enhance/.test(blob)) return "buff";
  if (/debuff|weaken|slow|poison|burn|bleed/.test(blob)) return "debuff";
  return "damage";
}
function combatAbilityUsable(s, name) {
  const detail = (s.combat?.ability_options || {})[name] || (s.skills || {})[name];
  if (!detail || typeof detail !== "object") return false;
  if (detail.combat_usable === false) return false;
  if (detail.combat_usable === true) return true;
  if (["damage", "heal", "buff", "debuff", "shield", "cleanse", "control", "summon", "movement", "detect", "stealth", "transform"].includes(String(detail.effect_type || "").toLowerCase())) return true;
  // Backward-compatible inference for older saves whose skills predate the
  // combat_usable field.  Profession/knowledge fundamentals no longer turn
  // into attacks merely because they have a numeric bonus.
  const blob = `${name} ${detail.description || ""} ${detail.effect || ""}`.toLowerCase();
  if (/navigator|navigation|craft|smith|cooking|merchant|account|research|history|language|fundamentals expected of this role/.test(blob)) return false;
  return /attack|strike|damage|weapon|combat|fight|jutsu|spell|blast|projectile|heal|restore hp|shield|guard|weaken|debuff|stun|bind|poison|haki|nen|chakra/.test(blob);
}
function populateCombatAbilitySelect(s) {
  const combat = s.combat || {};
  const cooldowns = combat.cooldowns || {};
  const abilitySel = $("#combat-ability");
  const options = s.combat?.ability_options && typeof s.combat.ability_options === "object"
    ? s.combat.ability_options : s.skills || {};
  const skills = Object.keys(options).filter((name) => combatAbilityUsable(s, name));
  const priorAbility = abilitySel.value;
  abilitySel.innerHTML = `<option value="">Plain Attack</option>` + skills.map((name) => {
    const readyAt = cooldowns[name] || 0;
    const remaining = readyAt - (combat.round || 1);
    const locked = remaining > 0;
    const icon = COMBAT_EFFECT_ICON[combatAbilityEffectType(s, name)];
    const detail = options[name] || {};
    const displayName = detail.name || name;
    const parentNote = detail.parent_skill && detail.parent_skill !== displayName ? ` — ${detail.parent_skill}` : "";
    const label = locked ? `${icon}${displayName}${parentNote} (recovering, ${remaining} rd)` : `${icon}${displayName}${parentNote}`;
    return `<option value="${escapeHtml(name)}"${locked ? " disabled" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
  if (skills.includes(priorAbility) && !$(`#combat-ability option[value="${CSS.escape(priorAbility)}"]`)?.disabled) abilitySel.value = priorAbility;
  updateCombatAttackButtonLabel(s);
}

const COMBAT_ACTION_ICON = {
  damage: ICONS.sword,
  heal: `<svg ${SVG_ICON_ATTRS}><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>`,
  debuff: `<svg ${SVG_ICON_ATTRS}><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>`,
};
for (const kind of ["buff", "shield", "cleanse", "control", "summon", "movement", "detect", "stealth", "transform", "utility"]) COMBAT_ACTION_ICON[kind] = ICONS.sparkles || ICONS.sword;
const COMBAT_ACTION_LABEL = { damage: "ATTACK", heal: "HEAL", buff: "EMPOWER", debuff: "WEAKEN", shield: "BARRIER", cleanse: "CLEANSE", control: "CONTROL", summon: "SUMMON", movement: "MOVE", detect: "ANALYZE", stealth: "CONCEAL", transform: "TRANSFORM", utility: "USE" };
function updateCombatAttackButtonLabel(s) {
  const selected = $("#combat-ability").value;
  const effectType = selected ? combatAbilityEffectType(s, selected) : "damage";
  $("#btn-combat-attack").innerHTML = `<i class="btn-icon-svg">${COMBAT_ACTION_ICON[effectType]}</i>${COMBAT_ACTION_LABEL[effectType]}`;
}
$("#combat-ability").addEventListener("change", () => { if (APP.state) updateCombatAttackButtonLabel(APP.state); });

// Small, purely cosmetic combat feedback — a floating number and a quick
// bar-flash — so a hit registers as an event, not just a number changing in
// place. No shake here by design; screen-shake is reserved for the moments
// that already used it (deaths, lethal danger) and isn't being added to.
function spawnFloatingCombatNumber(targetSelector, amount, kind) {
  const target = $(targetSelector);
  if (!target || !amount) return;
  const rect = target.getBoundingClientRect();
  const el = document.createElement("span");
  el.className = "floating-combat-number " + kind;
  el.textContent = (kind === "heal" ? "+" : "-") + Math.round(Math.abs(amount));
  el.style.left = (rect.left + rect.width / 2) + "px";
  el.style.top = rect.top + "px";
  document.body.appendChild(el);
  el.addEventListener("animationend", () => el.remove());
  setTimeout(() => el.remove(), 1200);
}

function flashCombatBar(targetSelector) {
  const target = $(targetSelector);
  if (!target) return;
  target.classList.remove("bar-flash");
  void target.offsetWidth;
  target.classList.add("bar-flash");
}

function combatConditionChip(row) {
  const parts = [];
  const pct = (label, value) => {
    const n = Math.round(Number(value || 0) * 100);
    if (n) parts.push(`${label} ${n > 0 ? "+" : ""}${n}%`);
  };
  pct("power", row.power_pct);
  pct("defense", row.defense_pct);
  pct("speed", row.speed_pct);
  pct("accuracy", row.accuracy_pct);
  if (row.blocks_action || /\b(stun(?:ned)?|paraly(?:zed|sis)|asleep|sleeping|frozen|freeze|immobili[sz]ed|incapacitated|unconscious|petrified|restrained|bound|controlled)\b/i.test(row.name || "")) parts.push("cannot act");
  const turns = Number(row.rounds_left || 0);
  const title = parts.length ? parts.join(" · ") : (turns ? `${turns} round${turns === 1 ? "" : "s"} remaining` : "Active effect");
  return `<span title="${escapeHtml(title)}">${escapeHtml(row.name || "Active effect")}${turns ? ` · ${escapeHtml(turns)}` : ""}${parts.length ? `<small>${escapeHtml(parts.join(" · "))}</small>` : ""}</span>`;
}

function renderCombatPanel(s) {
  const panel = $("#combat-panel");
  const combat = s.combat || {};
  const actionInput = $("#action-input");
  const tacticalWorld = ['Naruto','One Piece','Bleach'].includes(s.world) || !!combat.adventure_objective;
  const tactical = tacticalWorld && combat.active;
  actionInput.disabled = !!tactical;
  if (tactical) {
    panel.hidden = true;
    $("#mobile-combat-dock").hidden = true;
    const destination = s._tactical_battle_url || '/tactical-preview/designs/campaign.html';
    if (!location.pathname.startsWith('/tactical-preview/')) window.location.replace(destination);
    return;
  }
  if (!combat.active) {
    panel.hidden = true;
    actionInput.placeholder = "TYPE AN ACTION HERE\nPress Enter or Add to keep it in this chat until you Advance.";
    return;
  }
  panel.hidden = false;
  actionInput.placeholder = "Combat is active — use the combat controls, or describe a specific combat action here.";
  $("#combat-round").textContent = combat.round ?? 1;
  const bonusTurn = $("#combat-bonus-turn");
  bonusTurn.hidden = !combat.bonus_turn_pending;
  if (combat.bonus_turn_pending) bonusTurn.querySelector("span").textContent = `${combat.bonus_turn_reason || "Your speed advantage"} — choose any combat action before the enemy responds.`;
  const combatBrief = $("#combat-brief");
  const briefRows = [
    combat.cause ? `<span><b>WHY IT STARTED</b>${escapeHtml(combat.cause)}</span>` : "",
    combat.victory_condition ? `<span><b>OBJECTIVE</b>${escapeHtml(combat.victory_condition)}</span>` : "",
    combat.defeat_risk ? `<span><b>AT RISK</b>${escapeHtml(combat.defeat_risk)}</span>` : "",
  ].filter(Boolean);
  combatBrief.hidden = !briefRows.length;
  combatBrief.innerHTML = briefRows.join("");
  $("#combat-mode-badge").hidden = !combat.non_lethal;
  // The mercy toggle only means anything for a real, lethal-by-default fight
  // — a spar/test (non_lethal) already floors both sides, so the choice is
  // moot there and the row is hidden rather than shown disabled.
  const mercyRow = $("#combat-mercy-row");
  mercyRow.hidden = !!combat.non_lethal;
  $("#combat-mercy-toggle").checked = !!combat.spare_enemy;
  const e = combat.enemy || {};
  const dead = e.alive === false || Number(e.hp) <= 0;
  const pct = 100 * (Number(e.hp) || 0) / Math.max(1, Number(e.hp_max) || 1);
  const enemyBox = $("#combat-enemy");
  const wasDead = enemyBox.dataset.dead === "true";
  enemyBox.classList.toggle("dead", dead);
  enemyBox.dataset.dead = String(dead);
  if (dead && !wasDead) {
    enemyBox.classList.remove("defeat-transition");
    void enemyBox.offsetWidth;
    enemyBox.classList.add("defeat-transition");
  }
  const groupNote = e.is_group ? `<div class="combat-enemy-sub">Fighting as a group${e.group_size ? ` — roughly ${escapeHtml(e.group_size)} strong` : ""}</div>` : "";
  const defeatedLabel = combat.enemy_died ? "KILLED" : (combat.non_lethal || combat.spare_enemy || combat.death_prevented) ? "SUBDUED" : "DEFEATED";
  enemyBox.innerHTML = `<div class="combat-enemy-head"><b>${escapeHtml(e.name || "Enemy")}</b><span>${dead ? defeatedLabel : `${escapeHtml(e.hp)} / ${escapeHtml(e.hp_max)}`}</span></div>${groupNote}<div class="bar-track"><div class="bar-fill" style="width:${Math.max(0, Math.min(100, pct))}%"></div></div>`;
  const resourceRow = $("#combat-resource-row");
  if (s.resource_max) resourceRow.innerHTML = `<span>${escapeHtml(s.resource_name || "Energy")}</span><b>${escapeHtml(s.resource ?? 0)} / ${escapeHtml(s.resource_max)}</b>`;
  else resourceRow.innerHTML = "";
  const conditionRows = [
    Number(combat.player_shield || 0) > 0 ? { name: `Barrier ${combat.player_shield}`, rounds_left: null } : null,
    ...(combat.player_buffs || []), ...(combat.player_debuffs || []), ...(combat.player_statuses || []), ...(combat.summons || []),
  ].filter(Boolean);
  $("#combat-status-row").innerHTML = conditionRows.map(combatConditionChip).join("");
  const enemyConditions = [...(combat.enemy_debuffs || []), ...(combat.enemy_statuses || [])];
  if (enemyConditions.length) enemyBox.insertAdjacentHTML("beforeend", `<div class="combat-condition-strip">${enemyConditions.map(combatConditionChip).join("")}</div>`);
  populateCombatAbilitySelect(s);
}

function playConquerorsHakiCinematic(entries) {
  const victory = (entries || []).find((entry) => entry?.cinematic === "conquerors_haki" && entry?.success && entry?.visual_outcome === "victory");
  if (!victory) return Promise.resolve(false);
  document.querySelectorAll(".haoshoku-cinematic").forEach((node) => node.remove());
  const scene = document.createElement("div");
  scene.className = "haoshoku-cinematic";
  scene.setAttribute("role", "img");
  scene.setAttribute("aria-label", `${victory.ability || "Conqueror's Haki"} overwhelms the enemy`);
  scene.innerHTML = "<i class=\"haoshoku-bolt\"></i><i class=\"haoshoku-bolt\"></i><i class=\"haoshoku-bolt\"></i><i class=\"haoshoku-bolt\"></i>";
  document.body.appendChild(scene);
  playSfx("hit");
  if (navigator.vibrate) navigator.vibrate([35, 35, 70]);
  const duration = matchMedia("(prefers-reduced-motion: reduce)").matches ? 650 : 1550;
  return new Promise((resolve) => setTimeout(() => { scene.remove(); resolve(true); }, duration));
}

function appendCombatLogEntries(entries) {
  const log = $("#combat-log");
  (entries || []).forEach((e) => {
    const { text, cls } = combatLogLine(e);
    const row = document.createElement("div");
    row.className = "combat-log-row " + cls;
    row.textContent = text;
    log.appendChild(row);
  });
  log.scrollTop = log.scrollHeight;
  // Mirror the same lines into the Chronicle, styled like a dice check, so
  // combat rounds remain visible in the same log as every other story beat.
  const chronicleLines = (entries || []).map((e) => combatLogLine(e).text).join("\n");
  if (chronicleLines) {
    const entry = { text: "[COMBAT]\n" + chronicleLines, tag: "roll" };
    appendStoryEntries([entry]);
  }
}

let combatRoundBusy = false;
function setCombatButtonsDisabled(disabled) {
  $("#btn-combat-attack").disabled = $("#btn-combat-defend").disabled = $("#btn-combat-flee").disabled = $("#btn-combat-overwhelm").disabled = disabled;
}
async function submitCombatAction(action) {
  // Deliberately does NOT go through setBusy()/the "AI: GENERATING..." pill —
  // this round is resolved entirely locally and returns near-instantly, so
  // showing an AI-busy state here would misrepresent what's actually free.
  if (combatRoundBusy || APP.busy || !APP.state?.combat?.active) return;
  if (['Naruto','One Piece','Bleach'].includes(APP.state?.world)) {
    window.location.replace(APP.state?._tactical_battle_url || '/tactical-preview/designs/campaign.html');
    return;
  }
  if (APP.multiplayer) {
    try {
      const ability = (action === "attack" || action === "overwhelm") ? $("#combat-ability").value : "";
      const phrase = ability ? `${action} using ${ability}` : action;
      const queued = await apiPost("/api/actions/queue", { action: `In the current combat, ${phrase}.` });
      APP.state.queued_actions = queued.queued_actions || [];
      renderQueuedActions(APP.state.queued_actions);
      renderMultiplayer(await apiPost("/api/multiplayer/ready", { ready: true }));
      showToast("Combat choice locked in for this shared round.", "notify");
    } catch (error) { showToast(error.message, "danger"); }
    return;
  }
  combatRoundBusy = true;
  setCombatButtonsDisabled(true);
  try {
    const payload = { action };
    if ((action === "attack" || action === "overwhelm") && $("#combat-ability").value) payload.ability = $("#combat-ability").value;
    const priorEnemyHp = Number(APP.state?.combat?.enemy?.hp ?? NaN);
    const priorPlayerHp = Number(APP.state?.hp ?? NaN);
    const result = await apiPost("/api/combat/action", payload);
    appendCombatLogEntries(result.log_tail);
    await playConquerorsHakiCinematic(result.log_tail);
    playSfx("dice");
    if (result.hp !== undefined) { APP.state.hp = result.hp; APP.state.hp_max = result.hp_max; }
    if (result.resource !== undefined) { APP.state.resource = result.resource; APP.state.resource_max = result.resource_max; }
    APP.state.combat = result.combat;
    renderState(APP.state);
    if (result.awaiting_bonus_action) showToast("Speed advantage: choose your bonus action before the enemy responds.", "notify");
    const newEnemyHp = Number(result.combat?.enemy?.hp ?? NaN);
    if (Number.isFinite(priorEnemyHp) && Number.isFinite(newEnemyHp) && newEnemyHp < priorEnemyHp) {
      spawnFloatingCombatNumber("#combat-enemy .bar-track", priorEnemyHp - newEnemyHp, "damage");
      flashCombatBar("#combat-enemy .bar-fill");
      playSfx("hit");
    }
    if (Number.isFinite(priorPlayerHp) && result.hp !== undefined && Number(result.hp) < priorPlayerHp) {
      spawnFloatingCombatNumber("#bar-hp", priorPlayerHp - Number(result.hp), "damage");
    } else if (Number.isFinite(priorPlayerHp) && result.hp !== undefined && Number(result.hp) > priorPlayerHp) {
      spawnFloatingCombatNumber("#bar-hp", Number(result.hp) - priorPlayerHp, "heal");
    }
    if (!result.combat?.active) {
      shakeApp();
      setBusy(true);
      try {
        const narrated = await apiPost("/api/combat/narrate", {});
        await handleTurnResult(narrated);
      } finally { setBusy(false); }
    } else if (result.player_died) {
      playDeathCue(); shakeApp();
    }
  } catch (e) { showToast(e.message, "danger"); }
  finally { combatRoundBusy = false; setCombatButtonsDisabled(false); }
}
$("#btn-combat-attack").addEventListener("click", () => submitCombatAction("attack"));
$("#btn-combat-defend").addEventListener("click", () => submitCombatAction("defend"));
$("#btn-combat-flee").addEventListener("click", () => submitCombatAction("flee"));
$("#btn-combat-overwhelm").addEventListener("click", () => submitCombatAction("overwhelm"));
$("#combat-mercy-toggle").addEventListener("change", async (e) => {
  const spare = e.target.checked;
  try {
    const result = await apiPost("/api/combat/mercy", { spare });
    if (APP.state) APP.state.combat = result.combat;
    showToast(spare ? "You'll spare this enemy if you win — losing is still real." : "Mercy toggle off — winning this fight plays out at full stakes.", "system");
  } catch (err) { e.target.checked = !spare; showToast(err.message, "danger"); }
});

$("#btn-lethal-confirm").addEventListener("click", async () => {
  closeModal("modal-lethal");
  const pending = APP.pendingLethal;
  if (!pending) return;
  setBusy(true);
  try {
    if (pending.kind === "action") {
      appendStoryEntries([{ text: "> " + pending.action, tag: "player" }]);
      const result = await apiPost("/api/action/submit", { action: pending.action, confirmed_lethal: true, assessment: pending.assessment });
      await handleTurnResult(result, pending.action);
    } else if (pending.kind === "timeskip") {
      const payload = { ...pending.timeskip, confirmed_lethal: true };
      const result = await apiPost("/api/time/resolve", payload);
      await processTimeSkipResolution(result, payload);
    }
  } catch (e) { showToast(e.message, "danger"); playSfx("error"); }
  finally { setBusy(false); APP.pendingLethal = null; runBackgroundCheck(); }
});
$("#btn-lethal-cancel").addEventListener("click", () => {
  closeModal("modal-lethal");
  appendStoryEntries([{ text: "[ACTION REVERTED]\nYou stop before committing to the lethal decision.", tag: "meta" }]);
  APP.pendingLethal = null;
});

$("#btn-power-goal-confirm").addEventListener("click", async () => {
  closeModal("modal-power-goal");
  const pending = APP.pendingPowerGoal;
  if (!pending) return;
  setBusy(true);
  try {
    const payload = { ...pending, confirmed_power_goal: true };
    const result = await apiPost("/api/time/resolve", payload);
    await processTimeSkipResolution(result, payload);
  } catch (e) { showToast(e.message, "danger"); playSfx("error"); }
  finally { setBusy(false); APP.pendingPowerGoal = null; runBackgroundCheck(); }
});
$("#btn-power-goal-cancel").addEventListener("click", () => {
  closeModal("modal-power-goal");
  APP.pendingPowerGoal = null;
});

$("#btn-death-rewind").addEventListener("click", async () => {
  closeModal("modal-death");
  try {
    const result = await apiPost("/api/action/rewind_death", {});
    appendStoryEntries(result.story);
    renderState(result.state);
  } catch (e) { showToast(e.message, "danger"); }
});
$("#btn-death-keep").addEventListener("click", () => closeModal("modal-death"));

$("#btn-send").addEventListener("click", () => submitAction($("#action-input").value.trim()));
$("#action-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitAction($("#action-input").value.trim()); }
});

function removeOpeningSetupNotice() {
  $("#story-feed .story-entry").forEach((row) => {
    if (row.textContent.includes("AI SETUP REQUIRED")) row.remove();
  });
  $("#story-feed .story-beat").forEach((beat) => {
    if (!beat.querySelector(".story-entry, .story-beat-system")) beat.remove();
  });
}

$("#btn-retry-opening").addEventListener("click", async () => {
  if (!APP.campaignActive) { openModal("modal-campaign"); return; }
  setBusy(true);
  try {
    const result = await apiPost("/api/campaign/opening", {});
    removeOpeningSetupNotice();
    appendStoryEntries(result.story);
    renderState(result.state);
  } catch (e) {
    showToast(e.message, "danger");
    removeOpeningSetupNotice();
    appendStoryEntries([{ text: "[AI SETUP REQUIRED]\n" + e.message, tag: "danger" }]);
  }
  finally { setBusy(false); }
});

// ---------------------------------------------------------------------------
// Background world simulation polling
// ---------------------------------------------------------------------------
let bgPollTimer = null;
async function runBackgroundCheck() {
  try {
    const r = await apiPost("/api/background/run", {});
    if (r.started) setTimeout(pollBackground, 1500);
  } catch (e) {}
}
async function pollBackground() {
  try {
    const r = await apiGet("/api/background/poll");
    (r.events || []).forEach((ev) => {
      if (ev.type === "chat") {
        showToast(`${ev.sender}: ${ev.message}`, "message"); playSfx("message");
        appendStoryEntries([{ text: `[MESSAGE REACTION — ${ev.sender}]\n${ev.message}`, tag: "system" }]);
        if (ev.state) renderState(ev.state);
      } else if (ev.type === "world_event") {
        showToast(ev.message, "world"); playSfx("world_event");
        appendStoryEntries([{ text: `[WORLD REACTION]\n${ev.message}`, tag: "system" }]);
        if (ev.state) renderState(ev.state);
      }
    });
  } catch (e) {}
}
// World simulation is intentionally advanced only after the player confirms
// an Advance plan. This prevents unsolicited GM/world responses while the
// player is still queuing actions.

// ---------------------------------------------------------------------------
// Time control
// ---------------------------------------------------------------------------
function syncTimeControl(unitSelector, amountSelector, amountFieldSelector, momentLabelSelector, helpSelector) {
  const unit = $(unitSelector).value;
  const isMoment = unit === "moment";
  const isEvent = unit === "next_event";
  const isEventDriven = isMoment || isEvent;
  const amount = $(amountSelector);
  amount.hidden = isEventDriven;
  amount.disabled = isEventDriven;
  if (isEventDriven) amount.value = "1";
  if (amountFieldSelector) $(amountFieldSelector).hidden = isEventDriven;
  if (momentLabelSelector) {
    $(momentLabelSelector).hidden = !isEventDriven;
    $(momentLabelSelector).textContent = isEvent ? "MAJOR EVENT" : "NEXT BEAT";
  }
  if (helpSelector) {
    $(helpSelector).textContent = isEvent
      ? "Continues through routine updates and stops naturally at the next major personal or canon event."
      : isMoment ? "Moment resolves exactly one contextual story beat, never more than 24 hours."
      : "Long skips simulate the full period and may stop early for goals or major events.";
  }
  if (unitSelector === "#time-unit" && APP.state) renderQueuedActions(APP.state.queued_actions || []);
  if (unitSelector === "#time-unit") updateSelectedTimeLabel();
}

function updateSelectedTimeLabel() {
  const label = $("#time-mode-label");
  const unitEl = $("#time-unit");
  const amountEl = $("#time-amount");
  if (!label || !unitEl) return;
  const unit = unitEl.value || "moment";
  if (unit === "moment") label.textContent = "Selected skip: next story beat";
  else if (unit === "next_event") label.textContent = "Selected skip: next major event";
  else {
    const amount = Number(amountEl?.value || 1);
    const shownUnit = amount === 1 ? unit.replace(/s$/, "") : unit;
    label.textContent = `Selected skip: ${amount} ${shownUnit}`;
  }
  syncMobileTimeInputs();
  if (APP.state && isMobileLayout()) renderMobileState(APP.state);
}

$("#time-unit").addEventListener("change", () => syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help"));
$("#time-amount").addEventListener("input", () => { renderQueuedActions(APP.state?.queued_actions || []); updateSelectedTimeLabel(); });
$("#mobile-time-unit").addEventListener("change", applyMobileTimeInputs);
$("#mobile-time-amount").addEventListener("input", applyMobileTimeInputs);
$("#td-unit").addEventListener("change", () => syncTimeControl("#td-unit", "#td-amount", "#td-amount-field"));
syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help");
syncTimeControl("#td-unit", "#td-amount", "#td-amount-field");

$("#btn-advance").addEventListener("click", async () => {
  if (APP.busy || !APP.campaignActive) return;
  playNarutoAdvanceCue();
  const draft = $("#action-input").value.trim();
  if (draft) await submitAction(draft);
  const unit = $("#time-unit").value;
  const amount = ["moment", "next_event"].includes(unit) ? 1 : parseInt($("#time-amount").value || "1", 10);
  await beginTimeSkip(amount, unit, $("#time-plan").value, "normal");
});
$("#btn-detailed-time").addEventListener("click", () => {
  $("#td-amount").value = $("#time-amount").value;
  $("#td-unit").value = $("#time-unit").value;
  syncTimeControl("#td-unit", "#td-amount", "#td-amount-field");
  $("#td-orders").value = $("#time-plan").value;
  const queued = APP.state?.queued_actions || [];
  $("#td-queued-summary").innerHTML = queued.length
    ? `<b>${queued.length} queued action${queued.length === 1 ? "" : "s"} will be kept</b>${queued.map((action, index) => `<span>${index + 1}. ${escapeHtml(action)}</span>`).join("")}`
    : `<b>No queued actions yet</b><span>Your current Action Chat draft will be added before the time skip begins.</span>`;
  openModal("modal-time-detail");
});
$("#btn-begin-timeskip").addEventListener("click", async () => {
  const unit = $("#td-unit").value;
  const amount = ["moment", "next_event"].includes(unit) ? 1 : parseInt($("#td-amount").value || "1", 10);
  const orders = $("#td-orders").value;
  const intensity = $("#td-intensity").value;
  $("#time-unit").value = unit;
  $("#time-amount").value = String(amount);
  $("#time-plan").value = orders;
  syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help");
  playNarutoAdvanceCue();
  closeModal("modal-time-detail");
  const draft = $("#action-input").value.trim();
  if (draft) await submitAction(draft);
  await beginTimeSkip(amount, unit, orders, intensity);
});

async function beginTimeSkip(amount, unit, orders, intensity) {
  if (!APP.campaignActive) { showToast("Start a campaign first.", "system"); return; }
  if (APP.multiplayer) {
    try {
      if (orders?.trim()) {
        for (const action of orders.split(/\r?\n/).map((x) => x.trim()).filter(Boolean)) await apiPost("/api/actions/queue", { action });
      }
      if (APP.multiplayer.is_host) {
        await apiPost("/api/multiplayer/time", { amount, unit, intensity });
      }
      renderMultiplayer(await apiPost("/api/multiplayer/ready", { ready: true }));
      $("#action-input").value = "";
      $("#time-plan").value = "";
      showToast("Ready. The round resolves when both players are ready or the ten-minute timer expires.", "notify");
    } catch (error) { showToast(error.message, "danger"); }
    return;
  }
  setBusy(true);
  try {
    const assessData = await apiPost("/api/time/assess", { amount, unit, orders, intensity });
    const payload = { amount: assessData.amount, unit: assessData.unit, orders: assessData.orders, intensity: assessData.intensity, assessment: assessData.assessment };
    APP.pendingAdvance = payload;
    const difficult = payload.assessment?.difficult_checks || [];
    if (difficult.length) {
      APP.pendingDifficulty = { payload, checks: difficult };
      renderDifficultyGate(difficult);
      openModal("modal-difficult-check");
      return;
    }
    // Not risky enough to stop and ask, but still worth a quick heads-up
    // before committing — the same odds math just renders as a toast
    // instead of a blocking gate.
    const previews = payload.assessment?.check_previews || [];
    previews.slice(0, 2).forEach((p) => {
      const breakdown = formatBreakdownText(p.bonus_breakdown);
      showToast(`${p.action || p.reason}: about ${p.odds_percent ?? "?"}% odds${breakdown ? ` (${breakdown})` : ""}`, "system");
    });
    await resolveAssessedTimeSkip(payload);
  } catch (e) { renderQueuedActions(APP.state?.queued_actions || []); showToast(e.message, "danger"); playSfx("error"); }
  finally { setBusy(false); }
}

async function resolveAssessedTimeSkip(payload) {
  setBusy(true);
  const draft = $("#action-input").value, plan = $("#time-plan").value;
  try {
    $("#action-input").value = "";
    $("#time-plan").value = "";
    renderQueuedActions([]);
    playTimeAdvanceEffect(payload.amount, payload.unit);
    playSfx("time_skip");
    const result = await apiPost("/api/time/resolve", payload);
    await processTimeSkipResolution(result, payload);
  } catch (error) {
    if (!$("#action-input").value) $("#action-input").value = draft;
    if (!$("#time-plan").value) $("#time-plan").value = plan;
    saveMobileDraft();
    renderQueuedActions(APP.state?.queued_actions || []);
    showToast(error.message, "danger"); playSfx("error");
  } finally { setBusy(false); }
}

function formatBreakdownText(parts) {
  if (!Array.isArray(parts) || !parts.length) return "";
  return parts.map((p) => `${p.label} ${Number(p.value) >= 0 ? "+" : ""}${p.value}`).join(" · ");
}

function renderDifficultyGate(checks) {
  $("#difficult-check-list").innerHTML = checks.map((check) => {
    const range = check.difficulty_range || ["?", "?"];
    const bonus = Number(check.known_bonus || 0);
    const breakdown = formatBreakdownText(check.bonus_breakdown);
    const lethal = ["high", "extreme"].includes(String(check.risk || "").toLowerCase());
    const riskText = lethal ? `${String(check.risk).toUpperCase()} — FAILURE MAY BE FATAL` : `${check.risk || "none"} risk`;
    return `<article class="difficult-check-row"><header><b>${escapeHtml(check.action || check.reason)}</b><span>${escapeHtml(riskText)}</span></header><div><strong>Needed total ${escapeHtml(range[0])}–${escapeHtml(range[1])}</strong><span>Expected raw roll: about ${escapeHtml(check.expected_raw_needed)}/100 (~${escapeHtml(check.odds_percent ?? "?")}% odds)</span><span>${escapeHtml(check.ability)}${check.skill ? ` · ${escapeHtml(check.skill)}` : ""} · total bonus ${bonus >= 0 ? "+" : ""}${escapeHtml(bonus)}</span>${breakdown ? `<span class="difficult-check-breakdown">${escapeHtml(breakdown)}</span>` : ""}</div></article>`;
  }).join("");
}

function acceptedDifficultyPayload(pending) {
  const lethal = (pending?.checks || []).some((check) => ["high", "extreme"].includes(String(check.risk || "").toLowerCase()));
  return {
    ...pending.payload,
    danger_warning_acknowledged: true,
    confirmed_lethal: Boolean(pending.payload.confirmed_lethal || lethal),
  };
}

$("#btn-difficult-roll").addEventListener("click", async () => {
  const pending = APP.pendingDifficulty;
  if (!pending) return;
  closeModal("modal-difficult-check");
  APP.pendingDifficulty = null;
  await resolveAssessedTimeSkip(acceptedDifficultyPayload(pending));
});

$("#btn-difficult-cancel").addEventListener("click", () => {
  closeModal("modal-difficult-check");
  APP.pendingDifficulty = null;
  APP.pendingAdvance = null;
  renderQueuedActions(APP.state?.queued_actions || []);
  showToast("Advance canceled. Your queued actions are unchanged.", "system");
  $("#action-input").focus();
});

$("#btn-difficult-timing").addEventListener("click", () => startChallenge("timing"));
$("#btn-difficult-tactical").addEventListener("click", () => startChallenge("tactical"));

// Each stage is a risk-tolerance choice, not a specific action — the check
// title above these options already names the actual action (a jutsu, a
// negotiation, a lockpick, whatever it is), so the options themselves stay
// domain-neutral instead of forcing combat phrasing ("technique", "feint")
// onto checks that aren't a fight at all, which used to read as a total
// non sequitur against a social or stealth check.
const TACTICAL_SCENES = {
  archive: [
    { title: "Approach the archive", help: "Choose a believable way inside.", options: [
      { label: "Wear a clerk's disguise", detail: "Blend into the shift change and carry forged work orders.", points: 23, volatility: 7 },
      { label: "Enter across the rooftops", detail: "Avoid the doors and reach an upper records window.", points: 27, volatility: 16 },
      { label: "Bribe a records clerk", detail: "Trade coin or leverage for a quiet route through security.", points: 21, volatility: 9 },
    ]},
    { title: "Pass the inner watch", help: "The guarded stacks require a second decision.", options: [
      { label: "Follow the filing carts", detail: "Use routine traffic as moving cover.", points: 21, volatility: 6 },
      { label: "Create a false summons", detail: "Pull the watch away with a convincing emergency.", points: 25, volatility: 13 },
      { label: "Question a junior clerk", detail: "Risk conversation to learn the exact shelf and patrol gap.", points: 23, volatility: 10 },
    ]},
    { title: "Secure the record", help: "Take the objective without losing the escape route.", options: [
      { label: "Copy only the key page", detail: "Leave the archive intact and minimize evidence.", points: 20, volatility: 4 },
      { label: "Swap in a forged file", detail: "Hide the theft, but the replacement must survive inspection.", points: 26, volatility: 14 },
      { label: "Take the whole dossier", detail: "Gain everything now and outrun the alarm it may cause.", points: 30, volatility: 22 },
    ]},
  ],
  duel: [
    { title: "Take the initiative", help: "Choose how to shape the opening exchange.", options: [
      { label: "Apply measured pressure", detail: "Probe the opponent while protecting your guard.", points: 22, volatility: 6 },
      { label: "Invite the counterattack", detail: "Offer an opening and punish the committed response.", points: 26, volatility: 14 },
      { label: "Claim the terrain", detail: "Move the duel toward ground that favors your reach or abilities.", points: 24, volatility: 10 },
    ]},
    { title: "Read the adjustment", help: "Your opponent changes rhythm after the opening.", options: [
      { label: "Break their tempo", detail: "Interrupt combinations before they develop.", points: 23, volatility: 8 },
      { label: "Conserve for a reversal", detail: "Yield space now to preserve the stronger finish.", points: 20, volatility: 4 },
      { label: "Attack the exposed weakness", detail: "Commit immediately to the flaw you noticed.", points: 29, volatility: 19 },
    ]},
    { title: "Decide the clash", help: "Choose how to turn your advantage into an outcome.", options: [
      { label: "Force a clean surrender", detail: "Control the finish and limit needless harm.", points: 22, volatility: 6 },
      { label: "Land the decisive counter", detail: "Trust your read and end it in one exchange.", points: 27, volatility: 15 },
      { label: "Risk your strongest technique", detail: "Stake everything on overwhelming the opponent.", points: 32, volatility: 24 },
    ]},
  ],
  dungeon: [
    { title: "Read the passage", help: "Choose how to enter hostile ground.", options: [
      { label: "Scout every sign", detail: "Study tracks, airflow, seams, and recent disturbances.", points: 22, volatility: 5 },
      { label: "Disarm the obvious traps", detail: "Make a controlled lane before the party commits.", points: 25, volatility: 11 },
      { label: "Force a fast passage", detail: "Rely on speed and toughness before the dungeon reacts.", points: 29, volatility: 20 },
    ]},
    { title: "Cross the hazard", help: "The route closes around a new obstacle.", options: [
      { label: "Test a hidden route", detail: "Search for a builder's access or creature trail.", points: 24, volatility: 10 },
      { label: "Use tools and wards", detail: "Spend prepared resources to neutralize the danger.", points: 22, volatility: 5 },
      { label: "Trigger it on your terms", detail: "Control where and when the hazard releases.", points: 28, volatility: 18 },
    ]},
    { title: "Reach the objective", help: "The final chamber can still turn success into disaster.", options: [
      { label: "Secure an escape first", detail: "Protect the retreat before touching the objective.", points: 21, volatility: 4 },
      { label: "Separate prize from trap", detail: "Work carefully against the chamber's mechanism.", points: 26, volatility: 12 },
      { label: "Seize it before opposition arrives", detail: "Trade certainty for a decisive finish.", points: 31, volatility: 23 },
    ]},
  ],
  social: [
    { title: "Open the conversation", help: "Choose what gives your words weight.", options: [
      { label: "Appeal to shared interests", detail: "Show how cooperation serves both sides.", points: 23, volatility: 6 },
      { label: "Offer verifiable proof", detail: "Anchor your claim in facts the other side can test.", points: 25, volatility: 9 },
      { label: "Apply quiet leverage", detail: "Reveal what refusal may cost without making an open threat.", points: 28, volatility: 18 },
    ]},
    { title: "Answer resistance", help: "The other party exposes their real concern.", options: [
      { label: "Address the fear directly", detail: "Name the risk and offer a safeguard.", points: 24, volatility: 8 },
      { label: "Trade a limited concession", detail: "Give something useful without surrendering the goal.", points: 22, volatility: 5 },
      { label: "Call the bluff", detail: "Challenge whether they can afford to walk away.", points: 29, volatility: 19 },
    ]},
    { title: "Close the agreement", help: "Turn momentum into a clear commitment.", options: [
      { label: "Define the next concrete step", detail: "Secure a modest promise that is hard to misunderstand.", points: 22, volatility: 4 },
      { label: "Bind it with witnesses", detail: "Make the agreement costly to deny later.", points: 26, volatility: 12 },
      { label: "Demand the full commitment", detail: "Press for everything while your advantage lasts.", points: 31, volatility: 23 },
    ]},
  ],
  craft: [
    { title: "Prepare the work", help: "Choose how to handle the material's greatest uncertainty.", options: [
      { label: "Test a small sample", detail: "Learn its tolerances before risking the whole piece.", points: 22, volatility: 4 },
      { label: "Adapt a proven design", detail: "Modify reliable methods for this unusual commission.", points: 25, volatility: 10 },
      { label: "Attempt a breakthrough design", detail: "Pursue a much stronger result with little margin for error.", points: 30, volatility: 21 },
    ]},
    { title: "Control the critical step", help: "The work reaches the point where flaws become permanent.", options: [
      { label: "Slow the process", detail: "Protect stability at the cost of time and output.", points: 21, volatility: 4 },
      { label: "Correct the forming flaw", detail: "Intervene precisely before the weakness spreads.", points: 26, volatility: 13 },
      { label: "Use rare material now", detail: "Spend a valuable reserve to force a better result.", points: 29, volatility: 17 },
    ]},
    { title: "Finish and prove it", help: "Choose what standard the completed work must survive.", options: [
      { label: "Tune for reliability", detail: "Favor a dependable creation over peak performance.", points: 22, volatility: 5 },
      { label: "Field-test every function", detail: "Expose weaknesses now and repair what fails.", points: 26, volatility: 12 },
      { label: "Push beyond the safe limit", detail: "Try to awaken the work's exceptional potential.", points: 32, volatility: 24 },
    ]},
  ],
};

function tacticalStagesFor(check) {
  const action = String(check?.action || check?.reason || "").toLowerCase();
  if (/archive|records?|infiltrat|break in|steal|heist|guarded file/.test(action)) return TACTICAL_SCENES.archive;
  if (/duel|fight|battle|attack|combat|opponent|enemy|guardian/.test(action)) return TACTICAL_SCENES.duel;
  if (/dungeon|cave|ruin|trap|passage|tomb|labyrinth/.test(action)) return TACTICAL_SCENES.dungeon;
  if (/persuad|convince|negot|meeting|bargain|ask|recruit|diplom/.test(action)) return TACTICAL_SCENES.social;
  if (/craft|forge|smith|repair|build|enchant|brew|sew/.test(action)) return TACTICAL_SCENES.craft;
  return TACTICAL_SCENES.dungeon;
}
function startChallenge(mode) {
  const pending = APP.pendingDifficulty;
  if (!pending) return;
  const resolutionMode = $$('input[name="challenge-resolution"]:checked')[0]?.value === "continue" ? "continue" : "stop";
  closeModal("modal-difficult-check");
  APP.challenge = { mode, resolutionMode, payload: acceptedDifficultyPayload(pending), checks: pending.checks, index: 0, scores: {}, modes: {}, attempts: [], stage: 0, tacticalPoints: 10 };
  APP.pendingDifficulty = null;
  if (mode === "timing") showTimingCheck(); else showTacticalCheck();
}

function currentChallengeCheck() { return APP.challenge?.checks?.[APP.challenge.index]; }

function finishChallengeCheck(score) {
  const challenge = APP.challenge;
  const check = currentChallengeCheck();
  challenge.scores[check.id] = Math.max(1, Math.min(100, Math.round(score)));
  challenge.modes[check.id] = challenge.mode;
  challenge.index += 1;
  challenge.attempts = []; challenge.stage = 0; challenge.tacticalPoints = 10;
  if (challenge.index < challenge.checks.length) {
    if (challenge.mode === "timing") showTimingCheck(); else showTacticalCheck();
    return;
  }
  const payload = { ...challenge.payload, manual_rolls: { ...(challenge.payload.manual_rolls || {}), ...challenge.scores }, challenge_modes: challenge.modes, challenge_resolution_mode: challenge.resolutionMode };
  closeModal(challenge.mode === "timing" ? "modal-timing-challenge" : "modal-tactical-challenge");
  APP.challenge = null;
  resolveAssessedTimeSkip(payload);
}

let timingAnimation = 0;
let timingPosition = 0;
function animateTimingNeedle(startTime, speed) {
  const elapsed = performance.now() - startTime;
  const phase = (elapsed % speed) / speed;
  timingPosition = phase <= .5 ? phase * 200 : (1 - phase) * 200;
  $("#timing-needle").style.left = timingPosition + "%";
  timingAnimation = requestAnimationFrame(() => animateTimingNeedle(startTime, speed));
}

function beginTimingAttempt() {
  cancelAnimationFrame(timingAnimation);
  const check = currentChallengeCheck();
  const speed = Math.max(700, 1450 - Number(check?.expected_raw_needed || 65) * 6);
  animateTimingNeedle(performance.now(), speed);
  $("#btn-timing-lock").disabled = false;
  $("#btn-timing-lock").textContent = "LOCK TIMING";
}

function showTimingCheck() {
  const challenge = APP.challenge, check = currentChallengeCheck();
  $("#timing-check-count").textContent = `CHECK ${challenge.index + 1} OF ${challenge.checks.length}`;
  $("#timing-check-title").textContent = check.action || check.reason;
  $("#timing-check-info").textContent = `${check.ability} · expected raw requirement about ${check.expected_raw_needed}/100 · known bonus ${Number(check.known_bonus || 0) >= 0 ? "+" : ""}${check.known_bonus || 0}`;
  $("#timing-attempts").textContent = "Attempt 1 of 3";
  openModal("modal-timing-challenge");
  beginTimingAttempt();
}

$("#btn-timing-lock").addEventListener("click", () => {
  const challenge = APP.challenge;
  if (!challenge || challenge.mode !== "timing") return;
  cancelAnimationFrame(timingAnimation);
  const score = Math.max(1, Math.round(100 - Math.abs(timingPosition - 50) * 2));
  challenge.attempts.push(score);
  $("#btn-timing-lock").disabled = true;
  $("#btn-timing-lock").textContent = `SCORE ${score}/100`;
  $("#timing-attempts").textContent = challenge.attempts.map((value, index) => `Attempt ${index + 1}: ${value}`).join(" · ");
  if (challenge.attempts.length >= 3) {
    setTimeout(() => finishChallengeCheck(challenge.attempts.reduce((a, b) => a + b, 0) / 3), 450);
  } else {
    setTimeout(() => { $("#timing-attempts").textContent += ` · Next: ${challenge.attempts.length + 1} of 3`; beginTimingAttempt(); }, 450);
  }
});

function showTacticalCheck() {
  const challenge = APP.challenge, check = currentChallengeCheck();
  $("#tactical-check-count").textContent = `CHECK ${challenge.index + 1} OF ${challenge.checks.length}`;
  $("#tactical-check-title").textContent = check.action || check.reason;
  $("#tactical-check-info").textContent = `${check.ability} · expected raw requirement about ${check.expected_raw_needed}/100 · known bonus ${Number(check.known_bonus || 0) >= 0 ? "+" : ""}${check.known_bonus || 0}`;
  openModal("modal-tactical-challenge");
  renderTacticalStage();
}

function renderTacticalStage() {
  const challenge = APP.challenge, stage = tacticalStagesFor(currentChallengeCheck())[challenge.stage];
  $("#tactical-stage-title").textContent = stage.title;
  $("#tactical-stage-help").textContent = stage.help;
  $("#tactical-progress").textContent = `Approach score so far: ${challenge.tacticalPoints}`;
  $("#tactical-options").innerHTML = stage.options.map((option, index) => `<button type="button" data-tactical-option="${index}"><b>${escapeHtml(option.label)}</b><span>${escapeHtml(option.detail)}</span><small>Base +${option.points} · uncertainty ±${option.volatility}</small></button>`).join("");
}

$("#tactical-options").addEventListener("click", (event) => {
  const button = event.target.closest("[data-tactical-option]");
  const challenge = APP.challenge;
  if (!button || !challenge || challenge.mode !== "tactical") return;
  const stages = tacticalStagesFor(currentChallengeCheck());
  const option = stages[challenge.stage].options[Number(button.getAttribute("data-tactical-option"))];
  const random = new Uint32Array(1); crypto.getRandomValues(random);
  const swing = (random[0] % (option.volatility * 2 + 1)) - option.volatility;
  challenge.tacticalPoints += option.points + swing;
  challenge.stage += 1;
  if (challenge.stage >= stages.length) finishChallengeCheck(challenge.tacticalPoints);
  else renderTacticalStage();
});

function abortChallenge() {
  cancelAnimationFrame(timingAnimation);
  closeModal("modal-timing-challenge"); closeModal("modal-tactical-challenge");
  APP.challenge = null; APP.pendingAdvance = null;
  renderQueuedActions(APP.state?.queued_actions || []);
  showToast("Challenge canceled. Your queued actions are unchanged.", "system");
}
$("#btn-timing-abort").addEventListener("click", abortChallenge);
$("#btn-tactical-abort").addEventListener("click", abortChallenge);

async function processTimeSkipResolution(result, payload) {
  if (result.status === "lethal_confirm_required") {
    APP.pendingLethal = { kind: "timeskip", timeskip: payload };
    $("#lethal-warning").textContent = result.check.lethal_warning || "This plan could kill your character.";
    $("#lethal-risk").textContent = "Risk: " + (result.check.lethal_risk || "high").toUpperCase();
    openModal("modal-lethal");
    return;
  }
  if (result.status === "power_goal_confirm_required") {
    APP.pendingPowerGoal = payload;
    $("#power-goal-warning").textContent = result.warning || "This path may lead somewhere far beyond where you are now.";
    openModal("modal-power-goal");
    return;
  }
  if (result.status === "manual_roll_required") {
    APP.pendingManualRoll = { payload, checkId: result.check_id, check: result.check };
    $("#major-roll-reason").textContent = result.check.major_reason || result.check.reason || "A major turning point hangs in the balance.";
    const needed = result.check?.difficulty ?? result.check?.needed ?? result.check?.target;
    $("#major-roll-details").textContent = needed ? `Raw roll + bonuses vs ${needed} needed` : "Raw roll + relevant stat, skill, title, and situation bonuses";
    $("#major-roll-risk").textContent = String(result.check?.difficulty_label || result.check?.risk || "Extreme difficulty").replaceAll("_", " ");
    $("#major-roll-result").textContent = "Ready to roll";
    setPercentileDice(null);
    const marks = {"Naruto":"忍","Bleach":"魂","Jujutsu Kaisen":"呪","One Piece":"海","Hunter x Hunter":"H×H","Solo Max-Level Newbie":"塔","Overgeared":"OG","Reincarnated as a Slime":"◉","Custom World":"WW"};
    const themeNames = {"Naruto":"SHINOBI FATE","Bleach":"SOUL VERDICT","Jujutsu Kaisen":"CURSED FATE","One Piece":"GRAND LINE FATE","Hunter x Hunter":"HUNTER CHECK","Solo Max-Level Newbie":"TOWER SYSTEM","Overgeared":"SATISFY SYSTEM","Reincarnated as a Slime":"WORLD VOICE","Custom World":"WORLDWALKER"};
    $("#percentile-world-mark").textContent = marks[APP.state?.world] || "WW";
    $("#percentile-theme-label").textContent = themeNames[APP.state?.world] || "WORLDWALKER";
    $("#d100-orb").classList.remove("rolling", "revealed");
    $("#btn-major-roll").disabled = false;
    openModal("modal-major-roll");
    return;
  }
  handleTimeSkipResult(result, payload);
  APP.pendingAdvance = null;
  APP.pendingManualRoll = null;
  $("#time-plan").value = "";
  runBackgroundCheck();
}

function setPercentileDice(roll) {
  const raw = Number(roll);
  if (!Number.isFinite(raw)) {
    $("#d100-tens").textContent = "—"; $("#d100-ones").textContent = "—"; $("#d100-value").textContent = "?";
    $(".percentile-dice").setAttribute("aria-label", "Percentile dice waiting to roll");
    return;
  }
  const value = raw === 100 ? 0 : raw;
  $("#d100-tens").textContent = String(Math.floor(value / 10) * 10).padStart(2, "0");
  $("#d100-ones").textContent = String(value % 10);
  $("#d100-value").textContent = String(raw);
  $(".percentile-dice").setAttribute("aria-label", `Percentile dice showing ${raw}`);
}

$("#btn-major-roll").addEventListener("click", async () => {
  const pending = APP.pendingManualRoll;
  if (!pending) return;
  const button = $("#btn-major-roll");
  button.disabled = true;
  $("#d100-orb").classList.add("rolling");
  $("#percentile-tray").setAttribute("aria-busy", "true");
  $("#major-roll-result").textContent = "Dice in motion";
  playSfx("dice");
  const ticker = setInterval(() => setPercentileDice(1 + Math.floor(Math.random() * 100)), 72);
  try {
    const rolled = await apiPost("/api/dice/d100", {});
    await new Promise((resolve) => setTimeout(resolve, APP.animationsEnabled ? 1150 : 80));
    clearInterval(ticker);
    setPercentileDice(rolled.roll);
    $("#d100-orb").classList.remove("rolling"); $("#d100-orb").classList.add("revealed");
    $("#percentile-tray").setAttribute("aria-busy", "false");
    $("#major-roll-result").textContent = "Result locked";
    await new Promise((resolve) => setTimeout(resolve, APP.animationsEnabled ? 650 : 40));
    closeModal("modal-major-roll");
    const payload = { ...pending.payload, manual_rolls: { ...(pending.payload.manual_rolls || {}), [pending.checkId]: rolled.roll } };
    APP.pendingAdvance = payload;
    const result = await apiPost("/api/time/resolve", payload);
    await processTimeSkipResolution(result, payload);
  } catch (error) { clearInterval(ticker); showToast(error.message, "danger"); button.disabled = false; }
});

function clientDurationMinutes(amount, unit) {
  const multiplier = { moment: 1, minutes: 1, hours: 60, days: 1440, weeks: 10080, months: 43200 }[unit] || 1;
  return Math.max(0, Number(amount || 0) * multiplier);
}

function handleTimeSkipResult(result, payload) {
  const previousState = APP.state;
  appendStoryEntries(result.story, { focusNew: true });
  renderState(result.state);
  playNewCanonEventCues(previousState, result.state);
  // A resolved skip always returns the backend to moment mode. Mirror that
  // locally so the selector and World Systems label never disagree.
  $("#time-unit").value = "moment";
  syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help");
  handleNotifications(result.notifications);
  // The Advance button lives below Action Chat in its own scrolling column.
  // After a turn, return that column to the composer so the player's next
  // input is visible instead of leaving the view parked on Time Control.
  requestAnimationFrame(() => {
    const rightColumn = document.querySelector(".col-right");
    if (rightColumn) rightColumn.scrollTop = 0;
  });
  if (result.died) {
    // A time skip can end in death too (an extreme roll, the Tower's floor
    // countdown) — same death/rewind modal every other death path already
    // uses, just reached from a different resolution pipeline.
    playDeathCue(); shakeApp();
    openModal("modal-death");
  }
  if (result.major_event_reached) {
    showToast(`Major event reached: ${result.major_event_title || "campaign turning point"}.`, "world");
  }
  const eventStop = ["canon_event", "world_event"].includes(result.interruption_kind);
  const freshDangerStop = result.interruption_kind === "danger" && result.danger_notice_required !== false;
  if (result.interrupted && (eventStop || freshDangerStop)) {
    openEventNotice(result);
  } else if (result.interrupted && result.interruption_reason) {
    showToast(result.interruption_reason, result.interruption_kind === "goal_complete" ? "notify" : "system");
  }
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------
async function openNpcChat() {
  try {
    await refreshChat();
    openModal("modal-chat");
  } catch (error) {
    showToast(error.message || "Could not load NPC chat. Please try again.", "danger");
  }
}

$("#btn-open-chat").addEventListener("click", openNpcChat);

async function refreshChat() {
  const data = await apiGet("/api/chats");
  const list = $("#chat-contacts");
  const names = Array.from(new Set([...Object.keys(data.contacts || {}), ...Object.keys(data.chat_threads || {})])).sort();
  list.innerHTML = "";
  if (!names.length) { list.innerHTML = '<p class="hint">No contacts yet. Meet recurring characters in the story to unlock chats.</p>'; return; }
  names.forEach((name) => {
    const unread = (data.unread || []).filter((u) => u.thread === name).length;
    const contact = (data.contacts || {})[name] || {};
    const div = document.createElement("div");
    div.className = "contact-item" + (name === APP.activeChatThread ? " active" : "");
    div.dataset.contactName = name;
    div.innerHTML = `${personPortraitHtml(name, contact, { size: "sm" })}<span>${escapeHtml(name)}</span>${unread ? `<span class="unread-badge">${unread}</span>` : ""}`;
    div.addEventListener("click", () => renderChatThread(name, data));
    list.appendChild(div);
  });
  if (!APP.activeChatThread && names.length) renderChatThread(names[0], data);
  else if (APP.activeChatThread) renderChatThread(APP.activeChatThread, data);
}

function renderChatThread(name, data) {
  APP.activeChatThread = name;
  $$(".chat-contacts .contact-item").forEach((el) => el.classList.toggle("active", el.dataset.contactName === name));
  const msgs = (data.chat_threads || {})[name] || [];
  const contact = (data.contacts || {})[name] || {};
  const box = $("#chat-messages");
  box.innerHTML = msgs.map((m) => {
    const outgoing = m.direction === "outgoing";
    const sender = outgoing ? (APP.state?.name || "You") : (m.sender || name);
    const record = outgoing ? (APP.state || {}) : contact;
    return `<div class="chat-msg ${m.direction}">${personPortraitHtml(sender, record, { size: "sm", className: "chat-avatar" })}<div class="chat-msg-copy"><div class="meta">${escapeHtml(outgoing ? "You" : sender)} · ${escapeHtml(m.time || "")}</div><p>${escapeHtml(m.text)}</p></div></div>`;
  }).join("");
  box.scrollTop = box.scrollHeight;
  apiPost("/api/chats/read", { thread: name }).catch(() => {});
}

$("#btn-chat-send").addEventListener("click", async () => {
  const text = $("#chat-input").value.trim();
  const thread = APP.activeChatThread;
  if (!text || !thread) return;
  const btn = $("#btn-chat-send"), input = $("#chat-input");
  btn.disabled = true; input.disabled = true;
  const originalLabel = btn.textContent;
  btn.textContent = "…";
  // Show the player's own line immediately — the actual reply is a real AI
  // call and can take a few seconds, so the conversation shouldn't look
  // frozen while it's in flight.
  const box = $("#chat-messages");
  box.insertAdjacentHTML("beforeend", `<div class="chat-msg outgoing">${personPortraitHtml(APP.state?.name || "You", APP.state || {}, { size: "sm", className: "chat-avatar" })}<div class="chat-msg-copy"><div class="meta">You</div><p>${escapeHtml(text)}</p></div></div>`);
  box.scrollTop = box.scrollHeight;
  input.value = "";
  try {
    const result = await apiPost("/api/chats/send", { thread, message: text });
    if (result.state) { APP.state = result.state; }
    if (result.notifications) handleNotifications(result.notifications);
    const data = await apiGet("/api/chats");
    renderChatThread(thread, data);
    if (!result.reply) showToast(`${thread} hasn't replied yet.`, "system");
  } catch (e) {
    showToast(e.message, "danger");
  } finally {
    btn.disabled = false; input.disabled = false; btn.textContent = originalLabel; input.focus();
  }
});

// ---------------------------------------------------------------------------
// Power Summary — an instant, no-AI-call read of the character's current
// standing: an estimated tier (mirrors worlds.py's POWER_TIERS, the same
// ladder the Advisor anchors its own power comparisons to, so the two never
// contradict each other), key stats, and titles. Deliberately does NOT
// fabricate a comparison against named rivals — Worldwalker has no tracked
// per-NPC power data to draw that from honestly, so that judgment call is
// handed off to the Advisor instead, which has real campaign context.
// ---------------------------------------------------------------------------
const POWER_TIERS = [
  [0, "Mundane", "An ordinary person with no combat training."],
  [1, "Trained", "A capable fighter or specialist."],
  [2, "Skilled", "A seasoned professional."],
  [3, "Elite", "Among the best in a city or region."],
  [4, "Exceptional", "A nationally recognized talent."],
  [5, "Powerhouse", "Capable of single-handedly turning a battle."],
  [6, "Superhuman", "Clearly beyond ordinary human limits."],
  [7, "Legendary", "A living legend."],
  [8, "World-Class", "Among the strongest beings in the setting."],
  [9, "Cataclysmic", "Can reshape a region or end a war single-handedly."],
  [10, "Reality-Bending", "Power that strains or breaks the setting's normal rules entirely."],
];
const POWER_TIER_THRESHOLDS = [20, 35, 50, 65, 90, 130, 200, 350, 600, 1000];

function powerTierFromScore(score) {
  const numeric = Math.max(0, Number(score) || 0);
  let index = 0;
  for (const threshold of POWER_TIER_THRESHOLDS) { if (numeric >= threshold) index++; else break; }
  const [, name, description] = POWER_TIERS[index];
  return { index, name, description, score: numeric };
}

function estimatePowerTier(stats) {
  const values = Object.values(stats || {}).map(Number).filter((n) => Number.isFinite(n));
  const score = values.length ? values.length / values.reduce((total, value) => total + (1 / Math.max(1, value)), 0) : 0;
  return powerTierFromScore(score);
}

function openPowerSummary() {
  const s = APP.state || {};
  const profile = s._power_profile || {};
  const tier = profile.world_combat || profile.combat || estimatePowerTier(s.stats);
  const overall = profile.world_overall || profile.overall || estimatePowerTier(s.stats);
  const peak = profile.peak || {};
  const axes = profile.axes || {};
  const maxStat = Math.max(1, ...Object.values(s.stats || {}).map(Number).filter(Number.isFinite));
  const statRows = Object.entries(s.stats || {})
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .map(([name, value]) => {
      const pct = Math.max(2, Math.min(100, (Number(value) || 0) / maxStat * 100));
      return `<div class="power-stat-row"><i class="a-icon">${abilityIcon(name)}</i><span>${escapeHtml(name)}</span>
        <div class="clock-track"><i style="width:${pct}%"></i></div><b>${escapeHtml(value)}</b></div>`;
    }).join("") || '<div class="hint">No stats recorded yet.</div>';
  const titles = (s.titles || []).map((t) => `<span class="power-title-chip">🏅 ${escapeHtml(titleLabel(t))}</span>`).join("");
  const classCard = s.world !== "Bleach" && s.class_profile?.name ? renderClassCard(s.class_profile) : "";
  const releaseCards = s.world === "Bleach" ? renderBleachReleases(s.special || {}) : "";
  $("#power-summary-body").innerHTML = `
    <div class="power-summary-head">
      <div><b>${escapeHtml(s.name || "Traveler")}</b><span>${escapeHtml(s.world || "")}${s.position ? ` · ${escapeHtml(s.position)}` : ""}</span></div>
    </div>
    <div class="power-tier-card">
      <div class="power-tier-badge">Balanced Combat · ${escapeHtml(s.world || "World")} Tier ${escapeHtml(tier.index)} · ${escapeHtml(tier.name)}</div>
      <p>${escapeHtml(tier.description || profile.interpretation || "World-relative balanced combat standing.")}</p>
      <div class="power-axis-grid">
        <span><b>Peak</b>${escapeHtml(peak.stat || "—")} ${escapeHtml(peak.value ?? "—")}</span>
        <span><b>Offense</b>${escapeHtml(axes.offense?.stat || "—")} ${escapeHtml(axes.offense?.value ?? "—")}</span>
        <span><b>Speed</b>${escapeHtml(axes.speed?.stat || "—")} ${escapeHtml(axes.speed?.value ?? "—")}</span>
        <span><b>Defense</b>${escapeHtml(axes.defense?.stat || "—")} ${escapeHtml(axes.defense?.value ?? "—")}</span>
      </div>
      <small>Overall foundation: Tier ${escapeHtml(overall.index)} · ${escapeHtml(overall.name)} (balanced score ${escapeHtml(overall.score ?? "—")}). Peak output is not treated as every stat. ${escapeHtml(profile.interpretation || "")}</small>
    </div>
    <div class="power-stat-list">${statRows}</div>
    ${releaseCards}
    ${classCard}
    ${titles ? `<div class="power-title-list">${titles}</div>` : ""}
    <button id="btn-power-summary-ask-advisor" class="btn-ghost full">⚖ Ask the Advisor how you compare</button>
  `;
  $("#btn-power-summary-ask-advisor").addEventListener("click", () => {
    closeModal("modal-power-summary");
    closeModal("modal-journal");
    openModal("modal-advisor");
    askAdvisor("How strong am I compared to the threats and rivals around me right now?");
  });
  openModal("modal-power-summary");
}

// ---------------------------------------------------------------------------
// Advisor — Pax Historia-style meta guide: power levels, world state, advice.
// Out-of-character, no turn cost, no state changes. Responses are structured
// (summary + bullet points + suggested follow-ups) rather than a text blob.
// ---------------------------------------------------------------------------
function renderAdvisorChart(chart) {
  if (!chart || !chart.items || !chart.items.length) return "";
  const max = Math.max(...chart.items.map((it) => Math.abs(it.value)), 1e-9);
  const rows = chart.items.map((it) => {
    const pct = Math.max(2, Math.abs(it.value) / max * 100);
    const valueLabel = Number.isFinite(it.value) ? (Math.abs(it.value) >= 1000 ? it.value.toLocaleString() : String(it.value)) : "";
    return `<div class="advisor-chart-row">
      <div class="advisor-chart-label">${personPortraitHtml(it.label, it, { size: "xs" })}<span>${escapeHtml(it.label)}</span></div>
      <div class="advisor-chart-track"><div class="advisor-chart-bar" style="width:${pct}%"></div></div>
      <div class="advisor-chart-value">${escapeHtml(valueLabel)}</div>
    </div>`;
  }).join("");
  return `<div class="advisor-chart">
    <div class="advisor-chart-title">${escapeHtml(chart.title || "Comparison")}${chart.unit ? ` <span>(${escapeHtml(chart.unit)})</span>` : ""}</div>
    ${rows}
  </div>`;
}

function renderAdvisorMessage(m) {
  if (m.role === "player") {
    return `<div class="chat-msg outgoing">${personPortraitHtml(APP.state?.name || "You", APP.state || {}, { size: "sm", className: "chat-avatar" })}<div class="chat-msg-copy"><div class="meta">You</div><p>${escapeHtml(m.text)}</p></div></div>`;
  }
  const points = (m.points || []).map((p) => `<li>${escapeHtml(p)}</li>`).join("");
  const countdown = m.canon_countdown?.label ? `<div class="advisor-countdown">⏳ ${escapeHtml(m.canon_countdown.label)}</div>` : "";
  const evidenceRows = (m.evidence || []).map((row) => `<li><b>${escapeHtml(row.label || "Evidence")}</b><span>${escapeHtml(row.detail || "")}</span><small>${escapeHtml(row.source || "campaign")}</small></li>`).join("");
  const evidence = evidenceRows ? `<details class="advisor-evidence"><summary>Why the Advisor says this</summary><ul>${evidenceRows}</ul></details>` : "";
  const involved = mentionedPortraitsHtml([m.summary, m.text, ...(m.points || [])].filter(Boolean).join(" "), knownPersonRecords(), 3, "sm");
  return `<div class="chat-msg incoming advisor-msg"><div class="chat-msg-copy"><div class="meta advisor-meta">Advisor${m.fourth_wall ? " · FOURTH-WALL" : ""}${involved}</div>
    <div class="advisor-msg-summary">${escapeHtml(m.summary || m.text || "...")}</div>
    ${renderAdvisorChart(m.chart)}
    ${countdown}${points ? `<ul class="advisor-msg-points">${points}</ul>` : ""}${evidence}
  </div></div>`;
}

function renderAdvisorThread(thread) {
  const list = thread || [];
  const box = $("#advisor-messages");
  box.innerHTML = list.map(renderAdvisorMessage).join("") || '<p class="hint">No questions asked yet — try one of the prompts above.</p>';
  // Open on the beginning of the newest answer, not the bottom half of a
  // long briefing. On phones the old bottom-scroll made a briefing appear
  // to begin at point two or three with its summary off-screen.
  requestAnimationFrame(() => {
    const latest = box.querySelector(".advisor-msg:last-of-type") || box.lastElementChild;
    box.scrollTop = latest ? Math.max(0, latest.offsetTop - box.offsetTop - 6) : 0;
  });
  $("#advisor-starters").style.display = list.length ? "none" : "flex";

  const last = list[list.length - 1];
  const followWrap = $("#advisor-followups");
  if (last && last.role === "advisor" && last.follow_ups && last.follow_ups.length) {
    followWrap.innerHTML = last.follow_ups.map((q) => `<button data-q="${escapeHtml(q)}">${escapeHtml(q)}</button>`).join("");
  } else {
    followWrap.innerHTML = "";
  }
}

async function askAdvisor(text) {
  if (!text) return;
  $("#advisor-input").value = "";
  $("#advisor-starters").style.display = "none";
  const box = $("#advisor-messages");
  if (box.querySelector(".hint")) box.innerHTML = "";
  box.innerHTML += renderAdvisorMessage({ role: "player", text });
  box.scrollTop = box.scrollHeight;
  $("#advisor-followups").innerHTML = "";
  try {
    const result = await apiPost("/api/advisor/ask", { question: text, fourth_wall: $("#advisor-fourth-wall").checked });
    playSfx("notify");
    renderState(result.state);
    const r = await apiGet("/api/advisor");
    renderAdvisorThread(r.thread);
  } catch (e) { showToast(e.message, "danger"); }
}

$("#btn-open-advisor").addEventListener("click", async () => {
  if (!APP.campaignActive) { showToast("Start a campaign first.", "system"); return; }
  try {
    const r = await apiGet("/api/advisor");
    renderAdvisorThread(r.thread);
    openModal("modal-advisor");
  } catch (e) { showToast(e.message, "danger"); }
});

$("#btn-advisor-send").addEventListener("click", () => askAdvisor($("#advisor-input").value.trim()));
$("#advisor-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); askAdvisor($("#advisor-input").value.trim()); }
});
$("#advisor-starters").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-q]");
  if (btn) askAdvisor(btn.getAttribute("data-q"));
});
$("#advisor-followups").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-q]");
  if (btn) askAdvisor(btn.getAttribute("data-q"));
});

// ---------------------------------------------------------------------------
// Journal (party / quests / codex / inventory / shops / map / combat)
// ---------------------------------------------------------------------------
$$("[data-journal]").forEach((btn) => btn.addEventListener("click", () => openJournal(btn.getAttribute("data-journal"))));
$$("#journal-tabs button[data-tab]").forEach((btn) => btn.addEventListener("click", () => openJournal(btn.getAttribute("data-tab"))));
document.addEventListener("click", async (event) => {
  const relationshipChoice = event.target.closest("[data-interact-person]");
  if (relationshipChoice) {
    event.preventDefault(); event.stopPropagation();
    openActionDeck(relationshipChoice.getAttribute("data-interact-person"));
    return;
  }
  const portrait = event.target.closest("[data-person-open]");
  if (!portrait || portrait.closest(".contact-item,.suggestion-card,.roster-unit,.piece")) return;
  const name = portrait.getAttribute("data-person-open");
  if (!name || normalizePersonName(name) === normalizePersonName(APP.state?.name)) return;
  await openJournal("relationships");
  const card = [...document.querySelectorAll("[data-person-card]")].find((node) => normalizePersonName(node.getAttribute("data-person-card")) === normalizePersonName(name));
  if (card) { card.open = true; card.scrollIntoView({ block: "center", behavior: APP.animationsEnabled ? "smooth" : "auto" }); }
  else showToast(`${name} does not have a full relationship record yet.`, "system");
});
$("#btn-journal-advanced-toggle").addEventListener("click", () => setJournalAdvancedOpen($("#journal-tabs-advanced").hidden));

function setJournalAdvancedOpen(open) {
  $("#journal-tabs-advanced").hidden = !open;
  $("#btn-journal-advanced-toggle").textContent = open ? "Less ▴" : "More ▾";
}

let livingMapRefreshTimer = 0;
let livingMapRefreshSequence = 0;

function scheduleLivingMapRefresh(state) {
  window.clearTimeout(livingMapRefreshTimer);
  const signature = `${state?.campaign_id || state?.name || ""}|${state?.world || "Custom World"}|${state?.turn || 0}|${state?.location || ""}|${JSON.stringify([state?.political_regions,state?.location_details,state?.custom_locations])}`;
  if (APP.livingMapSignature === signature && $("#map-canvas")) return;
  livingMapRefreshTimer = window.setTimeout(() => refreshMainLivingMap(signature), 0);
}

async function refreshMainLivingMap(signature = "") {
  const host = $("#living-map-main-body");
  if (!host) return;
  const sequence = ++livingMapRefreshSequence;
  try {
    const data = await apiGet("/api/panels");
    if (window.WorldwalkerRosterSync) data.organization_roster = WorldwalkerRosterSync.reconcile(data.organization_roster, APP.state || {});
    if (sequence !== livingMapRefreshSequence) return;
    const activeWorld = APP.state?.world || "Custom World";
    if (data.world !== activeWorld) throw new Error(`Map data mismatch: expected ${activeWorld}, received ${data.world || "unknown"}.`);
    renderMainLivingMap(data);
    APP.livingMapSignature = signature || `${APP.state?.campaign_id || APP.state?.name || ""}|${activeWorld}|${APP.state?.turn || 0}|${APP.state?.location || ""}`;
  } catch (error) {
    if (sequence !== livingMapRefreshSequence) return;
    host.innerHTML = `<div class="living-map-unavailable"><b>${escapeHtml(APP.state?.world || "World")} MAP UNAVAILABLE</b><span>${escapeHtml(error.message || "This world's map could not be loaded.")}</span><button type="button" class="btn-ghost" data-map-retry>TRY AGAIN</button></div>`;
    host.querySelector("[data-map-retry]")?.addEventListener("click", () => refreshMainLivingMap());
  }
}

function selectedLivingMapBoard(mapPayload, world) {
  const boards = Array.isArray(mapPayload.boards) ? mapPayload.boards : [];
  const scope = `${APP.state?.campaign_id || APP.state?.name}:${world}`;
  APP.mapActiveRealm ||= {};
  if (APP.mapActiveRealm[scope] !== mapPayload.active_board) {
    APP.mapBoardSelectionByWorld ||= {};
    APP.mapBoardSelectionByWorld[world] = mapPayload.active_board;
    APP.mapActiveRealm[scope] = mapPayload.active_board;
  }
  const saved = APP.mapBoardSelectionByWorld?.[world];
  return boards.find((board) => board.name === saved)
    || boards.find((board) => board.name === mapPayload.active_board) || boards[0] || null;
}

function trackedLivingMapPeople(data, nodes) {
  const rosterNames = new Set();
  (data.organization_roster?.groups || []).forEach((group) => (group.members || []).forEach((member) => {
    if (member?.name && !["left", "dead", "deceased", "expelled"].includes(String(member.status || "active").toLowerCase())) rosterNames.add(normalizePersonName(member.name));
  }));
  const locate = (location) => {
    const key = normalizePersonName(location);
    if (!key || key === "unknown") return null;
    return nodes.find((node) => {
      const candidate = normalizePersonName(node.name);
      return candidate === key || candidate.includes(key) || key.includes(candidate);
    }) || null;
  };
  return (data.relationships_view?.people || []).filter((person) => {
    const score = Math.abs(Number(person.score) || 0);
    return score >= 20 || person.nemesis || rosterNames.has(normalizePersonName(person.name));
  }).map((person, index) => {
    const node = locate(person.last_known_location);
    if (!node) return null;
    const angle = (index % 8) * Math.PI / 4, radius = 1.15 + (index % 3) * .35;
    return { ...person, x: Number(node.x) + Math.cos(angle) * radius, y: Number(node.y) + Math.sin(angle) * radius };
  }).filter(Boolean);
}

function renderMainLivingMap(data) {
  const host = $("#living-map-main-body"), shell = $("#living-map-main");
  if (!host || !shell) return;
  APP.latestMapData = data;
  const world = data.world || APP.state?.world || "Custom World";
  const mapPayload = data.map_data || {};
  const boards = Array.isArray(mapPayload.boards) ? mapPayload.boards : [];
  const selectedBoard = selectedLivingMapBoard(mapPayload, world);
  const nodes = selectedBoard?.nodes || mapPayload.nodes || [];
  const regions = selectedBoard?.regions || mapPayload.regions || [];
  const mapImage = selectedBoard?.image || data.map_image || "";
  const atlas = selectedBoard?.atlas || mapPayload.atlas;
  const atlasKey = `${APP.state?.campaign_id || APP.state?.name || 'campaign'}:${atlas?.id || world}`;
  const mapMeta = mapPayload.meta || {};
  const travelGraph = data.travel_graph || { edges: {} };
  if (!atlas?.cells?.length || !nodes.length) throw new Error(`No ${world} geography is installed in this build.`);
  const knownCount = nodes.filter((node) => node.discovered).length;
  const legendChips = [...new Set(atlas.cells.map(cell => cell.owner))].sort()
    .map((name) => `<span class="territory-chip" style="--tc:${WorldAtlas.color(name)}"><i></i>${escapeHtml(name)}</span>`).join("");
  const boardPicker = boards.length ? `<label class="map-board-picker"><span>Realm map</span><select id="map-board-select">${boards.map((board) => `<option value="${escapeHtml(board.name)}"${board.name === selectedBoard?.name ? " selected" : ""}>${escapeHtml(board.name)}${board.name === mapPayload.active_board ? " · current realm" : ""}</option>`).join("")}</select></label>` : "";
  const mode = APP.mainMapMode || "political";
  host.innerHTML = `<div class="map-heading"><div><span class="map-kicker">${escapeHtml(mapMeta.projection || "LIVING ATLAS")}</span><b>${escapeHtml(selectedBoard?.name || world)}</b><small>${nodes.length} landmarks · ${knownCount} discovered · ${escapeHtml(APP.state?.world_time || "Current campaign")}</small></div>${boardPicker}<div class="map-mode-tabs" role="tablist" aria-label="Map view"><button data-main-map-mode="political">Political</button><button data-main-map-mode="danger">Danger</button><button data-main-map-mode="relationships">Relations</button><button data-main-map-mode="events">Events</button></div></div>` +
    (legendChips ? `<div class="territory-legend">${legendChips}</div>` : "") +
    `<div class="map-layout"><div class="map-wrap" id="map-wrap"><div class="map-canvas" id="map-canvas" data-map-render="living" data-world="${escapeHtml(world)}" style="--map-image:url('${escapeHtml(mapImage)}')"><canvas class="map-territories" id="map-territory-canvas"></canvas><canvas class="map-routes" id="map-route-canvas"></canvas><div class="map-faction-labels" id="map-faction-labels" aria-hidden="true"></div><div id="map-ambient" class="map-ambient" aria-hidden="true"></div></div><div class="map-view-pill" id="map-view-pill">WORLD VIEW</div><div class="map-zoom-controls"><button type="button" data-map-zoom-in title="Zoom in" aria-label="Zoom in">+</button><button type="button" data-map-zoom-out title="Zoom out" aria-label="Zoom out">−</button><button type="button" data-map-focus title="Focus current location" aria-label="Focus current location">◉</button><button type="button" data-map-zoom-reset title="Reset view" aria-label="Reset map view">⤢</button></div><div class="map-ribbon">The map shows the active ${escapeHtml(world)} campaign and changes with its narrative.</div></div><aside class="map-detail" id="map-detail" tabindex="-1"><b>Select a landmark</b><p>${escapeHtml(mapMeta.accuracy_note || "Borders repaint whenever the story changes control.")}</p><small>Drag to pan. Scroll or use the controls to zoom.${boards.length ? " Change realm above without moving the character." : ""}</small></aside></div>`;
  shell.dataset.mapMode = mode;
  host.querySelector('.map-heading').insertAdjacentHTML('afterend', `<form class="atlas-search"><input aria-label="Find a map location" placeholder="Find a location…" list="atlas-locations" autocomplete="off"><datalist id="atlas-locations">${nodes.map(n=>`<option value="${escapeHtml(n.name)}"></option>`).join('')}</datalist><button type="submit">Find</button><button type="button" data-atlas-info aria-label="Map information">ⓘ</button><small>Drag · pinch · zoom</small></form>`);
  shell.dataset.mapWorld = world;
  $$("[data-main-map-mode]", host).forEach((button) => button.classList.toggle("active", button.dataset.mainMapMode === mode));
  const mapCanvas = $("#map-canvas");
  const atlasResult = WorldAtlas.render(mapCanvas, atlas, atlasKey);
  const ribbon = host.querySelector('.map-ribbon');
  if (ribbon) ribbon.textContent = atlasResult.changed ? `Territory changed · ${atlasResult.changed} land tiles repainted` : 'Campaign borders · canon-informed geography';
  const previousPlayer = APP.lastLivingMapPlayer;
  nodes.forEach((node) => {
    const dot = document.createElement("button");
    const majorKinds = new Set(["capital", "city", "village", "nation", "region", "realm", "island", "kingdom", "empire", "floor"]);
    const major = majorKinds.has(String(node.kind || "").toLowerCase());
    dot.type = "button";
    dot.className = "map-node " + (node.current ? "here" : node.discovered ? "known" : "unknown") + (major ? " map-major" : "") + (node.danger_level ? " danger-" + node.danger_level.toLowerCase() : "") + (node.recently_changed ? " territory-changed" : "") + ((node.contested_by?.length || node.conflict_operations?.length) ? " territory-contested" : "");
    dot.style.left = `${node.x}%`;
    dot.style.top = `${node.y}%`;
    dot.title = `${node.display_name || node.name} · ${node.kind || "landmark"}${node.controller && node.controller !== "Unknown" ? ` · ${node.controller}` : ""}${node.contested_by?.length ? ` · Contested by ${node.contested_by.join(', ')}` : ""}${node.conflict_operations?.length ? ` · ${node.conflict_operations.length} active faction operation${node.conflict_operations.length===1?'':'s'}` : ""}`;
    dot.dataset.mapNode = node.name;
    dot.innerHTML = `<span class="map-pip"></span><span class="map-label">${escapeHtml(node.display_name || node.name)}</span>`;
    mapCanvas.appendChild(dot);
    if (node.current) {
      const piece = document.createElement('span');
      piece.className = 'map-person map-player-piece'; piece.textContent = '◆';
      piece.style.left = `${previousPlayer?.key === atlasKey ? previousPlayer.x : node.x}%`;
      piece.style.top = `${previousPlayer?.key === atlasKey ? previousPlayer.y : node.y}%`;
      mapCanvas.appendChild(piece);
      requestAnimationFrame(() => requestAnimationFrame(() => { piece.style.left = `${node.x}%`; piece.style.top = `${node.y}%`; }));
      APP.lastLivingMapPlayer = { key: atlasKey, world, x: Number(node.x), y: Number(node.y) };
    }
  });
  const previousPeople = APP.lastLivingMapPeople || {};
  const nextPeople = {};
  trackedLivingMapPeople(data, nodes).forEach((person) => {
    const marker = document.createElement("button"), key = `${atlasKey}:${normalizePersonName(person.name)}`;
    const previous = previousPeople[key];
    marker.type = "button"; marker.className = `map-person${person.nemesis ? " nemesis" : ""}`;
    marker.style.left = `${previous?.x ?? person.x}%`; marker.style.top = `${previous?.y ?? person.y}%`;
    marker.dataset.mapPerson = person.name;
    marker.title = `${person.name} · ${person.label || "Known person"} · last known at ${person.last_known_location}`;
    marker.innerHTML = `${personPortraitHtml(person.name, person, { size: "sm" })}<span>${escapeHtml(person.name)}</span>`;
    mapCanvas.appendChild(marker);
    requestAnimationFrame(() => requestAnimationFrame(() => { marker.style.left = `${person.x}%`; marker.style.top = `${person.y}%`; }));
    nextPeople[key] = { x: person.x, y: person.y };
  });
  APP.lastLivingMapPeople = nextPeople;
  APP.mapNodes = nodes; APP.mapRegions = regions; APP.travelGraph = travelGraph;
  WorldAtlas.bind($("#map-wrap"), mapCanvas, atlasKey, (zoom) => {
    shell.dataset.zoomBand = zoom < 1.35 ? 'world' : zoom < 2.2 ? 'regional' : 'local';
    const pill = $('#map-view-pill'); if (pill) pill.textContent = `${shell.dataset.zoomBand.toUpperCase()} VIEW`;
  });
  paintMapRoutes($("#map-route-canvas"), nodes, travelGraph);
  requestAnimationFrame(() => WorldAtlas.labels());
  wireMainLivingMap(host, world, mapPayload, atlas || {});
  LivingAdventures.wireMap(host);
}

function focusApprovedLivingMap() {
  closeModal("modal-journal");
  if (isMobileLayout()) setMobileView("map");
  else $("#living-map-main")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function wireMainLivingMap(host, world, mapPayload, atlas = {}) {
  const search = host.querySelector('.atlas-search');
  if (search) search.onsubmit = event => {
    event.preventDefault();
    const input = search.querySelector('input'), value = input.value.trim().toLowerCase();
    const node = (APP.mapNodes || []).find(n => [n.name,n.display_name].some(s=>s?.toLowerCase()===value)) || (value && (APP.mapNodes || []).find(n=>[n.name,n.display_name].some(s=>s?.toLowerCase().includes(value))));
    input.setCustomValidity(node ? '' : 'Choose a location on this map.');
    if (!node) { input.reportValidity(); return; }
    WorldAtlas.focus(node.x,node.y); showLivingMapNode(node.name);
  };
  search?.querySelector('input')?.addEventListener('input', event => event.target.setCustomValidity(''));
  host.querySelector("#map-board-select")?.addEventListener("change", (event) => {
    APP.mapBoardSelectionByWorld ||= {};
    APP.mapBoardSelectionByWorld[world] = event.target.value;
    refreshMainLivingMap();
  });
  host.querySelectorAll("[data-main-map-mode]").forEach((button) => button.addEventListener("click", () => {
    APP.mainMapMode = button.dataset.mainMapMode;
    $("#living-map-main").dataset.mapMode = APP.mainMapMode;
    host.querySelectorAll("[data-main-map-mode]").forEach((peer) => peer.classList.toggle("active", peer === button));
  }));
  host.querySelectorAll("[data-map-node]").forEach((button) => button.addEventListener("click", () => showLivingMapNode(button.dataset.mapNode)));
  host.querySelectorAll("[data-map-person]").forEach((button) => button.addEventListener("click", () => showLivingMapPerson(button.dataset.mapPerson)));
  host.onclick = (event) => {
    if (event.target.closest('[data-atlas-close]')) { LivingAdventures.cancelSelection(); $('#map-detail')?.classList.remove('open'); return; }
    if (event.target.closest('[data-atlas-info]')) {
      LivingAdventures.cancelSelection();
      const detail = $('#map-detail'); detail.classList.add('open');
      const context = atlas.context || {};
      detail.innerHTML = `<button type="button" class="atlas-close" data-atlas-close aria-label="Close map details">×</button><b>About this atlas</b>${(context.notes || []).map(note=>`<p>${escapeHtml(note)}</p>`).join('')}<p>Canon and well-supported fan references guide the geography. Unspecified borders are extrapolated for consistent play. All land has an assigned controller.</p><p>Starting history: ${escapeHtml(context.basis || 'world preset')}. Passing a canon date does not override your campaign’s conquests or prevented events.</p>${(context.sources || []).map(source=>`<p><a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.title)}</a></p>`).join('')}`;
      return;
    }
    const wrap = $("#map-wrap"); if (!wrap) return;
    const rect = wrap.getBoundingClientRect(), cx = rect.width / 2, cy = rect.height / 2;
    if (event.target.closest("[data-map-zoom-in]")) WorldAtlas.zoom(1.3);
    else if (event.target.closest("[data-map-zoom-out]")) WorldAtlas.zoom(1/1.3);
    else if (event.target.closest("[data-map-zoom-reset]")) WorldAtlas.reset();
    else if (event.target.closest("[data-map-focus]")) {
      const current = (APP.mapNodes || []).find((node) => node.current);
      if (current) WorldAtlas.focus(current.x, current.y);
    }
  };
}

function showLivingMapPerson(name) {
  LivingAdventures.cancelSelection();
  const person = (APP.latestMapData?.relationships_view?.people || []).find((row) => row.name === name), detail = $("#map-detail");
  if (!person || !detail) return;
  detail.classList.add("open");
  detail.innerHTML = `<div class="map-person-heading">${personPortraitHtml(person.name, person, { size: "md" })}<div><b>${escapeHtml(person.name)}</b><small>${escapeHtml(person.label || "Known person")}</small></div></div><p>${escapeHtml(person.goal || "No current goal is known.")}</p><dl><dt>Relationship</dt><dd>${escapeHtml(person.score ?? 0)}</dd><dt>Last known</dt><dd>${escapeHtml(person.last_known_location || "Unknown")}</dd><dt>Knowledge</dt><dd>${person.knowledge?.length ? person.knowledge.map(escapeHtml).join(", ") : "Nothing reliably established"}</dd></dl>`;
  detail.focus({ preventScroll: true });
  detail.insertAdjacentHTML('afterbegin','<button type="button" class="atlas-close" data-atlas-close aria-label="Close map details">×</button>');
}

async function showLivingMapNode(name) {
  return LivingAdventures.showLocation(name);
}

async function openJournal(tab) {
  if (tab === "map") {
    APP.journalTab = "map";
    return focusApprovedLivingMap();
  }
  APP.journalTab = tab;
  // The atlas is a primary play surface, not a card-sized journal entry.
  // Promote it to a viewport workspace while it is selected; every other
  // journal page keeps the familiar modal dimensions.
  $("#modal-journal").classList.toggle("map-workspace", tab === "map");
  if ($(`#journal-tabs-advanced button[data-tab="${tab}"]`)) setJournalAdvancedOpen(true);
  $$("#journal-tabs button[data-tab]").forEach((b) => b.classList.toggle("active", b.getAttribute("data-tab") === tab));
  openModal("modal-journal");
  const data = await apiGet("/api/panels");
  const panel = $("#journal-panel");
  const s = APP.state || {};
  if (tab === "party") {
    const combinations = data.companion_combinations || [];
    const playerSummary = s._uses_xp ? `Level ${s.level ?? 1} · ${worldIdentityLabel(s)}` : worldIdentityLabel(s);
    const reconciledRoster = window.WorldwalkerRosterSync ? WorldwalkerRosterSync.reconcile(data.organization_roster || s._organization_roster || {groups: []}, s) : (data.organization_roster || s._organization_roster || {groups: []});
    const partyRows = renderOrganizationRoster(reconciledRoster);
    const comboRows = combinations.length ? `<h3>Combination abilities</h3>${combinations.map((combo) => `<details class="combination-card"><summary><b>${escapeHtml(combo.name)}</b><span>${escapeHtml(combo.mastery || 0)}% mastery</span></summary><p>${escapeHtml(combo.description || "A practiced shared technique.")}</p><small>${escapeHtml((combo.participants || []).join(" + "))}</small>${combo.activation ? `<p><b>Use:</b> ${escapeHtml(combo.activation)}</p>` : ""}${combo.limitation ? `<p><b>Limit:</b> ${escapeHtml(combo.limitation)}</p>` : ""}</details>`).join("")}` : "";
    const command = data.organization_command || { groups: [], assignments: [], reports: [], task_types: [] };
    const ownedProperties = (data.property_economy?.properties || []);
    const commandForms = (command.groups || []).map((group) => {
      const memberChecks = (group.members || []).map((m) => `<label class="org-command-member${m.busy ? " is-busy" : ""}"><input type="checkbox" name="member" value="${escapeHtml(m.name)}"${m.busy ? " disabled" : ""}><span><b>${escapeHtml(m.name)}</b><small>${escapeHtml(m.position || "Member")} · ${escapeHtml(m.power_label || "Unassessed")}${m.busy ? " · Assigned" : ""}</small></span></label>`).join("");
      const taskOptions = (command.task_types || []).map((task) => `<option value="${escapeHtml(task.id)}">${escapeHtml(task.label)} · ${escapeHtml(formatDuration(task.duration_minutes))} · risk ${escapeHtml(task.risk)}</option>`).join("");
      const projectForm = group.authority === "leader" && ownedProperties.length ? `<form class="org-project-form" data-org-project-form data-group-id="${escapeHtml(group.id)}"><b>Develop an organization base</b><label>Owned base<select name="property">${ownedProperties.map((property) => `<option value="${escapeHtml(property.id)}">${escapeHtml(property.name)} · ${escapeHtml(property.location)}</option>`).join("")}</select></label><label>Facility<select name="facility"><option value="quarters">Member quarters</option><option value="training_hall">Training hall</option><option value="infirmary">Infirmary</option><option value="intelligence_office">Intelligence office</option><option value="defenses">Defenses</option><option value="storage">Storage wing</option><option value="workshop">Production floor</option></select></label><button type="submit">START 2-DAY PROJECT</button></form>` : "";
      return `<section class="organization-command-card"><header><b>${escapeHtml(group.name)}</b><span>${escapeHtml(group.authority)}</span></header><p class="hint">Resources: ${Object.entries(group.resources || {}).map(([k,v]) => `${escapeHtml(humanLabel(k))} ${escapeHtml(v)}`).join(" · ")}</p><form data-org-command-form data-group-id="${escapeHtml(group.id)}"><label>Assignment<select name="task">${taskOptions}</select></label><label>Objective / destination<input name="target" placeholder="What should this team accomplish?"></label><fieldset><legend>Assign members</legend>${memberChecks || '<span class="hint">No commandable members are currently available.</span>'}</fieldset><button type="submit"${memberChecks ? "" : " disabled"}>ISSUE ORDER</button></form>${projectForm}</section>`;
    }).join("");
    const assignmentRows = (command.assignments || []).slice().reverse().map((a) => `<article class="org-assignment"><header><b>${escapeHtml(a.group)} · ${escapeHtml(a.label || humanLabel(a.task))}</b><span>${escapeHtml(a.status)} · ${escapeHtml(a.progress || 0)}%</span></header><p>${escapeHtml(a.target)}</p><small>${escapeHtml((a.members || []).join(" · "))}</small>${a.report ? `<p>${escapeHtml(a.report)}</p>` : ""}${a.status === "active" ? `<button type="button" data-org-cancel="${escapeHtml(a.id)}">RECALL TEAM</button>` : ""}</article>`).join("");
    const commandCenter = commandForms ? `<h3>Organization command</h3><p class="hint">Delegate work through established authority. Assignments advance while campaign time passes; independent allies cannot be ordered.</p>${commandForms}${assignmentRows ? `<h3>Assignments & reports</h3>${assignmentRows}` : ""}` : "";
    panel.innerHTML = partyRows + `<div class="jrow"><b>${escapeHtml(s.name || "Traveler")}</b> — ${escapeHtml(playerSummary)}</div>` + commandCenter + comboRows;
    panel.querySelectorAll('[data-org-command-form]').forEach((form) => form.addEventListener('submit', async (event) => {
      event.preventDefault(); const button=form.querySelector('button[type="submit"]');button.disabled=true;
      try { const payload={action:'start',group_id:form.dataset.groupId,task:form.elements.task.value,target:form.elements.target.value,members:[...form.querySelectorAll('input[name="member"]:checked')].map(x=>x.value)}; await apiPost('/api/organization-command',payload); showToast('Organization assignment issued.','success'); return openJournal('party'); } catch(error){showToast(error.message,'danger');button.disabled=false;}
    }));
    panel.querySelectorAll('[data-org-project-form]').forEach((form) => form.addEventListener('submit', async (event) => {
      event.preventDefault(); const button=form.querySelector('button[type="submit"]');button.disabled=true;
      try { await apiPost('/api/organization-command',{action:'project',group_id:form.dataset.groupId,property_id:form.elements.property.value,facility:form.elements.facility.value}); showToast('Organization base project started.','success'); return openJournal('party'); } catch(error){showToast(error.message,'danger');button.disabled=false;}
    }));
    panel.querySelectorAll('[data-org-cancel]').forEach((button) => button.addEventListener('click', async () => {
      try { await apiPost('/api/organization-command',{action:'cancel',assignment_id:button.dataset.orgCancel}); showToast('Team recalled.','success'); return openJournal('party'); } catch(error){showToast(error.message,'danger');}
    }));
  } else if (tab === "search") {
    panel.innerHTML = `<div class="system-summary"><b>SEARCH YOUR CAMPAIGN</b><span>Find old actions, people, quests, skills, chapters, facts, and player corrections without scrolling through the entire Chronicle.</span></div><form id="campaign-search-form" class="campaign-search-form"><input id="campaign-search-query" type="search" minlength="2" placeholder="Try a name, place, ability, promise, or event" required><button class="btn-primary" type="submit">SEARCH</button></form><div id="campaign-search-results" class="campaign-search-results"><div class="jrow hint">Enter at least two characters to search locally. This makes no AI call.</div></div>`;
    setTimeout(() => $("#campaign-search-query")?.focus(), 0);
  } else if (tab === "corrections") {
    const corrections = [...(data.simulation?.integrity?.corrections || [])].reverse();
    const currencyCorrection = data.tracks_currency === false ? "" : `<option value="currency">Currency amount</option>`;
    panel.innerHTML = `<div class="system-summary"><b>CORRECT THE GM</b><span>Your correction becomes an authoritative campaign fact, previews the selected change before applying it, and is included in future GM context. This makes no AI call and does not advance time.</span></div>${APP.correctionSource ? `<blockquote class="correction-source"><small>${escapeHtml(APP.correctionSource.time || "Selected Chronicle entry")}</small><p>${escapeHtml(APP.correctionSource.text)}</p></blockquote>` : ""}<form id="gm-correction-form" class="gm-correction-form"><label>What needs correcting<select id="correction-type"><option value="fact">Story fact</option><option value="location">Current location</option><option value="inventory_add">Missing inventory item</option><option value="inventory_remove">Item you no longer own</option>${currencyCorrection}<option value="hp">Current health</option><option value="resource">Current energy pool</option><option value="quest_status">Quest status</option><option value="skill">Skill description</option></select></label><label>Target or name<input id="correction-target" type="text" placeholder="Sword, quest name, skill name, character…"></label><label>Correct value<textarea id="correction-value" rows="3" placeholder="Write the correct fact or value" required></textarea></label><label>Why, if useful<textarea id="correction-explanation" rows="2" placeholder="Optional context that helps the GM preserve this correction"></textarea></label><button class="btn-primary" type="submit">PREVIEW CORRECTION</button><div id="correction-preview" aria-live="polite"></div></form><h3>Correction history</h3>${corrections.length ? corrections.map((row) => `<article class="correction-card"><header><b>${escapeHtml(row.target || humanLabel(row.type))}</b><span>Turn ${escapeHtml(row.turn ?? 0)}</span></header><p>${escapeHtml(row.fact)}</p>${row.explanation ? `<small>${escapeHtml(row.explanation)}</small>` : ""}</article>`).join("") : '<div class="jrow hint">No player corrections have been needed.</div>'}`;
    $('#correction-type').insertAdjacentHTML('beforeend','<option value="territory">Territory controller (existing borders)</option>');
    $('#correction-type').insertAdjacentHTML('beforeend','<option value="npc_status">Confirmed NPC death (enter dead)</option>');
    panel.insertAdjacentHTML('afterbegin','<details class="correction-card"><summary>Review possible missing campaign records</summary><p>Local evidence search only. Historical gains may have been lost later. Nothing changes until you preview and confirm.</p><button type="button" id="review-campaign-records">CHECK RECENT RECORDS</button><div id="campaign-review-results" aria-live="polite"></div></details>');
    $('#review-campaign-records').onclick = async (event) => {
      event.target.disabled=true;
      try {
        const review=await apiGet('/api/campaign/review');
        const box=$('#campaign-review-results');
        box.innerHTML=(review.candidates || []).map((row,index)=>`<article class="correction-card"><b>${escapeHtml(row.target)}</b><p>${escapeHtml(row.note)}</p><blockquote>${escapeHtml(row.text)}</blockquote><button type="button" data-review-index="${index}">REVIEW THIS RECORD</button></article>`).join('') || '<p>No explicit acquisition statements found in the last 500 records. Use Search Campaign or enter a correction below for other wording.</p>';
        box.querySelectorAll('[data-review-index]').forEach(button=>button.onclick=()=>{
          const row=review.candidates[Number(button.dataset.reviewIndex)];
          $('#correction-type').value=row.type; $('#correction-target').value=row.target;
          $('#correction-value').value=row.value; $('#correction-explanation').value=row.note;
          $('#correction-preview').innerHTML=''; APP.correctionSource={text:row.text,time:`Turn ${row.turn ?? '?'}`};
          $('#gm-correction-form').scrollIntoView({block:'start',behavior:'smooth'});
        });
      } catch(error){showToast(error.message,'danger');}
      finally {event.target.disabled=false;}
    };
  } else if (tab === "simulation") {
    const integrity = data.simulation?.integrity || {}, reports = [...(integrity.recent_validation || [])].reverse();
    const schedules = Object.entries(integrity.npc_schedules || {}), packets = [...(integrity.information_packets || [])].reverse();
    const canon = integrity.canon_dependencies || { counts: {}, events: [] };
    const direction = data.simulation?.campaign_direction || {}, approaching = direction.approaching_canon_event || {};
    panel.innerHTML = `<div class="system-summary"><b>CAMPAIGN DIRECTOR</b><span>Keeps goals, pressures, and opportunities coherent locally without another AI call.</span></div><div class="director-grid"><div><b>Current goal</b><span>${escapeHtml(direction.primary_goal || "Choose a goal")}</span></div><div><b>Next obstacle</b><span>${escapeHtml(direction.next_obstacle || "None confirmed")}</span></div><div><b>Approaching event</b><span>${escapeHtml(approaching.title ? `${approaching.title} · ${approaching.days_until} days` : "No dated event loaded")}</span></div><div><b>Unresolved people</b><span>${escapeHtml((direction.unresolved_characters || []).map((x) => x.name).join(", ") || "None")}</span></div></div><div class="system-summary"><b>LOCAL SIMULATION SAFETY</b><span>These checks run on your computer after the GM writes a turn. They do not make another AI call.</span></div><div class="integrity-stats"><span><b>${escapeHtml(integrity.travel?.nodes || 0)}</b> mapped places</span><span><b>${escapeHtml(integrity.travel?.connections || 0)}</b> travel routes</span><span><b>${escapeHtml((integrity.active_goals || []).length)}</b> active stop goals</span><span><b>${escapeHtml(schedules.length)}</b> NPC schedules</span></div><h3>Recent turn checks</h3>${reports.length ? reports.map((row) => `<details class="integrity-report ${escapeHtml(row.status || "passed")}"><summary><b>Turn ${escapeHtml(row.turn)} · ${escapeHtml(row.status || "passed")}</b><span>${escapeHtml(row.actions_checked || 0)} actions · ${escapeHtml(row.rolls_checked || 0)} rolls</span></summary>${(row.repairs || []).length ? `<p><b>Repaired locally</b></p><ul>${row.repairs.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : ""}${(row.warnings || []).length ? `<p><b>Warnings</b></p><ul>${row.warnings.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : '<p>No mismatch was found.</p>'}</details>`).join("") : '<div class="jrow hint">Resolve a turn to create the first integrity report.</div>'}<h3>Active action goals</h3>${(integrity.active_goals || []).length ? integrity.active_goals.map((row) => `<div class="jrow"><b>${escapeHtml(row.kind || "goal")}</b><br>${escapeHtml(row.condition || row.action)}</div>`).join("") : '<div class="jrow hint">No “until/master/find/reach” goal is currently active.</div>'}<h3>NPC commitments</h3>${schedules.length ? schedules.map(([name,row]) => `<article class="schedule-card"><header><b>${escapeHtml(name)}</b><span>${escapeHtml(row.status || "planned")}</span></header><p>${escapeHtml(row.goal || "Private commitment")}</p><small>${escapeHtml(row.location || "Unknown")} · due around Canon Day ${escapeHtml(row.due_day ?? "?")}</small></article>`).join("") : '<div class="jrow hint">Schedules appear when recurring NPCs establish a real goal.</div>'}<h3>Information in motion</h3>${packets.length ? packets.slice(0,20).map((row) => `<div class="jrow"><b>${escapeHtml(row.fact)}</b><br><small>${escapeHtml(row.channel || "unknown route")} · ${escapeHtml(row.confidence || 0)}% confidence · recipients: ${escapeHtml((row.recipients || []).join(", ") || "none")}${Number(row.available_after_minutes || 0) > 0 ? ` · arrives in ${escapeHtml(row.available_after_minutes)} minutes` : " · delivered"}</small></div>`).join("") : '<div class="jrow hint">No structured news packet has moved yet.</div>'}<h3>Canon dependency health</h3><div class="jrow">${Object.entries(canon.counts || {}).filter(([,v]) => v).map(([k,v]) => `<b>${escapeHtml(v)} ${escapeHtml(k)}</b>`).join(" · ") || "No fixed canon dependencies."}</div>`;
  } else if (tab === "quests") {
    const active = data.quests || [];
    const qp = data.quest_presentation || questPresentation(data.world);
    const line = (label, value) => value ? `<div class="quest-brief-line"><b>${escapeHtml(label)}</b><span>${escapeHtml(value)}</span></div>` : "";
    const list = (label, values, emptyText = "") => values.length ? `<div class="quest-detail-label">${escapeHtml(label)}</div><ul>${values.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : (emptyText ? `<div class="quest-detail-label">${escapeHtml(label)}</div><p>${escapeHtml(emptyText)}</p>` : "");
    const archive = `<h3>${escapeHtml(qp.archive_label)}</h3>${(data.quest_archive || []).length ? data.quest_archive.map((q, i) => { const v = questView(q, i); return `<div class="jrow"><b>${escapeHtml(v.name)}</b> — ${escapeHtml(v.status)}<br>${escapeHtml(v.explanation)}</div>`; }).join("") : '<div class="jrow hint">Nothing has moved into campaign history yet.</div>'}`;
    if (qp.literal) {
      panel.innerHTML = (active.length ? active.map((raw, index) => {
      const q = questView(raw, index);
      const knowledge = q.knowledge.length ? `<div class="quest-detail-label">Discovered clues</div><ul>${q.knowledge.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : `<div class="quest-detail-label">Discovered clues</div><p>Nothing beyond the quest briefing is known yet.</p>`;
      const objectives = q.objectives.length ? `<div class="quest-detail-label">Tracked objectives</div><div class="objective-list">${q.objectives.map((obj) => `<div class="objective-row ${escapeHtml(obj.status || "active")}"><span>${obj.status === "complete" ? "✓" : obj.status === "failed" ? "✕" : obj.status === "locked" ? "◇" : "○"}</span><div><b>${escapeHtml(obj.text || obj.name || "Objective")}</b><small>${escapeHtml(obj.status || "active")}${obj.optional ? " · optional" : ""} · ${escapeHtml(obj.progress || 0)}%</small></div></div>`).join("")}</div>` : (q.conditions.length ? `<div class="quest-detail-label">Clear conditions / objectives</div><ul>${q.conditions.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : `<div class="quest-detail-label">Clear conditions</div><p>Not yet known. Discover more information or advance the quest.</p>`);
      const branches = [...textList(q.branchState.available), ...textList(q.branchState.locked).map((x) => `${x} (locked)` )];
      const branchInfo = q.branchState.current || branches.length ? `<div class="quest-detail-label">Current route</div><p>${escapeHtml(q.branchState.current || "main")}</p>${list("Known branches", branches)}` : "";
      return `<details class="quest-card"${index === 0 ? " open" : ""}><summary>${escapeHtml(q.name)} <small>— ${escapeHtml(q.status)} · ${escapeHtml(q.progress)}%</small></summary><div class="quest-details"><p class="quest-summary">${escapeHtml(q.explanation)}</p><div class="quest-progress"><i style="width:${Math.max(0, Math.min(100, q.progress))}%"></i></div><div class="quest-brief-grid">${line("Giver / cause", q.giver)}${line("Suggested next lead", q.firstStep)}${line("Deadline", q.deadline)}</div>${list("Known locations", q.locations)}${list("Current obstacles", q.risks)}${knowledge}${objectives}${list("Optional objectives", q.optionalObjectives)}${branchInfo}${list("Known rewards", q.rewards)}<div class="quest-note-row"><input type="text" placeholder="Add your own quest note" data-quest-note-input="${escapeHtml(q.name)}"><button type="button" data-quest-note-save="${escapeHtml(q.name)}">SAVE NOTE</button></div></div></details>`;
      }).join("") : `<div class="jrow">${escapeHtml(qp.empty_label)}.</div>`) + `<div class="jrow hint">Hidden quests discovered: ${data.hidden_quests_count}</div>` + archive;
    } else {
      const intro = `<div class="system-summary agenda-intro"><b>${escapeHtml(qp.tab_label.toUpperCase())}</b><span>This records responsibilities, promises, investigations, and developing situations. It follows what happens in the story—not percentages, mandatory steps, or a fixed solution.</span></div>`;
      const cards = active.length ? active.map((raw, index) => {
        const q = questView(raw, index);
        const possible = [...new Set([
          q.firstStep,
          ...textList(q.branchState.available),
        ].filter(Boolean))];
        const openThreads = [...new Set(q.objectives.filter((obj) => obj && obj.status !== "complete" && obj.status !== "failed").map((obj) => obj.text || obj.name).filter(Boolean))];
        const commitments = [...new Set([...q.commitments, ...q.optionalObjectives])];
        const knowledge = list("What you currently know", q.knowledge, "Only the original situation is confirmed so far.");
        return `<details class="quest-card agenda-card"${index === 0 ? " open" : ""}><summary>${escapeHtml(q.name)} <small>— ${escapeHtml(q.status)}</small></summary><div class="quest-details"><div class="quest-detail-label">Situation</div><p class="quest-summary">${escapeHtml(q.explanation)}</p><div class="quest-brief-grid">${line("Responsibility / source", q.giver)}${line("Current direction", q.firstStep)}${line("Time pressure", q.deadline)}</div>${list("Relevant places", q.locations)}${list("Immediate pressures", q.risks)}${knowledge}${list("Threads still in play", openThreads)}${list("Possible approaches", possible, "Choose any approach that makes sense in the story; you are not limited to a listed route.")}${list("Commitments and possibilities", commitments)}${list("Recent developments", q.developments)}<div class="quest-note-row"><input type="text" placeholder="Add your own agenda note" data-quest-note-input="${escapeHtml(q.name)}"><button type="button" data-quest-note-save="${escapeHtml(q.name)}">SAVE NOTE</button></div></div></details>`;
      }).join("") : `<div class="jrow">${escapeHtml(qp.empty_label)}. New responsibilities and leads will appear through play.</div>`;
      panel.innerHTML = intro + cards + archive;
    }
  } else if (tab === "skills") {
    const skills = Object.entries(data.skills || {});
    const titles = data.titles || [];
    const isBleach = data.world === "Bleach";
    const classRow = isBleach ? "" : renderClassCard(data.class_profile);
    const worldProgression = isBleach ? "" : renderWorldProgression(data.world, data.special || {}, data.class_profile || {}, data);
    const kido = skills.filter(([name, detail]) => /^(?:Had[ōo]|Bakud[ōo])\s*#/i.test(name) || (detail && typeof detail === "object" && detail.kido));
    const releases = skills.filter(([name, detail]) => /^(?:Shikai|Bankai)\b/i.test(name) || (detail && typeof detail === "object" && detail.release_stage));
    const foundations = skills.filter((row) => !kido.includes(row) && !releases.includes(row));
    const skillRows = skills.length
      ? skills.map(([name, detail]) => renderSkillCard(name, detail)).join("")
      : '<div class="jrow">No learned skills yet.</div>';
    const titleRows = titles.length
      ? titles.map((title) => `<div class="jrow">🏅 ${escapeHtml(titleLabel(title))}</div>`).join("")
      : '<div class="jrow hint">No titles earned yet.</div>';
    panel.innerHTML = isBleach
      ? `<button id="btn-open-power-summary" class="btn-ghost full">⚔ Power Summary</button><h3>Zanpakutō Releases</h3>${renderBleachReleases(data.special || {})}${renderBleachActivity(data)}<h3>Hadō & Bakudō</h3>${kido.length ? kido.map(([name, detail]) => renderSkillCard(name, detail)).join("") : '<div class="jrow hint">No numbered Kidō learned yet.</div>'}<h3>Soul Reaper Training</h3>${foundations.length ? foundations.map(([name, detail]) => renderSkillCard(name, detail)).join("") : '<div class="jrow hint">No additional training recorded.</div>'}<h3>Titles</h3>${titleRows}`
      : `<button id="btn-open-power-summary" class="btn-ghost full">⚔ Power Summary</button>${worldProgression ? `<h3>World Progression</h3>${worldProgression}` : ""}${classRow && data.world !== "Overgeared" ? `<h3>Class / Path</h3>${classRow}` : ""}<h3>Learned Skills</h3>${skillRows}<h3>Titles</h3>${titleRows}`;
    $("#btn-open-power-summary").addEventListener("click", openPowerSummary);
  } else if (tab === "achievements") {
    const achievements = data.achievements || [];
    const titles = data.titles || [];
    const legacy = data.legacy_trophies || [];
    const achievementView = (entry, index) => {
      const obj = entry && typeof entry === "object" ? entry : {};
      const name = compactReadable(obj.name || obj.title) || (typeof entry === "string" ? entry : `Achievement ${index + 1}`);
      const description = compactReadable(obj.description || obj.notes || obj.summary);
      const when = obj.turn !== undefined && obj.turn !== null ? `Turn ${compactReadable(obj.turn)}` : compactReadable(obj.date);
      return { name, description, when };
    };
    const achievementCards = achievements.length
      ? achievements.map((entry, i) => {
          const v = achievementView(entry, i);
          return `<article class="achievement-card" data-achievement-replay="${escapeHtml(v.name)}" title="Click to replay the unlock moment">
            <span class="achievement-icon">🏆</span>
            <div class="achievement-copy"><b>${escapeHtml(v.name)}</b>${v.description ? `<p>${escapeHtml(v.description)}</p>` : ""}${v.when ? `<small>${escapeHtml(v.when)}</small>` : ""}</div>
          </article>`;
        }).join("")
      : '<div class="jrow hint">No achievements unlocked yet.</div>';
    const titleCards = titles.length
      ? titles.map((t) => `<article class="achievement-card title-card"><span class="achievement-icon">🎖</span><div class="achievement-copy"><b>${escapeHtml(titleLabel(t))}</b></div></article>`).join("")
      : '<div class="jrow hint">No titles earned yet.</div>';
    const legacyCards = legacy.length ? legacy.map((entry) => `<article class="achievement-card legacy-card"><span class="achievement-icon">◆</span><div class="achievement-copy"><b>${escapeHtml(entry.title || "Legacy trophy")}</b>${entry.description ? `<p>${escapeHtml(entry.description)}</p>` : ""}<small>${escapeHtml(entry.category || "Legacy")}</small></div></article>`).join("") : '<div class="jrow hint">No optional trophies have been kept yet.</div>';
    panel.innerHTML = `<h3>Achievements</h3><div class="achievement-grid">${achievementCards}</div><h3>Legacy Trophies</h3><div class="achievement-grid">${legacyCards}</div><h3>Titles Earned</h3><div class="achievement-grid">${titleCards}</div>`;
    $$("[data-achievement-replay]").forEach((card) => card.addEventListener("click", () => {
      const name = card.getAttribute("data-achievement-replay");
      showCinematic("achievement", "ACHIEVEMENT UNLOCKED: " + name);
      playSfx("achievement");
    }));
  } else if (tab === "progression") {
    const logs = (data.progression_log || []).slice(-40).reverse();
    const ledger = (data.progression_ledger || []).slice(-40).reverse();
    const depth = data.world_depth || {};
    const masteryRows = (data.character_paths?.paths || []).map((path) => `<article class="progress-entry mastery-entry${path.pinned ? ' pinned' : ''}"><header><b>${escapeHtml(path.title || path.skill)}</b><span>${escapeHtml(path.stage)} · ${escapeHtml(path.mastery)}%</span></header><div class="clock-track"><i style="width:${Math.max(0, Math.min(100, Number(path.mastery || 0)))}%"></i></div><p>${(path.next_steps || []).map(escapeHtml).join(' · ')}</p><small>Combat refinement: +${escapeHtml(path.upgrades?.combat_bonus || 0)} · Resource efficiency ${escapeHtml(path.upgrades?.resource_efficiency_pct || 0)}%${path.upgrades?.range_bonus?` · Range +${escapeHtml(path.upgrades.range_bonus)}`:''}${path.upgrades?.duration_bonus?` · Duration +${escapeHtml(path.upgrades.duration_bonus)} round`:''}${path.upgrades?.potency_bonus?` · Effect potency +${escapeHtml(path.upgrades.potency_bonus)}%`:''}</small>${(path.mentor_candidates || []).length ? `<small>Known mentors: ${(path.mentor_candidates || []).map(escapeHtml).join(' · ')}</small>` : ''}<button type="button" data-character-path="${escapeHtml(path.pinned ? '' : path.id)}">${path.pinned ? 'Unpin development goal' : 'Pin as development goal'}</button></article>`).join("");
    const pathRows = (depth.progression_paths || []).map((path) => `<details class="progress-entry path-entry"><summary><b>${escapeHtml(path.name || "Development path")}</b><span>${escapeHtml(path.status || "Available")}</span></summary><div><p>${escapeHtml(path.description || "")}</p>${(path.possible_routes || []).length ? `<small>Possible routes — not a required order</small><ul>${path.possible_routes.map((route) => `<li>${escapeHtml(route)}</li>`).join("")}</ul>` : ""}${(path.hard_requirements || []).length ? `<small>True setting requirements</small><ul>${path.hard_requirements.map((requirement) => `<li>${escapeHtml(requirement)}</li>`).join("")}</ul>` : ""}</div></details>`).join("");
    const techniqueRows = (depth.signature_techniques || []).map((technique) => `<details class="progress-entry signature-entry"><summary><b>${escapeHtml(technique.name || "Signature technique")}</b><span>${escapeHtml(technique.stage || "Established")}</span></summary><div>${technique.mechanism ? `<p>${escapeHtml(technique.mechanism)}</p>` : ""}${technique.activation ? `<p><b>Use:</b> ${escapeHtml(technique.activation)}</p>` : ""}${technique.cost ? `<p><b>Cost or limitation:</b> ${escapeHtml(technique.cost)}</p>` : ""}${(technique.counters || []).length ? `<p><b>Counters:</b> ${escapeHtml(technique.counters.join(" · "))}</p>` : ""}${technique.next_milestone ? `<p><b>Possible next step:</b> ${escapeHtml(technique.next_milestone)}</p>` : ""}</div></details>`).join("");
    const ledgerRows = ledger.map((entry) => {
      const changes = (entry.changes || []).map((change) => {
        if (change.before !== undefined && change.after !== undefined) return `<li><b>${escapeHtml(change.name)}</b> ${escapeHtml(change.before)} → ${escapeHtml(change.after)} (${Number(change.delta) >= 0 ? "+" : ""}${escapeHtml(change.delta)})</li>`;
        return `<li><b>${escapeHtml(change.name)}</b> — ${escapeHtml(change.change || "changed")}</li>`;
      }).join("");
      const rolls = (entry.rolls || []).map((roll) => `<li>${escapeHtml(roll)}</li>`).join("");
      const duration = Number(entry.elapsed_minutes || 0) > 0 ? ` · ${escapeHtml(entry.elapsed_minutes)} minutes` : "";
      return `<details class="progress-entry ledger-entry"><summary><b>${escapeHtml(entry.cause || "Progress")}</b><span>Turn ${escapeHtml(entry.turn ?? "—")}${duration}</span></summary><div><ul>${changes}</ul>${rolls ? `<small>Relevant checks</small><ul>${rolls}</ul>` : ""}<p>${escapeHtml(entry.explanation || "Growth followed from the listed actions and outcomes.")}</p></div></details>`;
    }).join("");
    const rows = logs.map((entry) => {
      if (entry && entry.type === "xp") {
        const reasons = (entry.reasons || []).map((reason) => `<li><b>+${escapeHtml(reason.xp || 0)} XP</b> — ${escapeHtml(reason.action || "Progress")}: ${escapeHtml(reason.reason || "Meaningful activity")}</li>`).join("");
        const gains = Object.entries(entry.stat_gains || {}).map(([name, gain]) => `${name} +${gain}`).join(" · ");
        return `<article class="progress-entry xp-entry"><header><b>+${escapeHtml(entry.xp_awarded || 0)} XP</b><span>Turn ${escapeHtml(entry.turn ?? "—")}</span></header>${entry.levels_gained ? `<p class="level-gain">LEVEL UP ×${escapeHtml(entry.levels_gained)}${gains ? ` · ${escapeHtml(gains)}` : ""}</p>` : ""}<ul>${reasons}</ul></article>`;
      }
      const ability = entry && entry.ability ? entry.ability : "Training";
      return `<article class="progress-entry"><header><b>${escapeHtml(ability)}</b><span>${escapeHtml(entry?.effective_training_days ?? "—")} effective days</span></header><p>${escapeHtml(entry?.explanation || "Progress recorded.")}</p>${entry?.stat_gain ? `<small>Stat gain: +${escapeHtml(entry.stat_gain)}</small>` : ""}</article>`;
    }).join("");
    const summary = data.uses_xp
      ? `<div class="progress-summary"><b>LEVEL ${escapeHtml(data.level || 1)}</b><span>${escapeHtml(data.xp || 0)} / ${escapeHtml(data.xp_next || 100)} XP toward the next level</span></div><p class="hint">Meaningful actions earn contextual XP. Base stats increase automatically when XP produces a level.</p>`
      : `<div class="progress-summary"><b>WORLD-BASED GROWTH</b><span>No artificial XP or levels in this setting</span></div><p class="hint">Stats, techniques, knowledge, titles, ranks, and proficiency improve directly through world-valid experience.</p>`;
    panel.innerHTML = summary + `<h3>Character mastery</h3><p class="hint">Pin one established ability as your current development goal. Timed mastery sessions appear in Local activities when a goal is pinned; this does not lock other growth.</p>` + (masteryRows || '<div class="jrow hint">Learn an ability before a mastery path can be tracked.</div>') + `<h3>Flexible development paths</h3><p class="hint">These explain what is possible and what the world truly requires. They are not a mandatory order or locked skill tree.</p>` + (pathRows || '<div class="jrow hint">No world-specific paths are available yet.</div>') + (techniqueRows ? `<h3>Signature techniques</h3>${techniqueRows}` : "") + `<h3>Why your character changed</h3>` + (ledgerRows || '<div class="jrow hint">No lasting growth changes have been recorded yet.</div>') + `<h3>Training and XP history</h3>` + (rows || '<div class="jrow hint">No progression has been recorded yet.</div>');
    panel.querySelectorAll('[data-character-path]').forEach((button) => button.addEventListener('click', async () => {
      try { await apiPost('/api/character-paths/pin', {path_id: button.dataset.characterPath || ''}); showToast(button.dataset.characterPath ? 'Development goal pinned.' : 'Development goal unpinned.', 'notify'); openJournal('progression'); }
      catch (error) { showToast(error.message, 'danger'); }
    }));
  } else if (tab === "chapters") {
    const chapters = [...(data.chapter_summaries || [])].reverse();
    const recent = data.chapter_buffer || [];
    const daysIntoChapter = recent.length ? Math.max(0, Number(data.canon_day ?? 0) - Number(recent[0].canon_day ?? data.canon_day ?? 0)) : 0;
    panel.innerHTML = `<div class="system-summary"><b>CHAPTER MEMORY</b><span>${chapters.length} consolidated chapters · ${daysIntoChapter}/90 days toward the next</span></div>` +
      (chapters.length ? chapters.map((chapter, index) => `<details class="quest-card"${index === 0 ? " open" : ""}><summary>${escapeHtml(chapter.title || `Chapter ${chapter.number}`)} <small>— turns ${escapeHtml((chapter.turns || []).join("–"))}</small></summary><div class="quest-details"><p>${escapeHtml(chapter.narrative_summary || chapter.summary || "")}</p><details class="chapter-source-record"><summary>Detailed record</summary><div class="quest-detail-label">Key decisions</div><ul>${(chapter.key_decisions || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("") || "<li>None recorded.</li>"}</ul><div class="quest-detail-label">Lasting changes</div><ul>${(chapter.lasting_changes || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("") || "<li>None recorded.</li>"}</ul></details><small>${escapeHtml(chapter.time_span || "")}</small></div></details>`).join("") : '<div class="jrow">A chapter is consolidated roughly every 3 in-game months, or sooner if a long stretch passes without much time advancing.</div>');
  } else if (tab === "clocks") {
    const renderClocks = (title, clocks) => `<h3>${title}</h3>` + (Object.values(clocks || {}).length ? Object.values(clocks).map((clock) => {
      // mid_term_goal/core_ambition are optional depth beyond the one
      // immediate_goal/goal line every clock already gets — most won't
      // have them, same as the NPC relationship cards.
      const layers = (clock.mid_term_goal ? `<p><b>Building toward:</b> ${escapeHtml(clock.mid_term_goal)}</p>` : "") +
        (clock.core_ambition ? `<p><b>Deep down wants:</b> ${escapeHtml(clock.core_ambition)}</p>` : "");
      return `<article class="clock-row"><header><b>${escapeHtml(clock.name || "Unknown")}</b><span class="clock-status ${escapeHtml(clock.status || "active")}">${escapeHtml((clock.status || "active").replace(/_/g, " "))}</span></header><p>${escapeHtml(clock.immediate_goal || clock.goal || "Private agenda")}</p>${layers}<div class="clock-track"><i style="width:${Math.max(0, Math.min(100, Number(clock.progress || 0)))}%"></i></div><small>${escapeHtml(clock.progress || 0)} / ${escapeHtml(clock.threshold || 100)} · last moved ${escapeHtml(clock.last_update || "not yet")}</small>${clock.last_cause ? `<small class="causal-reason">Because: ${escapeHtml(clock.last_cause)}</small>` : ""}${clock.blocked_reason ? `<small class="causal-blocked">Blocked: ${escapeHtml(clock.blocked_reason)}</small>` : ""}${clock.opponent ? `<small>⚔ Power ${escapeHtml(clock.power ?? 50)} vs ${escapeHtml(clock.opponent)}${clock.contested_location ? ` over ${escapeHtml(clock.contested_location)}` : ""}</small>` : ""}</article>`;
    }).join("") : '<div class="jrow hint">No visible clocks yet. Important NPCs and factions gain clocks as they enter the campaign.</div>');
    const conflictRows=(data.world_conflict?.operations||[]).map((op)=>`<article class="clock-row conflict-operation"><header><b>${escapeHtml(op.faction)} · ${escapeHtml(op.type || 'operation')}</b><span class="clock-status ${escapeHtml(op.status || 'active')}">${escapeHtml(op.status || 'active')}</span></header><p>${escapeHtml(op.objective || 'Faction operation')}</p><div class="clock-track"><i style="width:${Math.max(0,Math.min(100,Number(op.progress||0)))}%"></i></div><small>${escapeHtml(op.target || 'Unspecified front')} · ${escapeHtml(op.progress || 0)}%</small>${op.recent_outcome?`<small>${escapeHtml(op.recent_outcome)}</small>`:''}</article>`).join('');
    panel.innerHTML = renderClocks("Faction agendas", data.faction_clocks) + `<h3>Active faction operations</h3>${conflictRows || '<div class="jrow hint">No visible strategic operations are active.</div>'}` + renderClocks("NPC agendas", data.npc_clocks);
  } else if (tab === "causality") {
    const recent = [...(data.causality?.recent || [])].reverse();
    const actorRows = [...(data.causality?.factions || []), ...(data.causality?.npcs || [])];
    const sim = data.simulation || {}, profile = sim.profile || { label: "Balanced", description: "Focused world detail" };
    const intentions = Object.entries(sim.intentions || {}), simEvents = [...(sim.recent_events || [])].reverse().slice(0, 20);
    panel.innerHTML = `<div class="system-summary"><b>${escapeHtml(profile.label)} WORLD CAUSALITY</b><span>${escapeHtml(profile.description)} Nearby actors receive full detail; distant actors use compact intentions and clocks.</span></div>` +
      `<h3>Persistent NPC intentions</h3>` + (intentions.length ? intentions.map(([name,row]) => `<article class="causality-card${row.status === "turning_point" ? " blocked" : ""}"><header><b>${escapeHtml(name)}</b><span>${escapeHtml(row.detail || "coarse")} · ${escapeHtml(row.progress || 0)}%</span></header><p>${escapeHtml(row.goal || "Private objective")}</p><small>Next: ${escapeHtml(row.next_action || row.plan || "Continue the plan")}</small><small>Location: ${escapeHtml(row.location || "Unknown")} · ${escapeHtml(row.status || "active")}</small></article>`).join("") : '<div class="jrow hint">Intentions appear after recurring characters establish goals.</div>') +
      `<h3>Current causal actors</h3>` + (actorRows.length ? actorRows.map((row) => `<article class="causality-card${row.blocked_reason ? " blocked" : ""}"><header><b>${escapeHtml(row.name)}</b><span>${escapeHtml(row.status)}</span></header><p>${escapeHtml(row.goal || "No concrete goal recorded.")}</p>${row.target_location ? `<small>Target: ${escapeHtml(row.target_location)}</small>` : ""}${row.last_cause ? `<small>Last cause: ${escapeHtml(row.last_cause)}</small>` : ""}${row.blocked_reason ? `<small class="causal-blocked">Blocked: ${escapeHtml(row.blocked_reason)}</small>` : ""}${Object.keys(row.resources || {}).length ? `<small>Resources: ${Object.entries(row.resources).map(([k,v]) => `${escapeHtml(k)} ${escapeHtml(v)}`).join(" · ")}</small>` : ""}</article>`).join("") : '<div class="jrow hint">No causal actors are active yet.</div>') +
      `<h3>Consolidated event record</h3>` + (simEvents.length ? simEvents.map((row) => `<details class="causality-entry"><summary><b>${escapeHtml(row.summary || "World development")}</b><span>${escapeHtml(row.importance || 0)}/100</span></summary><small>Turn ${escapeHtml(row.turn ?? "?")} · Day ${escapeHtml(row.canon_day ?? "?")} · ${escapeHtml((row.sources || []).join(", "))}</small></details>`).join("") : '<div class="jrow hint">No consolidated events recorded yet.</div>') +
      `<h3>Why the world moved</h3>` + (recent.length ? recent.map((row) => `<details class="causality-entry"><summary><b>${escapeHtml(row.actor)}</b><span>${Number(row.progress_delta) > 0 ? `+${escapeHtml(row.progress_delta)} progress` : "no progress"}</span></summary><p>${escapeHtml(row.goal || "Agenda")}</p>${row.reason ? `<small>Cause: ${escapeHtml(row.reason)}</small>` : ""}${row.blocked_reason ? `<small class="causal-blocked">Blocked: ${escapeHtml(row.blocked_reason)}</small>` : ""}</details>`).join("") : '<div class="jrow hint">No causal progress has been recorded yet.</div>');
  } else if (tab === "knowledge") {
    const people = data.npc_knowledge?.people || [];
    const buckets = [["confirmed","Confirmed"],["heard","Heard from others"],["suspected","Suspected"],["false_beliefs","False beliefs"]];
    panel.innerHTML = `<div class="system-summary"><b>NPC KNOWLEDGE BOUNDARIES</b><span>The narrator knows the campaign; characters act only on what they witnessed, heard, inferred, researched, or falsely believe.</span></div>` +
      (people.length ? people.map((person) => `<details class="knowledge-card"><summary><b>${escapeHtml(person.name)}</b><span>${escapeHtml(person.last_known_location || "Unknown")}</span></summary><div>${buckets.map(([key,label]) => { const rows = person.knowledge?.[key] || []; return `<section><b>${label}</b>${rows.length ? `<ul>${rows.map((row) => `<li>${escapeHtml(row.fact || row)}${row.source ? `<small>Source: ${escapeHtml(row.source)}${row.confidence !== undefined ? ` · ${escapeHtml(row.confidence)}%` : ""}</small>` : ""}</li>`).join("")}</ul>` : '<p class="hint">None recorded.</p>'}</section>`; }).join("")}</div></details>`).join("") : '<div class="jrow hint">No NPC has a structured knowledge record yet.</div>') +
      ((data.npc_knowledge?.recent_audit || []).length ? `<h3>Prevented omniscience</h3>${data.npc_knowledge.recent_audit.slice().reverse().map((row) => `<div class="jrow"><b>${escapeHtml(row.npc)}</b><br>${escapeHtml(row.fact)}<br><small>${escapeHtml(row.reason)}</small></div>`).join("")}` : "");
  } else if (tab === "relationships") {
    const people = data.relationships_view?.people || [];
    const factions = data.relationships_view?.factions || [];
    const affiliations = data.relationships_view?.affiliations || [];
    const npcNetwork = data.relationships_view?.npc_network || [];
    const intentionMap = data.simulation?.intentions || {};
    const publicRep = data.public_reputation || { fame: 0, infamy: 0, identity: "Unknown", jurisdictions: [], history: [] };
    const repRows = (publicRep.jurisdictions || []).map((j) => `<article class="reputation-row"><header><b>${escapeHtml(j.faction)}</b><span>${escapeHtml(j.wanted || "Clear")}</span></header><p>${escapeHtml(j.band || "Unknown")} · standing ${Number(j.standing || 0) >= 0 ? "+" : ""}${escapeHtml(j.standing || 0)} · heat ${escapeHtml(j.heat || 0)}</p><small>Recognition ${escapeHtml(j.recognition || 0)}%</small></article>`).join("");
    panel.innerHTML = `<div class="system-summary"><b>RELATIONSHIPS &amp; FACTIONS</b><span>Trust is evidence, not automatic obedience.</span></div>` +
      `<h3>Affiliations — your rank and standing</h3>` + (affiliations.length ? affiliations.map((a) => `<div class="jrow affiliation-row${a.status && a.status !== "active" ? ` ${escapeHtml(a.status)}` : ""}"><b>${escapeHtml(a.rank || "Member")}</b> — ${escapeHtml(a.faction)}${a.status && a.status !== "active" ? `<span class="affiliation-status">${escapeHtml(a.status)}</span>` : ""}${a.joined ? `<br><small>Joined: ${escapeHtml(a.joined)}</small>` : ""}${a.notes ? `<br><small>${escapeHtml(a.notes)}</small>` : ""}</div>`).join("") : '<div class="jrow hint">Not formally affiliated with any group, alliance, or hierarchy yet.</div>') +
      `<h3>Public profile</h3><div class="public-reputation-summary"><b>${escapeHtml(publicRep.identity || "Unknown")}</b><span>Fame ${escapeHtml(publicRep.fame || 0)} · Infamy ${escapeHtml(publicRep.infamy || 0)}</span><small>Public attention follows recorded witnesses, faction standing, and formal wanted/bounty records; private knowledge does not become reputation automatically.</small></div>${repRows || '<div class="jrow hint">No jurisdiction has developed a public stance toward you yet.</div>'}` +
      `<h3>People</h3>` + (people.length ? people.map((person) => {
        // mid_term_goal/core_ambition are optional depth beyond the one
        // goal line every tracked NPC already gets — most won't have them,
        // so the extra rows only render for characters the GM actually
        // bothered to layer.
        const layers = (person.mid_term_goal ? `<p><b>Building toward:</b> ${escapeHtml(person.mid_term_goal)}</p>` : "") +
          (person.core_ambition ? `<p><b>Deep down wants:</b> ${escapeHtml(person.core_ambition)}</p>` : "");
        const motive = intentionMap[person.name] || {};
        const motiveLines = `${textList(motive.loyalties).length ? `<p><b>Loyalties:</b> ${textList(motive.loyalties).map(escapeHtml).join(" · ")}</p>` : ""}${textList(motive.fears).length ? `<p><b>Known concerns:</b> ${textList(motive.fears).map(escapeHtml).join(" · ")}</p>` : ""}${motive.opinion_of_player ? `<p><b>Opinion of you:</b> ${escapeHtml(motive.opinion_of_player)}</p>` : ""}`;
        return `<details class="relationship-card${person.nemesis ? " nemesis-card" : ""}" data-person-card="${escapeHtml(person.name)}"><summary><button type="button" class="relationship-portrait-choice" data-interact-person="${escapeHtml(person.name)}" title="Choose an interaction with ${escapeHtml(person.name)}" aria-label="Choose an interaction with ${escapeHtml(person.name)}">${personPortraitHtml(person.name, person, { size: "sm" })}</button><b>${person.nemesis ? "⚠ " : ""}${escapeHtml(person.name)}</b><span>${escapeHtml(person.label)} · ${Number(person.score) >= 0 ? "+" : ""}${escapeHtml(person.score)}</span></summary><div><p><b>Goal:</b> ${escapeHtml(person.goal)}</p>${layers}${motiveLines}<p><b>Last known:</b> ${escapeHtml(person.last_known_location)}</p>${textList(person.promises).length ? `<p><b>Promises:</b> ${textList(person.promises).map(escapeHtml).join(" · ")}</p>` : ""}${textList(person.debts).length ? `<p><b>Debts:</b> ${textList(person.debts).map(escapeHtml).join(" · ")}</p>` : ""}${chainHistoryHtml(person.chain)}</div></details>`;
      }).join("") : '<div class="jrow hint">No recurring relationships have been established.</div>') +
      // NPCs relating to each other independent of the player — allies,
      // rivals, grudges the GM has established between two named
      // characters. This is the only place that data is actually visible;
      // without it, tracked NPC-to-NPC dynamics would just be invisible
      // bookkeeping the player has no way to see or reason about.
      `<h3>NPC Network — how they relate to each other</h3>` + (npcNetwork.length ? npcNetwork.map((rel) => {
        const negative = rel.strength < 0;
        return `<div class="jrow npc-network-row"><b>${escapeHtml(rel.a)}</b> <span class="npc-network-type">${escapeHtml(rel.type)}</span> <b>${escapeHtml(rel.b)}</b>
          <span class="npc-network-strength ${negative ? "negative" : "positive"}">${rel.strength > 0 ? "+" : ""}${escapeHtml(rel.strength)}</span>
          ${rel.status && rel.status !== "active" ? `<span class="affiliation-status">${escapeHtml(rel.status)}</span>` : ""}
          ${rel.note ? `<br><small>${escapeHtml(rel.note)}</small>` : ""}</div>`;
      }).join("") : '<div class="jrow hint">No relationships between other characters have been established yet.</div>') +
      `<h3>Faction standing</h3>` + (factions.length ? factions.map((f) => `<div class="jrow"><b>${escapeHtml(f.name)}</b><br>${escapeHtml(typeof f.standing === "object" ? compactReadable(f.standing.label || f.standing.status || f.standing.score) : f.standing)}${chainHistoryHtml(f.chain)}</div>`).join("") : '<div class="jrow hint">No faction reputation has been recorded.</div>');
  } else if (tab === "prerequisites") {
    const tracks = data.prerequisite_tracks || [];
    panel.innerHTML = tracks.length ? tracks.map((track, index) => {
      const status = String(track.status || "in_progress").replace(/_/g, " ");
      const list = (label, values, cls) => `<div class="quest-detail-label ${cls || ""}">${label}</div>` + ((values || []).length ? `<ul>${values.map((v) => `<li>${escapeHtml(v)}</li>`).join("")}</ul>` : `<p class="hint">None recorded.</p>`);
      return `<details class="quest-card prereq-card"${index === 0 ? " open" : ""}><summary>${escapeHtml(track.name || "Capability")} <small class="prereq-status ${escapeHtml(track.status || "")}">— ${escapeHtml(status)}</small></summary><div class="quest-details"><p>${escapeHtml(track.source_feat || "")}</p>${list("Requirements met", track.met_requirements, "met")}${list("Still missing", track.missing_requirements, "missing")}${list("Next steps", track.next_steps, "next")}<div class="quest-detail-label">Notes</div><p>${escapeHtml(track.notes || "No additional notes.")}</p></div></details>`;
    }).join("") : `<div class="jrow"><b>No tracked capability yet.</b><br/>Tell the GM what canon feat, technique, class, item, transformation, or position you want to pursue. The requirements will appear here.</div>`;
  } else if (tab === "timeline") {
    LivingAdventures.timeline(panel, data);
  } else if (tab === "schedule") {
    const events = data.scheduled_events || [];
    panel.innerHTML = events.length ? events.map((event) => `<div class="timeline-row upcoming"><div class="timeline-day">${escapeHtml(event.when || event.day || event.time || "Upcoming")}</div><div><b>${escapeHtml(event.title || event.name || "Scheduled event")}</b><p>${escapeHtml(event.summary || event.description || event.notes || "Known details will develop as the date approaches.")}</p></div></div>`).join("") : '<div class="jrow">No visible deadlines or scheduled events. Hidden events remain hidden until your character could know them.</div>';
  } else if (tab === "continuity") {
    const ledger = data.continuity || {};
    const canon = data.campaign_canon || [];
    const facts = ledger.facts || [];
    const section = (title, values) => `<h3>${title}</h3>${(values || []).length ? values.slice(-30).reverse().map((x) => `<div class="jrow">${escapeHtml(typeof x === "object" ? x.text || x.description || JSON.stringify(x) : x)}</div>`).join("") : '<div class="jrow hint">Nothing recorded.</div>'}`;
    panel.innerHTML = section("Campaign canon", canon) + section("Location changes", facts.filter((x) => x.type === "location")) + section("Appearance changes", facts.filter((x) => x.type === "appearance")) + section("Quest changes", facts.filter((x) => x.type === "quest")) + section("Warnings", ledger.warnings);
  } else if (tab === "memory") {
    const memory = data.narrative_memory || {};
    const memorySection = (title, key, empty) => {
      const rows = (memory[key] || []).slice().reverse();
      return `<section class="memory-section"><h3>${escapeHtml(title)}</h3>${rows.length ? rows.map((row) => `<article class="memory-row"><p>${escapeHtml(typeof row === "object" ? row.text : row)}</p><small>${escapeHtml(typeof row === "object" ? row.source || "Campaign" : "Campaign")}${row?.canon_day != null ? ` · Canon Day ${escapeHtml(row.canon_day)}` : ""}${row?.status ? ` · ${escapeHtml(row.status)}` : ""}</small></article>`).join("") : `<div class="jrow hint">${escapeHtml(empty)}</div>`}</section>`;
    };
    panel.innerHTML = `<div class="system-summary"><b>LONG-TERM NARRATIVE MEMORY</b><span>Campaign facts are separated by purpose so later turns can preserve them without rereading the entire Chronicle.</span></div>` +
      memorySection("Established facts", "established_facts", "No lasting facts recorded yet.") +
      memorySection("Player goals", "player_goals", "No long-term goal recorded yet.") +
      memorySection("Unresolved mysteries", "unresolved_mysteries", "No unresolved mystery recorded yet.") +
      memorySection("Promises", "promises", "No promises recorded yet.") +
      memorySection("Relationships", "relationships", "No recurring relationship recorded yet.") +
      memorySection("Consequences", "consequences", "No lasting consequence recorded yet.");
  } else if (tab === "world-feed") {
    // Split into what the player actually experienced vs. the world moving
    // on its own (NPC/faction clocks, canon beats delivered as background
    // texture rather than lived through) — background_world_feed mirrors
    // the exact same text those specific entries already carry in
    // world_events/timeline, so matching on content is enough to tell them
    // apart without changing the shape either list has always had.
    const entryText = (entry) => typeof entry === "object" ? (entry.text || entry.summary || JSON.stringify(entry)) : entry;
    const renderFeedEntry = (entry) => {
      const text = entryText(entry);
      const kind = typeof entry === "object" ? (entry.type || entry.tag || "World update") : "World update";
      return `<div class="jrow"><b>${escapeHtml(String(kind).replace(/_/g, " "))}</b><br>${escapeHtml(text)}</div>`;
    };
    const backgroundTexts = new Set((data.background_world_feed || []).map(entryText));
    const seen = new Set();
    const personal = [];
    [...(data.world_events || []), ...(data.timeline || [])].forEach((entry) => {
      const text = entryText(entry);
      if (seen.has(text)) return;
      seen.add(text);
      if (!backgroundTexts.has(text)) personal.push(entry);
    });
    const personalRows = personal.slice(-40).reverse().map(renderFeedEntry).join("")
      || '<div class="jrow">No major world updates have reached you yet.</div>';
    const backgroundRows = (data.background_world_feed || []).slice(-40).reverse().map(renderFeedEntry).join("")
      || '<div class="jrow hint">Nothing else has moved independently yet.</div>';
    panel.innerHTML = `<h3>Your Story</h3>${personalRows}<h3>The Wider World</h3><p class="hint">Things happening on their own, whether or not you were there for them.</p>${backgroundRows}`;
  } else if (tab === "codex") {
    const codex = data.codex || [];
    const generated = await apiGet("/api/ability-archive");
    const archivedRows = (generated.entries || []).slice().reverse().map((row) => {
      const ability = row.package || {};
      const effect = ability.effect || ability.description || ability.governing_rule || ability.shikai_effect || ability.enhancement || ability.details?.effect || "Original mechanics recorded for later reference.";
      return `<details class="ability-archive-row"><summary><b>${escapeHtml(row.name || "Original ability")}</b><span>${escapeHtml(row.world)} · ${escapeHtml(humanLabel(row.category || "ability"))}</span></summary><p>${escapeHtml(effect)}</p><small>${escapeHtml(row.created_at || "")}</small></details>`;
    }).join("") || `<div class="jrow hint">No original abilities have been generated for this account yet.</div>`;
    const codexRows = codex.length ? codex.map((c) => `<div class="jrow"><b>${escapeHtml(c.name || "Entry")}</b> <i>${escapeHtml(c.type || "")}</i><br/>${escapeHtml(c.notes || "")}</div>`).join("") : `<div class="jrow">No campaign codex entries yet.</div>`;
    panel.innerHTML = `${codexRows}<h3>Original Ability Archive</h3><p class="hint">Every non-canon ability, hidden class, Zanpakutō, and JJK birth-slot design this account has seen is saved here. Rerolls exclude the entire archive.</p>${archivedRows}`;
  } else if (tab === "inventory") {
    const inv = data.inventory || [];
    const eq = data.equipment || {};
    const currencyRows = data.tracks_currency === false ? [] : [currencyRowHtml(data.currency.name, data.currency.amount, data.currency)]
      .concat(Object.entries(data.currencies || {}).map(([k, v]) => currencyRowHtml(k, v && typeof v === "object" ? v.amount : v, v && typeof v === "object" ? { ...v, name: k } : null)));
    const activeDebts = (data.finance_debts || []).filter((row) => row && row.active !== false && Number(row.amount || 0) > 0);
    const debtRows = activeDebts.map((row) => `<div class="finance-debt-row"><span><b>${escapeHtml(row.label || "Outstanding obligation")}</b><small>${escapeHtml(Number(row.amount || 0).toLocaleString(undefined, { maximumFractionDigits: 4 }))} ${escapeHtml(row.currency || data.currency?.name || "Currency")} due</small></span><button type="button" data-debt-pay="${escapeHtml(row.id || "")}">Pay what you can</button></div>`).join("");
    const ledgerRows = (data.currency_ledger || []).slice(-12).reverse().map((row) => {
      const amount = Number(row.amount || 0);
      return `<div class="finance-ledger-row"><span class="${amount >= 0 ? "income" : "expense"}">${amount >= 0 ? "+" : ""}${escapeHtml(amount.toLocaleString(undefined, { maximumFractionDigits: 4 }))} ${escapeHtml(row.currency || "")}</span><span>${escapeHtml(row.reason || "Money changed hands")}</span></div>`;
    }).join("");
    const financeRows = data.tracks_currency === false ? "" : `${debtRows ? `<h3>Outstanding obligations</h3>${debtRows}` : ""}<details class="finance-history"><summary>Money history</summary>${ledgerRows || '<div class="jrow hint">No transactions recorded yet.</div>'}</details>`;
    const bagRows = inv.length ? inv.map((i) => {
      if (!i || typeof i !== "object") return `<div class="jrow">${escapeHtml(i)}</div>`;
      const effects = textList(i.effects || i.effect), limits = textList(i.restrictions || i.restriction);
      return `<article class="inventory-detail-card"><header><b>${escapeHtml(i.name || "Item")}</b><span>${escapeHtml(i.rating || i.grade || i.category || "Item")}</span></header>${effects.length ? `<p>${escapeHtml(effects.join(" · "))}</p>` : ""}${limits.length ? `<small>Limits: ${escapeHtml(limits.join(" · "))}</small>` : ""}${i.source || i.creator ? `<small>${escapeHtml(i.source || `Created by ${i.creator}`)}</small>` : ""}</article>`;
    }).join("") : `<div class="jrow">Bag is empty.</div>`;
    if (data.gear_style === "full") {
      panel.innerHTML = currencyRows.join("") + financeRows + buildMannequinHtml(eq) + bagRows;
      wireMannequinTooltips();
    } else {
      panel.innerHTML = currencyRows.join("") + financeRows + bagRows +
        (Object.keys(eq).length ? `<div class="jrow"><b>Weapon</b><br/>${Object.entries(eq).map(([k, v]) => `${escapeHtml(k)}: ${escapeHtml(v)}`).join("<br/>")}</div>` : "");
    }
  } else if (tab === "shops") {
    const shops = data.shops || [];
    const currency = data.currency || { name: "Currency", amount: 0 };
    const tracksCurrency = data.tracks_currency !== false;
    const shopBlocks = shops.length ? shops.map((sh) => {
      if (typeof sh !== "object" || !sh) return `<div class="jrow">${escapeHtml(sh)}</div>`;
      const inventory = Array.isArray(sh.inventory) ? sh.inventory : (Array.isArray(sh.items) ? sh.items : []);
      const itemRows = inventory.length ? inventory.map((it) => {
        const itemObj = (it && typeof it === "object") ? it : { name: it };
        const name = itemObj.name || itemObj.item || String(it);
        const price = parsePriceClient(itemObj.price ?? itemObj.cost ?? itemObj.value);
        const priceCurrency = itemObj.currency || itemObj.currency_name || itemObj.price_currency || currency.name;
        const canAfford = price != null && currencyBalanceClient(data, priceCurrency) >= price;
        const priceLabel = tracksCurrency ? (price != null ? `${escapeHtml(price)} ${escapeHtml(priceCurrency)}` : "price unclear") : escapeHtml(itemObj.access || "Narrative access");
        return `<div class="shop-item-row"><span class="shop-item-name">${escapeHtml(name)}</span><span class="shop-item-price">${priceLabel}</span>` +
          (tracksCurrency && price != null ? `<button type="button" class="shop-buy-btn" data-shop-buy="${escapeHtml(sh.name || "")}" data-shop-item="${escapeHtml(name)}"${canAfford ? "" : " disabled"}>Buy</button>` : "") +
          `</div>`;
      }).join("") : `<div class="shop-item-row muted">No priced inventory listed here yet.</div>`;
      return `<div class="jrow shop-block"><b>${escapeHtml(sh.name || "Shop")}</b><small>${escapeHtml(sh.type || "Merchant")}</small>${itemRows}</div>`;
    }).join("") : `<div class="jrow">${data.shop_types.map((t) => "• " + t).join("<br/>")}</div>`;
    const accessNote = tracksCurrency ? currencyRowHtml(currency.name, currency.amount, currency) : `<div class="system-summary"><b>SUPPLY ACCESS</b><span>This world handles routine equipment through rank, authorization, favors, requisitions, availability, or story events instead of a permanent money balance.</span></div>`;
    const economy = data.property_economy || { properties: [], work_orders: [], market: {} };
    const propertyRows = (economy.properties || []).map((p) => `<article class="property-card"><header><b>${escapeHtml(p.name)}</b><span>${escapeHtml(humanLabel(p.type || "property"))} · ${escapeHtml(p.location)}</span></header><p>Treasury: ${escapeHtml(p.treasury || 0)} ${escapeHtml(currency.name)}</p><small>${escapeHtml((p.facilities_readable || []).join(" · ") || "No facility upgrades yet")}</small></article>`).join("");
    const orderRows = (economy.work_orders || []).slice().reverse().map((o) => `<div class="jrow"><b>${escapeHtml(o.recipe)}</b> — ${escapeHtml(o.status)}<br><small>${escapeHtml((economy.properties || []).find(p => p.id === o.property_id)?.name || "Workshop")}</small></div>`).join("");
    const economyPanel = `<h3>Property & local economy</h3><div class="system-summary"><b>${escapeHtml((economy.market?.condition || "stable").toUpperCase())} MARKET</b><span>${escapeHtml(economy.market?.location || data.location || "Current location")} · price index ×${escapeHtml(economy.market?.price_multiplier || 1)}</span><small>Conflict, route conditions, and local public standing influence current market prices. Property proceeds accrue locally and must be collected there.</small></div>${propertyRows || '<div class="jrow hint">You do not own a tracked property yet. Available purchases and upgrades appear under Living Map → Local activities.</div>'}${orderRows ? `<h3>Production orders</h3>${orderRows}` : ""}`;
    panel.innerHTML = accessNote + shopBlocks + economyPanel +
      `<div class="jrow"><b>Training Focus</b><br/>${data.training_options.map(escapeHtml).join(", ")}</div>` +
      (Object.keys(data.ability_progress || {}).length ? `<div class="jrow"><b>Progress</b><br/>${Object.entries(data.ability_progress).map(([k, v]) => `${escapeHtml(k)}: ${escapeHtml(v)}`).join("<br/>")}</div>` : "");
  } else if (tab === "map") {
    const mapPayload = data.map_data || {};
    const boards = Array.isArray(mapPayload.boards) ? mapPayload.boards : [];
    const selectionKey = `${data.world || s.world || "World"}:${APP.mapBoardSelection || ""}`;
    const selectedBoard = boards.find((board) => selectionKey.endsWith(`:${board.name}`))
      || boards.find((board) => board.name === mapPayload.active_board) || boards[0];
    const nodes = selectedBoard?.nodes || mapPayload.nodes || [];
    const regions = selectedBoard?.regions || mapPayload.regions || [];
    const mapImage = selectedBoard?.image || data.map_image || "";
    const mapMeta = mapPayload.meta || {};
    const travelGraph = data.travel_graph || { edges: {} };
    const knownCount = nodes.filter((node) => node.discovered).length;
    const legendChips = groupNodesByController(regions.length ? regions : nodes).map((t) => `<span class="territory-chip" style="--tc:${t.color}"><i></i>${escapeHtml(t.controller)}</span>`).join("");
    const boardPicker = boards.length ? `<label class="map-board-picker"><span>Realm map</span><select id="map-board-select">${boards.map((board) => `<option value="${escapeHtml(board.name)}"${board.name === selectedBoard?.name ? " selected" : ""}>${escapeHtml(board.name)}${board.name === mapPayload.active_board ? " · current realm" : ""}</option>`).join("")}</select></label>` : "";
    panel.innerHTML = `<div class="map-heading"><div><span class="map-kicker">${escapeHtml(mapMeta.projection || "POLITICAL ATLAS")}</span><b>${escapeHtml(selectedBoard?.name || data.world || s.world || "World")}</b><small>${nodes.length} important landmarks · ${knownCount} visited or discovered</small></div>${boardPicker}<div class="map-legend"><span class="current">Current</span><span class="known">Discovered</span><span class="unknown">Known landmark</span></div></div>` +
      (legendChips ? `<div class="territory-legend">${legendChips}</div>` : "") +
      `<div class="map-layout"><div class="map-wrap" id="map-wrap"><div class="map-canvas" id="map-canvas" data-map-render="strategic" style="--map-image:url('${escapeHtml(mapImage)}')"><canvas class="map-territories" id="map-territory-canvas"></canvas><canvas class="map-routes" id="map-route-canvas"></canvas><div class="map-faction-labels" id="map-faction-labels" aria-hidden="true"></div><div id="map-ambient" class="map-ambient" aria-hidden="true"></div></div><div class="map-zoom-controls"><button type="button" data-map-zoom-in title="Zoom in" aria-label="Zoom in">+</button><button type="button" data-map-zoom-out title="Zoom out" aria-label="Zoom out">−</button><button type="button" data-map-zoom-reset title="Reset view" aria-label="Reset map view">⤾</button></div></div><aside class="map-detail" id="map-detail"><b>Select a landmark</b><p>${escapeHtml(mapMeta.accuracy_note || "Territory is shown as one clean strategy layer. Borders repaint when the story changes ownership.")}</p><small>Drag to pan. Scroll or use the controls to zoom.${boards.length ? " Switching realms changes only this view." : ""}</small></aside></div>`;
    const boardSelect = $("#map-board-select");
    if (boardSelect) boardSelect.addEventListener("change", () => { APP.mapBoardSelection = boardSelect.value; openJournal("map"); });
    const canvas = $("#map-canvas");
    const territoryData = regions.length ? regions : nodes;
    const territoryLayout = paintMapTerritories($("#map-territory-canvas"), territoryData);
    paintMapRoutes($("#map-route-canvas"), nodes, travelGraph);
    renderMapFactionLabels($("#map-faction-labels"), territoryLayout, nodes);
    applyNativeMapFx(nodes);
    nodes.forEach((node) => {
      const dot = document.createElement("button");
      dot.type = "button";
      const majorKinds = new Set(["capital", "city", "village", "nation", "region", "realm", "island"]);
      const major = majorKinds.has(String(node.kind || "").toLowerCase());
      dot.className = "map-node " + (node.current ? "here" : node.discovered ? "known" : "unknown") + (major ? " map-major" : "") + (node.danger_level ? " danger-" + node.danger_level.toLowerCase() : "") + (node.recently_changed ? " territory-changed" : "") + ((node.contested_by?.length || node.conflict_operations?.length) ? " territory-contested" : "");
      dot.style.left = node.x + "%"; dot.style.top = node.y + "%";
      dot.title = `${node.name} · ${node.kind || "landmark"} · Tier ${node.tier ?? "?"}${node.controller && node.controller !== "Unknown" ? ` · Controlled by ${node.controller}` : ""}${node.danger_level ? ` · ${node.danger_level} danger` : ""}${node.recently_changed ? " · Control recently changed" : ""}${node.contested_by?.length ? ` · Contested by ${node.contested_by.join(', ')}` : ""}`;
      dot.setAttribute("data-map-node", node.name);
      dot.innerHTML = `<span class="map-pip"></span><span class="map-label">${escapeHtml(node.name)}</span>`;
      canvas.appendChild(dot);
    });
    APP.mapNodes = nodes;
    APP.mapRegions = regions;
    APP.travelGraph = travelGraph;
    initMapPanZoom();
  } else if (tab === "lore") {
    const sources = data.lore_sources || [];
    const conflicts = data.lore_status?.conflicts || [];
    const auto = data.lore_automation || {settings:{}, sources:[], due:0};
    const aset = auto.settings || {};
    panel.innerHTML = `<div class="system-summary"><b>AUTHORITY-RANKED LORE LIBRARY</b><span>Pages are extracted and indexed locally. Routine updates use no AI calls; conflicting evidence is authority-ranked and only enters an already-needed GM prompt when relevant.</span></div><form id="lore-auto-form" class="lore-auto-form"><label class="lore-toggle"><input id="lore-auto-enabled" type="checkbox" ${aset.enabled ? "checked" : ""}><span><b>Automatic source refresh</b><small>Check approved sources when the game starts and they are due.</small></span></label><label>Refresh interval<select id="lore-auto-interval"><option value="7" ${Number(aset.interval_days)===7?"selected":""}>Weekly</option><option value="30" ${Number(aset.interval_days)!==7&&Number(aset.interval_days)!==90?"selected":""}>Monthly</option><option value="90" ${Number(aset.interval_days)===90?"selected":""}>Every 3 months</option></select></label><label class="lore-toggle"><input id="lore-auto-discovery" type="checkbox" ${aset.discover_related_pages ? "checked" : ""}><span><b>Bounded related-page discovery</b><small>Same website only, at most ${escapeHtml(aset.max_pages_per_refresh || 8)} queued pages per refresh.</small></span></label><button class="btn-primary" type="submit">SAVE</button><button class="btn-ghost" type="button" data-lore-refresh>REFRESH DUE NOW</button><small class="hint">${escapeHtml(auto.sources?.length || 0)} approved source(s) for this world · ${escapeHtml(auto.due || 0)} due · 0 dedicated AI calls per routine refresh.</small></form><form id="lore-url-form" class="lore-import"><label>Add or update an approved URL<input id="lore-url" type="url" placeholder="https://…" required></label><select id="lore-url-type"><option value="official_source">Official source</option><option value="official_reference">Official reference</option><option value="wiki" selected>Wiki</option><option value="forum">Forum</option><option value="fan_analysis">Fan analysis</option></select><button class="btn-primary" type="submit">UPDATE LIBRARY</button><label class="lore-toggle lore-source-options"><input id="lore-url-auto" type="checkbox" checked><span>Keep refreshed</span></label><label class="lore-toggle lore-source-options"><input id="lore-url-discover" type="checkbox"><span>Discover related pages</span></label></form><form id="lore-import-form" class="lore-import"><label>Add a lore pack<input id="lore-file" type="file" accept=".json,.md,.txt" required></label><select id="lore-world"><option>${escapeHtml(data.world || "Custom World")}</option><option>Custom World</option></select><button class="btn-primary" type="submit">IMPORT</button></form>` +
      (sources.length ? sources.map((source) => `<div class="jrow"><b>${escapeHtml(source.name)}</b><br>${escapeHtml(source.kind)} · authority ${escapeHtml(source.authority || 0)}/100 · ${escapeHtml(source.entries || 0)} entries${source.source_types?.length ? ` · ${source.source_types.map(escapeHtml).join(", ")}` : source.source_type ? ` · ${escapeHtml(source.source_type)}` : ""}${source.worlds?.length ? ` · ${source.worlds.map(escapeHtml).join(", ")}` : ""}</div>`).join("") : '<div class="jrow">Only built-in setting guidance is available.</div>') +
      `<h3>Source conflicts</h3>` + (conflicts.length ? conflicts.map((row) => `<details class="lore-conflict"><summary><b>${escapeHtml(row.claim)}</b><span>Resolved at ${escapeHtml(row.authority)}/100</span></summary><p>${escapeHtml(row.resolution)}</p><small>Preferred source: ${escapeHtml(row.source)} (${escapeHtml(row.source_type)})</small><ul>${(row.alternatives || []).map((alt) => `<li>Disputed: ${escapeHtml(alt.value)} — ${escapeHtml(alt.source)} (${escapeHtml(alt.authority)}/100)</li>`).join("")}</ul></details>`).join("") : '<div class="jrow hint">No explicit claim conflicts detected for this world.</div>') +
      `<p class="hint">JSON entries may include title, keys, text, source, source_type, citation, and claims. Source types: official_source, official_reference, licensed_reference, curated, wiki, forum, fan_analysis, imported, or custom.</p>`;
  } else if (tab === "tuning") {
    const t = data.difficulty_controls || {};
    const preset = data.progression_preset || {};
    const slider = (key, label, min, max, step, value, suffix = "×") => `<label class="tuning-row"><span><b>${label}</b><small id="${key}-value">${escapeHtml(value)}${suffix}</small></span><input type="range" id="${key}" min="${min}" max="${max}" step="${step}" value="${escapeHtml(value)}"></label>`;
    panel.innerHTML = `<div class="system-summary"><b>${escapeHtml(preset.label || "WORLD PROGRESSION")}</b><span>Separate controls change pacing and danger without rewriting lore.</span></div><form id="tuning-form" class="tuning-form">${slider("check_warning_threshold", "Difficult-check warning threshold", 40, 95, 1, t.check_warning_threshold || 65, "/100")}${slider("xp_rate", "XP rate", .5, 2, .05, t.xp_rate || 1)}${slider("training_rate", "Training rate", .5, 2, .05, t.training_rate || 1)}${slider("breakthrough_rate", "Breakthrough frequency", .5, 2, .05, t.breakthrough_rate || 1)}${slider("combat_danger", "Combat danger", .5, 2, .05, t.combat_danger || 1)}${slider("resource_pressure", "Resource pressure", .5, 2, .05, t.resource_pressure || 1)}<label class="tuning-notes-row"><span><b>Director's Notes</b><small>A standing note to the GM — tone, pacing, what to lean into or away from.</small></span><textarea id="director_notes" maxlength="500" placeholder="e.g. more politics and less combat; slow down on romance subplots">${escapeHtml(data.director_notes || "")}</textarea></label><button class="btn-primary" type="submit">SAVE TUNING</button></form>`;
  } else if (tab === "health") {
    const health = data.campaign_health || { score: 100, status: "Healthy", issues: [], counts: {} };
    panel.innerHTML = `<div class="health-score ${health.score < 60 ? "bad" : health.score < 85 ? "warn" : "good"}"><strong>${escapeHtml(health.score)}</strong><div><b>${escapeHtml(health.status)}</b><span>Campaign structure, knowledge, causality, and continuity check</span></div></div><div class="health-actions"><button type="button" class="btn-primary" data-health-repair="safe_all">APPLY ALL SAFE REPAIRS</button><button type="button" class="btn-ghost" data-support-bundle>DOWNLOAD SUPPORT ZIP</button></div><div class="health-counts">${Object.entries(health.counts || {}).map(([key, value]) => `<span><b>${escapeHtml(value)}</b>${escapeHtml(humanLabel(key))}</span>`).join("")}</div>` +
      ((health.issues || []).length ? health.issues.map((issue) => `<article class="health-issue ${escapeHtml(issue.severity)}"><header><b>${escapeHtml(issue.area)}</b><span>${escapeHtml(issue.severity)}</span></header><p>${escapeHtml(issue.message)}</p><small>${escapeHtml(issue.suggestion)}</small>${issue.repairable ? `<button type="button" class="health-repair-btn" data-health-repair="${escapeHtml(issue.repair_id)}">REPAIR THIS</button>` : ""}</article>`).join("") : '<div class="jrow"><b>No structural problems detected.</b><br>The campaign has objectives, continuity, causal world state, and enough persistent memory to continue cleanly.</div>');
  } else if (tab === "evaluations") {
    const scenarios = data.evaluations?.scenarios || [];
    const history = data.evaluations?.history || [];
    panel.innerHTML = `<div class="system-summary"><b>SIMULATION CORE CHECK</b><span>Runs deterministic checks in every world. It makes no AI calls, costs nothing, and never changes a campaign.</span><button type="button" class="btn-primary" data-eval-local>RUN FREE CORE CHECK</button></div><div class="system-summary"><b>LIVE NARRATOR EVALUATIONS</b><span>These isolated scenarios call AI models but never change the campaign. Each model/scenario pair uses one AI call and may incur its normal cost.</span></div><div class="evaluation-actions"><button type="button" class="btn-primary" data-eval-run="all">RUN ALL ${scenarios.length}</button><label class="evaluation-compare"><span>Compare models on the same scenarios</span><input id="evaluation-models" placeholder="gpt-5-mini, gpt-5.4-mini" value="${escapeHtml((data.evaluation_models || []).join(", "))}"><small>Two to five model IDs. This can make several paid calls.</small></label><button type="button" class="btn-ghost" data-eval-compare>COMPARE ON ALL SCENARIOS</button></div><div class="evaluation-grid">${scenarios.map((row) => `<article class="evaluation-card"><header><b>${escapeHtml(row.name)}</b><span>${escapeHtml(row.world)}</span></header><p>${escapeHtml(row.action)}</p><button type="button" class="btn-ghost" data-eval-run="${escapeHtml(row.id)}">RUN THIS SCENARIO</button></article>`).join("")}</div><h3>Recent reports</h3><div id="evaluation-result">${history.length ? history.map((row) => `<div class="jrow"><b>${escapeHtml(row.score)}/100 · ${escapeHtml(row.model || "Unknown model")}</b><br>${escapeHtml(row.scenario_count)} scenario(s) · ${escapeHtml(row.created_at || "")}</div>`).join("") : '<div class="jrow hint">No live model evaluation has been run yet.</div>'}</div>`;
  } else if (tab === "combat") {
    const c = data.combat || {};
    if (!c || !c.active) {
      panel.innerHTML = `<div class="jrow">No active structured combat.</div><div class="jrow hint">Use the Combat panel in the right column once a fight starts — it's not part of this Journal.</div>`;
    } else {
      const e = c.enemy || {};
      panel.innerHTML = `<div class="jrow">Round: ${escapeHtml(c.round ?? 1)}</div><div class="jrow">${escapeHtml(e.name || "Enemy")} — HP ${escapeHtml(e.hp ?? "?")}/${escapeHtml(e.hp_max ?? "?")}${e.is_group ? " (group)" : ""}</div>`;
    }
  }
}

// ---------------------------------------------------------------------------
// Political territory uses a single non-overlapping strategy grid. Each cell
// can have exactly one controller. Same-owner neighbors share no border, so
// annexations visibly join instead of stacking translucent blobs.
// ---------------------------------------------------------------------------
const MAP_FACTION_PALETTE = [
  "#d95b53", "#d4a43d", "#397fc1", "#735fc6", "#3f9c8e", "#b96aab",
  "#8da54a", "#cf754d", "#5a9eb4", "#9a6cbe", "#b77b42", "#6b9f62",
];
function factionHash(name) {
  let hash = 2166136261;
  for (let i = 0; i < String(name).length; i++) { hash ^= String(name).charCodeAt(i); hash = Math.imul(hash, 16777619); }
  return hash >>> 0;
}

function renderOrganizationRoster(roster) {
  const former = new Set(["left", "retired", "dead", "deceased", "expelled"]);
  const memberRow = member => {
    const power = member.power || {};
    const facts = [member.notes, member.reason, member.terms ? `Agreement: ${compactReadable(member.terms)}` : "", member.loyalty_basis ? `Loyalty: ${compactReadable(member.loyalty_basis)}` : "", member.independent ? "Independent ally—not under your command." : "", member.mentor ? `Mentor: ${member.mentor}` : "",
      Array.isArray(member.parents) && member.parents.length ? `Family: ${member.parents.join(", ")}` : ""].filter(Boolean);
    return `<article class="roster-member" role="listitem">
      <div class="roster-person">${personPortraitHtml(member.name, member, { size: "md" })}<span class="roster-person-copy"><strong>${escapeHtml(member.name)}${member.player ? ' <small>You</small>' : ''}</strong><span>${escapeHtml(member.status === "active" ? "Member" : humanLabel(member.status))}${member.age !== "" && member.age != null ? ` · Age ${escapeHtml(member.age)}` : ''}${member.stage ? ` · ${escapeHtml(member.stage)}` : ''}</span></span></div>
      <div class="roster-position"><span class="roster-mobile-label">Position</span><b>${escapeHtml(member.position || "Member")}</b>${member.unit ? `<small>${escapeHtml(member.unit)}</small>` : ''}${member.reports_to ? `<small>Reports to ${escapeHtml(member.reports_to)}</small>` : ''}</div>
      <div class="roster-power"><span class="roster-mobile-label">Combat power</span><b>${escapeHtml(power.label || "Not assessed")}</b><span>${power.score != null ? `${power.estimated ? '≈ ' : ''}${escapeHtml(power.score)} · ` : ''}${escapeHtml(power.source || "No recorded benchmark")}</span></div>
      ${facts.length ? `<details class="roster-member-notes"><summary>Member record</summary>${facts.map(f=>`<p>${escapeHtml(f)}</p>`).join('')}</details>` : ''}
    </article>`;
  };
  if (!roster.groups?.length) return `<section class="organization-roster"><h2>${escapeHtml(roster.label || "Your group")}</h2><p>No group membership is established yet. Recruit, join or form a group through the Chronicle; meeting someone alone does not add them to your roster.</p></section>`;
  return roster.groups.map(group => {
    const current = group.members.filter(member => !former.has(member.status) && member.status !== "candidate");
    const previous = group.members.filter(member => former.has(member.status));
    const candidates = group.members.filter(member => member.status === "candidate");
    return `<section class="organization-roster"><header class="roster-heading"><span>${escapeHtml(group.type)}</span><h2>${escapeHtml(group.name)}</h2><p>${current.length} members${group.leader ? ` · Led by ${escapeHtml(group.leader)}` : ''}</p>${group.successor ? `<p>Agreed successor: ${escapeHtml(group.successor)}</p>` : ''}</header>
      <p class="roster-caption">All members, including those away. ≈ marks estimated combat power.</p>
      <div class="roster-column-labels" aria-hidden="true"><span>Member</span><span>Position</span><span>Combat power</span></div>
      <div role="list" aria-label="${escapeHtml(group.name)} members">${current.map(memberRow).join('') || '<p>No current members are recorded.</p>'}</div>
      ${candidates.length ? `<details class="roster-history"><summary>Invitations & applicants (${candidates.length})</summary><div role="list">${candidates.map(memberRow).join('')}</div></details>` : ''}
      ${previous.length ? `<details class="roster-history"><summary>Former members & legacy (${previous.length})</summary><div role="list">${previous.map(memberRow).join('')}</div></details>` : ''}
      ${group.history?.length ? `<details class="roster-history"><summary>Group history</summary>${group.history.slice().reverse().map(event=>`<p><b>${escapeHtml(event.name)}</b> · ${escapeHtml(humanLabel(event.event))}<br>${escapeHtml(event.reason)}</p>`).join('')}</details>` : ''}
    </section>`;
  }).join('');
}
function factionColorMap(names) {
  const colors = new Map(), used = new Set();
  [...new Set(names)].sort((a, b) => a.localeCompare(b)).forEach((name) => {
    let slot = factionHash(name) % MAP_FACTION_PALETTE.length;
    for (let attempts = 0; attempts < MAP_FACTION_PALETTE.length && used.has(slot); attempts++) slot = (slot + 1) % MAP_FACTION_PALETTE.length;
    used.add(slot);
    colors.set(name, MAP_FACTION_PALETTE[slot]);
  });
  return colors;
}
function factionColor(name) {
  return MAP_FACTION_PALETTE[factionHash(name) % MAP_FACTION_PALETTE.length];
}
function groupNodesByController(nodes) {
  const byFaction = {};
  nodes.forEach((n) => {
    const controller = n.controller;
    if (!controller || controller === "Unknown" || controller === "Unclaimed") return;
    (byFaction[controller] = byFaction[controller] || []).push(n);
  });
  const controllers = Object.keys(byFaction).sort((a, b) => a.localeCompare(b));
  const colors = factionColorMap(controllers);
  return controllers.map((controller) => ({ controller, color: colors.get(controller) }));
}
function mapHash(value) {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i++) { hash ^= value.charCodeAt(i); hash = Math.imul(hash, 16777619); }
  return (hash >>> 0) / 4294967295;
}
function mapPointInPolygon(x, y, polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = Number(polygon[i][0]), yi = Number(polygon[i][1]);
    const xj = Number(polygon[j][0]), yj = Number(polygon[j][1]);
    const crosses = ((yi > y) !== (yj > y)) && (x < ((xj - xi) * (y - yi)) / ((yj - yi) || .00001) + xi);
    if (crosses) inside = !inside;
  }
  return inside;
}
function mapHexPath(ctx, cx, cy, radius) {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const angle = Math.PI / 180 * (30 + i * 60);
    const x = cx + radius * Math.cos(angle), y = cy + radius * Math.sin(angle);
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.closePath();
}
function paintMapRoutes(canvas, nodes, graph) {
  if (!canvas) return;
  const rect = canvas.parentElement.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);
  const nodeByName = new Map((nodes || []).map((node) => [node.name, node]));
  const seen = new Set();
  const routes = [];
  Object.entries(graph?.edges || {}).forEach(([from, edges]) => {
    const a = nodeByName.get(from);
    if (!a || !a.discovered) return;
    (edges || []).forEach((edge) => {
      const b = nodeByName.get(edge.to);
      if (!b || !b.discovered) return;
      const key = [from, edge.to].sort().join("|");
      if (seen.has(key)) return;
      seen.add(key);
      routes.push({ a, b, restricted: Boolean(edge.requirement) });
    });
  });
  ctx.lineCap = "round";
  routes.forEach(({ a, b, restricted }, index) => {
    const ax = Number(a.x) / 100 * width, ay = Number(a.y) / 100 * height;
    const bx = Number(b.x) / 100 * width, by = Number(b.y) / 100 * height;
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    const bend = (mapHash(`${a.name}:${b.name}`) - .5) * .16;
    const mx = (ax + bx) / 2 - (by - ay) * bend;
    const my = (ay + by) / 2 + (bx - ax) * bend;
    ctx.quadraticCurveTo(mx, my, bx, by);
    ctx.setLineDash(restricted ? [3, 5] : [8, 7]);
    ctx.lineDashOffset = -(index % 7);
    ctx.strokeStyle = restricted ? "rgba(240,186,106,.38)" : "rgba(220,240,244,.32)";
    ctx.lineWidth = restricted ? 1.1 : 1.35;
    ctx.stroke();
  });
  canvas.dataset.routeCount = String(routes.length);
}
function renderMapFactionLabels(layer, layout, nodes = []) {
  if (!layer) return;
  layer.innerHTML = "";
  const landmarkNames = new Set(nodes.map((node) => String(node.name || "").trim().toLowerCase()));
  (layout?.labels || []).forEach((label) => {
    if (label.cells < 5 || landmarkNames.has(String(label.controller).trim().toLowerCase())) return;
    const node = document.createElement("span");
    node.className = "map-faction-label";
    node.style.left = `${label.x}%`; node.style.top = `${label.y}%`; node.style.setProperty("--fc", label.color);
    node.textContent = label.controller;
    layer.appendChild(node);
  });
}
function paintMapTerritories(canvas, nodes) {
  if (!canvas) return;
  const owners = nodes.filter((n) => n.controller && n.controller !== "Unknown" && n.controller !== "Unclaimed");
  const WIDTH = 640, HEIGHT = 400, HEX = 7.2;
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, WIDTH, HEIGHT);
  if (!owners.length) return { labels: [] };
  const controllers = [...new Set(owners.map((n) => n.controller))].sort((a, b) => a.localeCompare(b));
  const colors = factionColorMap(controllers);
  const dx = Math.sqrt(3) * HEX, dy = 1.5 * HEX;
  const rowCount = Math.ceil(HEIGHT / dy) + 1, colCount = Math.ceil(WIDTH / dx) + 1;
  const cells = [], byKey = new Map();
  for (let row = -1; row < rowCount; row++) {
    for (let col = -1; col < colCount; col++) {
      const cx = col * dx + (row & 1 ? dx / 2 : 0), cy = row * dy;
      if (cx < -HEX || cy < -HEX || cx > WIDTH + HEX || cy > HEIGHT + HEX) continue;
      const px = cx / WIDTH * 100, py = cy / HEIGHT * 100;
      let winner = null, winnerScore = Infinity;
      owners.forEach((region, index) => {
        if (Number(region.hex_count) > 0) return;
        const polygon = Array.isArray(region.polygon) && region.polygon.length >= 3 ? region.polygon : null;
        const radius = Math.max(4, Math.min(42, Number(region.size) || 12));
        const rx = Number(region.x) || 50, ry = Number(region.y) || 50;
        const distance = Math.hypot((px - rx) * 1.04, py - ry);
        const score = distance / radius;
        const edgeNoise = (mapHash(`${region.id || region.name}:${row}:${col}`) - .5) * .16;
        const claimed = polygon ? mapPointInPolygon(px, py, polygon) : score <= 1.04 + edgeNoise;
        if (claimed && score < winnerScore) { winner = { region, index }; winnerScore = score; }
      });
      const cell = { row, col, cx, cy, winner, controller: winner?.region.controller || null };
      cells.push(cell); byKey.set(`${row}:${col}`, cell);
    }
  }
  // Narratively founded or explicitly resized holdings use an exact number
  // of cells. A new player claim is therefore visibly one hex, not a fuzzy
  // radius that happens to cover half the map; later state updates can grow
  // it by increasing hex_count.
  owners.filter((region) => Number(region.hex_count) > 0)
    .sort((a, b) => Number(Boolean(a.player_founded)) - Number(Boolean(b.player_founded)))
    .forEach((region) => {
      const count = Math.max(1, Math.min(cells.length, Math.floor(Number(region.hex_count) || 1)));
      const rx = Number(region.x) || 50, ry = Number(region.y) || 50;
      const nearest = [...cells].sort((a, b) => {
        const ad = Math.hypot(a.cx / WIDTH * 100 - rx, a.cy / HEIGHT * 100 - ry);
        const bd = Math.hypot(b.cx / WIDTH * 100 - rx, b.cy / HEIGHT * 100 - ry);
        return ad - bd || a.row - b.row || a.col - b.col;
      }).slice(0, count);
      const index = owners.indexOf(region);
      nearest.forEach((cell) => {
        cell.winner = { region, index };
        cell.controller = region.controller;
      });
    });
  // Paint opaque cells to a separate wash, then composite that entire layer
  // once. This avoids darker alpha accumulation along internal cell edges.
  const wash = document.createElement("canvas");
  wash.width = WIDTH; wash.height = HEIGHT;
  const washCtx = wash.getContext("2d");
  cells.forEach((cell) => {
    if (!cell.controller) return;
    mapHexPath(washCtx, cell.cx, cell.cy, HEX + .62);
    washCtx.fillStyle = colors.get(cell.controller); washCtx.fill();
  });
  ctx.save(); ctx.globalAlpha = .20; ctx.drawImage(wash, 0, 0); ctx.restore();
  const neighborForEdge = (cell, edge) => {
    const odd = Boolean(cell.row & 1), r = cell.row, c = cell.col;
    const keys = odd
      ? [[r + 1, c + 1], [r + 1, c], [r, c - 1], [r - 1, c], [r - 1, c + 1], [r, c + 1]]
      : [[r + 1, c], [r + 1, c - 1], [r, c - 1], [r - 1, c - 1], [r - 1, c], [r, c + 1]];
    return byKey.get(`${keys[edge][0]}:${keys[edge][1]}`);
  };
  // Only political borders are visible. Internal cells disappear, while
  // adjacent holdings with the same controller become one continuous realm.
  cells.forEach((cell) => {
    if (!cell.controller) return;
    for (let edge = 0; edge < 6; edge++) {
      if (neighborForEdge(cell, edge)?.controller === cell.controller) continue;
      const a = Math.PI / 180 * (30 + edge * 60), b = Math.PI / 180 * (30 + ((edge + 1) % 6) * 60);
      ctx.beginPath(); ctx.moveTo(cell.cx + HEX * Math.cos(a), cell.cy + HEX * Math.sin(a));
      ctx.lineTo(cell.cx + HEX * Math.cos(b), cell.cy + HEX * Math.sin(b));
      ctx.lineCap = "round";
      ctx.strokeStyle = "rgba(1,4,8,.82)";
      ctx.lineWidth = cell.winner?.region.recently_changed ? 5 : 3.8;
      ctx.stroke();
      ctx.strokeStyle = cell.winner?.region.recently_changed ? "rgba(255,220,116,.98)" : colors.get(cell.controller);
      ctx.lineWidth = cell.winner?.region.recently_changed ? 2.7 : 1.65;
      ctx.stroke();
    }
    if ((cell.winner?.region.contested_by || []).length) {
      ctx.save(); mapHexPath(ctx, cell.cx, cell.cy, HEX - .4); ctx.clip();
      ctx.strokeStyle = "rgba(255,255,255,.30)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(cell.cx - HEX, cell.cy + HEX * .7); ctx.lineTo(cell.cx + HEX, cell.cy - HEX * .7); ctx.stroke();
      ctx.restore();
    }
  });
  const totals = {};
  cells.forEach((cell) => {
    if (!cell.controller) return;
    const total = totals[cell.controller] ||= { controller: cell.controller, x: 0, y: 0, cells: 0, color: colors.get(cell.controller) };
    total.x += cell.cx / WIDTH * 100; total.y += cell.cy / HEIGHT * 100; total.cells++;
  });
  return { labels: Object.values(totals).map((row) => ({ ...row, x: row.x / row.cells, y: row.y / row.cells })) };
}

// ---------------------------------------------------------------------------
// Map pan/zoom — drag to pan, wheel or the on-screen buttons to zoom.
// Percent-based node/territory positions are untouched; only map-canvas's
// CSS transform changes, so everything already on it stays in sync for free.
// ---------------------------------------------------------------------------
let mapView = { scale: 1, x: 0, y: 0, dragging: false, lastX: 0, lastY: 0 };
function applyMapView() {
  const canvas = $("#map-canvas");
  if (canvas) canvas.style.transform = `translate(${mapView.x}px, ${mapView.y}px) scale(${mapView.scale})`;
  const shell = $("#living-map-main"), pill = $("#map-view-pill");
  const band = mapView.scale >= 2.2 ? "local" : mapView.scale >= 1.35 ? "regional" : "world";
  if (shell) shell.dataset.zoomBand = band;
  if (pill) pill.textContent = `${band.toUpperCase()} VIEW`;
}
function clampMapPan(wrap) {
  if (!wrap) return;
  const w = wrap.clientWidth, h = wrap.clientHeight;
  const scaledW = w * mapView.scale, scaledH = h * mapView.scale;
  const slackX = Math.max(0, (scaledW - w) / 2) + w * 0.4;
  const slackY = Math.max(0, (scaledH - h) / 2) + h * 0.4;
  mapView.x = Math.max(-slackX, Math.min(slackX, mapView.x));
  mapView.y = Math.max(-slackY, Math.min(slackY, mapView.y));
}
function setMapZoom(wrap, newScale, cx, cy) {
  const clamped = Math.max(0.6, Math.min(4, newScale));
  mapView.x = cx - ((cx - mapView.x) / mapView.scale) * clamped;
  mapView.y = cy - ((cy - mapView.y) / mapView.scale) * clamped;
  mapView.scale = clamped;
  clampMapPan(wrap);
  applyMapView();
}
function focusMapPoint(wrap, xPercent, yPercent, scale) {
  if (!wrap) return;
  const targetScale = Math.max(.6, Math.min(4, Number(scale) || 2.2));
  mapView.scale = targetScale;
  mapView.x = wrap.clientWidth / 2 - (Number(xPercent) / 100) * wrap.clientWidth * targetScale;
  mapView.y = wrap.clientHeight / 2 - (Number(yPercent) / 100) * wrap.clientHeight * targetScale;
  clampMapPan(wrap);
  applyMapView();
}
function initMapPanZoom() {
  // #map-wrap is a fresh DOM element every time this tab renders (its
  // parent's innerHTML was just replaced), so listeners are re-attached
  // fresh each time too — the old element and its listeners are simply
  // garbage collected together.
  mapView = { scale: 1, x: 0, y: 0, dragging: false, lastX: 0, lastY: 0 };
  applyMapView();
  const wrap = $("#map-wrap");
  if (!wrap) return;
  wrap.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".map-node")) return;
    mapView.dragging = true; mapView.lastX = e.clientX; mapView.lastY = e.clientY;
    wrap.classList.add("dragging");
    wrap.setPointerCapture(e.pointerId);
  });
  wrap.addEventListener("pointermove", (e) => {
    if (!mapView.dragging) return;
    mapView.x += e.clientX - mapView.lastX; mapView.y += e.clientY - mapView.lastY;
    mapView.lastX = e.clientX; mapView.lastY = e.clientY;
    clampMapPan(wrap);
    applyMapView();
  });
  const endDrag = () => { mapView.dragging = false; wrap.classList.remove("dragging"); };
  wrap.addEventListener("pointerup", endDrag);
  wrap.addEventListener("pointercancel", endDrag);
  wrap.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = wrap.getBoundingClientRect();
    setMapZoom(wrap, mapView.scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e.clientX - rect.left, e.clientY - rect.top);
  }, { passive: false });
}
$("#journal-panel").addEventListener("click", (event) => {
  const wrap = $("#map-wrap");
  if (!wrap) return;
  const rect = wrap.getBoundingClientRect(), cx = rect.width / 2, cy = rect.height / 2;
  if (event.target.closest("[data-map-zoom-in]")) setMapZoom(wrap, mapView.scale * 1.3, cx, cy);
  else if (event.target.closest("[data-map-zoom-out]")) setMapZoom(wrap, mapView.scale / 1.3, cx, cy);
  else if (event.target.closest("[data-map-zoom-reset]")) { mapView.scale = 1; mapView.x = 0; mapView.y = 0; applyMapView(); }
});


$("#journal-panel").addEventListener("input", (event) => {
  if (!event.target.matches(".tuning-row input")) return;
  const out = document.getElementById(event.target.id + "-value");
  if (out) out.textContent = event.target.value + (event.target.id === "check_warning_threshold" ? "/100" : "×");
});

$("#journal-panel").addEventListener("submit", async (event) => {
  if (event.target.id === "campaign-search-form") {
    event.preventDefault();
    const query = $("#campaign-search-query").value.trim();
    if (query.length < 2) return;
    const target = $("#campaign-search-results");
    target.innerHTML = '<div class="jrow hint">Searching this campaign…</div>';
    try {
      const result = await apiGet(`/api/campaign/search?q=${encodeURIComponent(query)}`);
      target.innerHTML = result.results?.length ? result.results.map((row) => `<article class="search-result"><header><b>${escapeHtml(row.title || humanLabel(row.kind))}</b><span>${escapeHtml(humanLabel(row.kind))}${row.turn != null ? ` · Turn ${escapeHtml(row.turn)}` : ""}</span></header><p>${escapeHtml(row.text || "")}</p></article>`).join("") : `<div class="jrow">No campaign record matched “${escapeHtml(query)}”.</div>`;
    } catch (error) { target.innerHTML = `<div class="jrow">${escapeHtml(error.message)}</div>`; }
  } else if (event.target.id === "gm-correction-form") {
    event.preventDefault();
    const payload = { type: $("#correction-type").value, target: $("#correction-target").value.trim(), value: $("#correction-value").value.trim(), explanation: $("#correction-explanation").value.trim(), source: APP.correctionSource || null };
    try {
      const preview = await apiPost("/api/campaign/correct/preview", payload);
      const box = $("#correction-preview");
      box.innerHTML = `<div class="correction-card"><h3>Review your correction</h3><p>${escapeHtml(preview.fact)}</p>${preview.changes.length ? preview.changes.map((change) => `<details><summary>${escapeHtml(humanLabel(change.field))}</summary><p>Before:</p><pre class="correction-value-diff">${escapeHtml(correctionReadable(change.before))}</pre><p>After:</p><pre class="correction-value-diff">${escapeHtml(correctionReadable(change.after))}</pre></details>`).join("") : '<p>This records a story fact; it does not alter stats or inventory.</p>'}<button type="button" class="btn-primary" id="btn-apply-preview">APPLY THIS CORRECTION</button></div>`;
      $("#btn-apply-preview").addEventListener("click", async (click) => {
        click.target.disabled = true;
        try {
          const result = await apiPost("/api/campaign/correct", { ...payload, preview_token: preview.preview_token });
          APP.correctionSource = null;
          renderState(result.state); appendStoryEntries(result.story || []);
          showToast("Correction saved as an authoritative campaign fact.", "notify");
          await openJournal("corrections");
        } catch (error) { showToast(error.message, "danger"); click.target.disabled = false; }
      });
      event.target.addEventListener("input", () => { box.innerHTML = ""; }, { once: true });
    } catch (error) { showToast(error.message, "danger"); }
  } else if (event.target.id === "tuning-form") {
    event.preventDefault();
    const keys = ["check_warning_threshold", "xp_rate", "training_rate", "breakthrough_rate", "combat_danger", "resource_pressure"];
    const payload = Object.fromEntries(keys.map((key) => [key, Number(document.getElementById(key).value)]));
    payload.director_notes = document.getElementById("director_notes").value;
    try { const result = await apiPost("/api/campaign/tuning", payload); APP.state = result.state; showToast("Campaign tuning saved.", "notify"); }
    catch (error) { showToast(error.message, "danger"); }
  } else if (event.target.id === "lore-url-form") {
    event.preventDefault();
    const button = event.target.querySelector("button"); button.disabled = true;
    try {
      await apiPost("/api/lore/update-url", {url: $("#lore-url").value, source_type: $("#lore-url-type").value, world: APP.state?.world || "Custom World", auto_refresh: $("#lore-url-auto").checked, discover: $("#lore-url-discover").checked});
      showToast("Lore source updated and cached locally.", "notify"); await openJournal("lore");
    } catch (e) { showToast(e.message, "danger"); button.disabled = false; }
  } else if (event.target.id === "lore-auto-form") {
    event.preventDefault();
    try {
      await apiPost("/api/lore/automation", {enabled: $("#lore-auto-enabled").checked, interval_days: Number($("#lore-auto-interval").value), discover_related_pages: $("#lore-auto-discovery").checked, recommended_sources:true, world: APP.state?.world || "Custom World"});
      showToast("Automatic lore coverage settings saved.", "notify"); await openJournal("lore");
    } catch (error) { showToast(error.message, "danger"); }
  } else if (event.target.id === "lore-import-form") {
    event.preventDefault();
    const file = $("#lore-file").files[0];
    if (!file) return;
    const form = new FormData(); form.append("file", file); form.append("world", $("#lore-world").value);
    try { await apiForm("/api/lore/import", form); showToast("Lore pack imported.", "notify"); await openJournal("lore"); }
    catch (error) { showToast(error.message, "danger"); }
  }
});

$("#journal-panel").addEventListener("click", async (event) => {
  const loreRefresh = event.target.closest("[data-lore-refresh]");
  if (loreRefresh) {
    loreRefresh.disabled = true;
    try {
      const result = await apiPost("/api/lore/refresh", {force:false, world: APP.state?.world || "Custom World"});
      const report = result.refresh || {};
      showToast(`Lore refresh: ${report.updated || 0} updated, ${report.unchanged || 0} unchanged${report.failed ? `, ${report.failed} failed` : ""}.`, report.failed ? "danger" : "notify");
      await openJournal("lore");
    } catch (error) { showToast(error.message, "danger"); loreRefresh.disabled = false; }
    return;
  }
  const repairButton = event.target.closest("[data-health-repair]");
  if (repairButton) {
    repairButton.disabled = true;
    try {
      const result = await apiPost("/api/campaign/health/repair", { repair_id: repairButton.getAttribute("data-health-repair") });
      renderState(result.state);
      showToast((result.repair?.applied || []).length ? result.repair.applied.join(" ") : "No safe repair was needed.", "notify");
      await openJournal("health");
    } catch (error) { showToast(error.message, "danger"); repairButton.disabled = false; }
    return;
  }
  if (event.target.closest("[data-support-bundle]")) {
    downloadEndpoint("/api/diagnostics/bundle");
    return;
  }
  const localEvalButton = event.target.closest("[data-eval-local]");
  if (localEvalButton) {
    localEvalButton.disabled = true;
    localEvalButton.textContent = "CHECKING EVERY WORLD";
    try {
      const report = await apiPost("/api/evaluations/local", {});
      const target = $("#evaluation-result");
      if (target) target.innerHTML = `<div class="evaluation-score"><strong>${escapeHtml(report.score)}/100</strong><div><b>Free simulation-core check</b><span>${escapeHtml(report.passed)}/${escapeHtml(report.total)} checks · 0 AI calls · $0.00</span></div></div>` + (report.worlds || []).map((row) => `<details class="evaluation-result"><summary><b>${escapeHtml(row.world)}</b><span>${escapeHtml(row.passed)}/${escapeHtml(row.total)}</span></summary>${Object.entries(row.checks || {}).map(([name, passed]) => `<div><b>${passed ? "PASS" : "FAIL"} — ${escapeHtml(name.replaceAll("_", " "))}</b></div>`).join("")}</details>`).join("");
      showToast(`Free simulation check finished at ${report.score}/100.`, report.score === 100 ? "notify" : "danger");
    } catch (error) { showToast(error.message, "danger"); }
    finally { localEvalButton.disabled = false; localEvalButton.textContent = "RUN FREE CORE CHECK"; }
    return;
  }
  const evalButton = event.target.closest("[data-eval-run]");
  if (evalButton) {
    const key = evalButton.getAttribute("data-eval-run");
    evalButton.disabled = true;
    evalButton.textContent = "RUNNING — THE CAMPAIGN WILL NOT CHANGE";
    try {
      const index = await apiGet("/api/evaluations");
      const scenarioIds = key === "all" ? (index.scenarios || []).map((row) => row.id) : [key];
      const report = await apiPost("/api/evaluations/run", { scenario_ids: scenarioIds });
      const target = $("#evaluation-result");
      if (target) target.innerHTML = `<div class="evaluation-score"><strong>${escapeHtml(report.score)}/100</strong><div><b>${escapeHtml(report.model || "Configured model")}</b><span>${escapeHtml(report.results?.length || 0)} isolated scenario(s) · ${escapeHtml(report.usage?.calls || 0)} AI call(s)</span></div></div>` + (report.results || []).map((row) => `<details class="evaluation-result"><summary><b>${escapeHtml(row.name)}</b><span>${escapeHtml(row.score)}/100</span></summary>${(row.criteria || []).map((item) => `<div><b>${escapeHtml(item.name)} — ${escapeHtml(item.score)}/${escapeHtml(item.max)}</b><p>${escapeHtml(item.detail)}</p></div>`).join("")}${row.error ? `<p class="causal-blocked">${escapeHtml(row.error)}</p>` : ""}</details>`).join("");
      showToast(`Model evaluation finished at ${report.score}/100. The campaign was not changed.`, "notify");
    } catch (error) { showToast(error.message, "danger"); }
    finally { evalButton.disabled = false; evalButton.textContent = key === "all" ? "RUN ALL" : "RUN THIS SCENARIO"; }
    return;
  }
  const compareButton = event.target.closest("[data-eval-compare]");
  if (compareButton) {
    const models = String($("#evaluation-models")?.value || "").split(",").map((x) => x.trim()).filter(Boolean);
    compareButton.disabled = true;
    compareButton.textContent = "COMPARING — CAMPAIGN WILL NOT CHANGE";
    try {
      const index = await apiGet("/api/evaluations");
      const comparison = await apiPost("/api/evaluations/compare", { models, scenario_ids: (index.scenarios || []).map((row) => row.id) });
      const target = $("#evaluation-result");
      if (target) target.innerHTML = `<div class="evaluation-ranking"><h3>Same-scenario ranking</h3>${(comparison.ranking || []).map((row) => `<div class="jrow"><b>#${escapeHtml(row.rank)} ${escapeHtml(row.model)} — ${escapeHtml(row.score)}/100</b><br>${escapeHtml(row.duration_seconds)}s · ${escapeHtml(row.calls)} calls · $${Number(row.cost_usd || 0).toFixed(4)}</div>`).join("")}</div>`;
      showToast("Model comparison complete. The campaign was not changed.", "notify");
    } catch (error) { showToast(error.message, "danger"); }
    finally { compareButton.disabled = false; compareButton.textContent = "COMPARE ON ALL SCENARIOS"; }
    return;
  }
  const noteButton = event.target.closest("[data-quest-note-save]");
  if (noteButton) {
    const name = noteButton.getAttribute("data-quest-note-save");
    const input = Array.from(document.querySelectorAll("[data-quest-note-input]")).find((x) => x.getAttribute("data-quest-note-input") === name);
    if (!input?.value.trim()) return;
    try { await apiPost("/api/quests/note", { name, note: input.value.trim() }); input.value = ""; showToast("Quest note saved.", "notify"); }
    catch (error) { showToast(error.message, "danger"); }
    return;
  }
  const buyButton = event.target.closest("[data-shop-buy]");
  if (buyButton) {
    if (buyButton.disabled) return;
    buyButton.disabled = true;
    const shop = buyButton.getAttribute("data-shop-buy");
    const item = buyButton.getAttribute("data-shop-item");
    try {
      const result = await apiPost("/api/shop/buy", { shop, item });
      showToast(result.message, "notify");
      const refreshed = await apiGet("/api/state");
      APP.campaignActive = refreshed.campaign_active;
      renderState(refreshed.state);
      await openJournal("shops");
    } catch (error) {
      showToast(error.message, "danger");
      buyButton.disabled = false;
    }
    return;
  }
  const debtButton = event.target.closest("[data-debt-pay]");
  if (debtButton) {
    debtButton.disabled = true;
    try {
      const result = await apiPost("/api/finance/debt/pay", { id: debtButton.getAttribute("data-debt-pay") });
      showToast(result.message, "notify");
      const refreshed = await apiGet("/api/state");
      APP.campaignActive = refreshed.campaign_active;
      renderState(refreshed.state);
      await openJournal("inventory");
    } catch (error) {
      showToast(error.message, "danger");
      debtButton.disabled = false;
    }
    return;
  }
  const nodeButton = event.target.closest("[data-map-node]");
  if (nodeButton) {
    const node = (APP.mapNodes || []).find((row) => row.name === nodeButton.getAttribute("data-map-node"));
    if (!node) return;
    const detail = $("#map-detail");
    const people = (node.notable_individuals || []).map((person) => typeof person === "object" ? person : { name: person });
    const links = APP.travelGraph?.edges?.[node.name] || [];
    const peopleRow = people.length ? `<div class="location-people" aria-label="Known people here">${people.slice(0, 4).map((person) => { const name = person.name || person.display_name || "Unknown"; return `<span>${personPortraitHtml(name, person, { size: "sm" })}<b>${escapeHtml(name)}</b></span>`; }).join("")}${people.length > 4 ? `<small>+${people.length - 4} more</small>` : ""}</div>` : "None recorded yet";
    detail.innerHTML = `<b>${escapeHtml(node.name)}</b><small>${escapeHtml(node.kind || "landmark")} · tier ${escapeHtml(node.tier || 1)}${node.current ? " · current location" : ""}</small><p>${escapeHtml(node.notes)}</p><dl><dt>Control</dt><dd>${escapeHtml(node.controller)}</dd>${node.danger_level ? `<dt>Danger</dt><dd class="danger-label danger-${escapeHtml(node.danger_level.toLowerCase())}">${escapeHtml(node.danger_level)}</dd>` : ""}<dt>Known people here</dt><dd>${peopleRow}</dd><dt>Quest links</dt><dd>${node.quests?.length ? node.quests.map(escapeHtml).join(", ") : "None known"}</dd><dt>Direct routes</dt><dd>${links.length ? links.map((x) => `${escapeHtml(x.to)} (${escapeHtml(formatDuration(x.minutes))})`).join("<br>") : "No direct route recorded"}</dd></dl><div id="map-route-preview" class="map-route-preview">Calculating route from your current location…</div>`;
    try {
      const route = await apiGet(`/api/travel/route?destination=${encodeURIComponent(node.name)}`);
      const preview = $("#map-route-preview");
      if (preview) preview.innerHTML = route.reachable ? `<b>Route from ${escapeHtml(route.origin)}</b><p>${(route.route || []).map(escapeHtml).join(" → ")}</p><small>Ordinary travel: about ${escapeHtml(formatDuration(route.minutes))}${(route.requirements || []).length ? ` · Needs: ${route.requirements.map(escapeHtml).join("; ")}` : ""}</small>` : `<b>No established route</b><p>${escapeHtml(route.reason || "This destination is not connected yet.")}</p>`;
    } catch (error) { /* The static landmark details remain useful offline. */ }
    return;
  }
});

// Delegated from document (not #story-feed) because that container gets
// replaced when the campaign view mounts — same reason .codex-term clicks
// above are delegated from document instead of a specific ancestor.
document.addEventListener("click", async (event) => {
  const buyButton = event.target.closest("[data-offer-buy]");
  if (!buyButton) return;
  if (buyButton.disabled) return;
  buyButton.disabled = true;
  const id = buyButton.getAttribute("data-offer-buy");
  try {
    const result = await apiPost("/api/purchase_offer/buy", { id });
    showToast(result.message, "notify");
    buyButton.textContent = "Bought";
    const card = buyButton.closest(".story-purchase-offer");
    if (card) card.classList.add("resolved");
    const refreshed = await apiGet("/api/state");
    APP.campaignActive = refreshed.campaign_active;
    renderState(refreshed.state);
  } catch (error) {
    showToast(error.message, "danger");
    buyButton.disabled = false;
  }
});

// ---------------------------------------------------------------------------
// New Campaign modal
// ---------------------------------------------------------------------------
function fillSelect(sel, values, selected) {
  const safeValues = Array.isArray(values) ? values : [];
  sel.innerHTML = safeValues.map((v) => `<option value="${escapeHtml(v)}"${v === selected ? " selected" : ""}>${escapeHtml(v)}</option>`).join("");
}

let ncCharacterStash = null;

function refreshCampaignWorldFields() {
  ncCharacterStash = null;
  const world = $("#nc-world").value;
  const worlds = (APP.worldsMeta && APP.worldsMeta.worlds) || {};
  const wd = worlds[world];
  if (!wd) throw new Error(`World data for "${world || "unknown"}" is missing. Restart this updated build.`);
  const origins = Array.isArray(wd.origins) && wd.origins.length ? wd.origins : ["Local Resident"];
  const archetypes = Array.isArray(wd.archetypes) && wd.archetypes.length ? wd.archetypes : ["Adventurer"];
  $("#nc-tagline").textContent = wd.tagline || "Begin a new story in this world.";
  fillSelect($("#nc-origin"), origins, origins[0]);
  fillSelect($("#nc-archetype"), archetypes, archetypes[0]);
  const isJjk = world === "Jujutsu Kaisen";
  const isHxh = world === "Hunter x Hunter";
  const isOnePiece = world === "One Piece";
  const isOvergeared = world === "Overgeared";
  $("#nc-archetype-field").hidden = isJjk;
  $("#nc-jjk-options").hidden = !isJjk;
  $("#nc-hxh-options").hidden = !isHxh;
  $("#nc-one-piece-options").hidden = !isOnePiece;
  $("#nc-overgeared-options").hidden = !isOvergeared;
  if (isJjk) $("#nc-archetype").innerHTML = '<option value="Jujutsu Sorcerer">Jujutsu Sorcerer</option>';
  $("#nc-custom-label").style.opacity = world === "Custom World" ? "1" : ".45";
  const abilities = wd.abilities || ["Strength", "Dexterity", "Constitution", "Intelligence", "Wisdom", "Charisma"];
  $("#nc-stats").innerHTML = abilities.map((k) => `<div><label>${abilityIcon(k)} ${escapeHtml(k)}</label><input type="number" min="-20" max="200" value="0" data-stat="${escapeHtml(k)}" title="Adjustment added to the generated world-relative value" /></div>`).join("");

  const startOpts = wd.start_options || [];
  const startWrap = $("#nc-start-wrap");
  startWrap.querySelector("label").textContent = world === "Jujutsu Kaisen" ? "Starting Placement" : "Starting Location";
  if (startOpts.length) {
    if (world === "One Piece") {
      const recommended = new Set(["Foosha Village", "Shells Town", "Baratie", "Loguetown", "Water 7"]);
      const eastBlue = new Set(["Goa Kingdom", "Shimotsuki Village", "Orange Town", "Syrup Village", "Cocoyasi Village", "Arlong Park"]);
      const government = new Set(["Marineford", "Impel Down", "Baltigo", "Mary Geoise", "Enies Lobby"]);
      const otherBlues = new Set(["Kano Country", "Sorbet Kingdom", "Germa Kingdom"]);
      const newWorld = new Set(["Dressrosa", "Totto Land", "Zou", "Wano Country", "Egghead Island", "Punk Hazard"]);
      const category = (o) => recommended.has(o.location) ? "Recommended" : eastBlue.has(o.location) ? "East Blue" :
        government.has(o.location) ? "Government & Revolution" : otherBlues.has(o.location) ? "Other Blues" :
        newWorld.has(o.location) ? "New World" : "Grand Line & Sky";
      const labels = ["Recommended", "East Blue", "Grand Line & Sky", "Government & Revolution", "Other Blues", "New World"];
      $("#nc-start").innerHTML = labels.map((label) => {
        const options = startOpts.map((o, i) => category(o) === label ? `<option value="${i}">${escapeHtml(o.label)}</option>` : "").join("");
        return options ? `<optgroup label="${escapeHtml(label)}">${options}</optgroup>` : "";
      }).join("");
    } else {
      $("#nc-start").innerHTML = startOpts.map((o, i) => `<option value="${i}">${escapeHtml(o.label)}</option>`).join("");
    }
    startWrap.style.display = "";
  } else {
    $("#nc-start").innerHTML = "";
    startWrap.style.display = "none";
  }
  const characters = wd.playable_characters || [];
  $("#nc-character-mode").innerHTML = '<option value="">Original Character</option>' + characters.map((c) => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.label || c.name)}</option>`).join("");
  $("#nc-character-note").textContent = characters.length
    ? "Choose an original character or take full control of a canon character at a major timeline moment. Canon will guide, never override, your choices."
    : "Create an original character shortly before the main storyline.";
  refreshEraRow();
  refreshJjkCreationOptions();
  refreshHxhCreationOptions();
  refreshOnePieceCreationOptions();
}

function refreshEraRow() {
  const wd = APP.worldsMeta?.worlds?.[$("#nc-world").value] || {};
  const eras = wd.starting_eras || [];
  const row = $("#nc-era-row");
  if (!eras.length || $("#nc-character-mode").value) {
    row.hidden = true;
    $("#nc-starting-era").innerHTML = "";
    $("#nc-era-note").textContent = "";
    return;
  }
  row.hidden = false;
  $("#nc-starting-era").innerHTML = eras.map((e) => `<option value="${escapeHtml(e.id)}">${escapeHtml(e.label)}</option>`).join("");
  $("#nc-starting-era").value = eras[0].id;
  $("#nc-era-note").textContent = eras[0].anchor || "";
}

function selectedCanonCharacter() {
  const wd = APP.worldsMeta?.worlds?.[$("#nc-world").value] || {};
  return (wd.playable_characters || []).find((c) => c.id === $("#nc-character-mode").value) || null;
}

function refreshJjkCreationOptions() {
  const active = $("#nc-world").value === "Jujutsu Kaisen" && !$("#nc-character-mode").value;
  $("#nc-jjk-options").hidden = !active;
  $("#nc-jjk-curse-grade-row").hidden = !(active && $("#nc-origin").value === "Sentient Cursed Spirit");
  if (active) {
    const rows = APP.worldsMeta?.worlds?.["Jujutsu Kaisen"]?.start_options || [];
    const index = rows.findIndex((row) => row.origin === $("#nc-origin").value);
    if (index >= 0) $("#nc-start").value = String(index);
  }
}

function refreshHxhCreationOptions() {
  const active = $("#nc-world").value === "Hunter x Hunter" && !$("#nc-character-mode").value;
  $("#nc-hxh-options").hidden = !active;
}

function refreshOnePieceCreationOptions() {
  const active = $("#nc-world").value === "One Piece" && !$("#nc-character-mode").value;
  $("#nc-one-piece-options").hidden = !active;
  $("#nc-op-haki-types").hidden = !(active && $("#nc-op-haki").checked);
}

function refreshOvergearedCreationOptions() {
  const active = $("#nc-world").value === "Overgeared" && !$("#nc-character-mode").value;
  $("#nc-overgeared-options").hidden = !active;
}

function collectCampaignPayload() {
  const stats = {};
  $$("#nc-stats input").forEach((inp) => { stats[inp.getAttribute("data-stat")] = parseInt(inp.value || "0", 10); });
  const wd = APP.worldsMeta.worlds[$("#nc-world").value];
  const startOpts = wd.start_options || [];
  const chosenStart = startOpts.length ? startOpts[parseInt($("#nc-start").value || "0", 10)] : null;
  return {
    name: $("#nc-name").value.trim() || "Traveler", world: $("#nc-world").value,
    difficulty: $("#nc-difficulty").value, background: $("#nc-background").value,
    appearance: $("#nc-appearance").value, custom_world: $("#nc-custom").value,
    origin: $("#nc-origin").value, archetype: $("#nc-world").value === "Jujutsu Kaisen" ? "Jujutsu Sorcerer" : $("#nc-archetype").value, stats,
    age: $("#nc-age").value.trim(),
    start_location: chosenStart ? chosenStart.location : "", start_note: chosenStart ? chosenStart.note : "",
    canon_character_id: $("#nc-character-mode").value,
    starting_era_id: $("#nc-era-row").hidden ? "" : ($("#nc-starting-era").value || ""),
    jjk_guarantee_strong: !!$("#nc-jjk-strong").checked,
    jjk_curse_grade: $("#nc-origin").value === "Sentient Cursed Spirit" ? $("#nc-jjk-curse-grade").value : "",
    hxh_start_with_nen: !!$("#nc-hxh-nen").checked,
    one_piece_devil_fruit: !!$("#nc-op-devil-fruit").checked,
    one_piece_haki_types: $("#nc-op-haki").checked ? [
      $("#nc-op-observation").checked ? "Observation" : "",
      $("#nc-op-armament").checked ? "Armament" : "",
      $("#nc-op-conqueror").checked ? "Conqueror" : "",
    ].filter(Boolean) : [],
    overgeared_class_start: $("#nc-overgeared-class-start").value || "narrative",
  };
}

async function openNewCampaignModal() {
  // Always refetch. This prevents character creation from using metadata left
  // in memory by an older build or a failed first request.
  APP.worldsMeta = await apiGet("/api/worlds");
  const worlds = APP.worldsMeta.worlds || {};
  const order = Array.isArray(APP.worldsMeta.order) ? APP.worldsMeta.order.filter((name) => worlds[name]) : Object.keys(worlds);
  const difficulties = APP.worldsMeta.difficulties || {};
  if (!order.length) throw new Error("No campaign worlds were returned by the game server.");
  const initialWorld = order.includes("One Piece") ? "One Piece" : order[0];
  const difficultyNames = Object.keys(difficulties);
  if (!difficultyNames.length) throw new Error("No campaign difficulties were returned by the game server.");
  const initialDifficulty = difficultyNames.includes("Adventurer") ? "Adventurer" : difficultyNames[0];
  fillSelect($("#nc-world"), order, initialWorld);
  fillSelect($("#nc-difficulty"), difficultyNames, initialDifficulty);
  $("#nc-diff-desc").textContent = (difficulties[initialDifficulty] || {}).description || "";
  refreshCampaignWorldFields();
  openModal("modal-campaign");
  closeModal("modal-welcome");
}
$("#nc-world").addEventListener("change", refreshCampaignWorldFields);
$("#nc-origin").addEventListener("change", refreshJjkCreationOptions);
$("#nc-op-haki").addEventListener("change", refreshOnePieceCreationOptions);
$("#nc-difficulty").addEventListener("change", () => { $("#nc-diff-desc").textContent = APP.worldsMeta.difficulties[$("#nc-difficulty").value].description; });
$("#nc-character-mode").addEventListener("change", () => {
  refreshEraRow();
  refreshJjkCreationOptions();
  refreshHxhCreationOptions();
  refreshOnePieceCreationOptions();
  refreshOvergearedCreationOptions();
  const c = selectedCanonCharacter();
  if (!c) {
    if (ncCharacterStash) {
      $("#nc-name").value = ncCharacterStash.name;
      $("#nc-background").value = ncCharacterStash.background;
      $("#nc-appearance").value = ncCharacterStash.appearance;
      $("#nc-origin").value = ncCharacterStash.origin;
      $("#nc-archetype").value = ncCharacterStash.archetype;
      $("#nc-age").value = ncCharacterStash.age;
      $("#nc-character-note").textContent = ncCharacterStash.note;
      ncCharacterStash = null;
    }
    return;
  }
  if (!ncCharacterStash) {
    ncCharacterStash = {
      name: $("#nc-name").value, background: $("#nc-background").value, appearance: $("#nc-appearance").value,
      origin: $("#nc-origin").value, archetype: $("#nc-archetype").value, note: $("#nc-character-note").textContent,
      age: $("#nc-age").value,
    };
  }
  $("#nc-name").value = c.name || "Traveler";
  $("#nc-background").value = c.background || "";
  $("#nc-appearance").value = c.appearance || "";
  $("#nc-age").value = (c.age ?? "") === "" ? "" : String(c.age);
  if (Array.from($("#nc-origin").options).some((o) => o.value === c.origin)) $("#nc-origin").value = c.origin;
  if (Array.from($("#nc-archetype").options).some((o) => o.value === c.archetype)) $("#nc-archetype").value = c.archetype;
  $("#nc-character-note").textContent = `${c.name} begins at ${c.location}, ${formatCalendarDate($("#nc-world").value, c.start_day, null, c.start_day)}. You control every decision; canon events remain pressures that can change naturally.`;
});
$("#nc-starting-era").addEventListener("change", () => {
  const wd = APP.worldsMeta?.worlds?.[$("#nc-world").value] || {};
  const era = (wd.starting_eras || []).find((e) => e.id === $("#nc-starting-era").value);
  $("#nc-era-note").textContent = era ? era.anchor || "" : "";
});

function renderCampaignPreview(p, payload) {
    const profile = p.starting_profile || {};
    APP.pendingPreview = p;
    APP.pendingCampaign = { ...payload, preview_stats: p.abilities, preview_profile: profile };
    const concealedSignature = profile.hidden_class?.discovery?.concealed && Number(profile.hidden_class.discovery.progress || 0) < 50 ? profile.hidden_class.signature_skill : "";
    const loadout = [...(profile.titles || []).map((x) => `Title: ${x}`), ...Object.keys(profile.skills || {}).filter((x) => x !== concealedSignature).map((x) => `Skill: ${x}`), ...Object.values(profile.equipment || {}).map((x) => `Gear: ${x}`)];
    const startingAbility = profile.generated_ability || null;
    const ability = startingAbility && startingAbility.details ? startingAbility.details : {};
    const startingTechniques = startingAbility && Array.isArray(startingAbility.additional_skills) ? startingAbility.additional_skills : [];
    const growth = profile.growth_profile || {};
    const abilityCard = p.world !== "Bleach" && startingAbility ? `<section class="generated-ability"><b>STARTING ABILITY — ${escapeHtml(startingAbility.name)}</b>${ability.kind ? `<span><strong>Type:</strong> ${escapeHtml(ability.kind)}</span>` : ""}<span>${escapeHtml(ability.effect || ability.description || "")}</span>${startingTechniques.length ? `<span><strong>Starting techniques:</strong> ${startingTechniques.map((row) => escapeHtml(row.name || "")).filter(Boolean).join(" · ")}</span>` : ""}<span><strong>In-world origin:</strong> ${escapeHtml(ability.origin || "A rare talent that has begun to surface.")}</span><span><strong>Limit:</strong> ${escapeHtml(ability.limitation || "Must be developed through play.")}</span><span><strong>Growth:</strong> ${escapeHtml(ability.growth_path || "Practice and suitable guidance.")}</span>${ability.canon_balance ? `<span><strong>World-scale balance:</strong> ${escapeHtml(ability.canon_balance)}</span>` : ""}</section>` : "";
    const classCard = p.world === "Jujutsu Kaisen" ? renderJjkBirthSlot(profile.jjk_birth_slot) : (p.world !== "Bleach" && (profile.class_profile || profile.hidden_class) ? renderClassCard(profile.class_profile || profile.hidden_class) : "");
    const bleachReleaseCard = p.world === "Bleach" ? renderBleachReleases(profile.bleach_release_profile ? {
      "Zanpakuto Profile": profile.bleach_release_profile,
      Shikai: ["Shikai", "Bankai"].includes(profile.bleach_release_profile.stage) ? `Achieved — ${profile.bleach_release_profile.shikai_name || profile.bleach_release_profile.name}` : "Unachieved",
      Bankai: profile.bleach_release_profile.stage === "Bankai" ? profile.bleach_release_profile.bankai_name : "Unachieved",
      PreviewConcept: profile.bleach_release_profile.stage === "Dormant",
    } : { Shikai: "Unachieved", Bankai: "Unachieved" }) : "";
    const host = profile.jinchuriki_profile || {};
    const jinchurikiPreviewCard = p.world === "Naruto" && host.beast ? `<details class="world-system-card expandable-special-card naruto-jinchuriki-system" open><summary><header><small>JINCHŪRIKI</small><h3>${escapeHtml(host.beast)} · ${escapeHtml(host.mastery || "Unmastered")}</h3></header><span class="expand-label"></span></summary><div class="expandable-special-body"><div class="world-system-detail"><b>Seal & relationship</b><span>${escapeHtml(`${host.seal || "Established seal"} · ${host.relationship || "Undeveloped"}`)}</span></div><div class="world-system-detail"><b>Available now</b><span>${escapeHtml(compactReadable(host.available_abilities) || "No deliberate access yet")}</span></div><div class="world-system-detail"><b>Full canon potential</b><span>${escapeHtml(compactReadable(host.canonical_abilities))}</span></div><div class="world-system-detail"><b>Drawbacks & dangers</b><span>${escapeHtml(compactReadable(host.drawbacks))}</span></div></div></details>` : "";
    const affinity = profile.naruto_affinity_profile || {};
    const affinityPreviewCard = p.world === "Naruto" && affinity.primary ? `<details class="world-system-card expandable-special-card naruto-affinity-system" open><summary><header><small>CHAKRA AFFINITY</small><h3>${escapeHtml(affinity.primary)}</h3></header><span class="expand-label"></span></summary><div class="expandable-special-body"><div class="world-system-detail"><b>Natural affinities</b><span>${escapeHtml(compactReadable(affinity.natural_affinities) || affinity.primary)}</span></div><div class="world-system-detail"><b>Learned proficiencies</b><span>${escapeHtml(compactReadable(affinity.proficiencies) || "None yet")}</span></div><div class="world-system-detail"><b>Natural advantage</b><span>${escapeHtml(affinity.native_rule)}</span></div><div class="world-system-detail"><b>Other natures</b><span>${escapeHtml(affinity.off_affinity_rule)}</span></div><div class="world-system-detail"><b>Learning rates</b><span>${escapeHtml(Object.entries(affinity.learning_rates || {}).map(([nature,rate]) => `${nature.replace(" Release", "")} ${Number(rate).toFixed(2)}×`).join(" · "))}</span></div></div></details>` : "";
    const nenPreviewCard = p.world === "Hunter x Hunter" ? renderNenPanel(profile.nen_profile || {}, {}, true) : "";
    const onePiecePreviewCard = p.world === "One Piece" && (profile.devil_fruit_profile || Object.keys(profile.haki_profile || {}).length) ? renderWorldProgression("One Piece", {
      "Devil Fruit Profile": profile.devil_fruit_profile || { name: "None", type: "None" },
      "Devil Fruit": profile.devil_fruit_profile?.name || "None", "Haki Profile": profile.haki_profile || {}, Bounty: 0,
    }, {}, {}) : "";
    const startWarnings = (p.start_warnings || []).filter(Boolean);
    const warningCard = startWarnings.length ? `<section class="start-warnings"><b>START CONSISTENCY NOTE</b>${startWarnings.map((warning) => `<span>${escapeHtml(warning)}</span>`).join("")}</section>` : "";
    const primer = p.world_primer || {};
    const primerCard = `<section class="world-primer"><div class="world-primer-kicker">WHAT YOU'RE GETTING INTO — NO SPOILERS</div><p class="world-primer-premise">${escapeHtml(primer.premise || "")}</p><div class="world-primer-row"><b>Tone</b><span>${escapeHtml(primer.tone || "")}</span></div><div class="world-primer-row"><b>How power works</b><span>${escapeHtml(primer.power_system || "")}</span></div>${(primer.factions || []).length ? `<div class="world-primer-row"><b>Major powers</b><ul>${primer.factions.map((f) => `<li>${escapeHtml(f)}</li>`).join("")}</ul></div>` : ""}${(primer.locations || []).length ? `<div class="world-primer-row"><b>Where the story ranges</b><ul>${primer.locations.map((l) => `<li>${escapeHtml(l)}</li>`).join("")}</ul></div>` : ""}<p class="world-primer-starting-note">${escapeHtml(primer.starting_note || "")}</p></section>`;
    const classLabels = {
        "Overgeared": "Hidden class",
        "Solo Max-Level Newbie": "Hidden class",
        "Naruto": "Secret shinobi path",
        "One Piece": "Hidden potential",
        "Hunter x Hunter": "Rare Nen potential",
        "Reincarnated as a Slime": "Unique evolution path",
        "Bleach": "Secret spiritual path",
        "Custom World": "Hidden potential",
    };
    const classLabel = classLabels[p.world] || "Hidden potential";
    const specialReroll = p.world === "Bleach" ? `<button type="button" data-preview-reroll="zanpakuto">Zanpakutō abilities</button>` : p.world === "Jujutsu Kaisen" ? `<button type="button" data-preview-reroll="jjk_special">Innate technique / restriction</button>` : p.world === "Hunter x Hunter" ? `<button type="button" data-preview-reroll="nen_ability">Nen ability</button>` : p.world === "One Piece" && profile.devil_fruit_profile ? `<button type="button" data-preview-reroll="devil_fruit">Devil Fruit</button><button type="button" data-preview-reroll="class">Hidden potential</button>` : `<button type="button" data-preview-reroll="class">${escapeHtml(classLabel)}</button><button type="button" data-preview-reroll="ability">Starting ability</button>`;
    const rerolls = p.canon_character ? "" : `<section class="preview-rerolls"><b>Keep the character, reroll one part</b><div>${specialReroll}<button type="button" data-preview-reroll="backstory">Expanded backstory</button><button type="button" data-preview-reroll="loadout">Starting loadout</button></div><small>Only the selected part changes. Everything else remains locked.</small></section>`;
    const learningRate = Number(growth.learning_rate || 1);
    const ordinaryGrowth = Math.abs(learningRate - 1) < 0.005 && String(growth.aptitude || "").toLowerCase().includes("typical");
    const growthLabel = !ordinaryGrowth && String(growth.aptitude || "").toLowerCase().includes("typical") ? "Modified learning potential" : (growth.aptitude || "Unusual potential");
    const growthSummary = ordinaryGrowth ? "" : `<div class="growth-summary"><b>${escapeHtml(growthLabel)}</b><span>${escapeHtml(learningRate.toFixed(2))}× sustained-learning rate</span><small>${escapeHtml(growth.explanation || "Actual growth still depends on time, training conditions, instruction, and recovery.")}</small></div>`;
    $("#campaign-preview").innerHTML = `${primerCard}<div class="preview-hero"><h2>${escapeHtml(p.name)}</h2><p>${escapeHtml(p.world)} · ${escapeHtml(p.difficulty)}</p></div>${warningCard}${profile.power_notice ? `<div class="power-notice"><b>POWER NOTICE — ${escapeHtml(profile.power_band)}</b><span>${escapeHtml(profile.power_notice)}</span></div>` : ""}<div class="preview-grid"><div><b>Beginning</b><span>${escapeHtml(p.start_location)} · ${escapeHtml(formatCalendarDate(p.world, p.start_day, null, p.start_day))}</span></div><div><b>Role</b><span>${escapeHtml(p.origin)} · ${escapeHtml(p.archetype)}${p.race ? ` · ${escapeHtml(p.race)}` : ""}</span></div><div><b>Timeline</b><span>${escapeHtml(p.canon_anchor || "Before the main story")}</span></div><div><b>Starting pools</b><span>HP ${escapeHtml(profile.hp_max)} · ${escapeHtml(p.resource)} ${escapeHtml(profile.resource_max)}</span></div></div><h3>Starting attributes</h3><div class="preview-stats">${Object.entries(p.abilities || {}).map(([k,v]) => `<span><b>${escapeHtml(k)}</b> ${escapeHtml(v)}</span>`).join("")}</div><h3>Starting loadout</h3><div class="preview-loadout">${loadout.map((x) => `<span>${escapeHtml(x)}</span>`).join("")}</div>${bleachReleaseCard}${onePiecePreviewCard}${nenPreviewCard}${affinityPreviewCard}${jinchurikiPreviewCard}${classCard}${abilityCard}<section class="generated-backstory"><b>BACKGROUND</b><p>${escapeHtml(p.background || "The GM will complete a fitting background during the opening.")}</p></section>${growthSummary}${rerolls}<p class="hint">${p.uses_xp ? "This setting canonically uses visible XP and levels." : "This setting progresses through stats, techniques, knowledge and titles—no artificial XP levels."} ${p.canon_character ? "You have full control of this major character." : (p.starting_era ? "This original character begins in the selected timeline era." : "This original character begins shortly before the world's main story.")}</p>`;
    openModal("modal-campaign-preview");
}

$("#btn-begin-campaign").addEventListener("click", async () => {
  const payload = collectCampaignPayload();
  try {
    const result = await apiPost("/api/campaign/preview", payload);
    renderCampaignPreview(result.preview, payload);
  } catch (e) { showToast(e.message, "danger"); }
});

$("#campaign-preview").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-preview-reroll]");
  if (!button || !APP.pendingPreview || !APP.pendingCampaign) return;
  button.disabled = true;
  const kind = button.getAttribute("data-preview-reroll");
  try {
    const result = await apiPost("/api/campaign/preview/reroll", {
      preview: APP.pendingPreview, kind, background: APP.pendingCampaign.background || "",
    });
    renderCampaignPreview(result.preview, APP.pendingCampaign);
    showToast(`${humanLabel(kind)} rerolled.`, "notify");
  } catch (error) {
    showToast(error.message, "danger");
    button.disabled = false;
  }
});

$("#btn-preview-back").addEventListener("click", () => closeModal("modal-campaign-preview"));
$("#btn-confirm-campaign").addEventListener("click", async () => {
  if (!APP.pendingCampaign || APP.busy) return;
  setBusy(true); APP.deferPortraitGeneration = true;
  playCampaignStartCue(APP.pendingCampaign);
  try {
    const created = await apiPost("/api/campaign/new", APP.pendingCampaign);
    APP.campaignActive = true; APP.portraitAttempted.clear();
    clearTransientFeedback();
    $("#story-feed").innerHTML = ""; appendStoryEntries(created.story || []); renderState(created.state);
    // A new campaign always begins at the next story beat. Do not carry a
    // previous campaign's long-skip selection or intervention state forward.
    $("#time-unit").value = "moment";
    $("#time-amount").value = "1";
    $("#td-unit").value = "moment";
    $("#td-amount").value = "1";
    syncTimeControl("#time-unit", "#time-amount", null, null, "#time-control-help");
    syncTimeControl("#td-unit", "#td-amount", "#td-amount-field");
    closeModal("modal-campaign-preview"); closeModal("modal-campaign"); closeModal("modal-welcome");
    $("#scene-title").textContent = "OPENING SCENE";
    try {
      const opening = await apiPost("/api/campaign/opening", {});
      appendStoryEntries(opening.story); renderState(opening.state);
      maybeShowOnboarding();
    } catch (error) {
      appendStoryEntries([{ text: "[AI SETUP REQUIRED]\nYour fresh campaign was created. Select a model in AI & Portrait Setup, then click RETRY OPENING.", tag: "system" }]);
      $("#hdr-ai").textContent = "AI: MODEL NOT SELECTED";
    }
  } catch (error) { showToast(error.message, "danger"); }
  finally { APP.deferPortraitGeneration = false; setBusy(false); APP.pendingCampaign = null; if (APP.state) ensureAiPortrait(APP.state); }
});

// ---------------------------------------------------------------------------
// First-time onboarding overlay — shown once, after a brand-new campaign's
// opening scene renders, so the player already has something on screen to
// relate the explanation to instead of reading it before any state exists.
// ---------------------------------------------------------------------------
async function maybeShowOnboarding() {
  try {
    const s = await apiGet("/api/settings");
    if (s.onboarding_seen) return;
    openModal("modal-onboarding");
  } catch (e) { /* non-critical: worst case the overlay just doesn't show */ }
}
$("#btn-onboarding-done").addEventListener("click", async () => {
  closeModal("modal-onboarding");
  try { await apiPost("/api/settings", { onboarding_seen: true }); } catch (e) { /* best effort */ }
});

// ---------------------------------------------------------------------------
// Settings modal
// ---------------------------------------------------------------------------
const CLOUD_MODELS = [
  { id: "gpt-5-nano", label: "Lowest cost · $0.05 input / $0.40 output per 1M tokens" },
  { id: "gpt-4o-mini", label: "Fast background model · $0.15 / $0.60" },
  { id: "gpt-5.6-luna", label: "Recommended balanced GM · $0.20 / $1.20" },
  { id: "gpt-5.4-nano", label: "Compact reasoning · $0.20 / $1.25" },
  { id: "gpt-5-mini", label: "Legacy budget reasoning · $0.25 / $2.00" },
  { id: "gpt-5.4-mini", label: "Stronger mini model · $0.75 / $4.50" },
  { id: "gpt-5.6-terra", label: "High-quality GM · $2.00 / $12.00" },
  { id: "gpt-5.4", label: "High-quality established model · $2.50 / $15.00" },
  { id: "gpt-5.6-sol", label: "Highest-quality GM · $4.00 / $20.00" },
];
const CLOUD_MODEL_SUGGESTIONS = CLOUD_MODELS.map((m) => m.id);

function refreshModelSelectionHelp() {
  const help = $("#model-selection-help");
  if (!help) return;
  const provider = ($$('input[name="provider"]:checked')[0] || {}).value || "local";
  if (provider !== "cloud") {
    help.textContent = "Local model quality and speed depend on your hardware and the model loaded in LM Studio.";
    return;
  }
  const describe = (id) => CLOUD_MODELS.find((m) => m.id === String(id || "").trim())?.label || "Custom model · price estimate unavailable";
  const major = $("#st-major-model")?.value?.trim();
  help.textContent = `Main: ${describe($("#st-main-model").value)} · Background: ${describe($("#st-bg-model").value)}${major ? ` · Major events: ${describe(major)}` : " · Major events inherit Main"}`;
}

function refreshModelSuggestions() {
  const provider = ($$('input[name="provider"]:checked')[0] || {}).value || "local";
  const list = $("#model-suggestions");
  if (provider === "cloud") {
    list.innerHTML = CLOUD_MODELS.map((m) => `<option value="${escapeHtml(m.id)}" label="${escapeHtml(m.label)}">`).join("");
    $("#btn-detect-models").style.display = "none";
    $("#detect-status").textContent = "Cloud mode: choose a preset or mix models. Balanced is the recommended starting point.";
  } else {
    $("#btn-detect-models").style.display = "";
    $("#detect-status").textContent = "Not tested yet.";
  }
  refreshModelSelectionHelp();
}
$$('input[name="provider"]').forEach((r) => r.addEventListener("change", () => {
  refreshModelSuggestions();
  if (r.checked && r.value === "cloud") {
    const main = $("#st-main-model"), background = $("#st-bg-model");
    if (!main.value.trim() || !CLOUD_MODEL_SUGGESTIONS.includes(main.value.trim())) main.value = "gpt-5.6-luna";
    if (!background.value.trim() || !CLOUD_MODEL_SUGGESTIONS.includes(background.value.trim())) background.value = "gpt-4o-mini";
  }
}));
[$("#st-main-model"), $("#st-bg-model"), $("#st-major-model")].forEach((input) => {
  input.addEventListener("input", refreshModelSelectionHelp);
  input.addEventListener("change", refreshModelSelectionHelp);
});

async function openSettingsModal() {
  const s = await apiGet("/api/settings");
  $$('input[name="provider"]').forEach((r) => r.checked = r.value === s.provider);
  $("#st-base-url").value = s.local_base_url || "http://localhost:1234/v1";
  $("#st-token").value = s.local_token || "";
  $("#st-main-model").value = s.model || "";
  $("#st-bg-model").value = s.secondary_model || "";
  $("#st-major-model").value = s.major_event_model || "";
  $("#st-advisor-model").value = s.advisor_model || "";
  $("#st-advisor-provider").value = s.advisor_provider || "inherit";
  $("#st-creative-model").value = s.creative_model || "";
  $("#st-creative-provider").value = s.creative_provider || "inherit";
  $("#st-cost-request-limit").value = Number(s.max_ai_cost_per_request_usd || 0);
  $("#st-cost-turn-limit").value = Number(s.max_ai_cost_per_turn_usd || 0);
  $("#st-turn-repair-limit").value = Number(s.max_ai_retries_per_turn ?? 2);
  $("#st-session-budget").value = Number(s.session_budget_warning_usd ?? 5);
  $("#st-api-key").value = "";
  $("#st-narration").value = s.narration || "Concise";
  $("#st-simulation-mode").value = s.simulation_mode || "balanced";
  $("#st-autosave").checked = !!s.autosave;
  $("#st-sound").checked = !!s.sound_enabled;
  $("#st-music").checked = s.music_enabled !== false;
  $("#st-music-volume").value = Number(s.music_volume ?? .35);
  $("#st-anim").checked = !!s.animations_enabled;
  $("#st-portrait-enabled").checked = s.portrait_generation_enabled !== false;
  $("#st-portrait-auto").checked = s.portrait_auto_generate === true;
  $("#st-canon-foreknowledge").checked = s.canon_foreknowledge === true;
  $("#st-local-combat-recap").checked = s.local_combat_recap !== false;
  $("#st-local-reentry-recap").checked = s.local_reentry_recap !== false;
  $("#st-local-message-gate").checked = s.local_message_gate !== false;
  $("#st-image-model").value = s.image_model || "gpt-image-2";
  $("#st-image-provider").value = s.image_provider || "inherit";
  $("#st-local-image-base-url").value = s.local_image_base_url || "";
  $("#st-local-image-model").value = s.local_image_model || "";
  $("#st-portrait-quality").value = s.portrait_quality || "low";
  $("#st-developer-mode").checked = !!s.developer_mode;
  refreshModelSuggestions();
  refreshUsagePill();
  openModal("modal-settings");
}

$("#btn-detect-models").addEventListener("click", async () => {
  $("#detect-status").textContent = "Checking LM Studio...";
  try {
    const r = await apiPost("/api/settings/detect_models", { base_url: $("#st-base-url").value.trim(), token: $("#st-token").value.trim() });
    if (!r.models || !r.models.length) { $("#detect-status").textContent = "Connected, but no models are visible."; return; }
    $("#model-suggestions").innerHTML = r.models.map((m) => `<option value="${escapeHtml(m)}">`).join("");
    if (!$("#st-main-model").value) $("#st-main-model").value = r.models[0];
    if (!$("#st-bg-model").value) $("#st-bg-model").value = r.models[0];
    $("#detect-status").textContent = `CONNECTED — ${r.models.length} model(s) found. Pick one from the suggestions.`;
  } catch (e) { $("#detect-status").textContent = "NOT CONNECTED"; showToast(e.message, "danger"); }
});

async function testAiConnection(provider) {
  $("#detect-status").textContent = "Testing the selected AI...";
  const result = await apiPost("/api/settings/test_ai", {
    provider,
    base_url: $("#st-base-url").value.trim(), token: $("#st-token").value.trim(),
    api_key: $("#st-api-key").value.trim(), model: $("#st-main-model").value.trim(),
  });
  $("#detect-status").textContent = `VERIFIED — ${result.model} is available.`;
  return result;
}

$("#btn-test-ai").addEventListener("click", async () => {
  try { await testAiConnection(($$('input[name="provider"]:checked')[0] || {}).value || "local"); }
  catch (error) { $("#detect-status").textContent = "INVALID CONNECTION"; showToast(error.message, "danger"); }
});

$("#btn-save-settings").addEventListener("click", async () => {
  const provider = $$('input[name="provider"]:checked')[0].value;
  const patch = {
    provider,
    local_base_url: $("#st-base-url").value.trim() || "http://localhost:1234/v1",
    local_token: $("#st-token").value.trim(),
    model: $("#st-main-model").value,
    secondary_model: $("#st-bg-model").value || $("#st-main-model").value,
    major_event_model: $("#st-major-model").value.trim(),
    advisor_model: $("#st-advisor-model").value.trim(),
    advisor_provider: $("#st-advisor-provider").value,
    creative_model: $("#st-creative-model").value.trim(),
    creative_provider: $("#st-creative-provider").value,
    max_ai_cost_per_request_usd: Number($("#st-cost-request-limit").value || 0),
    max_ai_cost_per_turn_usd: Number($("#st-cost-turn-limit").value || 0),
    max_ai_retries_per_turn: Number($("#st-turn-repair-limit").value || 0),
    session_budget_warning_usd: Number($("#st-session-budget").value || 0),
    narration: $("#st-narration").value,
    simulation_mode: $("#st-simulation-mode").value,
    autosave: $("#st-autosave").checked,
    sound_enabled: $("#st-sound").checked,
    music_enabled: $("#st-music").checked,
    music_volume: Number($("#st-music-volume").value || .35),
    animations_enabled: $("#st-anim").checked,
    portrait_generation_enabled: $("#st-portrait-enabled").checked,
    portrait_auto_generate: $("#st-portrait-auto").checked,
    canon_foreknowledge: $("#st-canon-foreknowledge").checked,
    local_combat_recap: $("#st-local-combat-recap").checked,
    local_reentry_recap: $("#st-local-reentry-recap").checked,
    local_message_gate: $("#st-local-message-gate").checked,
    image_model: $("#st-image-model").value.trim() || "gpt-image-2",
    image_provider: $("#st-image-provider").value,
    local_image_base_url: $("#st-local-image-base-url").value.trim(),
    local_image_model: $("#st-local-image-model").value.trim(),
    portrait_quality: $("#st-portrait-quality").value,
    developer_mode: $("#st-developer-mode").checked,
  };
  if ($("#st-api-key").value.trim()) patch.api_key = $("#st-api-key").value.trim();
  await apiPost("/api/settings", patch);
  try {
    await testAiConnection(provider);
  } catch (error) {
    $("#detect-status").textContent = "SAVED, BUT AI COULD NOT BE VERIFIED";
    $("#hdr-ai").textContent = "AI: CONNECTION INVALID";
    showToast(error.message, "danger");
    return;
  }
  APP.soundEnabled = patch.sound_enabled;
  if (!APP.soundEnabled) stopWorldCue();
  APP.musicEnabled = patch.music_enabled;
  setMusicWidgetVolume(patch.music_volume, false);
  fadeAudioTo(musicPlayer(), patch.music_volume, 300);
  if (!APP.musicEnabled) musicPlayer().pause();
  APP.animationsEnabled = patch.animations_enabled;
  closeModal("modal-settings");
  showToast(`AI mode: ${provider === "cloud" ? "OpenAI Cloud" : "Local LM Studio"} · ${patch.simulation_mode} simulation`, "system");
  await refreshHeaderAiStatus();
  const refreshed = await apiGet("/api/state");
  APP.campaignActive = refreshed.campaign_active;
  renderState(refreshed.state);
});

$("#btn-portrait-regenerate").addEventListener("click", () => {
  if (APP.state) ensureAiPortrait(APP.state, true);
});

$("#btn-end-transformation").addEventListener("click", async () => {
  try {
    const result = await apiPost("/api/portrait/form/end", {});
    renderState(result.state);
    showToast("Returned to base form.", "notify");
  } catch (error) { showToast(error.message, "danger"); }
});

async function openPortraitManager() {
  if (!APP.campaignActive) { showToast("Start or load a campaign first.", "system"); return; }
  const result = await apiGet("/api/portrait/history");
  const identity = result.identity || {};
  $("#portrait-canonical").value = identity.canonical_description || APP.state.appearance_desc || "";
  $("#portrait-temporary").value = (identity.temporary_traits || []).join("\n");
  $("#portrait-locked").checked = !!identity.locked;
  $("#portrait-history").innerHTML = (result.history || []).length
    ? result.history.map((h) => `<div class="history-row"><b>Turn ${escapeHtml(h.turn ?? "?")}</b><span>${escapeHtml(h.canonical_description || h.appearance_desc || "Previous portrait")}</span></div>`).join("")
    : '<p class="hint">No earlier portrait identity is recorded.</p>';
  openModal("modal-portrait-manager");
}
$("#btn-portrait-manage").addEventListener("click", openPortraitManager);
$("#btn-portrait-accept").addEventListener("click", async () => {
  try {
    const result = await apiPost("/api/portrait/identity", {
      canonical_description: $("#portrait-canonical").value.trim(),
      temporary_traits: $("#portrait-temporary").value.split(/\n/).map((x) => x.trim()).filter(Boolean),
      locked: $("#portrait-locked").checked,
    });
    renderState(result.state); closeModal("modal-portrait-manager"); showToast("Portrait identity saved.", "notify");
  } catch (error) { showToast(error.message, "danger"); }
});
$("#btn-portrait-upload").addEventListener("click", async () => {
  const file = $("#portrait-reference-file").files[0];
  if (!file) { showToast("Choose a portrait image first.", "system"); return; }
  const form = new FormData(); form.append("image", file);
  try {
    const result = await api("/api/portrait/reference", { method: "POST", body: form });
    renderState(result.state); showToast("Reference portrait saved.", "notify");
  } catch (error) { showToast(error.message, "danger"); }
});
$("#btn-portrait-revert").addEventListener("click", async () => {
  try { const result = await apiPost("/api/portrait/revert", {}); renderState(result.state); await openPortraitManager(); }
  catch (error) { showToast(error.message, "danger"); }
});

function downloadEndpoint(path) {
  const anchor = document.createElement("a"); anchor.href = path; anchor.download = "";
  document.body.appendChild(anchor); anchor.click(); anchor.remove();
}

async function refreshUsagePill() {
  try {
    const u = await apiGet("/api/usage");
    const pill = $("#hdr-cost"), summary = $("#usage-summary");
    const taskRows = Object.entries(u.by_task || {}).sort((a, b) => Number(b[1].cost_usd || 0) - Number(a[1].cost_usd || 0) || Number(b[1].calls || 0) - Number(a[1].calls || 0));
    const taskLabel = taskRows.slice(0, 5).map(([task, row]) => `${humanLabel(task)}: ${row.calls} call(s), ~$${Number(row.cost_usd || 0).toFixed(3)}`).join(" · ");
    if (u.provider !== "cloud") {
      pill.hidden = true;
      if (summary) summary.innerHTML = `<div class="usage-total"><b>LOCAL TEXT MODE</b><span>No per-call text charge · ${escapeHtml(u.total_calls)} call(s) this session</span></div>`;
    } else {
      const prefix = u.cost_estimate_complete ? "~$" : "$";
      pill.hidden = false;
      pill.textContent = `${prefix}${u.total_cost_usd.toFixed(2)} this session`;
      pill.classList.toggle("over-budget", !!u.over_session_budget);
      pill.title = `${u.total_calls} AI call(s) — main model + background model + ${u.portraits.generated} portrait(s).`
        + (taskLabel ? ` By task — ${taskLabel}.` : "")
        + (u.cached_input_tokens ? ` ${u.cached_input_tokens.toLocaleString()} input tokens were reported as cached.` : "")
        + (u.cost_is_conservative ? " Cached-input discounts are not subtracted, so this is a conservative ceiling." : "")
        + (u.cost_estimate_complete ? "" : " (one or more models are unpriced; total is a floor, not exact.)");
    }
    if (summary && u.provider === "cloud") {
      const rows = taskRows.length ? taskRows.map(([task, row]) => `<div class="usage-task"><b>${escapeHtml(humanLabel(task))}</b><span>${escapeHtml(row.calls)} call(s)</span><span>${Number(row.input_tokens || 0).toLocaleString()} in · ${Number(row.output_tokens || 0).toLocaleString()} out</span><strong>~$${Number(row.cost_usd || 0).toFixed(4)}</strong></div>`).join("") : `<div class="hint">No model calls yet.</div>`;
      summary.innerHTML = `<div class="usage-total ${u.over_session_budget ? "over-budget" : ""}"><b>${u.over_session_budget ? "SESSION WARNING" : "SESSION TOTAL"}</b><strong>~$${Number(u.total_cost_usd || 0).toFixed(4)}</strong><span>${escapeHtml(u.total_calls)} AI call(s) · ${escapeHtml(u.portraits.generated)} portrait(s)</span></div><div class="usage-task-list">${rows}</div><small>${u.cost_is_conservative ? "Conservative estimate: cached-input discounts are not subtracted. " : ""}${u.cost_estimate_complete ? "" : "Some selected model pricing is unknown, so this total is a floor."}</small>`;
    }
  } catch (e) { /* usage is a convenience readout, never block on it */ }
}

const PRESET_MODELS = {
  budget: { model: "gpt-5-nano", secondary_model: "gpt-5-nano", major_event_model: "", image_model: "gpt-image-2", portrait_quality: "low" },
  balanced: { model: "gpt-5.6-luna", secondary_model: "gpt-4o-mini", major_event_model: "", image_model: "gpt-image-2", portrait_quality: "low" },
  quality: { model: "gpt-5.6-terra", secondary_model: "gpt-5.6-luna", major_event_model: "", image_model: "gpt-image-2", portrait_quality: "high" },
  premium: { model: "gpt-5.6-sol", secondary_model: "gpt-5.6-terra", major_event_model: "", image_model: "gpt-image-2", portrait_quality: "high" },
};
function applyModelPreset(name) {
  const p = PRESET_MODELS[name];
  $$('input[name="provider"]').forEach((r) => r.checked = r.value === "cloud");
  $("#st-main-model").value = p.model;
  $("#st-bg-model").value = p.secondary_model;
  $("#st-major-model").value = p.major_event_model;
  $("#st-image-model").value = p.image_model;
  $("#st-portrait-quality").value = p.portrait_quality;
  refreshModelSuggestions();
  showToast(`${name[0].toUpperCase() + name.slice(1)} preset applied — press SAVE to confirm.`, "system");
}
$("#btn-preset-budget").addEventListener("click", () => applyModelPreset("budget"));
$("#btn-preset-balanced").addEventListener("click", () => applyModelPreset("balanced"));
$("#btn-preset-quality").addEventListener("click", () => applyModelPreset("quality"));
$("#btn-preset-premium").addEventListener("click", () => applyModelPreset("premium"));

async function refreshHeaderAiStatus() {
  const st = await apiGet("/api/state");
  $("#hdr-ai").textContent = aiStatusLabel(st);
}

function aiStatusLabel(st) {
  if (st.ai_ready) return "AI: READY";
  if (st.ai_connection_status === "invalid") return "AI: CONNECTION INVALID";
  return st.ai_connection_status === "untested" ? "AI: READY TO TEST" : "AI: MODEL NOT SELECTED";
}

// ---------------------------------------------------------------------------
// Menu bar actions
// ---------------------------------------------------------------------------
async function runMenuAction(action) {
  playSfx("ui_click");
  if (action === "new-campaign") await openNewCampaignModal();
  else if (action === "settings") await openSettingsModal();
  else if (action === "help") openModal("modal-help");
  else if (action === "save") { try { await apiPost("/api/save", {}); playSfx("save"); showToast("Campaign saved.", "notify"); } catch (err) { showToast(err.message, "danger"); } }
  else if (action === "load") await openLoadModal();
  else if (action === "undo") {
    try { const r = await apiPost("/api/action/undo", {}); appendStoryEntries(r.story); renderState(r.state); }
    catch (err) { showToast(err.message, "danger"); }
  }
  else if (action === "export") downloadEndpoint("/api/save/export");
  else if (action === "import") { await openLoadModal(); $("#campaign-import-file").click(); }
  else if (action === "world-packs") {
    const r = await apiGet("/api/world-packs");
    $("#world-pack-content").innerHTML = `<p>Drop validated JSON world packs into:</p><code>${escapeHtml(r.folder)}</code><h3>Loaded</h3>${(r.loaded || []).length ? (r.loaded || []).map((x) => `<div class="jrow">${escapeHtml(typeof x === "object" ? x.name || x.id || JSON.stringify(x) : x)}</div>`).join("") : '<p class="hint">Only built-in worlds are loaded.</p>'}<h3>Errors</h3>${(r.errors || []).length ? r.errors.map((x) => `<div class="advance-warning">${escapeHtml(typeof x === "object" ? JSON.stringify(x) : x)}</div>`).join("") : '<p class="hint">No world-pack errors.</p>'}`;
    openModal("modal-world-packs");
  }
  else if (action === "diagnostics") {
    const r = await apiGet("/api/diagnostics");
    const recoveryRows = (r.turn_recovery?.timeline || []).slice().reverse().map((row) => `<span><b>${escapeHtml(humanLabel(row.status || "checkpoint"))}</b>Turn ${escapeHtml(row.turn ?? "?")} · ${escapeHtml(humanLabel(row.route || "turn"))}</span>`).join("");
    $("#diagnostics-summary").innerHTML = `<div class="preview-grid"><div><b>Version</b><span>${escapeHtml(APP.state?._build_id || r.app_version || APP.state?._app_version || "?")}</span></div><div><b>Campaign</b><span>${escapeHtml(APP.state?.name || "None")}</span></div><div><b>Scene match</b><span>${escapeHtml(r.scene?.reason || "Unknown")}</span></div><div><b>Validation issues</b><span>${escapeHtml((r.validation_log || []).length)}</span></div></div>${recoveryRows ? `<details class="recovery-timeline"><summary>Recent safe turn checkpoints</summary>${recoveryRows}</details>` : ""}`;
    $("#btn-retry-failed-turn").hidden = !r.turn_recovery?.last_failed?.route;
    $("#diagnostics-json").textContent = JSON.stringify(r, null, 2); openModal("modal-diagnostics");
  }
  else if (action === "asset-folder") showToast("Scene art lives under assets/generated_scenes; custom overrides live under assets/user/<World>.", "system");
  else if (action === "music-folder") await openMusicFolder();
}

$("#btn-diagnostics-export").addEventListener("click", () => downloadEndpoint("/api/diagnostics/export"));
$("#btn-inline-retry").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  const pending = APP.retryRequest;
  try {
    const result = pending ? await apiPost(pending.path, pending.payload) : await apiPost("/api/action/retry_failed", {});
    if (pending?.path === "/api/time/resolve") await processTimeSkipResolution(result, pending.payload);
    else {
      if (result.state) renderState(result.state);
      if (result.story) appendStoryEntries(result.story, { focusNew: true });
    }
    $("#turn-recovery-notice").hidden = true;
  } catch (error) { showToast(error.message, "danger"); }
  finally { button.disabled = false; }
});
$("#btn-diagnostics-bundle").addEventListener("click", () => downloadEndpoint("/api/diagnostics/bundle"));
$("#btn-retry-failed-turn").addEventListener("click", async () => {
  const button = $("#btn-retry-failed-turn"); button.disabled = true;
  try {
    const result = await apiPost("/api/action/retry_failed", {});
    if (result.story) appendStoryEntries(result.story);
    if (result.state) renderState(result.state);
    button.hidden = true;
    showToast("The failed turn completed from its clean checkpoint.", "notify");
  } catch (error) { showToast(error.message, "danger"); }
  finally { button.disabled = false; }
});
$("#diagnostics-recovery-actions").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-diagnostic-repair]");
  if (!button) return;
  button.disabled = true;
  try {
    const result = await apiPost("/api/campaign/health/repair", {repair_id: button.getAttribute("data-diagnostic-repair")});
    renderState(result.state);
    showToast((result.repair?.applied || []).join(" ") || "That part of the campaign was already healthy.", "notify");
    const report = await apiGet("/api/diagnostics");
    $("#diagnostics-json").textContent = JSON.stringify(report, null, 2);
  } catch (error) { showToast(error.message, "danger"); }
  finally { button.disabled = false; }
});

// Explicit listeners are more reliable than delegated clicks inside a native
// WebView. Menus also toggle on click, so they do not depend on hover support.
$$('[data-action]').forEach((btn) => btn.addEventListener("click", async (e) => {
  e.preventDefault();
  $$(".menu.open").forEach((m) => m.classList.remove("open"));
  try { await runMenuAction(btn.getAttribute("data-action")); }
  catch (err) { console.error(err); showToast(err.message || "That menu action could not be opened.", "danger"); }
}));
$$('.menu-btn').forEach((btn) => btn.addEventListener("click", (e) => {
  e.stopPropagation();
  const menu = btn.closest(".menu"), wasOpen = menu.classList.contains("open");
  $$(".menu.open").forEach((m) => m.classList.remove("open"));
  if (!wasOpen) menu.classList.add("open");
}));
document.addEventListener("click", (e) => {
  if (!e.target.closest(".menu")) $$(".menu.open").forEach((m) => m.classList.remove("open"));
});
$("#btn-settings-gear").addEventListener("click", openSettingsModal);

async function openLoadModal() {
  const r = await apiGet("/api/saves");
  const list = $("#load-list");
  list.innerHTML = r.saves.length ? "" : '<li class="empty">No saved campaigns yet.</li>';
  r.saves.forEach((entry) => {
    const save = typeof entry === "string" ? { id: entry, label: entry, kind: "manual", saved_at: "" } : entry;
    const li = document.createElement("li");
    li.className = save.kind === "autosave" ? "autosave-entry" : "manual-save-entry";
    li.innerHTML = `<div class="save-info"><b>${escapeHtml(save.label || save.id)}</b><small>Version ${escapeHtml(save.version || "Legacy")}${save.saved_at ? ` · ${escapeHtml(save.saved_at)}` : ""}${save.corrupt ? ` · CORRUPT: ${escapeHtml(save.error || "Unreadable")}` : ""}</small></div><div class="save-actions"><button type="button" data-save-load>LOAD</button>${save.recoverable ? '<button type="button" data-save-recover>RECOVER</button>' : ""}<button type="button" data-save-delete class="danger-link">DELETE</button></div>`;
    li.querySelector("[data-save-load]").disabled = !!save.corrupt;
    li.querySelector("[data-save-load]").addEventListener("click", async () => {
      try {
        const res = await apiPost("/api/load", { name: save.id });
        APP.campaignActive = true;
        clearTransientFeedback();
        $("#story-feed").innerHTML = "";
        appendStoryEntries(res.story.map((s) => ({ text: s.text, tag: s.tag })));
        renderState(res.state);
        closeModal("modal-load");
        showToast(save.kind === "autosave" ? "Autosave recovered." : "Campaign loaded.", "notify");
        maybeFetchReentryRecap(res.state);
      } catch (err) { showToast(err.message, "danger"); }
    });
    li.querySelector("[data-save-recover]")?.addEventListener("click", async () => {
      try { const res = await apiPost("/api/save/recover", { name: save.id }); APP.campaignActive = true; clearTransientFeedback(); $("#story-feed").innerHTML = ""; appendStoryEntries(res.story || []); renderState(res.state); closeModal("modal-load"); showToast("Campaign recovered from its newest autosave.", "notify"); maybeFetchReentryRecap(res.state); }
      catch (err) { showToast(err.message, "danger"); }
    });
    li.querySelector("[data-save-delete]").addEventListener("click", async () => {
      if (!window.confirm(`Permanently delete ${save.label || save.id}?`)) return;
      try { await apiPost("/api/save/delete", { name: save.id }); li.remove(); showToast("Campaign save deleted.", "notify"); await refreshWelcomeSaveCount(); }
      catch (err) { showToast(err.message, "danger"); }
    });
    list.appendChild(li);
  });
  openModal("modal-load");
  closeModal("modal-welcome");
  return r.saves.length;
}

async function importSelectedCampaign() {
  const file = $("#campaign-import-file").files[0];
  if (!file) { showToast("Choose a Worldwalker JSON export first.", "system"); return; }
  const form = new FormData(); form.append("file", file);
  try {
    const result = await api("/api/save/import", { method: "POST", body: form });
    showToast(`Campaign imported from version ${result.version || "Legacy"}.`, "notify");
    await openLoadModal();
  } catch (error) { showToast(error.message, "danger"); }
}
$("#btn-campaign-import").addEventListener("click", importSelectedCampaign);
$("#campaign-import-file").addEventListener("change", () => { if ($("#campaign-import-file").files.length) importSelectedCampaign(); });

async function refreshWelcomeSaveCount() {
  try {
    const r = await apiGet("/api/saves");
    const count = (r.saves || []).length;
    $("#welcome-save-note").textContent = count ? `${count} saved campaign${count === 1 ? "" : "s"} found on this computer.` : "No saved campaigns found yet.";
  } catch (e) {
    $("#welcome-save-note").textContent = "Saved campaigns could not be checked.";
  }
}
$("#btn-welcome-new").addEventListener("click", async () => {
  try { await openNewCampaignModal(); }
  catch (e) { console.error(e); showToast("Could not open character creation: " + e.message, "danger"); }
});
$("#btn-welcome-load").addEventListener("click", async () => {
  try { await openLoadModal(); }
  catch (e) { console.error(e); showToast("Could not open saved games: " + e.message, "danger"); }
});

// ---------------------------------------------------------------------------
// Collapsible panels — every panel except Story & Events and the composer
// (the two the player always needs visible) can be collapsed to reclaim
// vertical space, per user request.
// ---------------------------------------------------------------------------
function initCollapsiblePanels() {
  $$(".panel").forEach((panel) => {
    if (panel.classList.contains("no-collapse")) return;
    const head = panel.querySelector(".panel-head");
    if (!head || head.querySelector(".collapse-chevron")) return;
    const chevron = document.createElement("span");
    chevron.className = "collapse-chevron";
    chevron.textContent = "▾";
    head.appendChild(chevron);
    head.addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      panel.classList.toggle("collapsed");
    });
  });
}

function initMobileExperience() {
  const readFlag = (key, fallback) => {
    try { const value = localStorage.getItem(`worldwalker_mobile_${key}`); return value === null ? fallback : value === "true"; }
    catch (_) { return fallback; }
  };
  const storeFlag = (key, value) => { try { localStorage.setItem(`worldwalker_mobile_${key}`, String(value)); } catch (_) {} };
  APP.mobileLowData = readFlag("low_data", false);
  APP.mobileHaptics = readFlag("haptics", true);
  APP.mobileLargeText = readFlag("large_text", false);
  document.body.classList.toggle("mobile-low-data", APP.mobileLowData);
  document.body.classList.toggle("mobile-large-text", APP.mobileLargeText);
  $("#mobile-low-data").checked = APP.mobileLowData;
  $("#mobile-haptics").checked = APP.mobileHaptics;
  $("#mobile-large-text").checked = APP.mobileLargeText;
  setMobileView("chronicle", false);

  $("#action-input").addEventListener("input", saveMobileDraft);
  $("#mobile-chronicle-tools").addEventListener("click", (event) => {
    const button = event.target.closest("[data-story-filter]");
    if (button) applyMobileStoryFilter(button.getAttribute("data-story-filter"));
  });
  $("#story-feed").addEventListener("click", (event) => {
    const button = event.target.closest(".mobile-beat-toggle");
    if (!button) return;
    const beat = button.closest(".story-beat");
    const collapsed = beat.classList.toggle("mobile-collapsed");
    button.setAttribute("aria-expanded", String(!collapsed));
    button.textContent = collapsed ? "Show routine details" : "Hide routine details";
  });
  $("#btn-mobile-queue-toggle").addEventListener("click", () => {
    const card = $(".action-chat-card");
    const collapsed = card.classList.toggle("queue-collapsed");
    $("#btn-mobile-queue-toggle").setAttribute("aria-expanded", String(!collapsed));
  });
  $("#btn-mobile-queue-clear").addEventListener("click", async () => {
    if (APP.busy || !(APP.state?.queued_actions || []).length) return;
    try {
      for (let index = APP.state.queued_actions.length - 1; index >= 0; index -= 1) {
        const result = await apiPost("/api/actions/remove", { index });
        APP.state.queued_actions = result.queued_actions || [];
      }
      renderQueuedActions(APP.state.queued_actions);
      mobileVibrate(10);
    } catch (error) { showToast(error.message, "danger"); }
  });

  $$("#mobile-bottom-nav [data-mobile-view]").forEach((button) => button.addEventListener("click", async () => {
    const view = button.getAttribute("data-mobile-view");
    mobileVibrate(8);
    if (view === "more") {
      $$("#mobile-bottom-nav [data-mobile-view]").forEach((peer) => peer.setAttribute("aria-selected", String(peer === button)));
      openModal("modal-mobile-more");
    } else setMobileView(view);
  }));
  $("#modal-journal").addEventListener("transitionend", () => {
    if (!$("#modal-journal").classList.contains("open")) setMobileView(APP.mobileView, false);
  });
  $("#modal-mobile-more").addEventListener("click", (event) => {
    const button = event.target.closest("[data-mobile-open]");
    if (!button) return;
    const target = button.getAttribute("data-mobile-open");
    if (target === "install") {
      if (APP.mobileInstallPrompt) {
        APP.mobileInstallPrompt.prompt();
        APP.mobileInstallPrompt.userChoice.finally(() => { APP.mobileInstallPrompt = null; button.hidden = true; });
      } else showToast("Use your browser menu and choose Add to Home Screen.", "notify");
      return;
    }
    closeModal("modal-mobile-more");
    if (target === "chat") openNpcChat();
    else if (target === "advisor") $("#btn-open-advisor").click();
    else if (target === "settings") $("#btn-settings-gear").click();
    else openJournal(target);
  });
  $("#mobile-low-data").addEventListener("change", (event) => {
    APP.mobileLowData = event.target.checked; storeFlag("low_data", APP.mobileLowData);
    document.body.classList.toggle("mobile-low-data", APP.mobileLowData);
  });
  $("#mobile-haptics").addEventListener("change", (event) => {
    APP.mobileHaptics = event.target.checked; storeFlag("haptics", APP.mobileHaptics); mobileVibrate([10, 20, 10]);
  });
  $("#mobile-large-text").addEventListener("change", (event) => {
    APP.mobileLargeText = event.target.checked; storeFlag("large_text", APP.mobileLargeText);
    document.body.classList.toggle("mobile-large-text", APP.mobileLargeText);
  });

  $("#btn-mobile-time").addEventListener("click", () => $("#btn-detailed-time").click());
  $("#btn-mobile-advance").addEventListener("click", () => { mobileVibrate(12); $("#btn-advance").click(); });
  $("#mobile-combat-dock").addEventListener("click", (event) => {
    const button = event.target.closest("[data-combat-proxy]");
    if (!button) return;
    const action = button.getAttribute("data-combat-proxy");
    mobileVibrate(action === "attack" ? 18 : 9);
    if (["attack", "defend", "flee"].includes(action)) $(`#btn-combat-${action}`).click();
    else if (action === "ability") { setMobileView("actions"); requestAnimationFrame(() => $("#combat-ability")?.focus()); }
    else if (action === "item") openJournal("inventory");
    else if (action === "nonlethal") {
      const toggle = $("#combat-mercy-toggle"); toggle.checked = !toggle.checked; toggle.dispatchEvent(new Event("change", { bubbles: true }));
    }
  });

  let queueGesture = null;
  $("#queued-actions").addEventListener("pointerdown", (event) => {
    if (!isMobileLayout() || event.target.closest("button")) return;
    const row = event.target.closest(".queued-action");
    if (!row) return;
    queueGesture = { row, index: Number(row.dataset.actionIndex), x: event.clientX, y: event.clientY };
  });
  $("#queued-actions").addEventListener("pointermove", (event) => {
    if (!queueGesture) return;
    const dx = Math.min(0, event.clientX - queueGesture.x);
    if (Math.abs(dx) > 12) queueGesture.row.style.transform = `translateX(${Math.max(-90, dx)}px)`;
  });
  const finishQueueGesture = async (event) => {
    if (!queueGesture) return;
    const gesture = queueGesture; queueGesture = null;
    gesture.row.style.transform = "";
    const dx = event.clientX - gesture.x, dy = event.clientY - gesture.y;
    try {
      let result = null;
      if (dx < -72) result = await apiPost("/api/actions/remove", { index: gesture.index });
      else if (Math.abs(dy) > 58) {
        const toIndex = Math.max(0, Math.min((APP.state?.queued_actions || []).length - 1, gesture.index + (dy > 0 ? 1 : -1)));
        if (toIndex !== gesture.index) result = await apiPost("/api/actions/move", { index: gesture.index, to_index: toIndex });
      }
      if (result) { APP.state.queued_actions = result.queued_actions || []; renderQueuedActions(APP.state.queued_actions); mobileVibrate(10); }
    } catch (error) { showToast(error.message, "danger"); }
  };
  $("#queued-actions").addEventListener("pointerup", finishQueueGesture);
  $("#queued-actions").addEventListener("pointercancel", () => { if (queueGesture) queueGesture.row.style.transform = ""; queueGesture = null; });

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault(); APP.mobileInstallPrompt = event; $("#btn-mobile-install").hidden = false;
  });
  const updateNetwork = () => probeGameServer({ restoreState: true });
  window.addEventListener("offline", updateNetwork);
  window.addEventListener("online", updateNetwork);
  window.addEventListener("pageshow", (event) => { if (event.persisted) updateNetwork(); });
  document.addEventListener("visibilitychange", () => {
    document.body.classList.toggle("app-backgrounded", document.hidden);
    if (!document.hidden) updateNetwork();
  });
  window.clearInterval(APP.serverProbeTimer);
  APP.serverProbeTimer = window.setInterval(updateNetwork, 15000);
  window.addEventListener("resize", () => APP.state && renderMobileState(APP.state));
  let mobileScrollTimer = null;
  window.addEventListener("scroll", () => {
    if (!isMobileLayout()) return;
    clearTimeout(mobileScrollTimer);
    mobileScrollTimer = setTimeout(() => {
      try { localStorage.setItem(mobileCampaignKey(`scroll_${APP.mobileView}`), String(window.scrollY || 0)); } catch (_) {}
    }, 120);
  }, { passive: true });
  window.addEventListener("beforeunload", (event) => {
    if (!$("#action-input").value.trim() && !(APP.state?.queued_actions || []).length) return;
    event.preventDefault(); event.returnValue = "";
  });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
function applyAccountSession(auth) {
  APP.accountsEnabled = !!auth.accounts_enabled;
  APP.account = auth.user || null;
  APP.csrfToken = auth.csrf_token || APP.csrfToken || "";
  if (auth.auth_token) {
    APP.authToken = auth.auth_token;
    persistAuthToken(APP.authToken);
  }
  const accountButton = $("#btn-account");
  accountButton.hidden = !APP.account;
  $("#btn-welcome-signout").hidden = !APP.account;
  $("#hdr-account-name").textContent = APP.account?.username || "";
  $("#invite-code-row").hidden = !auth.invite_required;
  $("#btn-multiplayer").hidden = !APP.account;
}

// ---------------------------------------------------------------------------
// Two-player shared campaigns
// ---------------------------------------------------------------------------
function multiplayerClock(seconds) {
  const safe = Math.max(0, Number(seconds || 0));
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(Math.floor(safe % 60)).padStart(2, "0")}`;
}

function renderMultiplayer(status) {
  APP.multiplayer = status?.active ? status : null;
  const button = $("#btn-multiplayer");
  button.hidden = !APP.accountsEnabled || !APP.account;
  button.classList.toggle("active", !!APP.multiplayer);
  $("#hdr-multiplayer-label").textContent = APP.multiplayer
    ? `R${status.round} · ${status.resolving ? "RESOLVING" : multiplayerClock(status.seconds_left)}`
    : "MULTIPLAYER";
  $("#multiplayer-inactive").hidden = !!APP.multiplayer;
  $("#multiplayer-active").hidden = !APP.multiplayer;
  if (!APP.multiplayer) {
    $("#btn-advance").textContent = "ADVANCE";
    return;
  }
  $("#multiplayer-invite-code").textContent = status.join_code || "------";
  $("#multiplayer-round").textContent = status.round;
  $("#multiplayer-timer").textContent = status.resolving ? "RESOLVING" : multiplayerClock(status.seconds_left);
  $("#multiplayer-players").innerHTML = (status.members || []).map((member) => {
    const classes = ["multiplayer-player", member.ready ? "ready" : "", member.connected ? "" : "offline"].filter(Boolean).join(" ");
    const state = !member.connected ? "Disconnected · Passes" : member.ready ? "Ready" : "Planning";
    return `<article class="${classes}"><header><b>${escapeHtml(member.character_name)}</b><span>${escapeHtml(member.role)}${member.is_you ? " · You" : ""}</span></header><small>${escapeHtml(member.username)} · ${state}</small></article>`;
  }).join("");
  $("#multiplayer-host-time").hidden = !status.is_host;
  $("#multiplayer-time-amount").value = status.time_amount || 1;
  $("#multiplayer-time-unit").value = status.time_unit || "moment";
  $("#multiplayer-intensity").value = status.intensity || "normal";
  $("#btn-multiplayer-ready").textContent = status.your_ready ? "NOT READY — EDIT PLAN" : "READY";
  $("#btn-multiplayer-ready").classList.toggle("btn-ghost", !!status.your_ready);
  $("#btn-multiplayer-ready").classList.toggle("btn-primary", !status.your_ready);
  $("#btn-multiplayer-ready").disabled = !!status.resolving;
  $("#btn-multiplayer-resolve").disabled = !!status.resolving;
  $("#btn-advance").textContent = status.your_ready ? "READY ✓" : "READY";
  $("#btn-advance").disabled = !!status.resolving || !!status.your_ready;
  $("#multiplayer-error").hidden = !status.last_error;
  $("#multiplayer-error").textContent = status.last_error || "";
  if (APP.state) {
    APP.state.queued_actions = status.your_actions || [];
    renderQueuedActions(APP.state.queued_actions);
  }
}

async function refreshMultiplayerStatus(showNewResult = true) {
  if (!APP.accountsEnabled || !APP.account) return;
  try {
    const status = await apiGet(`/api/multiplayer/status?since_round=${APP.multiplayerLastResult || 0}`);
    if (status.result && showNewResult) {
      APP.multiplayerLastResult = status.last_result_round || APP.multiplayerLastResult;
      appendStoryEntries(status.result.story || []);
      (status.result.notifications || []).forEach((note) => showToast(note.message || note, "notify"));
      const latest = await apiGet("/api/state");
      APP.campaignActive = latest.campaign_active;
      renderState(latest.state);
      playSfx("time_skip");
    } else if (status.last_result_round) {
      APP.multiplayerLastResult = Math.max(APP.multiplayerLastResult, status.last_result_round);
    }
    renderMultiplayer(status);
  } catch (error) {
    console.error("Multiplayer poll failed", error);
  }
}

function startMultiplayerPolling() {
  clearInterval(APP.multiplayerPoll);
  APP.multiplayerPoll = setInterval(() => refreshMultiplayerStatus(true), 2500);
}

$("#btn-multiplayer").addEventListener("click", async () => {
  await refreshMultiplayerStatus(false);
  openModal("modal-multiplayer");
});
$("#btn-multiplayer-create").addEventListener("click", async () => {
  try {
    await apiPost("/api/multiplayer/create", {});
    window.location.reload();
  } catch (error) { showToast(error.message, "danger"); }
});
$("#form-multiplayer-join").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await apiPost("/api/multiplayer/join", {
      join_code: $("#multiplayer-join-code").value.trim().toUpperCase(),
      character_name: $("#multiplayer-character-name").value.trim(),
      background: $("#multiplayer-character-background").value.trim(),
    });
    window.location.reload();
  } catch (error) { showToast(error.message, "danger"); }
});
$("#btn-multiplayer-ready").addEventListener("click", async () => {
  try { renderMultiplayer(await apiPost("/api/multiplayer/ready", { ready: !APP.multiplayer?.your_ready })); }
  catch (error) { showToast(error.message, "danger"); }
});
$("#btn-multiplayer-save-time").addEventListener("click", async () => {
  try {
    renderMultiplayer(await apiPost("/api/multiplayer/time", {
      amount: Number($("#multiplayer-time-amount").value || 1), unit: $("#multiplayer-time-unit").value,
      intensity: $("#multiplayer-intensity").value,
    }));
    showToast("Shared time advance saved.", "notify");
  } catch (error) { showToast(error.message, "danger"); }
});
$("#btn-multiplayer-resolve").addEventListener("click", async () => {
  try { await apiPost("/api/multiplayer/resolve", {}); await refreshMultiplayerStatus(false); }
  catch (error) { showToast(error.message, "danger"); }
});
$("#btn-multiplayer-leave").addEventListener("click", async () => {
  if (!window.confirm(APP.multiplayer?.is_host ? "Close this multiplayer room and return to your original single-player campaign?" : "Leave this multiplayer campaign?")) return;
  try { await apiPost("/api/multiplayer/leave", {}); window.location.reload(); }
  catch (error) { showToast(error.message, "danger"); }
});

function showAuthError(message) {
  const box = $("#auth-error");
  box.textContent = message || "Unable to sign in.";
  box.hidden = false;
}

async function finishGameBoot() {
  const [settings, st] = await Promise.all([apiGet("/api/settings"), apiGet("/api/state")]);
  APP.soundEnabled = !!settings.sound_enabled;
  APP.musicEnabled = settings.music_enabled !== false;
  APP.musicVolume = Number(settings.music_volume ?? .35);
  setMusicWidgetVolume(APP.musicVolume, false);
  APP.animationsEnabled = !!settings.animations_enabled;
  APP.campaignActive = st.campaign_active;
  renderState(st.state);
  $("#hdr-ai").textContent = aiStatusLabel(st);
  if (st.campaign_active) {
    $("#story-feed").innerHTML = "";
    const multiplayerState = st.state?._multiplayer;
    if (multiplayerState?.active) {
      APP.multiplayerLastResult = Number(multiplayerState.last_result_round || 0);
      renderMultiplayer(multiplayerState);
      const privateChronicle = Array.isArray(st.state._multiplayer_chronicle)
        ? st.state._multiplayer_chronicle : [];
      if (privateChronicle.length) appendStoryEntries(privateChronicle);
      else appendStoryEntries([{
        text: "Your private Chronicle begins here. Nearby scenes, shared events, and reports will appear as your character learns them.",
        tag: "system", multiplayer_scope: "local",
      }]);
    } else {
      appendStoryEntries(Array.isArray(st.tactical_story) && st.tactical_story.length ? st.tactical_story : [{ text: "Welcome back to " + (st.state.world || "Worldwalker") + ".", tag: "system" }]);
    }
  } else {
    appendStoryEntries([
      { text: "Welcome to Worldwalker.", tag: "system" },
      { text: "You stand at the threshold of endless possibilities.", tag: "system" },
      { text: "The road ahead is long, but every legend begins with a single choice.", tag: "system" },
      { text: "What will you do?", tag: "system" },
    ]);
    await refreshWelcomeSaveCount();
    openModal("modal-welcome");
  }
  initCollapsiblePanels();
  refreshUsagePill();
  if (APP.accountsEnabled) {
    await refreshMultiplayerStatus(false);
    startMultiplayerPolling();
  }
  await maybeShowPatchNotes();
}

$("#form-login").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#auth-error").hidden = true;
  try {
    const result = await apiPost("/api/auth/login", {
      username: $("#login-username").value.trim(), password: $("#login-password").value,
    });
    applyAccountSession({ accounts_enabled: true, user: result.user, csrf_token: result.csrf_token, invite_required: !$("#invite-code-row").hidden });
    closeModal("modal-auth");
    await finishGameBoot();
  } catch (error) { showAuthError(error.message); }
});

$("#form-register").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#auth-error").hidden = true;
  try {
    const result = await apiPost("/api/auth/register", {
      username: $("#register-username").value.trim(), password: $("#register-password").value,
      invite_code: $("#register-invite").value,
    });
    applyAccountSession({ accounts_enabled: true, user: result.user, csrf_token: result.csrf_token, invite_required: !$("#invite-code-row").hidden });
    closeModal("modal-auth");
    await finishGameBoot();
  } catch (error) { showAuthError(error.message); }
});

async function signOutAccount() {
  try { await apiPost("/api/auth/logout", {}); } catch (_) { /* reload still clears stale UI state */ }
  APP.authToken = "";
  persistAuthToken("");
  window.location.reload();
}
$("#btn-account").addEventListener("click", signOutAccount);
$("#btn-welcome-signout").addEventListener("click", signOutAccount);

async function boot() {
  try {
    const auth = await apiGet("/api/auth/session");
    setHostConnectionState(true);
    applyAccountSession(auth);
    if (auth.accounts_enabled && !auth.authenticated) {
      openModal("modal-auth");
      return;
    }
    await finishGameBoot();
  } catch (e) {
    console.error(e);
    setHostConnectionState(false, "The game server did not respond. Keep Phone Mode open on the PC, prevent the PC from sleeping, and then try again.");
  }
}
initMobileExperience();
boot();
