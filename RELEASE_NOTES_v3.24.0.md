# Worldwalker RPG 3.24.0

## Less GM pushback, more player-authored story

Real user report: the narrative was pushing back too hard on player actions
— routine, non-violent choices were getting softened, downgraded, or
outright refused more often than they should. The goal is to let the
player create the "what if" scenarios they want, with consequences coming
from how the world responds rather than from the GM overriding the action
itself. Extreme, lethal, and power-tier-leap situations still carry real
risk of failure.

- **Commanding a character under the player's authority** — a subordinate,
  companion, summon, or anyone who owes the player obedience in this
  campaign — now carries out the order as given, without GM-invented
  refusal or hesitation. The GM can still have them voice a concern or
  suggest a better approach afterward, but the order is already carried
  out. Independent NPCs, canon characters acting on their own motives, and
  hostile/neutral parties keep their own full agency — this only applies to
  characters actually under the player's command.
- **An action with a stated method now just happens as described.** The GM
  no longer softens or downgrades a described action into "an attempt" —
  the act happens, and the world's reaction (acceptance, a counteroffer,
  suspicion, retaliation, a later consequence) is where the actual stakes
  live.
- **Non-combat impossibility is now a roll, not a wall.** Previously, an
  action judged flatly "impossible" was blocked outright with no dice at
  all. Now, for anything non-combat and non-violent, a genuine on-paper
  impossibility under the world's own rules still gets a roll: success
  means the player finds a real way to make it happen, failure means a
  concrete narrative account of what happened instead — never a flat
  "nothing happens." Low odds, lack of canon precedent, social rank, and
  being ahead of the original protagonist were never valid reasons to
  block an action, and still aren't.
- **Extreme attempts, lethal undertakings, and combat/violence are
  unchanged** — dice and real risk of failure stay exactly where they were
  for those.
- Nightmare difficulty keeps its own separate, deliberately stricter
  contract untouched.

This is purely a change to the GM's own instructions (the live prompt) —
the Chronicle, presentation, and every mechanical system behave exactly as
before; only the content of what gets narrated changes.

## Verification

- 575 automated regression and feature tests pass, including new coverage
  confirming the commanded-character rule, the described-action rule, the
  non-combat impossibility roll, that extreme/lethal risk language is still
  present, and that Nightmare's stricter contract is untouched.
- Python compilation checks pass.
