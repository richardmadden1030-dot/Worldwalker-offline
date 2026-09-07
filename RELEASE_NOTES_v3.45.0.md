# Worldwalker RPG v3.45.0 — A More Consistent GM

- Conditional and negative actions no longer count as immediate violence. Pronoun candidates remain grounded in the live scene rather than guessed.
- Loyal subordinates with established command relationships must preserve the player's actual order. Refusal or deviation needs an existing reason, including in NPC chat.
- Reactions use references to actual campaign evidence. Reports cannot cause reactions before delivery; merely mentioning a distant character does not make them a witness.
- Named learned skills need mechanics, refused purchases do not award items, and explicit skill/title losses or recovered conditions are not mistakenly re-added.
- Current roles, affiliations and relationships take precedence over historical summaries. Changes retain bounded history, and knowledge keeps its original timestamps.
- NPC conversations receive relevant goals, loyalties, experiences and beliefs without treating every exchange as a new problem.
- Explicitly routine time-skip updates group by activity while retaining concrete progress, milestones, rewards and decisions. Routine progress alone is not a reason to interrupt.
- A detected contradiction gets one targeted repair with the original draft. Unresolved checked contradictions are rejected before application; valid turns need no additional AI call.
- Outcome-based evaluation cases supplement keyword checks. Multi-turn regressions cover hidden skills, real save import/load and combat usability across all nine worlds.

## Compatibility and scope

Works with existing saves (schema 20); no new campaign is required. Old Chronicle prose is not rewritten. Current facts are derived from the loaded save, with new change history accumulating during subsequent play. Offline prototype and visual layouts are unchanged.

Checks enforce verifiable contracts, not perfect understanding of arbitrary prose. Independent NPCs retain agency, and genuine inability or conflicting loyalties can still prevent an order. No paid live-model evaluation was used for this release; automated tests use deterministic responses and actual engine/save paths.

Validation: 846 automated tests and 54 subtests passed; frontend JavaScript and service-worker syntax checks passed. Both Windows and phone-host packaged startup self-tests passed.
