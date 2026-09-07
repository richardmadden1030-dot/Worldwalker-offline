# Worldwalker RPG 3.2.0

Version 3.2 focuses on narrator quality, reliable information boundaries, causal world simulation, and supportability.

## Narrator evaluation suite

- Six repeatable scenarios test multiple queued actions, long training, canon intervention, concealed classes, overwhelming combat, and NPC secrecy.
- Evaluations call the currently configured narrator model only when the player explicitly starts one.
- Each scenario receives scores for structured output, readability, action coverage, state accuracy, and lore/secrecy compliance.
- Evaluation runs are isolated and never alter the active campaign. The UI shows expected AI-call count before running all scenarios.

## Lore provenance and conflicts

- Lore entries now support source type, citation, and explicit claims.
- Evidence is ranked from official source material through curated references, wikis, forums, fan analysis, imports, and unknown sources.
- Conflicting explicit claims remain visible. The highest-authority source becomes the working resolution while alternatives remain marked as disputed.
- Retrieved GM context includes authority scores and conflict instructions instead of silently blending incompatible statements.

## NPC knowledge boundaries

- Recurring NPCs distinguish confirmed knowledge, hearsay, suspicions, and false beliefs.
- Knowledge records include a believable information path such as witnessing, being told, evidence, reports, research, public information, or inference.
- Unsupported knowledge of concealed player classes, hidden skills, and hidden stats is automatically downgraded to suspicion and recorded in an audit.
- The Journal now includes an NPC Knowledge screen showing exactly what each character believes and why.

## Causal world simulation

- NPC and faction clocks support methods, target locations, travel time, dependencies, resources, costs, and support.
- Missing travel, prerequisites, or resources mechanically block off-screen progress.
- Every clock movement records why it happened; the Journal's World Causality screen shows causes and blockers.

## Campaign health and support

- Campaign Health now offers individually targeted and one-click safe repairs for map discovery, quest structure, skill descriptions, deceased party members, and duplicate rewards.
- Repairs never invent quest solutions, character growth, or narrative outcomes, and every repair is audited.
- A one-click sanitized support ZIP contains version details, diagnostics, campaign state, recent story text, and settings needed to reproduce a problem.
- API keys, tokens, passwords, authorization values, and the user's home-directory path are automatically redacted.

## Validation

- App version: 3.2.0
- Save schema: 9
- Windows executable metadata: 3.2.0.0
- 277 automated tests before final packaging, plus live desktop interface verification.
