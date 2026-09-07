# Worldwalker RPG 3.4.0

Version 3.4 makes the simulation more dependable without adding another
ordinary-turn model call. Its new referee, travel, knowledge, scheduling,
search, and correction systems all run locally.

## Simulation integrity

- Every turn receives a local integrity report before its state patch is
  accepted. Roll/action pairing, elapsed time, goal stops, resource bounds,
  completed/deferred actions, and map-scale travel are checked.
- “Until,” “master,” “find,” “reach,” and other goal-bearing orders become
  explicit stop conditions. Early completion ends the skip at the reported
  completion time.
- Player corrections are authoritative, autosaved facts. Common state errors
  can be repaired directly without advancing time or calling the model.

## A world with distance, schedules, and information

- Every built-in world now exposes a connected landmark travel graph with
  routes, ordinary travel time, and access requirements. Local rooms and
  sublocations remain fluid and are not mistaken for cross-world travel.
- Recurring NPC intentions produce commitment schedules with goals, due days,
  locations, and due consequences.
- News can move as witnessed, spoken, written, broadcast, researched, rumored,
  or ability-carried information. Delay, recipients, and confidence are stored;
  narrator knowledge is not automatically NPC knowledge.

## Living canon and readable lore confidence

- Canon events expose dependencies on earlier story causes. Prevented causes
  can make later events delayed, altered, impossible, or replaced instead of
  allowing the original timeline to railroad itself back into existence.
- Timeline cards show whether lore is confirmed, adaptation-dependent,
  uncertain, or a best-fit date reconstruction.

## Player tools

- Campaign Search finds prior actions, outcomes, chapters, quests, people,
  skills, durable facts, and corrections locally.
- Correct the GM repairs a story fact, location, item, currency, health,
  energy, quest status, or skill description and preserves the correction in
  future narrator context.
- Simulation Checks shows recent validation, active stop goals, NPC schedules,
  information in motion, travel-graph size, and canon dependency health.
- The Map shows direct connections and calculates a full route from the
  player’s current location, including estimated time and access needs.

## Playtest refinements

- Explicit hidden-class themes are preserved: a requested space-time shinobi
  path now creates a matching Warp Fold class rather than an unrelated class.
- Exact day/week/month skips cannot silently stop after only a few hours. A
  shorter result now requires a reached goal, major event, or real interruption.
- The local one-call preflight recognizes elite guardians and similar hard
  obstacles, warns before time advances, and offers the normal d100 or either
  optional challenge.
- Iconic-location labels now match the art actually shown, while a specific
  shop, stall, alley, or interior still overrides the broader landmark.
- Duplicate player-correction search results and cramped challenge-choice
  labels were cleaned up, and Action Chat returns into view after each turn.

## Validation target

- App version: 3.4.0
- Save schema: 11
- Windows executable metadata: 3.4.0.0
- 321 automated regressions including the v3.4 quality-gate scenarios are expected
  before packaging, followed by live multi-world desktop play-testing.
