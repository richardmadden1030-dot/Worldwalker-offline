# Worldwalker RPG 3.26.0

## Recurring income/expenses no longer silently stop

Real user report: money wasn't being tracked as strictly as it should —
an established income seemed to stop even though nothing in the story
ended it. Root cause: the generic state-patch rule for list fields is a
full replace, not a merge. The GM is told to "always include the full
current list" whenever it touches `recurring_finances`, but if it later
mentioned money again for any other reason and didn't perfectly recall
every previously-established entry, the omitted ones were silently
deleted — an income could vanish for no in-fiction reason at all.

- `recurring_finances` (and `scheduled_events`, which had the identical
  fragility) now merge by label instead of replacing wholesale. An entry
  the GM's patch doesn't mention this turn is preserved, not erased. The
  only way an entry actually goes away is the GM explicitly marking it
  inactive/resolved, or a player correction — never silent omission.
- The GM's own instructions are stronger about this too: an income or
  expense "stays active indefinitely" and "keeps paying until its actual
  in-fiction source is genuinely gone," with an explicit warning against
  letting a real narrative event silently stop a payment without marking
  it inactive that same turn.

## Trade, blockades, and resource scarcity now have real teeth

Real user report: things like tolls, blockades, and trade routes should
have real narrative consequences — cutting a place off from resources,
especially during a hard time, should visibly matter, with the local
government and population reacting accordingly.

- Surfaced a real mechanic that already existed in the simulation but
  wasn't reachable in live play: `faction_clocks`/`npc_clocks` support
  `opponent`, `ally`, `power`, and `contested_location`. Once a clock with
  a declared opponent reaches its turning point, the application resolves
  a real strength-weighted outcome automatically — territory can change
  hands, and a losing side can be genuinely destroyed or lost — regardless
  of whether the player is present. The GM is now told this applies to
  trade disputes and blockades exactly like open conflict, not just
  outright war.
- New instruction: tolls, blockades, secured/cut trade routes, and who
  actually supplies a settlement must show up concretely in prices,
  scarcity, and the population's day-to-day situation — not flavor text.
  A settlement that just suffered a major disaster, or is currently cut
  off, should visibly struggle; its government is more likely to act to
  secure supplies, and its people's sentiment shifts toward whoever is
  actually providing for them.
- Scoped to the tasks that actually need it (a normal turn and a time
  skip) rather than every task, so the size-constrained combat recap and
  opening scene stay lean, unaffected by this addition.

Both changes are prompt-instruction and state-merge fixes — no schema,
UI, or mechanical changes; the Chronicle and presentation behave exactly
as before.

## Verification

- 588 automated regression and feature tests pass, including new coverage
  for the merge-not-replace fix (an income surviving an unrelated later
  patch, explicit deactivation still working, in-place updates still
  working) and the new faction/trade instructions reaching the right
  tasks without bloating the combat recap.
- Python compilation checks pass.
