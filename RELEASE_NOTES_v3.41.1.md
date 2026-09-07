# Worldwalker RPG v3.41.1

## Advance and combat hotfix

- Fixed the blocking `'str' object has no attribute 'get'` error when Advance receives an AI-authored combatant as a name instead of a full object.
- Compact enemy names are now preserved and converted into valid combat records before any combat or Chronicle code reads them.
- Existing saves receive nested combat-state repair for opponent, statuses, logs, cooldowns, contacts, chat threads, and message-delivery bookkeeping.
- Invalid or stale assessment rows are ignored safely instead of preventing the turn from resolving.
- Retains every v3.41.0 simulation, recovery, and Overgeared class-reception improvement.
