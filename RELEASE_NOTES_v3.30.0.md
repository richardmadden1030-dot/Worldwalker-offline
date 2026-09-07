# Worldwalker RPG 3.30.0

This release gives every world a shared, deterministic simulation backbone.

- Character capability now reconciles stats, resources, titles, techniques,
  equipment, conditions, and world-specific traits before the GM responds.
- Abilities receive consistent mechanics, costs, limits, counters, scaling,
  mastery stages, and world-relative validation without restricting original
  non-canon creations.
- Training and progression expectations now scale with the time invested,
  focus, supporting-stat growth, and whether the setting canonically uses XP.
- NPC continuity carries goals and recurring roles forward. Existing
  `nemesis` flags now drive persistent hostile schemes and story threads.
- Existing companion `combat_support` flags now reach the GM and apply a
  capped, visible mechanical support bonus during local combat.
- Encounters now track a coherent lifecycle from confrontation through active
  combat, escape/surrender, and aftermath.
- Quests, promises, nemeses, and continuing goals are normalized into living
  story threads so unresolved developments remain available across turns.
- Every resolved turn and time skip records a compact six-stage resolution
  transaction for internal consistency.
- A free local evaluator checks eight core simulation contracts in all nine
  worlds: 72 checks, no AI calls, and no API cost.
- Jinchuriki starts no longer receive an unrelated random special ability
  unless the player explicitly requested a separate one.

Save schema remains 19; existing current-format campaigns are migrated in
place when loaded.
