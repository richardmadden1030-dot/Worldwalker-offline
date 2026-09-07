# Worldwalker RPG v3.39.0

## Campaign reliability

- Every GM, Advisor, event, combat-summary, and background AI job now receives a compact source-ranked grounding packet assembled for its exact question or action. Current mechanical state and player corrections outrank summaries and stock canon.
- Narrated lasting changes are reconciled locally after each turn and time skip. Missing earned titles, notable items, quests, locations, conditions, and fully described skills are safely repaired; ambiguous claims are recorded as validation warnings instead of guessed.
- Long campaigns locally deduplicate durable memories and archive verified older turn records into searchable summaries with source digests. This adds no AI call.

## Living factions

- Factions now retain strategic and immediate goals, leadership state, resources, alliances, rivals, active operations, and recent outcomes.
- Operations continue between player scenes and leadership loss creates succession pressure without erasing the faction's existing agenda.
- These systems remain narrative-facing rather than adding another management screen.

## Journal cleanup

- Journal > More has been reduced from 17 entries to four player-facing pages: Progress, Chapters, NPC Knowledge, and Timeline.
- Search Campaign and Correct the GM remain available from the main navigation. Internal causality, continuity, memory, tuning, lore maintenance, campaign health, and model-evaluation pages no longer crowd normal Journal use.

## Testing

- A deterministic three-turn regression now runs through all nine supported worlds.
- Added focused coverage for grounding precedence, consequence repair, memory consolidation/search, faction strategy, and the simplified Journal.
