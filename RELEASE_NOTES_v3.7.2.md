# Worldwalker RPG 3.7.2

Version 3.7.2 makes character power, training, and original starting powers
use one coherent set of rules.

## Power and Advisor consistency

- Power Summary, Advisor, and GM now receive the same current-stat power
  profile.
- Balanced combat uses offense, speed, and defense together rather than a flat
  arithmetic average that lets one huge specialty mislabel the whole character.
- A peak stat remains fully meaningful and is shown separately from balanced
  combat and overall foundations.
- Current mechanical stats outrank a canon character's original strength,
  starting band, old rank, or stale Advisor estimate.
- Power Summary opens above the Journal and its bars scale relative to the
  current sheet instead of filling completely above 100.

## Training

- Focused training gives smaller gains to every secondary stat, with larger
  gains to world-specific supporting stats.
- Plain `I train` orders become balanced whole-character training, beginning
  with the weakest foundation and improving the full sheet over sufficient
  time.
- Named stats in the action are selected correctly instead of falling back to
  an archetype's first stat.
- Specific in-world training methods receive visible method multipliers.
  Especially effective lore-native methods, such as Naruto shadow-clone
  training, can produce extraordinary targeted development.
- Current mastery, elapsed time, intensity, aptitude, breakthroughs, and method
  quality are all recorded in the training summary.
- Nightmare retains its prior strict single-stat rate and behavior.

## Original classes and abilities

- When a model is configured, character creation asks the lightweight model to
  author an original class, bloodline, or ability from the complete background
  instead of selecting a visible stock result.
- Overgeared hidden classes receive a defining feature, meaningful limits,
  signature skill, rarity cause, class quest/progression route, and a
  canon-relative power budget.
- Naruto kekkei genkai and other original abilities receive a setting-native
  type, origin, coherent applications, costs/counters, growth milestones, and
  a comparison to similar canon power categories.
- Multiple starting techniques returned for claimed abilities are persisted as
  normal readable skills.
- Offline or malformed-model creation still uses validated world-native
  fallbacks, so campaign creation never depends on an AI call succeeding.

## Verification

- Added regressions for the reported 749-Ninjutsu Yahiko sheet, shared Advisor
  state, modal stacking, proportional training, plain training, accelerated
  methods, Nightmare preservation, AI-authored hidden classes, and persisted
  kekkei-genkai techniques.
