# Worldwalker RPG 3.3.0

Version 3.3 improves simulation depth while reducing redundant context and
model requests. It deliberately does not add a new cost-dashboard surface.

## Lean turn pipeline

- A normal Advance uses a deterministic local planning pass and one combined
  narrator request for actions, relevant NPC reactions, quests, canon
  pressure, and wider-world consequences.
- Continuity recovery can still retry a malformed or contradictory response;
  that is an error-recovery exception rather than the normal path.
- Economy and Balanced modes perform background maintenance locally. Deep
  mode may make one additional background request every four resolved turns.

## Simulation modes and relevance

- Economy keeps the smallest local detail bubble and shortest context.
- Balanced is the default and keeps nearby actors and active threads detailed.
- Deep retains more NPCs, lore, history, and world updates.
- Distant people and factions advance through compact clocks and intentions
  until their actions become relevant to the player or reach a turning point.

## Persistent world state

- Recurring NPCs retain a goal, plan, next action, resources, relationship,
  knowledge, location, progress, and status.
- An importance scheduler preserves major developments, deduplicates repeated
  reports, and combines routine overflow into one wider-world summary.
- Narrator updates, clocks, and NPC intentions share one consolidated event
  ledger so the same development is not separately recorded as multiple
  systems' unrelated output.

## Smaller prompts and reused assets

- The context compiler sends the current scene, relevant actors, active
  quests, approaching pressure, a recent history tail, and compact chapter
  memory instead of an ever-growing raw campaign history.
- Ranked lore retrieval is cached by world, query, location, and known skills.
- Portrait cache keys ignore stat, reputation, position, and other nonvisual
  changes. New keys require a visible appearance, equipment, affiliation
  clothing, or transformation change.
- Environment cache keys change only with physical place, encounter type, or
  an active major event; routine Chronicle wording cannot churn scene art.

## Validation

- App version: 3.3.0
- Save schema: 10
- Windows executable metadata: 3.3.0.0
- 292 automated tests are expected before packaging, followed by live desktop
  interface verification and a packaged-executable self-test.
