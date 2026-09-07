# Worldwalker RPG v3.42.0

## Resilient turns and deeper campaign continuity

- Failed Advance, event, and combat operations now roll back completely and retain a safe retry action instead of leaving half-applied campaign state.
- Malformed AI events, updates, chats, checks, and combat data are repaired before gameplay uses them.
- Continuing scenarios remember their cause, objective, stakes, location, participants, and recent developments.
- Generated abilities now reject renamed or lightly reworded copies more reliably.
- Combat displays why it began, its current objective, and what is at risk.
- NPC messages react to actual campaign events and relationship context.
- Every built-in world records deduplicated setting-specific milestones.
- Diagnostics shows per-task calls, tokens, model, estimated cost, recovery history, and the active scenario.
- Long-campaign processing uses bounded histories and lighter transaction snapshots.
- The automated free playtest matrix now covers all built-in worlds, malformed response recovery, and transaction safety.

The optional “Why did this happen?” explainer was intentionally not included.
