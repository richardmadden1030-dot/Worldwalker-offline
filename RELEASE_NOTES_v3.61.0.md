# v3.61.0 — Narrative-to-gameplay consistency

- Discovered places no longer teleport the player. Only explicit travel transitions update the current location.
- Named NPC ability gains stay on that NPC. Unsupported non-player consequences are flagged for review instead of awarded to the player.
- Ability names are matched without case sensitivity, including manual corrections, preventing duplicate Fireball/fireball entries.
- Confirmed NPC deaths synchronize memory, contacts, companions and historical organization rosters. Tactical battle receipts apply this to named casualties without inventing loot or broadcasting private knowledge.
- Suspected deaths and other uncertain outcomes do not become confirmed mechanical changes. A quest marked in progress cannot be completed merely because its explanation contains the word "completed".
- Destroyed or removed named items are also cleared from equipment slots.
- Existing campaign-record review now includes unresolved structured consequences and skips explicit ability gains followed by later recorded losses. Repairs remain preview-and-confirm, never automatic on load.
- Correct the GM can preview and confirm an established NPC's death, with a stale-state check. No extra management dashboard or AI request is added.
- Correction previews now show complete structured before/after records instead of blank object values; confirmation buttons have phone-friendly tap targets.

Existing recruitment, special-power panels, territory controls, standing orders and long-skip systems remain in place. This release fixes tested gaps between them rather than introducing a second simulation. The new reconciliation safeguards work on existing saves during subsequent turns; historical mistakes require review or explicit correction.

Testing uses disposable synthetic campaigns and supplied GM-response fixtures, not paid live-model generations or edits to real player saves. Authored world-map ambiguity and arbitrary prose without sufficient structured evidence still require GM judgment or player review.
