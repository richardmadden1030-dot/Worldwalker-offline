# Worldwalker RPG v3.28.0

## Simulation and mechanics

- Added a world-native power benchmark registry used by the Power Summary, Advisor context, and combat calibration.
- Added simultaneous local two-player combat rounds with separate player choices, HP, defense, status control, speed-earned chosen bonus turns, and one shared enemy response.
- Added a mechanics compiler for original abilities: activation, resource, cost, range, targets, duration, cooldown, counterplay, scaling, validation, and mastery stages are filled locally when missing.
- Added semantic near-duplicate detection so renamed or lightly paraphrased generated abilities are rejected and rerolled, while canon abilities may still recur.
- Replaced radius-only political shading with stable polygon territory geometry. Regions can transfer owners, retain contested claimants, merge visually under one controller, and preserve exact borders in saves.

## Lower AI cost

- Common factual Advisor questions about current power, canon countdowns, active objectives, and session cost now answer locally.
- Combat recaps and LitRPG combat XP can resolve locally by default; AI narration remains opt-in through Settings.
- Return summaries are assembled from tracked feeds and clocks locally by default.
- A local relevance gate skips unsolicited-message AI calls when no contact has a plausible reason to write.
- Lore retrieval now uses a persistent local SQLite full-text index with lexical fallback and no summarization call.
- AI context now removes empty scaffolding, UI-only territory vertices, and carries a small recent-state delta alongside existing chapter memory.
- Added separate optional Advisor and character/ability-creator model lanes, each able to inherit, use local inference, or use cloud inference.
- Added a separately routable local image endpoint so portraits can remain local even when text narration is cloud-based.
- Added per-task call, token, cache, and cost telemetry to the usage API and Settings cost summary.

## Presentation

- Power Summary now names the character's setting-specific balanced tier instead of only showing the generic cross-world ladder.
- Contested territory uses a readable hatch overlay and recently changed borders receive a visible highlight.
