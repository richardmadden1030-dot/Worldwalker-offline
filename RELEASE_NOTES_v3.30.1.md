# Worldwalker RPG 3.30.1

This patch restores Advisor context, removes hidden enemy level scaling, and
deepens special-power presentation and combat consequences.

- The Advisor now uses the main GM model unless the player explicitly chooses
  a separate Advisor model. It no longer silently falls back to the cheaper
  background-event model.
- Advisor questions receive question-relevant evidence from the full campaign,
  plus recent continuity, progression, corrections, relationships, faction
  history, rosters, schedules, resolutions, and twenty recent turns.
- Short but meaningful questions are no longer forced into a one-sentence
  low-token reply. Only acknowledgements such as “thanks” use that path.
- The current question is no longer duplicated inside conversation history.
- Advisor instructions now prioritize current state and player corrections,
  distinguish past from present, check contradictions, and answer the exact
  question before adding context.
- Canon countdowns appear only when timing or planning is relevant instead of
  being forced into every answer.
- The local quest shortcut no longer hijacks specific questions about why a
  quest failed or what previously happened.
- Missing enemy combat numbers now use the enemy’s own world-relative role.
  They never derive from the player’s stats.
- Explicit canon-authored enemy power and HP are preserved unchanged. A random
  bandit remains ordinary against a Kage-level player, while a canonically
  overwhelming enemy remains overwhelming.
- Lethal-mode victories now kill defeated enemies by default. Mercy and
  non-lethal choices still subdue them, while immortality or explicit narrative
  protection can prevent death and must be explained in the Chronicle.
- Naruto World Progression now presents Service Record, Chakra Affinity,
  Kekkei Genkai and Dojutsu, then Jinchuriki as four distinct dossiers.
- The expanded Jinchuriki dossier shows the sealed beast, control and bond,
  exact permanent stat and chakra bonuses, available and locked abilities,
  forms, risks, affinities, traits, and progression.
- Jinchuriki bonuses are stored as exact derived values instead of being
  re-estimated differently by the UI and simulation.
- Kekkei Genkai and Dojutsu receive a dedicated expandable panel. Ordinary
  named jutsu remain in Learned Skills without a redundant generic techniques
  panel.
- The generated tailed-beast art sheet contains all nine beasts plus the
  Ten-Tails and is cropped automatically for the character's sealed beast.
- Activating a tailed-beast form, Dojutsu, Shikai, Bankai, Domain Expansion, or
  other recognized transformation now requests a matching portrait variant.
  Ending the form restores the cached normal portrait without another image
  generation call.
- The new Naruto progression layout is responsive and has no horizontal
  overflow at a 430-pixel phone viewport.

Save schema remains 19.
