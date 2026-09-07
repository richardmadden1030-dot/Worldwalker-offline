# Worldwalker RPG v3.21.0

## Flexible world depth

- Every bundled setting now has an explicit world-law profile used by the GM,
  progression logic, downtime resolution, elite encounters, and opportunity
  generation. It runs locally and adds no separate AI call.
- The Progress Journal shows flexible development paths, possible routes, and
  genuine setting requirements. These are guidance, never a mandatory order
  or locked skill tree.
- Original named techniques persist with their mechanism, activation, costs,
  counters, current stage, evidence, and possible next milestone.
- Training, study, networking, patrols, and crafting resolve through vocabulary
  and consequences appropriate to the selected world.
- Important opponents retain a stable encounter identity, tactical habits,
  objectives, weakness clues, phases when appropriate, and retreat logic.
- Factions receive setting-specific doctrine and retain current capabilities,
  pressure, and status without adding a visible management spreadsheet.
- Canon events record location- and knowledge-aware ripple effects rather than
  teleporting distant players into the original cast's scene.
- The local opportunity engine builds leads from role, location, known people,
  responsibilities, and unfinished development.

## World-specific depth

- One Piece tracks crew roles, bonds and voyages separately from ship condition,
  capabilities and upgrades; bounty is distinct from fame and infamy.
- Hunter x Hunter records category efficiency, Hatsu vows, restriction
  consequences, professional specialties, verified intelligence, and access.
- Naruto records teams, mentors, clan relationships, jutsu research and
  elemental notes alongside rank, nature, lineage, summons and known jutsu.
- Solo Max-Level Newbie records build synergies, rival progress, floor factions,
  rules, alternate clears and confirmed hazards.
- Overgeared records equipment synergies, skill combinations and rankings in
  addition to class, XP, affinity, guild and optional production progression.
- Reincarnated as a Slime records synthesis, subordinate evolution, settlements,
  specialists, alliances and national pressures.
- Bleach records the Zanpakuto relationship and evidence, inner world, release
  applications, Bankai mastery, academy/division duty, mentors and patrols.

Save schema 17 adds the locally maintained `world_depth` record.

## Hosted-account settings

- Cloud API keys and local-provider tokens are persisted only in the signed-in
  player's UUID-scoped settings file. New accounts no longer inherit a desktop,
  host, or environment API secret. Provider and model names may still seed as
  harmless defaults, and settings responses never return the stored key.
