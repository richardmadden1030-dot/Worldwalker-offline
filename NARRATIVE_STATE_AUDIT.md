# Narrative/state integration audit — September 5, 2026

Baseline: v3.60.0. Eight targeted reconciliation tests produced seven reproducible failures and one successful control case before implementation.

| Test | Baseline finding | Updated behavior |
|---|---|---|
| Location discovery | Changed current location | Records discovery without travel |
| Differently capitalized ability | Created second skill | Reuses existing name |
| NPC-owned skill | Granted to player | Records on named NPC |
| Suspected player death | Killed player | Does not apply uncertain transition |
| Confirmed NPC death | Ledger only | Synchronizes established identity records |
| In-progress quest, "not completed" evidence | Completed quest | Explicit transition controls status |
| Destroyed equipped item | Remained equipped | Removes equipment reference |
| Normal skill gain and quest completion | Worked | Preserved |

Additional regression coverage checks Sharingan special-panel synchronization, the real time-skip pipeline, historical roster preservation, read-only review and later losses, missing-mechanics review, explicit corrections, idempotent tactical receipts, and serialized state across all built-in worlds.

Existing recruitment/consent, command-chain, NPC training, long-skip equivalence, territory and knowledge tests are retained. No new recruitment or map engine was necessary. The broader pytest runner also collects function-based tests omitted by unittest discovery; an obsolete Solo atlas assertion was updated to allow the already-shipped Earth-entrance civil territory without inventing floor-country regions.

Limits: these are deterministic integration tests with authored responses and disposable synthetic states. They do not measure live-model compliance or prove that every historical narrative is mechanically complete. Uncertain or incomplete consequences remain reviewable rather than receiving guessed mechanics.
