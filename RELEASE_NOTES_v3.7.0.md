# Worldwalker RPG 3.7.0

Version 3.7.0 focuses on simulation consistency, playability, and lower AI cost.

- Normal AI calls now receive compact, task-specific rules and state instead
  of the entire campaign instruction set on every request.
- Advisor and combat-summary work can use the selected background model.
- Usage reporting separates cached and uncached input tokens and clearly marks
  the displayed dollar estimate as conservative when cache discounts may apply.
- AI portraits are generated on demand by default. Optional automatic portrait
  generation remains available in Settings.
- Finished fights no longer force battlefield art over the player's current
  location, and combat logs no longer repeat earlier rounds in the Chronicle.
- Suggested actions reject completed fights, travel to the current location,
  and unknown invented contacts.
- Profession and knowledge skills no longer appear as combat attacks unless
  they explicitly have a combat use.
- After a time skip resolves, the main control returns to Moment and no longer
  leaves a stale duration selected.
- Mobile Advisor choices wrap into readable rows and leave more room for the
  conversation itself.
- Autosaves use compact JSON, retain three checkpoints, and cap old diagnostic
  history. Manual saves retain six checkpoints for deliberate rollback.
- Generated starter skills now carry explicit combat metadata, and generated
  backgrounds use more natural, concrete prose.

The save schema remains 13. Fresh 3.7 campaigns are recommended.
