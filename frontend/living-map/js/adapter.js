/* ==========================================================================
   WorldwalkerStateAdapter  —  REAL CAMPAIGN MIRROR

     Worldwalker save bundle  (sample_data/real_naruto_save.json, a COPY)
             |
             v
     WorldwalkerStateAdapter        (this file — pure, no DOM, no mutation)
             |
             v
     LivingMapState                 (same shape prototype.js buildStateFromData() makes)
             |
             v
     existing map renderer          (unchanged)

   Read-only. Nothing here writes to the save, the real game, or the network.
   It reuses Worldwalker's OWN concepts where they exist (map_snapshot-style
   nodes, WORLD_TERRITORIES, canon timeline, reputation, faction_clocks,
   npc_intentions, world_events, quests, campaign_direction, chapter_summaries).
   ========================================================================== */

(function (global) {
  "use strict";

  const slug = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "x";
  const norm = (s) => String(s || "").toLowerCase().replace(/[’'`]/g, "'").replace(/\s+/g, " ").trim();
  const clampNum = (v, a, b) => (v < a ? a : v > b ? b : v);
  const uniq = (arr) => Array.from(new Set(arr.filter(Boolean)));
  const NPC_ACCENTS = ["#8fb3c7", "#e6a23c", "#7fbf8f", "#dd8aa0", "#9a6ec2", "#5fae6f", "#c98a4a", "#6fb0b7", "#d8b878", "#b98a6a"];
  const accentFor = (name) => { let h = 0; for (const c of String(name)) h = (h * 31 + c.charCodeAt(0)) | 0; return NPC_ACCENTS[Math.abs(h) % NPC_ACCENTS.length]; };
  const initialsFor = (name) => {
    const parts = String(name || "?").trim().split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return String(name || "?").slice(0, 2).toUpperCase();
  };
  const sceneForLocation = (locName) => {
    const l = norm(locName);
    if (l.includes("rain") || l.includes("amegakure") || l.includes("ame")) return "assets/scenes/naruto_amegakure.webp";
    if (l.includes("konoha") || l.includes("leaf")) return "assets/scenes/naruto_konohagakure.webp";
    if (l.includes("sand") || l.includes("suna")) return "assets/scenes/naruto_sunagakure.webp";
    if (l.includes("mist") || l.includes("kiri") || l.includes("water")) return "assets/scenes/naruto_kirigakure.webp";
    if (l.includes("toad") || l.includes("myoboku") || l.includes("shrine") || l.includes("forest") || l.includes("passage")) return "assets/scenes/forest_path.webp";
    if (l.includes("bridge") || l.includes("front") || l.includes("battle")) return "assets/scenes/battlefield_dusk.webp";
    return "assets/scenes/academy_classroom.webp";
  };

  /* ---------------------------------------------------------------- location registry */
  function makeResolver(registry) {
    const entries = (registry && registry.entries) || [];
    const byNorm = new Map();
    for (const e of entries) {
      byNorm.set(norm(e.name), e);
      for (const a of e.aliases || []) byNorm.set(norm(a), e);
    }
    // longest keys first so "land of water" beats "water"
    const keys = Array.from(byNorm.keys()).sort((a, b) => b.length - a.length);

    const canonNames = new Set(entries.map((e) => norm(e.name)));
    function resolve(rawName) {
      const q = norm(rawName);
      if (!q) return { resolved: false, query: rawName };
      if (byNorm.has(q)) { const e = byNorm.get(q); return hit(e, rawName, q === norm(e.name) ? "name" : "alias"); }
      for (const k of keys) {
        if (k.length < 4) continue;
        if (q.includes(k) || k.includes(q)) { const e = byNorm.get(k); return hit(e, rawName, "fuzzy"); }
      }
      return { resolved: false, query: rawName };
    }
    function hit(e, rawName, via) {
      return {
        resolved: true, query: rawName, id: e.id, name: e.name, x: e.x, y: e.y,
        kind: e.kind, region: e.region || null, parent: e.parent || null,
        via, approx: !!e.approx || via === "fuzzy",
      };
    }
    return { resolve, entries, canonNames };
  }

  /* ---------------------------------------------------------------- world_events string parsing */
  function parseWorldEventLine(line) {
    const text = String(line || "").trim();
    if (!text) return null;
    // "Month D, Year Y — Title\nLocation: X. summary"
    const locM = text.match(/location:\s*([^.\n]+)\.?/i);
    let title = text.split("\n")[0].replace(/\s+—\s+/, " — ");
    const dateM = title.match(/^([A-Z][a-z]+ \d+, Year \d+)\s+—\s+(.+)$/);
    if (dateM) title = dateM[2];
    const clashM = text.match(/^⚔\s*(.+?) and (.+?) clash over (.+?),/i);
    let importance = "low";
    if (/⚔|clash|assault|attack|war|invasion|massacre/i.test(text)) importance = "high";
    else if (/mission|commitment is now due|delegation|summit/i.test(text)) importance = "medium";
    return {
      raw: text, title: title.length > 120 ? title.slice(0, 117) + "…" : title,
      location: locM ? locM[1].trim() : (clashM ? clashM[3].trim() : ""),
      date: dateM ? dateM[1] : "",
      combat: /⚔|clash|assault|attack|war|invasion|massacre|battle/i.test(text),
      importance,
      summary: text.replace(/^[^.]*\.\s*/, "").trim().slice(0, 400),
    };
  }

  /* ---------------------------------------------------------------- NPC merge */
  const PLAYER_FACTIONS = new Set(["Akatsuki"]);
  function mergeNpcs(st, panels) {
    const out = {}; // name -> record
    const get = (name) => (out[name] || (out[name] = { name, roles: [], goals: [], locs: [], companion: false, mentor: false, nemesis: false }));

    // Worldwalker's own derived relationship snapshot (from /api/panels) is the
    // best source when it's available — it already merges memories + contacts.
    const rv = panels && panels.relationships_view;
    for (const row of (rv && rv.people) || []) {
      if (!row || !row.name) continue;
      const r = get(row.name);
      if (row.label && row.label !== "Unknown") r.roles.push(row.label);
      if (row.goal && row.goal !== "Unknown") r.goals.push(row.goal);
      if (row.last_known_location && row.last_known_location !== "Unknown") r.locs.push(row.last_known_location);
      if (typeof row.score === "number") r.panelScore = row.score;
      if (row.nemesis) r.nemesis = true;
      r.recurring = true;
    }

    for (const c of st.companions || []) {
      if (!c || !c.name) continue;
      const r = get(c.name); r.companion = true; if (c.role) r.roles.push(c.role);
    }
    const intents = st.npc_intentions || {};
    for (const [name, v] of Object.entries(intents)) {
      if (!v || typeof v !== "object") continue;
      const r = get(name);
      if (v.relationship) r.roles.push(v.relationship);
      if (v.opinion_of_player) r.opinion = v.opinion_of_player;
      if (v.goal) r.goals.push(v.goal);
      if (v.location) r.locs.push(v.location);
      if (v.last_known_location) r.locs.push(v.last_known_location);
      if (v.nemesis) r.nemesis = true;
      if (v.recurring) r.recurring = true;
    }
    const cont = st.npc_continuity || {};
    for (const [name, v] of Object.entries(cont)) {
      if (!v || typeof v !== "object") continue;
      const r = get(name);
      if (v.companion) r.companion = true;
      if (v.nemesis) r.nemesis = true;
      if (v.role && v.role !== "NPC") r.roles.push(v.role);
      if (v.attitude && v.attitude !== "Unknown") r.attitude = v.attitude;
      if (v.goal) r.goals.push(v.goal);
      if (v.last_known_location && v.last_known_location !== "Unknown") r.locs.push(v.last_known_location);
    }
    for (const [name, v] of Object.entries(st.npc_schedules || {})) {
      if (v && v.location) get(name).locs.push(v.location);
      if (v && v.goal) get(name).goals.push(v.goal);
    }
    for (const u of (st.campaign_direction || {}).unresolved_characters || []) {
      if (!u || !u.name) continue;
      const r = get(u.name);
      if (u.location) r.locs.push(u.location);
      if (u.goal) r.goals.push(u.goal);
    }
    for (const p of (st.life_context || {}).people || []) {
      if (!p || !p.name) continue;
      const r = get(p.name);
      if (p.role) r.roles.push(p.role);
      if (p.active_goal) r.goals.push(p.active_goal);
    }
    // contacts: keep only "person" kind (groups belong in factions)
    for (const [name, v] of Object.entries(st.contacts || {})) {
      if (!v || v.kind === "group") continue;
      const r = get(name);
      if (v.last_known_location && v.last_known_location !== "Unknown") r.locs.push(v.last_known_location);
      if (typeof v.relationship === "number" && v.relationship) r.contactScore = v.relationship;
      r.contact = true;
    }
    // drop the player and pure faction names
    delete out[st.name];
    for (const f of ["Konohagakure", "Sunagakure", "Kirigakure", "Kumogakure", "Iwagakure", "Amegakure", "Iron Country", "Akatsuki"]) delete out[f];

    // finalize
    for (const r of Object.values(out)) {
      r.role = uniq(r.roles)[0] || (r.companion ? "Companion" : "Contact");
      r.mentor = /mentor|sensei|teacher/i.test(r.role) || /mentor|sensei/i.test(r.attitude || "");
      r.goal = uniq(r.goals)[0] || "";
      r.location = uniq(r.locs)[0] || "";
      let sc = 10;
      if (r.companion) sc = 58;
      else if (r.mentor) sc = 36;
      else if (r.recurring) sc = 22;
      if (r.nemesis) sc = -42;
      if (typeof r.contactScore === "number" && r.contactScore) sc = clampNum(r.contactScore, -100, 100);
      if (typeof r.panelScore === "number" && r.panelScore) sc = clampNum(r.panelScore, -100, 100);
      r.score = sc;
      r.sub = (r.opinion || r.attitude || r.role || "Contact").toString();
      if (r.sub.length > 60) r.sub = r.sub.slice(0, 57) + "…";
    }
    return out;
  }

  /* ---------------------------------------------------------------- chronicle classification */
  function classifyChron(text, hint) {
    const t = norm(text);
    if (hint) return hint;
    if (/canon|uchiha massacre|nine-tails|akatsuki is founded|kannabi/i.test(t)) return "canon";
    if (/train|drill|sage mode|master|senjutsu|spar|chakra control/i.test(t)) return "training";
    if (/travel|road|route|journey|depart|set out|arrive/i.test(t)) return "travel";
    if (/clash|battle|kill|assault|attack|combat|strike|defeat|fought|dead/i.test(t)) return "combat";
    if (/nagato|konan|jiraiya|kisame|orochimaru|kagari|hanzō|hanzo|relationship|ally|betray/i.test(t)) return "relationship";
    if (/quest|objective|mission|bounty|assignment/i.test(t)) return "mission";
    if (/investigat|research|scout|intel|lead connects/i.test(t)) return "intrigue";
    if (/election|government|tax|charity|logistics|province|province|recruit|province/i.test(t)) return "development";
    return "world";
  }

  /* ================================================================ MAIN */
  function buildLivingMapState(bundle, opts) {
    opts = opts || {};
    const registry = opts.registry || { entries: [] };
    const canonTL = opts.canonTimeline || { events: [] };
    const regionDefs = opts.regionDefs || {};       // from map_regions.json .regions
    const factionDefs = opts.factionDefs || {};     // .factions
    const dangerColors = opts.dangerColors || {};
    const relColors = opts.relationshipColors || {};
    const panels = opts.panels || null;             // /api/panels (live mode only)

    const st = (bundle && bundle.state) || {};
    const camp = (bundle && bundle.campaign) || {};
    const R = makeResolver(registry);

    const diag = {
      saveFile: opts.saveFileName || "real_naruto_save.json",
      saveVersion: bundle.version || "?",
      schemaVersion: bundle.schema_version || st.schema_version || "?",
      savedAt: bundle.saved_at || "?",
      world: st.world || camp.world || "?",
      campaignName: st.name || camp.name || "?",
      turn: st.turn || camp.turn || 0,
      worldTime: st.world_time || camp.world_time || "",
      canonDay: st.canon_day,
      resolvedLocations: 0, unresolvedLocations: 0, unresolvedNames: [],
      mappedNpcs: 0, unmappedNpcs: 0, unmappedNpcNames: [],
      activeQuests: 0, worldEvents: 0, canonEventsFired: (st.canon_events_fired || []).length,
      organizations: 0, factionClocks: Object.keys(st.faction_clocks || {}).length,
      travelGraphNodes: 0, chronicleEntries: 0,
      notes: [], resolutions: [],
      playerLocation: null, eventLocations: [], npcLocations: [],
      approximateLocations: [], aliasMatches: [],
    };
    const unresolvedSet = new Set();
    function tryResolve(name, tag) {
      const r = R.resolve(name);
      const raw = name == null ? "" : String(name).trim();
      if (r.resolved) {
        diag.resolvedLocations++;
        diag.resolutions.push({ tag: tag || "", raw, name: r.name, via: r.via, approx: r.approx });
        if (r.approx && raw) diag.approximateLocations.push(`${raw} → ${r.name} (${r.via})`);
        if ((r.via === "alias" || r.via === "fuzzy") && raw) diag.aliasMatches.push(`${raw} → ${r.name}`);
      } else if (raw) {
        diag.unresolvedLocations++; unresolvedSet.add(raw);
      }
      return r;
    }

    /* ---- PLAYER ---- */
    const aff0 = (st.affiliations || [])[0] || {};
    const playerLocRes = tryResolve(st.location, 'player');
    const sp = st.special || {};
    const knownJutsu = Array.isArray(sp["Known Jutsu"]) ? sp["Known Jutsu"] : [];
    const abilities = uniq([...knownJutsu, ...Object.keys(st.skills || {}), ...Object.keys(st.ability_registry || {})]).slice(0, 6);
    const powerTier = (((st.capability_profile || {}).power || {}).player_facing || {}).balanced || {};
    const goals = [];
    const dir = st.campaign_direction || {};
    if (dir.primary_goal) goals.push({ text: dir.primary_goal, tag: "ambition", note: "Campaign primary goal" });
    for (const q of st.quests || []) {
      if (!q || String(q.status || "").toLowerCase() !== "active") continue;
      diag.activeQuests++;
      for (const o of (q.objectives || [])) {
        if (String(o.status || "").toLowerCase() === "active")
          goals.push({ text: o.text, tag: "mission", note: `${q.name} · ${o.progress || 0}%` });
      }
    }
    for (const arc of st.campaign_arcs || []) {
      if (!arc || String(arc.status || "").toLowerCase() !== "active") continue;
      goals.push({ text: arc.title, tag: arc.kind === "investigation" ? "intrigue" : arc.kind === "relationship" ? "relationship" : "ambition", note: `Arc · ${arc.phase || arc.progress + "%"}` });
    }
    for (const [, thr] of Object.entries(st.story_threads || {})) {
      if (!thr || thr.kind !== "agenda" || String(thr.status).toLowerCase() !== "active") continue;
      goals.push({ text: thr.title, tag: "training", note: thr.detail || "Standing agenda" });
    }

    const player = {
      id: "player", name: st.name || "Player", monogram: (st.name || "P").trim()[0] || "P",
      age: st.age != null ? String(st.age) : "",
      affiliation: aff0.faction || st.world || "",
      rank: sp["Shinobi Rank"] || powerTier.name || st.starting_power_band || "",
      homeLocation: playerLocRes.resolved ? playerLocRes.id : null,
      homeLocationRaw: st.location || "",
      x: playerLocRes.resolved ? playerLocRes.x : 0.5,
      y: playerLocRes.resolved ? playerLocRes.y : 0.5,
      locResolved: playerLocRes.resolved, locApprox: !!playerLocRes.approx,
      health: { cur: num(st.hp, 0), max: num(st.hp_max, num(st.hp, 1) || 1) },
      chakra: { cur: num(st.resource, 0), max: num(st.resource_max, num(st.resource, 1) || 1) },
      chakraControl: null,
      resourceName: st.resource_name || "Chakra",
      stats: st.stats && typeof st.stats === "object" ? st.stats : null,
      powerTier: powerTier.name || "",
      natures: [{ name: sp["Nature Affinity"] || "Unknown", known: !!sp["Nature Affinity"] && sp["Nature Affinity"] !== "Unknown" }],
      abilities: abilities.length ? abilities : ["(no abilities recorded)"],
      goals: goals.slice(0, 7).length ? goals.slice(0, 7) : [{ text: "(no active goals recorded)", tag: "ambition", note: "" }],
      status: st.position || "Active",
    };

    /* ---- NPCs + relationships ---- */
    const merged = mergeNpcs(st, panels);
    const npcs = {}, relationships = {};
    const npcRows = Object.values(merged);
    const playerNameKey = norm(st.name || "");
    const sharedOrganizationMembers = new Set();
    const organizationsForTracking = [
      ...Object.values(st.organizations || {}),
      ...((((panels || {}).organization_roster || {}).organizations) || []),
    ];
    for (const organization of organizationsForTracking) {
      if (!organization || typeof organization !== "object") continue;
      const rawMembers = organization.members || organization.roster || [];
      const memberNames = Array.isArray(rawMembers)
        ? rawMembers.map((member) => typeof member === "string" ? member : member && member.name)
        : Object.keys(rawMembers || {});
      const normalizedMembers = memberNames.filter(Boolean).map(norm);
      const playerOwnsOrBelongs = normalizedMembers.includes(playerNameKey)
        || organization.player_member === true || organization.player_owned === true
        || norm(organization.leader || organization.owner || "") === playerNameKey;
      if (playerOwnsOrBelongs) normalizedMembers.forEach((name) => sharedOrganizationMembers.add(name));
    }
    // rank for the left panel: companions + mentors + strongest ties
    npcRows.sort((a, b) => (b.companion - a.companion) || (Math.abs(b.score) - Math.abs(a.score)));
    npcRows.forEach((r, i) => {
      const id = slug(r.name);
      const locRes = tryResolve(r.location, 'npc:' + r.name);
      const mapped = locRes.resolved;
      if (mapped) diag.mappedNpcs++; else { diag.unmappedNpcs++; if (r.location || r.companion || r.recurring) diag.unmappedNpcNames.push(r.name); }
      // jitter co-located npcs so markers don't perfectly stack
      const jx = ((i % 3) - 1) * 0.012, jy = (Math.floor(i / 3) % 3 - 1) * 0.012;
      npcs[id] = {
        id, name: r.name, role: r.role, homeLocation: mapped ? locRes.id : null,
        trueLocation: mapped ? locRes.id : null,
        x: mapped ? locRes.x + jx : null, y: mapped ? locRes.y + jy : null,
        trueX: mapped ? locRes.x + jx : null, trueY: mapped ? locRes.y + jy : null,
        scope: r.companion || r.mentor || r.nemesis ? "regional" : "local",
        importance: r.companion ? "high" : r.nemesis ? "high" : "medium",
        infoStatus: "confirmed",
        status: r.location ? `Last known: ${r.location}` : (r.companion ? "Inner circle" : "Contact"),
        affiliations: r.companion ? [aff0.faction || "Akatsuki"] : [],
        recent: r.opinion || r.attitude || "—",
        bio: uniq([r.opinion, r.goal].filter(Boolean)).join("  ·  ") || r.role || "A figure in this campaign.",
        abilities: [], initials: initialsFor(r.name), accent: accentFor(r.name),
        scene: sceneForLocation(r.location || r.role),
        _unmapped: !mapped, _locRaw: r.location || "",
        _mapTrackEligible: !!(r.companion || r.mentor || r.nemesis
          || Math.abs(Number(r.score) || 0) >= 20
          || sharedOrganizationMembers.has(norm(r.name))),
      };
      if (i < 6) relationships[id] = { score: r.score, sub: r.sub };
    });

    /* ---- LOCATIONS ---- */
    const locations = {};
    const territories = { land_of_fire: "konoha", land_of_wind: "suna", land_of_rain: "ame", land_of_water: "kiri", land_of_lightning: "kumo", land_of_earth: "iwa", land_of_rivers: "konoha" };
    const discovered = new Set((st.discovered_locations || []).map(norm));
    const parsedEvents = (st.world_events || []).map(parseWorldEventLine).filter(Boolean);
    diag.worldEvents = parsedEvents.length;

    for (const e of R.entries) {
      if (!(e.kind === "village" || e.kind === "nation")) continue;
      const devs = parsedEvents
        .filter((pe) => pe.location && R.resolve(pe.location).id === e.id)
        .slice(-3).map((pe) => pe.title);
      const repl = (st.reputation || {})[e.name];
      let status = "Independent";
      if (typeof repl === "number") status = repl > 40 ? "Aligned with you" : repl < -5 ? "Wary of you" : "Neutral toward you";
      if (norm(e.name) === "amegakure") status = "Akatsuki power base";
      locations[e.id] = {
        id: e.id, type: e.kind === "nation" ? "village" : "village", name: e.name,
        short: "", region: e.region || null, x: e.x, y: e.y, scope: "world",
        importance: norm(e.name) === "amegakure" ? "critical" : "high",
        leaderLabel: "Controller", leader: (opts.territoriesByName && opts.territoriesByName[e.name]) || e.name,
        status, people: npcRows.filter((r) => R.resolve(r.location).id === e.id).map((r) => slug(r.name)).filter((s) => npcs[s]),
        developments: devs.length ? devs : ["No local developments recorded in this save."],
        orgs: [], scene: sceneForLocation(e.name), discovered: discovered.has(norm(e.name)),
      };
    }
    // local Konoha points
    for (const e of R.entries) {
      if (e.kind !== "landmark" || e.parent !== "konoha") continue;
      locations[e.id] = {
        id: e.id, type: "landmark", name: e.name, parent: "konoha", region: e.region || "land_of_fire",
        x: e.x, y: e.y, scope: "local", importance: "low",
        inspector: { summary: "Canonical Konoha site (from the prototype location registry)." },
      };
    }

    /* ---- WORLD EVENTS (map markers where located) — newest first, deduped ---- */
    const worldEvents = {};
    const seenSig = new Set();
    parsedEvents.slice().reverse().forEach((pe, idx) => {
      const lr = pe.location ? tryResolve(pe.location, 'event') : { resolved: false };
      if (!lr.resolved) return;
      const sig = norm(pe.title) + "@" + lr.id;
      if (seenSig.has(sig)) return;
      seenSig.add(sig);
      if (Object.keys(worldEvents).length >= 8) return;
      const id = "we_" + slug(pe.title).slice(0, 24) + "_" + idx;
      worldEvents[id] = {
        id, type: "world_event", name: pe.title,
        x: lr.x + (idx % 3 - 1) * 0.012 + 0.016, y: lr.y - 0.018, region: lr.region || null,
        scope: pe.importance === "high" ? "world" : "regional",
        importance: pe.importance, status: "active", infoStatus: "confirmed",
        inspector: { summary: pe.summary || pe.raw },
      };
    });

    /* ---- CANON (primary approaching event) ---- */
    const cd = num(st.canon_day, -7);
    const upcoming = (canonTL.events || [])
      .filter((ev) => typeof ev.day === "number" && ev.day > cd && !ev.historical_only)
      .sort((a, b) => a.day - b.day);
    const dirCanon = dir.approaching_canon_event || {};
    const primaryEv = upcoming[0] || (dirCanon.title ? { title: dirCanon.title, location: dirCanon.location, day: cd + Math.round((dirCanon.days_until || 0)), summary: dirCanon.summary } : null);
    let primaryCanon = null;
    if (primaryEv) {
      const lr = tryResolve(primaryEv.location, 'canon');
      primaryCanon = {
        id: slug(primaryEv.title), name: primaryEv.title,
        daysOut: Math.max(0, Math.round((primaryEv.day - cd))),
        triggered: false,
        x: lr.resolved ? lr.x : 0.5, y: lr.resolved ? lr.y : 0.5,
        locResolved: lr.resolved, locationRaw: primaryEv.location || "",
        impactRegion: lr.region || "land_of_fire", impactDanger: "high", activeDays: 5,
        banner: primaryEv.banner || "",
        summary: primaryEv.summary || dirCanon.summary || "",
      };
    } else {
      primaryCanon = { id: "none", name: "No further canon events on record", daysOut: 0, triggered: true, x: 0.5, y: 0.5, impactRegion: "land_of_fire", impactDanger: "low", activeDays: 0, summary: "" };
    }
    const firedCanon = (st.canon_events_fired || []).map((s) => {
      const m = String(s).match(/day:(-?\d+):(.+)/);
      return m ? { day: +m[1], title: m[2] } : { day: 0, title: String(s) };
    });

    /* ---- REGIONS ---- */
    const regions = {};
    const repStance = (name) => {
      const v = (st.reputation || {})[name];
      if (typeof v !== "number") return "neutral";
      if (v >= 60) return "friendly";
      if (v >= 10) return "neutral";
      if (v > -5) return "neutral";
      if (v > -30) return "strained";
      return "hostile";
    };
    for (const [rid, rdef] of Object.entries(regionDefs)) {
      const ctrl = territories[rid] || rdef.controller;
      const factionName = { konoha: "Konohagakure", suna: "Sunagakure", ame: "Amegakure", kiri: "Kirigakure", kumo: "Kumogakure", iwa: "Iwagakure" }[ctrl] || rdef.name;
      regions[rid] = Object.assign({}, rdef, {
        controller: ctrl,
        relationship: repStance(factionName),
        danger: "low",
      });
    }
    // approaching canon event nudges its region
    if (primaryCanon && primaryCanon.daysOut > 0 && primaryCanon.daysOut < 120 && regions[primaryCanon.impactRegion])
      regions[primaryCanon.impactRegion].danger = "moderate";

    /* ---- ORGANIZATIONS (roster -> Amegakure/Akatsuki notes) ---- */
    const orgs = st.organizations || {};
    diag.organizations = Object.keys(orgs).length;
    const orgRosterLines = [];
    for (const o of Object.values(orgs)) {
      if (!o || !o.name) continue;
      const members = Object.keys(o.members || {});
      orgRosterLines.push(`${o.name}: ${members.slice(0, 6).join(", ")}${members.length > 6 ? "…" : ""}`);
      if (locations.ame) locations.ame.orgs = uniq([...(locations.ame.orgs || []), o.name]);
    }

    /* ---- CHRONICLE (recent, classified) ---- */
    const chron = [];
    const push = (day, type, text) => { if (text) chron.push({ day: day || 0, type, text: String(text).slice(0, 260) }); };
    for (const m of (st.world_milestones || []).slice(-6)) push(m.turn, "development", `${m.title || m.heading || "Milestone"} — ${m.detail || ""}`);
    for (const ev of firedCanon) push(0, "canon", `CANON — ${ev.title}`);
    for (const c of (st.campaign_canon || []).slice(-6)) push(c.turn, classifyChron(c.action + " " + c.outcome, "action"), `${trimTo(c.action, 90)} → ${trimTo(c.outcome, 150)}`);
    for (const ch of (st.chapter_summaries || []).slice(-3)) push((ch.turns || [0]).slice(-1)[0], "development", `${ch.title || "Chapter"} — ${trimTo(ch.summary, 200)}`);
    for (const se of (st.simulation_events || []).filter((e) => (e.importance || 0) >= 25).slice(-10)) push(se.turn, classifyChron(se.summary), trimTo(se.summary, 220));
    for (const pe of parsedEvents.slice(-8)) push(0, pe.combat ? "combat" : "world", `${pe.date ? pe.date + " — " : ""}${pe.title}`);
    for (const t of st.timeline || []) push(st.turn, "canon", trimTo(t, 220));
    // dedupe + sort recent first
    const seen = new Set();
    const chronicle = chron.filter((e) => { const k = e.text.slice(0, 80); if (seen.has(k)) return false; seen.add(k); return true; })
      .sort((a, b) => (b.day || 0) - (a.day || 0)).slice(0, 42);
    diag.chronicleEntries = chronicle.length;

    /* ---- RISKS ---- */
    const risks = [];
    if (dir.next_obstacle) risks.push(dir.next_obstacle);
    for (const [name, v] of Object.entries(st.reputation || {})) {
      if (typeof v === "number" && v <= -10 && !PLAYER_FACTIONS.has(name)) risks.push(`Hostile standing: ${name} (${v})`);
    }
    let tp = 0;
    for (const [name, fc] of Object.entries(st.faction_clocks || {})) {
      if (fc && fc.status === "turning_point" && !PLAYER_FACTIONS.has(name) && tp < 3) { risks.push(`${name} has reached a strategic turning point`); tp++; }
    }
    if (primaryCanon && primaryCanon.daysOut > 0) risks.push(`Approaching canon: ${primaryCanon.name} (~${primaryCanon.daysOut} days)`);

    /* ---- diagnostics finalize ---- */
    diag.unresolvedNames = Array.from(unresolvedSet).sort();
    diag.unresolvedLocations = diag.unresolvedNames.length;
    diag.unmappedNpcNames = Object.values(npcs).filter((n) => n._unmapped)
      .map((n) => n.name + (n._locRaw ? ` (recorded: ${n._locRaw})` : " (no location on record)")).sort();
    diag.unmappedNpcs = Object.values(npcs).filter((n) => n._unmapped).length;
    diag.mappedNpcs = Object.values(npcs).filter((n) => !n._unmapped).length;
    diag.mappedNpcNames = Object.values(npcs).filter((n) => !n._unmapped).map((n) => n.name).sort();
    diag.travelGraphNodes = (panels && panels.travel_graph && panels.travel_graph.nodes ? panels.travel_graph.nodes.length : null)
      || R.entries.filter((e) => ["village", "nation", "landmark", "region", "battlefield"].includes(e.kind)).length;
    diag.orgRosterLines = orgRosterLines;
    diag.primaryCanon = primaryCanon ? `${primaryCanon.name} (~${primaryCanon.daysOut} days, ${primaryCanon.locResolved ? "located" : "not located"})` : "none";
    // resolution breakdown
    const rf = (tag) => diag.resolutions.filter((x) => x.tag === tag || (tag === "npc" && x.tag.startsWith("npc:")));
    diag.playerLocation = (() => {
      const p = diag.resolutions.find((x) => x.tag === "player");
      return p ? `${p.raw} → ${p.name}${p.approx ? " (Approximate)" : ""}` : `${st.location || "?"} → unresolved`;
    })();
    diag.eventLocations = uniq(rf("event").map((x) => `${x.raw} → ${x.name}${x.approx ? " (Approximate)" : ""}`));
    diag.npcLocations = uniq(rf("npc").map((x) => `${x.tag.slice(4)} @ ${x.raw} → ${x.name}${x.approx ? " (Approximate)" : ""}`));
    diag.approximateLocations = uniq(diag.approximateLocations);
    diag.aliasMatches = uniq(diag.aliasMatches);
    diag.notes.push("Worldwalker's own Naruto coordinates (backend/worlds.py) sit ~0.10 south of Konoha/Suna/Amegakure on the shipped map webp; the registry uses artwork-measured placements instead.");
    diag.notes.push("state.relationships and state.npc_relationships are empty in this save; NPC ties were reconstructed from contacts + companions + npc_intentions + npc_continuity + campaign_direction.");
    diag.notes.push("No routes / travel_history / planned_route in this save — the real mirror is static (no moving entities).");
    diag.notes.push("No per-region danger in the save; Danger mode shows only the approaching canon event's region.");

    return {
      sourceKey: "real",
      sourceLabel: `Real Campaign Copy — ${st.name} / ${st.world}`,
      readOnly: true,
      era: narutoEra(st),
      season: (st.weather ? cap(st.weather) : "") || "",
      day: num(st.turn, 0),
      timelineLabel: st.world_time || "",
      player, relationships, npcs, locations, groups: {}, features: {}, worldEvents,
      transients: {}, routes: {}, scenarios: {},
      canon: { primary: primaryCanon }, primaryCanon,
      firedCanon,
      worldState: { konohaTension: 0 },
      risks: uniq(risks).slice(0, 8),
      chronicle,
      regions, factions: factionDefs, dangerColors, relationshipColors: relColors,
      diagnostics: diag,
    };
  }

  /* helpers */
  function num(v, d) { const n = Number(v); return Number.isFinite(n) ? n : d; }
  function cap(s) { s = String(s || ""); return s ? s[0].toUpperCase() + s.slice(1) : s; }
  function trimTo(s, n) { s = String(s || "").replace(/\s+/g, " ").trim(); return s.length > n ? s.slice(0, n - 1) + "…" : s; }
  function narutoEra(st) {
    const cd = num(st.canon_day, -7);
    if (cd < -4380) return "Pre-series — Founders era";
    if (cd < 0) return "Pre-series — before Naruto's graduation";
    if (cd < 330) return "Part I";
    if (cd < 1069) return "Part I — timeskip";
    if (cd < 1684) return "Shippūden";
    return "Post-war era";
  }

  /* ================================================================ LIVE
     Same builder, fed from Worldwalker's live GET APIs instead of a save file.
     payload = { state (/api/state .state), panels (/api/panels),
                 combat (/api/combat/state), meta:{version,busy,campaignActive} } */
  function buildLivingMapStateFromLive(payload, opts) {
    payload = payload || {};
    const st = payload.state || {};
    const meta = payload.meta || {};
    const bundle = {
      version: meta.version || st.campaign_created_version || "live",
      schema_version: st.schema_version,
      saved_at: "(live poll)",
      campaign: { name: st.name, world: st.world, turn: st.turn, world_time: st.world_time },
      state: st,
    };
    const L = buildLivingMapState(bundle, Object.assign({}, opts, {
      saveFileName: "LIVE — " + (st.name || "campaign") + " / " + (st.world || "?"),
      panels: payload.panels || null,
    }));
    L.sourceKey = "live";
    L.sourceLabel = `Live Worldwalker — ${st.name || "?"} / ${st.world || "?"}`;
    L.readOnly = true;
    L.timelineLabel = st.world_time || "";

    // per-node controller from Worldwalker's own map_snapshot (authoritative)
    const nodes = (payload.panels && payload.panels.map_data && payload.panels.map_data.nodes) || [];
    const nodeCtrl = {};
    for (const nd of nodes) {
      const rr = makeResolver(opts.registry || { entries: [] }).resolve(nd.name);
      if (rr.resolved && nd.controller && !/^unknown|unclaimed$/i.test(nd.controller)) nodeCtrl[rr.region || rr.id] = nd.controller;
    }
    for (const [rid, reg] of Object.entries(L.regions)) {
      const ctrlName = nodeCtrl[rid];
      if (ctrlName) {
        const slugMap = { Konohagakure: "konoha", Sunagakure: "suna", Amegakure: "ame", Kirigakure: "kiri", Kumogakure: "kumo", Iwagakure: "iwa", Akatsuki: "akatsuki" };
        reg.controller = slugMap[ctrlName] || reg.controller;
      }
    }

    // combat
    const cb = (payload.combat && payload.combat.combat) || {};
    L.combat = {
      active: !!(cb.active || cb.round || cb.enemy || cb.enemy_hp || cb.enemy_name),
      enemy: cb.enemy || cb.enemy_name || "an opponent",
      location: cb.location || st.location || "",
      round: cb.round || 0,
    };
    if (payload.combat && payload.combat.hp != null) {
      L.player.health = { cur: num(payload.combat.hp, L.player.health.cur), max: num(payload.combat.hp_max, L.player.health.max) };
      L.player.chakra = { cur: num(payload.combat.resource, L.player.chakra.cur), max: num(payload.combat.resource_max, L.player.chakra.max) };
    }

    L.live = { busy: !!meta.busy, campaignActive: meta.campaignActive !== false, wwVersion: meta.version || "" };
    L.travelGraph = (payload.panels && payload.panels.travel_graph) || null;
    L.diagnostics.notes = [
      "LIVE mode: Worldwalker is the only authority. This map only visualises what /api/state + /api/panels report.",
      "NPC ties/locations come from /api/panels relationships_view (Worldwalker's own relationship_snapshot) when present, else the raw state.",
      "Region controllers come from /api/panels map_data node controllers where they resolve to a region.",
      "Movement between polls is animated as a PRESENTATION transition (curved 2-point path unless travel_graph gives a real route) — not authoritative pathfinding.",
      "Worldwalker's own coordinate table is not used for placement; the artwork-aligned registry is.",
    ];
    return L;
  }

  global.WorldwalkerStateAdapter = { buildLivingMapState, buildLivingMapStateFromLive, makeResolver, parseWorldEventLine };
})(typeof window !== "undefined" ? window : globalThis);
