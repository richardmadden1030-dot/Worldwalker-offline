# Reliable turns, clearer outcomes

Build: `3.62.0-reliability-1`. Base app/save version remains 3.62.0, schema 21.

## Player-visible changes

The Chronicle includes an expandable recorded-outcome entry after a committed
resolving operation. It reports net HP/resource/stat changes, visible skills and
class changes, inventory quantities, equipment, currency, quest status,
relationships, location and elapsed time. XP rollover shows both level/progress
values rather than inventing an earned-XP total. Existing hidden-class and
signature-skill visibility rules are used. No additional rewards or AI calls are
created by the summary. Previously saved prose is not rewritten.

Next-action suggestions prioritize current questions, relevant objectives,
urgent recovery, nearby available people and approaching player-owned
obligations. Completed quests and dead/unavailable contacts are excluded from
the action deck. Suggestions remain editable proposals; freeform input and
existing world progression rules are unchanged. Ranking is local, not another
narrator request.

Map calculations now wait for usable geometry, reject invalid camera values,
and release old input listeners when rebound. Tabs also honor the game's
animation and low-data switches. A compact desktop layout addresses the
721–1100px range without changing the existing phone navigation boundary.

## Recovery and consistency

Unreadable JSON or incomplete gameplay responses cannot clear the recovery
notice. A pending request is retained in the tab's session storage where
available. Retry checks a read-only, authenticated campaign request-status
endpoint before resending. Completed outcomes are replayed with current public
state; active operations are not resubmitted. Unknown outcomes can only be
retried when the campaign identity and original state guard still match.

The latest eight request receipts are stored with the campaign and excluded
from public state and AI prompts. With autosave disabled, crash recovery is
limited to the most recently saved state. The same request ID cannot be reused
for a different payload or campaign. Combat and event routes preserve IDs.
Assessment and confirmation responses refresh the guard used by the next step.
Failed transactions do not append a result summary; confirmed results use stable
story IDs to avoid duplicating receipts on replay. These changes do not promise
exactly-once behavior across arbitrary old exports, deliberate Undo, or different
servers with independent copies of a save.

Confirmed NPC-death propagation now recognizes explicitly recorded aliases and
shared IDs. Conflicting IDs and ambiguous aliases are left unresolved instead
of applying a death to multiple people. Unambiguous legacy record copies receive
a stable person ID; historical group ranks and membership records remain. This
is a targeted identity foundation, not a replacement of every NPC name lookup.

## AI controls

Authentication, permission and invalid-request errors no longer enter a generic
JSON-repair loop. Quota/billing and ordinary rate-limit errors stop for review
rather than hammering the provider. Transient service/connection failures and
malformed output have one bounded retry per call. Oversized TPM requests retain
the existing reduced-payload recovery path.

Two optional settings are available in AI & Portrait Setup: estimated spending
per resolved turn (0 disables) and automatic repairs per turn (default 2, range
0–5). The repair count spans transport, feature negotiation and semantic repair
across model roles in that resolving operation. Estimated cost reservations are
shared across its outgoing requests. They are estimates, not exact provider
billing guarantees. Unknown model prices cannot be checked when a nonzero turn
budget is configured. Separate background, portrait, advisor and side-chat work
are not part of a resolving turn's budget. Manual Retry starts a new budget.

## Code organization and checks

API/recovery code, the action deck and receipt rendering are separate scripts.
The large frontend file is incrementally smaller; this is not a full rewrite.
Asset URLs and the service-worker cache carry the build ID; patch notes and
Diagnostics expose it without changing the save schema.

- `tests/test_reliability_update.py`: receipt correctness/visibility, real
  save/load, request identity, rollback, combat IDs, assessment guards, retry
  classification, budgets, and conservative NPC identities.
- `tools/check_reliability_browser.py`: actual HTML, styles, scripts and Flask
  routes with deterministic turn outcomes. It tests corrupt successful
  responses, reload recovery, confirmations, contextual choices, long
  Chronicles, responsive layouts and hidden/rebound maps.
- `tools/check_workspace_tabs.py`: existing isolated workspace regressions.

Run `PYTHONPATH=backend:tests python -m pytest tests tools/check_workspace_tabs.py
 tools/check_reliability_browser.py` with Flask, Pillow, pytest and Playwright
Chromium installed. Windows uses `;` rather than `:` for PYTHONPATH. In a sandbox
that prohibits browser HTTP navigation, `WORLDWALKER_IN_MEMORY_BROWSER=1` uses
an in-process transport adapter while retaining the production shell/handlers;
normal CI uses the real loopback HTTP server. No live paid models are used in
these checks. Interactive gameplay with a user's models, long-term real-world
campaign behavior and every browser/device are not verified by these tests.

## Publishing

Source updates go only to `richardmadden1030-dot/worldwalker-rpg:master`.
Richard handles the `Dexsidius/WorldWalkerRPG_Webapp:web_prod` push manually.
Windows previews are built separately from the stable release and must include
the entire portable folder, including `_internal` and music.
