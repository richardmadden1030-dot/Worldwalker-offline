# Living Adventures — 3.63.0-adventures-1

This release extends the current campaign, not the deferred model-free campaign
conversion. Existing saves, portraits, maps, freeform input and queues remain.

## Play

Open **Living Map -> Local activities**, or select a map location. The existing
map drawer now has a location illustration, current information, available
services, known local contacts, original adventure leads and recorded aftermaths.
Remote places offer route planning, not remote purchases or teleporting services.

Every activity button displays its duration (and a purchase/passage cost when
applicable). Clicking it opens a server-validated preview showing start/end time,
cost, warnings and a known interruption. **Cancel does nothing. Confirm and
resolve runs the action automatically**; it does not append a future instruction
to the composer. Independent typed drafts, queued actions and standing plans
are preserved. Training uses the existing world progression rules and energy;
rest does not cure special injuries. Routine rest, talk, preparation and shopping
do not farm generic action XP. Shops use actual existing stock and prices; the
update does not mint invented merchant inventories.

Known appointments and significant local canon boundaries pause an action or
journey rather than silently skipping it. Its remaining duration can be resumed
or explicitly canceled. Completion-only effects, such as purchases and rewards,
are not applied to an unfinished action. Resuming a purchase checks current
stock, price and currency. Live combat must be resolved on the tactical screen.

## Journeys

Known destinations compare up to three distinct routes found in the actual
travel graph: fastest, lower danger, and via a known shelter where a distinct
alternative exists. No duplicate option is invented just to fill three cards.
Normal, cautious and swift travel have different durations and exposure. Booked
passage, where supported, has a displayed currency cost. Chosen companions must
be agreed party members present at the departure point, not arbitrary contacts.

Sea passage, realm access, permits and cleared Tower-floor requirements are
checked server-side. Existing route estimates are campaign estimates, not exact
canon geographical measurements. Paused journeys remember completed edges and
partial-leg progress. The displayed current place is the last reached waypoint;
resume never charges already traveled time twice. A high-exposure journey may
have one seeded pursuit/escape encounter. Routine safe travel has no compulsory
random fight. Preparation and a companion reduce exposure; preparation can also
reduce the number of pursuers. Completed edges discover locations and companions
move with the arriving player. Paid booked passage is not refunded on cancellation.

## Objective adventures and lasting consequences

Settlements/hubs support a sequence of three **original, non-canon** local
adventures, each available once per campaign and origin. Different worlds use
their own local context and existing tactical terrain profiles:

- **The Missing Dispatch:** investigate, negotiate, infiltrate or fight to
  retrieve the dispatch and return its carrier to the marked exit. A fallen
  carrier drops it; killing every enemy alone cannot win. Success reopens a
  local mapped supply connection, reducing that edge's travel time by 15%.
- **A Light on the Road:** secure a peaceful outcome or protect a beacon for
  four full rounds. Raiders actually move toward and attack it. Nearby allies
  can shield it, and bodies/terrain can block access. Success opens a shelter
  that improves local hourly rest recovery by 25%.
- **The Witness's Passage:** secure the testimony discreetly/peacefully or move
  the player to the far exit through a contested checkpoint. Killing enemies
  is not a substitute for reaching the exit. Success establishes a courier
  contact, extending later route preparation to three days.

Negotiation/infiltration have recorded seeded checks, influenced by preparation
and relevant character attributes. A failed approach begins the objective
encounter rather than claiming success. Opposition strength comes from the
location tier, not an automatic match to the player's power. Normal combat
abilities, movement, obstacles and resource costs remain in force. The tactical
screen labels objectives, progress, exits, interaction actions and visible enemy
intentions. Other worlds use their saved generic ability mechanics rather than
inventing unsupported anime powers.

Success awards a single recorded outcome through existing currency/XP rules
where those systems apply. Withdrawal/failure records an aftermath without the
success reward. The location, route and relevant courier contact retain the
result and link to its Chronicle entry; reading the link cannot repeat a reward.
Different approaches are stored in the outcome, and negotiated agreements earn
more affinity. A completed local problem is not automatically reopened.

## Reliability and limits

Signed, expiring previews bind action, time, price, account, campaign and state.
The executor rechecks availability under the game lock and uses the existing
atomic transaction and request-receipt system. Unknown/malformed results can be
retried by their original ID; a duplicate request cannot repeat rewards or
purchases. Narrator patches cannot rewrite the engine-owned adventure or finish
an active objective battle. No personal saves or credentials are shipped.

These timed local operations deliberately resolve their mechanics locally;
ordinary freeform campaigns still use the player's configured narrator. The
three reusable adventures are not a complete authored regional campaign or a
complete model-free replacement. Ordinary shops/people/services depend on
established campaign data. This release does not simulate every possible civic
activity. Shared multiplayer rooms retain their existing coordinated-turn
system: these independent timed local operations are explicitly blocked there
rather than moving other players' shared clock without consent.

Calendar precision and compatibility are documented in `WORLD_CALENDARS.md`.

## Verification

`tests/test_living_adventures.py` exercises the actual local resolvers, signed
APIs, no-op cancellation/preview, stale/tampered requests, duplicate receipts,
rollback, purchase interruptions, access constraints, companion travel,
all-world tactical objectives, preserved saves, actual calendar-month lengths,
Python/JavaScript parity, and unmasked canon without knowledge leakage.

`tools/check_adventures_browser.py` opens the production HTML/CSS/scripts and
Flask routes, clicks real confirmations, checks responsive location drawers,
verifies timeline controls, and exercises tactical objective controls. No paid
models are called. CI uses real loopback HTTP. Only restricted development
sandboxes use the existing opt-in in-memory transport adapter.

Run `PYTHONPATH=backend:tests:tools python -m pytest tests
 tools/check_workspace_tabs.py tools/check_reliability_browser.py
 tools/check_adventures_browser.py` on one line (Windows uses semicolons for
PYTHONPATH). Full release testing includes syntax and packaged startup checks.
Automated tests are not a guarantee of bug-free gameplay on every device or
with arbitrary old/custom saves. The Windows package remains an unsigned
preview; back up a campaign before using a new build.
