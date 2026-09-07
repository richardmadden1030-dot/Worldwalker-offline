# Worldwalker RPG v3.36.0

## Multiplayer combat recovery

- Repairs older multiplayer combat records whose character, enemy, status, or log fields were stored as strings instead of structured data.
- Attack, Defend, Ability, Item, Flee, Nonlethal, and Overwhelm remain usable after the repair instead of failing with `'str' object has no attribute 'get'`.
- The repair happens in place when the round resolves, so affected shared campaigns do not need to be restarted.

## Hunter x Hunter — Nen

- Character creation can start with awakened Nen or keep it latent until it is discovered in the story.
- Every original character receives one persistent, account-unique Hatsu shaped by their background, with an affinity, activation rule, applications, vows, limitations, counters, aura cost, and growth path.
- The Skills view has a dedicated expandable Nen dossier and six-category affinity graph. Latent characters see only the locked potential, without leaking the hidden ability.
- Nen abilities can be rerolled during preview without repeating a previously seen generated ability.

## One Piece — Haki and Devil Fruits

- Character creation can independently grant Observation, Armament, and Conqueror's Haki.
- Players can start with a Devil Fruit; an explicitly described fruit is honored, while an unspecified fruit is generated from the character background.
- Generated fruits include a coherent type, governing power, techniques, limits, counters, and awakening path, and never repeat for the same account.
- Devil Fruits can be rerolled during preview without affecting canon fruits.

## Verification

- All 691 automated tests pass.
- Mobile campaign creation was verified in an iPhone-sized browser, including conditional controls and the full Nen dossier.
- Browser console verification completed without JavaScript errors.
