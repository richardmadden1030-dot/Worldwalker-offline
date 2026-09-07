# World Systems Preview — 3.63.0-world-systems-1

This local preview builds on Living Adventures without changing save schema 21 or requiring a new campaign.

## Character Paths
- Existing visible skills receive deterministic mastery paths; concealed/unowned skills remain unavailable.
- Players can pin one current development goal from Progress.
- Timed local sessions cover fundamentals, efficiency, application practice, and established mentors who are physically present.
- Partial sessions credit only elapsed work; cancel/interrupt behavior uses the existing confirmed timed-action pipeline.
- Mastery changes actual combat mechanics through bounded accuracy/check bonuses, resource efficiency, tactical range, effect duration, and status potency where the established skill supports those fields.
- Ordinary demonstrated use can add modest evidence/progress, while focused training remains the primary route.

## Living Factions & World Conflict
- Existing faction clocks and resources remain authoritative.
- Active operations appear in the Clocks journal and at their local map location.
- Players can spend confirmed local time to investigate, assist, or sabotage an active operation.
- Completed operations resolve deterministically from their relevant faction resource and persist outcomes into the world feed.
- Military pressure becomes contested territory first; defended holdings can fortify or weaken; established control changes require sustained successful pressure instead of one routine background tick.
- Read-only map/journal views do not create IDs or mutate campaign state.

## Expeditions, Dungeons & Boss Hunts
- Each world receives an original non-canon expedition template grounded in its existing terrain vocabulary.
- Expeditions persist across preparation, scouting, multiple exploration sections, an elite encounter, camp recovery, and a boss encounter.
- Hazard attrition is deterministic and can be mitigated by relevant established detection/knowledge/mobility skills.
- Boss scouting records confirmed intelligence and rumors separately.
- Bosses enter real phase 2/3 states at health thresholds, gain tactical pressure buffs, and may alter the arena without cutting all traversable routes.
- Withdrawal saves the current expedition stage and progress for later resumption.
- Completion is idempotent and uses existing XP rules; a single expedition title records the achievement.

## Canon Divergence & Player-Targeted Minor Events
- The public Canon timeline keeps future events visible as a player reference.
- Future minor events that remain possible can be marked **Intervene in this minor event**.
- Targeting advances no time and leaks no future knowledge into NPC memories.
- GM context explicitly preserves reasonable leads, timing and access toward the target instead of silently background-resolving it.
- The flag does not teleport the character, bypass access, guarantee success, or make an impossible/replaced event occur.
- If the player reaches the correct place/window, the normally-minor event becomes an actual intervention stop like a major canon decision point.
- Canon dependency status remains authoritative, and targeted events record whether they occurred, were missed, replaced or became impossible.

## Verification
The final local source suite runs all existing backend tests plus workspace, reliability, Living Adventures and four-system browser regressions. Browser checks use the project's in-memory adapter only where this sandbox blocks loopback HTTP. No paid model calls are used.

The Windows package is constructed locally from the previously verified 3.63.0 Windows onedir build by replacing its embedded Python PYZ archive with Python 3.12-compiled modules from this tested source tree and replacing the bundled frontend directory. The original Windows bootloader and runtime DLLs remain unchanged. The package can be structurally verified here, but this Linux sandbox cannot execute the Windows `.exe`; back up a campaign before using the preview.
