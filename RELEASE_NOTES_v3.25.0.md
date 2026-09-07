# Worldwalker RPG 3.25.0

## Quests and player-set goals are now actually completable

Real user report: objectives and quests were too ambiguous. In worlds
without XP/leveling (every world except Solo Max-Level Newbie and
Overgeared), a quest deliberately has no rigid built-in objectives or
progress bar — but that flexibility meant a player-stated goal like "I want
to prepare for [event]" could sit vague indefinitely, with no clear path to
actually finishing it and no guarantee the GM would ever surface a way to
work toward it.

- A player-stated goal now becomes a real quest the same way a GM-given one
  does, and it stays genuinely completable through the player's own effort
  — it must never sit permanently vague with no path to finishing it.
- **Specific goals** (a stat threshold, a particular technique, a named
  item, a confrontation to survive) get concrete objectives set to those
  exact things, and the GM is now instructed to actively create narrative
  opportunities — scenes, encounters, training sessions, specific tasks —
  for the player to actually attempt and complete them, instead of waiting
  for the player to guess how to advance it.
- **Ambiguous goals** (general preparation, growing stronger, getting
  ready) still become a tracked quest. Every time the player takes action
  genuinely relevant to it, the GM now credits real, felt progress toward
  it, paced so consistent honest effort actually reaches completion by its
  due date instead of stalling indefinitely.
- A due date gets set whenever the goal has one, and progress is paced
  against it. When objectives are met — or, for an ambiguous goal, genuine
  accumulated effort by the due date reasonably supports it — the GM now
  resolves the quest as complete in that turn's update. A completable goal
  must actually be able to complete.

This is purely a change to the GM's own instructions (the live prompt) —
the quest lifecycle code (objective tracking, narrative-mode vs. literal-
mode presentation, completion detection) was already correct and needed no
changes; it just wasn't being told to actually use the completable path
that already existed. The Chronicle and presentation behave exactly as
before; only the content of what gets narrated and tracked changes.

## Verification

- 580 automated regression and feature tests pass, including new coverage
  confirming the new instructions are present in the live prompt and that
  a narrative-mode (non-XP world) quest can still reach a genuinely
  completed status through the existing normalization pipeline.
- Python compilation checks pass.
