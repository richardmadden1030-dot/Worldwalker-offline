// The Action Deck is a local, context-aware front door to the same freeform
// AI composer. It never resolves an action by itself and never limits typing.
const ACTION_CATEGORIES = [
  { id: "recommended", label: "For you", icon: "◇" },
  { id: "people", label: "People", icon: "◎" },
  { id: "training", label: "Training", icon: "△" },
  { id: "travel", label: "Travel", icon: "↗" },
  { id: "missions", label: "Work", icon: "▣" },
  { id: "organization", label: "Group", icon: "♜" },
  { id: "combat", label: "Combat", icon: "⚔" },
  { id: "personal", label: "Personal", icon: "☾" },
  { id: "world", label: "World", icon: "✦" },
];
const ACTION_DURATION_LABELS = { moment: "", hour: "for the next hour", day: "for the next day", week: "for the next week", month: "for the next month" };
let actionDeckCategory = "recommended";
let actionDeckPerson = "";
let actionDeckDurationTouched = false;

function actionDeckStorageKey(kind) {
  return mobileCampaignKey(`action_deck_${kind}`);
}
function readActionDeckStore(kind) {
  try { const value = JSON.parse(localStorage.getItem(actionDeckStorageKey(kind)) || "[]"); return Array.isArray(value) ? value : []; }
  catch (_) { return []; }
}
function writeActionDeckStore(kind, rows) {
  try { localStorage.setItem(actionDeckStorageKey(kind), JSON.stringify(rows.slice(0, kind === "recent" ? 8 : 24))); }
  catch (_) { /* The action still remains usable when storage is unavailable. */ }
}
function actionDeckPeople(state = APP.state || {}) {
  const records = knownPersonRecords(state);
  const rows = [];
  const add = (person, fallback = {}) => {
    const record = person && typeof person === "object" ? person : { name: person, ...fallback };
    const name = String(record.name || record.display_name || "").trim();
    if (!name || normalizePersonName(name) === normalizePersonName(state.name) || rows.some((row) => normalizePersonName(row.name) === normalizePersonName(name))) return;
    const merged = { ...(records[name] || {}), ...record, name };
    if (actionPersonAvailable(merged)) rows.push(merged);
  };
  Object.entries(records).forEach(([name, record]) => add(record && typeof record === "object" ? { name, ...record } : { name }));
  (Array.isArray(state.companions) ? state.companions : []).forEach((row) => add(row));
  (Array.isArray(state._organization_roster?.members) ? state._organization_roster.members : []).forEach((row) => add(row));
  return rows.slice(0, 30);
}
function actionDeckLocations(state = APP.state || {}) {
  const names = new Set();
  Object.keys(state.location_details || {}).forEach((name) => names.add(name));
  const custom = Array.isArray(state.custom_locations) ? state.custom_locations : Object.values(state.custom_locations || {});
  custom.forEach((row) => names.add(typeof row === "object" ? row.name : row));
  (Array.isArray(state.travel_history) ? state.travel_history : []).forEach((row) => names.add(typeof row === "object" ? (row.destination || row.to || row.location) : row));
  names.delete(state.location);
  names.delete(undefined); names.delete("");
  return [...names].slice(0, 8);
}
function actionChoice(id, category, label, description, text, extra = {}) {
  return { id, category, label, description, text, duration: "moment", ...extra };
}
function personInteractionChoices(person, state = APP.state || {}) {
  const name = person.name;
  const role = String(person.position || person.role || "").toLowerCase();
  const isMember = Boolean(person.combat_support || person.member || person.reports_to || role || (state._organization_roster?.members || []).some((row) => normalizePersonName(row.name) === normalizePersonName(name)));
  return [
    actionChoice(`talk:${name}`, "people", `Talk with ${name}`, "Have a direct conversation about whatever matters now.", `Talk privately with ${name}`),
    actionChoice(`spend:${name}`, "people", `Spend time together`, `Strengthen or explore your relationship with ${name}.`, `Spend meaningful time with ${name}`, { duration: "hour" }),
    actionChoice(`advice:${name}`, "people", `Ask for advice`, `Ask ${name} for their honest view of your current situation.`, `Ask ${name} for advice about my current situation`),
    actionChoice(`help:${name}`, "people", `Offer help`, `Find out what ${name} needs and help if you can.`, `Ask what ${name} needs and offer meaningful help`),
    actionChoice(`train:${name}`, "people", `Train together`, `Practice together using your established abilities and styles.`, `Train together with ${name}`, { duration: "hour" }),
    actionChoice(`gift:${name}`, "people", `Give something`, `Choose an appropriate possession or arrange a thoughtful gift.`, `Give ${name} an appropriate gift and explain why`),
    actionChoice(`protect:${name}`, "people", `Protect or care for them`, `Make their safety or care an ongoing priority.`, `Ensure that ${name} is protected and properly cared for`, { duration: "ongoing" }),
    actionChoice(`spar:${name}`, "people", `Challenge to a spar`, `Request a nonlethal practice match. They can still decline.`, `Ask ${name} for a nonlethal sparring match`),
    ...(isMember ? [actionChoice(`order:${name}`, "people", `Give an instruction`, `Issue a clear order that respects the established command structure.`, `Give ${name} a direct instruction`)] : []),
  ];
}
function worldActionChoices(state = APP.state || {}) {
  const world = state.world || "Custom World";
  const choices = {
    Naruto: [
      ["naruto-mission", "Review mission opportunities", "Check missions appropriate to your rank, village access and current obligations.", "Review the missions currently available to me"],
      ["naruto-chakra", "Develop chakra affinity", "Train a lore-accurate nature affinity or an established proficiency.", "Train my established chakra nature affinity"],
      ["naruto-intel", "Review shinobi intelligence", "Check reports, rumors and classified information available at your rank.", "Review the shinobi intelligence and mission reports I am authorized to access"],
      ["naruto-duty", "Perform village duties", "Patrol, report, teach or support the village according to your position.", "Carry out the duties expected of my current shinobi position"],
    ],
    "One Piece": [
      ["op-sail", "Plan the next voyage", "Choose a destination, supplies and the crew's immediate priorities.", "Plan our next voyage with the crew"],
      ["op-news", "Read the latest newspaper", "Catch up on public events, bounties and World Government attention.", "Read the latest newspaper and discuss it with my group"],
      ["op-island", "Explore the current island", "Look for its people, culture, conflict, secrets and opportunities.", "Explore the current island and learn what is happening here"],
      ["op-crew", "Hold a crew meeting", "Bring the whole crew together regardless of current duties.", "Call a meeting of my full crew or unit"],
    ],
    "Hunter x Hunter": [
      ["hxh-work", "Look for Hunter work", "Find opportunities matching your license, specialty and contacts.", "Look for Hunter work suited to my specialty and reputation"],
      ["hxh-nen", "Practice Nen fundamentals", "Train an established Nen principle or Hatsu application.", "Train one of my established Nen disciplines"],
      ["hxh-info", "Trade information", "Seek, verify, buy or exchange useful information.", "Look for a useful information trade"],
      ["hxh-track", "Investigate a lead", "Track a person, object, creature or unanswered question.", "Investigate one of my current leads"],
    ],
    Bleach: [
      ["bleach-duty", "Perform spiritual duties", "Patrol, conduct Konso, investigate Hollows or file division reports.", "Carry out the spiritual duties expected of my current role"],
      ["bleach-zan", "Commune with Zanpakuto", "Enter the inner world or deepen the relationship with your sword spirit.", "Meditate and commune with my Zanpakuto spirit"],
      ["bleach-kido", "Practice Kido", "Train a learned Hado or Bakudo spell with proper control.", "Practice one of my learned Kido spells"],
      ["bleach-division", "Report to the division", "Check assignments, mentors, expectations and squad matters.", "Report to my division and review my current duties"],
    ],
    "Jujutsu Kaisen": [
      ["jjk-mission", "Review curse missions", "Look for incidents appropriate to your official access and actual strength.", "Review the curse-related missions currently available to me"],
      ["jjk-technique", "Develop technique application", "Explore a new use of the same innate governing principle.", "Train a new application of my established innate technique"],
      ["jjk-intel", "Research a curse", "Investigate its human cause, manifestations and known victims.", "Research one of the curses or incidents relevant to me"],
      ["jjk-politics", "Handle headquarters or clan matters", "Deal with evaluations, obligations, rivals and political pressure.", "Address the jujutsu political or clan matter most relevant to me"],
    ],
    Overgeared: [
      ["og-opportunity", "Look for Satisfy opportunities", "Find military, political, magical, merchant, exploration or social work.", "Look for worthwhile opportunities in Satisfy beyond routine crafting"],
      ["og-rankings", "Check rankings and news", "Review player, guild and public developments around you.", "Check the latest rankings, guild news and major Satisfy events"],
      ["og-class", "Pursue class development", "Seek a narrative milestone appropriate to your class behavior and accomplishments.", "Pursue an opportunity that could develop my current class"],
      ["og-guild", "Handle guild affairs", "Review members, resources, promises, rivals and current responsibilities.", "Review and handle my current guild or organizational affairs"],
    ],
    "Solo Max-Level Newbie": [
      ["solo-floor", "Study the current floor", "Review rules, factions, hidden conditions and possible clear routes.", "Study the current floor and identify plausible clear conditions"],
      ["solo-memory", "Review foreknowledge", "Separate remembered game knowledge from confirmed and unreliable facts.", "Review what I remember, what has been confirmed and what may have changed"],
      ["solo-synergy", "Review build synergy", "Examine how titles, artifacts, stats and copied abilities work together.", "Review and improve the synergy of my current build"],
      ["solo-admin", "Investigate the administrator", "Learn their preferences, loopholes, rivalries and reactions.", "Investigate the current floor administrator and their preferences"],
    ],
    "Reincarnated as a Slime": [
      ["slime-nation", "Review the nation", "Check specialists, infrastructure, defense, culture and internal concerns.", "Review the current condition and needs of my nation or settlement"],
      ["slime-subordinates", "Meet with subordinates", "Hear reports and let named followers raise plans or problems.", "Call my named subordinates together for reports and discussion"],
      ["slime-analysis", "Analyze something unknown", "Use established analysis abilities on a creature, object or skill.", "Analyze one unknown creature, object or ability relevant to me"],
      ["slime-diplomacy", "Handle diplomacy", "Address alliances, legitimacy, religion, trade or international response.", "Review and handle my most important diplomatic concern"],
    ],
  };
  return (choices[world] || [
    ["custom-opportunity", "Look for opportunities", "Find work, training, people or problems supported by this world.", "Look for opportunities that fit my current situation"],
    ["custom-research", "Study the world", "Learn more about local rules, history, factions and threats.", "Research the world and my current surroundings"],
  ]).map(([id, label, description, text]) => actionChoice(id, "world", label, description, text));
}
function buildActionDeckChoices(state = APP.state || {}, personName = "") {
  const people = actionDeckPeople(state);
  const person = personName ? people.find((row) => normalizePersonName(row.name) === normalizePersonName(personName)) || { name: personName } : null;
  if (person) return personInteractionChoices(person, state);
  const choices = [];
  (state.suggested_actions || []).slice(0, 5).forEach((text, index) => choices.push(actionChoice(`suggested:${index}:${text}`, "recommended", text, "Suggested from the current scene and campaign state.", text)));
  const hpRatio = Number(state.hp || 0) / Math.max(1, Number(state.hp_max || 1));
  choices.push(actionChoice("personal-rest", "personal", hpRatio < .75 ? "Rest and recover" : "Take a proper rest", "Recover from exertion and allow ordinary needs to be addressed.", "Rest and recover properly", { duration: "hour" }));
  choices.push(actionChoice("personal-sleep", "personal", "Sleep", "Sleep for an appropriate amount of time and recover naturally.", "Get proper sleep", { duration: "hour" }));
  choices.push(actionChoice("personal-meal", "personal", "Eat and drink", "Have a suitable meal and take care of basic needs.", "Eat, drink and take care of my basic needs", { duration: "hour" }));
  choices.push(actionChoice("personal-relax", "personal", "Relax", "Spend unstructured time reducing stress or enjoying the present.", "Take time to relax", { duration: "hour" }));
  choices.push(actionChoice("personal-recover", "personal", "Seek treatment", "Address injuries, illness, exhaustion or lingering status effects.", "Seek appropriate treatment and recovery"));
  choices.push(actionChoice("personal-maintain", "personal", "Maintain equipment", "Clean, organize and maintain important reusable possessions.", "Maintain and organize my important equipment", { duration: "hour" }));
  choices.push(actionChoice("personal-reflect", "personal", "Reflect and plan", "Review recent events and decide what matters next.", "Take time to reflect on recent events and plan my next priorities", { duration: "hour" }));
  choices.push(actionChoice("personal-shop", "personal", "Shop or trade", "Buy, sell or trade something appropriate to local availability and your actual funds.", "Shop or trade for something useful in the current location"));
  choices.push(actionChoice("personal-finances", "personal", "Manage money and property", "Review meaningful funds, income, debts, businesses and owned property without tracking trivial purchases.", "Review and manage my money, income and property", { duration: "hour" }));
  choices.push(actionChoice("personal-celebrate", "personal", "Celebrate", "Mark a victory, milestone or relationship in a way that fits this world.", "Celebrate a recent achievement with the appropriate people", { duration: "hour" }));
  people.slice(0, 6).forEach((row) => choices.push(actionChoice(`person:${row.name}`, "people", `Interact with ${row.name}`, row.role || row.position || "Choose how you want to approach this person.", `Talk with ${row.name}`, { person: row })));
  choices.push(actionChoice("people-message", "people", "Send a message", "Contact someone who is not currently nearby.", "Send a message to someone I know"));
  choices.push(actionChoice("people-socialize", "people", "Socialize", "Spend ordinary social time with available people.", "Spend time socializing with people around me", { duration: "hour" }));
  choices.push(actionChoice("people-mentor", "people", "Teach or mentor", "Help someone develop through instruction suited to your established knowledge.", "Teach or mentor someone using skills I actually possess", { duration: "hour" }));
  choices.push(actionChoice("people-recruit", "people", "Invite or recruit", "Ask someone to join an appropriate group without overriding their motives or consent.", "Invite an appropriate person to join my group"));
  const skillNames = Object.keys(state.skills || {}).slice(0, 5);
  skillNames.forEach((name) => choices.push(actionChoice(`skill:${name}`, "training", `Practice ${name}`, "Train an established ability without inventing a separate generic skill.", `Practice and improve ${name}`, { duration: "hour" })));
  choices.push(actionChoice("training-stats", "training", "Condition the body", "Train the physical attributes appropriate to your established style.", "Condition my body using training appropriate to my established fighting style", { duration: "hour" }));
  choices.push(actionChoice("training-study", "training", "Study or research", "Learn through available records, observation or instruction.", "Study a subject relevant to my current goals", { duration: "hour" }));
  choices.push(actionChoice("training-mentor", "training", "Seek instruction", "Ask an appropriate person to teach or guide you.", "Seek an appropriate teacher for something I want to learn"));
  actionDeckLocations(state).forEach((name) => choices.push(actionChoice(`travel:${name}`, "travel", `Travel to ${name}`, "Use an established route and an appropriate method of travel.", `Travel to ${name}`, { duration: "hour" })));
  choices.push(actionChoice("travel-explore", "travel", "Explore nearby", "Look around the current area without committing to a distant journey.", "Explore the area around my current location", { duration: "hour" }));
  (state.quests || []).filter(q => typeof q !== "object" || !/complete|failed|cancelled|abandoned/i.test(q.status || "")).slice(0, 5).forEach((quest, index) => { const name = typeof quest === "object" ? (quest.name || quest.title || `Current objective ${index + 1}`) : quest; choices.push(actionChoice(`quest:${name}`, "missions", `Work on ${name}`, "Make concrete progress using the time selected.", `Work toward ${name}`, { duration: "hour" })); });
  choices.push(actionChoice("missions-work", "missions", "Look for work", "Find appropriate paid, official or informal work.", "Look for work appropriate to my abilities and position"));
  choices.push(actionChoice("missions-investigate", "missions", "Investigate a problem", "Follow a known lead or examine a current concern.", "Investigate the most relevant unresolved problem available to me", { duration: "hour" }));
  const group = state._organization_roster;
  choices.push(actionChoice("group-meeting", "organization", `Call a ${group?.label ? group.label.toLowerCase() : "group"} meeting`, "Gather associated members for reports, discussion or planning.", "Call a meeting of my full group"));
  choices.push(actionChoice("group-orders", "organization", "Issue group instructions", "Give clear orders through the established command structure.", "Issue clear instructions to the members under my authority"));
  choices.push(actionChoice("group-review", "organization", "Review the organization", "Check members, roles, commitments, resources and current concerns.", "Review my organization, its members and its current needs"));
  choices.push(actionChoice("group-territory", "organization", "Manage territory", "Handle an established holding, settlement or claimed land through narrative decisions.", "Review and manage the territory under my legitimate control", { duration: "hour" }));
  if (state.combat?.active) {
    choices.push(actionChoice("combat-current", "combat", "Resolve the current battle", "Return to the active combat controls and finish the encounter.", "Continue fighting the current enemy"));
  } else {
    choices.push(actionChoice("combat-spar", "combat", "Find a sparring partner", "Arrange a nonlethal practice fight with a willing opponent.", "Find an appropriate partner for a nonlethal spar"));
    choices.push(actionChoice("combat-patrol", "combat", "Patrol for danger", "Search for credible threats without manufacturing a battle.", "Patrol the area and respond only to dangers that actually exist", { duration: "hour" }));
    choices.push(actionChoice("combat-hunt", "combat", "Hunt a known threat", "Track a threat already supported by the narrative.", "Hunt one of the known threats relevant to my current location"));
  }
  choices.push(...worldActionChoices(state));
  const base = choices.filter(row => row.category !== "recommended");
  return [...rankActionDeckChoices(choices, state), ...base];
}
function actionTextWithDuration(action, duration) {
  const base = String(action.text || action.label || "").replace(/[.!?]+$/, "");
  if (duration === "ongoing") return `${base}. Treat this as a standing instruction and continue it whenever the narrative allows until I cancel it or circumstances require it to stop.`;
  const phrase = ACTION_DURATION_LABELS[duration] || "";
  return phrase ? `${base} ${phrase}.` : `${base}.`;
}
function renderActionDeckMiniList(selector, rows, emptyText) {
  const target = $(selector);
  target.innerHTML = rows.length ? rows.map((row) => `<button type="button" data-action-deck-saved="${encodeURIComponent(JSON.stringify(row))}"><b>${escapeHtml(row.label || row.text || row)}</b></button>`).join("") : `<span>${escapeHtml(emptyText)}</span>`;
}
function renderActionDeck() {
  const state = APP.state || {};
  const choices = buildActionDeckChoices(state, actionDeckPerson);
  const activeCategory = actionDeckPerson ? "people" : actionDeckCategory;
  const categories = $("#action-deck-categories");
  categories.hidden = Boolean(actionDeckPerson);
  categories.innerHTML = ACTION_CATEGORIES.map((row) => `<button type="button" data-action-category="${row.id}" aria-pressed="${row.id === activeCategory}"><span aria-hidden="true">${row.icon}</span><b>${row.label}</b></button>`).join("");
  const personBox = $("#action-deck-person");
  if (actionDeckPerson) {
    const person = actionDeckPeople(state).find((row) => normalizePersonName(row.name) === normalizePersonName(actionDeckPerson)) || { name: actionDeckPerson };
    personBox.hidden = false;
    personBox.innerHTML = `${personPortraitHtml(person.name, person, { size: "md" })}<span><b>${escapeHtml(person.name)}</b><small>Choose how you want to interact</small></span><button type="button" data-clear-action-person>All actions</button>`;
    $("#action-deck-context").textContent = `Interact with ${person.name}`;
  } else {
    personBox.hidden = true;
    personBox.replaceChildren();
    $("#action-deck-context").textContent = `${state.location || "Current location"}. ${state.world || "Current world"}`;
  }
  const filtered = choices.filter((row) => row.category === activeCategory).slice(0, actionDeckPerson ? 12 : 10);
  const favorites = readActionDeckStore("favorites");
  const favoriteIds = new Set(favorites.map((row) => row.id));
  $("#action-deck-list").innerHTML = filtered.map((row) => `<article class="action-choice" role="listitem"><button type="button" class="action-choice-main" data-action-choice="${escapeHtml(row.id)}"><span class="action-choice-icon" aria-hidden="true">${ACTION_CATEGORIES.find((cat) => cat.id === row.category)?.icon || "◇"}</span><span><b>${escapeHtml(row.label)}</b><small>${escapeHtml(row.description)}</small></span><i aria-hidden="true">›</i></button><button type="button" class="action-choice-favorite" data-favorite-action="${escapeHtml(row.id)}" aria-label="${favoriteIds.has(row.id) ? "Remove from favorites" : "Add to favorites"}" aria-pressed="${favoriteIds.has(row.id)}">${favoriteIds.has(row.id) ? "★" : "☆"}</button></article>`).join("");
  $("#action-deck-empty").hidden = Boolean(filtered.length);
  $("#action-deck-list").hidden = !filtered.length;
  renderActionDeckMiniList("#action-deck-favorites", favorites.slice(0, 5), "No favorites yet");
  renderActionDeckMiniList("#action-deck-recent", readActionDeckStore("recent").slice(0, 5), "No recent choices");
  renderActionDeckMiniList("#action-deck-ongoing", (state.standing_orders || []).slice(0, 4).map((text, index) => ({ id: `ongoing:${index}`, label: text, text })), "No standing instructions");
  renderActionDeckMiniList("#action-deck-queue", (state.queued_actions || []).slice(0, 4).map((text, index) => ({ id: `queue:${index}`, label: `${index + 1}. ${text}`, text })), "Nothing queued yet");
  $("#action-deck-queue-count").textContent = `${(state.queued_actions || []).length} queued`;
}
function openActionDeck(personName = "") {
  actionDeckPerson = personName || "";
  actionDeckCategory = personName ? "people" : "recommended";
  actionDeckDurationTouched = false;
  $("#action-deck-duration").value = "moment";
  renderActionDeck();
  openModal("modal-action-deck");
}
function placeActionInComposer(action) {
  if (!action) return;
  const duration = actionDeckDurationTouched ? ($("#action-deck-duration").value || "moment") : (action.duration || "moment");
  const text = actionTextWithDuration(action, duration);
  const input = $("#action-input");
  input.value = input.value.trim() ? `${input.value.trim()}\n${text}` : text;
  saveMobileDraft();
  const saved = { id: action.id, label: action.label, text: action.text, description: action.description, category: action.category, person: action.person?.name || actionDeckPerson || "", duration };
  const recent = [saved, ...readActionDeckStore("recent").filter((row) => row.id !== saved.id)].slice(0, 8);
  writeActionDeckStore("recent", recent);
  closeModal("modal-action-deck");
  setMobileView("actions", false);
  input.focus(); input.setSelectionRange(input.value.length, input.value.length);
  showToast("Action added to the composer. Edit it or add it to your plan.", "system");
}


// Rank existing options and a small number of evidence-backed follow-ups.
// This is local UI advice, not a new simulation or a restriction on freeform play.
function actionPersonAvailable(person) {
  return person?.alive !== false && !["dead", "deceased", "missing", "absent", "away", "unreachable", "departed"].includes(String(person?.status || person?.membership_status || "").toLowerCase());
}
function rankActionDeckChoices(choices, state) {
  const scene = state.scene_state || {};
  const sceneCurrent = scene.location === state.location && (!Number.isFinite(scene.turn) || Number(state.turn || 0) - scene.turn <= 1);
  const objective = [sceneCurrent ? scene.current_objective : "", ...(state.quests || []).filter(q => typeof q === "object" && !/complete|failed|cancelled|abandoned/i.test(q.status || "")).map(q => `${q.name || q.title || ""} ${q.next_hint || ""}`)].join(" ");
  const tokens = text => new Set(String(text || "").toLowerCase().match(/[a-z0-9]{4,}/g) || []);
  const goalWords = tokens(objective);
  const nearby = actionDeckPeople(state).filter(person => actionPersonAvailable(person) &&
    ((sceneCurrent && (scene.present || []).includes(person.name)) || person.last_known_location === state.location || person.location === state.location));
  const recent = new Set(readActionDeckStore("recent").slice(0, 3).map(row => String(row.text || "").toLowerCase()));
  const pool = choices.filter(row => row.category !== "recommended" || row.id.startsWith("suggested:"));
  const hpRatio = Number(state.hp || 0) / Math.max(1, Number(state.hp_max || 1));
  const scored = pool.map((row, index) => {
    let score = row.category === "recommended" ? 35 : row.category === "missions" ? 14 : 0;
    const words = tokens(`${row.label} ${row.text}`);
    score += [...words].filter(w => goalWords.has(w)).length * 8;
    if (["personal-rest", "personal-recover"].includes(row.id) && hpRatio < .6) score += hpRatio < .3 ? 120 : 75;
    if (row.person) score += nearby.some(p => p.name === row.person.name) ? 38 : -50;
    if (row.category === "organization" && !(state._organization_roster?.members || []).length) score -= 100;
    if (row.category === "world") score += 5;
    if (recent.has(String(row.text || "").toLowerCase())) score -= 18;
    if (state.combat?.active) score += row.id === "combat-current" ? 160 : -50;
    return { row, score, index };
  });
  const propose = (id, label, why, text, score) => scored.push({ row: actionChoice(id, "recommended", label, why, text), score, index: scored.length });
  if (!state.combat?.active && sceneCurrent && scene.unresolved_question) {
    const question = String(scene.unresolved_question).slice(0, 280);
    propose("scene:question", "Answer the open question", question, `Respond to the current question: ${question}`, 90);
  }
  for (const [index, item] of (state.obligation_ledger || []).entries()) {
    if (!item || typeof item !== "object" || !["active", "due"].includes(String(item.status || "active").toLowerCase())) continue;
    if (![String(state.name || "").toLowerCase(), "player", "you"].includes(String(item.owner || "").toLowerCase())) continue;
    const deadline = item.due_canon_day;
    const due = item.status === "due" || (typeof deadline === "number" && deadline <= Number(state.canon_day || 0) + 2);
    const task = String(item.text || item.promise || "").trim().slice(0, 240);
    if (due && task && !state.combat?.active) propose(`commitment:${item.id || index}`, `Follow up: ${task}`, item.status === "due" || deadline <= Number(state.canon_day || 0) ? "Your recorded commitment is due." : "Your recorded deadline is approaching.", `Work toward my recorded commitment: ${task}`, 85);
  }
  const results = [], seen = new Set();
  for (const { row, score } of scored.sort((a, b) => b.score - a.score || a.index - b.index)) {
    if (score < 0) continue;
    const key = String(row.text || row.label).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    results.push({ ...row, id: `recommended:${row.id}`, category: "recommended" });
    if (results.length === 5) break;
  }
  return results;
}
