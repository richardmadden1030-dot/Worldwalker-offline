# Worldwalker RPG v3.43.0 — Long Campaign Stability

- Repairs malformed campaign state before Advance begins.
- Archives orphaned action goals and reconciles duplicate/resolved quests.
- Closes stale combat states that could trap every later control.
- Preserves full multi-action plans with completed, deferred, and replaced order states.
- Splits campaign memory into recent turns, chapter summaries, and verified archives.
- Recovers useful partial AI replies without a second paid request.
- Adds short support IDs and richer local diagnostics for unexpected failures.
- Stores compact undo checkpoints instead of repeating the full campaign history in every snapshot.
- Validates deep NPC, scene, quest, combat, and history shapes on old and imported saves.
- Includes regression coverage using the reported turn-311 Chen Su campaign.
- Rewords off-screen NPC growth and plans so ordinary goals are no longer presented as nonsensical training methods or overdue commitments.
