# Living Relationships and Rivalries — v3.62.0

## Existing systems retained

NPC consequence chains, attitude/relationship fields, chats, command contracts, organizations, nemesis flags and staged world plans already existed. This update connects them rather than creating a parallel social dashboard or competing relationship score.

## Findings addressed

1. `living_world._npc_contact` pasted arbitrary NPC goals into canned dialogue and claimed they involved the player. It is now a no-op compatibility entry point; evidence-based candidates reach the existing GM request instead.
2. Repeated social actions emitted narrator-facing instructions as Chronicle prose. Those generic social notices are removed.
3. Contact paths missed `alive:false`, `status:dead`, and roster death records. Local/background eligibility now consults established death/incapacitation states. This does not claim to validate all arbitrary AI-authored incoming messages.
4. Shared words in a private event could make an unrelated contact learn it. Keyword overlap alone is no longer sufficient for the existing reactive-news helper. Its older explicit-name/public-news heuristics remain; full semantic information provenance still depends on GM knowledge contracts.
5. Repeated identical relationship reasons filled the bounded chain. Normalized exact duplicates are now ignored.

## Implementation boundaries

`relationship_life` proposes at most four existing shared experiences and accepts at most one follow-up every three turns. Delivered/closed experiences have stable fingerprints persisted in the save. Deferred experiences remain available; no rendering/read call consumes them. Known dead, missing, imprisoned or incapacitated NPCs cannot initiate through this path. Present-scene or contact permission is required and is rechecked after the turn.

The GM supplies actual dialogue and a delivery basis using the normal request. Canon personality, semantic feasibility, actual elapsed courier travel time, and whether an offer is appropriate remain GM judgments, not claims proved by the local validator. No new paid call, resource award, automatic agreement, obedience conversion or rival stat change is made by this module. Existing optional background AI still exists.

Existing saves require no migration and no rewriting of old chats. Only recorded shared experiences are eligible; a private goal alone is not enough. The update is for the AI-driven main game, not a new offline dialogue catalog.

## Verification

- `tests/test_relationship_life.py`: 26 tests, including real normal-turn and time-skip delivery, old-save read-only selection, all-world round trips, cooldowns, duplicate suppression, unavailable senders, invalid IDs, current-scene checks, chat context and unchanged stats/resources.
- Full suite: **1,116 passed; 759 subtests passed**, `output/v3620-verified-tests.log`.
- Updated the legacy test that required goal-pasting dialogue to assert its intentional removal, rather than preserving the defective behavior.
- Browser: existing desktop chat and mobile More → NPC Chat; full message at 390px and 320px, no horizontal overflow. Screenshots under `output/playwright/relationships3620-*`.
- Browser fixtures and integration tests use disposable campaigns and authored GM responses, not live paid AI generations or real player saves. Native phone Safari and Cloudflare deployment were not verified.
