# Worldwalker RPG v3.15.0

## Mechanical combat conditions

- Paralysis, stun, sleep, freezing, immobilization, restraint and equivalent hard-control labels now consume the affected combatant's action.
- Weakening now reduces real power, accuracy, defense, speed and damage instead of only displaying a condition name.
- Enemy attacks may carry authored control or debuff effects, which persist for their stated duration and can be cleansed.
- Reapplied conditions refresh cleanly without duplicate chips or an unavoidable permanent paralysis loop.
- Combat condition chips now show their mechanical percentages and clearly say when a combatant cannot act.

## Intensity-aware character creation

- Background language now has sharply graded mechanical weight: talented, prodigy, immense, legendary, godlike and immeasurable are distinct starting scales.
- Explicitly extreme characters can begin above 1,000 world-relative stats when requested; there is no hidden cap or automatic normalization toward average.
- Age-relative claims such as being a prodigy or stronger than peers increase both starting stats and learning aptitude.
- Named specialties receive an additional matching-stat emphasis, and derived health/energy pools scale from the final values.
- Generated abilities and hidden classes receive mastery/rank descriptions consistent with the claimed starting power.
- Extreme combat power no longer accidentally produces extreme starting wealth.

## AI cost

- No additional model calls were added. Combat status resolution and language-to-stat scaling are local mechanics.
