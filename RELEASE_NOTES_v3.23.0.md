# Worldwalker RPG 3.23.0

## Recurring income and expenses are now mechanically tracked

- Established a real user report: a monthly income established in the story
  more than once was never actually being counted. Root cause — the game had
  no structured place to record a *repeating* financial fact at all. Currency
  was a single number the AI could only bump for a one-time purchase or
  payment; a recurring job, shop, rent, or stipend had to be remembered and
  manually re-applied by the narrator every time it came due, which drifted
  and silently dropped over a long campaign exactly like training, NPC
  goals, and canon events used to before they got dedicated deterministic
  systems.
- A repeating income or expense the player establishes (a job, a shop's
  regular take, rent, staff wages, a stipend, tribute, upkeep) is now
  recorded as a structured `recurring_finances` entry — label, income or
  expense, amount, interval, and next due day — the same way a promised
  confrontation already becomes a `scheduled_events` entry.
- The application pays each one out automatically as canon_day advances,
  independent of the AI's own memory. A single long time skip correctly
  catches up every cycle it crossed (a year-long skip with a weekly income
  applies all 52 payments, not just one), and each payment leaves a visible
  `[FINANCES]` note in the Chronicle.
- Bleach continues to treat currency as narrative-only, as established
  previously, and worlds that don't track a numeric currency at all are
  likewise excluded — both at the prompt level and, as a hard backstop, in
  the state validator.

## Verification

- 569 automated regression and feature tests pass, including new coverage
  for on-schedule payment, multi-cycle catch-up on a long skip, expenses
  going negative, inactive entries being skipped, and the Bleach/no-currency
  exclusion holding at both the prompt and validator level.
- Python compilation checks pass.
