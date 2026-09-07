# Worldwalker RPG — Web/Desktop Rebuild

A from-scratch UI rebuild of Worldwalker RPG on top of the original game engine
logic. Same local-AI-driven, freeform text RPG across nine settings (One Piece,
Naruto, Hunter x Hunter, Solo Max-Level Newbie, Overgeared, Reincarnated as a Slime, Bleach, Jujutsu Kaisen, Custom World) —
now with a real animated HTML/CSS/JS interface instead of Tkinter, running in
a native desktop window via `pywebview`.

Current app version: **3.64.0** (compatible with save schema 21).
Current preview build: **3.64.0-membership-truth-1**.


Version 3.64.0 adds character mastery paths, persistent faction operations, multi-stage expeditions and boss phases, player-targeted minor canon-event intervention, organization delegation, public reputation/wanted status, property/economy/production, and engine-owned official team membership. The Team screen, GM and Advisor now consume the same canonical organization ledger; relationships, locations and faction names cannot become members. Named recruitment and player join decisions require explicit local confirmation.

Living Adventures adds confirmed, timed location activities, route and companion
choices, retrieval/protection/escape encounters, persistent local aftermaths,
fixed world calendar anchors and an openly accessible canon reference.
See `LIVING_ADVENTURES.md` and `WORLD_CALENDARS.md` for controls, provenance,
compatibility and tested scope. The original freeform composer remains available.

This build adds durable request recovery, expandable recorded-outcome entries,
contextual action suggestions, bounded AI repairs, safer map cameras and
conservative NPC identity linking. See `RELIABILITY_UPDATE.md` for scope, tests
and limitations. The build identifier is visible in patch notes and Diagnostics.

Version 3.57.2 directly integrates the approved Living Map prototype renderer, including its
World/Regional/Local semantic zoom and dominant center-stage layout. Version 3.57.1 integrated an interim Living Map presentation while retaining
the sharper setting-specific atlases introduced in 3.57.0. It replaces the old
blob-style territory overlay with soft influence, adds map modes, moving pieces,
relationship-gated tracking, semantic zoom, desktop context panels, and a true
mobile Map tab.

Version 3.57.0 rebuilt every bundled world atlas with sharper setting-specific
art and recalibrated landmarks. Bleach now has separate switchable boards for
Soul Society, the World of the Living, Hueco Mundo, the Royal Realm and Hell;
the player's current realm opens automatically without preventing map browsing.

Version 3.56.0 promotes the Living Atlas to a full-screen strategy workspace,
adds a dedicated mobile Map tab, upgrades every bundled map for deep zooming,
and rebuilds Naruto around a clean label-free 4K atlas with stable canon-shaped
political regions and corrected live landmark placement. Territory remains
narrative-driven and can still change, merge, or grow from a single claimed hex.

Version 3.54.0 adds a local Character Life & Legacy engine for companion goals,
relationship phases, mentorship, family choices, development, succession and
lasting deeds. Major milestones require causal evidence or player consent, old
saves migrate automatically, and the same compact state supports AI and offline
resolution without an additional AI call.

Version 3.53.1 fixes completed-turn Chronicle focus so every layout begins at
the first newly generated update instead of jumping to the campaign's beginning.

Version 3.53.0 adds a local Campaign Arc Director that turns established quests,
standing instructions, repeated development and nemeses into optional multi-turn
arcs. Threads advance only when relevant actions or recorded events touch them,
support multiple conclusions, close with persistent epilogues, and create quiet
aftermaths without another AI call.

Version 3.52.0 adds a local Living World Director: repeated behavior creates grounded follow-ups, known NPCs can initiate contact from remembered goals, outcomes are tracked with more variety, vague typed actions are confirmed before queuing, and more everyday actions are available without additional AI calls.

Version 3.51.1 adds a compact, world-aware action picker without limiting the
existing freeform composer. It includes rest and recovery, training, travel,
work, group duties and world-specific activities. Relationship portraits open
person-specific interactions, and ongoing selections become explicit standing
instructions. The picker runs locally and adds no AI request of its own.

Version 3.50.0 puts approved character portraits into conversations, rosters,
relationships, notifications, Advisor comparisons, timeline events, major events,
location previews, suggested interactions, and tactical turn/target controls without
adding new panels. Unknown people use initials rather than an incorrect portrait.

Version 3.49.0 presets One Piece's battle-relevant canon power library locally,
including Devil Fruits, Haki applications, fighting styles, transformations and
successful Conqueror's Haki Overwhelm animation. Version 3.48.0 replaces Party
with persistent world-native group rosters: crew,
Marine squad, shinobi organization, guild, division and other appropriate labels.
Members remain listed while away, with positions and same-world combat ratings
(estimates are labeled). Narrative events record agreements, recruitment, departure,
command chains, family, mentors and accepted organizational succession. Ongoing NPC
training and aging are calculated locally from elapsed time and their own activities,
not the player's power. Succession requires actual death or explicit retirement and
never replaces the player's character. Old saves migrate without starting again.
No separate model call is added; bounded group context uses the existing GM request.

Version 3.46.0 adds concise narrative chapter recaps, connected people/place/promise
retrieval, group and unambiguous follow-up commands, relevant-evidence checks, and
protection for settled stories. Failed turns retain dice and reusable drafts; repaired
responses are checked again before application. Chronicle entries offer **Correct this**
with a preview before any change. Old saves receive the same rules and a compact chapter
display without discarding their original continuity record. Chapter prose rides on the
existing turn request when due, with a local extractive fallback; no separate recap call
is needed in normal gameplay. Local multi-year regression scenarios cover all nine worlds.

Version 3.45.1 adds **More → NPC Chat** to the mobile layout, opening the existing
Chats & Contacts screen without changing desktop navigation or chat behavior.

Version 3.45.0 strengthens conditional/negative intent, evidence-linked NPC reactions,
faithful subordinate commands, current-versus-historical facts, individual NPC dialogue,
routine time-skip grouping, and narrative/outcome validation. Repairs receive the original
draft, and a still-contradictory result is rejected before application. New multi-turn
regressions exercise hidden abilities, real save export/import/load, and combat availability
across all nine worlds. Existing saves work without starting over; old Chronicle text is
preserved. Ordinary successful turns do not require an additional model call.

Version 3.44.3 adds locally parsed player intent, causal complication limits, NPC knowledge and temporal boundaries, deterministic progression guidance, relevant liked-turn examples, stronger named-character estimates, narrative Dōjutsu recovery, and first-update Chronicle anchoring. Version 3.44.2 made named applications inside umbrella abilities usable in combat, grounded incoming messages in sender knowledge, and removed repeated agenda boilerplate. Version 3.44.1 adds reliable money accounting, payable obligations, exact
fractional currencies, and the approved One Piece Poneglyph Chronicle. Version 3.44.0 adds causal outcome resolution, smaller task-specific AI prompts,
long-campaign request compaction, approved world-specific Attributes panels, and
bundled canon portrait/form art. Version 3.43.0 added a pre-Advance campaign health pass, stale goal/quest/combat
cleanup, deep nested-state validation, compact checkpoints, partial AI-response
recovery, tiered campaign memory, actionable error IDs, and a complete standing-
order lifecycle for long-running campaigns.

Version 3.40.0 gives the GM a persistent live-scene ledger, broader conditional
response repair, narrative/mechanical outcome-scale checks, canon-divergence
impact tracking, delayed consequences and structured obligations, varied beat
pacing, evidence-backed Advisor answers, selective lore retrieval, and a soft
style profile learned only from turns the player explicitly likes. Every
release now shows its player-facing patch notes once per browser/account.

Version 3.39.0 grounds every AI role in a small source-ranked set of current
campaign facts, reconciles narrated consequences with mechanical state, gives
factions persistent strategy and operations, and locally consolidates long
campaign memory. The Journal's More menu now contains only Progress, Chapters,
NPC Knowledge, and Timeline; maintenance and diagnostic internals no longer
crowd normal play. Automated three-turn regression coverage now exercises all
nine supported worlds.

Version 3.38.0 adds persistent world-depth records, context-routed prompts,
multi-factor JJK clashes, richer LitRPG floors/classes, and readable long-title
major-event cinematics. It retains the 3.37.2 fixes that stop duel arrangements from prematurely starting
combat, including the reported case where “with a deep bow” was misread as an
opponent named Deep Bow. It also adds local canon identity/role locks across
all supported canon worlds, repairs unambiguous Bleach division swaps, and
rejects placeholder labels such as “hidden flash-related class” before they
can become an actual class name.

Version 3.37.1 restores Bleach Chronicle updates to the clean, readable panel
layout used before v3.37.0. The Hell Butterfly artwork and Chronicle animation
were removed; all other v3.37.0 systems remain intact.

Version 3.37.0 gives each world a more native Chronicle presentation, including
Naruto scroll turns, Bleach Hell Butterfly dispatches, One Piece Poneglyph
records, and game-system styling for Overgeared and Solo Max-Level Newbie. It
also adds persistent companion combination abilities, narrative territory and
headquarters growth, world-native information delivery, downtime surprises,
incoming social messages, chat-aware GM context, and player-approved legacy
trophies.

Version 3.36.2 replaces renamed-template power rerolls with persistent,
mechanic-level originality across every world that supports unique abilities.
JJK techniques, Nen, Devil Fruits, Zanpakutō, hidden classes, bloodlines, and
other original powers are compared against the account's permanent archive;
canon abilities and player-authored creation facts remain authoritative. It
also adds world-themed desktop cursors for Naruto, Bleach, and JJK, including a
spinning Naruto shuriken while the game is working, and verifies the complete
Naruto/Bleach music bundle in release tests.

Version 3.36.1 makes explicit creation-background facts immutable across
generation and rerolls, synchronizes named Zanpakutō throughout the character
state, guarantees local Advisor power comparisons, deduplicates title notices,
and uses world-native power terminology everywhere players can see it.

Version 3.36.0 repairs multiplayer combat states created with older or malformed
character and enemy records so every combat control remains usable instead of
raising a string-shape error. Hunter x Hunter creation now supports awakened or
latent Nen with a unique persistent Hatsu and a dedicated affinity dossier. One
Piece creation now supports chosen Haki branches and unique generated Devil
Fruits that interpret the character background and never repeat for an account.

Version 3.35.0 turns every canon-event interruption into a native full-screen cinematic using the event's real title, date, location, player position, travel context, world theme, and best available cached scene art. It adds replay, mobile composition, reduced-motion support, and keeps the Chronicle as the actual decision surface.

Version 3.34.0 adds a cleaner political atlas, world-authentic percentile dice, compact decision cards, an informational canon-event sheet with position and travel context, and an expandable transformation panel that remains tied to portrait state.
Existing saves created before age tracking receive a one-time deterministic
repair from their current calendar year, and long skips add one compact
birthday update instead of leaving the creation age permanently frozen.

Version 3.33.0 adds a local cinematic feedback system without adding AI calls.
Every world now has its own restrained ambient identity, while time, weather,
combat, transformations, major abilities, stat changes, level-ups, Chronicle
beats, music, and map discoveries receive contextual visual feedback. Maps show
known travel routes, danger and event markers, and fog pockets for undiscovered
landmarks. All continuous effects respect animation, reduced-motion, and mobile
low-data settings, and the existing desktop and phone information layouts stay
intact.

Version 3.32.0 replaces overlapping territory blobs with a single clean
strategy-atlas layer. Political shading can no longer overlap, borders vanish
between neighboring holdings controlled by the same faction, authored borders
remain supported, and narrative location-control changes repaint the map
immediately. The atlas also gains clearer political labels, a compact legend,
cleaner landmark priority, and mobile-safe sizing. Mobile time controls now
offer amount and unit selectors directly beside Advance, plus a separate clock
button for the detailed modal; queued actions and the current draft remain
intact when changing time settings.

Version 3.31.0 adds the approved phone companion interface: persistent bottom
navigation, a compact live status ribbon, full-screen mobile journals and
Advisor, a keyboard-safe action queue, sticky Advance and combat controls,
Chronicle filters, map improvements, draft recovery, low-data and large-text
modes, offline feedback, haptics, and installable-PWA refinements. The Advisor
also estimates any named character from current campaign evidence and canon
context instead of refusing when no numeric NPC sheet exists. Tailed-beast
chakra cloaks now trigger and later restore transformation portraits through
the normal Advance flow.

Version 3.30.1 restores a fully grounded Advisor, removes the last local combat
fallback that could scale an underspecified enemy to the player, makes ordinary
combat victories lethal unless mercy is chosen, and adds full Naruto lineage,
Jinchūriki, and active-form portrait presentation.

Version 3.30.0 unifies character capability, abilities, progression, NPC
continuity, encounter phases, and living story threads behind every turn. It
also makes existing nemesis and companion combat-support flags mechanically
visible to the GM, and adds a free nine-world simulation evaluator.

Version 3.29.0 adds persistent narrative intentions: ongoing care, delegated
training, protection, policies, routines, and projects continue between turns
without repeated player commands, while milestones and interruptions remain
part of the normal Chronicle. Naruto chakra affinities now distinguish one
natural affinity from learned nature proficiencies and mastery, preserve
canon-correct start profiles, and require a bloodline or other established
mechanism for multiple innate elemental affinities.

Version 3.28.0 adds world-native power benchmarks, simultaneous local two-player combat,
compiled mechanics and semantic uniqueness for generated abilities, polygon territory control,
and a broad AI-cost reduction layer with task routing and per-task telemetry.

Version 3.27.2 gave Naruto Jinchūriki a dedicated power system separate from
ordinary jutsu, Kekkei Genkai, Dōjutsu, and classes. It tracks the sealed
tailed beast as an independent character, its complete canon potential,
currently accessible abilities, seal condition, relationship, bond, control,
transformation stage, reserve increase, mastery requirements, and the physical,
social, political, and extraction dangers that remain relevant.
Naruto characters also receive a persistent chakra-affinity profile: native
elemental jutsu develop faster and more efficiently, off-affinity natures need
more time and instruction but remain possible, combined releases retain their
special prerequisites, and tailed-beast nature access stays distinct from the
host's own natural affinity.
Combat speed advantages now pause after the first action and return the full
combat controls for a player-chosen quickened turn instead of automatically
repeating the same move.

Version 3.27.1 adds a mobile-safe signed login fallback for browsers and
installed PWAs that discard the normal secure session cookie. It also records
every non-canon generated ability, hidden class, Zanpakuto, and JJK birth-slot
design in a per-account Codex archive and prevents rerolls from repeating any
name or mechanical package the player has already seen.

Version 3.27 deepens Jujutsu Kaisen play with coherent generated technique
packages, persistent mastery tracks, binding vows, technique intelligence,
Black Flash records, grade evidence, clan obligations, curse growth, soul and
possession state, role-specific opening missions, a clearer progression
journal, and four optimized setting scenes. It also fixes full-year recurring
finance calculations, partial finance updates and duplicate labels, improves
mobile modal readability, and replaces misleading queued-action risk labels.

Version 3.22 adds a complete Jujutsu Kaisen world with Tokyo and Kyoto school
starts for all three years, independent curse users, great-clan members,
sentient cursed spirits, four eras, and playable Yuji, Gojo, Yuta, Megumi, and
Maki starts. Original characters receive exactly one generated birth slot—an
Innate Cursed Technique or Heavenly Restriction—with an optional strong-power
guarantee, technique-derived applications, curse grades and feeding growth,
and a Black Flash screen effect. It also adds bespoke JJK scenes, a world map,
theme styling, portrait direction, lore sources, and progression rules. Bleach
saves with an achieved release now recover a missing Zanpakutō name from their
release profile or learned Shikai skill.

Version 3.21.1 lets original Bleach characters preview and reroll a complete,
coherent Zanpakutō concept before confirming the campaign. Previewing dormant
Shikai and Bankai abilities does not grant either release; unless the background
explicitly establishes ownership, both milestones must still be earned in play.

Version 3.21 gives every setting a deterministic world-law profile, flexible
development paths, setting-specific downtime, persistent signature-technique
records, faction doctrine, canon-event ripples, contextual opportunities, and
distinct elite encounter structure. These systems reuse the normal narration
call rather than adding another AI request. The Progress Journal explains
possible routes and genuine prerequisites without turning them into a fixed
skill tree. One Piece crews and ships, Hunter Nen restrictions, Naruto jutsu
research, Solo floor ecology, Overgeared build synergy, Slime evolution and
nation play, and Bleach Zanpakuto/squad growth now have persistent state.

Version 3.20 makes Satisfy classes complete starting playstyles instead of
labels. Every creation archetype has real starting skills, a class quest,
mechanical action bonuses, role-specific leads, advancement paths, and equal
credit for combat and non-combat contributions. Summoned partners are now
persistent contracts, level/XP is prominent in both LitRPG worlds, progression
arrives through canon-styled Satisfy or Tower notices, and accidental combat
starts from tense or figurative language are rejected.

Version 3.19 turns Overgeared into the full world of Satisfy instead of a
mostly crafting-focused route. Character creation now offers martial, magical,
support, command, companion, exploration, social, production and hybrid roles.
Original class authorship studies the complete canon class catalog as design
precedent while creating a distinct class for the player's background. Class-
aligned adventures advance every role; production records only appear after a
character actually chooses a production path.

Version 3.18.1 gives each multiplayer character a durable, proximity-aware
Chronicle. Local scenes reach characters who are present, private moments stay
private, distant information can arrive through messages, reports, rumors or
broadcasts, and genuinely shared events reach both players. Each account's
filtered history survives refreshes and server restarts, with Nearby, Reported
and Shared markers explaining how the character learned each update.

Version 3.18 adds durable two-player campaigns to the hosted friend server.
The host shares a copy of any current campaign with a six-character invite
code; each account keeps its own character, action plan, readiness and portrait
while both players inhabit one authoritative world and Chronicle. Rounds last
ten minutes, resolve early when both players are ready, pass disconnected or
unready characters, and advance one Moment when nobody is ready. Shared rooms
survive refreshes and server restarts. This version also adds a persistent
music-widget volume slider and exposes the complete world time on hover.

Version 3.17 adds private friend accounts to the hosted build. Everyone can
use the same Cloudflare URL while retaining an isolated live session, settings,
saves, autosaves, and imported campaigns. The Docker image now runs through
Gunicorn, and older campaign exports can be imported directly into the signed-in
account. Desktop and local-phone hosting remain single-player and unchanged.
API keys are also stored per account: one player cannot read or overwrite
another player's key, and a newly registered account never inherits a server or
host key. In a shared multiplayer room, the room host's configured key powers
the authoritative simulation without exposing that key to the other player.

Version 3.16.2 bundles seven default Bleach tracks and four default Naruto
tracks in their portable world music folders. They are available immediately
in both desktop and phone-host builds while keeping each folder open for
user-added music.

Version 3.16.1 adds compact Naruto-specific sound cues: a short Advance sound,
a hand-sign cue for original-character starts, Pain's theme for the Pain canon
start and the beginning of Pain's Assault, and a death cue for Naruto campaigns.
The cues respect the sound-effects setting, avoid overlapping one another, and
briefly lower active background music.

Version 3.16 adds a deterministic depth audit across every bundled world,
structured scene identity for much more reliable environment artwork, and
opt-in automatic lore coverage. Approved sources refresh with conditional
downloads and local extraction; same-site discovery is bounded, and routine
refreshes make zero AI calls.

Version 3.15 makes combat conditions fully mechanical: hard control consumes
actions, weakening changes real combat values, and both sides can carry timed
conditions. Character creation now reads the degree of the player's language,
so talented, prodigy, immense, godlike, and immeasurable starts produce sharply
different open-ended stats and matching generated powers without extra AI calls.

Version 3.12 separates literal System quests from ordinary story goals.
Overgeared and Solo Max-Level Newbie retain objective progress, completion
conditions, and quest branches. Every other setting now presents missions,
promises, investigations, and personal goals through a world-themed narrative
Agenda with current knowledge, pressures, developments, and possible leads—no
progress bars, mandatory route order, or automatic checklist completion.

Version 3.11 turns the lightweight Solo Max-Level Newbie and Overgeared
profiles into persistent setting simulations. Solo now tracks full floor
scenarios, hidden-condition discovery, copied-ability requirements,
foreknowledge, rivals, artifacts, party roles, achievement chains and clear
reports. Overgeared now separates class development from individual production
disciplines and tracks class quests, NPC affinity, guilds, territory, orders,
economy and public rankings. Crafting in every world remains part of the
Chronicle; routine ore and components no longer clutter the Bag, while named,
reusable and story-important finished items receive readable item cards.

Version 3.10 brings the non-Bleach worlds up to the same mechanical standard
as the Bleach rebuild without adding map nodes or timeline dates. One Piece,
Hunter × Hunter, Naruto, Solo Max-Level Newbie, Overgeared, and Reincarnated
as a Slime now have dedicated world-system records and Journal cards. Existing
canon events are spoiler-safe and causally ordered, canon-character starts use
complete deterministic stat sheets and live opening situations, every ordinary
origin receives a saved role, loadout, progression state, and opening quest,
and non-level settings no longer receive a misleading Level label in Party.
Additional selectable starts use only locations that were already on each map.

Version 3.8.1 adds a fully mechanical Pain canon start immediately after
Yahiko's death, while the Deva Path and transformed Akatsuki are first taking
shape. It also expands One Piece creation from three starting locations to a
broad selection across the Blues, Grand Line, World Government territory and
the New World; every new choice has an opening premise and a matching map node.

Version 3.8.0 makes campaign-start labels mechanically authoritative. Canon
characters and high-status original origins now begin with their promised
rank, affiliation, signature abilities, equipment, knowledge, quests, and
conditions before the opening narration runs. It also adds start-era
consistency warnings and automatic correction for impossible default-era
origins, expands maps and timelines, limits direct messaging of inaccessible
factions, and adds focused new archetypes and eras across the non-Bleach worlds.

Version 3.7.2 unifies current-stat interpretation across the Power Summary,
Advisor, and GM. Extreme specialties remain powerful without being mistaken
for balanced reality-bending capability, and the Power Summary now opens above
the Journal. Focused training develops related and secondary stats, plain
training builds the full sheet, and world-valid accelerated methods can produce
exceptional growth. Configured AI models now author original, canon-balanced
starting classes, bloodlines, abilities, and matching starting techniques;
offline creation retains safe world-valid fallbacks.

Version 3.7.1 makes Story, Adventurer, and Veteran explicitly player-favoring:
possible actions resolve decisively, diplomacy is challenged through NPC and
faction responses instead of abstract failure, and specific world-valid plans
bypass arbitrary gates. Sustained training is faster and broader; six months
of rigorous Naruto combat training can now establish jōnin-level capability
without falsely granting an official village rank. Nightmare remains strict.

Version 3.7.0 reduces AI cost and improves simulation consistency. It sends
task-specific context to each model, uses the main model for Advisor unless a
separate Advisor model is explicitly selected, uses the secondary model for
combat narration when configured, reports cached-token savings, keeps only
useful autosave history, and disables automatic portrait generation by default.
It also improves standing plans, roll/action labeling, training and quest
reports, combat entry, scene-matched artwork, suggestions, mobile Advisor
readability, and moment/time-skip controls.

Version 3.6.3 gives dangerous confrontations one persistent warning instead
of reopening a warning for every difficult choice in the same scene. Normal
moment-to-moment checks continue after the warning is accepted; only a new
credible chance of death warns again. Committed attacks from either side now
enter structured combat immediately through expanded deterministic detection.

Version 3.6.2 moves major/canon events back into the normal Chronicle and
Action Chat: their popup is now a close-only notice, unavoidable violence
opens structured combat immediately, and event importance alone no longer
forces a roll. Challenge minigames can either stop after their result or carry
that result through the remaining requested skip. Phone chats and the Advisor
now reserve most of the screen for readable conversation history.

Version 3.6 adds a local campaign director, persistent NPC motives, optional
relationship scenes, branching quest routes, productive failures, readable
cause-and-effect and training reports, editable/reorderable time-skip plans,
major-event model routing, request/session cost limits, and opt-in same-scenario
model comparisons. These systems reuse state the game already tracks and do
not add routine AI calls.

Version 3.3 reduces simulation bloat: normal Advances use a deterministic
planning pass plus one combined narrator request, while Economy, Balanced,
and Deep detail modes control how much of the wider world stays in focus.
NPC intentions, lore retrieval, event importance, and art reuse are cached or
advanced locally whenever a model call is not necessary.

## Running it

```
pip install -r requirements.txt
python launcher.py
```

or double-click `run_game.bat` on Windows. The desktop launcher chooses an
available local port and opens it in a native window automatically — no
browser tab, no manual server step. The launcher deliberately avoids a fixed
port: an older process can no longer make a new window attach to stale art,
JavaScript, or campaign state. Desktop responses are also marked no-cache.

With no campaign active, startup opens a dedicated welcome screen with two
working choices: **Start New Campaign** or **Load Existing Save**.

## Playing from a phone

Extract the Phone Host package on a Windows PC and double-click
`Start Phone Mode.bat`. Keep the host window open, connect the phone to the
same trusted Wi-Fi, and open the address displayed across the top of the host
window. If Windows Firewall asks, allow access on **Private networks** only.

The phone interface puts the scene and Chronicle first, then Action Chat and
time controls, with character and journal panels below. It uses the same
campaign, autosave, music, AI configuration, and server-side API key as the
host PC. Do not use Phone Mode on public or untrusted Wi-Fi; anyone who can
reach the displayed local address can control that running game. The included
web-app manifest supports home-screen installation when the page is served in
a browser-approved secure context, but ordinary local HTTP play works directly
in the phone browser while the PC host is running.

New Campaign now uses a preview/confirmation step and can start as an original
character or at a curated major-character timeline moment (including Yahiko
founding the original Akatsuki, Naruto's birth or graduation, Gon leaving Whale
Island, and comparable starts in the other supported worlds). The player has
full control of canon characters; the timeline steers through living pressures
and relationships but never forces the source character's decisions.

For local AI (recommended, free, no per-turn cost): open LM Studio, load a
chat/instruct model, Developer → Start Server, then in-game go to
**OPTIONS → AI & Portrait Setup → Detect Models**, pick a model, Save.

Settings and saves live in `%APPDATA%\WorldwalkerRPG\` — the same folder the
original Tkinter build used, so an existing local-AI configuration carries
over automatically.

## Architecture

- `backend/worlds.py` — world data, difficulties, base character state
  (ported 1:1 from the original `worldwalker.py`).
- `backend/ai_client.py` — the local/cloud AI client (Responses API with
  Chat Completions fallback), also ported 1:1.
- `backend/game.py` — `GameSession`: the actual game engine (assess → roll →
  resolve turn loop, time skips, chat/contacts, background world ticks,
  memory management, save/load). All Tkinter UI code has been removed; every
  method returns plain dicts.
- `backend/app.py` — Flask routes exposing `GameSession` as a small JSON API,
  plus static file serving for the frontend and game assets.
- `frontend/` — the actual UI: `index.html` + `css/style.css` +
  `js/app.js`. Pure vanilla JS, no build step.
- `launcher.py` — runs the Flask app on a background thread and opens it in
  a `pywebview` window.

## About the artwork

The generated art library contains the original landmark/environment set plus
five new optimized location-specific banners for merchant shops, taverns,
academy classrooms, ship decks, and arena floors. This prevents broad fallback
art—especially battlefields—from appearing inside ordinary local places.

Version 2.2 replaced the old mislabeled placeholder set with 38 original,
generated environment paintings in `assets/generated_scenes/`. Twenty-four
are recognizable location anchors across the supported worlds—including
Hidden Leaf Village, Heaven's Arena, Water 7, Skypiea, Tempest, and more;
the rest cover live scene types such as towns, caves,
dungeons, duels, monster battlefields, castles, forests, harbors, and night
skies. `backend/util.py` selects art from the player's current physical
location first, then a landmark, then the closest environment category.
Concrete places such as merchant stalls and markets outrank old battlefield
references in the story log. A canvas fallback prevents blank loads.

## Version 2.5 progression rules

- Every uncertain action uses a contextual d100 check. The application samples a difficulty from the GM's lore-grounded range, rolls once, adds world-relative stats, skills and titles, and succeeds only when the modified roll is strictly greater than the difficulty.
- Stats are open-ended and meaningful only inside their current world/era. D&D modifiers and the former 20/99 caps are gone.
- Health and the setting's energy pool are derived from starting stats and grow with them.
- Long training counts accumulated daily sessions. A month of uninterrupted training is approximately 30 days of progress, with a persistent chance of a lore-explained breakthrough.
- XP and levels appear only in settings that canonically expose them as an in-fiction system (Overgeared and Solo Max-Level Newbie).
- Evolutions, transformations, climactic confrontations and other major turning points pause for an animated manual Fate Check.
- Advance stops at major canon events and asks whether the player wants to intervene moment-to-moment.
- The Advisor provides deeper briefings and canon countdowns; optional Fourth-Wall mode may explain simulation mechanics and legitimate exploits without changing state.

Version 2.5.4 makes XP authoritative in literal-System worlds: every meaningful
action receives a contextual award, sustained training scales with its actual
elapsed time, and level-ups spend carried XP and raise world-relative base
stats. The Progress journal explains each award and level gain. Non-System
worlds continue to grow directly through training, techniques, knowledge,
titles, ranks, and proficiency rather than artificial XP.

D100 results now use one compact action-linked line: raw roll out of 100 plus
the combined bonus, final total, required number, and outcome. Individual
calculation boxes have been removed from the Chronicle.

## Version 2.6 simulation and campaign tools

Before a difficult uncertain action resolves, the game shows the contextual
d100 target, applicable bonuses, and risk without moving time. The player may
roll normally, use the Timing Clash reaction challenge, use the Tactical
Approach decision challenge, or cancel and revise the queued actions.

**Skip to next major event** advances through routine developments while still
recording world updates, then ends naturally at the first major personal or
canon turning point. It does not create a separate intervention prompt.

The Journal now includes chapter summaries, persistent NPC and faction clocks,
relationship snapshots, quest objective/branch states, lore-source imports,
progression tuning, campaign-health diagnostics, and an interactive map that
can estimate and queue travel routes. The main cloud GM defaults to GPT-5.6
Luna while the cheaper background simulation remains on GPT-4o mini; existing
model selections are never silently replaced.

## Guided journeys and world music

The GM ends every resolved scene or time skip with three optional, contextual
leads: the strongest current story lead, a useful growth/preparation option,
and an alternate exploration, social, or travel hook. These are guidance rather
than restrictions. Clicking one copies it into the Action Chat for editing; it
does not resolve anything until the player presses **ADVANCE**.

The story log now uses the full center column. Active Quest and World Feed are
compact left-side buttons that open their complete journal pages, while the
persistent Action Chat occupies the right rail. Queued actions remain visible
there until the player confirms the next turn.

An Advance with no new action continues the previous standing orders when
possible while still moving NPCs, factions, markets, travel, rumors, and canon
pressures. Goal-worded orders can end a skip early: if an ability is mastered
on day 13 of a requested month, the simulation stops on day 13. If the deadline
arrives first, the story explains the in-world obstacle and offers a relevant
next step. Major-event stops use a non-blurred context panel and end with a
specific character-named intervention question.

The **moment** unit is event-driven rather than a literal one-minute step. It
resolves only the next immediate meaningful story beat, allows that beat to use
the believable minutes or hours it needs, and never advances more than 24 hours.
Any later queued actions remain deferred for another Advance.

Moment is always exactly one beat and therefore has no quantity field. Numeric
skip amounts are shown only for days, weeks, and months. Routine Advances now
proceed directly after their hidden mechanical assessment; interrupting panels
are reserved for lethal warnings, major events, and animated major d100 rolls.

The center Chronicle groups each response into a clearly labelled story beat.
Narration, player decisions, world updates, checks, and urgent consequences use
separate visual levels, while routine system information stays compact. A
Latest button returns directly to the newest beat. Its complete flex/overflow
chain is constrained so the feed always scrolls through its final entry.

Major-event intervention is an inline Chronicle decision instead of a modal.
**Yes — Stop Here** leaves the simulation at the event for player input;
**No — Keep Simulating** resumes the unspent portion of the original skip as if
the pause had not become a player turn. The event context remains visible while
the choice is made.

Portable music folders sit beside the source launcher or packaged EXE under
`music/`, with one folder per supported world plus `Shared`. Drop MP3 or MP4
files into the matching world folder, then use the music rescan/folder controls
under World Systems. MP3 is recommended for the broadest playback support.

The left Skills & Titles summary displays names only. Clicking it opens the
full journal view, where each skill is presented as a short effect summary plus
rank/check bonus, use, origin, cost or limitation, and growth path when known.
Raw object notation and internal calculation fields are not shown.

An explicit request to start or accept a quest always creates a structured
quest and a Chronicle briefing. The Quests journal now surfaces its giver or
cause, objective, known locations and risks, first actionable step, completion
conditions, deadline, and rewards whenever those facts are known.

The shipped build uses quality-86 WebP versions (about 88% smaller than the
master PNGs). Lightweight canvas overlays animate only appropriate details—torch flicker,
embers, stars, fireflies, leaves, cave drips, crowds, and water shimmer—so the
painted backgrounds stay sharp and the desktop build remains responsive. GIF
and WebP scene files are also supported automatically if added later.

The Journal's Map tab uses seven generated world atlases from
`assets/generated_maps/`, with every important landmark from `WORLD_DATA`
overlaid, route guides, discovery status, and a pulsing current-location pin.

## Lore, canon timeline, and prerequisite tracking

`backend/lore.py` is an offline-first retrieval layer. Every GM request receives
only the setting notes relevant to the current action, plus live state/codex
context. Optional JSON lore packs can be added under `assets/lore/`. The game
does not claim to live-browse wikis from the packaged EXE.

Every source world begins three to seven days before its protagonist's opening
story event. The Journal → Timeline tab shows relative Canon Day dates and
important scheduled events. Advance is the only control that moves this clock;
events fire when crossed, while prior player actions can create recorded canon
divergences instead of being railroaded.

When the player pursues a notable canon feat, class, item, transformation, or
position, the GM creates a Journal → Prerequisites track showing requirements
met, missing requirements, next steps, and why something is currently blocked.

Autosave writes atomically to one rolling recovery file per campaign, replacing
that campaign's prior autosave instead of filling the Load screen with numbered
copies. Manual saves remain separate, and both appear in the Load screen.

## Background completion and starting potential

The campaign preview now turns vague background claims into usable world data.
For example, “I have some kind of fire ability” produces a randomly selected,
setting-valid named ability with an origin, practical effect, limitation, and
growth path. It appears in the starting loadout and Skills journal, and the GM
must preserve it as an authoritative fact rather than asking the player to
define it again.

Missing upbringing, training, relationship, formative-event, motivation, and
complication details are filled in without replacing facts the player supplied.
The completed background creates a visible Growth Profile. Its aptitude rate
affects sustained training, while time, repetition, recovery, current mastery,
teachers, resources, and rolls continue to determine the actual result.

Character portraits are AI-generated square illustrations. The prompt uses the
player's description, age, origin, archetype, visible traits, equipment, form,
and position; missing details are filled in coherently. Each world has its own
broad visual language without requesting an exact living-artist imitation or a
canon character likeness. Portraits default to low-quality 1024×1024 generation
for speed, are cached under `%APPDATA%\WorldwalkerRPG\portraits`, and regenerate
only when a visually relevant trait changes. Later updates edit the previous
portrait to preserve identity. A manual Regenerate button is also available.

Cloud portraits use the OpenAI image model configured under **OPTIONS → AI &
Portrait Setup** (default `gpt-image-2`) and have separate image-API usage costs.
Local portrait generation is optional and requires an OpenAI-compatible image
endpoint/model. When neither is configured, the game immediately shows one of
seven lightweight bundled world-style portraits instead of a broken image.

Time is explicitly player-controlled. Typing an action adds it to a persistent
ordered queue and produces no GM or world response. Chat messages are queued in
the same way. Choose a duration and press **ADVANCE** to review time estimates,
checks, rushing penalties, and likely deferred actions; only confirmation rolls,
moves the clock, or lets the world respond. The result is emitted as separate,
detailed chronological updates for each major action, NPC/faction reaction,
consequence, interruption, and due canon event.

Campaign Library shows each save's app version, supports import/export, rolling
autosave recovery, and guarded permanent deletion. Developer Diagnostics exposes
the last action assessment, scene-selection reason, state-patch validation,
continuity warnings, lore context, world-pack status, and an exportable report.

The GM treats canon feats as evidence of what the setting permits, not as
abilities reserved for canon protagonists. A player who meets the same
world-specific prerequisites can attempt, learn, reproduce, obtain, or build
toward the same result. If an action is currently impossible, the GM must name
the exact missing prerequisite or lore conflict and explain what can change.
Lore comes from the selected model's available source knowledge plus the live
campaign state/codex; the desktop build does not silently live-browse websites.

To override the shipped art, drop a `background.png` into
`assets/user/<World>/` (e.g. `assets/user/One_Piece/background.png`) — the
game already checks there first and will use it for every scene in that
world.

## Per-world UI skins

Each world reskins the whole interface, not just accent colors — different
display fonts, panel corner treatments, and motifs, defined in
`frontend/css/style.css` under `body[data-world="..."]`:

- **One Piece** — nautical poster look, `Pirata One` display font.
- **Naruto** — ink/scroll panels with clipped corners, `Yuji Syuku` font, a
  small red seal mark on panel headers.
- **Hunter x Hunter** — license-card angled panel corners, clean modern
  green/gold.
- **Solo Max-Level Newbie** — sci-fi system UI: `Orbitron`/mono fonts, neon
  cyan glow, animated scanline overlay, octagon-cut panels.
- **Overgeared** — forge/MMO fantasy: `Cinzel Decorative`, riveted bronze
  corner studs.
- **Custom World** — the ornate default theme.
