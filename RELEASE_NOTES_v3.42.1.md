# Worldwalker RPG v3.42.1

## Long-campaign Advance recovery

- Fixed the exact `'str' object has no attribute 'get'` crash reproduced from Chen Su's turn-311 campaign.
- Canon context now handles both compact companion names and structured companion records.
- Import/load migration removes misplaced response-envelope fields from NPC memories while preserving real NPC and group dossiers.
- Incoming AI patches are filtered so the same NPC-memory contamination cannot accumulate again.
- Existing campaigns require no restart; importing or loading them applies the repair automatically.
