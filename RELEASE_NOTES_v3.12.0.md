# Worldwalker RPG v3.12.0

## World-authentic missions

- Overgeared and Solo Max-Level Newbie keep literal quests, objective progress,
  branches, rewards, and completion conditions because their worlds actually
  expose those systems to characters.
- Naruto uses a Mission Agenda, One Piece a Voyage Log, Hunter x Hunter a
  Hunter Agenda, Bleach a Division Agenda, Reincarnated as a Slime a Journey
  Agenda, and custom settings a neutral Agenda.
- Narrative-world entries show the situation, current knowledge, pressures,
  relevant places, developments, and possible approaches without progress
  bars, fixed routes, or mandatory checklists.
- The GM may resolve a narrative mission through any logically valid route the
  player establishes. Completing internal objective fields can no longer
  silently auto-complete a non-System mission.
- Chronicle briefings and completion notices now use each world's narrative
  terminology instead of generic quest-system wording.

## Interface and reliability

- The left-rail shortcut and Journal tab rename themselves for the current
  world.
- Hidden opportunity counts are no longer exposed in narrative-world agendas.
- The backend sends a single authoritative presentation profile to the Journal,
  while the frontend includes the same mapping as an offline-safe fallback.
