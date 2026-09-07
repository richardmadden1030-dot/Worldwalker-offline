# Worldwalker RPG 3.1.0

This release focuses on campaign reliability, readable progression, and stronger world identity.

## New systems

- A GM state validator catches contradictory locations, dead companions acting as active party members, accidental skill renames, duplicate rewards, and overdue events before they reach the Chronicle.
- Long-term narrative memory tracks established facts, goals, mysteries, promises, relationships, and consequences without bloating every story entry.
- Active quests now show progress, known clues, completion conditions, current obstacles, optional objectives, and a concrete next lead.
- The canon timeline distinguishes likely, occurred, altered, delayed, and impossible events, explains why history changed, and records replacement consequences.
- A progression ledger explains every stat, pool, experience, level, title, skill, and class change and ties it to the action that caused it.
- Hidden classes can begin genuinely concealed. Relevant actions reveal clues and discovery progress before the class name, mechanics, and signature skill become fully known.
- Character creation can reroll the class, special ability, backstory, or starting loadout independently without discarding the parts the player already likes.
- Scene art now carries a context-match confidence score and falls back to neutral world art when a specific available image would contradict the current location.
- Every supported world now has distinct colors, iconography, terminology, interface framing, and subtle sound character.

## Quality and testing

- Fixed multiple queued checks incorrectly inheriting the final action's label.
- Added automated three-turn campaign simulations for every supported world.
- Expanded the automated suite to 262 passing tests.
- App version: 3.1.0
- Save schema: 8
- Windows executable file metadata: 3.1.0.0

Campaign checkpoint branching and the pre-advance action-planning preview were intentionally left out of this release.
